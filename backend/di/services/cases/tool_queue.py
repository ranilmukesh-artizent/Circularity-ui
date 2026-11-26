"""The live queue plan of an org's open tool returns (plan 9, P9-3.13, story TF-08; registry entry I-5).

    open_queue(s, org_unit_id) -> [valuer case]     every open tool-fleet return of the org, with its live named demand
    plan_of(s, org_unit_id) -> Plan                 the queue planned (a read, writes nothing)
    replan(s, org_unit_id) -> Plan                  the same, and every open case valued again with it

`open_queue` gives the valuer inputs of the org's tool-fleet cases that are not closed: the open ones (status new) and the
ones an approved or executing decision holds (status sent, which keep their order and their repair center slot), each
with its `dem` extended by the org's named demand of its class (the queue's tagged orders and the live renewals, sales
orders, bids, pool requests and repair orders of its sources). A case never competes with another org's returns.
`plan_of` runs the pack's planner (`engine.queue.planner_for`, the heuristic by default; the pack setting
`valuer.params["planner"]`) with `slots` the pack's repair center slots; the planner takes off the refurbishments in
progress (sent cases on the refurb path). `replan` also refreshes the stored routes and recommendation of every open case
whose result changed, with a journal row by `system` ("Re-planned: <old> -> <new>", di.services.cases.replan.on_opened).
The decision of a single case (`intake.tool_plan` over `intake.tool_queue`) is the same plan, so its result equals the plan's.

Owns: reading the queue and planning it. Never does: approve a case or move it to another stage, or call a language model.
"""

from typing import Any

from sqlalchemy.orm import Session

from di.services.cases import intake
from di.services.cases import replan as replanner
from di.services.modeler.valuers import tool_inputs
from di.services.modeler.valuers.tool_fleet import Plan

__all__ = ["Plan", "open_queue", "plan_of", "replan"]


def _queue(s: Session, org_unit_id: str) -> tuple[intake.ToolQueue, list[dict[str, Any]]]:
    docs = intake.open_tool_cases(s, org_unit_id)
    return intake.queue_of(s, org_unit_id, [intake.tool_input(d) for d in docs]), docs


def open_queue(s: Session, org_unit_id: str) -> list[dict[str, Any]]:
    """The valuer cases of the org's open tool returns, with their live `dem` (module docstring)."""
    q, _ = _queue(s, org_unit_id)
    return [c | {"dem": tool_inputs.merge_demand(c["dem"], q.demand[c["id"]])} for c in q.cases]


def plan_of(s: Session, org_unit_id: str) -> Plan:
    """The org's open queue planned with the pack's planner; reads only."""
    q, docs = _queue(s, org_unit_id)
    rules = intake.case_rules(s, docs[0]) if docs else []
    return intake.tool_plan(q, rules)


def replan(s: Session, org_unit_id: str) -> Plan:
    """`plan_of`, and every open case of the org valued again with the queue as it is (journaled when it moved)."""
    plan = plan_of(s, org_unit_id)
    replanner.on_opened(s, org_unit_id)
    return plan
