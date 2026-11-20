"""The seed: the demo's synthetic world, loaded from the B1 golden files (docs/backend-steps.md, B2).

from sim.seed import seed
s = seed()
s.cases["RT-1048"].facts.routes[0].net   # 9600.0
"""

from dataclasses import dataclass
from functools import cache
from typing import Any

from sim.seed import golden
from sim.seed.model import (
    Case,
    CaseFacts,
    ClosedDecision,
    DemoResults,
    RouteFacts,
    RouteResult,
    WorkflowState,
    World,
)

_FACT_FIELDS = set(CaseFacts.model_fields) - {"routes", "facts"}
_ROUTE_FACT_FIELDS = set(RouteFacts.model_fields)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)


def _pick(raw: dict, fields: set[str]) -> dict:
    """Take the fields of a pydantic model from a camelCase golden record."""
    return {f: raw[_camel(f)] for f in fields if _camel(f) in raw}


def _case(raw: dict[str, Any]) -> Case:
    routes = raw["routes"]
    rec = raw.get("recommendation")
    facts = CaseFacts(
        **_pick(raw, _FACT_FIELDS),
        facts=raw.get("facts") or [],
        routes=[RouteFacts(**_pick(r, _ROUTE_FACT_FIELDS - {"net"})) for r in routes],
    )
    results = DemoResults(
        routes=[RouteResult(**_pick(r, set(RouteResult.model_fields))) for r in routes],
        recommendation=next(i for i, r in enumerate(routes) if r == rec) if rec else None,
        model=raw["model"],
        predictions=raw.get("predictions") or [],
        snapshot=raw.get("snapshot") or {},
        pool=raw.get("pool"),
        pool_result=raw.get("poolResult"),
    )
    state = WorkflowState(**_pick(raw, set(WorkflowState.model_fields)))
    return Case(facts=facts, results=results, state=state)


@dataclass(frozen=True)
class Seed:
    world: World
    cases: dict[str, Case]  # by case id, in the demo's order
    decisions: list[ClosedDecision]
    sources: list[dict[str, Any]]  # the demo's SOURCES (shape used by B3-B5 and B9)
    source_types: dict[str, dict[str, Any]]


@cache
def seed() -> Seed:
    world = World.model_validate(golden.load("world"))
    cases = {c["id"]: _case(c) for c in golden.load("cases")}
    decisions = [ClosedDecision.model_validate(d) for d in golden.load("decisions")]
    src = golden.load("sources")
    return Seed(world=world, cases=cases, decisions=decisions, sources=src["sources"], source_types=src["types"])
