"""Sync one source into the canonical store (docs/backend-steps.md, B9).

    run_sync("erp", trigger="manual")            → {"run_id", "status", "records_read", "facts_written", …}
    enqueue_sync(session, "erp", "webhook")       → queue a job for the worker (once: no duplicates while queued)
    enqueue_due(session)                          → queue every source whose interval has passed (worker, every 30 s)

Status of a source after a run: live (ok or partial), failing (the system did not answer), auth_expired (credentials
refused). paused / disconnected / unavailable are set by people (Connection Fabric) and are never synced.
"""

import json
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from di import golden
from di.canonical import store
from di.config import get_settings
from di.connectors.http import SourceClient, SourceError
from di.connectors.registry import ADAPTERS
from di.db import SessionLocal
from di.jobs import enqueue

log = logging.getLogger("di.sync")
COMMIT_EVERY = 200
NOT_SYNCED = ("paused", "disconnected", "unavailable")
SAFETY_INTERVAL_MIN = 60  # event-driven sources (interval 0) still get a full check every hour
# vendors replaced on purpose (docs/backend-steps.md, B5b); the same list as source-sim's registry
VENDOR_OVERRIDES = {"tms": "Oracle Transportation Management"}  # was the fictional "ShipLane TMS"


def provisioned(source_id: str) -> bool:
    """A connector exists and the source starts connected. AWS IoT (B5c) has a connector but starts not provisioned,
    as in the demo, until it is connected (connect_source) or configured to start connected (DI_IOT_CONNECTED)."""
    a = ADAPTERS.get(source_id)
    return a is not None and bool(getattr(a, "provisioned", True))


def ensure_sources(session: Session) -> None:
    """Register the demo's 21 sources once (vendor, type, interval, authority, owner)."""
    for s in golden.load("sources")["sources"]:
        status = "live" if provisioned(s["id"]) else "unavailable"
        session.execute(
            text(
                "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner, confidence, note) "
                "VALUES (:id, :v, :t, :st, :i, :a, :o, :c, :n) ON CONFLICT (id) DO UPDATE SET vendor = EXCLUDED.vendor"
            ),
            {
                "id": s["id"],
                "v": VENDOR_OVERRIDES.get(s["id"], s["vendor"]),
                "t": s["type"],
                "st": status,
                "i": int(s.get("interval") or 0),
                "a": s.get("authority") or [],
                "o": s.get("owner"),
                "c": s.get("conf"),
                "n": s.get("note"),
            },
        )
    # a source that gained (or lost) a connector since it was registered
    session.execute(
        text("UPDATE source_system SET status = 'live', updated_at = now() WHERE status = 'unavailable' AND id = ANY(:ids)"),
        {"ids": [i for i in ADAPTERS if provisioned(i)]},
    )
    session.execute(
        text("UPDATE source_system SET status = 'unavailable', updated_at = now() WHERE NOT (id = ANY(:ids))"),
        {"ids": list(ADAPTERS)},
    )
    for sid, a in ADAPTERS.items():
        if getattr(a, "connected_confidence", None) is not None:
            _connected_confidence(session, sid, a.connected_confidence)
    session.commit()
    for sid, a in ADAPTERS.items():  # configured to start connected (DI_IOT_CONNECTED): its rules deliver from the start
        if hasattr(a, "set_delivery") and provisioned(sid):
            _set_delivery(a, True)


def _connected_confidence(session: Session, source_id: str, conf: float) -> None:
    """A source the demo lists with confidence 0 (no data yet) gets its connector's confidence once connected."""
    session.execute(
        text(
            "UPDATE source_system SET confidence = :c WHERE id = :i AND status <> 'unavailable' "
            "AND coalesce(confidence, 0) = 0"
        ),
        {"c": conf, "i": source_id},
    )


def connect_source(session: Session, source_id: str) -> dict:
    """Connect (provision) a source that has a connector but is not provisioned, e.g. AWS IoT (B5c): it becomes
    `live` and a full initial sync is queued. A source that is already connected is left as it is."""
    adapter = ADAPTERS.get(source_id)
    if adapter is None:
        raise KeyError(f"No connector for {source_id}")
    status = session.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": source_id}).scalar()
    if status is None:
        raise KeyError(f"No source {source_id}")
    changed = status == "unavailable"
    if changed:
        session.execute(text("UPDATE source_system SET status = 'live', updated_at = now() WHERE id = :i"), {"i": source_id})
        if getattr(adapter, "connected_confidence", None) is not None:
            _connected_confidence(session, source_id, adapter.connected_confidence)
    job = enqueue_sync(session, source_id, "initial", full=True) if changed else None
    session.commit()
    _set_delivery(adapter, True)
    return {"source_id": source_id, "status": "live" if changed else status, "connected": changed, "queued_job": job}


