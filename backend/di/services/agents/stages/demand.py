# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `demand` (plan 9, P9-2.1; registry entry I-7): the named demand the case already carries.

Owns: the stage's output (the case's `dem` document) and its confidence: 1.0 when every named order of it is dated (an
`at`, `due`, `date` or `needBy` field), else null (unknown).
Never does: call an action or look for new demand (the queue planner, I-5, does that when it values the routes). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next
from di.services.agents.stage_context import StageId

ID: StageId = "demand"
ACTIONS: tuple[str, ...] = ()
DATE_KEYS = ("at", "due", "date", "needBy")


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    return Done("The demand is read.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call, nothing to keep."""


def _orders(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    dem = case.get("dem")
    if not isinstance(dem, Mapping):
        return []
    return [d for v in dem.values() if isinstance(v, list) for d in v if isinstance(d, Mapping)]


def _date(d: Mapping[str, Any]) -> str | None:
    return next((str(d[k]) for k in DATE_KEYS if d.get(k)), None)


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    orders = _orders(case)
    return 1.0 if orders and all(_date(d) for d in orders) else None


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    dem = case.get("dem")
    return {"demand": dict(dem) if isinstance(dem, Mapping) else None, "orders": len(_orders(case))}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"fact": str(d.get("id") or "order"), "source": str(d.get("who") or ""), "at": _date(d)} for d in _orders(case)]
