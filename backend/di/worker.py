"""di-worker: claims jobs from the Postgres queue and runs their handler.

Run with:  python -m di.worker
Handlers register by job kind: `sync.source` (B9; a sync of a file source that read new files then runs the source's
file-triggered workflows, di/workflow/triggers.py file_arrived), `instruction.send` (B13b, di/services/instructions)
and `workflow.run` (B15, di/services/actions/workflows: a workflow run, step by step, its progress on the live-update
stream), and `agent.step` (plan 8 MVP-11.5, di/services/agents/runtime: an agent run's steps until it blocks).
Besides jobs, the loop queues due syncs and due scheduled workflow runs (di/workflow/triggers.py) every 30 s
and, while sending instructions is on, acknowledges due simulated steps every 5 s.

Plan 2: the loop waits on LISTEN di_jobs (a dedicated autocommit connection; the trigger job_notify NOTIFYs it when a
job is queued) or `worker_poll_seconds`, whichever comes first; a running job heartbeats every 30 s from a thread, and
the periodic step requeues jobs whose heartbeat went quiet for 5 minutes (jobs.reap_stale; dead when spent).
"""

import logging
import signal
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from sqlalchemy.engine import make_url

from di.core import jobs
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.core.logs import configure_logging

log = logging.getLogger("di.worker")

