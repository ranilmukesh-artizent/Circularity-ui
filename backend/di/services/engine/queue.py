"""The queue planner port (plan 9, P9-1.4; registry entry I-5).

    QueuePlanner.plan(cases, demand, capacity, *, rules=(), params=None) -> Plan
    HeuristicPlanner       the tool-fleet valuer's `plan_queue`: every open return of the queue, one return per named
                           order, refurbishment within the slots. The default; its output is `plan_queue`'s, unchanged.
    planner_for(pack)      the planner a pack names in `valuer.params["planner"]` (default "heuristic")

Owns: the port and its default. `demand` maps a case id to the named orders (the valuer's `dem` shape) to add to that
case; the planner merges them into copies of the cases, so a caller's cases are never changed. Never does: read a
database or the clock, or write a decision (di.services.cases.intake and replan call it and record the result).
`MilpPlanner` (SciPy `milp`) is not built here; a pack that names another planner is refused.
"""

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from di.services.modeler.pack import Pack
from di.services.modeler.valuers import tool_fleet
from di.services.modeler.valuers.tool_fleet import Case, Params, Plan, Rule

Dem = dict[str, Any]  # the valuer's `dem`: lease, so, bid (lists), proj (one or None), wo (parts -> lists), rcq


@dataclass(frozen=True)
class Capacity:
    """What the plan may use: the repair center's refurbishment `slots` (and units per depot, for planners that use it)."""

    slots: int
    depots: Mapping[str, int] = field(default_factory=dict)


class QueuePlanner(Protocol):
    def plan(
        self,
        cases: Sequence[Case],
        demand: Mapping[str, Dem],
        capacity: Capacity,
        *,
        rules: Sequence[Rule] = (),
        params: Params | None = None,
    ) -> Plan: ...


def _add(have: list[dict[str, Any]], extra: Sequence[dict[str, Any]]) -> None:
    """Append the orders of `extra` that `have` does not hold yet (by item id)."""
    seen = {d["id"] for d in have}
    for d in extra:
        if d["id"] not in seen:
            seen.add(d["id"])
            have.append(copy.deepcopy(d))


def _merged(case: Case, extra: Dem) -> Case:
    """A copy of the case whose `dem` also holds the named orders of `extra`, one per item id."""
    c = copy.deepcopy(case)
    dm = c["dem"]
    for kind in ("lease", "so", "bid"):
        _add(dm[kind], extra.get(kind) or [])
    if extra.get("proj") and not dm.get("proj"):
        dm["proj"] = copy.deepcopy(extra["proj"])
    for part, orders in (extra.get("wo") or {}).items():
        _add(dm["wo"].setdefault(part, []), orders)
    return c


class HeuristicPlanner:
    """The default planner: the prototype's greedy regret plan (tool_fleet.plan_queue) over the queue."""

    def plan(
        self,
        cases: Sequence[Case],
        demand: Mapping[str, Dem],
        capacity: Capacity,
        *,
        rules: Sequence[Rule] = (),
        params: Params | None = None,
    ) -> Plan:
        queue = [_merged(c, demand[c["id"]]) if demand.get(c["id"]) else c for c in cases]
        return tool_fleet.plan_queue((params or tool_fleet.BASEP) | {"slots": capacity.slots}, rules, queue=queue)


def planner_for(pack: Pack) -> QueuePlanner:
    """The planner the pack names (`valuer.params["planner"]`, default "heuristic"); ValueError for any other."""
    name = pack.valuer.params.get("planner", "heuristic")
    if name == "heuristic":
        return HeuristicPlanner()
    raise ValueError(f"No queue planner {name}")
