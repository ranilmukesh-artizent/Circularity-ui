from sqlalchemy import text

from di import jobs, worker
from di.db import SessionLocal


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
