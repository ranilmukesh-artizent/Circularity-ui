import threading
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from di import worker
from di.core import jobs
from di.core.db import SessionLocal
from tests.test_models_migrations import scratch_url  # noqa: F401  (fixture: a scratch database, never di)

QUEUE_COLUMNS = {"priority", "max_attempts", "heartbeat_at", "dedupe_key", "history"}


def _status(session, job_id):
    return session.execute(text("SELECT status, attempts, last_error FROM job WHERE id = :id"), {"id": job_id}).one()


def test_claim_is_exclusive(session):
    job = jobs.enqueue(session, "ping", {"n": 1})
    session.commit()

    with SessionLocal() as a, SessionLocal() as b:
        first = jobs.claim(a)  # row locked until a commits
        second = jobs.claim(b)  # SKIP LOCKED: b must not get the same job
        assert first is not None and first.id == job.id
        assert second is None
        a.commit()
        b.commit()


def test_worker_runs_handler_and_completes(session):
    seen = []
    worker.HANDLERS["test.echo"] = seen.append
    job = jobs.enqueue(session, "test.echo", {"hello": "world"})
    session.commit()

    assert worker.run_once() is True
    assert seen == [{"hello": "world"}]
    assert _status(session, job.id).status == "done"
    assert worker.run_once() is False


def test_failed_job_is_requeued_with_backoff_then_fails(session, monkeypatch):
    job = jobs.enqueue(session, "no.such.kind")
    session.commit()

    assert worker.run_once() is True
    status, attempts, err = _status(session, job.id)
    assert (status, attempts) == ("queued", 1)
    assert "no handler" in err
    assert worker.run_once() is False  # backoff: not ready yet

    # exhaust the attempts
    session.execute(text("UPDATE job SET attempts = 4, run_after = now() WHERE id = :id"), {"id": job.id})
    session.commit()
    assert worker.run_once() is True
    assert _status(session, job.id).status == "dead"  # plan 2: out of attempts, kept for a retry


# ---------------------------------------------------------------- plan 2 task 1: the schema (migration 0018)
def _job_schema(url: str) -> tuple[set[str], set[str], bool]:
    eng = create_engine(url)
    try:
        cols = {c["name"] for c in inspect(eng).get_columns("job")}
        idx = {i["name"] for i in inspect(eng).get_indexes("job")}
        with eng.connect() as c:
            trig = c.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname = 'job_notify'")).scalar() == 1
        return cols, idx, trig
    finally:
        eng.dispose()


def test_job_queue_migration_round_trips(scratch_url):  # noqa: F811
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", scratch_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    cols, idx, trig = _job_schema(scratch_url)
    assert cols >= QUEUE_COLUMNS and idx >= {"ux_job_dedupe", "ix_job_claim"} and trig

    command.downgrade(cfg, "0017")
    cols, idx, trig = _job_schema(scratch_url)
    assert not (QUEUE_COLUMNS & cols) and not ({"ux_job_dedupe", "ix_job_claim"} & idx) and not trig

    command.upgrade(cfg, "head")
    cols, idx, trig = _job_schema(scratch_url)
    assert cols >= QUEUE_COLUMNS and idx >= {"ux_job_dedupe", "ix_job_claim"} and trig


def test_new_job_defaults(session):
    session.execute(text("INSERT INTO job (kind) VALUES ('ping')"))
    row = session.execute(text("SELECT priority, max_attempts, heartbeat_at, dedupe_key, history FROM job")).one()
    assert tuple(row) == (100, 5, None, None, [])
    session.rollback()


def test_dedupe_key_is_unique_while_queued_or_running(session):
    insert = text("INSERT INTO job (kind, dedupe_key) VALUES ('ping', 'k1')")
    session.execute(insert)
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(insert)
    session.rollback()
    session.execute(text("UPDATE job SET status = 'running' WHERE dedupe_key = 'k1'"))
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(insert)
    session.rollback()
    session.execute(text("UPDATE job SET status = 'done' WHERE dedupe_key = 'k1'"))
    session.execute(insert)  # a finished job frees its key
    session.commit()


def test_status_allows_dead_and_cancelled(session):
    session.execute(text("INSERT INTO job (kind, status) VALUES ('ping', 'dead'), ('ping', 'cancelled')"))
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(text("INSERT INTO job (kind, status) VALUES ('ping', 'lost')"))
    session.rollback()


# ---------------------------------------------------------------- plan 2 task 2: the queue functions
def _claim_one() -> jobs.ClaimedJob | None:
    with SessionLocal() as s:
        job = jobs.claim(s)
        s.commit()
        return job


def _row(session, job_id):
    session.expire_all()
    return session.execute(text("SELECT * FROM job WHERE id = :id"), {"id": job_id}).mappings().one()


def test_claim_takes_the_lowest_priority_first(session):
    low = jobs.enqueue(session, "ping", {"n": "low"}, priority=200)
    high = jobs.enqueue(session, "ping", {"n": "high"}, priority=10)
    normal = jobs.enqueue(session, "ping", {"n": "normal"})
    session.commit()
    assert [_claim_one().id for _ in range(3)] == [high.id, normal.id, low.id]
    assert _claim_one() is None


