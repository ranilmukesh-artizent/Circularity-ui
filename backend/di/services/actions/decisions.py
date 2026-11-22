"""Decision and case-work actions (B12): decision.prepare, submit, approve, override, decline; evidence.request,
evidence.recordResult, case.reevaluate; scenario.save and delete; notify.send and acknowledge, comment.add, escalation.send.

Ports of the demo's handlers (index.html, `defAction('decision.submit', ...)` and the ones after it). The pipeline has
already validated the input and checked the permission, the tenant boundary and the warehouse lock; the guards here
are the demo's state checks, in its order.

**The clock.** The workspace runs on the demo's clock, pinned to its as-of time (see di.repositories.common), so every stamp a
handler writes (approval, submission, events, notifications) is that time. Each handler also pins `ctx.now`, so the
journal entry (which the case run reads back as "who acted, when") carries the same time.

**Random draws.** The demo runs each state-changing handler on a generator seeded from the action's key
(`seeded(ctx.key, ...)`), so its draws are a function of the key, not of history. `_seeded` is that generator, which
lets evidence.recordResult and case.reevaluate rebuild routes to the dollar.
"""

import copy
import math
from collections.abc import Callable
from typing import Any

from di.core import policy, state
from di.repositories.common import AS_OF, case_demand, hash_id, iso, limit_for, money
from di.services import instructions
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionError, guard, implement
from di.services.cases import lifecycle, store
from di.services.engine.evaluate import build_routes
from di.services.engine.predictor import FormulaPredictor
from di.services.engine.routes import GATES, SUSTAINABILITY, fail, rank_routes
from di.services.execution.steps import approval_ref, steps_for  # the execution steps (B13 moved them to di.services.execution)

NOW = iso(AS_OF)  # the demo's asOfNow(), pinned

# ---------------------------------------------------------------- workspace collections written here
# Saved what-if scenarios (the demo's S.ti.saved, per case) and comments (S.cm, per record key). Both start empty.
state.register("scenarios", list)
state.register("comments", list)
WORKBENCH_WEIGHTS = {"net": 50, "time": 20, "env": 15, "serv": 15}  # S.ti.w: the Workbench's default fit weights
NOTE_SEQ_START = 101  # S.ntSeq starts at 102
EVENT_SEQ_START = 9091  # EV_SEQ: the starting log ends at EV-9091


# ---------------------------------------------------------------- helpers
def _seeded(key: str) -> Callable[[], float]:
    """The demo's seeded(key): mulberry32 seeded from the key's hashId. Unsigned 32-bit arithmetic throughout, which
    gives JavaScript's int32 results bit for bit."""
    a = int(hash_id(key), 16)

    def imul(x: int, y: int) -> int:
        return (x * y) & 0xFFFFFFFF

    def rnd() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rnd


def _wpick(rnd: Callable[[], float], pairs: list[tuple[str, float]]) -> str:
    r = rnd() * sum(w for _, w in pairs)
    for v, w in pairs:
        r -= w
        if r <= 0:
            return v
    return pairs[-1][0]


def _key(action: str, i: dict, ctx: CallContext) -> str:
    """The demo's ctx.key: the idempotency key, taken before the handler changes what it depends on (the cycle)."""
    a = ACTIONS[action]
    return f"{action}:{a.idem(i, ctx)}" if a.idem else action


def _by(ctx: CallContext) -> str:
    """Who acts (the demo's x.by)."""
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


def _case(ctx: CallContext, case_id: str) -> store.Case:
    c = store.get(ctx.session, case_id, for_update=True)
    if c is None:
        raise ActionError("not_found", f"No live case {case_id}.")
    return c


def _peek(ctx: CallContext, case_id: str) -> store.Case:
    """The case for a guard (the pipeline has checked it exists)."""
    c = store.get(ctx.session, case_id)
    if c is None:
        raise ActionError("not_found", f"No live case {case_id}.")
    return c


def cyc(c: store.Case) -> int:
    return c.get("cycle") or 0


