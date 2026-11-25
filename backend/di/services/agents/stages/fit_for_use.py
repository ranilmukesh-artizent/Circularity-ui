# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `fit_for_use` (plan 9, P9-2.1; registry entry I-7): the parts worth harvesting.

Owns: the stage's output (the parts whose remaining life is at or above the pack's `rulMin`, 50 when the pack names none;
the runtime puts the pack's value in the run state as `rul_min`) and its confidence, 1.0.
Never does: call an action or value a route (the harvest route's value is the valuation stage's). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next
from di.services.agents.stage_context import StageId

ID: StageId = "fit_for_use"
ACTIONS: tuple[str, ...] = ()
RUL_MIN = 50


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    return Done("The parts are checked.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call, nothing to keep."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    return 1.0


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    floor = float(st.get("rul_min", RUL_MIN))
    life = [v for v in case.get("partRul") or [] if isinstance(v, int | float) and not isinstance(v, bool)]
    return {"rul_min": floor, "parts": [{"part": j, "rul": v} for j, v in enumerate(life) if v >= floor]}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []
