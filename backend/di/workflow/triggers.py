"""Workflow triggers (plan 6 C6): a published workflow runs on its trigger, not only on Run now.

Which workflows a trigger starts: published in the app (`published_here`: a draft, a paused workflow or one of the
demo's seeded workflows never runs on its own), not running, and,
when the workflow belongs to a source, that source not paused, disconnected, unavailable or deleted (the connectors do
not read it either). Such a workflow is skipped silently: its trigger fires again later, and a skipped run would only
add noise to the run list. Run now (workflow.run) is not a trigger and keeps its own guard.

- schedule (`{"t": "schedule", "min": n}`): due `n` minutes after the later of its last run (`last.ts`) and its last
  publish or save (`updated`), on the workspace clock (di/core/clock.py). `due()` lists them; the worker's periodic step
  queues them (`tick()`). Counting from what the database holds keeps the suite's golden screens still: on the pinned
  as-of time every seeded schedule ran less than its interval ago (the demo's last runs are minutes old), so nothing
  is due, and the suite's worker is stopped anyway (scripts/dev/api-test.sh).
- event (`on_event`): a webhook for the workflow's source (di/connectors/webhook.py, both routes), of the workflow's
  event type when it has one (an Event trigger block's setting; `*` patterns as in fnmatch).
- approval (`on_approval`): an instruction queued for the workflow's target system (di/services/instructions/queue.py).
- file (`on_file`, through `file_arrived`): a sync of a source that delivers files (an SFTP or CSV drop: the Sims
  partner drop) read new records (di/worker.py, the `sync.source` job).
- case (`on_case`): a case needs a new decision, i.e. it moves to re-evaluation (declined, or changed after approval;
  di/services/cases/lifecycle.py move).

**The trigger blocks.** A graph with a Scheduler (x_sched) or Event trigger (x_evtrig) block sets the workflow's
trigger (`from_graph`): `{"t": "schedule", "min": interval_min}` or `{"t": "event", "type": event_type}` (no type: any
event). `trigger_of(w)` is what the triggers read: the block's trigger in the graph that runs (`graph_for_run`), else the
Settings tab's `trig`. Save keeps `trig` in step with the block (di/services/actions/workflows.py save), so the list's trigger
text and the Settings tab say the same ("Set by the Scheduler block").

A trigger queues a `workflow.run` job `{wf, trig}` without a run record (the label is the run record's `trig`:
Schedule, Event, File, Approval, Case). A webhook or an approval therefore changes no workspace state when it is
received; the worker makes the run record when it takes the job (`start()`, called by its `workflow.run` handler),
checking again that the workflow may run. One run at a time per workflow: no job is queued while the workflow is
running or a `workflow.run` job for it is queued or running (the dedupe key `wf:<id>` of the plan, done the way
di.connectors.sync.enqueue_sync does it until the job queue has dedupe keys).

DI_WORKFLOW_TRIGGERS=false switches every trigger off (`enabled()`); the api suite does (tests/conftest.py).
"""

import fnmatch
import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import jobs, state
from di.repositories.common import ms

log = logging.getLogger("di.triggers")

LABEL = {"schedule": "Schedule", "event": "Event", "file": "File", "approval": "Approval", "case": "Case"}
NOT_RUN = ("paused", "disconnected", "unavailable")  # the sources the connectors do not read (sync.NOT_SYNCED)
MIN_MS = 60_000


TRIGGER_BLOCKS = ("x_sched", "x_evtrig")


def from_graph(g: Any) -> dict | None:
    """The trigger a graph's Scheduler or Event trigger block sets (the first such block), or None."""
    from di.workflow.blocks import node_cfg

    nodes = g.get("nodes") if isinstance(g, dict) else None
    for n in nodes if isinstance(nodes, list) else []:
        if not isinstance(n, dict) or n.get("k") != "xf" or n.get("ref") not in TRIGGER_BLOCKS:
            continue
        cfg = node_cfg(n)
        if n["ref"] == "x_sched":
            m = cfg.get("interval_min")
            return {"t": "schedule", "min": int(m) if isinstance(m, int | float) and not isinstance(m, bool) and m >= 1 else 60}
        et = cfg.get("event_type")
        return {"t": "event"} | ({"type": et.strip()} if isinstance(et, str) and et.strip() else {})
    return None


def _run_graph(w: dict) -> Any:
    """The graph that runs, without building a template's graph (templates have no trigger blocks)."""
    pub = w.get("pub")
    return (pub or {}).get("graph") if pub else w.get("graph")


def trigger_of(w: dict) -> dict:
    """The workflow's trigger: its trigger block's, else the Settings tab's."""
    return from_graph(_run_graph(w)) or w.get("trig") or {}


def _kind(w: dict) -> str | None:
    return trigger_of(w).get("t")


def _source_ok(s: Session, w: dict) -> bool:
    sid = w.get("src")
    if not sid:
        return True
    from di.connectors import lifecycle

    status = s.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar()
    return status not in NOT_RUN and not lifecycle.is_deleted(s, sid)


