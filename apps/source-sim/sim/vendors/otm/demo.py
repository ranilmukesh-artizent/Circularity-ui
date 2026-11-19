"""The demo's logistics world (index.html: LOCS, LANE_KM, RATE_CARD, exInbound, afLease), shared by the OTM mock and
the Oracle Depot Repair mock. Copied from the retired generic ShipLane spec with the same values, so a lane, a freight
amount, a pickup date or an RMA reads the same in every system."""

import math
import re
from datetime import datetime, timedelta, timezone

from sim.seed.model import CaseFacts

FACILITY = {"Warehouse 1": "WH01", "Warehouse 2": "WH02", "Repair centre": "RC01"}  # Manhattan facility ids


def facility_id(location: str) -> str:
    return FACILITY.get(location) or "ST" + location.split()[-1].zfill(2)  # Site 3 -> ST03


FX = 83.5  # INR per USD, rate dated 2026-10-06 (EX_FX)
IST = timezone(timedelta(hours=5, minutes=30))


def jround(x: float) -> int:
    """JavaScript Math.round (half up), so derived numbers equal the demo's."""
    return math.floor(x + 0.5)


def hash_id(s: str) -> str:
    """The demo's hashId: FNV-1a 32-bit, upper-case hex."""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08X}"


def as_hex(case_id: str, k: str) -> int:
    return int(hash_id(case_id + k), 16)


def case_no(case_id: str) -> int:
    return int(case_id[3:])  # RT-1048 -> 1048


# ---------------------------------------------------------------- locations and lanes (LOCS, LANE_KM, RATE_CARD)
LOCS: dict[str, dict] = {
    "WH-PNQ-01": {"kind": "Warehouse", "name": "Warehouse 1", "city": "Pune (Chakan)", "lat": 18.76, "lon": 73.86},
    "WH-MAA-02": {"kind": "Warehouse", "name": "Warehouse 2", "city": "Chennai (Sriperumbudur)", "lat": 12.97, "lon": 79.95},
    "RC-HSR-01": {"kind": "Repair centre", "name": "Repair centre", "city": "Hosur", "lat": 12.74, "lon": 77.83},
    "LOC-PNQ-01": {
        "kind": "Customer site",
        "site": "Site 1",
        "name": "Pune Works",
        "city": "Pune (Pimpri)",
        "lat": 18.63,
        "lon": 73.80,
    },
    "LOC-HSR-02": {
        "kind": "Customer site",
        "site": "Site 2",
        "name": "Hosur Assembly",
        "city": "Hosur",
        "lat": 12.72,
        "lon": 77.81,
    },
    "LOC-CHN-03": {
        "kind": "Customer site",
        "site": "Site 3",
        "name": "Chennai Foundry",
        "city": "Chennai (Ambattur)",
        "lat": 13.10,
        "lon": 80.16,
    },
    "LOC-NSK-04": {
        "kind": "Customer site",
        "site": "Site 4",
        "name": "Nashik Plant",
        "city": "Nashik",
        "lat": 19.99,
        "lon": 73.79,
    },
    "LOC-VTZ-05": {
        "kind": "Customer site",
        "site": "Site 5",
        "name": "Vizag Port Yard",
        "city": "Visakhapatnam",
        "lat": 17.69,
        "lon": 83.22,
    },
    "LOC-CBE-06": {
        "kind": "Customer site",
        "site": "Site 6",
        "name": "Coimbatore Mill",
        "city": "Coimbatore",
        "lat": 11.02,
        "lon": 76.96,
    },
    "LOC-STV-07": {
        "kind": "Customer site",
        "site": "Site 7",
        "name": "Surat Textiles",
        "city": "Surat",
        "lat": 21.17,
        "lon": 72.83,
    },
    "LOC-IDR-08": {
        "kind": "Customer site",
        "site": "Site 8",
        "name": "Indore Packaging",
        "city": "Indore",
        "lat": 22.72,
        "lon": 75.86,
    },
    "EXT-BOM": {"kind": "Buyer hub", "name": "Dealer network hub", "city": "Mumbai (Bhiwandi)", "lat": 19.30, "lon": 73.06},
    "EXT-BLR": {"kind": "Buyer hub", "name": "Refurbisher auction hub", "city": "Bengaluru", "lat": 12.97, "lon": 77.59},
    "PTN-MAA": {"kind": "Partner", "name": "Certified recycler", "city": "Chennai (Gummidipoondi)", "lat": 13.40, "lon": 80.11},
}
FAC_LOC = {"Warehouse 1": "WH-PNQ-01", "Warehouse 2": "WH-MAA-02", "Repair centre": "RC-HSR-01"}
SITE_LOC = {v["site"]: k for k, v in LOCS.items() if "site" in v}
TENANT_SITES = {
    "Customer A": ["Site 1", "Site 3", "Site 2", "Site 4"],
    "Customer B": ["Site 6", "Site 7"],
    "Customer C": ["Site 8", "Site 5"],
}
LANE_KM = {
    ("WH-PNQ-01", "RC-HSR-01"): 930,
    ("RC-HSR-01", "WH-MAA-02"): 260,
    ("WH-MAA-02", "LOC-CHN-03"): 34,
    ("WH-PNQ-01", "LOC-CHN-03"): 1180,
}
RATE_CARD = {
    "id": "RC-2026.2",
    "carrier": "Northline 3PL",
    "contract": "NL-MSA-2025-11",
    "vehicle": "LCV 1.5 t with tail-lift",
    "perKm": 20,
    "load": 1200,
    "min": 3600,
    "ptl": [(100, 6), (500, 10), (math.inf, 16)],
    "docket": 350,
    "ptlMin": 450,
    "detFree": 120,
    "detUsd": 72,
}
CARRIERS = {  # SCAC -> name; Northline holds RC-2026.2, the other two run return pickups on the same card (afLease)
    "NLTL": "Northline 3PL",
    "VLFR": "Velo Freight",
    "CSHL": "Coastal Haulage",
}
SCAC = {v: k for k, v in CARRIERS.items()}


