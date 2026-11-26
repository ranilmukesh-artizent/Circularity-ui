"""Execution actions (B13): adapter.acknowledge, instruction.resend, outcome.confirm.

Ports of the demo's handlers (index.html, `defAction('outcome.confirm', ...)` and the two after it). Once a decision
is approved (di.services.actions.decisions), each step of its plan is an instruction to one enterprise system; the system
acknowledges the active step and returns the document it created, which activates the next step. The first
acknowledgement moves the case to executing, the last to closed; Finance then confirms the outcome.

Only the enterprise-system adapter acknowledges (risk "system": the pipeline refuses people and agents); it acts as
`pipeline.SYSTEM`, the demo's AF_SYS.

**B13b, the real loop.** adapter.acknowledge takes two optional inputs beyond the demo's: `ref`, the system's own
document reference read from its completion event (di/services/instructions/events.py), and `simulated`, set by the simulated
adapter for steps whose system has no write in the mocks. Without `ref` the reference is the demo's formula and the
acknowledgement is marked simulated, exactly as in the demo (the B13a parity tests). When sending instructions is on
(di/services/instructions), an acknowledgement also marks the step's instruction acknowledged and queues the next step, and
instruction.resend sends the latest instruction again under its key.
"""

from typing import Any

from di.repositories.common import hash_id, money
from di.services import instructions
from di.services.actions.decisions import NOW, _by, _case, _key, _peek, cyc, push_event, skey
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, guard, implement
from di.services.cases import lifecycle, store
from di.services.engine.jsmath import js_sum
from di.services.execution import (
    EX_STEP,
    ack_note,
    ack_ref,
    asset,
    ex_ev,
    line_actuals,
    ref_label,
    residual,
    value_order,
    variance,
)


def _active(c: store.Case) -> int:
    """The index of the active step, -1 when there is none."""
    x = c.get("exec")
    return next((i for i, s in enumerate(x["steps"]) if s["state"] == "active"), -1) if x else -1


# ---------------------------------------------------------------- outcome.confirm
# Compliance text: pending review by Kinective's Legal team.
RECYCLING_TEXT = "Recycling needs the recycler's certificate before the case closes (GR-06)"


def recycling_refusal(c: store.Case) -> str | None:
    """P9-3.14 (GR-06): a tool-fleet case closed on `exit` needs a custody step the recycler acknowledged with its own
    certificate reference (not a simulated acknowledgement); the refusal text, or None when nothing is missing."""
    if c.get("template") != "tool_fleet" or ((c.get("chosen") or c.get("recommendation") or {}).get("id")) != "exit":
        return None
    for s in (c.get("exec") or {}).get("steps") or []:
        a = s.get("ack")
        if s.get("k") == "custody" and a and a.get("ref") and not a.get("sim"):
            return None
    return RECYCLING_TEXT


@guard("outcome.confirm")
def confirm_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    if c.get("outcome"):
        return "duplicate", "The outcome is already confirmed"
    if c["stage"] != "closed":
        return "conflict", f"The outcome has not been reported yet; {c['id']} is still with the enterprise systems."
    if refusal := recycling_refusal(c):
        return "conflict", refusal
    return None


def _confirm_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 9, cyc(c))


@implement("outcome.confirm", idem=_confirm_idem, emits=["outcome.confirmed"])
def outcome_confirm(i: dict[str, Any], ctx: CallContext):
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
    if c.get("template") == "tool_fleet":  # P9-3.17: a net off the prediction by more than the pack's tolerance goes to Finance
        variance.check(ctx.session, c, net, r["net"])
    return {"case_id": c["id"], "actual": net, "predicted": r["net"], "variance": net - r["net"]}


# ---------------------------------------------------------------- adapter.acknowledge
@guard("adapter.acknowledge")
def ack_guard(i: dict[str, Any], ctx: CallContext):
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


def _ack_idem(i: dict[str, Any], ctx: CallContext):
    """<case>:8:<approval>:<step>; the last step's acknowledgement reports the outcome, so it is keyed to stage 9."""
    c = _peek(ctx, i["case_id"])
    x, a = c.get("exec"), _active(c)
    return skey(c, 9 if x and a >= len(x["steps"]) - 1 else 8, f"{x['ref'] if x else ''}:{a}")


# every event an acknowledgement can emit, in the demo's order (`new Set(Object.values(EX_STEP).map(d => d.ev))`)
ACK_EVENTS = list(dict.fromkeys(d["ev"] for d in EX_STEP.values()))
# B13b inputs (the demo's catalog has case_id and step): the system's own reference, and the simulated adapter's mark
ACTIONS["adapter.acknowledge"].input |= {"ref": {"req": False, "t": "string"}, "simulated": {"req": False, "t": "boolean"}}
SIMULATED_NOTE = " (simulated acknowledgement: no write for this step in the mocked systems)"


@implement("adapter.acknowledge", idem=_ack_idem, emits=ACK_EVENTS)
def adapter_acknowledge(i: dict[str, Any], ctx: CallContext):
    key = _key("adapter.acknowledge", i, ctx)
    c = _case(ctx, i["case_id"])
    e = c["exec"]
    k = _active(c)
    s = e["steps"][k]
    s["state"] = "done"
    # the reference is the system's own (from its event), else the step's planned document number (ackRef's number is
    # only for steps stored without a kind); only a reference from the system makes the acknowledgement real
    num = 40000 + int(c["id"][3:]) * 7 + k * 13 + cyc(c) * 101
    real = i.get("ref") or None
    s["ack"] = {"by": s["sys"].split(" · ")[0], "ref": real or ack_ref(c, s, num), "at": NOW, "sim": not real}
    if k + 1 < len(e["steps"]):
        e["steps"][k + 1]["state"] = "active"
        e["steps"][k + 1]["activeAt"] = NOW
    if s.get("k") in asset.KINDS:  # P9-13.1: the ERP's gain or loss on the asset, stored as it answered
        asset.record(ctx.session, c, k)
        residual.record(c, (c.get("finance") or {}).get("asset"))  # P9-13.2: the lease residual against the proceeds
    t = ex_ev(s)
    note = ack_note(s, c)
    push_event(
        ctx,
        {
            "dir": "in", "type": t, "caseId": c["id"], "decisionId": e["decisionId"], "approval": e["ref"],
            "ver": e["instruction"], "dest": s["sys"], "ack": "acknowledged",
            "key": "idem-" + hash_id(c["id"] + t + e["ref"])[:6].lower(), "retries": 0, "ref": s["ack"]["ref"],
            "note": f"{ref_label(s)} returned by {s['ack']['by']}" + (f": {note}" if note else "")
            + (SIMULATED_NOTE if i.get("simulated") else ""),
            "sim": not real,
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
    instructions.on_acknowledged(ctx.session, c, k, s["ack"]["ref"])  # the next step goes out (when sending is on)
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
def resend_guard(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return None if c.get("exec") else ("conflict", "Nothing to resend: no instruction has been sent.")


def _resend_idem(i: dict[str, Any], ctx: CallContext):
    c = _peek(ctx, i["case_id"])
    return skey(c, 8, f"resend:{(c.get('exec') or {}).get('ref')}")


@implement("instruction.resend", idem=_resend_idem, emits=["instruction.sent"])
def instruction_resend(i: dict[str, Any], ctx: CallContext):
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
    instructions.resend(ctx.session, c)  # the real resend, under the same key (when sending is on)
    return {"case_id": c["id"], "deduplicated": True}
