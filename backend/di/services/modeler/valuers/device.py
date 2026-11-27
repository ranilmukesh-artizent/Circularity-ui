"""Device valuer: a port of the PO prototype's device recommerce engine
(docs/reference/po-modeler/recover-app-prototype.html, "Device recommerce engine", lines 2328-2352; the device branch
of `fSim`, 2411-2413).

- `dLots` (2337): 48 sample lots drawn from `rng(4242)`.
- `dScore` (2341): one channel's cash per unit, expected days to sell and score (cash less a penalty for days past
  the 60-day SLA), and whether the channel may take the lot (grade D never on Buy Now or Marketplace; lot size cap).
- `dDecide` (2347): the business rules (exclude, require, prefer) over the four channels; the best by score.
- P9-6.15 (story DV-11), a received device only: `repair_sell` (a repair quote, then the best listing channel), `parts` (a
  teardown into service stock) and `recycle` (a certified recycler's material value less its fee). Their settings are the pack's
  `valuer.params.more_routes`; a PO lot never has them (`channels_for`). The prototype has no such routes.
- P9-6.16 (story DV-12), a received device only: `replacement`, the avoided purchase of an open replacement demand less prep and
  logistics (`_replacement`); the demand is read by `device.inputs` and reserved at approval by `device.replacement`.

The prototype's TPL has no device entry, so it gives the template no name; it is "Device recommerce" (fixtures/golden/
po/README.md). Pure code: no Session, no I/O. Lots and rules are the prototype's JSON shapes, as in the goldens.
"""

import copy
import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, NotRequired, TypedDict

from di.services.engine.jsmath import js_round, js_sum
from di.services.engine.predictor import PriceBand
from di.services.modeler.carbon import co2_avoided
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers.rng import mulberry32

Lot = dict[str, Any]
Rule = dict[str, Any]

NAME = "Device recommerce"

# The channels, their settings, the learning table and the policy are the pack's `valuer.params` (packs/device.json),
# copied so a valuer never changes the cached pack.
_PACK = load_pack("device")
_PARAMS: dict[str, Any] = copy.deepcopy(_PACK.valuer.params)
DCH: list[str] = _PARAMS["dch"]  # 2329
DCN: dict[str, str] = _PARAMS["dcn"]
WHOLESALE_INDEX: dict[str, float] = _PARAMS["wholesale_index"]  # a wholesale lot's price share of the reference value per grade
# The channels of a Recover device case (a lot with an `imei`, P9-6.4): the pack's `recover_channels`, the ones the valuer can
# price today. A PO lot (no imei) keeps DCH.
RECOVER: list[str] = _PARAMS["recover_channels"]  # 2330
# Channel settings (2332): fee share, fixed fee, logistics per unit, listing window in days, maximum lot size.
DCFG: dict[str, dict[str, float]] = _PARAMS["dcfg"]
# Channel learning per grade, age band and channel (2333): [lots sold, sell-through, days to sell, price index, return rate].
DST: dict[str, dict[str, dict[str, list[float]]]] = _PARAMS["dst"]
# Models (2335): brand, model, reference value of grade A, age band.
DMOD: list[list[Any]] = [
    ["Apple", "iPhone 15", 470, "0-24m"],
    ["Apple", "iPhone 14", 370, "25-48m"],
    ["Apple", "iPhone 13", 290, "25-48m"],
    ["Apple", "iPhone 12", 210, "49m+"],
    ["Samsung", "Galaxy S24", 400, "0-24m"],
    ["Samsung", "Galaxy S23", 300, "25-48m"],
    ["Samsung", "Galaxy S21", 170, "49m+"],
    ["Google", "Pixel 9", 360, "0-24m"],
    ["Google", "Pixel 8", 250, "25-48m"],
    ["Motorola", "Moto G Power 2024", 95, "0-24m"],
]
# The routes of a received device beyond the sale channels (P9-6.15): the pack's settings for `repair_sell`, `parts`, `recycle`.
MORE: dict[str, dict[str, Any]] = _PARAMS["more_routes"]
EXTRA: tuple[str, ...] = tuple(MORE)
GRADE_MULT = {
    "A": 1.0,
    "B": 0.85,
    "C": 0.68,
    "D": 0.45,
}  # a grade's share of the grade-A reference value (the lots' `ref`, dLots 2337)
# Policy (2334): holding cost a unit a day, penalty a day past the SLA, SLA days, cost per return, weekly price erosion,
# recovery floor.
DG: dict[str, float] = _PARAMS["dg"]

