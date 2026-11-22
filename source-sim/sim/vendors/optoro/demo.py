"""The demo's return-logistics numbers (index.html afLease / exInbound), copied from the retired ShipLane generic spec
so the Optoro mock keeps the same RMA, pickup, carrier, lane and freight per case while ShipLane is replaced by OTM.
Every value here equals the old sim/generic/specs/shiplane.py helpers (same hashes, same rounding)."""

import math
import re
from datetime import timedelta

from sim.seed.model import CaseFacts
from sim.vendors.manhattan.seed import facility_id  # noqa: F401 - re-exported for the Optoro seed

FX = 83.5  # INR per USD, rate dated 2026-10-06


def jround(x: float) -> int:
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
    return int(case_id[3:])


LOCS: dict[str, dict] = {
    "WH-PNQ-01": {"kind": "Warehouse", "name": "Warehouse 1", "lat": 18.76, "lon": 73.86},
    "WH-MAA-02": {"kind": "Warehouse", "name": "Warehouse 2", "lat": 12.97, "lon": 79.95},
    "RC-HSR-01": {"kind": "Repair centre", "name": "Repair centre", "lat": 12.74, "lon": 77.83},
    "LOC-PNQ-01": {"kind": "Customer site", "site": "Site 1", "name": "Pune Works", "lat": 18.63, "lon": 73.80},
    "LOC-HSR-02": {"kind": "Customer site", "site": "Site 2", "name": "Hosur Assembly", "lat": 12.72, "lon": 77.81},
    "LOC-CHN-03": {"kind": "Customer site", "site": "Site 3", "name": "Chennai Foundry", "lat": 13.10, "lon": 80.16},
    "LOC-NSK-04": {"kind": "Customer site", "site": "Site 4", "name": "Nashik Plant", "lat": 19.99, "lon": 73.79},
    "LOC-VTZ-05": {"kind": "Customer site", "site": "Site 5", "name": "Vizag Port Yard", "lat": 17.69, "lon": 83.22},
    "LOC-CBE-06": {"kind": "Customer site", "site": "Site 6", "name": "Coimbatore Mill", "lat": 11.02, "lon": 76.96},
    "LOC-STV-07": {"kind": "Customer site", "site": "Site 7", "name": "Surat Textiles", "lat": 21.17, "lon": 72.83},
    "LOC-IDR-08": {"kind": "Customer site", "site": "Site 8", "name": "Indore Packaging", "lat": 22.72, "lon": 75.86},
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
RATE = {"perKm": 20, "load": 1200, "min": 3600, "ptl": [(100, 6), (500, 10), (math.inf, 16)], "docket": 350, "ptlMin": 450}
SCAC = {"Northline 3PL": "NLTL", "Velo Freight": "VLFR", "Coastal Haulage": "CSHL"}


def lane_km(a: str, b: str) -> int:
    if a == b:
        return 0
    if (a, b) in LANE_KM or (b, a) in LANE_KM:
        return LANE_KM.get((a, b)) or LANE_KM[(b, a)]
    A, B, r = LOCS[a], LOCS[b], math.pi / 180
    x = (B["lon"] - A["lon"]) * r * math.cos((A["lat"] + B["lat"]) / 2 * r)
    y = (B["lat"] - A["lat"]) * r
    return max(5, jround(math.hypot(x, y) * 6371 * 1.25 / 5) * 5)


def lane_inr(a: str, b: str, kg: int) -> int:
    km = lane_km(a, b)
    if kg >= 150:
        return max(RATE["min"], km * RATE["perKm"] + RATE["load"])
    band = next(rate for limit, rate in RATE["ptl"] if km <= limit)
    return max(RATE["ptlMin"], jround(kg * band) + RATE["docket"])


def ex_kg(f: CaseFacts) -> int:
    m = re.match(r"\s*([\d.]+)", str(f.spec.get("Rated power", "")))
    kw = float(m.group(1)) if m else 22
    u = {"motor": 40 + 6 * kw, "pump": 95, "control": 18, "drill": 3.5, "batch": 3, "it": 2.4}.get(f.cls, 20)
    return jround(u * f.qty)


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
    sites = TENANT_SITES.get(f.owner) or TENANT_SITES["Customer A"]
    frm = SITE_LOC[sites[case_no(f.id) % len(sites)]]
    to = FAC_LOC.get(f.location, "WH-PNQ-01")
    inr = lane_inr(frm, to, max(150, ex_kg(f)))
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
        "freight_usd": jround(inr / FX),
        "lane": {"from": frm, "to": to, "inr": inr},
    }


def demand_order(f: CaseFacts) -> str | None:
    if f.id == "RT-1048":
        return "SO-48102"
    return f"SO-{48000 + (case_no(f.id) * 7) % 997}" if f.demand.internal else None


def load_id(f: CaseFacts) -> str:
    return f"LD-{20000 + case_no(f.id)}"
