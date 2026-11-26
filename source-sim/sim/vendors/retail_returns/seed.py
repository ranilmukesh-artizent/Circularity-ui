"""The retail returns mock's seed: twelve returned items, synthetic, fixed (no randomness).

`items()` is pure: the documents as the API serves them, in item order. Phones and tablets carry an IMEI; apparel and footwear
do not. Unsold apparel and footwear are in the list; one unsold jacket names an allowed exception.
"""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.retail_returns.models import RETURN, metadata

# (item class, sku, unsold, exceptionEvidence)
ROWS = (
    ("phone", "PH-14-128", False, None),
    ("phone", "PH-13-256", False, None),
    ("tablet", "TB-10-64", False, None),
    ("apparel", "JK-221-M", True, None),
    ("apparel", "JK-221-L", True, {"exception": "safety", "ref": "EV-2026-0042"}),
    ("apparel", "SH-310-S", False, None),
    ("apparel", "CT-118-M", True, None),
    ("footwear", "SH-9-42", True, None),
    ("footwear", "SH-9-43", False, None),
    ("phone", "PH-12-64", False, None),
    ("tablet", "TB-11-128", False, None),
    ("footwear", "SH-7-40", False, None),
)


def item(n: int) -> dict:
    cls, sku, unsold, evidence = ROWS[n - 1]
    device = cls in ("phone", "tablet")
    return {
        "itemId": f"RET-{n:04d}",
        "serial": f"SN-B2C-{n:04d}",
        "imei": f"35999000{n:07d}" if device else None,
        "itemClass": cls,
        "sku": sku,
        "unsold": unsold,
        "exceptionEvidence": evidence,
    }


def items() -> list[dict]:
    return [item(n) for n in range(1, len(ROWS) + 1)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = items()
    conn.execute(insert(RETURN), [{"item_id": d["itemId"], "doc": d} for d in rows])
    return {"return_item": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS retail_returns"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM retail_returns.return_item")).scalar_one() == 0:
        load(conn, s)