def skey(c: store.Case, stage: int, x: object = None) -> str:
    """The demo's stage key: <case>:<stage>[:<step>], so a repeat is a no-op."""
    return f"{c['id']}:{stage}" + (f":{x}" if x is not None else "")


def push_event(ctx: CallContext, e: dict, key: str | None) -> dict:
    """The demo's pushEvent: a new event at the head of the log (EVENTS), stamped with the action that made it."""
    s = ctx.session
    n = state.next_number(s, "events", "EV-", EVENT_SEQ_START)
    e = {
        **e,
        "id": f"EV-{n}",
        "ts": e.get("ts") or NOW,
        "by": e.get("by") or _by(ctx),
        "prep": ctx.preparer,
        "run": ctx.run_id,
        "akey": key,
    }
    return state.add(s, "events", e["id"], e)


def rb_log(ctx: CallContext, type_: str, note: str, key: str) -> dict:
    """The demo's rbLog: an access-control entry in the event log."""
    return push_event(
        ctx,
        {
            "dir": "in", "type": type_, "caseId": None, "decisionId": None, "approval": None, "ver": None,
            "dest": "Circularity · access control", "ack": "acknowledged",
            "key": "acc-" + hash_id(type_ + note + key)[:6].lower(), "note": note, "by": _by(ctx), "ts": NOW,
        },
        key,
    )  # fmt: skip


def _decision_id(c: store.Case) -> str:
    return "DI-2026-" + c["id"][3:]


def _rebuild(c: store.Case, rnd: Callable[[], float]) -> None:
    """The demo's buildRoutes on the action's generator, then rankRoutes. The demo's last draw decides whether the
    recycler needs a hazardous-waste route for a battery or IT lot; it comes after every valuation draw, so it is
    taken after build_routes (the engine's only later rule, Economics, never excludes material: its net is positive)."""
    routes = build_routes({**c, "hazardousMaterial": False}, FormulaPredictor(rnd))
    if c["cls"] in ("batch", "it"):
        m = next((r for r in routes if r["id"] == "material"), None)
        if m and rnd() < 0.12:
            fail(m, SUSTAINABILITY, "Cell chemistry requires an approved hazardous-waste route")
    c["routes"] = routes
    c["recommendation"] = rank_routes(routes, c.get("blocked"))


def _rerank(c: store.Case) -> None:
    c["recommendation"] = rank_routes(c["routes"], c.get("blocked"))


# ---------------------------------------------------------------- decision flow
@guard("decision.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    if c["stage"] != "awaiting_approval":
        return "conflict", f"{c['id']} is not awaiting approval."
    if c.get("submitted"):
        return "duplicate", f"{c['id']} is already submitted"
    return None


def _submit_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 7, f"submit:{cyc(c)}")


@implement("decision.submit", idem=_submit_idem, emits=["decision.submitted"])
def submit(i: dict[str, Any], ctx: CallContext):
    key = _key("decision.submit", i, ctx)
    c, by = _case(ctx, i["case_id"]), _by(ctx)
    # byId: the demo adds it right after (afOn('action')), for the self-approval rule
    c["submitted"] = {"by": by, "at": NOW, "byId": ctx.actor.id}
    push_event(
        ctx,
        {
            "dir": "out", "type": "decision.submitted", "caseId": c["id"], "decisionId": _decision_id(c), "approval": None,
            "ver": None, "dest": "Approver queue", "ack": "acknowledged",
            "key": "sub-" + hash_id(f"{c['id']}{cyc(c)}")[:6].lower(), "note": "Submitted for review by " + by, "by": by,
            "ts": NOW,
        },
        key,
    )  # fmt: skip
    store.save(ctx.session, c)
    return {"case_id": c["id"], "submitted_by": by}


