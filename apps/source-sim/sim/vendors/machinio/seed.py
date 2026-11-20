"""Machinio: tables (Postgres schema `machinio`) and the seed (docs/BACKEND_STEPS.md, B5b).

Tables
    listings          the seller account's own inventory (Machinio System): one per case with a resale route,
                      stock_number = the asset id. Active for an as-is sale; a draft (to be published after the
                      refurbishment) when the only resale route is refurbish-then-sell.
    similar_listings  other dealers' active listings Machinio matches to one of ours (same make, model, category):
                      listing demand and time to sale. At the case's condition for the as-is route, one grade up for
                      refurbish-then-sell (RT-1049: "Grade A listings: 14 open").
    offers            offers received on our listings (as-is routes): RT-1048 MO-91048 $5,600; firm where the demo's
                      term is a dealer or lot offer (RT-1033 "Offer from dealer" $460, RT-1052 "Lot proceeds
                      (20 x $128)"). Fees split the route's "Fees and freight" term as the demo's cost trace does:
                      freight on rate card RC-2026.2 from the holding facility to the buyer hub (capped at 70%), the
                      rest the channel fee. Valid 14 days from when they were made.

Values are the B5 generic mock's (sim/generic/specs/machinio.py), reshaped; the lane helpers are copied from the
ShipLane spec so this package does not depend on it.
"""

import math
import re
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts, RouteFacts

FX = 83.5  # INR per USD (EX_FX, dated 2026-10-06)
ACCOUNT = {
    "id": "acct_7Q2M4K",
    "company": "Northfield India Remarketing (Circularity)",
    "plan": "Machinio System",
    "country": "IN",
    "currency": "USD",
    "time_zone": "Asia/Kolkata",
}
DEALERS = [
    ("dlr_10412", "Western Plant Traders", "sales@westernplant.example"),
    ("dlr_10877", "Deccan Machinery Exchange", "offers@deccanmx.example"),
    ("dlr_11203", "Coromandel Used Equipment", "trade@coromandel-ue.example"),
    ("dlr_11590", "Bharat Industrial Resale", "buy@bharatresale.example"),
    ("dlr_12044", "Konkan Tools & Drives", "desk@konkantools.example"),
]
CONDITION = {"A": "Excellent", "B": "Very good", "C": "Good", "D": "Fair"}
GRADE_UP = {"A": "A", "B": "A", "C": "B", "D": "C"}
OFFER_DAYS = 14  # validity window of an offer

# --------------------------------------------------------------- lanes (copied from the ShipLane spec: LOCS, RC-2026.2)
LOCS = {
    "WH-PNQ-01": (18.76, 73.86, "Pune (Chakan)"),
    "WH-MAA-02": (12.97, 79.95, "Chennai (Sriperumbudur)"),
    "RC-HSR-01": (12.74, 77.83, "Hosur"),
    "EXT-BOM": (19.30, 73.06, "Mumbai (Bhiwandi)"),
    "EXT-BLR": (12.97, 77.59, "Bengaluru"),
}
FAC_LOC = {"Warehouse 1": "WH-PNQ-01", "Warehouse 2": "WH-MAA-02", "Repair centre": "RC-HSR-01"}
LANE_KM = {("WH-PNQ-01", "RC-HSR-01"): 930, ("RC-HSR-01", "WH-MAA-02"): 260}
RATE = {"perKm": 20, "load": 1200, "min": 3600, "ptl": [(100, 6), (500, 10), (math.inf, 16)], "docket": 350, "ptlMin": 450}


def jround(x: float) -> int:
    return math.floor(x + 0.5)


def as_hex(case_id: str, k: str) -> int:
    h = 2166136261
    for ch in case_id + k:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def case_no(case_id: str) -> int:
    return int(case_id[3:])


def lane_km(a: str, b: str) -> int:
    if a == b:
        return 0
    if (a, b) in LANE_KM or (b, a) in LANE_KM:
        return LANE_KM.get((a, b)) or LANE_KM[(b, a)]
    (la, oa, _), (lb, ob, _), r = LOCS[a], LOCS[b], math.pi / 180
    x = (ob - oa) * r * math.cos((la + lb) / 2 * r)
    y = (lb - la) * r
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


def resale_hub(f: CaseFacts) -> str:
    return "EXT-BLR" if f.cls in ("it", "control") else "EXT-BOM"


