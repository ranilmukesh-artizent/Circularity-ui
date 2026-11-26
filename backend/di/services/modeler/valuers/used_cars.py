"""The used-car channel valuer (plan 9, P9-9.10, story UC-10; registry entry I-21: `VALUERS["used_cars"]`). It values every
channel a returned car can take, net of what each costs, so the case recommends the channel with the best money after costs.

    value_routes(facts, pack, as_of) -> [PathValue]   `retail:<lot id>` per lot with sales history, then `auction`,
                                                      `dealer_trade`, `salvage`; `net` = value - costs
    evidence_lines(facts, best, pack) -> [str]        the plain facts behind the best channel (optional valuer hook)

`facts` is the case's valuer snapshot: nested records (`asset`, `condition`, `market`) as the canonical store holds them, or
the same names as flat dotted keys (`"asset.book_value"`, the pack's sample form). The market inputs are the facts of the
dealer system (per lot: `lot_avg_price`, `lot_days_to_sale`, `lot_spread`, `lot_comparables`, `lot_distance_miles`;
`dealer_bid`), the pricing guide (`retail_guide_price`, `wholesale_guide_price`) and the auction platform
(`auction_sell_fee`, `auction_transport`, `auction_next_sale_days`, `salvage_bid`), written by their adapters (P9-9.6).
Every number is a parameter of the pack (`valuer.params.params`): nothing is a constant here. Money is `Decimal`, each figure
rounded half up to the cent.

Order (R20): the gates (title, odometer, recall, brand) have already failed the routes they block in `decide_case`; this valuer
prices all four channels either way, and a route a gate blocks keeps its value and loses its rank. A channel that cannot be
valued (a missing input) is not ok and says what is missing; it is never valued from a made-up number.

Never does: read a session, a clock or a source, write anything, or call a language model: every figure and every reason here
is computed (R16), so there is nothing for the model to interpret. A person approves reconditioning over the limit (AP-UC-RECON,
I-10); this valuer only reports it.
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from di.services.modeler.carbon import co2_avoided
from di.services.modeler.pack import Pack
from di.services.modeler.valuers.tool_fleet import PathValue, ValueLine

D = Decimal
CENT = D("0.01")
RECON_APPROVAL = "AP-UC-RECON"  # the guardrail that holds the recon limit


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


def _num(facts: Mapping[str, Any], path: str) -> Decimal | None:
    v = _fact(facts, path)
    return _d(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _by_lot(facts: Mapping[str, Any], path: str, lot: str) -> Any:
    v = _fact(facts, path)
    return v.get(lot) if isinstance(v, Mapping) else None


def _line(type_: str, label: str, amt: Decimal, kind: str, basis: str = "") -> ValueLine:
    return {"type": type_, "label": label, "basis": basis, "amt": _f(amt), "kind": kind}


def _grade(facts: Mapping[str, Any], pack: Pack) -> str | None:
    """The car's grade: the case's own, else the pack's mapping of the inspection's condition score."""
    g = facts.get("grade") or _fact(facts, "condition.grade")
    if g:
        return str(g)
    score = _fact(facts, "condition.condition_score")
    return pack.grades.map_from.get(str(score)) if score is not None else None


def _pct(x: Decimal) -> str:
    return f"{(x * 100).quantize(D('1'), ROUND_HALF_UP)}%"


def _value(
    route: str, name: str, lines: list[ValueLine], pack: Pack, facts: Mapping[str, Any], dest: dict[str, Any]
) -> PathValue:
    total = {t: sum((_d(x["amt"]) for x in lines if x["type"] == t), D(0)) for t in ("v", "c", "h")}
    qty = float(facts.get("qty") or 1)
    cv = co2_avoided(pack, facts.get("cls"), route.split(":")[0], qty, confirmed=False)
    return {
        "k": route, "ok": True, "gross": _f(total["v"]), "cost": _f(total["c"]), "hold": _f(total["h"]),
        "net": _f(total["v"] - total["c"] - total["h"]), "why": "", "lines": lines, "dest": dest | {"name": name},
        "misses": [], "co2": cv.kg if cv else None, "co2Prov": cv.prov() if cv else None,
    }  # fmt: skip


def _set_dest(v: PathValue, extra: dict[str, Any]) -> None:
    v["dest"] = {**(v["dest"] or {}), **extra}


def _no(route: str, name: str, why: str, misses: list[str] | None = None) -> PathValue:
    return {
        "k": route, "ok": False, "gross": 0.0, "cost": 0.0, "hold": 0.0, "net": 0.0, "why": why, "lines": [],
        "dest": {"name": name, "days": None, "confidence": None, "gross_vs_book": None}, "misses": misses or [],
        "co2": None, "co2Prov": None,
    }  # fmt: skip


def _dest(days: Any, confidence: Decimal | None, net: float, book: Decimal | None) -> dict[str, Any]:
    gvb = _f(_d(net) - book) if book is not None else None
    return {"days": days, "confidence": float(confidence) if confidence is not None else None, "gross_vs_book": gvb}


def _confidence(spread: Decimal | None, value: Decimal, few: bool, params: Mapping[str, Any]) -> Decimal | None:
    """1 - spread / value, to 2 places; times the pack's factor when the lot has few comparables."""
    if spread is None or value <= 0:
        return None
    conf = (1 - spread / value).quantize(CENT, ROUND_HALF_UP)
    return (conf * _d(params["confidence_few_comparables_factor"])).quantize(CENT, ROUND_HALF_UP) if few else conf


