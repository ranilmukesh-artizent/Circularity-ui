"""The CMDB mock's seed: 70 configuration items, synthetic, computed from the serial's number (no randomness).

`cis()` is pure: the documents as the API serves them, in serial order. The logistics mock imports `PICKUP_1` and
`PICKUP_2` for the serials its manifests list.
"""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.itsm_cmdb.models import CI, metadata

PICKUP_1 = tuple(f"SN-IT-{n:04d}" for n in range(1, 51))
PICKUP_2 = tuple(f"SN-IT-{n:04d}" for n in range(101, 121))
CLASSES = ("laptop", "desktop", "server", "network")
MODELS = {"laptop": "LT-14 G9", "desktop": "DT-30 S5", "server": "SV-2U R7", "network": "SW-48 P2"}
NEW_PRICE = {"laptop": 1400.0, "desktop": 900.0, "server": 6500.0, "network": 2200.0}
MEDIA = {"laptop": ("ssd",), "desktop": ("ssd", "hdd"), "server": ("hdd", "hdd"), "network": ()}


def media_serial(serial: str, k: int) -> str:
    return f"MS-{serial[3:]}-{k}"


def ci(serial: str) -> dict:
    n = int(serial.rsplit("-", 1)[1])
    cls = CLASSES[n % len(CLASSES)]
    leased = n <= 50 and n % 5 == 0
    return {
        "ciId": f"CI{n:05d}",
        "serial": serial,
        "model": MODELS[cls],
        "assetClass": cls,
        "ownerOrg": "Customer A",
        "securityLevel": "high" if n % 7 == 0 else "standard",
        "leaseRef": f"LS-IT-{n:04d}" if leased else None,
        "lessorReturnRequired": leased,
        "consentToResell": not leased,
        "newPrice": NEW_PRICE[cls],
        "media": [{"mediaSerial": media_serial(serial, k), "type": t} for k, t in enumerate(MEDIA[cls], 1)],
    }


def cis() -> list[dict]:
    return [ci(s) for s in (*PICKUP_1, *PICKUP_2)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = cis()
    conn.execute(insert(CI), [{"serial": d["serial"], "doc": d} for d in rows])
    return {"ci": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS itsm_cmdb"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM itsm_cmdb.ci")).scalar_one() == 0:
        load(conn, s)