def _set_delivery(adapter, enabled: bool) -> None:
    """Switch the source's own event delivery on or off where the system has one (AWS IoT topic rules). A failure is
    logged, not raised: syncs still read the system, and the next connect or disconnect tries again."""
    fn = getattr(adapter, "set_delivery", None)
    if fn is None:
        return
    try:
        fn(enabled)
    except Exception:  # noqa: BLE001 - the system may be down; the connection itself is recorded either way
        log.warning("could not %s event delivery for %s", "enable" if enabled else "disable", adapter.source_id, exc_info=True)


def disconnect_source(session: Session, source_id: str, purge: bool = False) -> dict:
    """Back to not provisioned (`unavailable`), as the demo starts AWS IoT. With purge, everything the source brought
    is removed too: its facts (the canonical values fall back to the other sources, its conflicts are deleted), raw
    records, cursors, runs and fetch log, and its completeness, confidence and sync times go back to the demo's."""
    if session.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": source_id}).first() is None:
        raise KeyError(f"No source {source_id}")
    session.execute(
        text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"),
        {"s": source_id},
    )
    session.execute(text("UPDATE source_system SET status = 'unavailable', updated_at = now() WHERE id = :i"), {"i": source_id})
    out = {"source_id": source_id, "status": "unavailable", "purged": purge}
    if purge:
        out["facts_removed"] = _purge(session, source_id)
    session.commit()
    if (adapter := ADAPTERS.get(source_id)) is not None:
        _set_delivery(adapter, False)
    return out


def _purge(session: Session, source_id: str) -> int:
    touched = session.execute(
        text("DELETE FROM provenance WHERE source_id = :s RETURNING model, key, field"), {"s": source_id}
    ).all()
    now = datetime.now(UTC)
    for model, key, field in sorted(set(touched)):
        left = session.execute(
            text("SELECT count(*) FROM provenance WHERE model = :m AND key = :k AND field = :f"),
            {"m": model, "k": key, "f": field},
        ).scalar_one()
        if left:
            store._settle(session, model, key, field, now)  # the other sources' value again
        else:
            session.execute(
                text(
                    "UPDATE canonical SET data = data - CAST(:f AS text), version = version + 1, updated_at = :at "
                    "WHERE model = :m AND key = :k AND jsonb_exists(data, CAST(:f AS text))"
                ),
                {"m": model, "k": key, "f": field, "at": now},
            )
    for model, key in sorted({(m, k) for m, k, _ in touched}):
        session.execute(
            text("DELETE FROM canonical WHERE model = :m AND key = :k AND data = '{}'::jsonb"), {"m": model, "k": key}
        )
    session.execute(text('DELETE FROM conflict WHERE jsonb_exists("values", :s)'), {"s": source_id})
    for table in ("raw_record", "sync_cursor", "fetch_log", "sync_run"):
        session.execute(text(f"DELETE FROM {table} WHERE source_id = :s"), {"s": source_id})  # noqa: S608 - fixed names
    session.execute(
        text("DELETE FROM job WHERE kind = 'sync.source' AND status <> 'running' AND payload->>'source_id' = :s"),
        {"s": source_id},
    )
    ref = next((s for s in golden.load("sources")["sources"] if s["id"] == source_id), {})
    session.execute(  # as registered by ensure_sources: no completeness or sync times yet, the demo's confidence
        text(
            "UPDATE source_system SET completeness = NULL, confidence = :cf, last_sync_at = NULL, last_success_at = NULL "
            "WHERE id = :i"
        ),
        {"cf": ref.get("conf"), "i": source_id},
    )
    return len(touched)


def _cursor(session: Session, source_id: str, resource: str) -> str | None:
    return session.execute(
        text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = :r"), {"s": source_id, "r": resource}
    ).scalar()


def _set_cursor(session: Session, source_id: str, resource: str, cursor: str) -> None:
    session.execute(
        text(
            "INSERT INTO sync_cursor (source_id, resource, cursor) VALUES (:s, :r, :c) "
            "ON CONFLICT (source_id, resource) DO UPDATE SET cursor = EXCLUDED.cursor, updated_at = now()"
        ),
        {"s": source_id, "r": resource, "c": cursor},
    )