# compileDevice(PUB.device) (2367, flow 2357-2366): the published flow's rule DR-01.
LIVE_RULES: list[Rule] = [{"action": "exclude", "id": "DR-01", "path": "buynow", "scope": {"dohMin": 45}}]


class ChannelValue(TypedDict):
    k: str
    cash: float
    days: float
    score: float
    ok: bool
    why: str
    co2: float | None  # kg CO2e avoided for the lot, information only (carbon.co2_avoided); None without a factor
    co2Prov: dict[str, Any] | None  # the card's provenance (carbon.Co2.prov); None without a factor
    # with a price band (P9-6.10): the same cash at the band's P10 and P90, the feed week it rests on and the model that gave it
    p10_cash: NotRequired[float]
    p90_cash: NotRequired[float]
    feed_week: NotRequired[str | None]
    model_id: NotRequired[str | None]
    # `repair_sell` (P9-6.15): the channel the repaired device sells on, and the repair quote it rests on
    via: NotRequired[str]
    repair: NotRequired[dict[str, Any]]
    # `replacement` (P9-6.16): the demand unit it fills, {demand_id, unit_cost, open}
    replacement: NotRequired[dict[str, Any]]


class Decision(TypedDict):
    best: ChannelValue | None
    all: list[ChannelValue]  # every channel, `ok` after the rules


def _build_lots() -> list[Lot]:  # dLots (2337-2340)
    r = mulberry32(4242)
    gm = {"A": 1, "B": 0.85, "C": 0.68, "D": 0.45}
    lots = []
    for i in range(48):
        m = DMOD[math.floor(r() * len(DMOD))]
        g = "ABBCCD"[math.floor(r() * 6)]
        qty = max(2, js_round(math.exp(1.2 + r() * 4.2)))
        doh = 1 + math.floor(r() * 80)
        lots.append(
            {
                "id": f"LOT-{40210 + i}",
                "brand": m[0],
                "model": m[1],
                "band": m[3],
                "grade": g,
                "ref": js_round(m[2] * gm[g]),
                "qty": qty,
                "doh": doh,
            }
        )
    return lots


_LOTS: list[list[Lot]] = []


def sample_lots() -> list[Lot]:
    """The 48 sample lots (golden device_lots.json)."""
    if not _LOTS:
        _LOTS.append(_build_lots())
    return copy.deepcopy(_LOTS[0])


def _cash(lot: Lot, channel: str, price: float) -> tuple[float, float]:
    """(cash a unit, days to sell) on a channel at the sale `price` a unit: an unsold lot falls back to auction after the
    channel's window, at the eroded price."""
    s = DST[lot["grade"]][lot["band"]][channel]
    a = DST[lot["grade"]][lot["band"]]["auction"]
    c = DCFG[channel]
    ca = DCFG["auction"]
    net = price * (1 - c["fee"]) - c["fix"] - c["log"] - s[4] * DG["retc"]
    aun = lot["ref"] * a[3] * (1 - ca["fee"]) - ca["fix"] - ca["log"] - a[4] * DG["retc"]
    days = s[1] * s[2] + (1 - s[1]) * (c["win"] + a[2])
    cash = s[1] * net + (1 - s[1]) * aun * math.pow(1 - DG["ero"], c["win"] / 7) - DG["hold"] * days
    return cash, days