def test_a_delayed_job_is_not_claimed_early(session):
    later = jobs.enqueue(session, "ping", run_after=datetime.now(UTC) + timedelta(hours=1))
    session.commit()
    assert _claim_one() is None
    session.execute(text("UPDATE job SET run_after = now() WHERE id = :id"), {"id": later.id})
    session.commit()
    assert _claim_one().id == later.id


def test_a_job_is_dead_after_max_attempts_with_its_errors_in_history(session):
    job = jobs.enqueue(session, "ping", max_attempts=2)
    session.commit()
    for attempt in (1, 2):
        claimed = _claim_one()
        assert claimed.id == job.id and claimed.attempts == attempt and claimed.max_attempts == 2
        with SessionLocal() as s:
            jobs.fail(s, claimed, f"boom {attempt}")
            s.execute(text("UPDATE job SET run_after = now() WHERE id = :id"), {"id": job.id})  # skip the backoff
            s.commit()
    row = _row(session, job.id)
    assert (row["status"], row["attempts"], row["last_error"]) == ("dead", 2, "boom 2")
    assert [h["error"] for h in row["history"]] == ["boom 1", "boom 2"] and all(h["at"] for h in row["history"])
    assert _claim_one() is None


def test_claim_sets_the_heartbeat_and_heartbeat_moves_it(session):
    job = jobs.enqueue(session, "ping")
    session.commit()
    _claim_one()
    first = _row(session, job.id)["heartbeat_at"]
    assert first is not None
    session.execute(text("UPDATE job SET heartbeat_at = now() - interval '1 minute' WHERE id = :id"), {"id": job.id})
    session.commit()
    with SessionLocal() as s:
        jobs.heartbeat(s, job.id)
        s.commit()
    assert _row(session, job.id)["heartbeat_at"] > first - timedelta(seconds=1)


def test_the_reaper_requeues_a_stale_running_job_and_buries_a_spent_one(session):
    stale = jobs.enqueue(session, "ping", {"n": "stale"})
    fresh = jobs.enqueue(session, "ping", {"n": "fresh"})
    spent = jobs.enqueue(session, "ping", {"n": "spent"}, max_attempts=1)
    session.commit()
    for _ in range(3):
        _claim_one()
    session.execute(
        text("UPDATE job SET heartbeat_at = now() - interval '10 minutes' WHERE id IN (:a, :b)"),
        {"a": stale.id, "b": spent.id},
    )
    session.commit()
    with SessionLocal() as s:
        assert jobs.reap_stale(s, timedelta(minutes=5)) == 2
        s.commit()
    assert _row(session, stale.id)["status"] == "queued"
    assert "stale" in _row(session, stale.id)["history"][-1]["error"]
    assert _row(session, fresh.id)["status"] == "running"
    assert _row(session, spent.id)["status"] == "dead"


def test_two_concurrent_claimers_never_get_the_same_job(session):
    ids = {jobs.enqueue(session, "ping", {"n": n}).id for n in range(40)}
    session.commit()
    got: dict[str, list[int]] = {"a": [], "b": []}
    start = threading.Barrier(2)

    def drain(name: str) -> None:
        start.wait()
        while (job := _claim_one()) is not None:
            got[name].append(job.id)

    threads = [threading.Thread(target=drain, args=(n,)) for n in got]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not set(got["a"]) & set(got["b"])
    assert sorted(got["a"] + got["b"]) == sorted(ids)


def test_enqueue_with_a_dedupe_key_returns_the_queued_job(session):
    first = jobs.enqueue(session, "ping", {"n": 1}, dedupe_key="sync:erp")
    again = jobs.enqueue(session, "ping", {"n": 2}, dedupe_key="sync:erp")
    session.commit()
    assert again.id == first.id and again.payload == {"n": 1}
    assert session.execute(text("SELECT count(*) FROM job")).scalar() == 1
    session.execute(text("UPDATE job SET status = 'done' WHERE id = :id"), {"id": first.id})
    session.commit()
    assert jobs.enqueue(session, "ping", dedupe_key="sync:erp").id != first.id  # a finished job frees the key


def test_cancel_only_a_queued_job(session):
    queued = jobs.enqueue(session, "ping")
    running = jobs.enqueue(session, "ping", priority=1)
    session.commit()
    _claim_one()  # takes `running`
    assert jobs.cancel(session, running.id) is False
    assert jobs.cancel(session, queued.id) is True
    assert jobs.cancel(session, queued.id) is False  # already cancelled
    session.commit()
    assert _row(session, queued.id)["status"] == "cancelled"
    assert _row(session, running.id)["status"] == "running"


def test_retry_puts_a_dead_job_back_with_attempts_reset(session):
    job = jobs.enqueue(session, "ping", max_attempts=1)
    session.commit()
    with SessionLocal() as s:
        jobs.fail(s, _claim_one(), "boom")
        s.commit()
    assert jobs.retry(session, job.id) is True
    session.commit()
    row = _row(session, job.id)
    assert (row["status"], row["attempts"]) == ("queued", 0)
    assert row["history"][0]["error"] == "boom" and row["history"][-1]["event"] == "retry"
    assert jobs.retry(session, job.id) is False  # only a dead, failed or cancelled job is retried
