"""Execution actions (B13): adapter.acknowledge, instruction.resend, outcome.confirm.

Ports of the demo's handlers (index.html, `defAction('outcome.confirm', ...)` and the two after it). Once a decision
is approved (di.actions.decisions), each step of its plan is an instruction to one enterprise system; the system
acknowledges the active step and returns the document it created, which activates the next step. The first
acknowledgement moves the case to executing, the last to closed; Finance then confirms the outcome.

Only the enterprise-system adapter acknowledges (risk "system": the pipeline refuses people and agents); it acts as
`pipeline.SYSTEM`, the demo's AF_SYS.
"""

from di.actions.decisions import NOW, _by, _case, _key, _peek, cyc, push_event, skey
from di.actions.registry import guard, implement
from di.cases import lifecycle, store
from di.engine.jsmath import js_sum
from di.execution import EX_STEP, ack_note, ack_ref, ex_ev, line_actuals, ref_label, value_order
from di.reads.common import hash_id, money


def _active(c: store.Case) -> int:
    """The index of the active step, -1 when there is none."""
    x = c.get("exec")
    return next((i for i, s in enumerate(x["steps"]) if s["state"] == "active"), -1) if x else -1


# ---------------------------------------------------------------- outcome.confirm
@guard("outcome.confirm")
def confirm_guard(i, ctx):
    c = _peek(ctx, i["case_id"])
    if c.get("outcome"):
        return "duplicate", "The outcome is already confirmed"
    if c["stage"] != "closed":
        return "conflict", f"The outcome has not been reported yet; {c['id']} is still with the enterprise systems."
    return None


def _confirm_idem(i, ctx):
    c = _peek(ctx, i["case_id"])
    return skey(c, 9, cyc(c))


@implement("outcome.confirm", idem=_confirm_idem, emits=["outcome.confirmed"])
def outcome_confirm(i, ctx):
    """Finance confirms the reported outcome: an actual per cost line of the chosen route, linked to the decision so the
    models that predicted them learn from the difference."""
    key = _key("outcome.confirm", i, ctx)
    c = _case(ctx, i["case_id"])
    r = c.get("chosen") or c["recommendation"]
    lines = line_actuals(c, r)
    vo = value_order(c)
    net = js_sum(ln["act"] for ln in lines)
    c["outcome"] = {"net": net, "lines": lines, "order": vo["ref"] if vo else None, "by": _by(ctx), "at": NOW}
    x = c["exec"]
    on = f" on {vo['ref']}" if vo else ""
    learned = len([ln for ln in lines if ln["model"]])
    push_event(
        ctx,
        {
            "dir": "in", "type": "outcome.confirmed", "caseId": c["id"], "decisionId": x["decisionId"], "approval": x["ref"],
            "ver": x["instruction"], "dest": "ERP · finance", "ack": "acknowledged",
            "key": "idem-" + hash_id(c["id"] + "fin")[:6], "retries": 0, "ref": vo["ref"] if vo else None,
            "note": f"Actual {money(net)} against predicted {money(r['net'])}{on}; {learned} cost lines to the models",
        },
        key,
    )  # fmt: skip
    store.save(ctx.session, c)
    return {"case_id": c["id"], "actual": net, "predicted": r["net"], "variance": net - r["net"]}


# ---------------------------------------------------------------- adapter.acknowledge
@guard("adapter.acknowledge")
def ack_guard(i, ctx):
    c = _peek(ctx, i["case_id"])
    if not c.get("exec"):
        return "conflict", f"Nothing has been sent for {c['id']} yet."
    a = _active(c)
    if a < 0:
        return "conflict", f"Every step for {c['id']} is already acknowledged."
    # a system repeating an earlier step's acknowledgement (the demo's text names the step it asked about)
    if i.get("step") is not None and i["step"] != a:
        return "duplicate", f"Step {i['step'] + 1} is already acknowledged"
    return None


