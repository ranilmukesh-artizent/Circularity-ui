"""The dealer mock's seed: 40 trade-ins, 3 lots, 60 lot-sale cells, 60 partner bids and 30 cars on the lots, synthetic
and computed (no randomness). The pinned figures are listed in the package docstring.

`lot_cell(lot, segment, band)` is pure: it gives one cell of the lots' sales history. Exact fractions keep the pinned
prices exact (SUV 0-40k: 24,000 at LOT-C, 59/60 of it at LOT-N, 81/80 at LOT-S). The stock holds the five EV crossovers
at LOT-N that have sat more than 45 days (VINs ...041-...045, lease returns), three more EV crossovers, and 22 trade-ins
(VINs ...061-...082), two of which are over 45 days.
"""

from datetime import UTC, datetime, timedelta
from fractions import Fraction

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.dealer_dms.models import RECORD, metadata
from sim.vendors.vehicle_lease.seed import SEGMENTS, returns, vin

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
LOTS = (("LOT-N", "North lot", 12), ("LOT-C", "Central lot", 40), ("LOT-S", "South lot", 95))
SEGS = ("compact", "midsize", "suv", "ev_crossover", "truck")
BANDS = ("0-40k", "40-80k", "80-120k", "120k+")
BASE_PRICE = {"compact": 14000, "midsize": 17500, "suv": 24000, "ev_crossover": 29000, "truck": 28000}
BAND_PRICE = (Fraction(1), Fraction(4, 5), Fraction(31, 50), Fraction(12, 25))
LOT_PRICE = {"LOT-N": Fraction(59, 60), "LOT-C": Fraction(1), "LOT-S": Fraction(81, 80)}
CENTRAL_DAYS = {"compact": 19, "midsize": 22, "suv": 21, "truck": 30}  # at LOT-C in the first band; +4 a band
EV_DAYS = {"LOT-N": 58, "LOT-C": 33, "LOT-S": 29}  # every band
LOT_COUNT = {"LOT-N": 12, "LOT-C": 22, "LOT-S": 18}  # SUV 0-40k
SEG_SHARE = {"compact": Fraction(11, 10), "midsize": Fraction(9, 10), "suv": Fraction(1), "ev_crossover": Fraction(7, 20),
             "truck": Fraction(1, 2)}  # fmt: skip
BAND_SHARE = (Fraction(1), Fraction(4, 5), Fraction(1, 2), Fraction(1, 4))
LOT_SPREAD = {"LOT-N": 1500, "LOT-C": 1300, "LOT-S": 1200}  # SUV 0-40k
FIRST_TRADE, LAST_TRADE = 61, 100
PAYOFF_UNCONFIRMED = {62}
EV_STOCK = ((41, "LOT-N", 52), (42, "LOT-N", 58), (43, "LOT-N", 61), (44, "LOT-N", 66), (45, "LOT-N", 72),
            (46, "LOT-C", 31), (47, "LOT-C", 35), (48, "LOT-S", 29))  # fmt: skip
TRADE_STOCK = range(61, 83)
OLD_TRADES = {63: 49, 70: 47}  # the two non-EV cars over 45 days


def band_of(miles: int) -> str:
    return BANDS[0] if miles < 40000 else BANDS[1] if miles < 80000 else BANDS[2] if miles < 120000 else BANDS[3]


def car_of(vin_: str) -> tuple[str, int] | None:
    """(segment, mileage) of a car of the lease and trade-in mocks by VIN (...001 to ...060 returned leases, ...061 to ...100
    trade-ins), or None for a VIN the group does not know."""
    if not vin_.startswith("SYNUC") or not vin_[5:].isdigit():
        return None
    n = int(vin_[5:])
    if 1 <= n <= 60:
        r = returns()[n - 1]
        return r["segment"], r["odometerAtReturn"]
    if FIRST_TRADE <= n <= LAST_TRADE:
        segment, _p, _y, miles = _trade_car(n)
        return segment, miles
    return None


def lot_cell(lot: str, segment: str, band: str) -> dict:
    """One cell of a lot's own sales history: {avgPrice, avgDaysToSale, count, spread}."""
    b = BANDS.index(band)
    price = round(Fraction(BASE_PRICE[segment]) * BAND_PRICE[b] * LOT_PRICE[lot] / 50) * 50
    if segment == "ev_crossover":
        days = EV_DAYS[lot]
    else:
        central = CENTRAL_DAYS[segment] + 4 * b
        days = central + 13 if lot == "LOT-N" else max(3, central - 6) if lot == "LOT-S" else central
    count = max(3, round(LOT_COUNT[lot] * SEG_SHARE[segment] * BAND_SHARE[b]))
    spread = LOT_SPREAD[lot] + 100 * b + (200 if segment in ("truck", "ev_crossover") else 0)
    return {"avgPrice": price, "avgDaysToSale": days, "count": count, "spread": spread}