def _ap_guard(i: dict[str, Any], ctx: CallContext, c) -> tuple[str, str] | None:  # noqa: ARG001 - guards take (input, ctx, case)
    """The demo's apReviewed and apGuard: shared by approve and override."""
    if i.get("reviewed") is not True:
        return "validation_error", "Confirm that you reviewed the evidence snapshot."
    if c["stage"] != "awaiting_approval":
        return "conflict", f"{c['id']} is not awaiting approval."
    t = next((r for r in c["routes"] if r["plan"] == i.get("route")), None)
    if i.get("route") and not t:
        return "not_found", f'No route "{i["route"]}" on {c["id"]}.'
    if t and t["excluded"]:
        return (
            "conflict",
            f"An excluded route cannot be approved: {GATES[t['failGate']]} failed. Failed gates are resolved by "
            "engineering and policy owners, never waived.",
        )
    if not c.get("recommendation"):
        return "conflict", "No eligible route to approve."
    return None


def _ap_policy(i: dict[str, Any], ctx: CallContext, c) -> tuple | None:
    """The demo's afPolicy: no self-approval, and the approver's limit (the larger of the route's net and the spend).
    A limit refusal carries `escalate: 'admin'`, as in the demo."""
    r = next((x for x in c["routes"] if x["plan"] == i.get("route")), None) or c.get("recommendation")
    val = max(abs(r["net"] if r else 0), _spend(i))
    lim = limit_for(ctx.actor.account, ctx.actor.ctx)  # AF.cfg.limits, as Admin set them
    sub = c.get("submitted")
    if sub and sub.get("byId") == ctx.actor.id and not ctx.actor.ctx.self_approval:  # AF.cfg.self
        return (
            "out_of_scope",
            f"You submitted {c['id']}, so another person must approve it. Admin can allow self-approval within a limit.",
        )
    if val > lim:
        return (
            "limit_exceeded",
            f"{c['id']} is worth {money(val)}, above your approval limit of {money(lim)}. It escalates to Admin.",
            {"escalate": "admin"},
        )
    return None


def _spend(i) -> float:
    """`+i.spend || 0`."""
    v = i.get("spend")
    return v if isinstance(v, int | float) and not isinstance(v, bool) and not math.isnan(v) else 0


@guard("decision.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    g = _ap_guard(i, ctx, c)
    rec = c.get("recommendation")
    if not g and i.get("route") and rec and i["route"] != rec["plan"]:
        g = "conflict", "That route is not the recommendation; use Override."
    return g or _ap_policy(i, ctx, c)


@guard("decision.override")
def override_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return _ap_guard(i, ctx, c) or _ap_policy(i, ctx, c)


def _approve_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 7, cyc(c))


def _approve(action: str, i: dict[str, Any], ctx: CallContext) -> dict:
    """The demo's approveHandler: the approval, the execution plan with its first step active, and the instruction."""
    key = _key(action, i, ctx)
    c, by = _case(ctx, i["case_id"]), _by(ctx)
    rec = c["recommendation"]
    t = next((r for r in c["routes"] if r["plan"] == i.get("route")), None) or rec
    is_ov = t is not rec
    ref = approval_ref(c["id"]) + (f"-{cyc(c) + 1}" if cyc(c) else "")
    c["chosen"] = copy.deepcopy(t)
    steps = steps_for(t)
    steps[0]["activeAt"] = NOW
    c["exec"] = {
        "ref": ref,
        "decisionId": _decision_id(c),
        "instruction": 1,
        "steps": steps,
        "dest": steps[0]["sys"].split(" · ")[0] + " / " + steps[1]["sys"].split(" · ")[0],
        "approvedAt": NOW,
        "approver": by,
    }
    c["approval"] = {
        "ref": ref, "by": by, "at": NOW, "rationale": i["rationale"], "spend": _spend(i), "terms": i.get("terms") or "",
        "prep": ctx.preparer,
    }  # fmt: skip
    if is_ov:
        c["override"] = {"rec": rec["plan"], "chosen": t["plan"], "reason": i["rationale"]}
    push_event(
        ctx,
        {
            "dir": "out", "type": "instruction.sent", "caseId": c["id"], "decisionId": c["exec"]["decisionId"],
            "approval": ref, "ver": 1, "dest": steps[0]["sys"], "ack": "sent · awaiting ack",
            "key": "idem-" + hash_id(c["id"] + ref)[:6].lower(), "retries": 0,
            "note": "Override approved with reason" if is_ov else "", "sim": True,
        },
        key,
    )  # fmt: skip
    lifecycle.move(ctx.session, c, "approved", f"{'Override approved' if is_ov else 'Approved'} under {ref}", ctx.actor.id)
    instructions.queue_first(ctx.session, c)  # B13b: the first step goes to its system (when sending is on)
    return {"case_id": c["id"], "ref": ref, "route": t["plan"], "net": t["net"], "override": is_ov, "sent_to": steps[0]["sys"]}


