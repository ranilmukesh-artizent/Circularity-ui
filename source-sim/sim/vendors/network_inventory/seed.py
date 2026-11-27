"""The network inventory mock's seed: 120 network elements, synthetic, computed from the serial's number (no randomness).

`elements()` is pure: the documents as the API serves them, in serial order. The decommission tracker mock imports
`element()` for the sites of the units it removes. `LATE` is the element that joins the inventory one simulated day
after a reset (scheduled; event `inventory.element.created`). The pinned elements are listed in the package docstring.
"""

from datetime import timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.core import clock, scheduler
from sim.seed import Seed
from sim.vendors.network_inventory.models import ELEMENT, metadata

SOURCE = "tn_inv"
HANDLER = "tn_inv.element.create"
COUNT = 120
REGIONS = ("North", "South", "East", "West")  # 30 elements each, in serial order
# (model, part number, manufacturer, hardware revision, export class confirmed, export class inferred)
MODELS = (
    ("RAD-7700", "PN-7700-01", "MFR-A", "A1", "5A002", None),
    ("RRU-4410", "PN-4410-02", "MFR-B", "B2", None, "5A992"),
    ("RTR-880", "PN-0880-07", "MFR-C", "C1", None, None),
    ("BBU-5200", "PN-5200-03", "MFR-B", "A3", None, None),
    ("LCD-100G", "PN-1100-05", "MFR-C", "D1", None, None),
    ("MWL-60", "PN-0060-09", "MFR-A", "B1", None, None),
)
LATE_SERIAL = "SN-TN-0201"
# SN-TN-0015, the bench's unit whose wipe failed twice, is a previous-generation baseband that brokers bid on and no region
# needs: without the wipe it would resell, so its case shows the wipe gate as what closes the resale (story TN-06).
PINNED = {15: ("BBU-2200", "PN-2200-04", "MFR-B", "C1", None, None)}


def serial(n: int) -> str:
    return f"SN-TN-{n:04d}"


def _status(n: int) -> str:
    """The first 33 are the units the tracker's ordinary jobs removed; every sixth after them is a regional spare."""
    return "removed" if n <= 33 else "spare" if n % 6 == 0 else "in_service"


def element(n: int) -> dict:
    model, part, maker, hw, confirmed, inferred = PINNED.get(n) or MODELS[n % len(MODELS)]
    firmware = f"{5 + n % 4}.{n % 3}.{n % 5}" if model == "RTR-880" else f"3.{n % 3}.{n % 5}"
    return {
        "serial": serial(n),
        "model": model,
        "partNumber": part,
        "hwRevision": hw,
        "firmware": firmware,
        "manufacturer": maker,
        "site": f"SITE-{100 + n - 1}",
        "siteKind": "core" if n % 10 == 0 else "edge",
        "region": REGIONS[(n - 1) // 30],
        "status": _status(n),
        "exportClassInferred": inferred,
        "exportClassConfirmed": confirmed,
    }


def late_element() -> dict:
    """SN-TN-0201 (job RJ-09 removed it): an RAD-7700 from the North, taken off SITE-301."""
    model, part, maker, hw, confirmed, inferred = MODELS[0]
    return {
        "serial": LATE_SERIAL, "model": model, "partNumber": part, "hwRevision": hw, "firmware": "3.0.1", "manufacturer": maker,
        "site": "SITE-301", "siteKind": "edge", "region": "North", "status": "removed",
        "exportClassInferred": inferred, "exportClassConfirmed": confirmed,
    }  # fmt: skip


def elements() -> list[dict]:
    return [element(n) for n in range(1, COUNT + 1)]


def insert_element(conn: Connection, doc: dict) -> None:
    conn.execute(insert(ELEMENT).values(serial=doc["serial"], site=doc["site"], doc=doc))


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    conn.execute(insert(ELEMENT), [{"serial": d["serial"], "site": d["site"], "doc": d} for d in elements()])
    scheduler.schedule(conn, clock.now(conn) + timedelta(days=1), HANDLER, {"serial": LATE_SERIAL}, SOURCE)
    return {"element": COUNT}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS network_inventory"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM network_inventory.element")).scalar_one() == 0:
        load(conn, s)
