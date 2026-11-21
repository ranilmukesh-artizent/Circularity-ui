"""Plan 6 A6: sync reliability. A source GET is retried on 429, 5xx and timeouts; one sync per source at a time; a
failing source is retried after 2, 4, 8 … minutes (capped at its interval), not only after a full interval.

Needs source-sim (faults on Machinio, `dlr`: API key auth, so no token call is hit by the fault). The backoff waits
are replaced by a recorder (`_sleep`), so these tests do not wait; the suite's base wait is tiny anyway (conftest).
"""

import threading
import time
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import text

from di.config import get_settings
from di.connectors import http as source_http
from di.connectors.http import ApiKey, SourceClient, SourceError
from di.connectors.sync import enqueue_due, ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
SID = "dlr"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def drop_sync_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


def streak() -> tuple:
    with SessionLocal() as s:
        return s.execute(
            text("SELECT fail_streak, last_sync_at, next_retry_at, status FROM source_system WHERE id = :i"), {"i": SID}
        ).one()


@pytest.fixture(scope="module", autouse=True)
def machinio():
    sim("DELETE", "/_sim/faults", params={"system": SID})
    with SessionLocal() as s:
        ensure_sources(s)
    yield
    sim("DELETE", "/_sim/faults", params={"system": SID})
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_system SET interval_min = 0 WHERE id = :i"), {"i": SID})
    run_sync(SID, "manual")  # back to live, streak cleared
    drop_sync_jobs()


@pytest.fixture
def waits(monkeypatch):
    """The backoff waits, recorded instead of slept."""
    seen: list[float] = []
    monkeypatch.setattr(source_http, "_sleep", seen.append)
    return seen