def _wholesale(lot: Lot, band: PriceBand | None) -> tuple[float, float, float, float, str]:
    """(cash, p10 cash, p90 cash, days, why) a unit of a wholesale lot (P9-6.10): the best open approved bid a unit when the
    lot's inputs name one (`inputs.bid_per_unit`, P9-6.11), else the index estimate: the grade's `wholesale_index` times the
    reference value ("No live bid: index estimate"); with a band (the model learned wholesale prices) its P10, P50 and P90."""
    c = DCFG["wholesale"]
    bid = (lot.get("inputs") or {}).get("bid_per_unit")

    def cash(price: float) -> float:
        return price * (1 - c["fee"]) - c["fix"] - c["log"] - DG["hold"] * c["win"]

    if bid is not None:
        v = cash(float(bid))
        return v, v, v, c["win"], "Best open bid"
    if band is not None:
        return cash(band.p50), cash(band.p10), cash(band.p90), c["win"], "No live bid: index estimate"
    v = cash(float(_PARAMS["wholesale_index"][lot["grade"]]) * lot["ref"])
    return v, v, v, c["win"], "No live bid: index estimate"


def repair_line(q: Mapping[str, Any]) -> str:
    """The evidence line of a repair quote: "battery swap +$28 price, −$24 cost, +5 days" (DV-11, verbatim)."""
    return f"{str(q['repair']).lower()} +${q['price_uplift']:g} price, −${q['cost']:g} cost, +{q['days']:g} days"


def _repair_sell(lot: Lot, bands: Mapping[str, PriceBand]) -> tuple[float, float, bool, str, str | None]:
    """(cash, days, ok, why, channel) a unit repaired, then sold (P9-6.15): on each listing channel the repaired price (its sale
    price plus the quote's price uplift) goes through that channel's own formula (fees, logistics, returns, sell-through and the
    days to sell), then the repair cost and the holding cost of the extra days come off:
    cash = repaired price net of the channel − repair cost − hold × extra days. The channel with the most cash takes it. No quote,
    no route."""
    q = (lot.get("inputs") or {}).get("repair_quote")
    if not q:
        return 0.0, 0.0, False, "No repair quote on file", None
    best: tuple[float, float, str] | None = None
    for ch in MORE["repair_sell"]["channels"]:
        if lot["qty"] > DCFG[ch]["lot"] or (lot["grade"] == "D" and ch in ("buynow", "market")):
            continue
        band = bands.get(ch)
        price = (band.p50 if band is not None else lot["ref"] * DST[lot["grade"]][lot["band"]][ch][3]) + float(q["price_uplift"])
        cash, days = _cash(lot, ch, price)
        cash -= float(q["cost"]) + DG["hold"] * float(q["days"])
        if best is None or cash > best[0]:
            best = (cash, days + float(q["days"]), ch)
    if best is None:
        return 0.0, 0.0, False, "", None
    return best[0], best[1], True, repair_line(q), best[2]


def _parts_base(lot: Lot) -> float:
    """The grade-A feed price of the device's SKU (`inputs.feed_price_a`), else the reference value scaled up to grade A."""
    a = (lot.get("inputs") or {}).get("feed_price_a")
    return float(a) if a is not None else float(lot["ref"]) / GRADE_MULT[lot["grade"]]


def _plain(x: float) -> str:
    return f"${x:,.0f}" if round(x, 2) == int(round(x, 2)) else f"${x:,.2f}"