def run_sync(source_id: str, trigger: str = "manual", full: bool = False) -> dict:
    adapter = ADAPTERS.get(source_id)
    if adapter is None:
        raise KeyError(f"No adapter for {source_id}")
    with SessionLocal() as s:
        src = s.execute(text("SELECT status, confidence FROM source_system WHERE id = :i"), {"i": source_id}).first()
        if src and src.status in NOT_SYNCED:
            return {"source_id": source_id, "status": "skipped", "reason": src.status}
        run_id = s.execute(
            text("INSERT INTO sync_run (source_id, trigger, status) VALUES (:s, :t, 'running') RETURNING id"),
            {"s": source_id, "t": trigger},
        ).scalar_one()
        s.commit()
        conf = float(src.confidence) if src and src.confidence is not None else None
        client = SourceClient(source_id, get_settings().source_sim_url + adapter.base_path, adapter.auth(), s, run_id)
        read = written = failed = 0
        status, error = "ok", None
        try:
            for res in adapter.resources():
                since = None if (full or not res.delta) else _cursor(s, source_id, res.name)
                newest = since
                failed_here = 0
                for rec in res.read(client, since):
                    read += 1
                    s.execute(
                        text(
                            "INSERT INTO raw_record (source_id, resource, ext_id, payload, request, fetched_at) "
                            "VALUES (:s, :r, :e, CAST(:p AS jsonb), :q, now()) ON CONFLICT (source_id, resource, ext_id) "
                            "DO UPDATE SET payload = EXCLUDED.payload, request = EXCLUDED.request, fetched_at = now()"
                        ),
                        {
                            "s": source_id,
                            "r": rec.resource,
                            "e": rec.ext_id,
                            "p": json.dumps(rec.payload, default=str),
                            "q": rec.request,
                        },
                    )
                    for attempt in range(3):
                        try:
                            with s.begin_nested():
                                facts = [
                                    f if f.resource else type(f)(**{**f.__dict__, "resource": rec.resource, "ext_id": rec.ext_id})
                                    for f in adapter.map(rec)
                                ]
                                written += store.apply(s, source_id, facts, conf)
                            break
                        except OperationalError as e:  # a deadlock with a concurrent sync: try the record again
                            if "deadlock" not in str(e).lower() or attempt == 2:
                                failed, failed_here = failed + 1, failed_here + 1
                                status, error = "partial", error or f"{rec.resource}/{rec.ext_id}: {str(e).splitlines()[0]}"[:500]
                                break
                            time.sleep(0.05 * (attempt + 1))
                        except Exception as e:  # noqa: BLE001 - a record that cannot be mapped is counted, not fatal
                            failed, failed_here = failed + 1, failed_here + 1
                            status = "partial"
                            error = error or f"{rec.resource}/{rec.ext_id}: {type(e).__name__}: {e}"[:500]
                            log.warning("map failed %s %s/%s: %s", source_id, rec.resource, rec.ext_id, e)
                            break
                    if rec.changed and (newest is None or rec.changed > newest):
                        newest = rec.changed
                    if read % COMMIT_EVERY == 0:
                        s.commit()
                # a resource with failed records keeps its old cursor, so the next sync reads them again
                if res.delta and newest and not failed_here:
                    _set_cursor(s, source_id, res.name, newest)
                s.commit()
            new_status = "live"
        except SourceError as e:
            s.rollback()
            status, error = "failed", str(e)[:500]
            new_status = "auth_expired" if e.kind == "auth" else "failing"
        finally:
            client.close()
        s.execute(
            text(
                "UPDATE sync_run SET status = :st, finished_at = now(), records_read = :r, facts_written = :w, "
                "records_failed = :f, "
                "error = :e WHERE id = :id"
            ),
            {"st": status, "r": read, "w": written, "f": failed, "e": error, "id": run_id},
        )
        s.execute(
            text(
                "UPDATE source_system SET status = CASE WHEN status IN ('paused','disconnected','unavailable') "
                "THEN status ELSE :ns END, "
                "last_sync_at = now(), last_success_at = CASE WHEN :ok THEN now() ELSE last_success_at END, updated_at = now(), "
                "completeness = CASE WHEN :ok AND :r > 0 THEN round(100.0 * (:r - :f) / :r, 2) ELSE completeness END "
                "WHERE id = :s"
            ),
            {"ns": new_status, "ok": status != "failed", "r": read, "f": failed, "s": source_id},
        )
        s.commit()
    return {
        "run_id": run_id,
        "source_id": source_id,
        "status": status,
        "records_read": read,
        "facts_written": written,
        "records_failed": failed,
        "error": error,
    }


def enqueue_sync(session: Session, source_id: str, trigger: str, full: bool = False) -> int | None:
    """Queue a sync job unless one for this source is already waiting. Returns the job id (None if already queued)."""
    waiting = session.execute(
        text("SELECT id FROM job WHERE kind = 'sync.source' AND status IN ('queued','running') AND payload->>'source_id' = :s"),
        {"s": source_id},
    ).first()
    if waiting:
        return None
    return enqueue(session, "sync.source", {"source_id": source_id, "trigger": trigger, "full": full}).id


def enqueue_due(session: Session) -> list[str]:
    now = datetime.now(UTC)
    queued = []
    for r in session.execute(text("SELECT id, status, interval_min, last_sync_at FROM source_system ORDER BY id")).all():
        if r.id not in ADAPTERS or r.status in NOT_SYNCED:
            continue
        every = timedelta(minutes=r.interval_min or SAFETY_INTERVAL_MIN)
        due = r.last_sync_at is None or now - r.last_sync_at >= every
        if due and enqueue_sync(session, r.id, "initial" if r.last_sync_at is None else "schedule"):
            queued.append(r.id)
    session.commit()
    return queued