def fee_split(f: CaseFacts, r: RouteFacts) -> dict:
    """The demo's exTrace for a resale 'Fees and freight' term: freight legs on RC-2026.2, the rest channel fees (INR)."""
    fees = next((t for t in r.terms if t.kind == "fees"), None)
    if fees is None:
        return {"total_inr": 0, "freight_inr": 0, "channel_inr": 0, "lanes": []}
    src, rc, hub, kg = FAC_LOC.get(f.location, "WH-PNQ-01"), "RC-HSR-01", resale_hub(f), ex_kg(f)
    stops = [src, rc, hub] if r.variant == "refurb" else [src, hub]
    stops = [x for i, x in enumerate(stops) if i == 0 or x != stops[i - 1]]
    legs = [(a, b) for a, b in pairwise(stops) if a == rc or rc not in stops]
    total = jround(abs(fees.amt) * FX)
    freight = [lane_inr(a, b, kg) for a, b in legs]
    fr, cap = sum(freight), jround(total * 0.7)
    s = cap / fr if fr > cap and fr else 1
    freight_inr = sum(jround(x * s / 10) * 10 for x in freight)
    return {
        "total_inr": total,
        "freight_inr": freight_inr,
        "channel_inr": total - freight_inr,
        "lanes": [f"{a}>{b}" for a, b in legs],
    }


def model_of(f: CaseFacts) -> str:
    return " ".join(str(v) for v in list(f.spec.values())[:2])


def _z(d: datetime) -> str:
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sale(r: RouteFacts):
    return next((t for t in r.terms if t.kind == "sale" and t.amt > 0), None)