def _replacement(lot: Lot) -> tuple[float, float, bool, str, dict[str, Any]]:
    """(cash, days, ok, why, extra) a unit filling an open replacement demand (P9-6.16, DV-12): the avoided purchase (the demand's
    `unit_cost`, `inputs.replacement`) less the pack's prep and logistics cost; "Avoids buying a replacement: $340". Only a
    single device of the pack's grades and age band with a demand unit left is eligible; the reason says which is missing. The
    demand unit itself is reserved at the decision's approval (`device.replacement`)."""
    p = MORE["replacement"]
    demand = (lot.get("inputs") or {}).get("replacement")
    if lot["grade"] not in p["grades"]:
        return 0.0, p["days"], False, f"Replacement stock takes grade {' or '.join(p['grades'])}", {}
    if lot["band"] not in p["bands"]:
        return 0.0, p["days"], False, f"Replacement stock is for the {' or '.join(p['bands'])} age band", {}
    if not demand or lot["qty"] > p["lot"]:
        return 0.0, p["days"], False, "No open replacement demand", {}
    cost = float(demand["unit_cost"])
    view = {"demand_id": demand["demand_id"], "unit_cost": cost, "open": demand["open"]}
    why = f"Avoids buying a replacement: {_plain(cost)}"
    return cost - p["prep"] - p["logistics"], p["days"], True, why, {"replacement": view}


def _more(lot: Lot, channel: str, bands: Mapping[str, PriceBand]) -> tuple[float, float, bool, str, dict[str, Any]]:
    """(cash, days, ok, why, extra) a unit on `repair_sell`, `parts` or `recycle` (P9-6.15). Parts: the pack's share of the
    grade-A feed price less the teardown cost. Recycle: the material value less the recycler's fee (a certified recycler, with a
    certificate: the `cert` step)."""
    p = MORE[channel]
    if channel == "repair_sell":
        cash, days, ok, why, via = _repair_sell(lot, bands)
        extra: dict[str, Any] = {"via": via, "repair": dict(lot["inputs"]["repair_quote"])} if via else {}
        return cash, days, ok, why, extra
    if channel == "replacement":
        return _replacement(lot)
    ok = lot["qty"] <= p["lot"]
    if channel == "parts":
        return p["value_share"] * _parts_base(lot) - p["teardown"], p["days"], ok, "", {}
    return p["material"] - p["fee"], p["days"], ok, "", {}


def score(lot: Lot, channel: str, band: PriceBand | None = None, bands: Mapping[str, PriceBand] | None = None) -> ChannelValue:
    """dScore (2341): an unsold lot falls back to auction after the channel's window, at the eroded price. With `band` the
    sale price is its P50 (instead of the reference value times the grade's price index) and the value gains `p10_cash` and
    `p90_cash` (the same formula at P10 and P90), `feed_week` and `model_id`; days and sell-through still come from `DST`.
    The `wholesale` channel (a Recover case's lot sale, P9-6.10) has no learning table: see `_wholesale`. The routes of
    `EXTRA` (P9-6.15) have none either: see `_more`; `bands` (default the lot's own) are the sale channels' bands for
    `repair_sell`."""
    extra: dict[str, Any] = {}
    if channel in EXTRA:
        cash, days, ok, why, extra = _more(lot, channel, bands_of(lot) if bands is None else bands)
    elif channel == "wholesale":
        c = DCFG[channel]
        cash, lo, hi, days, why = _wholesale(lot, band)
        ok = lot["qty"] <= c["lot"]
        why = why if ok else ""
        if band is not None:
            extra = {"p10_cash": lo, "p90_cash": hi, "feed_week": _week(band), "model_id": band.model_id}
    else:
        c = DCFG[channel]
        why = ""
        price = lot["ref"] * DST[lot["grade"]][lot["band"]][channel][3] if band is None else band.p50
        cash, days = _cash(lot, channel, price)
        ok = not (lot["grade"] == "D" and channel in ("buynow", "market")) and lot["qty"] <= c["lot"]
        if band is not None:
            extra = {
                "p10_cash": _cash(lot, channel, band.p10)[0], "p90_cash": _cash(lot, channel, band.p90)[0],
                "feed_week": _week(band), "model_id": band.model_id,
            }  # fmt: skip
    if ok:
        ok, why = _checks(lot, channel, cash, why)
    cv = co2_avoided(_PACK, None, channel, lot["qty"], confirmed=False)
    value: ChannelValue = {
        "k": channel,
        "cash": cash,
        "days": days,
        "score": cash - DG["pen"] * max(0, lot["doh"] + days - DG["sla"]),
        "ok": ok,
        "why": why,
        "co2": cv.kg if cv else None,
        "co2Prov": cv.prov() if cv else None,
    }
    return value | extra  # type: ignore[return-value]