def _trade_car(n: int) -> tuple[str, str, int, int]:
    """(segment, powertrain, model year, mileage) of a trade-in's car."""
    segment = SEGMENTS[n % 4]
    powertrain = "hybrid" if n % 5 == 0 else "diesel" if segment == "truck" else "petrol"
    return segment, powertrain, 2017 + (n * 5) % 8, round((20000 + (n * 7919) % 110000) / 10) * 10


def trade_in(n: int) -> dict:
    segment, powertrain, year, miles = _trade_car(n)
    band = band_of(miles)
    allowance = round(Fraction(BASE_PRICE[segment]) * BAND_PRICE[BANDS.index(band)] * Fraction(17, 20) / 50) * 50
    return {
        "tradeId": f"TI-{n:04d}",
        "vin": vin(n),
        "tradeAllowance": allowance,
        "payoffAmount": round(Fraction(allowance) * Fraction(3, 5) / 50) * 50,
        "payoffConfirmed": n not in PAYOFF_UNCONFIRMED,
        "mileage": miles,
        "modelYear": year,
        "segment": segment,
        "powertrain": powertrain,
        "receivedAt": (AS_OF - timedelta(days=n % 10, hours=n % 7)).isoformat(),
        "store": f"Store {1 + n % 3}",
    }


def _stock_row(k: int, n: int, lot: str, days: int, segment: str, powertrain: str) -> dict:
    return {
        "stockId": f"ST-{k:03d}", "vin": vin(n), "lotId": lot, "segment": segment, "powertrain": powertrain,
        "daysOnLot": days, "askingPrice": lot_cell(lot, segment, "0-40k")["avgPrice"],
    }  # fmt: skip


def stock() -> list[dict]:
    rows = [_stock_row(k, n, lot, days, "ev_crossover", "ev") for k, (n, lot, days) in enumerate(EV_STOCK, 1)]
    for n in TRADE_STOCK:
        segment, powertrain, _y, _m = _trade_car(n)
        days = OLD_TRADES.get(n, 3 + ((n - 61) * 7) % 41)
        rows.append(_stock_row(len(rows) + 1, n, LOTS[(n - 61) % 3][0], days, segment, powertrain))
    return rows


def partner_bids() -> list[dict]:
    return [
        {
            "bidId": f"PB-{r['leaseId'][3:]}", "vin": r["vin"], "partner": "Partner dealer A (synthetic)",
            "amount": round(Fraction(r["residualValue"] * 107, 100) / 100) * 100,
            "validUntil": (AS_OF + timedelta(days=7)).isoformat(),
        }
        for r in returns()
    ]  # fmt: skip


def records() -> list[dict]:
    """Every RECORD row, in listing order."""
    out: list[dict] = []

    def add(kind: str, rec_id: str, doc: dict, **cols) -> None:
        out.append({"kind": kind, "rec_id": rec_id, "ord": sum(r["kind"] == kind for r in out), "doc": doc} | cols)

    for n in range(FIRST_TRADE, LAST_TRADE + 1):
        d = trade_in(n)
        add("trade-ins", d["tradeId"], d, vin=d["vin"], segment=d["segment"])
    for lot, name, miles in LOTS:
        add("lots", lot, {"lotId": lot, "name": name, "distanceMiles": miles}, lot_id=lot)
    for lot, _name, _miles in LOTS:
        for seg in SEGS:
            for band in BANDS:
                doc = {"lotId": lot, "segment": seg, "mileageBand": band, **lot_cell(lot, seg, band)}
                add("lot-sales", f"{lot}:{seg}:{band}", doc, lot_id=lot, segment=seg, mileage_band=band)
    for d in partner_bids():
        add("partner-bids", d["bidId"], d, vin=d["vin"])
    for d in stock():
        add("stock", d["stockId"], d, vin=d["vin"], lot_id=d["lotId"], segment=d["segment"])
    return out


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = records()
    conn.execute(insert(RECORD), [{"vin": None, "lot_id": None, "segment": None, "mileage_band": None} | r for r in rows])
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return counts


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS dealer_dms"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM dealer_dms.record")).scalar_one() == 0:
        load(conn, s)
