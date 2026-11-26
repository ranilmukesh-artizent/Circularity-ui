"""The telecom five-route valuer (plan 9, P9-10.9, story TN-11; registry entry I-21: `VALUERS["telecom_network"]`). It values
every route a decommissioned network unit can take, net of what each costs, so the case recommends the route with the best money
after costs and shows "New spend avoided" as the value of the two reuse routes.

    value_routes(facts, pack, as_of) -> [PathValue]   `redeploy`, `spare`, `resell`, `harvest`, `recycle`, in that order;
                                                      `net` = value - costs - holding

    redeploy  value "New spend avoided" = the model's new price, against a named open site demand (else not ok: "No open site
              demand"); costs test, firmware upgrade (when the unit's firmware major version is `firmware_major_gap_for_upgrade`
              or more behind the demand's minimum), logistics, install job
    spare     value "New spend avoided" = new price x the use probability of the unit's spares region; costs refurbishment,
              holding x `spare_horizon_months`, logistics
    resell    value = the best broker bid; costs broker fee, logistics, export compliance; not ok "A region needs this model
              within 6 months" when any region's six-month need for the model is above zero
    harvest   value = the sum of the board values of the open repair needs; costs teardown and a test of each board
    recycle   value = weight x the material rate; costs recycling fee and logistics

`facts` is the case's valuer snapshot: nested records (`asset`, `market`, `demand`) or the same names as flat dotted keys. The
inputs are the facts of spares planning (P9-10.4: `market.new_price`, `demand.use_probability`, `demand.need_6m`, each a number
for the unit's own cell or a mapping region -> number), the broker marketplace (P9-10.5: `market.broker_bids`, a list of bids
with `unitPrice`), the test bench (`asset.weight_kg`, `asset.firmware`) and the site demand (`demand.open_site_demand`, `id`,
`site`, `firmware_min_major`, `board_needs`: a list of `{part, value}`). The unit's spares region is `asset.spares_region`, else
`spares.region_below_target`, else `asset.region`. Every number is a parameter of the pack (`valuer.params.params`); money is
`Decimal`, each figure rounded half up to the cent.

Order (R20): the gates (inventory match, wipe, covered equipment, export control) have already failed the routes they block in
`decide_case`; this valuer prices all five either way, and a route a gate blocks keeps its value and loses its rank. A route that
cannot be valued (a missing input) is not ok and says what is missing; it is never valued from a made-up number. Carbon `d` is 1
only with a named demand (B 5.7): the avoided figure is asked of `co2_avoided` with `confirmed` set by that demand.

Never does: read a session, a clock or a source, write anything, or call a language model: every figure and every reason here is
computed (R16), so there is nothing for the model to interpret. Export classification and screening stay with the gate
(`gate_checks.network`); the export compliance cost here is the pack's flat cost of a resale.
"""

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from di.services.modeler.carbon import co2_avoided
from di.services.modeler.pack import Pack
from di.services.modeler.valuers.tool_fleet import PathValue, ValueLine

D = Decimal
CENT = D("0.01")
SPEND = "New spend avoided"


def _d(x: Any) -> Decimal:
    return D(str(x))


def _c(x: Decimal) -> Decimal:
    return x.quantize(CENT, ROUND_HALF_UP)


def _f(x: Decimal) -> float:
    return float(_c(x))


def _fact(facts: Mapping[str, Any], path: str) -> Any:
    """A fact by dotted name: the nested record first, else the flat key; None when missing."""
    cur: Any = facts
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return facts.get(path)
        cur = cur[part]
    return cur