LISTING = ("buynow", "offers", "auction")  # the channels that list the device (GR-D9)


def _money(x: float) -> str:
    return f"${int(js_round(x)):,}"


def _checks(lot: Lot, channel: str, cash: float, why: str) -> tuple[bool, str]:
    """The guardrails that read the case's facts (P9-6.19, DV-15). GR-D5: `market` is out when its cash is below the live Buy Now
    price of the same SKU and grade (`inputs.live_buynow`; none, no effect). GR-D9: a Recover device (an `imei`) whose case
    opened with a parts declaration fact (`inputs.parts_status`, always present from `gather`) cannot be listed on Buy Now,
    Offers or Auction without a genuine or non-genuine declaration; non-genuine is allowed and shown. A lot with no such fact
    (a PO lot, a hand-built lot) is unchanged. Returns (ok, why)."""
    inp = lot.get("inputs") or {}
    live = inp.get("live_buynow")
    if channel == "market" and live is not None and cash < float(live):
        return False, f"Marketplace never undercuts the live Buy Now price (GR-D5): {_money(cash)} < {_money(float(live))}"
    if (
        (channel in LISTING or channel == "repair_sell") and lot.get("imei") and "parts_status" in inp
    ):  # repair then sell lists it too
        status = inp["parts_status"]
        if status == "non_genuine":
            return True, (f"{why}; " if channel == "repair_sell" and why else "") + "Parts declared non-genuine (GR-D9)"
        if status != "genuine":
            return False, "No genuine-parts declaration (GR-D9)"
    return True, why


def _week(band: PriceBand) -> str | None:
    return band.feed_week.isoformat() if isinstance(band.feed_week, date) else None


def bands_of(lot: Lot) -> dict[str, PriceBand]:
    """The price bands a received device's case opened with (`inputs.bands`, one per channel, P9-6.10); none for a PO lot."""
    out: dict[str, PriceBand] = {}
    for k, b in ((lot.get("inputs") or {}).get("bands") or {}).items():
        week = b.get("feed_week")
        out[k] = PriceBand(
            float(b["p10"]), float(b["p50"]), float(b["p90"]), b.get("model_id"), date.fromisoformat(week) if week else None
        )
    return out


def in_scope(lot: Lot, s: dict[str, Any]) -> bool:  # dIn (2345)
    for dim in ("brand", "grade", "band"):
        if s.get(dim) and lot[dim] not in s[dim]:
            return False
    if s.get("dohMin") not in (None, "") and lot["doh"] < float(s["dohMin"]):
        return False
    if s.get("qtyMin") not in (None, "") and lot["qty"] < float(s["qtyMin"]):
        return False
    return _listing_in_scope(lot, s)


def _listing_in_scope(lot: Lot, s: dict[str, Any]) -> bool:
    """The scope of a listed device (P9-6.13): the channel it is listed on, the days listed (`listDaysMin`, at or above) and
    the offers (`offersMax`, at most; `offers_under` is the offers less one, so the dim's "below" reads "at most"). A lot with
    no listing is out of any scope that names one of these."""
    got = ((lot.get("inputs") or {}).get("listing")) or {}
    if s.get("listChannel") and got.get("channel") not in s["listChannel"]:
        return False
    if s.get("listDaysMin") not in (None, "") and (got.get("days") is None or got["days"] < float(s["listDaysMin"])):
        return False
    if s.get("offersMax") in (None, ""):
        return True
    return got.get("offers_under") is not None and got["offers_under"] < float(s["offersMax"])