def _retail(
    lot: str, facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], names: Mapping[str, str], recon: Decimal | None
) -> PathValue:
    route, label = f"retail:{lot}", f"{names['retail']} · {_lot_name(facts, lot)}"
    if recon is None:
        return _no(route, label, "No reconditioning estimate yet: the inspection has not been read", ["condition.recon_estimate"])
    n = _by_lot(facts, "market.lot_comparables", lot)
    avg = _by_lot(facts, "market.lot_avg_price", lot)
    guide = _num(facts, "market.retail_guide_price")
    few = n is not None and n < int(p["confidence_min_comparables"])
    if few and guide is not None:  # too few sales on the lot: the pricing guide's retail value instead
        value, basis = guide, f"retail guide value ({n} comparables at the lot)"
    else:
        value, basis = (
            _d(avg if avg is not None else guide),
            f"average of {n if n is not None else 'the'} comparable sales at the lot",
        )
    if avg is None and guide is None:
        return _no(route, label, "No retail price for this lot yet", ["market.lot_avg_price"])
    miles, days = (
        _d(_by_lot(facts, "market.lot_distance_miles", lot) or 0),
        _d(_by_lot(facts, "market.lot_days_to_sale", lot) or 0),
    )
    warranty = _d(p["warranty_reserve_pct"])
    lines = [
        _line("v", "Retail price", value, "sale", basis),
        _line("c", "Reconditioning", recon, "prep", "inspection estimate"),
        _line("c", f"Transport to {_lot_name(facts, lot)}", miles * _d(p["transport_per_mile"]), "fees", f"{miles} miles"),
        _line("h", "Holding cost", days * _d(p["holding_cost_per_day"]), "fees", f"{days} days to sell at the lot"),
        _line("c", "Retail selling cost", _d(p["retail_selling_cost"]), "fees"),
        _line("c", "Warranty reserve", warranty * value, "risk", f"{_pct(warranty)} of the price"),
    ]  # fmt: skip
    v = _value(route, label, lines, pack, facts, {})
    conf = _confidence(_num({"s": _by_lot(facts, "market.lot_spread", lot)}, "s"), value, few, p)
    _set_dest(v, _dest(_by_lot(facts, "market.lot_days_to_sale", lot), conf, v["net"], _num(facts, "asset.book_value")))
    return v


def _lot_name(facts: Mapping[str, Any], lot: str) -> str:
    named = _by_lot(facts, "market.lot_names", lot)
    return str(named) if named else lot


