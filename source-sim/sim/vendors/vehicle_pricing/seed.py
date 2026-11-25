"""The pricing guide mock's seed: a value for each of the 100 cars (60 lease returns, 40 trade-ins), synthetic and
computed from the car (no randomness). The pinned cars are listed in the package docstring.

`values()` is pure; it reads the cars from the lease mock's `returns()` and the dealer mock's `trade_in(n)`.
"""

from datetime import UTC, datetime
from fractions import Fraction

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.dealer_dms.seed import BAND_PRICE, BANDS, BASE_PRICE, FIRST_TRADE, LAST_TRADE, band_of, trade_in
from sim.vendors.vehicle_lease.seed import returns
from sim.vendors.vehicle_pricing.models import VALUE, metadata

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
PINNED_RETAIL = {"SYNUC000000000001": 24000, "SYNUC000000000008": 21000}  # lease cars ...001 and ...008


def _round100(x: Fraction) -> int:
    return round(x / 100) * 100


def value(vin: str, segment: str, year: int, miles: int) -> dict:
    band = band_of(miles)
    year_factor = 1 + Fraction(3, 100) * (year - 2022)
    retail = PINNED_RETAIL.get(vin) or _round100(Fraction(BASE_PRICE[segment]) * BAND_PRICE[BANDS.index(band)] * year_factor)
    wholesale = _round100(Fraction(retail) * Fraction(112, 125))
    return {"vin": vin, "retail": retail, "wholesale": wholesale, "segment": segment, "band": band, "asOf": AS_OF.isoformat()}


def values() -> list[dict]:
    cars = [value(r["vin"], r["segment"], r["modelYear"], r["odometerAtReturn"]) for r in returns()]
    for n in range(FIRST_TRADE, LAST_TRADE + 1):
        t = trade_in(n)
        cars.append(value(t["vin"], t["segment"], t["modelYear"], t["mileage"]))
    return cars


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [{"vin": d["vin"], "doc": d} for d in values()]
    conn.execute(insert(VALUE), rows)
    return {"value": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS vehicle_pricing"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM vehicle_pricing.value")).scalar_one() == 0:
        load(conn, s)
