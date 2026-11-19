"""A small Postgres job queue (plan decision D6: no Redis)."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.models import Job


@dataclass
class ClaimedJob:
    id: int
    kind: str
    payload: dict
    attempts: int


def enqueue(session: Session, kind: str, payload: dict | None = None) -> Job:
    job = Job(kind=kind, payload=payload or {})
    session.add(job)
    session.flush()
    return job


_CLAIM = text(
    """
    UPDATE job SET status = 'running', locked_at = now(), attempts = attempts + 1, updated_at = now()
    WHERE id = (
        SELECT id FROM job
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, kind, payload, attempts
    """
)


def claim(session: Session) -> ClaimedJob | None:
    row = session.execute(_CLAIM).first()
    return ClaimedJob(*row) if row else None


def complete(session: Session, job_id: int) -> None:
    session.execute(
        text("UPDATE job SET status = 'done', locked_at = NULL, last_error = NULL, updated_at = now() WHERE id = :id"),
        {"id": job_id},
    )


def fail(session: Session, job: ClaimedJob, error: str, max_attempts: int) -> None:
    """Retry with exponential backoff (2, 4, 8 … seconds) until max_attempts, then mark failed."""
    if job.attempts >= max_attempts:
        sql = "UPDATE job SET status = 'failed', locked_at = NULL, last_error = :err, updated_at = now() WHERE id = :id"
        params = {"id": job.id, "err": error}
    else:
        sql = (
            "UPDATE job SET status = 'queued', locked_at = NULL, last_error = :err, updated_at = now(), "
            "run_after = now() + CAST(:delay AS integer) * interval '1 second' WHERE id = :id"
        )
        params = {"id": job.id, "err": error, "delay": 2**job.attempts}
    session.execute(text(sql), params)