@implement("decision.approve", idem=_approve_idem, emits=["instruction.sent"])
def approve(i: dict[str, Any], ctx: CallContext):
    return _approve("decision.approve", i, ctx)


@implement("decision.override", idem=_approve_idem, emits=["instruction.sent"])
def override(i: dict[str, Any], ctx: CallContext):
    return _approve("decision.override", i, ctx)


@guard("decision.decline")
def decline_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return ("conflict", f"{c['id']} is not awaiting approval.") if c["stage"] != "awaiting_approval" else None


def _decline_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 7, f"decline:{cyc(c)}")


@implement("decision.decline", idem=_decline_idem, emits=["decision.declined"])
def decline(i: dict[str, Any], ctx: CallContext):
    key = _key("decision.decline", i, ctx)
    c, by = _case(ctx, i["case_id"]), _by(ctx)
    c["reevalReason"] = f"Declined by {by}: {i['reason']}"
    c["submitted"] = None
    c["cycle"] = cyc(c) + 1  # a new decision cycle: new keys for submit, approve and decline
    push_event(
        ctx,
        {
            "dir": "in", "type": "decision.declined", "caseId": c["id"], "decisionId": _decision_id(c), "approval": None,
            "ver": None, "dest": "Circularity", "ack": "acknowledged",
            "key": "dcl-" + hash_id(f"{c['id']}{c['cycle']}")[:6].lower(), "note": i["reason"], "by": by, "ts": NOW,
        },
        key,
    )  # fmt: skip
    lifecycle.move(ctx.session, c, "reeval", c["reevalReason"], ctx.actor.id)
    return {"case_id": c["id"], "stage": "reeval"}


def draft_rationale(c: store.Case) -> str:
    """The demo's afDraftRationale: the rationale the agent drafts for the approver to edit or acknowledge."""
    r = c.get("recommendation")
    if not r:
        return ""
    el = sorted((x for x in c["routes"] if not x["excluded"]), key=lambda x: -x["net"])
    nx = el[1] if len(el) > 1 else None
    m = case_demand(c)
    out = f"{r['plan']} gives {money(r['net'])} predicted net"
    if nx:
        out += f", {money(r['net'] - nx['net'])} ahead of {nx['plan']}"
    out += ". "
    if r.get("demandStatus") == "confirmed":
        out += "Demand is confirmed" + (f" ({m['order']})" if m and m.get("order") else "") + "."
    else:
        out += "Demand is a forecast, so a non-realisation allowance is included."
    snap = c.get("snapshot")
    return out + (f" Evidence snapshot {snap['id']}." if snap else "")


@guard("decision.prepare")
def prepare_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    if c.get("blocked"):
        return "conflict", f"{c['id']}: {c['blocked']['reason']}"
    if not c.get("recommendation"):
        return "conflict", f"{c['id']} has no eligible route; every route failed a gate."
    return None


@implement("decision.prepare")
def prepare(i: dict[str, Any], ctx: CallContext):
    c, by = _case(ctx, i["case_id"]), _by(ctx)
    snap = c.get("snapshot")
    c["packet"] = {
        "at": NOW,
        "by": by,
        "prep": ctx.preparer,
        "rationale": draft_rationale(c),
        "snapshot": snap["id"] if snap else None,
    }
    store.save(ctx.session, c)
    r = c["recommendation"]
    return {"case_id": c["id"], "recommended": r["plan"], "net": r["net"]}


