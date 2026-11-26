"""The battery management mock's seed: five packs, pinned (no randomness)."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.battery_bms.models import PACK, metadata


def _pack(pack_id: str, vin: str | None, chem: str, soh: int, life: int, market: str, *, thermal=False, damaged=False) -> dict:
    return {
        "packId": pack_id, "vinRef": vin, "chemistry": chem, "sohPct": soh, "expectedLifeYears": life,
        "readAt": "2026-11-10", "thermalEvent": thermal, "damaged": damaged,
        "safetyClass": "damaged" if damaged or thermal else "9", "market": market,
    }  # fmt: skip


def packs() -> list[dict]:
    return [
        _pack("BP-044", "SYNUC000000000044", "NMC", 74, 4, "EU"),
        _pack("BP-101", None, "LFP", 86, 8, "US"),
        _pack("BP-102", None, "NMC", 66, 3, "EU"),
        _pack("BP-103", None, "NMC", 71, 3, "US", damaged=True),
        _pack("BP-104", "SYNUC000000000104", "NCA", 78, 5, "US", thermal=True),
    ]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = packs()
    conn.execute(insert(PACK), [{"pack_id": p["packId"], "doc": p} for p in rows])
    return {"pack": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS battery_bms"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM battery_bms.pack")).scalar_one() == 0:
        load(conn, s)
