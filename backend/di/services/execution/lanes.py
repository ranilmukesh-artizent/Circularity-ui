"""Facilities, customer sites, lanes and the rate card (the demo's LOCS, laneCost, RATE_CARD, exStage, exMoveRaw).

Road distances come from di.repositories.common (LANE_KM pinned where measured, else straight line x 1.25, `_lane_km`), as do
the site and facility codes; this module adds what each location is and when it receives. The rate card lives in
Oracle Transportation Management.
"""

from typing import Any

from di.repositories.common import FAC_LOC, SITE_LOC, Case, _lane_km, case_demand, ex_hh, ex_num, inr
from di.repositories.common import LOCS as COORDS
from di.services.engine.jsmath import js_round
from di.services.execution.util import num_or, parse_float

EX_DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _loc(kind: str, name: str, city: str, days: list[int], hrs: tuple[int, int], **kw) -> dict[str, Any]:
    return {"kind": kind, "name": name, "city": city, "days": days, "hrs": hrs, **kw}


_WEEK, _MON_SAT, _MON_FRI = [0, 1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5]
# What each location is and its receiving days (0 = Sunday) and hours; coordinates are in di.repositories.common.LOCS
LOCS: dict[str, dict[str, Any]] = {
    "WH-PNQ-01": _loc("Warehouse", "Warehouse 1", "Pune (Chakan)", _MON_SAT, (7, 19), bin="A-12-03", bay="S-02"),
    "WH-MAA-02": _loc("Warehouse", "Warehouse 2", "Chennai (Sriperumbudur)", _MON_SAT, (7, 19), bin="B-04-11", bay="S-04"),
    "RC-HSR-01": _loc("Repair centre", "Repair centre", "Hosur", _WEEK, (6, 22), bin="R-01-02", bay="D-01"),
    "LOC-PNQ-01": _loc("Customer site", "Pune Works", "Pune (Pimpri)", _MON_FRI, (9, 17), site="Site 1"),
    "LOC-HSR-02": _loc("Customer site", "Hosur Assembly", "Hosur", [1, 3, 5], (8, 13), site="Site 2"),
    "LOC-CHN-03": _loc("Customer site", "Chennai Foundry", "Chennai (Ambattur)", [2, 4, 6], (8, 12), site="Site 3"),
    "LOC-NSK-04": _loc("Customer site", "Nashik Plant", "Nashik", _MON_FRI, (9, 17), site="Site 4"),
    "LOC-VTZ-05": _loc("Customer site", "Vizag Port Yard", "Visakhapatnam", _MON_SAT, (6, 18), site="Site 5"),
    "LOC-CBE-06": _loc("Customer site", "Coimbatore Mill", "Coimbatore", [1, 3, 5], (8, 14), site="Site 6"),
    "LOC-STV-07": _loc("Customer site", "Surat Textiles", "Surat", _MON_FRI, (9, 17), site="Site 7"),
    "LOC-IDR-08": _loc("Customer site", "Indore Packaging", "Indore", [2, 4], (10, 16), site="Site 8"),
    "EXT-BOM": _loc("Buyer hub", "Dealer network hub", "Mumbai (Bhiwandi)", _MON_SAT, (9, 18)),
    "EXT-BLR": _loc("Buyer hub", "Refurbisher auction hub", "Bengaluru", _MON_SAT, (9, 18)),
    "PTN-MAA": _loc("Partner", "Certified recycler", "Chennai (Gummidipoondi)", _MON_SAT, (8, 17)),
}
assert LOCS.keys() == COORDS.keys()  # noqa: S101 - import-time check: one list of locations, two tables

# Rate card RC-2026.2 (K7): dedicated vehicle from 150 kg, part load below by distance band
RATE_CARD: dict[str, Any] = {
    "id": "RC-2026.2", "carrier": "Northline 3PL", "contract": "NL-MSA-2025-11", "vehicle": "LCV 1.5 t with tail-lift",
    "perKm": 20, "load": 1200, "min": 3600, "ptl": [(100, 6), (500, 10), (float("inf"), 16)], "docket": 350, "ptlMin": 450,
    "detFree": 120, "detUsd": 72,
}  # fmt: skip
RC = "RC-HSR-01"


def lane_km(a: str, b: str) -> int:
    return _lane_km(a, b)


def loc_name(k: str | None) -> str:
    """The demo's locName: "Chennai Foundry (Site 3)", "Warehouse 2 · Chennai (Sriperumbudur)"."""
    L = LOCS.get(k) if k is not None else None
    if not L:
        return str(k)
    return f"{L['name']} ({L['site']})" if L.get("site") else f"{L['name']} · {L['city']}"


def loc_win(k: str) -> str:
    """The demo's locWin: the receiving window, "Tue/Thu/Sat 08:00–12:00"."""
    L = LOCS[k]
    d = L["days"]
    run = len(d) > 2 and d[-1] - d[0] == len(d) - 1
    days = "Every day" if len(d) == 7 else f"{EX_DOW[d[0]]}–{EX_DOW[d[-1]]}" if run else "/".join(EX_DOW[x] for x in d)
    return f"{days} {ex_hh(L['hrs'][0])}–{ex_hh(L['hrs'][1])}"