# --------------------------------------------------------------- tables
md = MetaData(schema="machinio")
LISTINGS = Table(
    "listings",
    md,
    Column("listing_id", String(30), primary_key=True),
    Column("stock_number", String(30), nullable=False, index=True),
    Column("status", String(20), nullable=False),  # draft, active, pending_sale, sold, withdrawn
    Column("listed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
)
SIMILAR = Table(
    "similar_listings",
    md,
    Column("listing_id", String(30), primary_key=True),
    Column("similar_to", String(30), nullable=False, index=True),
    Column("status", String(20), nullable=False),
    Column("condition", String(20), nullable=False),
    Column("listed_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
)
OFFERS = Table(
    "offers",
    md,
    Column("offer_id", String(30), primary_key=True),
    Column("listing_id", String(30), nullable=False, index=True),
    Column("status", String(20), nullable=False),  # open, countered, accepted, declined, expired
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("doc", JSONB, nullable=False),
)


# --------------------------------------------------------------- seed
def _own_listing(f: CaseFacts, r: RouteFacts, as_of: datetime, draft: bool) -> dict:
    sale = _sale(r)
    grade = GRADE_UP[f.grade] if draft else f.grade
    h = as_hex(f.id, "|dlr|own")
    listed = None if draft else as_of - timedelta(days=2 + h % 10, hours=h % 9)
    created = (listed or as_of - timedelta(days=1)) - timedelta(hours=3)
    lid = f"ML-{90000 + case_no(f.id)}-01"
    return {
        "id": lid,
        "stock_number": f.asset_id,
        "title": f"{f.mfr} {f.product} · " + " · ".join(str(v) for v in list(f.spec.values())[:2]),
        "category": f.product,
        "make": f.mfr,
        "model": model_of(f),
        "year": 2026 - int(f.age),
        "quantity": f.qty,
        "condition": CONDITION[grade],
        "price": {
            "amount": float(jround(sale.amt * 1.08 / (10 if sale.amt >= 1000 else 1)) * (10 if sale.amt >= 1000 else 1)),
            "currency": "USD",
        },
        "location": {"city": LOCS[resale_hub(f)][2], "country": "IN"},
        "status": "draft" if draft else "active",
        "listing_fee": {"amount": 25.0 if sale.amt < 1000 else 75.0, "currency": "USD"},
        "views": 0 if draft else 60 + h % 300,
        "inquiries_count": 0 if draft else 1 + (h >> 8) % 6,
        "url": f"https://www.machinio.com/listings/{90000 + case_no(f.id)}01",
        "listed_at": _z(listed) if listed else None,
        "created_at": _z(created),
        "updated_at": _z(listed or created),
    }


def _similar(f: CaseFacts, r: RouteFacts, as_of: datetime, own_id: str) -> list[dict]:
    sale = _sale(r)
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
        listed = as_of - timedelta(days=3 + h % 45)
        dealer = DEALERS[(h >> 4) % len(DEALERS)]
        out.append(
            {
                "id": f"ML-{90000 + case_no(f.id)}-{tag}{i + 1:02d}",
                "similar_to": own_id,
                "title": f"{f.mfr} {f.product} · " + " · ".join(str(v) for v in list(f.spec.values())[:2]),
                "category": f.product,
                "make": f.mfr,
                "model": model_of(f),
                "year": 2026 - int(max(0.5, f.age + ((h >> 8) % 21 - 10) / 10)),
                "condition": CONDITION[grade],
                "price": {"amount": float(jround(sale.amt * (1.04 + (h % 17) / 100) / step) * step), "currency": "USD"},
                "dealer": {"id": dealer[0], "name": dealer[1]},
                "location": {"city": LOCS[resale_hub(f)][2], "country": "IN"},
                "views": 40 + (h >> 8) % 400,
                "inquiries_count": (h >> 12) % 9,
                "status": "active",
                "listed_at": _z(listed),
                "updated_at": _z(listed),
            }
        )
    return out


def _offer(f: CaseFacts, r: RouteFacts, as_of: datetime, listing_id: str) -> dict:
    sale = _sale(r)
    split = fee_split(f, r)
    h = as_hex(f.id, "|dlr|o")
    lot = re.search(r"\((\d+) × \$([\d,]+)\)", sale.label)
    firm = sale.label.startswith("Offer from dealer") or sale.label.startswith("Lot proceeds")
    made = as_of - timedelta(days=1 + h % 9, hours=h % 7)
    dealer = DEALERS[h % len(DEALERS)]
    return {
        "id": f"MO-{90000 + case_no(f.id)}",
        "listing_id": listing_id,
        "stock_number": f.asset_id,
        "dealer_id": dealer[0],
        "dealer_name": dealer[1],
        "dealer_contact": dealer[2],
        "offer_type": "lot" if f.qty > 1 or lot else "single",
        "offer_kind": "firm" if firm else "indicative",
        "quantity": int(lot.group(1)) if lot else f.qty,
        "unit_amount": float(lot.group(2).replace(",", "")) if lot else None,
        "offer_amount": float(sale.amt),
        "offer_currency": "USD",
        "condition_basis": CONDITION.get(f.grade or "", "As is"),
        "fees": {
            "total_usd": round(split["total_inr"] / FX, 2),
            "freight_inr": split["freight_inr"],
            "freight_lanes": split["lanes"],
            "channel_fee_inr": split["channel_inr"],
            "commission_pct": round(split["channel_inr"] / (sale.amt * FX) * 100, 1) if sale.amt else None,
        },
        "estimated_days_to_sale": 6 + h % 30,
        "pickup_location": LOCS[resale_hub(f)][2],
        "status": "open",
        "counter_amount": None,
        "created_at": _z(made),
        "expires_at": _z(made + timedelta(days=OFFER_DAYS)),
        "responded_at": None,
        "updated_at": _z(made),
    }


def build(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    listings, similar, offers = [], [], []
    for case in s.cases.values():
        f = case.facts
        routes = [r for r in f.routes if r.id == "resale" and _sale(r) and f.grade]
        if not routes:
            continue
        asis = next((r for r in routes if r.variant != "refurb"), None)
        own = _own_listing(f, asis or routes[0], as_of, draft=asis is None)
        listings.append(own)
        for r in routes:
            similar += _similar(f, r, as_of, own["id"])
        if asis:
            offers.append(_offer(f, asis, as_of, own["id"]))
    return {"listings": listings, "similar_listings": similar, "offers": offers}


def _ts(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def create(conn: Connection) -> None:
    conn.execute(text('CREATE SCHEMA IF NOT EXISTS "machinio"'))
    md.create_all(conn)


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    d = build(seed)
    conn.execute(
        insert(LISTINGS),
        [
            {
                "listing_id": x["id"],
                "stock_number": x["stock_number"],
                "status": x["status"],
                "listed_at": _ts(x["listed_at"]),
                "updated_at": _ts(x["updated_at"]),
                "doc": x,
            }
            for x in d["listings"]
        ],
    )
    conn.execute(
        insert(SIMILAR),
        [
            {
                "listing_id": x["id"],
                "similar_to": x["similar_to"],
                "status": x["status"],
                "condition": x["condition"],
                "listed_at": _ts(x["listed_at"]),
                "updated_at": _ts(x["updated_at"]),
                "doc": x,
            }
            for x in d["similar_listings"]
        ],
    )
    conn.execute(
        insert(OFFERS),
        [
            {
                "offer_id": x["id"],
                "listing_id": x["listing_id"],
                "status": x["status"],
                "expires_at": _ts(x["expires_at"]),
                "updated_at": _ts(x["updated_at"]),
                "doc": x,
            }
            for x in d["offers"]
        ],
    )
    return {k: len(v) for k, v in d.items()}


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    conn.execute(text('DROP TABLE IF EXISTS "machinio".docs, "machinio".counters'))  # the B5 generic mock's tables
    md.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(select(LISTINGS.c.listing_id).limit(1)).first() is None:
        load(conn, seed)