def channels_for(lot: Lot) -> list[str]:
    """The channels a lot is scored on (P9-6.4): `DCH` for a PO lot (no `imei`: today's numbers), the pack's Recover list
    for a received device. The channel list is the only switch between the two kinds of case."""
    return list(RECOVER if lot.get("imei") else DCH)


def decide(lot: Lot, rules: Sequence[Rule] | None = None, bands: Mapping[str, PriceBand] | None = None) -> Decision:
    """dDecide (2347): rules in order; a prefer rule wins when within 15% of the best score; rules that would leave no
    channel are waived. `rules` defaults to the published flow's rules. Only `channels_for(lot)` are scored, each on its price
    band (`bands`, default the lot's own, `bands_of`)."""
    bands = bands_of(lot) if bands is None else bands
    values = [score(lot, k, bands.get(k), bands) for k in channels_for(lot)]
    keep = [v["ok"] for v in values]
    pref = None
    for r in LIVE_RULES if rules is None else rules:
        if not in_scope(lot, r.get("scope") or {}):
            continue
        v = next((x for x in values if x["k"] == r.get("path")), None)
        if not v or not v["ok"]:
            continue
        if r["action"] == "exclude":
            v["ok"] = False
        elif r["action"] == "require":
            for x in values:
                if x is not v:
                    x["ok"] = False
        else:
            pref = r["path"]
    if not any(v["ok"] for v in values):
        for v, ok0 in zip(values, keep, strict=True):
            v["ok"] = ok0
    ok = sorted((v for v in values if v["ok"]), key=lambda v: -v["score"])
    pv = next((v for v in ok if v["k"] == pref), None) if pref else None
    if pv and pv is not ok[0] and pv["score"] >= ok[0]["score"] - abs(ok[0]["score"]) * 0.15:
        ok = [pv] + [v for v in ok if v is not pv]
    return {"best": copy.copy(ok[0]) if ok else None, "all": values}


def _best(lot: Lot, rules: Sequence[Rule]) -> ChannelValue:
    best = decide(lot, rules)["best"]
    if best is None:
        raise ValueError(f"no channel may take lot {lot['id']}")
    return best


def simulate(base_rules: Sequence[Rule], cand_rules: Sequence[Rule], lots: Sequence[Lot] | None = None) -> dict[str, Any]:
    """fSim for the device template (2411-2413): every lot decided under both rule sets; the lots whose channel
    changes (`flips`), the change in cash over all units (`dv`), in average days a unit (`dd`) and in units sold past
    the SLA (`dl`). `lots` defaults to the sample lots."""
    ls = list(lots) if lots is not None else sample_lots()
    base = [_best(lot, base_rules) for lot in ls]
    cand = [_best(lot, cand_rules) for lot in ls]
    u = sum(lot["qty"] for lot in ls)

    def tot(vs: list[ChannelValue]) -> float:
        return js_sum(v["cash"] * lot["qty"] for v, lot in zip(vs, ls, strict=True))

    def days(vs: list[ChannelValue]) -> float:
        return js_sum(v["days"] * lot["qty"] for v, lot in zip(vs, ls, strict=True)) / u

    def late(vs: list[ChannelValue]) -> int:
        return sum(lot["qty"] if lot["doh"] + v["days"] > DG["sla"] else 0 for v, lot in zip(vs, ls, strict=True))

    flips = [
        {"id": lot["id"], "from": b["k"], "to": s["k"]} for lot, b, s in zip(ls, base, cand, strict=True) if b["k"] != s["k"]
    ]
    return {
        "kind": "device",
        "n": len(ls),
        "u": u,
        "flips": flips,
        "dv": tot(cand) - tot(base),
        "cash": tot(cand),
        "dd": days(cand) - days(base),
        "days": days(cand),
        "dl": late(cand) - late(base),
    }