def _auction(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    need = {k: _num(facts, k) for k in (
        "market.wholesale_guide_price", "market.auction_sell_fee", "market.auction_transport", "market.auction_next_sale_days",
        "asset.mileage_at_return",
    )}  # fmt: skip
    grade = _grade(facts, pack)
    gone = [k for k, v in need.items() if v is None] + ([] if grade else ["condition.grade"])
    if gone:
        return _no("auction", name, "No auction value yet: " + ", ".join(gone) + " missing", gone)
    wholesale, fee, transport, days, miles = (_d(need[k]) for k in need)  # none is missing: `gone` is empty
    tops = sorted(int(t) for t in p["mileage_band_tops"])
    top = next((t for t in tops if miles < t), tops[-1])
    over = max(D(0), miles - top) / D(10000)  # tens of thousands of miles over the band's top
    factor = _d(p["auction_condition_factor"][grade])
    value = wholesale * factor * (1 + _d(p["mileage_factor_per_10k_over_band"]) * over)
    arbitration = _d(p["arbitration_risk_pct"])
    lines = [
        _line("v", "Auction price", value, "sale", f"wholesale guide x grade {grade}, {over:.2f} x 10k miles over"),
        _line("c", "Auction selling fee", fee, "fees"),
        _line("c", "Transport to the auction", transport, "fees"),
        _line("h", "Holding until the next sale", days * _d(p["holding_cost_per_day"]), "fees", f"{days} days"),
        _line("c", "Arbitration risk", arbitration * value, "risk", f"{_pct(arbitration)} of the price"),
    ]  # fmt: skip
    v = _value("auction", name, lines, pack, facts, {})
    _set_dest(v, _dest(int(days), None, v["net"], _num(facts, "asset.book_value")))
    return v


def _dealer(facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str) -> PathValue:
    bid = _num(facts, "market.dealer_bid")
    if bid is None:
        return _no("dealer_trade", name, "No partner bid", ["market.dealer_bid"])
    lines = [
        _line("v", "Partner dealer bid", bid, "sale", "the highest partner bid"),
        _line("c", "Transport to the dealer", _d(p["dealer_transport"]), "fees"),
        _line("c", "Title transfer", _d(p["title_transfer_cost"]), "fees"),
    ]
    v = _value("dealer_trade", name, lines, pack, facts, {})
    _set_dest(v, _dest(None, None, v["net"], _num(facts, "asset.book_value")))
    return v


def _salvage(
    facts: Mapping[str, Any], pack: Pack, p: Mapping[str, Any], name: str, recon: Decimal | None, best_retail: Decimal | None
) -> PathValue:
    share = _d(p["salvage_trigger_recon_share"])
    if recon is None or best_retail is None:
        return _no("salvage", name, "Not considered: no reconditioning estimate or retail value yet")
    if recon <= share * best_retail:
        return _no("salvage", name, f"Not considered: recon under {_pct(share)} of retail value")
    bid = _num(facts, "market.salvage_bid")
    if bid is None:
        return _no("salvage", name, "No salvage bid", ["market.salvage_bid"])
    lines = [
        _line("v", "Salvage bid", bid, "sale", "the best salvage bid"),
        _line("c", "Tow", _d(p["salvage_tow"]), "fees"),
        _line("c", "Title brand administration", _d(p["salvage_brand_admin"]), "fees"),
    ]
    v = _value("salvage", name, lines, pack, facts, {})
    _set_dest(v, _dest(None, None, v["net"], _num(facts, "asset.book_value")))
    return v


def value_routes(facts: Mapping[str, Any], pack: Pack, _as_of: datetime | None = None) -> list[PathValue]:
    """Every channel of the car, valued net: one retail route per lot with sales history (by lot id), then auction, dealer
    trade and salvage (`_as_of` is for plug-ins that read evidence by time; unused here)."""
    p: Mapping[str, Any] = pack.valuer.params["params"]
    names = {r.id: r.name for r in pack.routes}
    recon = _num(facts, "condition.recon_estimate")
    prices = _fact(facts, "market.lot_avg_price")
    lots = sorted(prices) if isinstance(prices, Mapping) else []
    retail = [_retail(lot, facts, pack, p, names, recon) for lot in lots]
    if not retail:  # no lot has sales history yet: the channel stays on the case, not valued
        retail = [_no("retail", names["retail"], "No lot has comparable sales yet", ["market.lot_avg_price"])]
    best = max((_d(x["gross"]) for x in retail if x["ok"]), default=None)
    guide = _num(facts, "market.retail_guide_price")
    return [
        *retail,
        _auction(facts, pack, p, names["auction"]),
        _dealer(facts, pack, p, names["dealer_trade"]),
        _salvage(facts, pack, p, names["salvage"], recon, best if best is not None else guide),
    ]


def evidence_lines(facts: Mapping[str, Any], best: PathValue | None, pack: Pack) -> list[str]:
    """The plain facts behind the decision: the comparable sales at the best lot, the recon against the approval limit and
    the auction price before fees. A line is left out when its facts are missing."""
    out: list[str] = []
    if best and best["k"].startswith("retail:"):
        lot = best["k"].split(":", 1)[1]
        n, days = _by_lot(facts, "market.lot_comparables", lot), _by_lot(facts, "market.lot_days_to_sale", lot)
        if n is not None and days is not None:
            out.append(f"Comparable sales at {_lot_name(facts, lot)}: {n}, average {days} days")
    recon = _num(facts, "condition.recon_estimate")
    limit = next((g.param for g in pack.guardrails if g.id == RECON_APPROVAL and g.param), None)
    if recon is not None and limit is not None:
        out.append(f"Recon ${_c(recon):,.0f} against the ${_c(_d(limit.value)):,.0f} limit")
    auction = next((v for v in value_routes(facts, pack) if v["k"] == "auction" and v["ok"]), None)
    if auction is not None:
        out.append(f"Auction ${_c(_d(auction['gross'])):,.0f} before fees")
    return out