def lane_cost(a: str, b: str, kg: int) -> dict:
    """The demo's laneCost: a leg's distance and freight on the rate card."""
    km, R = lane_km(a, b), RATE_CARD
    if kg >= 150:
        raw = km * R["perKm"] + R["load"]
        calc = (
            f"{ex_num(km)} km · minimum charge {inr(R['min'])}"
            if raw < R["min"]
            else f"{ex_num(km)} km × ₹{R['perKm']} + {inr(R['load'])} loading"
        )
        return {"km": km, "inr": max(R["min"], raw), "mode": "Dedicated " + R["vehicle"], "calc": calc}
    band = next(x[1] for x in R["ptl"] if km <= x[0])
    raw = js_round(kg * band) + R["docket"]
    calc = (
        f"{kg} kg · minimum charge {inr(R['ptlMin'])}" if raw < R["ptlMin"] else f"{kg} kg × ₹{band} + {inr(R['docket'])} docket"
    )
    return {"km": km, "inr": max(R["ptlMin"], raw), "mode": "Part load", "calc": calc}


def transit_h(km: int) -> float:
    """The demo's transitH: driving hours at 55 km/h, plus an 8-hour rest per 600 km."""
    return max(0.5, js_round((km / 55 + 8 * (km // 600)) * 10) / 10)


def ex_kg(c: Case) -> int:
    """The demo's exKg: the shipping weight."""
    kw = num_or(parse_float((c.get("spec") or {}).get("Rated power")), 22)
    u = {"motor": 40 + 6 * kw, "pump": 95, "control": 18, "drill": 3.5, "batch": 3, "it": 2.4}.get(c["cls"]) or 20
    return js_round(u * c["qty"])


def ex_stage(to: str) -> dict:
    """The demo's exStage (K5): stage at the warehouse nearest the ship-to; a site nearer the Repair centre than any
    warehouse is delivered direct."""
    ws: list[dict[str, Any]] = sorted(
        ({"k": k, "km": lane_km(k, to)} for k, L in LOCS.items() if L["kind"] == "Warehouse"), key=lambda x: x["km"]
    )
    rc, w = lane_km(RC, to), ws[0]
    if rc < w["km"]:
        why = (
            f"Delivered direct from {RC}: {ex_num(rc)} km to {to}, nearer than any warehouse "
            f"({w['k']} is {ex_num(w['km'])} km)"
        )
        return {"code": None, "km": rc, "why": why}
    others = ", ".join(f"{x['k']} is {ex_num(x['km'])} km" for x in ws[1:])
    why = (
        f"{w['k']} is {ex_num(w['km'])} km from {to}; {others}. It has an inbound slot and meets the site's "
        f"{loc_win(to)} window"
    )
    return {"code": w["k"], "km": w["km"], "why": why}


def ex_move_raw(c: Case, r: dict) -> dict | None:
    """The demo's exMoveRaw: the stops and priced legs of a route, without the repair timing (so legs can be priced
    before the labour hours are known)."""
    M = case_demand(c)
    src = FAC_LOC.get(c["location"]) or "WH-PNQ-01"
    kg = ex_kg(c)
    hub = "EXT-BLR" if c["cls"] in ("it", "control") else "EXT-BOM"
    rid = r.get("id")
    if rid == "redeploy":
        site: Any = (c.get("demand") or {}).get("site")
        to = (M and M.get("shipTo")) or SITE_LOC.get(site) or "LOC-HSR-02"
        st = ex_stage(to)
        stops = [src, RC, *([st["code"]] if st["code"] else []), to]
    elif rid == "relase":
        stops = [src, RC, "WH-MAA-02" if src == RC else src]
    elif rid == "resale":
        stops = [src, RC, hub] if r.get("variant") == "refurb" else [src, hub]
    elif rid == "intparts":
        stops = [src, RC]
    elif rid == "extparts":
        stops = [src, RC, hub]
    elif rid in ("material", "exit"):
        stops = [src, "PTN-MAA"]
    else:
        return None
    stops = [s for i, s in enumerate(stops) if i == 0 or s != stops[i - 1]]
    legs = [{"n": i + 1, "from": stops[i], "to": b, **lane_cost(stops[i], b, kg)} for i, b in enumerate(stops[1:])]
    return {"stops": stops, "legs": legs}


def ex_move_legs_for(c: Case, r: dict) -> list[dict]:
    """The demo's exMoveLegsFor: the legs a refurbishment pays for (for a resale, only the leg to the Repair centre)."""
    m = ex_move_raw(c, r)
    if not m:
        return []
    return [x for x in m["legs"] if x["to"] == RC] if r.get("id") == "resale" else m["legs"]
