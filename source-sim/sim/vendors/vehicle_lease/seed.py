"""The vehicle lease mock's seed: 60 lease returns, synthetic, computed from the VIN's number (no randomness).

`returns()` is pure: the documents as the API serves them, in VIN order. The dealer mock imports `returns()` for the
cars' residual values (its partner bids follow them). The pinned cars are listed in the package docstring.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.vehicle_lease.models import LEASE_RETURN, metadata

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
COUNT = 60
SEGMENTS = ("compact", "midsize", "suv", "truck")  # the cycle for the cars that are not EV crossovers
RESIDUAL_BASE = {"compact": 11000, "midsize": 14000, "suv": 19500, "truck": 23000, "ev_crossover": 27000}
CONTRACT_MILES = (36000, 30000, 45000)
EV_FIRST, EV_LAST = 41, 48
PINNED_ODOMETER = {1: 38000, 4: 61240, 5: 133000}
LAST_SERVICE = {4: 46240}  # every other car's last-service reading equals its reading at return
NOT_ACTUAL = {11, 12}
FLEET_SELLERS = {50: 40}


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _segment(n: int) -> str:
    return "ev_crossover" if EV_FIRST <= n <= EV_LAST else SEGMENTS[(n + 1) % 4]  # n = 1 is an SUV


def _powertrain(n: int, segment: str) -> str:
    if segment == "ev_crossover":
        return "ev"
    return "hybrid" if n % 5 == 0 else "diesel" if segment == "truck" else "petrol"


def _return(n: int) -> dict:
    segment = _segment(n)
    year = 2022 if n == 1 else 2019 + (n * 3) % 6
    contract = CONTRACT_MILES[(n - 1) % 3]
    odometer = PINNED_ODOMETER.get(n) or round(contract * (0.7 + 0.06 * (n % 6)) / 10) * 10
    residual = 19500 if n == 1 else round(RESIDUAL_BASE[segment] * (1 - 0.05 * (2025 - year)) / 100) * 100
    return {
        "leaseId": f"LS-{n:04d}",
        "vin": vin(n),
        "lesseeRef": f"L-{n:04d}",
        "leaseEnd": (AS_OF.date() - timedelta(days=n % 25)).isoformat(),
        "residualValue": residual,
        "contractMileage": contract,
        "odometerAtReturn": odometer,
        "odometerLastService": LAST_SERVICE.get(n, odometer),
        "odometerStatementRef": f"OS-{n:04d}",
        "odometerNotActual": n in NOT_ACTUAL,
        "modelYear": year,
        "segment": segment,
        "powertrain": _powertrain(n, segment),
        "returnCenter": "RC-East" if n <= 30 else "RC-West",
        "sellerFleetSize": FLEET_SELLERS.get(n, 0),
        "status": "returned",
        "updatedAt": (AS_OF - timedelta(minutes=COUNT - n)).isoformat(),
    }


def returns() -> list[dict]:
    return [_return(n) for n in range(1, COUNT + 1)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [
        {"lease_id": d["leaseId"], "vin": d["vin"], "doc": d, "updated_at": datetime.fromisoformat(d["updatedAt"])}
        for d in returns()
    ]
    conn.execute(insert(LEASE_RETURN), rows)
    return {"lease_return": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS vehicle_lease"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM vehicle_lease.lease_return")).scalar_one() == 0:
        load(conn, s)
