"""Load the seed (B2) into the S/4HANA tables, as S/4 would hold it at the demo's as-of time.

What S/4 owns here (the demo's SOURCES.erp: "inventory valuation, actual cost postings, purchase baseline;
finance only, orders live in OMS"):
- plants:        customer sites Site 1..8 → 1010..1080 (the demo maps EKPO-WERKS 1030 → Site 3);
                 Warehouse 1, Warehouse 2, Repair centre → 2010, 2020, 2030
- materials:     one per returned asset (MATNR = asset id, e.g. MTR-2041), stock at its current location
- valuation:     standard price in INR (assumed: price new × grade factor × e^(−age/τ), the demo's residual-value shape)
- purchase plan: one planned purchase per case whose routes avoid a purchase (EBELN = 48000 + case number, e.g.
                 RT-1048 → 49048, as the demo's approval terms say "cancel planned purchase PO-49048"); NETPR in INR
                 at the demo's dated rate of 83.5 INR/USD (RT-1048: 12,000 USD → 10,02,000.00 INR)
- journal:       none. Actual cost postings (BKPF/ACDOCA) arrive only through the Journal Entry - Post service
                 (sim/vendors/s4/journal.py) once an approved decision runs; a reset clears them.
"""

import math
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.s4 import models as t

INR_PER_USD = Decimal("83.5")  # the demo's MAPPINGS: "Currency at 83.5 (rate dated 2026-10-06)"
FACILITY_PLANTS = {"Warehouse 1": "2010", "Warehouse 2": "2020", "Repair centre": "2030"}
STORAGE_LOCATION = "RT01"  # returns


def site_plant(site_id: str) -> str:
    return f"10{int(site_id.split()[-1])}0"  # Site 3 -> 1030


def location_plant(location: str) -> str:
    return FACILITY_PLANTS.get(location) or site_plant(location)


def _inr(usd: float) -> Decimal:
    return (Decimal(str(usd)) * INR_PER_USD).quantize(Decimal("0.01"), ROUND_HALF_UP)


def supplier_ids(seed: Seed) -> dict[str, str]:
    names = sorted({m for c in seed.world.classes.values() for m in c.mfr})
    return {n: f"{10000001 + i:010d}" for i, n in enumerate(names)}


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    w = seed.world
    changed = w.as_of - timedelta(days=1)  # everything seeded counts as changed the day before the as-of time
    rows: dict[str, list[dict]] = {name: [] for name in ("T001W", "LFA1", "MARA", "MAKT", "MARC", "MARD", "MBEW", "EKKO", "EKPO")}

    for s in w.sites:
        rows["T001W"].append({"WERKS": site_plant(s.id), "NAME1": s.name, "ORT01": s.name.split()[0], "LAST_CHANGE": changed})
    for f, plant in FACILITY_PLANTS.items():
        rows["T001W"].append({"WERKS": plant, "NAME1": f"Northfield {f}", "ORT01": "", "LAST_CHANGE": changed})
    suppliers = supplier_ids(seed)
    for name, lifnr in suppliers.items():
        rows["LFA1"].append({"LIFNR": lifnr, "NAME1": name, "LAST_CHANGE": changed})

    for case in seed.cases.values():
        f = case.facts
        cls = w.classes[f.cls]
        plant = location_plant(f.location)
        unit = "EA"
        spec = next(iter(f.spec.values()), "")
        rows["MARA"].append(
            {
                "MATNR": f.asset_id,
                "MTART": "HAWA",
                "MATKL": cls.pre,
                "MEINS": unit,
                "MFRNR": f.mfr,
                "ERSDA": f.received.date(),
                "LAST_CHANGE": changed,
            }
        )
        rows["MAKT"].append(
            {"MATNR": f.asset_id, "SPRAS": "EN", "MAKTX": f"{f.product} {f.mfr} {spec}"[:40], "LAST_CHANGE": changed}
        )
        rows["MARC"].append({"MATNR": f.asset_id, "WERKS": plant, "EKGRP": "RT1", "LAST_CHANGE": changed})
        rows["MARD"].append(
            {
                "MATNR": f.asset_id,
                "WERKS": plant,
                "LGORT": STORAGE_LOCATION,
                "LABST": f.qty,
                "INSME": 0,
                "SPEME": 0,
                "LAST_CHANGE": changed,
            }
        )
        grade_factor = w.grade_factor.get(f.grade or "C", w.grade_factor["C"])
        unit_value = cls.pnew * grade_factor * math.exp(-f.age / cls.tau)
        rows["MBEW"].append(
            {
                "MATNR": f.asset_id,
                "BWKEY": plant,
                "BKLAS": "3100",
                "VPRSV": "S",
                "STPRS": _inr(unit_value),
                "PEINH": 1,
                "WAERS": "INR",
                "LAST_CHANGE": changed,
            }
        )

        purchase = max((term.amt for r in f.routes for term in r.terms if term.kind == "purchase"), default=0)
        if purchase > 0 and f.demand.internal:
            ebeln = str(48000 + int(f.id.split("-")[1]))
            werks = site_plant(f.demand.site) if f.demand.site else plant
            rows["EKKO"].append(
                {
                    "EBELN": ebeln,
                    "BSTYP": "F",
                    "BSART": "NB",
                    "LIFNR": suppliers.get(f.mfr, next(iter(suppliers.values()))),
                    "BUKRS": "1000",
                    "WAERS": "INR",
                    "AEDAT": (w.as_of - timedelta(days=20)).date(),
                    "LAST_CHANGE": changed,
                }
            )
            rows["EKPO"].append(
                {
                    "EBELN": ebeln,
                    "EBELP": "00010",
                    "MATNR": None,
                    "TXZ01": f"New {f.product.lower()} for {f.owner}"[:40],
                    "WERKS": werks,
                    "MENGE": f.qty,
                    "MEINS": unit,
                    "NETPR": _inr(purchase / f.qty),
                    "PEINH": 1,
                    "WAERS": "INR",
                    "LOEKZ": "",
                    "LAST_CHANGE": changed,
                }
            )

    for name, data in rows.items():
        if data:
            conn.execute(insert(t.metadata.tables[f"s4.{name}"]), data)
    return {name: len(data) for name, data in rows.items()} | {"ANLA": load_assets(conn)}


