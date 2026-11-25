"""Device valuer: a port of the PO prototype's device recommerce engine
(docs/reference/po-modeler/recover-app-prototype.html, "Device recommerce engine", lines 2328-2352; the device branch
of `fSim`, 2411-2413).

- `dLots` (2337): 48 sample lots drawn from `rng(4242)`.
- `dScore` (2341): one channel's cash per unit, expected days to sell and score (cash less a penalty for days past
  the 60-day SLA), and whether the channel may take the lot (grade D never on Buy Now or Marketplace; lot size cap).
- `dDecide` (2347): the business rules (exclude, require, prefer) over the four channels; the best by score.

The prototype's TPL has no device entry, so it gives the template no name; it is "Device recommerce" (fixtures/golden/
po/README.md). Pure code: no Session, no I/O. Lots and rules are the prototype's JSON shapes, as in the goldens.
"""

import copy
import math
from collections.abc import Sequence
from typing import Any, TypedDict

from di.services.engine.jsmath import js_round, js_sum
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
DCN: dict[str, str] = _PARAMS["dcn"]  # 2330
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


def score(lot: Lot, channel: str) -> ChannelValue:
    """dScore (2341): an unsold lot falls back to auction after the channel's window, at the eroded price."""
    s = DST[lot["grade"]][lot["band"]][channel]
    a = DST[lot["grade"]][lot["band"]]["auction"]
    c = DCFG[channel]
    ca = DCFG["auction"]
    net = lot["ref"] * s[3] * (1 - c["fee"]) - c["fix"] - c["log"] - s[4] * DG["retc"]
    aun = lot["ref"] * a[3] * (1 - ca["fee"]) - ca["fix"] - ca["log"] - a[4] * DG["retc"]
    days = s[1] * s[2] + (1 - s[1]) * (c["win"] + a[2])
    cash = s[1] * net + (1 - s[1]) * aun * math.pow(1 - DG["ero"], c["win"] / 7) - DG["hold"] * days
    ok = not (lot["grade"] == "D" and channel in ("buynow", "market")) and lot["qty"] <= c["lot"]
    cv = co2_avoided(_PACK, None, channel, lot["qty"], confirmed=False)
    return {
        "k": channel,
        "cash": cash,
        "days": days,
        "score": cash - DG["pen"] * max(0, lot["doh"] + days - DG["sla"]),
        "ok": ok,
        "why": "",
        "co2": cv.kg if cv else None,
        "co2Prov": cv.prov() if cv else None,
    }


def in_scope(lot: Lot, s: dict[str, Any]) -> bool:  # dIn (2345)
    for dim in ("brand", "grade", "band"):
        if s.get(dim) and lot[dim] not in s[dim]:
            return False
    if s.get("dohMin") not in (None, "") and lot["doh"] < float(s["dohMin"]):
        return False
    return not (s.get("qtyMin") not in (None, "") and lot["qty"] < float(s["qtyMin"]))


def decide(lot: Lot, rules: Sequence[Rule] | None = None) -> Decision:
    """dDecide (2347): rules in order; a prefer rule wins when within 15% of the best score; rules that would leave no
    channel are waived. `rules` defaults to the published flow's rules."""
    values = [score(lot, k) for k in DCH]
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
