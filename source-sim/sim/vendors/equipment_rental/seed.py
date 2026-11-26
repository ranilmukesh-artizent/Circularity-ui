"""The equipment rental mock's seed: eight off-rent machines and what the rental system knows about them (pinned, no
randomness). The machines are the replay samples RF-S1 ... RF-S8 of the `rental_fleet` pack."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.equipment_rental.models import DOC, metadata

# machine id, class, hours, branch, age (years), book value, utilisation of the branch and class, used price of the hours band
MACHINES = (
    ("M-0001", "excavator_20t", 6200, "BR-1", 8, 52000, 0.72, 61000),
    ("M-0002", "excavator_20t", 3900, "BR-1", 5, 98000, 0.72, 112000),
    ("M-0003", "wheel_loader", 5100, "BR-2", 6, 61000, 0.31, 74000),
    ("M-0004", "scissor_lift", 2400, "BR-1", 4, 14000, 0.66, 17500),
    ("M-0005", "telehandler", 4800, "BR-2", 6, 44000, 0.58, 52000),
    ("M-0006", "excavator_20t", 9400, "BR-3", 11, 21000, 0.45, 33000),
    ("M-0007", "generator", 7300, "BR-1", 12, 2500, 0.12, 6200),
    ("M-0008", "wheel_loader", 6800, "BR-1", 7, 40000, 0.80, 51000),
)
IDLE_DAYS = {"M-0003": 44}


def band(hours: int) -> str:
    """The 1,000-hour band of a reading: 6,200 -> `6000-7000`."""
    low = hours // 1000 * 1000
    return f"{low}-{low + 1000}"


def docs() -> list[tuple[str, str, dict]]:
    out: list[tuple[str, str, dict]] = []
    for mid, cls, hours, br, age, book, util, price in MACHINES:
        out.append(("off_rent", mid, {"machineId": mid, "assetClass": cls, "hours": hours, "branch": br, "ageYears": age,
                                     "bookValue": book, "offRentAt": "2026-11-20T08:00:00+00:00"}))  # fmt: skip
        out.append(("utilisation", f"{br}:{cls}", {"branch": br, "assetClass": cls, "utilisation": util}))
        out.append(("price", f"{cls}:{band(hours)}", {"assetClass": cls, "hoursBand": band(hours), "price": price}))
        if mid in IDLE_DAYS:
            out.append(("idle", mid, {"machineId": mid, "assetClass": cls, "branch": br, "idleDays": IDLE_DAYS[mid]}))
    out.append(("damage", "DC-1", {"claimId": "DC-1", "machineId": "M-0005", "renterRef": "R-0042", "amount": 2350,
                                   "photosRef": "PH-0005"}))  # fmt: skip
    out.append(("damage", "DC-2", {"claimId": "DC-2", "machineId": "M-0004", "renterRef": "R-0007", "amount": 80,
                                   "photosRef": "PH-0004"}))  # fmt: skip
    out.append(("plan", "PP-1", {"planId": "PP-1", "branch": "BR-3", "assetClass": "wheel_loader", "qty": 1}))
    return out


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = docs()
    conn.execute(insert(DOC), [{"kind": k, "key": key, "doc": d} for k, key, d in rows])
    return {"doc": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS equipment_rental"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM equipment_rental.doc")).scalar_one() == 0:
        load(conn, s)
