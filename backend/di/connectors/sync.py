"""Sync one source into the canonical store (docs/backend-steps.md, B9).

    run_sync("erp", trigger="manual")            → {"run_id", "status", "records_read", "facts_written", …}
    enqueue_sync(session, "erp", "webhook")       → queue a job for the worker (once: no duplicates while queued)
    enqueue_due(session)                          → queue every source whose interval has passed (worker, every 30 s)

Status of a source after a run: live (ok or partial), failing (the system did not answer), auth_expired (credentials
refused). paused / disconnected / unavailable are set by people (Connection Fabric) and are never synced, nor is a
deleted source (di.connectors.lifecycle).

**A sync is the run of the source's ingest workflow (plan 6 C5).** run_sync keeps what a sync owns (the per-source
lock, the sync_run row, the credential check, the source's status, completeness and retry schedule) and hands the data
to the workflow engine (di.workflow.engine.run_graph) with a Feed on its client: the published ingest workflow bound to
the source (di.workflow.binding), else the default ingest graph, whose steps pass every record on unchanged, so the
canonical data and provenance are exactly what the adapter (and the saved field mapping) produce
(tests/test_workflow_engine.py, test_engine_parity_canonical). Reading, raw records, cursors, mapping, the canonical
writes and the held records are the engine's. A bound workflow handles the resources its connector reads; the
source's other resources are read through the default graph narrowed to them (binding.rest_graph), in the same
sync_run, whose counts are both parts' (tests/test_sync_binding.py).
"""

import functools
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from di.connectors import connection, lifecycle, manual, mapping, mcp_client
from di.connectors.http import SourceError
from di.connectors.registry import ADAPTERS, adapter_for, has_adapter, python_adapter
from di.core import golden
from di.core.db import SessionLocal, engine
from di.core.jobs import enqueue
from di.services.canonical import store
from di.services.cases import record_match
from di.workflow import binding
from di.workflow.engine import Feed, run_graph

log = logging.getLogger("di.sync")
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
    session.execute(  # the demo's sources only: a source created in the Connection Fabric has no connector by design
        text("UPDATE source_system SET status = 'unavailable', updated_at = now() WHERE NOT (id = ANY(:ids)) AND id = ANY(:ref)"),
        {"ids": list(ADAPTERS), "ref": [s["id"] for s in golden.load("sources")["sources"]]},
    )
    for sid, a in ADAPTERS.items():
        if a.connected_confidence is not None:
            _connected_confidence(session, sid, a.connected_confidence)
    connection.seed_demo(session)  # their connections: source-sim's mocks (plan 6 A2)
    session.commit()
    for sid, a in ADAPTERS.items():  # configured to start connected (DI_IOT_CONNECTED): its rules deliver from the start
        if hasattr(a, "set_delivery") and provisioned(sid):
            _set_delivery(a, True)


SOURCE_TABLES = ("sync_run", "fetch_log", "raw_record", "sync_cursor")  # rows kept per source


def reset_sources(conn: Connection) -> None:
    """Back to the demo's sources, for the demo reset (tests/starting.py, scripts/reset_starting.py).

    Sources created in the Connection Fabric (from the catalogue or by hand) are removed with their sync history and
    queued syncs. The demo's own sources get back their reference description (vendor, interval, owner, note) and,
    their starting status when a person paused or disconnected them or a sync left them failing or auth_expired (the
    secrets a person rotated are deleted too, so the next sync decides again from the demo's credentials; plan 6: the
    workflow checks read these statuses), and no retry schedule. Connector data of the demo's sources is kept."""
    ref = golden.load("sources")["sources"]
    ids = [s["id"] for s in ref]
    made = list(conn.execute(text("SELECT id FROM source_system WHERE NOT (id = ANY(:i))"), {"i": ids}).scalars())
    conn.execute(text("DELETE FROM source_secret"))  # credentials stored in the app (plan 6 A1)
    manual.remove(Session(bind=conn))  # Manual Import data (plan 6 B3); the imports list is reset with the workspace
    connection.reset_demo(conn, ids)  # the demo sources' connections back on source-sim (plan 6 A2)
    conn.execute(text("DELETE FROM field_mapping"))  # edited mappings (plan 6 A4): every source maps as its code does
    if made:
        for t in SOURCE_TABLES:
            conn.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = ANY(:i)"), {"i": made})
        conn.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": made})
    for s in ref:
        start = "live" if provisioned(s["id"]) else "unavailable"
        conn.execute(
            text(
                "UPDATE source_system SET vendor = :v, interval_min = :iv, owner = :o, note = :n, "
                "status = CASE WHEN status IN ('paused', 'disconnected', 'failing', 'auth_expired') OR (:st = 'unavailable') "
                "THEN :st ELSE status END, fail_streak = 0, next_retry_at = NULL, org_unit_id = NULL "  # 0020: shared
                "WHERE id = :id"
            ),
            {
                "id": s["id"],
                "v": VENDOR_OVERRIDES.get(s["id"], s["vendor"]),
                "iv": int(s.get("interval") or 0),
                "o": s.get("owner"),
                "n": s.get("note"),
                "st": start,
            },
        )


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
    job = mark_connected(session, source_id, status) if changed else None
    session.commit()
    _set_delivery(adapter, True)
    return {"source_id": source_id, "status": "live" if changed else status, "connected": changed, "queued_job": job}


