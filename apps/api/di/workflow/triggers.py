"""Workflow triggers (plan 6 C6): a published workflow runs on its trigger, not only on Run now.

Which workflows a trigger starts: published (a draft or a paused workflow never runs on its own), not running, and,
when the workflow belongs to a source, that source not paused, disconnected, unavailable or deleted (the connectors do
not read it either). Such a workflow is skipped silently: its trigger fires again later, and a skipped run would only
add noise to the run list. Run now (workflow.run) is not a trigger and keeps its own guard.

- schedule (`{"t": "schedule", "min": n}`): due `n` minutes after the later of its last run (`last.ts`) and its last
  publish or save (`updated`), on the workspace clock (di/clock.py). `due()` lists them; the worker's periodic step
  queues them (`tick()`). Counting from what the database holds keeps the suite's golden screens still: on the pinned
  as-of time every seeded schedule ran less than its interval ago (the demo's last runs are minutes old), so nothing
  is due, and the suite's worker is stopped anyway (scripts/dev/api-test.sh).
- event (`on_event`): a webhook for the workflow's source (di/connectors/webhook.py, both routes).
- approval (`on_approval`): an instruction queued for the workflow's target system (di/instructions/queue.py).
- file (`on_file`) and case (`on_case`): helpers for the file intake and the case request; nothing calls them yet.

A trigger queues a `workflow.run` job `{wf, trig}` without a run record (the label is the run record's `trig`:
Schedule, Event, File, Approval, Case). A webhook or an approval therefore changes no workspace state when it is
received; the worker makes the run record when it takes the job (`start()`, called by its `workflow.run` handler),
checking again that the workflow may run. One run at a time per workflow: no job is queued while the workflow is
running or a `workflow.run` job for it is queued or running (the dedupe key `wf:<id>` of the plan, done the way
di.connectors.sync.enqueue_sync does it until the job queue has dedupe keys).

DI_WORKFLOW_TRIGGERS=false switches every trigger off (`enabled()`); the api suite does (tests/conftest.py).
"""

import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import jobs, state
from di.reads.common import ms

log = logging.getLogger("di.triggers")

LABEL = {"schedule": "Schedule", "event": "Event", "file": "File", "approval": "Approval", "case": "Case"}
NOT_RUN = ("paused", "disconnected", "unavailable")  # the sources the connectors do not read (sync.NOT_SYNCED)
MIN_MS = 60_000


def _kind(w: dict) -> str | None:
    return (w.get("trig") or {}).get("t")


def _source_ok(s: Session, w: dict) -> bool:
    sid = w.get("src")
    if not sid:
        return True
    from di.connectors import lifecycle

    status = s.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar()
    return status not in NOT_RUN and not lifecycle.is_deleted(s, sid)


def may_run(s: Session, w: dict) -> bool:
    return w.get("status") == "published" and not w.get("running") and _source_ok(s, w)


def _pending(s: Session, wid: str) -> bool:
    return (
        s.execute(
            text(
                "SELECT 1 FROM job WHERE kind = 'workflow.run' AND status IN ('queued','running') "
                "AND payload->>'wf' = :w LIMIT 1"
            ),
            {"w": wid},
        ).first()
        is not None
    )


def enabled() -> bool:
    """DI_WORKFLOW_TRIGGERS (default on). The api suite turns triggers off (tests/conftest.py), as it turns off sending
    instructions: tests that run the worker's jobs in-process (the RT-1048 milestone) would otherwise also run every
    workflow their events and instructions trigger. tests/test_triggers.py turns them on for itself."""
    return os.environ.get("DI_WORKFLOW_TRIGGERS", "true").strip().lower() not in ("0", "false", "no", "off")


def fire(s: Session, wid: str, trig: str) -> int | None:
    """Queue a run of the workflow under trigger label `trig`, in the caller's transaction. Returns the job id, or None
    when triggers are off, or the workflow may not run or already has a run queued or running."""
    if not enabled():
        return None
    w = state.get(s, "workflows", wid)
    if w is None or not may_run(s, w) or _pending(s, wid):
        return None
    return jobs.enqueue(s, "workflow.run", {"wf": wid, "trig": trig}).id


