"""The queue plan of a unit pack: spares before new, and every named demand filled once (plan 9, P9-10.10, stories TN-12 and
TN-13; the rule R20 step 3, `Decision.plan`). `decide_case` calls it for the `telecom_network` pack after the gates and the
valuer; the planner itself is `di.services.engine.queue.fill_orders` (I-5), which names no industry.

    value_unit(facts, pack, as_of) -> [PathValue]     the valuer's five routes, with the two planning limits below
    plan(case, pack, as_of, members) -> [PathValue]   the case's values after the queue: a route that lost its order is not
                                                      offered and says why ("Site demand SD-112 filled by SN-TN-0001")

Orders. A site demand is one unit (`demand.id`, open, for the unit's model when the demand names one: `demand.model`). A
spares gap is the units a region lacks for a model (`spares.gap`, target - stock; no fact: no limit). Each unit bids its
redeploy net on the site demand it sees and its spare net on the gap of the region below target; the best gain places first,
ties by serial, so every case of the queue reads one plan. A unit takes one order. A case an approved decision holds keeps
its order and is placed first. A unit a gate blocks from a route does not bid with it.

Spares before new (TN-12): a spare is offered for the region below its spares target (`spares.region_below_target`), and for
no other; resale stays with the valuer (not offered while any region's six-month forecast needs the model). Site swap (TN-13):
the valuer's redeploy lists `firmware_upgrade` before `site_transfer` for a unit below the demand's firmware minimum.

Never does: read the clock (the valuer and gates are given `as_of`), write anything, send a requisition or any order to an
executing system (reducing a purchase requisition is a person's action, held for them), or call a model: every number and
reason is computed (R16).
"""

import copy
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from di.services.cases import gate_hold
from di.services.engine.queue import Bid, fill_orders
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import VALUERS
from di.services.modeler.valuers.telecom_network import fact
from di.services.modeler.valuers.tool_fleet import PathValue

NO_TARGET = "No region is below its spares target"
HELD = ("approved", "executing")  # a case a decision has been taken on keeps its order


def facts_of(c: Mapping[str, Any]) -> dict[str, Any]:
    """The facts a case is valued on: the snapshot over the case's own fields, a facts mapping as it is."""
    return {**{k: v for k, v in c.items() if k != "valuer"}, **(c.get("valuer") or {})}


def key_of(c: Mapping[str, Any], facts: Mapping[str, Any]) -> str:
    """The unit's name in a reason: its serial, else the case id."""
    return str(c.get("serial") or fact(facts, "asset.serial") or facts.get("serial") or c.get("id"))


def _spares_order(facts: Mapping[str, Any]) -> str | None:
    region = fact(facts, "spares.region_below_target")
    return f"spares:{region}:{fact(facts, 'asset.model')}" if region else None


def _site_order(facts: Mapping[str, Any]) -> str | None:
    return str(fact(facts, "demand.id")) if fact(facts, "demand.open_site_demand") is True and fact(facts, "demand.id") else None


def _said(order: str) -> str:
    if order.startswith("spares:"):
        return "Spares gap " + order.removeprefix("spares:").replace(":", " ")
    return f"Site demand {order}"


def _no(v: PathValue, why: str) -> None:
    v["ok"], v["why"] = False, why


def value_unit(facts: Mapping[str, Any], pack: Pack, as_of: datetime | None) -> list[PathValue]:
    """The valuer's routes with the planning limits: a spare only for a region below its target, a redeploy only to a demand
    for the unit's model."""
    values = VALUERS["telecom_network"](facts, pack, as_of)
    for v in values:
        if v["k"] == "spare" and v["ok"] and _spares_order(facts) is None:
            _no(v, NO_TARGET)
        want, have = fact(facts, "demand.model"), fact(facts, "asset.model")
        if v["k"] == "redeploy" and v["ok"] and want and have and want != have:
            _no(v, f"Site demand {fact(facts, 'demand.id')} is for the model {want}")
    return values


def _blocked(c: Mapping[str, Any], pack: Pack, as_of: datetime | None) -> frozenset[str]:
    """The routes the gates block for another case of the queue (on a copy: a gate's hold never touches that case)."""
    results = gate_hold.apply(copy.deepcopy(dict(c)), [], pack, as_of)
    return frozenset(i for r in results if not r.passed and r.effect.kind == "block" for i in r.effect.routes)


def _bids(
    unit: str, facts: Mapping[str, Any], values: Sequence[PathValue], blocked: frozenset[str], cap: dict[str, int]
) -> list[Bid]:
    out: list[Bid] = []
    for v in values:
        if not v["ok"] or v["k"] in blocked:
            continue
        if v["k"] == "redeploy" and (o := _site_order(facts)):
            out.append(Bid(unit, "redeploy", o, v["net"]))
        elif v["k"] == "spare" and (o := _spares_order(facts)):
            gap = fact(facts, "spares.gap")
            if isinstance(gap, int | float) and not isinstance(gap, bool):
                cap[o] = max(int(gap), 0)
                out.append(Bid(unit, "spare", o, v["net"]))
            else:  # no gap on file: nothing to fill, every spare is offered (an order of its own)
                out.append(Bid(unit, "spare", f"{o}:{unit}", v["net"]))
    return out


def _held(unit: str, c: Mapping[str, Any], facts: Mapping[str, Any]) -> list[Bid]:
    rec = c.get("recommendation") or {}
    order = _site_order(facts) if rec.get("id") == "redeploy" else None  # only a named demand is kept for its unit
    return [Bid(unit, "redeploy", order, float("inf"))] if c.get("stage") in HELD and order else []


def plan(
    c: Mapping[str, Any], pack: Pack, as_of: datetime | None, blocked: frozenset[str], members: Sequence[Mapping[str, Any]]
) -> list[PathValue]:
    """The values of case `c` after the queue plan; `members` are the other units of its queue (their cases or facts)."""
    facts = facts_of(c)
    me = key_of(c, facts)
    values = value_unit(facts, pack, as_of)
    cap: dict[str, int] = {}
    bids = _bids(me, facts, values, blocked, cap)
    for m in members:
        if m.get("id") == c.get("id"):
            continue
        mf = facts_of(m)
        mk = key_of(m, mf)
        bids += _held(mk, m, mf) or _bids(mk, mf, value_unit(mf, pack, as_of), _blocked(m, pack, as_of), cap)
    _, lost = fill_orders(bids, cap)
    orders = {b.route: b.order.split(f":{me}")[0] for b in bids if b.unit == me}
    for v in values:
        holder = lost.get((me, v["k"]))
        if holder is not None and v["ok"]:
            _no(v, f"{_said(orders[v['k']])} filled by {holder}" if holder else f"{_said(orders[v['k']])} is full")
    return values
