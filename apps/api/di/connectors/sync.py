"""Sync one source into the canonical store (docs/BACKEND_STEPS.md, B9).

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
# vendors replaced on purpose (docs/BACKEND_STEPS.md, B5b); the same list as source-sim's registry
VENDOR_OVERRIDES = {"tms": "Oracle Transportation Management"}  # was the fictional "ShipLane TMS"


def ensure_sources(session: Session) -> None:
    """Register the demo's 21 sources once (vendor, type, interval, authority, owner)."""
    for s in golden.load("sources")["sources"]:
        status = "unavailable" if s["id"] not in ADAPTERS else "live"
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
        {"ids": list(ADAPTERS)},
    )
    session.execute(
        text("UPDATE source_system SET status = 'unavailable', updated_at = now() WHERE NOT (id = ANY(:ids))"),
        {"ids": list(ADAPTERS)},
    )
    session.commit()


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
        if r.last_sync_at is None or now - r.last_sync_at >= every:
            if enqueue_sync(session, r.id, "initial" if r.last_sync_at is None else "schedule"):
                queued.append(r.id)
    session.commit()
    return queued