def _matching(s: Session, kind: str, src: str | None = None) -> list[dict]:
    from di.reads import workflows as studio

    return [
        w
        for w in studio.all_workflows(s)
        if _kind(w) == kind and w.get("status") == "published" and (src is None or w.get("src") == src)
    ]


def _fire_all(s: Session, kind: str, src: str | None = None) -> list[str]:
    return [w["id"] for w in _matching(s, kind, src) if fire(s, w["id"], LABEL[kind]) is not None]


# ---------------------------------------------------------------- schedule
def due(s: Session, now: datetime) -> list[tuple[str, str]]:
    """(workflow id, trigger label) of the scheduled workflows whose interval has passed at `now`."""
    t = ms(now.isoformat())
    out = []
    for w in _matching(s, "schedule"):
        every = (w.get("trig") or {}).get("min")
        if not isinstance(every, int | float) or isinstance(every, bool) or every <= 0:
            continue
        base = max(int((w.get("last") or {}).get("ts") or 0), int(w.get("updated") or 0))
        if t - base >= every * MIN_MS and may_run(s, w):
            out.append((w["id"], LABEL["schedule"]))
    return out


def tick(s: Session, now: datetime) -> list[str]:
    """The worker's periodic step: queue the due schedules (the caller commits). Returns the workflow ids queued."""
    return [wid for wid, label in due(s, now) if fire(s, wid, label) is not None]


# ---------------------------------------------------------------- the other triggers
def on_event(s: Session, source_id: str) -> list[str]:
    """A webhook for this source: its published event-triggered workflows, except the one bound to the source's sync
    (source_config.workflow, plan 6 C5): the webhook already queues the sync, which runs that workflow, so firing it
    here too would ingest the same change twice."""
    from di.connectors import lifecycle

    bound = (state.get(s, lifecycle.COLLECTION, source_id) or {}).get("workflow")
    return [
        w["id"] for w in _matching(s, "event", source_id)
        if w["id"] != bound and fire(s, w["id"], LABEL["event"]) is not None
    ]  # fmt: skip


def on_file(s: Session, source_id: str) -> list[str]:
    """A file landed for this source: its published file-triggered workflows."""
    return _fire_all(s, "file", source_id)


def on_approval(s: Session, target_id: str) -> list[str]:
    """An instruction was queued for this target system: its published approval-triggered (outbound) workflows."""
    return _fire_all(s, "approval", target_id)


def on_case(s: Session, case_id: str) -> list[str]:
    """A case asked for a decision: the published case-triggered (decision) workflows."""
    log.debug("case request %s", case_id)
    return _fire_all(s, "case")


def safely(fn, s: Session, arg: str) -> list[str]:
    """Run a trigger inside a savepoint: a trigger that fails is logged and undone, and never breaks its caller's
    transaction (a webhook, an instruction)."""
    try:
        with s.begin_nested():
            return fn(s, arg)
    except Exception:
        log.exception("trigger %s(%s) failed", getattr(fn, "__name__", fn), arg)
        return []


# ---------------------------------------------------------------- the worker takes the job
def start(payload: dict[str, Any]) -> dict[str, Any] | None:
    """For a `workflow.run` job queued by a trigger: make the run record (labelled with the trigger) and return the
    payload the run job takes, or None when the workflow may no longer run (deleted, paused, already running)."""
    from di.actions import workflows as wf
    from di.db import SessionLocal

    wid, trig = payload["wf"], payload.get("trig") or "Schedule"
    with SessionLocal() as s:
        w = state.get(s, "workflows", wid, for_update=True)
        if w is not None:  # a run a dead worker left open is closed first (plan 6 C7); this job is the caller's own
            wf.reap_lost_run(s, w, wf._now(), jobs_ok=1)
        if w is None or not may_run(s, w):
            s.commit()
            return None
        key = wf.start_run(s, w, trig, wf._now(), enqueue=False)
        s.commit()
    return {"run": key, "wf": wid, "trig": trig}