def loc_facility(code: str) -> str | None:
    """The Manhattan facility id of a location code (WH-PNQ-01 -> WH01, LOC-CHN-03 -> ST03); None for hubs/partners."""
    loc = LOCS[code]
    if "site" in loc:
        return facility_id(loc["site"])
    return facility_id(loc["name"]) if loc["kind"] in ("Warehouse", "Repair centre") else None


def lane_km(a: str, b: str) -> int:
    if a == b:
        return 0
    if (a, b) in LANE_KM or (b, a) in LANE_KM:
        return LANE_KM.get((a, b)) or LANE_KM[(b, a)]
    A, B, r = LOCS[a], LOCS[b], math.pi / 180
    x = (B["lon"] - A["lon"]) * r * math.cos((A["lat"] + B["lat"]) / 2 * r)
    y = (B["lat"] - A["lat"]) * r
    return max(5, jround(math.hypot(x, y) * 6371 * 1.25 / 5) * 5)


def lane_cost(a: str, b: str, kg: int) -> dict:
    """laneCost: a dedicated LCV from 150 kg, else part load by distance band; INR."""
    km, R = lane_km(a, b), RATE_CARD
    if kg >= 150:
        raw = km * R["perKm"] + R["load"]
        calc = (
            f"{km:,} km · minimum charge ₹{R['min']:,}"
            if raw < R["min"]
            else f"{km:,} km × ₹{R['perKm']} + ₹{R['load']:,} loading"
        )
        return {"km": km, "inr": max(R["min"], raw), "mode": "Dedicated " + R["vehicle"], "calc": calc}
    band = next(rate for limit, rate in R["ptl"] if km <= limit)
    raw = jround(kg * band) + R["docket"]
    calc = f"{kg} kg · minimum charge ₹{R['ptlMin']}" if raw < R["ptlMin"] else f"{kg} kg × ₹{band} + ₹{R['docket']} docket"
    return {"km": km, "inr": max(R["ptlMin"], raw), "mode": "Part load", "calc": calc}


def transit_h(km: float) -> float:
    return max(0.5, jround((km / 55 + 8 * math.floor(km / 600)) * 10) / 10)


def ex_kg(f: CaseFacts) -> int:
    m = re.match(r"\s*([\d.]+)", str(f.spec.get("Rated power", "")))
    kw = float(m.group(1)) if m else 22
    u = {"motor": 40 + 6 * kw, "pump": 95, "control": 18, "drill": 3.5, "batch": 3, "it": 2.4}.get(f.cls, 20)
    return jround(u * f.qty)


def resale_hub(f: CaseFacts) -> str:
    return "EXT-BLR" if f.cls in ("it", "control") else "EXT-BOM"


def inbound(f: CaseFacts) -> dict:
    """exInbound: the customer site the unit came back from to the facility that received it (a dedicated pickup)."""
    sites = TENANT_SITES.get(f.owner) or TENANT_SITES["Customer A"]
    frm = SITE_LOC[sites[case_no(f.id) % len(sites)]]
    to = FAC_LOC.get(f.location, "WH-PNQ-01")
    return {"from": frm, "to": to} | lane_cost(frm, to, max(150, ex_kg(f)))


def rma(f: CaseFacts) -> str:
    return f"RMA-{55800 + as_hex(f.id, 'rma') % 900}"


def return_logistics(f: CaseFacts) -> dict:
    """afLease, stages 1-3: lease end, return authorisation, pickup, carrier, arrival and inbound freight."""

    def h(k: str) -> int:
        return as_hex(f.id, "|af|" + k)

    rec = f.received
    end = rec - timedelta(days=16 + h("end") % 38)
    auth = end + timedelta(days=3 + h("ra") % 6)
    pickup = auth + timedelta(days=2 + h("pk") % 5)
    lane = inbound(f)
    return {
        "lease": f"LC-{4000 + h('lc') % 900}",
        "end": end,
        "intent": ["return at term", "return at term", "early return", "upgrade to a newer model"][h("in") % 4],
        "rma": rma(f),
        "auth": auth,
        "fee": f.qty * (0 if h("fee") % 3 else 40 + h("f2") % 8 * 10),
        "pickup": pickup,
        "eta": rec - timedelta(days=h("eta") % 2),
        "carrier": ["Northline 3PL", "Velo Freight", "Coastal Haulage"][h("cr") % 3],
        "freight_usd": jround(lane["inr"] / FX),
        "lane": lane,
    }


def demand_order(f: CaseFacts) -> str | None:
    """demandOrder: the OMS order line a redeployment fills."""
    if f.id == "RT-1048":
        return "SO-48102"
    return f"SO-{48000 + (case_no(f.id) * 7) % 997}" if f.demand.internal else None


def ist(d: datetime) -> str:
    return d.astimezone(IST).isoformat(timespec="seconds")


def at_ist(day: datetime, hour: float) -> datetime:
    """`day`'s calendar date at a local (IST) hour, as an aware datetime."""
    return datetime(day.year, day.month, day.day, tzinfo=IST) + timedelta(hours=hour)
