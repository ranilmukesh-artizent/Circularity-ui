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
    assert _status(session, job.id).status == "failed"


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