def _ack_idem(i, ctx):
    """<case>:8:<approval>:<step>; the last step's acknowledgement reports the outcome, so it is keyed to stage 9."""
    c = _peek(ctx, i["case_id"])
    x, a = c.get("exec"), _active(c)
    return skey(c, 9 if x and a >= len(x["steps"]) - 1 else 8, f"{x['ref'] if x else ''}:{a}")


# every event an acknowledgement can emit, in the demo's order (`new Set(Object.values(EX_STEP).map(d => d.ev))`)
ACK_EVENTS = list(dict.fromkeys(d["ev"] for d in EX_STEP.values()))


@implement("adapter.acknowledge", idem=_ack_idem, emits=ACK_EVENTS)
def adapter_acknowledge(i, ctx):
    key = _key("adapter.acknowledge", i, ctx)
    c = _case(ctx, i["case_id"])
    e = c["exec"]
    k = _active(c)
    s = e["steps"][k]
    s["state"] = "done"
    # the reference is the step's planned document number (ackRef's number is only for steps stored without a kind)
    num = 40000 + int(c["id"][3:]) * 7 + k * 13 + cyc(c) * 101
    s["ack"] = {"by": s["sys"].split(" · ")[0], "ref": ack_ref(c, s, num), "at": NOW, "sim": True}
    if k + 1 < len(e["steps"]):
        e["steps"][k + 1]["state"] = "active"
        e["steps"][k + 1]["activeAt"] = NOW
    t = ex_ev(s)
    note = ack_note(s, c)
    push_event(
        ctx,
        {
            "dir": "in", "type": t, "caseId": c["id"], "decisionId": e["decisionId"], "approval": e["ref"],
            "ver": e["instruction"], "dest": s["sys"], "ack": "acknowledged",
            "key": "idem-" + hash_id(c["id"] + t + e["ref"])[:6].lower(), "retries": 0, "ref": s["ack"]["ref"],
            "note": f"{ref_label(s)} returned by {s['ack']['by']}" + (f": {note}" if note else ""), "sim": True,
        },
        key,
    )  # fmt: skip
    why = f"{s['label']} acknowledged by {s['ack']['by']} ({s['ack']['ref']})"
    moved = False
    if k == 0 and c["stage"] != "executing":
        lifecycle.move(ctx.session, c, "executing", why, ctx.actor.id)
        moved = True
    if k == len(e["steps"]) - 1:
        lifecycle.move(ctx.session, c, "closed", why, ctx.actor.id)
        moved = True
    if not moved:
        store.save(ctx.session, c)
    return {
        "case_id": c["id"],
        "step": k,
        "label": s["label"],
        "by": s["ack"]["by"],
        "ref": s["ack"]["ref"],
        "ref_label": ref_label(s),
    }


# ---------------------------------------------------------------- instruction.resend
@guard("instruction.resend")
def resend_guard(i, ctx):
    c = _peek(ctx, i["case_id"])
    return None if c.get("exec") else ("conflict", "Nothing to resend: no instruction has been sent.")


def _resend_idem(i, ctx):
    c = _peek(ctx, i["case_id"])
    return skey(c, 8, f"resend:{(c.get('exec') or {}).get('ref')}")


@implement("instruction.resend", idem=_resend_idem, emits=["instruction.sent"])
def instruction_resend(i, ctx):
    """Send the approved instruction again under the same idempotency key: the target system ignores the duplicate, so
    nothing is reserved or ordered twice."""
    key = _key("instruction.resend", i, ctx)
    c = _case(ctx, i["case_id"])
    e = c["exec"]
    push_event(
        ctx,
        {
            "dir": "out", "type": "instruction.sent", "caseId": c["id"], "decisionId": e["decisionId"], "approval": e["ref"],
            "ver": e["instruction"], "dest": e["steps"][0]["sys"], "ack": "duplicate · deduplicated",
            "key": "idem-" + hash_id(c["id"] + e["ref"])[:6].lower(), "retries": 1,
            "note": "Repeated message ignored: same idempotency key, no second reservation or work order", "sim": True,
        },
        key,
    )  # fmt: skip
    return {"case_id": c["id"], "deduplicated": True}
