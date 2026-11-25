"""The vehicle inspection mock's seed: 100 inspections, synthetic, computed from the VIN's number (no randomness).

`inspections()` is pure: the documents as the API serves it, in VIN order. The pinned cars are listed in the package
docstring.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.vehicle_inspection.models import INSPECTION, metadata
from sim.vendors.vehicle_lease.seed import returns as lease_returns

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
COUNT = 100
LATE = range(90, 94)  # inspections still `scheduled`
EV_SOH = {41: 92, 42: 88, 43: 83, 44: 74, 45: 90, 46: 85, 47: 81, 48: 95}  # the pack readings of the EVs
HAIL = range(30, 35)
PAIRED = range(15, 20)
SCORE = {1: 4}
RECON = {1: 1200, 7: 2800, 8: 16500}
PHOTO_READING = {4: 61240}
CONDITION_WORD = ("ok", "worn", "ok", "replace")
AREAS = ("odometer", "front", "rear", "left side", "right side", "interior")
FIT_FROM = 80  # state of health (%) from which a pack is fit for retail


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _odometer(n: int, lease: dict[str, dict]) -> int:
    if n in PHOTO_READING:
        return PHOTO_READING[n]
    return lease[vin(n)]["odometerAtReturn"] if vin(n) in lease else 20000 + (n * 317) % 40000 // 10 * 10


def _recon(n: int) -> int:
    if n in RECON:
        return RECON[n]
    return 1500 + (n - 30) * 150 if n in HAIL else 300 + (n * 173) % 19 * 100  # 300 .. 2,100


def _lines(n: int, estimate: int) -> list[dict]:
    if n == 1:
        return [
            {"label": "Paint and panel, rear door", "amount": 700, "excessWear": True},
            {"label": "Tyres", "amount": 500, "excessWear": False},
        ]
    first = round(estimate * 0.6 / 10) * 10
    return [
        {"label": "Paint and panel", "amount": first, "excessWear": n % 2 == 0},
        {"label": "Tyres", "amount": estimate - first, "excessWear": False},
    ]


def _damage(n: int) -> list[dict]:
    if n in HAIL:
        return [{"area": "roof", "kind": "hail", "note": "Hail dents on the roof and bonnet"}]
    if n % 3 == 0:
        return [{"area": "rear bumper", "kind": "scratch", "note": "Light scratch, paint intact"}]
    return []


def _inspection(n: int, lease: dict[str, dict]) -> dict:
    late = n in LATE
    estimate = 0 if late else _recon(n)
    return {
        "inspectionId": f"INS-{n:04d}",
        "vin": vin(n),
        "status": "scheduled" if late else "complete",
        "conditionScore": None if late else SCORE.get(n, 1 + (n * 3 + 1) % 5),
        "odometerPhotoReading": None if late else _odometer(n, lease),
        "photos": [] if late else [{"photoId": f"PH-{n:04d}-{i}", "area": a} for i, a in enumerate(AREAS[: 3 + n % 4], 1)],
        "damage": [] if late else _damage(n),
        "hailDamage": n in HAIL,
        "tyres": None if late else CONDITION_WORD[n % 4],
        "brakes": None if late else CONDITION_WORD[(n + 1) % 4],
        "reconEstimate": None if late else estimate,
        "reconLines": [] if late else _lines(n, estimate),
        "batterySoh": None if late else EV_SOH.get(n),
        "pairedDevices": n in PAIRED,
        "completedAt": None if late else (AS_OF - timedelta(days=1 + n % 20)).isoformat(),
        "updatedAt": (AS_OF - timedelta(minutes=COUNT - n)).isoformat(),
    }


def inspections() -> list[dict]:
    lease = {d["vin"]: d for d in lease_returns()}
    return [_inspection(n, lease) for n in range(1, COUNT + 1)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [
        {"inspection_id": d["inspectionId"], "vin": d["vin"], "doc": d, "updated_at": datetime.fromisoformat(d["updatedAt"])}
        for d in inspections()
    ]
    conn.execute(insert(INSPECTION), rows)
    return {"inspection": len(rows), "battery_assessment": 0}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS vehicle_inspection"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM vehicle_inspection.inspection")).scalar_one() == 0:
        load(conn, s)