def _num(v: Any) -> Decimal | None:
    return _d(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _line(type_: str, label: str, amt: Decimal, kind: str, basis: str = "") -> ValueLine:
    return {"type": type_, "label": label, "basis": basis, "amt": _f(amt), "kind": kind}


def _no(route: str, name: str, why: str, misses: list[str] | None = None) -> PathValue:
    return {
        "k": route, "ok": False, "gross": 0.0, "cost": 0.0, "hold": 0.0, "net": 0.0, "why": why, "lines": [],
        "dest": {"name": name}, "misses": misses or [], "co2": None, "co2Prov": None,
    }  # fmt: skip


def _value(
    route: str, name: str, lines: list[ValueLine], pack: Pack, facts: Mapping[str, Any], dest: dict[str, Any], named: bool
) -> PathValue:
    total = {t: sum((_d(x["amt"]) for x in lines if x["type"] == t), D(0)) for t in ("v", "c", "h")}
    cls = facts.get("cls") or _fact(facts, "asset.class")
    cv = co2_avoided(pack, cls, route, float(facts.get("qty") or 1), confirmed=named)
    return {
        "k": route, "ok": True, "gross": _f(total["v"]), "cost": _f(total["c"]), "hold": _f(total["h"]),
        "net": _f(total["v"] - total["c"] - total["h"]), "why": "", "lines": lines, "dest": dest | {"name": name},
        "misses": [], "co2": cv.kg if cv else None, "co2Prov": cv.prov() if cv else None,
    }  # fmt: skip


def _region(facts: Mapping[str, Any]) -> str | None:
    """The region whose spares pool the unit would join."""
    for path in ("asset.spares_region", "spares.region_below_target", "asset.region"):
        r = _fact(facts, path)
        if r:
            return str(r)
    return None


def _of_cell(v: Any, region: str | None) -> Decimal | None:
    """A planning figure of the unit's own cell: a number as it is, or the region's entry of a mapping."""
    if isinstance(v, Mapping):
        return _num(v.get(region)) if region is not None else None
    return _num(v)


def _firmware_gap(facts: Mapping[str, Any]) -> int | None:
    """How many major versions the unit's firmware is behind the demand's minimum; None when either is unknown."""
    fw = re.match(r"\D*(\d+)", str(_fact(facts, "asset.firmware") or ""))
    need = _num(_fact(facts, "demand.firmware_min_major"))
    return int(need) - int(fw.group(1)) if fw and need is not None else None


def _redeploy(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    if _fact(facts, "demand.open_site_demand") is not True:
        return _no("redeploy", name, "No open site demand")
    price = _num(_fact(facts, "market.new_price"))
    if price is None:
        return _no("redeploy", name, "No new price on file: market.new_price missing", ["market.new_price"])
    site, demand = _fact(facts, "demand.site"), _fact(facts, "demand.id")
    lines = [
        _line("v", SPEND, price, "purchase", f"new price of the model, against {demand or 'the open site demand'}"),
        _line("c", "Test", _d(p["test_cost"]), "prep"),
    ]
    gap = _firmware_gap(facts)
    if gap is not None and gap >= int(p["firmware_major_gap_for_upgrade"]):
        lines.append(_line("c", "Firmware upgrade", _d(p["firmware_upgrade_cost"]), "prep", f"{gap} major versions behind"))
    lines += [
        _line("c", "Logistics", _d(p["logistics_per_unit"]), "fees"),
        _line("c", "Install job", _d(p["install_job"]), "fees", f"at {site}" if site else ""),
    ]
    return _value("redeploy", name, lines, pack, facts, {"site": site, "demand": demand}, True)


def _spare(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    region = _region(facts)
    price = _num(_fact(facts, "market.new_price"))
    prob = _of_cell(_fact(facts, "demand.use_probability"), region)
    gone = [k for k, v in (("market.new_price", price), ("demand.use_probability", prob)) if v is None]
    if price is None or prob is None:
        return _no("spare", name, "No spares value yet: " + ", ".join(gone) + " missing", gone)
    months = int(p["spare_horizon_months"])
    lines = [
        _line("v", SPEND, price * prob, "purchase", f"new price x {prob} use probability in {region or 'the region'}"),
        _line("c", "Refurbishment", _d(p["refurb_cost"]), "prep"),
        _line("h", "Holding as a spare", _d(p["spare_holding_per_month"]) * months, "fees", f"{months} months"),
        _line("c", "Logistics", _d(p["logistics_per_unit"]), "fees"),
    ]
    named = _fact(facts, "demand.open_site_demand") is True
    return _value("spare", name, lines, pack, facts, {"region": region}, named)


def _resell(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    prices = [
        _num(b.get("unitPrice")) for b in _fact(facts, "market.broker_bids") or [] if isinstance(b, Mapping)
    ]  # fmt: skip
    best = max((x for x in prices if x is not None), default=None)
    if best is None:
        return _no("resell", name, "No broker bid", ["market.broker_bids"])
    need = _fact(facts, "demand.need_6m")
    if need is None:
        return _no("resell", name, "No six-month need on file: demand.need_6m missing", ["demand.need_6m"])
    cells = need if isinstance(need, Mapping) else {_region(facts): need}
    regions = sorted(str(r) for r, n in cells.items() if (_num(n) or D(0)) > 0)
    lines = [
        _line("v", "Best broker bid", best, "sale", "the highest bid"),
        _line("c", "Broker fee", best * _d(p["broker_fee_pct"]), "fees", f"{_d(p['broker_fee_pct']) * 100:.0f}% of the bid"),
        _line("c", "Logistics", _d(p["logistics_per_unit"]), "fees"),
        _line("c", "Export compliance", _d(p["export_compliance_cost"]), "fees"),
    ]
    v = _value("resell", name, lines, pack, facts, {"regions": regions}, False)
    if regions:  # the value stays on the route; the route is not offered
        v["ok"], v["why"] = False, f"A region needs this model within {int(p['resale_needs_horizon_months'])} months"
    return v


def _harvest(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    needs = [b for b in _fact(facts, "demand.board_needs") or [] if isinstance(b, Mapping) and _num(b.get("value")) is not None]
    if not needs:
        return _no("harvest", name, "No open repair need for a board")
    lines = [_line("v", f"Board {b.get('part') or 'for a repair'}", _d(b["value"]), "parts", "open repair need") for b in needs]
    lines += [
        _line("c", "Teardown", _d(p["teardown_cost"]), "prep"),
        _line("c", "Board tests", _d(p["board_test_cost"]) * len(needs), "prep", f"{len(needs)} boards"),
    ]
    return _value("harvest", name, lines, pack, facts, {"boards": len(needs)}, False)


def _recycle(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    kg = _num(_fact(facts, "asset.weight_kg"))
    if kg is None:
        return _no("recycle", name, "No weight on file: asset.weight_kg missing", ["asset.weight_kg"])
    lines = [
        _line("v", "Material value", kg * _d(p["material_per_kg"]), "material", f"{kg} kg x {p['material_per_kg']} a kg"),
        _line("c", "Recycling fee", _d(p["recycle_fee"]), "fees"),
        _line("c", "Logistics", _d(p["logistics_per_unit"]), "fees"),
    ]
    return _value("recycle", name, lines, pack, facts, {}, False)


def value_routes(facts: Mapping[str, Any], pack: Pack, _as_of: datetime | None = None) -> list[PathValue]:
    """The five routes of the unit valued net, in the pack's order (`_as_of` is for plug-ins that read evidence by time;
    unused here)."""
    p: Mapping[str, Any] = pack.valuer.params["params"]
    names = {r.id: r.name for r in pack.routes}
    return [
        _redeploy(facts, pack, p, names["redeploy"]),
        _spare(facts, pack, p, names["spare"]),
        _resell(facts, pack, p, names["resell"]),
        _harvest(facts, pack, p, names["harvest"]),
        _recycle(facts, pack, p, names["recycle"]),
    ]