def published_here(w: dict) -> bool:
    """Published in the app (it has a published version, `pub`, set by workflow.publish / setStatus). The demo's
    seeded "published" workflows have none: they stay illustrations and fire on no trigger, as they bind no sync and
    carry no outbound settings (binding.py, di/services/instructions/outbound.py); otherwise ~30 of them would run on every
    source event, approval and schedule and queue ahead of people's own work."""
    return bool(w.get("pub"))


def may_run(s: Session, w: dict) -> bool:
    return w.get("status") == "published" and published_here(w) and not w.get("running") and _source_ok(s, w)


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
    from di.repositories import workflows as studio

    return [
        w
        for w in studio.all_workflows(s)
        if _kind(w) == kind and w.get("status") == "published" and published_here(w) and (src is None or w.get("src") == src)
    ]


def _fire_all(s: Session, kind: str, src: str | None = None) -> list[str]:
    return [w["id"] for w in _matching(s, kind, src) if fire(s, w["id"], LABEL[kind]) is not None]


# ---------------------------------------------------------------- schedule
def due(s: Session, now: datetime) -> list[tuple[str, str]]:
    """(workflow id, trigger label) of the scheduled workflows whose interval has passed at `now`."""
    t = ms(now.isoformat())
    out = []
    for w in _matching(s, "schedule"):
        every = trigger_of(w).get("min")
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
def _bound(s: Session, source_id: str) -> str | None:
    from di.connectors import lifecycle

    return (state.get(s, lifecycle.COLLECTION, source_id) or {}).get("workflow")


def _type_ok(w: dict, event_type: str | None) -> bool:
    want = trigger_of(w).get("type")
    return not want or (event_type is not None and fnmatch.fnmatchcase(event_type, want))


def on_event(s: Session, source_id: str, event_type: str | None = None) -> list[str]:
    """A webhook for this source (an event of `event_type`): its published event-triggered workflows whose event type
    matches (or that take any event), except the one bound to the source's sync (source_config.workflow, plan 6 C5):
    the webhook already queues the sync, which runs that workflow, so firing it here too would ingest the same change
    twice."""
    bound = _bound(s, source_id)
    return [
        w["id"] for w in _matching(s, "event", source_id)
        if w["id"] != bound and _type_ok(w, event_type) and fire(s, w["id"], LABEL["event"]) is not None
    ]  # fmt: skip


def on_file(s: Session, source_id: str) -> list[str]:
    """New files landed for this source: its published file-triggered workflows, except the one bound to the source's
    sync (the sync that read the files ran it)."""
    bound = _bound(s, source_id)
    return [w["id"] for w in _matching(s, "file", source_id) if w["id"] != bound and fire(s, w["id"], LABEL["file"]) is not None]


def delivers_files(source_id: str, s: Any = None) -> bool:
    """A source that delivers files (an SFTP or CSV drop: arrival channel `file`). With a session, the sources as
    they are now (di/workflow/live.py), so a file source connected from the catalogue or made by hand counts too;
    without one, the demo's reference."""
    from di.repositories.reference import channels
    from di.services.actions.workflows import src, src_or_live

    so = src_or_live(source_id, s) if s is not None else src(source_id)
    return so is not None and "file" in channels(so)


def file_arrived(source_id: str, records_read: int) -> list[str]:
    """After a sync of the source (the worker's `sync.source` job): when it is a file source and the sync read new
    records (new files: an unchanged drop reads none), its file-triggered workflows run. Its own transaction; never
    raises, so a trigger never fails the sync."""
    from di.core.db import SessionLocal

    try:
        if records_read <= 0 or not enabled():
            return []
        with SessionLocal() as s:
            if not delivers_files(source_id, s):
                return []
            out = safely(on_file, s, source_id)
            s.commit()
        return out
    except Exception:
        log.exception("file triggers for %s failed", source_id)
        return []


def on_approval(s: Session, target_id: str) -> list[str]:
    """An instruction was queued for this target system: its published approval-triggered (outbound) workflows."""
    return _fire_all(s, "approval", target_id)


def on_case(s: Session, case_id: str) -> list[str]:
    """A case asked for a decision: the published case-triggered (decision) workflows."""
    if not enabled():  # called inside the case actions: no workflow scan while triggers are off
        return []
    log.debug("case request %s", case_id)
    return _fire_all(s, "case")


def safely(fn, s: Session, *args: Any) -> list[str]:
    """Run a trigger inside a savepoint: a trigger that fails is logged and undone, and never breaks its caller's
    transaction (a webhook, an instruction, a case's stage move)."""
    try:
        with s.begin_nested():
            return fn(s, *args)
    except Exception:
        log.exception("trigger %s%s failed", getattr(fn, "__name__", fn), args)
        return []


# ---------------------------------------------------------------- the worker takes the job
def start(payload: dict[str, Any]) -> dict[str, Any] | None:
    """For a `workflow.run` job queued by a trigger: make the run record (labelled with the trigger) and return the
    payload the run job takes, or None when the workflow may no longer run (deleted, paused, already running)."""
    from di.core.db import SessionLocal
    from di.services.actions import workflows as wf

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
