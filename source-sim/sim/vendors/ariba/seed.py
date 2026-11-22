"""Load the seed (B2) into the Ariba tables.

What Ariba owns here (the demo's SOURCES.proc: "purchase alternatives, supplier quotes, lead times, sourcing events"):
- suppliers:  every manufacturer in the asset classes, linked to the S/4 supplier of the same name (LFA1)
- events:     one RFQ per planned purchase in S/4 (the cost of buying new instead of reusing), in EUR
- bids:       three quotes per event, from the class's manufacturers. The best is 0.942 × the purchase baseline in
              EUR, so RT-1048 gets the demo's mapping example: QuotedUnitPrice €10,400.00 → $11,300 at 0.92 EUR/USD,
              SupplierLeadTime 21 days, SupplierId SUP-88120
- POs:        the draft purchase order (Composing) behind each planned purchase, linked to the S/4 number
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.ariba import models as t
from sim.vendors.s4.seed import location_plant, site_plant, supplier_ids

EUR_PER_USD = Decimal("0.92")  # the demo's RG_CUR: EUR 0.92
QUOTE_FACTORS = (Decimal("0.942"), Decimal("0.975"), Decimal("1.010"))  # best, second, third quote vs the baseline
LEAD_TIMES = (21, 28, 35)
ANCHOR = ("Voltara", 88120)  # the demo's example supplier id


def sm_vendor_ids(seed: Seed) -> dict[str, str]:
    names = sorted({m for c in seed.world.classes.values() for m in c.mfr})
    base = ANCHOR[1] - 10 * names.index(ANCHOR[0])
    return {n: f"SUP-{base + 10 * i}" for i, n in enumerate(names)}


def _eur(usd: float, factor: Decimal) -> Decimal:
    return (Decimal(str(usd)) * EUR_PER_USD * factor).quantize(Decimal("1"), ROUND_HALF_UP).quantize(Decimal("0.01"))


def planned_purchases(seed: Seed):
    """(case, unit purchase price in USD, S/4 PO number, plant): the same rule as sim/vendors/s4/seed.py."""
    for case in seed.cases.values():
        f = case.facts
        purchase = max((term.amt for r in f.routes for term in r.terms if term.kind == "purchase"), default=0)
        if purchase > 0 and f.demand.internal:
            plant = site_plant(f.demand.site) if f.demand.site else location_plant(f.location)
            yield case, purchase / f.qty, str(48000 + int(f.id.split("-")[1])), plant


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    w = seed.world
    at = w.as_of - timedelta(days=1)
    sm = sm_vendor_ids(seed)
    erp = supplier_ids(seed)
    category = {m: c.plural for c in w.classes.values() for m in c.mfr}
    suppliers = [
        {
            "sm_vendor_id": sm[n],
            "erp_vendor_id": erp[n],
            "name": n,
            "country": "IN",
            "registration_status": "Registered",
            "qualification_status": "Qualified",
            "category": category[n],
            "updated_at": at,
        }
        for n in sorted(sm)
    ]
    events, bids, pos = [], [], []
    for case, unit_usd, ebeln, plant in planned_purchases(seed):
        f = case.facts
        num = f.id.split("-")[1]
        event_id = f"Doc{num}"
        created = w.as_of - timedelta(days=12)
        events.append(
            {
                "event_id": event_id,
                "title": f"New {f.product.lower()} for {f.owner} · {f.demand.site or f.location}",
                "event_type": "RFQ",
                "status": "Open",
                "commodity": w.classes[f.cls].plural,
                "currency": "EUR",
                "quantity": f.qty,
                "plant": plant,
                "external_ref": ebeln,
                "owner": "Procurement",
                "created_at": created,
                "close_at": w.as_of + timedelta(days=9),
                "updated_at": at,
            }
        )
        makers = [f.mfr] + [m for m in w.classes[f.cls].mfr if m != f.mfr]
        for i, (maker, factor, lead) in enumerate(zip(makers, QUOTE_FACTORS, LEAD_TIMES, strict=False)):
            bids.append(
                {
                    "bid_id": f"{event_id}-B{i + 1}",
                    "event_id": event_id,
                    "sm_vendor_id": sm[maker],
                    "unit_price": _eur(unit_usd, factor),
                    "currency": "EUR",
                    "lead_time_days": lead,
                    "valid_until": (w.as_of + timedelta(days=30)).date(),
                    "status": "Submitted",
                    "submitted_at": created + timedelta(days=2 + i),
                }
            )
        pos.append(
            {
                "po_id": f"EP{ebeln}",
                "erp_po": ebeln,
                "event_id": event_id,
                "sm_vendor_id": sm[f.mfr],
                "status": "Composing",
                "amount": _eur(unit_usd * f.qty, QUOTE_FACTORS[0]),
                "currency": "EUR",
                "plant": plant,
                "created_at": created,
                "updated_at": at,
            }
        )
    for table, rows in ((t.SUPPLIERS, suppliers), (t.EVENTS, events), (t.BIDS, bids), (t.PURCHASE_ORDERS, pos)):
        if rows:
            conn.execute(insert(table), rows)
    return {"suppliers": len(suppliers), "events": len(events), "bids": len(bids), "purchase_orders": len(pos)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS ariba"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM ariba.suppliers")).scalar_one() == 0:
        load(conn, seed)
