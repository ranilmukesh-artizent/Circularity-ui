"""Records a Wait step (x_wait) parks, and the run that comes back for them (plan 6 follow-up).

    park(s, wf, node, run_id, recs, resume_at, now) -> key | None   in the run's transaction
    load(s, key)                                    -> (node id, records) | None
    resume({"wait": key})                           -> what happened (the worker's `workflow.resume` handler)

**Where the records wait.** In the workspace collection "workflow_waits" (table state_item, so no migration): one item
per Wait step and run, {id, wf, node, run, at, records}, each record as {ext_id, resource, data, facts, meta}. With it
a `workflow.resume` job {wait, wf} is queued, due `at - now` later on the wall clock (the job's run_after; the
workspace clock may be pinned, so it cannot be waited on), and the worker takes it then.

**Coming back.** The job makes a run record labelled "Resume" (as a trigger does) and runs the workflow's graph that
runs now (graph_for_run) through the run job with the wait's key: the engine skips every step before and beside the
Wait step, gives the Wait step the parked records with `ctx.resumed`, and runs the steps after it as usual (the
canvas shows the others skipped). The Wait step decides again: after a Duration everything goes on; with Until, the
records that meet it go on and the rest are parked again (a new item and job) until 7 days have passed, then held.
Until is checked on each record's newest landed version (raw_record), for records not yet mapped to facts.

When the job finds the workflow running, or paused, it comes back later (RETRY_MIN); a workflow that was deleted takes
its waiting records with it; a Wait step that is no longer in the graph holds them (failed_record, rule `wait`) so
they can be reprocessed. A test run (dry) parks nothing.
"""

import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di import jobs, state
from di.canonical.store import Fact
from di.workflow.steps.core import Rec, parse_ts

log = logging.getLogger("di.workflow.waits")
COLLECTION = "workflow_waits"
RETRY_MIN = 1  # the workflow is running or paused: try again this much later
state.register(COLLECTION, lambda: [])


def _plain(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


def _dump(r: Rec) -> dict:
    facts = [asdict(f) for f in r.facts] if r.facts is not None else None
    return _plain({"ext_id": r.ext_id, "resource": r.resource, "data": r.data, "facts": facts, "meta": r.meta})


def _rec(d: dict) -> Rec:
    facts = [Fact(**f) for f in d["facts"]] if d.get("facts") is not None else None
    return Rec(d["ext_id"], d["resource"], dict(d.get("data") or {}), facts, dict(d.get("meta") or {}))


def _queue(s: Session, key: str, wid: str, seconds: float) -> int:
    """The `workflow.resume` job, due `seconds` from now on the database's (wall) clock."""
    job = jobs.enqueue(s, "workflow.resume", {"wait": key, "wf": wid})
    s.execute(
        text("UPDATE job SET run_after = now() + make_interval(secs => :d) WHERE id = :i"),
        {"d": max(0.0, float(seconds)), "i": job.id},
    )
    return job.id


def park(s: Session, wf: dict, node: dict, run_id: Any, recs: list[Rec], resume_at: str, now: datetime) -> str | None:
    """Keep the records a Wait step holds back and queue the run that comes back for them: due `resume_at - now`
    later (`now`: the run's time, the workspace clock), counted on the wall clock, since the workspace clock may be
    pinned. None when the run belongs to no stored workflow (nothing could resume it)."""
    wid = (wf or {}).get("id")
    if not wid or state.get(s, "workflows", wid) is None:
        log.warning("wait step %s: no stored workflow %s to come back to; %s records not parked", node.get("id"), wid, len(recs))
        return None
    key = f"WAIT-{uuid.uuid4().hex[:12]}"
    item = {"id": key, "wf": wid, "node": node["id"], "run": run_id, "at": resume_at, "records": [_dump(r) for r in recs]}
    state.add(s, COLLECTION, key, item)
    at = parse_ts(resume_at)
    _queue(s, key, wid, (at - now).total_seconds() if at is not None else 0)
    return key


def _newest(s: Session, r: Rec) -> Rec:
    """The record with its newest landed payload (raw_record), when it is not yet mapped to facts."""
    sid = r.meta.get("source_id")
    if r.facts is not None or not sid:
        return r
    p = s.execute(
        text("SELECT payload FROM raw_record WHERE source_id = :s AND resource = :r AND ext_id = :e"),
        {"s": sid, "r": r.resource, "e": r.ext_id},
    ).scalar()
    return Rec(r.ext_id, r.resource, dict(p), None, r.meta) if isinstance(p, dict) else r


def load(s: Session, key: str) -> tuple[str, list[Rec]] | None:
    """The Wait step and the records parked under `key`, each with its newest landed payload."""
    item = state.get(s, COLLECTION, key)
    if item is None:
        return None
    return item["node"], [_newest(s, _rec(d)) for d in item["records"]]


def _later(s: Session, key: str, wid: str) -> None:
    _queue(s, key, wid, RETRY_MIN * 60)


def _hold_all(s: Session, item: dict, reason: str) -> None:
    from di.canonical.failed import hold

    for d in item["records"]:
        r = _rec(d)
        hold(s, run_kind="workflow", reason=reason, run_id=item.get("run"), source_id=r.meta.get("source_id"),
             step=item["node"], resource=r.resource, ext_id=r.ext_id, rule="wait", payload=r.data)  # fmt: skip


def resume(payload: dict) -> dict:
    """The `workflow.resume` job: run the workflow on from the Wait step with the records parked under payload.wait
    (see the module docstring). The parked item goes once the run took it."""
    from di.actions import workflows as wfa
    from di.db import SessionLocal

    key = payload["wait"]
    with SessionLocal() as s:
        item = state.get(s, COLLECTION, key, for_update=True)
        if item is None:
            return {"wait": key, "skipped": "gone"}
        wid = item["wf"]
        w = state.get(s, "workflows", wid, for_update=True)
        if w is None:
            state.delete(s, COLLECTION, key)
            s.commit()
            return {"wait": key, "skipped": "workflow deleted"}
        if w.get("status") == "paused" or (w.get("running") and wfa.run_active(s, wid)):
            _later(s, key, wid)
            s.commit()
            return {"wait": key, "deferred": "paused" if w.get("status") == "paused" else "running"}
        wfa.reap_lost_run(s, w, wfa._now())
        if item["node"] not in {n["id"] for n in wfa.graph_for_run(w)["nodes"]}:
            _hold_all(s, item, "the Wait step is no longer in the workflow")
            state.delete(s, COLLECTION, key)
            s.commit()
            return {"wait": key, "held": len(item["records"])}
        run_key = wfa.start_run(s, w, "Resume", wfa._now(), enqueue=False)
        s.commit()
    out = wfa.run_job({"run": run_key, "wf": wid, "trig": "Resume", "wait": key})
    with SessionLocal() as s:
        if out.get("skipped") == "already_running":
            _later(s, key, wid)
        else:
            state.delete(s, COLLECTION, key)
        s.commit()
    return {"wait": key, **out}


__all__ = ["COLLECTION", "load", "park", "resume"]