# ---------------------------------------------------------------- evidence
@guard("evidence.request")
def request_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    if not c.get("blocked"):
        return "conflict", f"{c['id']} has no missing evidence to request."
    if c.get("requested"):
        return "duplicate", f"{c['blocked']['action']} was already sent ({c['requested']['ref']})"
    return None


def _request_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 5, f"request:{cyc(c)}")


@implement("evidence.request", idem=_request_idem, emits=["evidence.requested"])
def evidence_request(i: dict[str, Any], ctx: CallContext):
    key = _key("evidence.request", i, ctx)
    c, by = _case(ctx, i["case_id"]), _by(ctx)
    c["reqN"] = (c.get("reqN") or 0) + 1
    ref = f"WO-{60000 + int(c['id'][3:]) * 3 + c['reqN']}"
    c["requested"] = {"ref": ref, "at": NOW, "by": by}
    b = c["blocked"]
    push_event(
        ctx,
        {
            "dir": "out", "type": "evidence.requested", "caseId": c["id"], "decisionId": None, "approval": None, "ver": 1,
            "dest": b["owner"], "ack": "sent · awaiting ack", "key": "idem-" + hash_id(f"{c['id']}req{c['reqN']}")[:6],
            "retries": 0, "note": b["action"], "sim": True,
        },
        key,
    )  # fmt: skip
    for e in c.get("evidence") or []:
        if e["state"] in ("missing", "partial"):
            e["note"] = (e["note"] + " · " if e.get("note") else "") + "requested " + ref
    store.save(ctx.session, c)
    return {"case_id": c["id"], "ref": ref, "what": b["action"], "to": b["owner"]}


@guard("evidence.recordResult")
def record_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return ("duplicate", f"{c['id']} is already assessed") if not c.get("blocked") and c.get("assessment") == "Ready" else None


@implement("evidence.recordResult", idem=lambda i, ctx: skey(_peek(ctx, i["case_id"]), 5, "result"), emits=["inspection.result"])
def record_result(i: dict[str, Any], ctx: CallContext):
    key = _key("evidence.recordResult", i, ctx)
    c = _case(ctx, i["case_id"])
    rnd = _seeded(key)
    hero = bool(c.get("hero"))
    # a hand-modelled case was inspected to grade B with 30 months' life; any other draws its grade and life
    c["grade"] = "B" if hero else _wpick(rnd, [("A", 22), ("B", 41), ("C", 25), ("D", 12)])
    c["condition"] = "Grade " + c["grade"]
    c["assessment"], c["readiness"], c["blocked"] = "Ready", "ready", None
    if c["grade"] == "D":
        c["engLife"] = "Below minimum"
    else:
        c["engLife"] = f"{30 if hero else math.floor(12 + rnd() * 37)} months"  # rint(12, 48)
    c["nextInspection"] = "Mar 2027"
    for e in c.get("evidence") or []:
        e["state"], e["note"], e["fresh"] = "ready", "", "just now"
    if hero:
        c["demand"] = {"internal": True, "confirmed": True, "site": "Site 4", "lease": None, "parts": True}
    _rebuild(c, rnd)
    c["requested"], c["predictions"] = None, None
    r = c["recommendation"]
    if r:
        c["snapshot"] = {"id": "EVS-" + hash_id(c["id"] + "new"), "takenAt": NOW, "items": len(c.get("evidence") or [])}
    push_event(
        ctx,
        {
            "dir": "in", "type": "inspection.result", "caseId": c["id"], "decisionId": None, "approval": None, "ver": None,
            "dest": "Inspection", "ack": "acknowledged", "key": "idem-" + hash_id(c["id"] + "res")[:6], "retries": 0,
            "note": "Grade " + c["grade"], "sim": True,
        },
        key,
    )  # fmt: skip
    lifecycle.move(
        ctx.session, c, "awaiting_approval" if r else "none", "Inspection result recorded: Grade " + c["grade"], ctx.actor.id
    )
    return {"case_id": c["id"], "grade": c["grade"], "recommendation": r["plan"] if r else None, "net": r["net"] if r else None}


@guard("case.reevaluate")
def reevaluate_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return ("conflict", f"{i['case_id']} is not waiting for re-evaluation.") if c["stage"] != "reeval" else None


