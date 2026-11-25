"""Service desk actions (plan 9: P9-4.5 SD-08, P9-4.7 SD-06, P9-4.10 SD-09; registry entry I-14 measured, not changed).

    serviceDesk.computeAccuracy   act  {}   replay the estimate on the held-out repairs of every org unit and store today's
                                            figures per tool class (`di.services.service_desk.accuracy`)

    serviceDesk.postFault         act  {case_id, line, fault_code, notes?}   the fault found on a draft line: the line's estimate
                                            and the options of the case run again (`estimate.estimate_line`, then the one
                                            decider, `intake.revalue` -> `decide_case`, R19); its technician-check item closes

    serviceDesk.whatIf            read  {case_id, line?, credit_pct?, take_up?, repair_cost_pct?, wait_days?}   the options run
                                            again on a copy with the levers moved, and the expected margin over credit 0 to 40%
                                            (service_desk.what_if); stores, journals and sends nothing

computeAccuracy only measures: no model, table or bar changes, so it needs no maker-checker and an agent may run it (not in
FORBIDDEN_ACTIONS). Permission `manageMarketTables`. The worker runs the same job once a simulated day (`serviceDesk.accuracy`).
Changing the bar is a guardrail change (the GR-S1 parameters, I-4), not an action here.

postFault needs `assess` (the Engineer's), keeps the ticket's text, and an agent's call is held for a person (HELD_FOR_PERSON,
I-10). It approves and releases nothing, so it is not in FORBIDDEN_ACTIONS. No model step (R16): the fault is a code picked from
the depot's four and nothing reads the free text, so there is no `AgentLoop` here. whatIf is a read and a computation: no model
step either (R16), so no model tests; an agent may call it, and it approves and releases nothing, so it joins no forbidden list.
"""

from datetime import date
from typing import Any

from di.core import clock
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import process, store
from di.services.service_desk import accuracy, estimate, what_if
from di.services.service_desk import inputs as sd_inputs

ACTIONS.setdefault(
    "serviceDesk.computeAccuracy",
    ActionDef(
        id="serviceDesk.computeAccuracy", title="Compute repair estimate accuracy", verb="compute the repair estimate accuracy",
        desc="Replay the repair estimate on the repairs closed in the last weeks and store its accuracy per tool class. "
             "Changes no model or price.",
        risk="act", perm="manageMarketTables", scope="none", input={},
    ),
)  # fmt: skip


@implement("serviceDesk.computeAccuracy")
def compute_accuracy(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - takes no input
    rows = accuracy.compute(ctx.session, clock.now().date())
    below = sum(1 for r in rows if not r.instant)
    return {
        "families": len(rows), "below": below, "as_of": clock.now().date().isoformat(),
        "log": f"Repair estimate accuracy computed: {len(rows)} families, {below} below the bar",
    }  # fmt: skip


ACTIONS.setdefault(
    "serviceDesk.postFault",
    ActionDef(
        id="serviceDesk.postFault", title="Post the fault", verb="post a fault",
        desc="Post the fault found on a draft line of a service ticket. The line is priced again and its options run again.",
        risk="act", perm="assess", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "line": {"req": True, "t": "number"},
            "fault_code": {"req": True, "t": "string"},
            "notes": {"t": "string"},
        },
    ),
)  # fmt: skip


def _line(c: Any, n: Any) -> dict[str, Any] | None:
    base = (c or {}).get("serviceDesk")
    return next((x for x in base["lines"] if x["n"] == n), None) if isinstance(base, dict) else None


@guard("serviceDesk.postFault")
def post_fault_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i["fault_code"] not in estimate.FAULTS:
        return "validation_error", f"Unknown fault code {i['fault_code']}. Use one of {', '.join(estimate.FAULTS)}."
    c = store.get(ctx.session, i["case_id"])
    if c is None or not isinstance(c.get("serviceDesk"), dict):
        return "not_found", f"{i['case_id']} is not a service ticket case."
    ln = _line(c, i["line"])
    if ln is None:
        return "validation_error", f"No line {i['line']} on {i['case_id']}."
    if ln.get("fault_code") == i["fault_code"]:
        return "conflict", "This fault is already posted."
    return None


@implement("serviceDesk.postFault", idem=lambda i, ctx: f"{i['case_id']}:{int(i['line'])}:{i['fault_code']}")  # noqa: ARG005 - the key is the input
def post_fault(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    from di.services.cases import intake  # intake imports the actions layer

    s = ctx.session
    c = store.get(s, i["case_id"], for_update=True)
    ln = _line(c, i["line"])
    if c is None or ln is None:
        raise ActionError("not_found", f"No line {i['line']} on {i['case_id']}.")
    item = estimate.check_item(s, c["id"], ln)
    if item is not None:
        process.close_item(s, item, f"Fault posted: {i['fault_code']}", ctx.actor.id)
    ln["fault_code"] = i["fault_code"]
    if note := (i.get("notes") or "").strip():
        ln["fault_notes"] = note
    as_of = date.fromisoformat((ln.get("estimate") or {}).get("as_of") or clock.now().date().isoformat())
    ln["estimate"] = estimate.as_dict(estimate.estimate_line(s, c, ln, as_of), as_of, None)  # the check is closed: no item
    intake.revalue(s, c)  # the one decider, as `case.reevaluate` runs it
    store.save(s, c)
    return {
        "case_id": c["id"], "line": ln["n"], "fault_code": i["fault_code"],
        "log": f"Fault posted for {ln['serial']}: {i['fault_code']}; options re-run",
    }  # fmt: skip


ACTIONS.setdefault(
    "serviceDesk.whatIf",
    ActionDef(
        id="serviceDesk.whatIf", title="Test a credit", verb="test a credit",
        desc="Run the options of a service ticket again with another credit, take-up, repair cost or wait, and see the "
             "expected margin over credits from 0 to 40%. Changes nothing and sends nothing.",
        risk="read", perm=None, scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "line": {"t": "number"},
            "credit_pct": {"t": "number"},
            "take_up": {"t": "number"},
            "repair_cost_pct": {"t": "number"},
            "wait_days": {"t": "number"},
        },
    ),
)  # fmt: skip

_LEVERS = ("credit_pct", "take_up", "repair_cost_pct", "wait_days")


@guard("serviceDesk.whatIf")
def what_if_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := what_if.out_of_range(i):
        return "validation_error", bad
    c = store.get(ctx.session, i["case_id"])
    if c is None or not isinstance(c.get("serviceDesk"), dict):
        return "not_found", f"{i['case_id']} is not a service ticket case."
    if i.get("line") is not None and _line(c, i["line"]) is None:
        return "validation_error", f"No line {i['line']} on {i['case_id']}."
    return None


@implement("serviceDesk.whatIf")
def what_if_read(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """A read: no case save, no journal row (the pipeline stops after a read), no instruction. No model step (R16)."""
    s = ctx.session
    c = store.get(s, i["case_id"])
    if c is None:
        raise ActionError("not_found", f"No case {i['case_id']}.")
    sd = c.get("serviceDesk") or {}
    given = [date.fromisoformat(ln["estimate"]["as_of"]) for ln in sd.get("lines", []) if ln.get("estimate")]
    inputs = sd_inputs.gather(s, c, max(given, default=clock.now().date()))
    if inputs is None:
        raise ActionError("not_found", f"No approved tables for the market of {i['case_id']}.")
    only = int(i["line"]) if i.get("line") is not None else None
    out = what_if.check(inputs, {k: i[k] for k in _LEVERS if i.get(k) is not None}, only)
    return out | {"case_id": i["case_id"], "log": "Credit tested: nothing was changed or sent"}
