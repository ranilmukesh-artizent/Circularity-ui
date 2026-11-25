# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `disposition` (plan 9, P9-2.1; registry entry I-7): submit the decision and wait for a person to approve it.

Owns: the step list (when the pack names a queue planner, first a wait for the queue plan, `Wait("queue")`, that the job
`queue.plan` ends (P9-2.8, di.services.agents.queue_job; the runtime enqueues it); then `decision.submit` when the case
awaits approval and is not submitted yet, then a wait for the approval; `runtime.resume_waiting` wakes the run when a
person approves), the stage's output and its confidence, the valuation stage's. A case that is neither approved nor
awaiting approval ends the run with a note, as the autopilot did.
Never does: approve, override or decline (AGENTS.md rule 10; `decision.approve` is not in ACTIONS). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Halt, Next, Skip, Wait
from di.services.agents.stage_context import StageId
from di.services.modeler.pack import Pack

ID: StageId = "disposition"
ACTIONS = ("decision.submit",)


def planner_name(pack: Pack) -> str | None:
    """The queue planner the pack names (`valuer.params["planner"]`; a tool-fleet pack uses the heuristic one), else None:
    then this stage decides alone and never waits for a queue."""
    named = pack.valuer.params.get("planner")
    return str(named) if named else ("heuristic" if pack.valuer.kind == "tool_fleet" else None)


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if n == 0:
        if case.get("approval"):
            return Skip("already approved")
        if case.get("stage") != "awaiting_approval":
            return Halt(f"{case['id']} is not ready for approval")
        if st.get("queue_planner") and not case.get("queuePlan"):
            return Wait("queue")
        return Skip("already submitted") if case.get("submitted") else Call("decision.submit", {"case_id": case["id"]})
    if n == 1:
        return Skip("approved") if case.get("approval") else Wait("approval")
    return Done("The decision is approved.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No later step needs a submit's output: the case document says whether it was submitted."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    v = (st.get("confidence") or {}).get("valuation")
    return float(v) if v is not None else None


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "stage": case.get("stage"), "submitted": bool(case.get("submitted")), "approved": bool(case.get("approval")),
    }  # fmt: skip
    if isinstance(case.get("queuePlan"), Mapping):  # the planned route and why (P9-2.8)
        out["queue_plan"] = dict(case["queuePlan"])
    return out


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []
