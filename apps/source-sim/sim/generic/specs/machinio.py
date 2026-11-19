"""Machinio (the demo's SOURCES.dlr): dealer offers, listing demand, fees, time-to-sale.
Read: GET /listings, /offers. Read only.

Per case with a resale route:
- offers: one dealer offer for the as-is sale at the route's sale proceeds (a firm offer or lot offer where the demo's
  term says so, e.g. RT-1033 "Offer from dealer" $460, RT-1052 "Lot proceeds (20 x $128)"). Its fees split the
  route's "Fees and freight" term the way the demo's cost trace does: freight on the ShipLane RC-2026.2 lane from
  the holding facility (or the repair centre) to the buyer hub, capped at 70%, and the rest as the channel fee.
- listings: open dealer listings for comparable units (listing demand and time-to-sale), at the case's grade for the
  as-is route and one grade up for refurbish-then-sell (RT-1049: "Grade A listings: 14 open").
"""

import re
from datetime import timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.ritchie import GRADE_UP
from sim.generic.specs.shiplane import FAC_LOC, FX, LOCS, as_hex, case_no, ex_kg, jround, lane_cost, resale_hub
from sim.seed import Seed
from sim.seed.model import CaseFacts, RouteFacts

DEALERS = [
    "Western Plant Traders",
    "Deccan Machinery Exchange",
    "Coromandel Used Equipment",
    "Bharat Industrial Resale",
    "Konkan Tools & Drives",
]
CONDITION = {"A": "Excellent", "B": "Very good", "C": "Good", "D": "Fair"}


def fee_split(f: CaseFacts, r: RouteFacts) -> dict | None:
    """The demo's exTrace for a resale 'Fees and freight' term: freight legs on RC-2026.2, the rest channel fees (INR)."""
    fees = next((t for t in r.terms if t.kind == "fees"), None)
    if fees is None:
        return None
    src, rc, hub, kg = FAC_LOC.get(f.location, "WH-PNQ-01"), "RC-HSR-01", resale_hub(f), ex_kg(f)
    stops = [src, rc, hub] if r.variant == "refurb" else [src, hub]
    stops = [x for i, x in enumerate(stops) if i == 0 or x != stops[i - 1]]
    legs = [(a, b) for a, b in zip(stops, stops[1:], strict=False) if a == rc or rc not in stops]
    total = jround(abs(fees.amt) * FX)
    freight = [lane_cost(a, b, kg)["inr"] for a, b in legs]
    fr, cap = sum(freight), jround(total * 0.7)
    s = cap / fr if fr > cap and fr else 1
    freight_inr = sum(jround(x * s / 10) * 10 for x in freight)
    return {
        "total_inr": total,
        "freight_inr": freight_inr,
        "channel_inr": total - freight_inr,
        "lanes": [f"{a}>{b}" for a, b in legs],
    }


def _offer(f: CaseFacts, r: RouteFacts, as_of) -> dict | None:
    sale = next((t for t in r.terms if t.kind == "sale" and t.amt > 0), None)
    if sale is None:
        return None
    split = fee_split(f, r) or {"total_inr": 0, "freight_inr": 0, "channel_inr": 0, "lanes": []}
    h = as_hex(f.id, "|dlr|o")
    lot = re.search(r"\((\d+) × \$([\d,]+)\)", sale.label)
    firm = sale.label.startswith("Offer from dealer") or sale.label.startswith("Lot proceeds")
    made = as_of - timedelta(days=1 + h % 9, hours=h % 7)
    return {
        "offer_id": f"MO-{90000 + case_no(f.id)}",
        "asset_ref": f.asset_id,
        "listing_ref": f"ML-{90000 + case_no(f.id)}-01",
        "dealer_name": DEALERS[h % len(DEALERS)],
        "offer_type": "lot" if f.qty > 1 or lot else "single",
        "quantity": int(lot.group(1)) if lot else f.qty,
        "unit_amount": float(lot.group(2).replace(",", "")) if lot else None,
        "offer_amount": float(sale.amt),
        "currency": "USD",
        "status": "firm" if firm else "indicative",
        "condition_basis": CONDITION.get(f.grade or "", "As is"),
        "fees": {
            "total_usd": round(split["total_inr"] / FX, 2),
            "freight_inr": split["freight_inr"],
            "freight_lanes": split["lanes"],
            "channel_fee_inr": split["channel_inr"],
            "commission_pct": round(split["channel_inr"] / (sale.amt * FX) * 100, 1) if sale.amt else None,
        },
        "estimated_days_to_sale": 6 + h % 30,
        "pickup_hub": LOCS[resale_hub(f)]["city"],
        "created_at": made.isoformat(),
        "expires_at": (made + timedelta(days=14)).isoformat(),
    }


def _listings(f: CaseFacts, r: RouteFacts, as_of) -> list[dict]:
    sale = next((t for t in r.terms if t.kind == "sale" and t.amt > 0), None)
    if sale is None or not f.grade:
        return []
    refurb = r.variant == "refurb"
    n = 3 + as_hex(f.id, "|dlr|n") % 3
    for note in r.gate_notes:
        m = re.search(r"Grade [A-D] listings: (\d+) open", note)
        if m:
            n = int(m.group(1))
    grade = GRADE_UP[f.grade] if refurb else f.grade
    tag = "R" if refurb else "L"
    step = 10 if sale.amt >= 1000 else 1
    out = []
    for i in range(n):
        h = as_hex(f.id, f"|dlr|{tag}|{i}")
        age_days = 3 + h % 45
        out.append(
            {
                "listing_id": f"ML-{90000 + case_no(f.id)}-{tag}{i + 1:02d}",
                "subject_asset": f.asset_id,
                "title": f"{f.mfr} {f.product} · " + " · ".join(str(v) for v in list(f.spec.values())[:2]),
                "category": f.cls,
                "make": f.mfr,
                "condition": CONDITION[grade],
                "grade": grade,
                "asking_price": float(jround(sale.amt * (1.04 + (h % 17) / 100) / step) * step),
                "currency": "USD",
                "dealer_name": DEALERS[(h >> 4) % len(DEALERS)],
                "location": LOCS[resale_hub(f)]["city"],
                "listing_age_days": age_days,
                "views": 40 + (h >> 8) % 400,
                "enquiries": (h >> 12) % 9,
                "status": "active",
                "listed_at": (as_of - timedelta(days=age_days)).date().isoformat(),
                "listing_fee_usd": 25.0 if sale.amt < 1000 else 75.0,
            }
        )
    return out


def seed(s: Seed) -> dict[str, list[dict]]:
    listings, offers = [], []
    as_of = s.world.as_of
    for case in s.cases.values():
        f = case.facts
        for r in f.routes:
            if r.id != "resale":
                continue
            listings += _listings(f, r, as_of)
            if r.variant != "refurb":
                o = _offer(f, r, as_of)
                if o:
                    offers.append(o)
    return {"listings": listings, "offers": offers}


SPEC = Spec(
    source_id="dlr",
    title="Machinio",
    schema="machinio",
    base_path="/machinio/v1",
    auth=Auth("api_key", header="X-Api-Key"),
    paging=Paging("page", page_param="page", size_param="per_page", items_key="data", next_key="next_page", total_key="total"),
    resources=(
        Resource("listings", "/listings", "listing_id", filters=("subject_asset", "category", "make", "condition", "status")),
        Resource("offers", "/offers", "offer_id", filters=("asset_ref", "dealer_name", "status", "offer_type")),
    ),
    seed=seed,
)
