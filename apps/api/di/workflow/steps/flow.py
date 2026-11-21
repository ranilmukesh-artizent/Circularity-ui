# ruff: noqa: ARG001 - every step has the STEPS signature (records, cfg, ctx); not every step needs ctx
"""Orchestration and sink steps (plan 6, task C4): wait, loop, call workflow, error handler, audit log, publish.

Minimal semantics: the engine (task C5) owns timing and calling other workflows, so x_wait and x_call say what they
need in `side` (resume_at, call) and pass the records on. The sinks collect; the only writes are the error handler's
held records (failed_record) and the published event (stream_event), and neither happens when ctx.dry.
"""

import json
from datetime import timedelta

from sqlalchemy import text

from di.workflow.steps.core import Rec, Reject, StepCtx, StepResult, clone, condition, get, iso_z, log, opt

# the settings each step reads (keys of di/workflow/blocks.py)
KEYS = {
    "x_wait": {"duration": "duration_min", "until": "until"},
    "x_loop": {"items": "items_path"},
    "x_call": {"workflow": "workflow"},
    "x_err": {"action": "action"},
    "x_audit": {"level": "level"},
    "x_pub": {"topic": "topic"},
}


def x_wait(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Records that meet `until` (an expression; empty: all) go on, the others wait (side.waiting); with a duration,
    side.resume_at is when the engine should go on."""
    k = KEYS["x_wait"]
    minutes, until = opt(cfg, k["duration"], 0), opt(cfg, k["until"], "")
    test = condition(until)
    out: list[Rec] = []
    waiting: list[Rec] = []
    for r in recs:
        (out if test(r) else waiting).append(clone(r))
    side: dict = {"waiting": waiting}
    if minutes:
        side["resume_at"] = iso_z(ctx.now + timedelta(minutes=minutes))
    return StepResult(out, [], side)


def x_loop(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """One record per item of the list at the items path ("<id>#<n>", meta.parent and meta.index); a record without
    such a list goes on as it is. Items path empty: each record as it is."""
    path = opt(cfg, KEYS["x_loop"]["items"], "")
    if not path:
        return StepResult([clone(r) for r in recs], [], {})
    out, expanded = [], 0
    for r in recs:
        items = get(r, path)
        if not isinstance(items, list):
            out.append(clone(r))
            continue
        expanded += 1
        for i, it in enumerate(items):
            data = dict(it) if isinstance(it, dict) else {"value": it}
            out.append(Rec(f"{r.ext_id}#{i}", r.resource, data, None, {**r.meta, "parent": r.ext_id, "index": i}))
    return StepResult(out, [], {"expanded": expanded})


def x_call(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Pass-through; side.call names the workflow the engine runs with these records."""
    wf = opt(cfg, KEYS["x_call"]["workflow"], "")
    return StepResult([clone(r) for r in recs], [], {"call": {"workflow": wf, "records": len(recs)}} if wf else {})


def _summary(j: Reject) -> dict:
    return {
        "ext_id": j.rec.ext_id,
        "resource": j.rec.resource,
        "field": j.field,
        "rule": j.rule,
        "value": j.value,
        "reason": j.reason,
    }


def x_err(recs: list, cfg: dict, ctx: StepCtx) -> StepResult:
    """Receives the rejected records of the steps before it (Reject, or Rec for a record sent here whole). `action`
    hold: each is held in failed_record for reprocessing (not when ctx.dry); drop: counted only. Nothing goes on."""
    action = opt(cfg, KEYS["x_err"]["action"], "hold")
    rejects = [j if isinstance(j, Reject) else Reject(j, None, "error", None, "sent to the error handler") for j in recs]
    held: list[int] = []
    if action == "hold" and not ctx.dry and ctx.s is not None:
        from di.canonical.failed import hold

        for j in rejects:
            held.append(hold(
                ctx.s, run_kind="workflow", reason=j.reason, run_id=ctx.run_id, source_id=ctx.source_id,
                step=(ctx.node or {}).get("id"), resource=j.rec.resource, ext_id=j.rec.ext_id, field=j.field,
                rule=j.rule, value=j.value, payload=j.rec.data,
            ))  # fmt: skip
    side = {"rejects": [_summary(j) for j in rejects], "held": len(rejects) if action == "hold" else 0,
            "dropped": len(rejects) if action == "drop" else 0, "held_ids": held}  # fmt: skip
    log(ctx, f"error handler: {len(rejects)} records {'held' if action == 'hold' else 'dropped'}")
    return StepResult([], [], side)


def x_audit(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Run status and counts to the run's log (ctx.log) at the level; the records pass on."""
    level = opt(cfg, KEYS["x_audit"]["level"], "info")
    audit = {"level": level, "records": len(recs), "run_id": ctx.run_id, "workflow": (ctx.wf or {}).get("id")}
    log(ctx, f"[{level}] audit: {len(recs)} records")
    return StepResult([clone(r) for r in recs], [], {"audit": audit})


def x_pub(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """A model-updated event on the live stream (stream_event, kind workflow) naming the topic and the records' keys;
    not when ctx.dry or nothing changed. The records pass on. The payload has the stream's workflow shape
    ({collection, op, id, data}, as migration 0009's trigger writes it) under its own collection, "published", so the
    Studio's listeners, which read workflow_runs and workflows, are not confused by it."""
    topic = opt(cfg, KEYS["x_pub"]["topic"], "model.updated")
    keys = [r.ext_id for r in recs]
    sent = bool(recs) and not ctx.dry and ctx.s is not None
    if sent:
        data = {"type": "model.updated", "topic": topic, "workflow": (ctx.wf or {}).get("id"),
                "run_id": ctx.run_id, "count": len(keys), "keys": keys[:50]}  # fmt: skip
        payload = {"collection": "published", "op": "insert", "id": f"{ctx.run_id}:{(ctx.node or {}).get('id', '')}",
                   "data": data}  # fmt: skip
        ctx.s.execute(text("SELECT stream_put('workflow', NULL, CAST(:p AS jsonb))"), {"p": json.dumps(payload, default=str)})
    return StepResult(
        [clone(r) for r in recs], [], {"publish": {"topic": topic, "count": len(keys), "keys": keys[:50], "sent": sent}}
    )


STEPS = {"x_wait": x_wait, "x_loop": x_loop, "x_call": x_call, "x_err": x_err, "x_audit": x_audit, "x_pub": x_pub}
