"""The recycler portal mock's seed: two recyclers, synthetic and fixed (no randomness). Pickups and certificates start empty."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.recycler_portal.models import VENDOR, metadata

SOURCE = "tn_recycler"
HANDLER = "tn_recycler.certificates.issue"


def vendors() -> list[tuple[dict, bool]]:
    """(document, lapsed): RV-1 is valid with a dangerous-goods lane, RV-2 has lapsed."""
    return [
        (
            {
                "vendorId": "RV-1", "label": "Recycler one", "dgLane": True, "regions": ["North", "South"],
                "certificate": {"scheme": "R2v3", "ref": "R2V3-0001", "expires": "2027-06-30"},
            },
            False,
        ),
        (
            {
                "vendorId": "RV-2", "label": "Recycler two", "dgLane": False, "regions": ["East", "West"],
                "certificate": {"scheme": "e-Stewards", "ref": "ES-0002", "expires": "2026-10-31"},
            },
            True,
        ),
    ]  # fmt: skip


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    conn.execute(insert(VENDOR), [{"vendor_id": d["vendorId"], "lapsed": lapsed, "doc": d} for d, lapsed in vendors()])
    return {"vendor": 2}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS recycler_portal"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM recycler_portal.vendor")).scalar_one() == 0:
        load(conn, s)
