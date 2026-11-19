"""di-worker: claims jobs from the Postgres queue and runs their handler.

Run with:  python -m di.worker
Handlers register by job kind. Phase 2 adds source sync jobs; phase 4 adds outbound instructions.
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
    log.info("worker started; handlers: %s", ", ".join(sorted(HANDLERS)))
    while not stopping:
        if not run_once():
            time.sleep(poll)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