def _reeval_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 6, f"reeval:{cyc(c)}")


@implement("case.reevaluate", idem=_reeval_idem, emits=["decision.reevaluated"])
def reevaluate(i: dict[str, Any], ctx: CallContext):
    key = _key("case.reevaluate", i, ctx)
    c, by = _case(ctx, i["case_id"]), _by(ctx)
    was = c["recommendation"]["plan"] if c.get("recommendation") else None
    # a hand-modelled case keeps its routes and is ranked again; any other is valued again from the formulas
    if c.get("hero"):
        _rerank(c)
    else:
        _rebuild(c, _seeded(key))
    r = c["recommendation"]
    c["reevalReason"] = None
    c["snapshot"] = {"id": "EVS-" + hash_id(f"{c['id']}re{cyc(c)}"), "takenAt": NOW, "items": len(c.get("evidence") or [])}
    push_event(
        ctx,
        {
            "dir": "in", "type": "decision.reevaluated", "caseId": c["id"], "decisionId": _decision_id(c), "approval": None,
            "ver": None, "dest": "Circularity", "ack": "acknowledged", "key": "rev-" + hash_id(f"{c['id']}{cyc(c)}")[:6].lower(),
            "note": f"{r['plan']} · {money(r['net'])}" if r else "No eligible route", "by": by, "ts": NOW,
        },
        key,
    )  # fmt: skip
    lifecycle.move(ctx.session, c, "awaiting_approval" if r else "none", "Re-evaluated", ctx.actor.id)
    return {"case_id": c["id"], "was": was, "now": r["plan"] if r else None, "net": r["net"] if r else None}


# ---------------------------------------------------------------- scenarios (saved what-ifs; the decision never changes)
@implement("scenario.save")
def scenario_save(i: dict[str, Any], ctx: CallContext):
    """The demo names a scenario `sc` + hashId of its journal position (`scenario.save#<seq>`). The server's journal
    seq is only known after the handler, so the name hashes the workspace's own count of saved scenarios instead."""
    s, by = ctx.session, _by(ctx)
    n = state.next_number(s, "scenarios", "SCN-", 0)
    sid = "sc" + hash_id(f"scenario.save#{n}|{i['case_id']}")[:6].lower()
    item = {
        "id": sid, "n": n, "case_id": i["case_id"], "name": i["name"], "top": i.get("top") or "", "scen": dict(i["scen"]),
        "w": dict(i.get("w") or WORKBENCH_WEIGHTS), "by": by, "prep": ctx.preparer,
    }  # fmt: skip
    state.add(s, "scenarios", f"SCN-{n}", item)
    return {"case_id": i["case_id"], "id": sid, "name": i["name"]}


@implement("scenario.delete")
def scenario_delete(i: dict[str, Any], ctx: CallContext):
    s = ctx.session
    _by(ctx)
    for x in saved_scenarios(s, i["case_id"]):
        if x["id"] == i["id"]:
            state.delete(s, "scenarios", f"SCN-{x['n']}")
    return {"case_id": i["case_id"], "id": i["id"]}  # deleting a scenario that is not there is not an error


def saved_scenarios(s, case_id: str) -> list[dict]:
    """The scenarios saved for a case, oldest first (the demo's S.ti.saved[case_id])."""
    return [x for x in state.items(s, "scenarios") if x["case_id"] == case_id]


# ---------------------------------------------------------------- notifications, comments, escalations
def _recipient_guard(i: dict[str, Any], ctx: CallContext):
    return ("not_found", "Unknown recipient.") if policy.account(i["to"], ctx.actor.ctx) is None else None


def _recipient(i: dict[str, Any], ctx: CallContext) -> policy.Account:
    """The recipient _recipient_guard found."""
    to = policy.account(i["to"], ctx.actor.ctx)
    if to is None:
        raise ActionError("not_found", "Unknown recipient.")
    return to


guard("notify.send")(_recipient_guard)
guard("escalation.send")(_recipient_guard)