def mark_connected(session: Session, source_id: str, was: str) -> int | None:
    """Make a source `live` again in the caller's transaction (no commit) and queue its sync: a full initial sync
    when it was not provisioned (`unavailable`), else a manual one. Returns the queued job (None if one is waiting).
    A source without a connector (created in the Connection Fabric) only becomes live."""
    session.execute(text("UPDATE source_system SET status = 'live', updated_at = now() WHERE id = :i"), {"i": source_id})
    adapter = python_adapter(source_id)  # another instance's too (plm_wc_2, plan 8 MVP-9.3)
    if adapter is None:
        return None
    if adapter.connected_confidence is not None:
        _connected_confidence(session, source_id, adapter.connected_confidence)
    if was == "unavailable":
        return enqueue_sync(session, source_id, "initial", full=True)
    return enqueue_sync(session, source_id, "manual")


def drop_queued(session: Session, source_id: str) -> None:
    """Forget the source's sync jobs that have not started (pause, disconnect, delete); a running one finishes."""
    session.execute(
        text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"),
        {"s": source_id},
    )


def set_delivery(source_id: str, enabled: bool) -> None:
    """Switch the source's own event delivery on or off (AWS IoT topic rules), where it has one."""
    if (adapter := ADAPTERS.get(source_id)) is not None:
        _set_delivery(adapter, enabled)


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
    drop_queued(session, source_id)
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
    ref: dict[str, Any] = next((s for s in golden.load("sources")["sources"] if s["id"] == source_id), {})
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


# ---------------------------------------------------------------- one sync per source, retries (plan 6 A6)
def _one_at_a_time(fn):
    """One sync of a source at a time, and its retry schedule.

    The lock is `pg_try_advisory_xact_lock(hashtext('sync:' || source_id))`, held by a transaction on a connection of
    its own for the whole run (the sync commits as it goes, which would release a lock taken in its own session). A sync
    of a source that is already syncing returns `skipped` / `running` and records no run. The lock goes when the run
    ends, or with the connection if the process dies.

    After the run: a failed one adds 1 to `fail_streak` and sets `next_retry_at` = last sync + min(2**fail_streak
    minutes, the source's interval), which enqueue_due honours; any other finished run resets both."""

    @functools.wraps(fn)
    def run(source_id: str, *args, **kw) -> dict:
        with engine.connect() as lock:
            got = lock.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('sync:' || :s))"), {"s": source_id}).scalar()
            if not got:
                lock.rollback()
                return {"source_id": source_id, "status": "skipped", "reason": "running"}
            try:
                out = fn(source_id, *args, **kw)
                if out.get("status") in ("ok", "partial", "failed"):
                    _settle_streak(source_id, out["status"] == "failed")
                return out
            finally:
                lock.rollback()  # releases the lock

    return run


def _settle_streak(source_id: str, failed: bool) -> None:
    with SessionLocal() as s:
        if failed:
            s.execute(
                text(
                    "UPDATE source_system SET fail_streak = fail_streak + 1, next_retry_at = coalesce(last_sync_at, now()) "
                    "+ make_interval(mins => least(CAST(power(2, least(fail_streak + 1, 20)) AS integer), "
                    "CASE WHEN interval_min > 0 THEN interval_min ELSE :safety END)) WHERE id = :i"
                ),
                {"i": source_id, "safety": SAFETY_INTERVAL_MIN},
            )
        else:
            s.execute(
                text(
                    "UPDATE source_system SET fail_streak = 0, next_retry_at = NULL "
                    "WHERE id = :i AND (fail_streak > 0 OR next_retry_at IS NOT NULL)"
                ),
                {"i": source_id},
            )
        s.commit()


