"""A small Postgres job queue (plan decision D6: no Redis; hardened in plan 2).

    enqueue(s, kind, payload, priority=100, run_after=None, max_attempts=None, dedupe_key=None) -> Job
        a dedupe hit (a queued or running job with the same key: unique index ux_job_dedupe) returns that job
    claim(s) -> ClaimedJob | None      the next ready job by priority (lower first), run_after, id; SKIP LOCKED
    heartbeat(s, id)                   a running job is alive (the worker beats every 30 s)
    complete(s, id) / fail(s, job, error)
        fail retries with exponential backoff (2, 4, 8 … s) and appends {at, attempt, error} to `history`; at the
        job's max_attempts it is `dead` (kept for a retry, never lost)
    reap_stale(s, stale_after) -> int  running jobs whose heartbeat went quiet (a worker died): requeued, or dead when
                                       spent
    cancel(s, id) -> bool              only a queued job
    retry(s, id) -> bool               a dead, failed or cancelled job is queued again with its attempts reset
    reprioritise(s, id, priority) -> bool   only a queued job

Every queued job wakes a waiting worker through the trigger job_notify (NOTIFY di_jobs, migration 0018).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from di.core.config import get_settings
from di.models import Job

ACTIVE = ("queued", "running")  # the statuses a dedupe key is unique among (ux_job_dedupe)
RETRYABLE = ("dead", "failed", "cancelled")


@dataclass
class ClaimedJob:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int = 5


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 100,
    run_after: datetime | None = None,
    max_attempts: int | None = None,
    dedupe_key: str | None = None,
) -> Job:
    """Queue a job. `max_attempts` defaults to the setting job_max_attempts (5). With a `dedupe_key` that a queued or
    running job already holds, nothing is added and that job is returned."""
    values: dict[str, Any] = {
        "kind": kind,
        "payload": payload or {},
        "priority": priority,
        "max_attempts": max_attempts or get_settings().job_max_attempts,
        "dedupe_key": dedupe_key,
    }
    if run_after is not None:
        values["run_after"] = run_after
    if dedupe_key is None:
        job = Job(**values)
        session.add(job)
        session.flush()
        return job
    stmt = (
        insert(Job)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=text("status IN ('queued','running')"))
        .returning(Job.id)
    )
    job_id = session.execute(stmt).scalar()
    if job_id is None:  # a dedupe hit
        job_id = session.execute(
            text("SELECT id FROM job WHERE dedupe_key = :k AND status IN ('queued','running')"), {"k": dedupe_key}
        ).scalar_one()
    return session.get_one(Job, job_id)


_CLAIM = text(
    """
    UPDATE job SET status = 'running', locked_at = now(), heartbeat_at = now(), attempts = attempts + 1,
                   updated_at = now()
    WHERE id = (
        SELECT id FROM job
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY priority, run_after, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, kind, payload, attempts, max_attempts
    """
)


def claim(session: Session) -> ClaimedJob | None:
    row = session.execute(_CLAIM).first()
    return ClaimedJob(*row) if row else None


def heartbeat(session: Session, job_id: int) -> None:
    session.execute(text("UPDATE job SET heartbeat_at = now() WHERE id = :id AND status = 'running'"), {"id": job_id})


def complete(session: Session, job_id: int) -> None:
    session.execute(
        text(
            "UPDATE job SET status = 'done', locked_at = NULL, heartbeat_at = NULL, last_error = NULL, updated_at = now() "
            "WHERE id = :id"
        ),
        {"id": job_id},
    )


# an attempt ends in error: dead when spent (:dead), else queued again after :delay seconds; the error is appended to
# `history`
_FAIL = text(
    """
    UPDATE job SET status = CASE WHEN CAST(:dead AS boolean) THEN 'dead' ELSE 'queued' END,
                   run_after = CASE WHEN CAST(:dead AS boolean) THEN run_after
                                    ELSE now() + CAST(:delay AS integer) * interval '1 second' END,
                   locked_at = NULL, heartbeat_at = NULL, last_error = CAST(:err AS text),
                   history = history || jsonb_build_array(
                       jsonb_build_object('at', now(), 'attempt', attempts, 'error', CAST(:err AS text))),
                   updated_at = now()
    WHERE id = :id
    """
)

_REAP = text(
    """
    UPDATE job SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
                   run_after = now(), locked_at = NULL, heartbeat_at = NULL, last_error = CAST(:err AS text),
                   history = history || jsonb_build_array(
                       jsonb_build_object('at', now(), 'attempt', attempts, 'error', CAST(:err AS text))),
                   updated_at = now()
    WHERE status = 'running' AND COALESCE(heartbeat_at, locked_at, updated_at) < now() - :after
    RETURNING id
    """
)


def fail(session: Session, job: ClaimedJob, error: str, max_attempts: int | None = None) -> None:
    """Retry with exponential backoff (2, 4, 8 … seconds) until the job's max_attempts (or `max_attempts`, when
    given), then mark it dead. Every error is kept in `history`."""
    dead = job.attempts >= (max_attempts or job.max_attempts)
    session.execute(_FAIL, {"id": job.id, "err": error, "dead": dead, "delay": 2**job.attempts})


def reap_stale(session: Session, stale_after: timedelta = timedelta(minutes=5)) -> int:
    """Running jobs with no heartbeat for `stale_after` lost their worker: requeued (dead when out of attempts).
    Returns how many were reaped."""
    rows = session.execute(_REAP, {"after": stale_after, "err": "stale: no heartbeat, the worker was lost"}).all()
    return len(rows)


def cancel(session: Session, job_id: int) -> bool:
    """Cancel a queued job. A running, finished or unknown job is left alone (False)."""
    row = session.execute(
        text("UPDATE job SET status = 'cancelled', updated_at = now() WHERE id = :id AND status = 'queued' RETURNING id"),
        {"id": job_id},
    ).first()
    return row is not None


def retry(session: Session, job_id: int) -> bool:
    """Queue a dead, failed or cancelled job again, now, with its attempts reset; its last error stays in `history`.
    False when the job is not retryable, or another queued or running job holds its dedupe key."""
    row = session.execute(
        text(
            "UPDATE job SET status = 'queued', attempts = 0, run_after = now(), locked_at = NULL, heartbeat_at = NULL, "
            "history = history || jsonb_build_array(jsonb_build_object('at', now(), 'event', 'retry', "
            "'error', last_error)), updated_at = now() "
            "WHERE id = :id AND status IN ('dead','failed','cancelled') AND (dedupe_key IS NULL OR NOT EXISTS ("
            "  SELECT 1 FROM job o WHERE o.dedupe_key = job.dedupe_key AND o.status IN ('queued','running'))) "
            "RETURNING id"
        ),
        {"id": job_id},
    ).first()
    return row is not None


def reprioritise(session: Session, job_id: int, priority: int) -> bool:
    """Change a queued job's priority (lower runs first). False for any other job."""
    row = session.execute(
        text("UPDATE job SET priority = :p, updated_at = now() WHERE id = :id AND status = 'queued' RETURNING id"),
        {"id": job_id, "p": priority},
    ).first()
    return row is not None
