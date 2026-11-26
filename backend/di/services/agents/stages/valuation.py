# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `valuation` (plan 9, P9-2.1; registry entry I-7): the best and the second route with their nets.

Owns: the step list (`case.reevaluate` when the case waits for re-evaluation, else the read `case.routes`; the legacy
`case_autopilot` alias skips that read so its calls stay as they were), the stage's output (the two best eligible routes
of the case, as the engine valued them) and its confidence:
- when both routes carry `p10` and `p90`: 1 minus the overlap of the two best intervals over the width of the best
  one, clipped to [0, 1];
- else 0.5 plus the lead of the best net over the second, as a share of the best net (at most 0.5 more);
- 1.0 with a single eligible route, null with none.
Never does: value a route itself (`decide_case`, I-6, did; R19) or change a case. Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip
from di.services.agents.stage_context import StageId

ID: StageId = "valuation"
ACTIONS = ("case.reevaluate", "case.routes")


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    cid = {"case_id": case["id"]}
    if n == 0:
        if case.get("stage") == "reeval":
            return Call("case.reevaluate", cid)
        return Skip("legacy autopilot: no route read") if st.get("legacy") else Call("case.routes", cid)
    return Done("The routes are valued.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call keeps anything: the case document holds the valued routes."""


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _top_two(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    routes = [
        r for r in case.get("routes") or [] if isinstance(r, Mapping) and not r.get("excluded") and _num(r.get("net")) is not None
    ]
    return sorted(routes, key=lambda r: -float(r["net"]))[:2]


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    dc = case.get("decisionConfidence")  # a tool return: the confidence of its life class (P9-3.15), not the routes' overlap
    if isinstance(dc, float):
        return dc
    top = _top_two(case)
    if not top:
        return None
    if len(top) == 1:
        return 1.0
    a, b = top
    band = [_num(x.get(k)) for x in (a, b) for k in ("p10", "p90")]
    if all(v is not None for v in band):
        a10, a90, b10, b90 = (float(v) for v in band if v is not None)
        width = a90 - a10
        overlap = max(0.0, min(a90, b90) - max(a10, b10))
        share = (1.0 if overlap > 0 else 0.0) if width <= 0 else overlap / width
        return min(1.0, max(0.0, 1.0 - share))
    lead = float(a["net"]) - float(b["net"])
    return 0.5 + min(0.5, lead / max(abs(float(a["net"])), 1.0))


def _route(r: Mapping[str, Any]) -> dict[str, Any]:
    return {"route": r.get("id"), "plan": r.get("plan"), "net": r.get("net")}


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    top = _top_two(case)
    return {"best": _route(top[0]) if top else None, "second": _route(top[1]) if len(top) > 1 else None}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []
