# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `outcome` (plan 9, P9-2.21; registry entry I-7; journey stage 9): what the executing systems finally reported, and
the actual costs and realised value Finance confirmed.

Owns: the step list, the stage's output `{actual_costs, realised_value, confirmed_by}` and its confidence, 1.0 once the
outcome is confirmed:
    a case that is not closed        `Done` skipped ("not closed"): the executing systems have not reported yet
    a closed case, no outcome yet    `Wait("outcome")`: Finance confirms it with `outcome.confirm`. The packs carry no switch
                                     for this, so every closed case waits for the person. The `outcome.confirm` that lands
                                     wakes the run (`runtime._confirmed`, as `resume_waiting` does for approvals)
    an outcome on the case           `Done`
`actual_costs` are the confirmed lines `[{item, actual}]` (the case's `outcome.lines`, one per cost line of the chosen route),
`realised_value` the confirmed net. An unconfirmed case has an empty output: nothing is invented.
Never does: confirm an outcome (`outcome.confirm` is in `FORBIDDEN_ACTIONS`, a person's), call an action, or read a clock. Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next, Wait
from di.services.agents.stage_context import StageId

ID: StageId = "outcome"
ACTIONS: tuple[str, ...] = ()
WAITING = "outcome"


def confirmed(case: Mapping[str, Any]) -> Mapping[str, Any] | None:
    out = case.get("outcome")
    return out if isinstance(out, Mapping) else None


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if confirmed(case) is not None:
        return Done("The outcome is confirmed.")
    if case.get("stage") != "closed":
        return Done("The case is not closed.", skipped=True)
    return Wait(WAITING)


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call, nothing to keep."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    return 1.0 if confirmed(case) is not None else None


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    out = confirmed(case)
    if out is None:
        return {}
    lines = [{"item": ln.get("label"), "actual": ln.get("act")} for ln in out.get("lines") or [] if isinstance(ln, Mapping)]
    return {"actual_costs": lines, "realised_value": out.get("net"), "confirmed_by": out.get("by")}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = confirmed(case)
    if out is None:
        return []
    return [{"fact": "Confirmed outcome", "source": str(out.get("order") or "Finance"), "at": out.get("at")}]