@_one_at_a_time
def run_sync(source_id: str, trigger: str = "manual", full: bool = False) -> dict:
    with SessionLocal() as s:
        # an MCP connection (plan 8 MVP-11.7, di.connectors.mcp_client), else the Python adapter, or the configured one
        adapter = mcp_client.adapter_for(s, source_id) or adapter_for(s, source_id)
        if adapter is None:
            raise KeyError(f"No adapter for {source_id}")
        src = s.execute(text("SELECT status, confidence FROM source_system WHERE id = :i"), {"i": source_id}).first()
        if src is None:  # a connector beyond the demo's sources that nobody registered yet (di.connectors.extra)
            return {"source_id": source_id, "status": "skipped", "reason": "not registered"}
        if src.status in NOT_SYNCED:
            return {"source_id": source_id, "status": "skipped", "reason": src.status}
        if lifecycle.is_deleted(s, source_id):
            return {"source_id": source_id, "status": "skipped", "reason": "deleted"}
        if connection.in_test(s, source_id):  # plan 9 P9-8.1: promoted to production before it is synced
            return {"source_id": source_id, "status": "skipped", "reason": "test environment"}
        run_id = s.execute(
            text("INSERT INTO sync_run (source_id, trigger, status) VALUES (:s, :t, 'running') RETURNING id"),
            {"s": source_id, "t": trigger},
        ).scalar_one()
        s.commit()
        conf = float(src.confidence) if src and src.confidence is not None else None
        client = connection.client_for(s, source_id, adapter, run_id)  # its URL and stored secret (plan 6 A2)
        # the field mapping a person saved, over a Python adapter's own (plan 6 A4); None: the adapter's mapping as is
        remap = mapping.mapper(s, source_id, source_id in ADAPTERS)
        # plan 6 C5: the sync is the run of the source's ingest workflow (the bound published one, else the default
        # graph, whose steps pass every record on: the canonical data is what the adapter maps, as before)
        wf, graph = binding.bound(s, source_id)
        parts = [(wf, graph, Feed(source_id, adapter, client, run_id, full, conf, remap))]
        # the resources a bound workflow does not read sync through the default graph, in this same run
        if wf.get("id") and (rest := binding.unread(graph, source_id, [r.name for r in adapter.resources()])):
            rest_feed = Feed(source_id, adapter, client, run_id, full, conf, remap)
            parts.append((binding.default_wf(source_id), binding.rest_graph(source_id, rest), rest_feed))
        status, error, new_status = "ok", None, "live"
        held = 0
        try:
            connection.check_credential(s, source_id)  # an expired stored credential is not used (plan 6 A5)
            for w, g, feed in parts:
                res = run_graph(s, w, g, trigger=trigger, feeds={source_id: feed}, run_id=run_id, run_kind="sync", full=full)
                # records a step of the workflow held (validation ...) count as failed, beside those not stored
                held += sum(c["rej"] for n, c in res.counts.items() if _is_xf(g, n))
                if res.status == "failed":
                    if status != "failed":
                        status, error = "failed", (res.error or "the sync failed")[:500]
                    if res.error_kind is not None:  # the system did not answer, or refused the credential
                        new_status = "auth_expired" if res.error_kind == "auth" else "failing"
                        break
        except SourceError as e:
            s.rollback()
            status, error = "failed", str(e)[:500]
            new_status = "auth_expired" if e.kind == "auth" else "failing"
        finally:
            client.close()
        read, written = sum(p[2].read for p in parts), sum(p[2].written for p in parts)
        failed = sum(p[2].failed for p in parts) + (held if status != "failed" else 0)
        if status == "ok" and failed:
            first = next((p[2].first_error for p in parts if p[2].first_error), None)
            status, error = "partial", first or f"{failed} records held by {wf.get('name')}"
        if status != "failed" and (after := getattr(adapter, "after_sync", None)) is not None:
            try:  # an adapter's own follow-up once its records are stored (fleet non-return items, P9-3.18); never fails the sync
                with s.begin_nested():
                    after(s)
            except Exception:
                log.exception("after_sync of %s failed", source_id)
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
        if status != "failed" and record_match.is_record_source(s, source_id):  # the pack's system of record (P9-1.10)
            enqueue(s, "case.recordMatch", {"source_id": source_id}, dedupe_key=f"case.recordMatch:{source_id}")
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


def _is_xf(graph: dict, nid: str) -> bool:
    return any(n.get("id") == nid and n.get("k") == "xf" for n in graph.get("nodes") or [])


def enqueue_sync(session: Session, source_id: str, trigger: str, full: bool = False) -> int | None:
    """Queue a sync job unless one for this source is already waiting. Returns the job id (None if already queued, or when
    the source's connection is in the test environment: only test runs and discovery read it, plan 9 P9-8.1)."""
    if connection.in_test(session, source_id):
        return None
    waiting = session.execute(
        text("SELECT id FROM job WHERE kind = 'sync.source' AND status IN ('queued','running') AND payload->>'source_id' = :s"),
        {"s": source_id},
    ).first()
    if waiting:
        return None
    return enqueue(session, "sync.source", {"source_id": source_id, "trigger": trigger, "full": full}).id


def enqueue_due(session: Session, now: datetime | None = None) -> list[str]:
    """`now` defaults to the wall clock (the sync times are the database's now()); tests pass one."""
    now = now or datetime.now(UTC)
    queued = []
    gone = lifecycle.deleted(session)
    rows = session.execute(
        text("SELECT id, status, interval_min, last_sync_at, next_retry_at FROM source_system ORDER BY id")
    ).all()
    for r in rows:
        if r.status in NOT_SYNCED or r.id in gone or not has_adapter(session, r.id):  # Python or configured (A3)
            continue
        every = timedelta(minutes=r.interval_min or SAFETY_INTERVAL_MIN)
        due = r.last_sync_at is None or now - r.last_sync_at >= every
        if r.next_retry_at is not None:  # a failing source: its retry time (never later than the interval) decides
            due = now >= r.next_retry_at
        if due and enqueue_sync(session, r.id, "initial" if r.last_sync_at is None else "schedule"):
            queued.append(r.id)
    session.commit()
    return queued