# ---------------------------------------------------------------- SourceClient retries (no source-sim)
def mock_client(session, handler) -> SourceClient:
    c = SourceClient("test", "http://source.test", ApiKey("X-Api-Key", "k"), session)
    c.http.close()
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def answers(*items):
    """A transport handler that answers `items` in turn: an int status, (status, headers), or an exception class."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        item = items[len(calls)]
        calls.append(request.method)
        if isinstance(item, type) and issubclass(item, Exception):
            raise item("simulated", request=request)
        status, headers = item if isinstance(item, tuple) else (item, {})
        return httpx.Response(status, headers=headers, json={"ok": status < 400})

    return handler, calls


def test_get_is_retried_on_429_5xx_and_timeouts_with_backoff(session, waits):
    base = get_settings().source_retry_base_seconds
    handler, calls = answers(503, 429, httpx.ReadTimeout, 200)
    c = mock_client(session, handler)
    assert c.get_json("/x") == {"ok": True}
    assert len(calls) == 4 and waits == [base, base * 2, base * 4]
    session.rollback()


def test_retry_after_is_honoured_up_to_30_seconds(session, waits):
    handler, _ = answers((429, {"Retry-After": "7"}), (503, {"Retry-After": "120"}), 200)
    assert mock_client(session, handler).get_json("/x") == {"ok": True}
    assert waits == [7.0, 30.0]
    session.rollback()


def test_retries_stop_after_three_and_raise(session, waits):
    handler, calls = answers(503, 503, 503, 503)
    with pytest.raises(SourceError) as e:
        mock_client(session, handler).get_json("/x")
    assert e.value.kind == "unavailable" and e.value.status == 503 and len(calls) == 4 and len(waits) == 3
    handler, calls = answers(httpx.ConnectTimeout, httpx.ConnectTimeout, httpx.ConnectTimeout, httpx.ConnectTimeout)
    with pytest.raises(SourceError) as e:
        mock_client(session, handler).get_json("/x")
    assert e.value.kind == "unavailable" and len(calls) == 4
    session.rollback()


def test_writes_and_client_errors_are_not_retried(session, waits):
    handler, calls = answers(503)
    with pytest.raises(SourceError):
        mock_client(session, handler).request("POST", "/x", json={})
    handler2, calls2 = answers(404)
    with pytest.raises(SourceError) as e:
        mock_client(session, handler2).get_json("/x")
    handler3, calls3 = answers(httpx.ConnectError)  # refused or unknown host: not a timeout, fails at once
    with pytest.raises(SourceError):
        mock_client(session, handler3).get_json("/x")
    assert (len(calls), len(calls2), len(calls3), e.value.kind, waits) == (1, 1, 1, "client", [])
    session.rollback()


def test_a_401_still_refreshes_once_without_backoff(session, waits):
    handler, calls = answers(401, 200)
    assert mock_client(session, handler).get_json("/x") == {"ok": True}
    assert len(calls) == 2 and waits == []
    session.rollback()


# ---------------------------------------------------------------- against source-sim
def test_a_503_burst_of_two_then_ok_is_one_ok_sync(waits, monkeypatch):
    """The fault is removed during the second wait, so the third try of the first request succeeds."""
    seen = waits

    def wait(seconds: float) -> None:
        seen.append(seconds)
        if len(seen) == 2:
            sim("DELETE", "/_sim/faults", params={"system": SID})

    monkeypatch.setattr(source_http, "_sleep", wait)
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "error", "value": 503})
    out = run_sync(SID, "manual")
    assert out["status"] == "ok", out
    with SessionLocal() as s:
        first = s.execute(
            text("SELECT url, status FROM fetch_log WHERE run_id = :r ORDER BY id LIMIT 3"), {"r": out["run_id"]}
        ).all()
        runs = s.execute(
            text("SELECT count(*) FROM sync_run WHERE id >= :r AND source_id = :i"), {"r": out["run_id"], "i": SID}
        ).scalar_one()
    assert [r.status for r in first] == [503, 503, 200] and len({r.url for r in first}) == 1
    assert runs == 1 and len(seen) == 2
    assert streak().fail_streak == 0


def test_a_failing_source_retries_after_2_4_8_minutes(waits):
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "unavailable"})
    try:
        for n, minutes in enumerate((2, 4, 8), start=1):
            assert run_sync(SID, "schedule")["status"] == "failed"
            row = streak()
            assert row.fail_streak == n and row.status == "failing"
            assert row.next_retry_at - row.last_sync_at == timedelta(minutes=minutes)
            drop_sync_jobs()
            with SessionLocal() as s:
                assert SID not in enqueue_due(s, now=row.next_retry_at - timedelta(seconds=1))
            drop_sync_jobs()
            with SessionLocal() as s:
                assert SID in enqueue_due(s, now=row.next_retry_at)
            drop_sync_jobs()
    finally:
        sim("DELETE", "/_sim/faults", params={"system": SID})
    assert run_sync(SID, "schedule")["status"] == "ok"
    row = streak()
    assert (row.fail_streak, row.next_retry_at, row.status) == (0, None, "live")


def test_the_retry_wait_is_capped_at_the_interval(waits):
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_system SET interval_min = 3 WHERE id = :i"), {"i": SID})
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "unavailable"})
    try:
        gaps = []
        for _ in range(3):
            run_sync(SID, "schedule")
            row = streak()
            gaps.append(row.next_retry_at - row.last_sync_at)
    finally:
        sim("DELETE", "/_sim/faults", params={"system": SID})
        with engine.begin() as conn:
            conn.execute(text("UPDATE source_system SET interval_min = 0 WHERE id = :i"), {"i": SID})
    assert gaps == [timedelta(minutes=2), timedelta(minutes=3), timedelta(minutes=3)]
    assert run_sync(SID, "manual")["status"] == "ok" and streak().fail_streak == 0


def runs_of(source_id: str) -> int:
    with SessionLocal() as s:
        return s.execute(text("SELECT count(*) FROM sync_run WHERE source_id = :i"), {"i": source_id}).scalar_one()


def test_a_sync_of_a_source_already_syncing_is_skipped():
    before = runs_of(SID)
    with engine.connect() as conn, conn.begin():
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('sync:' || :s))"), {"s": SID})
        assert run_sync(SID, "manual") == {"source_id": SID, "status": "skipped", "reason": "running"}
    assert runs_of(SID) == before  # a skipped sync records no run
    assert run_sync(SID, "manual")["status"] == "ok"  # the lock went with the transaction


def test_two_concurrent_syncs_one_is_skipped():
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "latency", "value": 100})
    results: list[dict] = []
    try:
        a = threading.Thread(target=lambda: results.append(run_sync(SID, "manual")))
        a.start()
        deadline = time.monotonic() + 20
        with SessionLocal() as s:
            while time.monotonic() < deadline:
                s.rollback()
                if s.execute(text("SELECT 1 FROM sync_run WHERE source_id = :i AND status = 'running'"), {"i": SID}).first():
                    break
                time.sleep(0.02)
        results.append(run_sync(SID, "manual"))
        a.join(120)
    finally:
        sim("DELETE", "/_sim/faults", params={"system": SID})
    assert sorted(r["status"] for r in results) == ["ok", "skipped"], results
    assert next(r for r in results if r["status"] == "skipped")["reason"] == "running"