def assets() -> list[dict]:
    """The fixed-asset master of the three packs that own their assets (P9-13.1): 60 cars, 120 network units and 45 medical
    devices, keyed as the other mocks key them. Book values are computed from the unit's number (no randomness); in USD."""
    from sim.vendors.medical_rental_system.seed import tag
    from sim.vendors.network_inventory.seed import serial
    from sim.vendors.vehicle_lease.seed import vin

    out = []
    groups = (("Vehicle", range(1, 61), vin, 18000, 100, 10), ("Network unit", range(1, 121), serial, 4200, 25, 7),
              ("Medical device", range(1, 46), tag, 9500, 60, 9))  # fmt: skip
    for label, nums, key, base, step, mod in groups:
        for n in nums:
            book = base - step * ((n - 1) % mod)
            out.append({
                "ANLN1": f"{100000 + len(out) + 1}", "ASSET_KEY": key(n), "TXT50": f"{label} {key(n)}",
                "AK_VALUE": Decimal(book) * Decimal("1.6"), "BOOK_VALUE": Decimal(book), "WAERS": "USD", "LOCATION": "",
                "STATUS": "active",
            })  # fmt: skip
    return out


def load_assets(conn: Connection) -> int:
    rows = assets()
    conn.execute(insert(t.ANLA), rows)
    return len(rows)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    """Drop and recreate every S/4 table, then load the seed."""
    conn.execute(text('DROP VIEW IF EXISTS s4."V_MATL_STK"'))
    conn.execute(text('DROP VIEW IF EXISTS s4."V_JE_ITEM"'))
    t.metadata.drop_all(conn)
    for seq in t.SEQUENCES:
        conn.execute(text(f"DROP SEQUENCE IF EXISTS s4.{seq}"))
    create(conn)
    return load(conn, seed)  # no journal entries: the starting state has no actual cost postings


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS s4"))
    # ACDOCA was a placeholder before B13 (no rows, fewer columns): rebuild it once with the journal-entry columns
    old = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 's4' AND table_name = 'ACDOCA' AND NOT EXISTS "
            "(SELECT 1 FROM information_schema.columns WHERE table_schema = 's4' AND table_name = 'ACDOCA' "
            "AND column_name = 'DRCRK')"
        )
    ).first()
    if old:
        conn.execute(text('DROP TABLE s4."ACDOCA" CASCADE'))
    t.metadata.create_all(conn)
    conn.execute(text(t.STOCK_VIEW_DDL))
    conn.execute(text(t.JE_ITEM_VIEW_DDL))
    for ddl in t.SEQUENCES_DDL:
        conn.execute(text(ddl))


def ensure(conn: Connection, seed: Seed) -> None:
    """Create the tables and load the seed once (on first start)."""
    create(conn)
    if conn.execute(text('SELECT count(*) FROM s4."MARA"')).scalar_one() == 0:
        load(conn, seed)
    elif conn.execute(text('SELECT count(*) FROM s4."ANLA"')).scalar_one() == 0:
        load_assets(conn)  # a database seeded before P9-13.1 gets the asset master once
