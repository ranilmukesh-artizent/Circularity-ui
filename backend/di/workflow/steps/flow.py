# ruff: noqa: ARG001 - every step has the STEPS signature (records, cfg, ctx); not every step needs ctx
"""Orchestration and sink steps (plan 6, task C4): wait, loop, call workflow, error handler, audit log, publish.

x_wait says which records wait and when to come back (side.waiting, side.resume_at); the engine parks them and queues
the run that comes back (di/workflow/waits.py). x_call starts the other workflow (a `workflow.run` job with trigger
"Workflow", through di/workflow/triggers.fire). The writes: the error handler's held records (failed_record), the audit
entry (the "events" log the Audit page reads), the published event (stream_event) and the called workflow's job; none
of them happens when ctx.dry.
"""

import json
import re
from datetime import UTC, timedelta

from sqlalchemy import text

from di.workflow.steps.core import (
    Rec,
    Reject,
    StepCtx,
    StepError,
    StepResult,
    clone,
    condition,
    get,
    iso_z,
    log,
    opt,
    parse_ts,
)

RECHECK_MIN = 15  # x_wait: how often Until is checked again when Duration is 0
MAX_WAIT_MIN = 10080  # x_wait: a record waits at most 7 days (Duration's maximum), then it is held

# the settings each step reads (keys of di/workflow/blocks.py)
KEYS = {
    "x_wait": {"duration": "duration_min", "until": "until"},
    "x_loop": {"items": "items_path"},
    "x_call": {"workflow": "workflow"},
    "x_err": {"action": "action"},
    "x_audit": {"level": "level"},
    "x_pub": {"topic": "topic"},
    "x_case": {
        "template": "template",
        "reason": "reason",
        "asset": "asset_field",
        "org": "org_unit_id",
        "only": "only_if",
        "reason_field": "reason_field",
        "facts": "facts",
    },
}


