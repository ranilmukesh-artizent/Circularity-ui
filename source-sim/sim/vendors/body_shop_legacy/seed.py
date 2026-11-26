"""The legacy body-shop mock's seed: 600 repairs over 100 cars, synthetic and fixed (no randomness).

`repairs()` is pure: the API documents in order. Repair n (1-600) belongs to car ((n - 1) mod 100) + 1, so every car has six.
"""

from datetime import date, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.body_shop_legacy.models import REPAIR, metadata

COUNT, CARS = 600, 100
LAST_DAY = date(2026, 10, 6)
AREAS = (
    "front bumper", "rear quarter panel", "driver door", "hood", "windshield", "roof", "tailgate", "passenger door",
    "rear bumper", "fender", "side mirror", "rocker panel",
)  # fmt: skip
CLAIM_OVER = 3000  # ASSUMPTION: an insurance claim is made for the repairs over this cost


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _repair(n: int) -> dict:
    car = (n - 1) % CARS + 1
    cost = 180 + (n * 137) % 3400  # 180 to 3,579
    return {
        "repairId": f"BS-{n:04d}",
        "vin": vin(car),
        "damageArea": AREAS[(n * 7 + car) % len(AREAS)],
        "repairDate": (LAST_DAY - timedelta(days=(n * 11) % 1500)).isoformat(),
        "cost": cost,
        "insuranceClaim": cost > CLAIM_OVER,
    }


def repairs() -> list[dict]:
    return [_repair(n) for n in range(1, COUNT + 1)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [{"n": n, "repair_id": d["repairId"], "vin": d["vin"], "doc": d} for n, d in enumerate(repairs(), 1)]
    conn.execute(insert(REPAIR), rows)
    return {"repair": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS body_shop_legacy"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM body_shop_legacy.repair")).scalar_one() == 0:
        load(conn, s)
