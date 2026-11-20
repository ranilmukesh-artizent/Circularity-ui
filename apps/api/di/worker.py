"""di-worker: claims jobs from the Postgres queue and runs their handler.

Run with:  python -m di.worker
Handlers register by job kind: `sync.source` (B9), `instruction.send` (B13b, di/instructions) and `workflow.run`
(B15, di/actions/workflows: a workflow run, step by step, its progress on the live-update stream). Besides jobs, the
loop queues due syncs every 30 s and, while sending instructions is on, acknowledges due simulated steps every 5 s.
"""

import logging
import signal
import time
from collections.abc import Callable

from di import jobs
from di.config import get_settings
from di.db import SessionLocal

log = logging.getLogger("di.worker")

Handler = Callable[[dict], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


@handler("ping")
def _ping(payload: dict) -> None:
    log.info("ping %s", payload)


def run_once() -> bool:
    """Claim and run one job. Returns False when the queue had nothing ready."""
    settings = get_settings()
    with SessionLocal() as session:
        job = jobs.claim(session)
        session.commit()
    if job is None:
        return False

    with SessionLocal() as session:
        try:
            fn = HANDLERS.get(job.kind)
            if fn is None:
                raise LookupError(f"no handler for job kind {job.kind!r}")
            fn(job.payload)
            jobs.complete(session, job.id)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            log.exception("job %s (%s) failed", job.id, job.kind)
            jobs.fail(session, job, f"{type(exc).__name__}: {exc}", settings.job_max_attempts)
        session.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    poll = get_settings().worker_poll_seconds
    startup()
    log.info("worker started; handlers: %s", ", ".join(sorted(HANDLERS)))
    next_periodic = next_tick = 0.0
    while not stopping:
        if time.monotonic() >= next_periodic:
            periodic()
            next_periodic = time.monotonic() + 30
        if time.monotonic() >= next_tick and get_settings().instructions:
            tick_instructions()  # simulated acknowledgements fall due as the simulated clock moves
            next_tick = time.monotonic() + 5
        if not run_once():
            time.sleep(poll)
    log.info("worker stopped")


# ---------------------------------------------------------------- connectors (B9)
@handler("sync.source")
def _sync(payload: dict) -> None:
    from di.connectors.sync import run_sync

    out = run_sync(payload["source_id"], payload.get("trigger", "schedule"), bool(payload.get("full")))
    log.info("sync %s: %s", payload["source_id"], out)


# ---------------------------------------------------------------- outbound instructions (B13b)
@handler("instruction.send")
def _instruction_send(payload: dict) -> None:
    import di.actions.execution  # noqa: F401 - registers adapter.acknowledge, which acknowledgements go through
    from di.instructions.send import send

    out = send(int(payload["instruction_id"]), bool(payload.get("resend")))
    log.info("instruction %s: %s", payload["instruction_id"], out)


# ---------------------------------------------------------------- workflow runs (B15)
@handler("workflow.run")
def _workflow_run(payload: dict) -> None:
    from di.actions.workflows import run_job

    out = run_job(payload)
    log.info("workflow run %s: %s", payload.get("run"), out)


def tick_instructions() -> None:
    """Acknowledge the simulated steps that are due on the simulated clock."""
    import di.actions.execution  # noqa: F401
    from di.instructions.send import tick

    try:
        if n := tick():
            log.info("simulated acknowledgements: %s", n)
    except Exception:  # noqa: BLE001
        log.exception("simulated acknowledgements failed")


def startup() -> None:
    """Register the sources and subscribe to source-sim's change events (idempotent)."""
    from di.connectors.sync import ensure_sources
    from di.connectors.webhook import ensure_subscription

    try:
        with SessionLocal() as s:
            ensure_sources(s)
        ensure_subscription()
    except Exception:  # noqa: BLE001 - the periodic step retries the subscription
        log.exception("startup step failed")


def periodic() -> None:
    """Every 30 s: make sure source-sim still delivers its change events here (a source-sim reset or a failed start-up
    subscription loses them), queue the syncs that are due, and drop live-update events older than a day (a
    reconnecting client replays at most 500, so older ones are never read again)."""
    from sqlalchemy import text

    from di.connectors.sync import enqueue_due
    from di.connectors.webhook import ensure_subscription

    try:
        ensure_subscription()
    except Exception:  # noqa: BLE001 - source-sim may be down; the next tick tries again
        log.exception("webhook subscription failed")
    try:
        with SessionLocal() as s:
            queued = enqueue_due(s)
            s.execute(text("DELETE FROM stream_event WHERE at < now() - interval '1 day'"))
            s.commit()
        if queued:
            log.info("queued syncs: %s", ", ".join(queued))
    except Exception:  # noqa: BLE001
        log.exception("periodic step failed")


if __name__ == "__main__":
    main()
