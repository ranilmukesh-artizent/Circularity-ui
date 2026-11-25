"""The auction mock's seed: 52 weekly sales (two sites), 20 cleared-price cells, 60 salvage bids and 4 buyers, synthetic
and computed (no randomness). The pinned figures are listed in the package docstring.

Cleared prices are 86 percent of the dealer mock's base price for the segment and band (the wholesale level below
retail); the salvage bids follow the lease mock's residual values.
"""

from datetime import UTC, datetime, timedelta
from fractions import Fraction

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.dealer_dms.seed import BAND_PRICE, BANDS, BASE_PRICE, SEGS
from sim.vendors.vehicle_auction.models import RECORD, metadata
from sim.vendors.vehicle_lease.seed import returns

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
FEES = {"sellFee": 325, "transport": 120}
SITES = (("AUC-E", "East auction", "RC-East", 6), ("AUC-W", "West auction", "RC-West", 2))  # id, name, centre, first day
SALES_PER_SITE = 26
PINNED_BID = {1: 2100, 8: 3900}
BIDDERS = ("SB-1", "SB-2", "SB-3")
BUYERS = (
    ("SB-1", "Salvage buyer 1 (synthetic)", True, True),
    ("SB-2", "Salvage buyer 2 (synthetic)", True, False),  # does not report to the national title database
    ("SB-3", "Salvage buyer 3 (synthetic)", True, True),
    ("RB-1", "Wholesale buyer 1 (synthetic)", False, True),
)


def sales() -> list[dict]:
    out = []
    for site, name, centre, first in SITES:
        for k in range(SALES_PER_SITE):
            day = (AS_OF + timedelta(days=first + 7 * k)).date().isoformat()
            out.append({"saleId": f"{site}-{day}", "site": site, "siteName": name, "returnCenter": centre, "saleDate": day})
    return out


def result_cell(segment: str, band: str) -> dict:
    b = BANDS.index(band)
    price = round(Fraction(BASE_PRICE[segment]) * BAND_PRICE[b] * Fraction(43, 50) / 100) * 100
    return {"segment": segment, "band": band, "avgClearedPrice": price, "count": max(4, 40 - 9 * b - 3 * SEGS.index(segment))}


def salvage_bids() -> list[dict]:
    rows = []
    for r in returns():
        n = int(r["vin"][-3:])
        amount = PINNED_BID.get(n) or round(r["residualValue"] * 14 / 10000) * 100
        buyer = "SB-1" if n in PINNED_BID else BIDDERS[n % 3]
        rows.append(
            {
                "bidId": f"SBID-{n:04d}", "vin": r["vin"], "buyerId": buyer, "amount": amount,
                "validUntil": (AS_OF + timedelta(days=7)).isoformat(),
            }
        )  # fmt: skip
    return rows


def records() -> list[dict]:
    """Every RECORD row, in listing order."""
    out: list[dict] = []

    def add(kind: str, rec_id: str, doc: dict, **cols) -> None:
        out.append({"kind": kind, "rec_id": rec_id, "ord": sum(r["kind"] == kind for r in out), "doc": doc} | cols)

    for d in sales():
        add("sales", d["saleId"], d, site=d["site"])
    for seg in SEGS:
        for band in BANDS:
            add("results", f"{seg}:{band}", result_cell(seg, band), segment=seg, band=band)
    for d in salvage_bids():
        add("salvage-bids", d["bidId"], d, vin=d["vin"])
    for buyer, name, salvage, reporting in BUYERS:
        add("buyers", buyer, {"buyerId": buyer, "name": name, "salvage": salvage, "titleDbReporting": reporting})
    return out


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = records()
    conn.execute(insert(RECORD), [{"vin": None, "site": None, "segment": None, "band": None} | r for r in rows])
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return counts


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS vehicle_auction"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM vehicle_auction.record")).scalar_one() == 0:
        load(conn, s)