Handler = Callable[[dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


@handler("ping")
def _ping(payload: dict[str, Any]) -> None:
    log.info("ping %s", payload)


HEARTBEAT_SECONDS = 30.0  # a running job's heartbeat (jobs.heartbeat); the reaper requeues one quiet for STALE_AFTER
STALE_AFTER = timedelta(minutes=5)
CHANNEL = "di_jobs"  # NOTIFY'd by the trigger job_notify whenever a job is queued (migration 0018)


def _beat(job_id: int, done: threading.Event) -> None:
    while not done.wait(HEARTBEAT_SECONDS):
        try:
            with SessionLocal() as session:
                jobs.heartbeat(session, job_id)
                session.commit()
        except Exception:  # a missed beat is retried; only a long silence lets the reaper take the job
            log.exception("heartbeat of job %s failed", job_id)


def run_once() -> bool:
    """Claim and run one job, heartbeating it from a thread while it runs. Returns False when nothing was ready."""
    with SessionLocal() as session:
        job = jobs.claim(session)
        session.commit()
    if job is None:
        return False

    done = threading.Event()
    beat = threading.Thread(target=_beat, args=(job.id, done), name=f"heartbeat-{job.id}", daemon=True)
    beat.start()
    try:
        with SessionLocal() as session:
            try:
                fn = HANDLERS.get(job.kind)
                if fn is None:
                    raise LookupError(f"no handler for job kind {job.kind!r}")
                fn(job.payload)
                jobs.complete(session, job.id)
            except Exception as exc:  # every failure is recorded on the job
                log.exception("job %s (%s) failed", job.id, job.kind)
                jobs.fail(session, job, f"{type(exc).__name__}: {exc}")  # dead at the job's own max_attempts
            session.commit()
    finally:
        done.set()
        beat.join()
    return True


class Wakeup:
    """Waits for NOTIFY di_jobs on a dedicated autocommit connection, or `poll` seconds, whichever comes first. If the
    connection cannot be had (or drops), it sleeps `poll` and tries again next time: polling is the fallback."""

    def __init__(self) -> None:
        self.conn: psycopg.Connection | None = None

    def _connect(self) -> psycopg.Connection | None:
        url = make_url(get_settings().database_url).set(drivername="postgresql")
        try:
            conn = psycopg.connect(url.render_as_string(hide_password=False), autocommit=True)
            conn.execute(f"LISTEN {CHANNEL}")
            return conn
        except Exception:
            log.exception("cannot listen on %s; polling instead", CHANNEL)
            return None

    def wait(self, poll: float) -> None:
        if self.conn is None or self.conn.closed:
            self.conn = self._connect()
        if self.conn is None:
            time.sleep(poll)
            return
        try:
            for _ in self.conn.notifies(timeout=poll, stop_after=1):
                pass
        except Exception:
            log.exception("listening on %s failed; reconnecting", CHANNEL)
            self.close()
            time.sleep(min(poll, 1.0))

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None


def serve(stopping: Callable[[], bool], poll: float, *, housekeeping: bool = True) -> None:
    """The worker loop: run every ready job, then wait for a NOTIFY or `poll` seconds. With `housekeeping`, also the
    periodic step every 30 s and the simulated acknowledgements every 5 s."""
    wakeup = Wakeup()
    next_periodic = next_tick = 0.0
    try:
        while not stopping():
            if housekeeping and time.monotonic() >= next_periodic:
                periodic()
                next_periodic = time.monotonic() + 30
            if housekeeping and time.monotonic() >= next_tick and get_settings().instructions:
                tick_instructions()  # simulated acknowledgements fall due as the simulated clock moves
                next_tick = time.monotonic() + 5
            if not run_once():
                wakeup.wait(poll)
    finally:
        wakeup.close()


def main() -> None:
    configure_logging()  # the api's format and level (di/core/logs.py)
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    startup()
    log.info("worker started; handlers: %s", ", ".join(sorted(HANDLERS)))
    serve(lambda: stopping, get_settings().worker_poll_seconds)
    log.info("worker stopped")


# ---------------------------------------------------------------- connectors (B9)
@handler("sync.source")
def _sync(payload: dict[str, Any]) -> None:
    from di.connectors.sync import run_sync

    out = run_sync(payload["source_id"], payload.get("trigger", "schedule"), bool(payload.get("full")))
    log.info("sync %s: %s", payload["source_id"], out)
    if out.get("status") in ("ok", "partial"):  # new files read: the file-triggered workflows run (never raises)
        from di.workflow.triggers import file_arrived

        file_arrived(payload["source_id"], int(out.get("records_read") or 0))


# ---------------------------------------------------------------- outbound instructions (B13b)
@handler("instruction.send")
def _instruction_send(payload: dict[str, Any]) -> None:
    import di.services.actions.execution  # noqa: F401 - registers adapter.acknowledge, which acknowledgements go through
    from di.services.instructions.send import send

    out = send(int(payload["instruction_id"]), bool(payload.get("resend")))
    log.info("instruction %s: %s", payload["instruction_id"], out)


# ---------------------------------------------------------------- workflow runs (B15)
@handler("workflow.run")
def _workflow_run(payload: dict[str, Any]) -> None:
    from di.services.actions.workflows import run_job

    if "run" not in payload:  # queued by a trigger (plan 6 C6, di/workflow/triggers.py): its run record is made now
        from di.workflow.triggers import start

        started = start(payload)
        if started is None:
            log.info("triggered run of %s skipped: it may not run now", payload.get("wf"))
            return
        payload = started
    out = run_job(payload)
    log.info("workflow run %s: %s", payload.get("run"), out)


@handler("workflow.resume")
def _workflow_resume(payload: dict[str, Any]) -> None:
    """A Wait step's parked records are due: the workflow runs on from that step (di/workflow/waits.py)."""
    from di.workflow.waits import resume

    log.info("workflow resume %s: %s", payload.get("wait"), resume(payload))


# ---------------------------------------------------------------- agent runs (plan 8 MVP-11.5)
@handler("agent.step")
def _agent_step(payload: dict[str, Any]) -> None:
    """An agent run's next steps, until it waits for a person, ends or stops (di/services/agents/runtime.py)."""
    from di.services.agents import runtime  # registers the handlers its playbooks call
    from di.services.cases import use_database_scope

    use_database_scope()  # the run acts as a person: a case's owner and location from the database, as in the api
    with SessionLocal() as s:
        log.info("agent run %s: %s", payload["run_id"], runtime.run_until_blocked(s, payload["run_id"]))


@handler("trace.prune")
def _trace_prune(payload: dict[str, Any]) -> None:  # noqa: ARG001 - jobs take a payload
    """Delete the spans of agent runs older than the setting `trace_retention_days` (di.core.tracing.prune, P9-2.6)."""
    from di.core import tracing

    with SessionLocal() as s:
        n = tracing.prune(s, get_settings().trace_retention_days)
        s.commit()
    log.info("trace prune: deleted %s span(s)", n)


_last_prune: str | None = None


def enqueue_trace_prune() -> None:
    """Queue the daily `trace.prune` job: once per calendar day (UTC) per worker process, from the periodic step."""
    global _last_prune
    today = datetime.now(UTC).date().isoformat()
    if _last_prune == today:
        return
    with SessionLocal() as s:
        jobs.enqueue(s, "trace.prune", {}, priority=200, dedupe_key="trace.prune")
        s.commit()
    _last_prune = today


@handler("agent.autostart")
def _agent_autostart(payload: dict[str, Any]) -> None:
    """A case was opened and the autopilot setting is on: start its run (runtime.autostart, P9-0.9). The run's own
    `agent.step` job does the work."""
    from di.services.agents import runtime

    with SessionLocal() as s:
        log.info("autopilot on open %s: %s", payload["case_id"], runtime.autostart(s, payload["case_id"], payload.get("account")))
        s.commit()


@handler("case.gateRecheck")
def _gate_recheck(payload: dict[str, Any]) -> None:
    """Gate evidence landed for an asset (a `compliance` fact, canonical.apply): the cases held for it are valued again
    and the ones that clear are released (di.services.cases.gate_hold.recheck, P9-1.2)."""
    from di.services.cases import gate_hold

    with SessionLocal() as s:
        released = gate_hold.recheck(s, payload["asset_key"])
        s.commit()
    log.info("gate recheck %s: released %s", payload["asset_key"], released or "none")


@handler("case.replan")
def _case_replan(payload: dict[str, Any]) -> None:
    """A tool-fleet case was opened: the org's other open cases are planned again with it, so an order two returns want
    goes to one (di.services.cases.replan.on_opened, P9-1.4)."""
    from di.services.cases import replan

    with SessionLocal() as s:
        moved = replan.on_opened(s, payload["org_unit_id"])
        s.commit()
    log.info("replan %s: moved %s", payload["org_unit_id"], moved or "none")


@handler("case.reevaluate")
def _case_reevaluate(payload: dict[str, Any]) -> None:
    """A workbench grade landed for a tool-fleet case's serial (canonical.apply): the open case is valued again with it
    (di.services.cases.replan.on_graded, P9-3.5)."""
    from di.services.cases import replan

    with SessionLocal() as s:
        done = replan.on_graded(s, payload["case_id"])
        s.commit()
    log.info("regrade %s: %s", payload["case_id"], "valued again" if done else "left as it is")


@handler("queue.plan")
def _queue_plan(payload: dict[str, Any]) -> None:
    """A disposition stage waits for the queue plan: plan the pack's open cases of the org together and wake the runs
    (di.services.agents.queue_job.plan, P9-2.8)."""
    from di.services.agents import queue_job

    with SessionLocal() as s:
        woken = queue_job.plan(s, payload["pack"], payload["org_unit_id"])
        s.commit()
    log.info("queue plan %s/%s: woke %s", payload["pack"], payload["org_unit_id"], woken or "none")


@handler("case.recordMatch")
def _record_match(payload: dict[str, Any]) -> None:
    """A sync of a pack's system of record finished: the cases not yet found are matched again, and the assets it says are
    on their way back with no case after the pack's wait become exceptions (di.services.cases.record_match.reconcile,
    P9-1.10)."""
    from di.services.cases import record_match

    with SessionLocal() as s:
        report = record_match.reconcile(s, payload["source_id"])
        s.commit()
    log.info("record match %s: %s", payload["source_id"], report)


@handler("work.sla")
def _work_sla(payload: dict[str, Any]) -> None:
    """A work item's due time came (di.services.cases.process.open_item queued this job): if it is still open it is
    escalated (process.on_sla, P9-1.7). The timer only asks someone else; it never approves or resolves."""
    from di.services.cases import process

    with SessionLocal() as s:
        outcome = process.on_sla(s, payload["item_id"])
        s.commit()
    log.info("work sla %s: %s", payload["item_id"], outcome)


def tick_instructions() -> None:
    """Acknowledge the simulated steps that are due on the simulated clock."""
    import di.services.actions.execution  # noqa: F401
    from di.services.instructions.send import tick

    try:
        if n := tick():
            log.info("simulated acknowledgements: %s", n)
    except Exception:
        log.exception("simulated acknowledgements failed")


def startup() -> None:
    """Register the sources and subscribe to source-sim's change events (idempotent)."""
    from di.connectors.sync import ensure_sources
    from di.connectors.webhook import ensure_subscription

    try:
        with SessionLocal() as s:
            ensure_sources(s)
        ensure_subscription()
    except Exception:  # the periodic step retries the subscription
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
    except Exception:  # source-sim may be down; the next tick tries again
        log.exception("webhook subscription failed")
    try:
        with SessionLocal() as s:
            queued = enqueue_due(s)
            s.execute(text("DELETE FROM stream_event WHERE at < now() - interval '1 day'"))
            s.commit()
        if queued:
            log.info("queued syncs: %s", ", ".join(queued))
    except Exception:
        log.exception("periodic step failed")
    try:
        enqueue_trace_prune()
    except Exception:
        log.exception("queueing the trace prune failed")
    tick_triggers()  # first: a lost workflow run is closed ("worker lost") before its stale job is requeued
    try:
        with SessionLocal() as s:
            reaped = jobs.reap_stale(s, STALE_AFTER)
            s.commit()
        if reaped:
            log.warning("requeued %s job(s) whose worker was lost", reaped)
    except Exception:
        log.exception("reaping stale jobs failed")


def tick_triggers() -> None:
    """Queue the workflows whose schedule is due on the workspace clock (plan 6 C6)."""
    from di.core import clock
    from di.workflow import triggers

    try:
        with SessionLocal() as s:
            queued = triggers.tick(s, clock.now())
            s.commit()
        if queued:
            log.info("queued scheduled workflow runs: %s", ", ".join(queued))
    except Exception:
        log.exception("workflow triggers failed")
    reap_lost_runs()


def reap_lost_runs() -> None:
    """Close workflow runs a dead worker left open (`running` set, no job queued or going, no run lock held): the run
    fails with "worker lost" and the workflow can run again (plan 6 C7; Run now and triggered starts do the same)."""
    from di.repositories.workflows import all_workflows
    from di.services.actions import workflows as wf

    try:
        with SessionLocal() as s:
            now = wf._now()
            closed = [w["id"] for w in all_workflows(s) if w.get("running") and wf.reap_lost_run(s, w, now)]
            s.commit()
        if closed:
            log.warning("closed workflow runs their worker lost: %s", ", ".join(closed))
    except Exception:
        log.exception("reaping lost workflow runs failed")


if __name__ == "__main__":
    main()