def x_wait(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Which records go on now and which wait (side.waiting, each with meta.wait_since), and when the run comes back
    for them (side.resume_at); the engine parks the waiting ones (di/workflow/waits.py, not when dry).

    - Duration and Until empty: every record goes on (the default).
    - Duration only: every record waits Duration minutes; when the run comes back (ctx.resumed) they all go on.
    - Until: records that meet it go on; the others wait and are checked again every Duration minutes (0: every
      RECHECK_MIN), each time on their newest landed version. A record still waiting MAX_WAIT_MIN (7 days) after it
      first waited is rejected (rule `wait`), so it is held instead of waiting for ever."""
    k = KEYS["x_wait"]
    minutes, until = opt(cfg, k["duration"], 0), opt(cfg, k["until"], "")
    test = condition(until)
    out: list[Rec] = []
    waiting: list[Rec] = []
    rejected: list[Reject] = []
    for r in recs:
        go = test(r) if until else (ctx.resumed or not minutes)
        c = clone(r)
        if go:
            c.meta.pop("wait_since", None)
            out.append(c)
            continue
        since = parse_ts(r.meta.get("wait_since")) or ctx.now
        if ctx.now - since >= timedelta(minutes=MAX_WAIT_MIN):
            rejected.append(Reject(r, None, "wait", until or None, f"Until ({until}) was not met within 7 days"))
            continue
        c.meta["wait_since"] = iso_z(since)
        waiting.append(c)
    side: dict = {"waiting": waiting}
    if waiting:
        side["resume_at"] = iso_z(ctx.now + timedelta(minutes=minutes or RECHECK_MIN))
    return StepResult(out, rejected, side)


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


def _calls(w: dict, wid: str) -> bool:
    """The graph that runs for `w` has a Call workflow step calling `wid`."""
    from di.services.actions.workflows import graph_for_run

    return any(
        n.get("k") == "xf" and n.get("ref") == "x_call" and (n.get("cfg") or {}).get("workflow") == wid
        for n in graph_for_run(w).get("nodes") or []
    )


def x_call(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """Starts the named workflow: a `workflow.run` job with trigger "Workflow" (triggers.fire: only a published
    workflow that is not running or queued, and only while workflow triggers are on), passing nothing. Not when
    ctx.dry. Calling its own workflow, a workflow that does not exist, or one that calls this one back (a cycle of one
    hop) fails the step. The records pass on; side.call says what happened (started, and why not)."""
    target = str(opt(cfg, KEYS["x_call"]["workflow"], "")).strip()
    out = [clone(r) for r in recs]
    if not target:
        return StepResult(out, [], {})
    me = (ctx.wf or {}).get("id")
    if target == me:
        raise StepError(f"Call workflow cannot call its own workflow ({me})")
    call: dict = {"workflow": target, "records": len(recs)}
    if ctx.s is not None:
        from di.core import state

        other = state.get(ctx.s, "workflows", target)
        if other is None:
            raise StepError(f"Call workflow: there is no workflow {target}")
        if me and _calls(other, me):
            raise StepError(f"Call workflow: {target} calls {me} back, so the calls would go round in a circle")
        if not ctx.dry:
            from di.workflow import triggers

            job = triggers.fire(ctx.s, target, "Workflow")
            call["started"] = job is not None
            if job is None:
                call["why"] = (
                    "workflow triggers are off" if not triggers.enabled()
                    else f"{target} is not published" if other.get("status") != "published"
                    else f"{target} is running or queued already"
                )  # fmt: skip
            log(ctx, f"call workflow {target}: " + ("started" if job is not None else f"not started ({call['why']})"))
    return StepResult(out, [], {"call": call})


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
        from di.services.canonical.failed import hold

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


def _audit_entry(ctx: StepCtx, level: str, count: int) -> str:
    """One entry in the workspace event log ("events", what the Audit page lists), journal-free: type
    workflow.audit, naming the workflow, the run, the step, the level and the record count. Returns its id."""
    from di.core import state
    from di.services.actions.decisions import EVENT_SEQ_START
    from di.workflow.engine import label

    wf, node = ctx.wf or {}, ctx.node or {}
    wid, step = wf.get("id"), label(node, ctx.s) if node.get("k") else node.get("id")
    n = state.next_number(ctx.s, "events", "EV-", EVENT_SEQ_START)
    now = ctx.now.astimezone(UTC)
    e = {
        "id": f"EV-{n}", "dir": "in", "type": "workflow.audit", "caseId": None, "decisionId": None, "approval": None,
        "ver": None, "dest": f"Circularity · workflow {wf.get('name') or wid}", "ack": "recorded",
        "key": f"{wid}/{node.get('id')}", "note": f"{wid} · run {ctx.run_id} · step {step}: {count} records ({level})",
        "by": None, "ts": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z", "prep": None,
        "run": ctx.run_id, "akey": None, "level": level, "records": count, "wf": wid, "step": node.get("id"),
    }  # fmt: skip
    state.add(ctx.s, "events", e["id"], e)
    return e["id"]


def x_audit(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """One entry per run step in the audit log (`_audit_entry`: the Audit page's event log) with the level and the
    record count, and a line in the run's log (ctx.log); not when ctx.dry. The records pass on."""
    level = opt(cfg, KEYS["x_audit"]["level"], "info")
    audit = {"level": level, "records": len(recs), "run_id": ctx.run_id, "workflow": (ctx.wf or {}).get("id")}
    if not ctx.dry and ctx.s is not None:
        audit["event"] = _audit_entry(ctx, level, len(recs))
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


def _only_if(spec: str) -> tuple[str, str] | None:
    """Only if's "field=value" (None: every record)."""
    if not spec.strip():
        return None
    field_, sep, value = spec.partition("=")
    if not sep or not field_.strip():
        raise StepError(f"Open case: Only if must read field=value, not {spec!r}")
    return field_.strip(), value.strip()


def _reason_spec(spec: str) -> tuple[str, dict[str, str]]:
    """Reason field's "field" or "field: value=reason, value=reason" as (field, map); no field: ("", {})."""
    field_, _, pairs = spec.partition(":")
    out = {}
    for pair in pairs.split(","):
        if pair.strip():
            value, _, reason = pair.partition("=")
            out[value.strip()] = reason.strip()
    return field_.strip(), out


def reason_of(data: dict, fixed: str, spec: str) -> str:
    """The reason a record opens its case for: the value of the Reason field through the map (a value the map leaves out
    is used as it is), else the fixed Reason (no spec, or the record has no value)."""
    field_, mapping = _reason_spec(spec)
    value = data.get(field_) if field_ else None
    return fixed if value in (None, "") else mapping.get(str(value), str(value))


def facts_of_record(data: dict, fields: list) -> dict:
    """The listed record fields as the case's facts, under their snake case names (toolClass -> tool_class); a field the
    record lacks is left out."""
    return {re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(f)).lower(): data[f] for f in fields if data.get(f) not in (None, "")}


def _publisher(wf: dict) -> str:
    """Who published the workflow (its newest "Published" history line), else its owner."""
    pub = next((h.get("by") for h in wf.get("hist") or [] if h.get("note") == "Published" and h.get("by")), None)
    return str(pub or wf.get("owner") or "system")


def _source_org(ctx: StepCtx) -> str | None:
    if ctx.s is None or not ctx.source_id:
        return None
    return ctx.s.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": ctx.source_id}).scalar()


def x_case(recs: list[Rec], cfg: dict, ctx: StepCtx) -> StepResult:
    """A case for each record passing Only if (field=value), for the asset key at Asset field, through
    di.services.cases.intake.open_case as the system, with the workflow's publisher recorded as `by`; the org unit is
    the setting or else the source's. A record whose asset and reason already have a case is skipped (a re-sync, a
    replay), as is one without an asset key; one intake refuses (no asset class ...) is counted with its reason. In a
    dry run nothing opens: the step says "Would open N cases". The records pass on; side.cases says what happened.
    Plan 9 (P9-3.4): Reason field ("kind", or "kind: value=reason, ...") takes each record's reason from the record,
    Facts copies the listed record fields into the case's facts (snake case names); without them it is as before."""
    k = KEYS["x_case"]
    only = _only_if(str(opt(cfg, k["only"], "")))
    field_ = str(opt(cfg, k["asset"], "")).strip()
    if not field_:
        raise StepError("Open case needs the Asset field that holds the asset key")
    org = str(opt(cfg, k["org"], "")).strip() or _source_org(ctx)
    if not org:
        raise StepError("Open case needs an Org unit: set one, or bind the source to an org unit")
    picked = [r for r in recs if only is None or str(get(r, only[0], "")) == only[1]]
    keys = [str(v) for r in picked if (v := get(r, field_)) not in (None, "")]
    out = [clone(r) for r in recs]
    cases: dict = {"passing": len(picked), "opened": [], "skipped": len(picked) - len(keys), "failed": []}
    if ctx.dry or ctx.s is None:
        cases["would_open"] = len(keys)
        log(ctx, f"Would open {len(keys)} cases")
        return StepResult(out, [], {"cases": cases})
    from di.services.actions.registry import ActionError
    from di.services.cases import intake

    base = {"org_unit_id": org, "template_key": opt(cfg, k["template"], "industrial"), "by": _publisher(ctx.wf or {})}
    fixed, spec, fields = str(opt(cfg, k["reason"], "rma")), str(opt(cfg, k["reason_field"], "")), list(opt(cfg, k["facts"], []))
    for r in picked:
        if (key := get(r, field_)) in (None, ""):
            continue
        key = str(key)
        reason = reason_of(r.data, fixed, spec)
        i = base | {"asset_key": key, "reason": reason} | ({"facts": facts_of_record(r.data, fields)} if fields else {})
        try:
            with ctx.s.begin_nested():
                cases["opened"].append(intake.open_case(ctx.s, i, "system")["id"])
        except ActionError as e:
            if e.code == "duplicate":
                cases["skipped"] += 1
            else:
                cases["failed"].append({"asset_key": key, "reason": e.message})
    log(ctx, f"open case: {len(cases['opened'])} opened, {cases['skipped']} skipped, {len(cases['failed'])} not opened")
    return StepResult(out, [], {"cases": cases})


STEPS = {
    "x_wait": x_wait, "x_loop": x_loop, "x_call": x_call, "x_err": x_err, "x_audit": x_audit, "x_pub": x_pub,
    "x_case": x_case,
}  # fmt: skip