def _notify(ctx: CallContext, n: dict) -> dict:
    """Add a notification (the demo's S.notes.push, numbered from S.ntSeq)."""
    s = ctx.session
    n = {"id": f"NTF-{state.next_number(s, 'notes', 'NTF-', NOTE_SEQ_START)}", **n}
    return state.add(s, "notes", n["id"], n)


@implement(
    "notify.send",
    idem=lambda i, ctx: "ntf:" + hash_id(f"{i['ex_id']}|{i['to']}|{i['msg']}"),  # noqa: ARG005 - idem keys take (input, ctx)
    emits=["notification.sent"],
)
def notify_send(i: dict[str, Any], ctx: CallContext):
    key, by, to = _key("notify.send", i, ctx), _by(ctx), _recipient(i, ctx)
    n = _notify(
        ctx,
        {
            "exId": i["ex_id"], "title": i["title"], "msg": i["msg"], "sev": i["sev"], "to": to.id, "toLabel": to.label,
            "from": by, "at": NOW, "status": "open", "ids": list(i.get("ids") or [])[:40], "prep": ctx.preparer,
        },
    )  # fmt: skip
    rb_log(ctx, "notification.sent", f"{n['id']} · {n['title']} → {to.label}", key)
    return {"id": n["id"], "to": to.label}


@guard("notify.acknowledge")
def ack_guard(i: dict[str, Any], ctx: CallContext):
    n = state.get(ctx.session, "notes", i["id"])
    if not n:
        return "not_found", f"No notification {i['id']}."
    if n["to"] != ctx.actor.id:
        return "out_of_scope", f"That notification is addressed to {n['toLabel']}."
    if n["status"] == "ack":
        return "duplicate", "Already acknowledged"
    return None


@implement("notify.acknowledge", idem=lambda i, ctx: "ntf-ack:" + i["id"], emits=["notification.acknowledged"])  # noqa: ARG005 - idem keys take (input, ctx)
def notify_acknowledge(i: dict[str, Any], ctx: CallContext):
    key, by = _key("notify.acknowledge", i, ctx), _by(ctx)
    n = state.need(ctx.session, "notes", i["id"], for_update=True)
    n.update(status="ack", ackBy=by, ackAt=NOW)
    state.put(ctx.session, "notes", n["id"], n)
    rb_log(ctx, "notification.acknowledged", f"{n['id']} · {n['title']} · in hand by {by}", key)
    return {"id": n["id"]}


@implement("comment.add")
def comment_add(i: dict[str, Any], ctx: CallContext):
    """Comments are data, never instructions: kept as posted (up to 500 characters) under the record's key."""
    s, by = ctx.session, _by(ctx)
    n = state.next_number(s, "comments", "CM-", 0)
    state.add(s, "comments", f"CM-{n}", {"key": i["key"], "by": by, "at": NOW, "text": i["text"][:500], "prep": ctx.preparer})
    return {"key": i["key"]}


def comments(s, key: str) -> list[dict]:
    """The comments on a record, oldest first (the demo's cmList)."""
    return [x for x in state.items(s, "comments") if x["key"] == key]


@implement(
    "escalation.send",
    idem=lambda i, ctx: f"esc:{i['case_id']}:{i['to']}:{hash_id(i['msg'])}",  # noqa: ARG005 - idem keys take (input, ctx)
)
def escalation_send(i: dict[str, Any], ctx: CallContext):
    key, by, to = _key("escalation.send", i, ctx), _by(ctx), _recipient(i, ctx)
    n = _notify(
        ctx,
        {
            "exId": "esc:" + i["case_id"], "title": "Escalation · " + i["case_id"], "msg": i["msg"], "sev": "Medium",
            "to": to.id, "toLabel": to.label, "from": by, "at": NOW, "status": "open", "ids": [i["case_id"]],
            "prep": ctx.preparer,
        },
    )  # fmt: skip
    rb_log(ctx, "escalation.sent", f"{n['id']} · {i['case_id']} → {to.label}", key)
    return {"id": n["id"], "to": to.label, "case_id": i["case_id"]}
