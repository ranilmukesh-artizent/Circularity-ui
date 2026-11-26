"""The ITAD logistics mock's seed: two pickups and the erasure records of the received media (pinned, no randomness)."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.itad_logistics.models import ERASURE, PICKUP, metadata
from sim.vendors.itsm_cmdb import seed as cmdb

EXTRA_SERIAL = "SN-IT-9999"  # received, on no manifest
NOT_RECEIVED = ("SN-IT-0017", "SN-IT-0042")  # on PU-01's manifest, never arrived
CUSTODY = (
    {"event": "picked_up", "at": "2026-11-02T08:00:00+00:00", "by": "driver-d1"},
    {"event": "in_transit", "at": "2026-11-02T16:00:00+00:00", "by": "carrier-c1"},
    {"event": "received", "at": "2026-11-03T09:00:00+00:00", "by": "dock-w1"},
)
CLEAR_ONLY = "SN-IT-0004"  # an SSD cleared, not purged
FAILED = "SN-IT-0008"  # an SSD whose purge failed verification


def pickups() -> list[dict]:
    first = [s for s in cmdb.PICKUP_1 if s not in NOT_RECEIVED] + [EXTRA_SERIAL]
    return [
        {"pickupId": "PU-01", "manifest": list(cmdb.PICKUP_1), "custody": [dict(c) for c in CUSTODY], "received": first},
        {"pickupId": "PU-02", "manifest": list(cmdb.PICKUP_2), "custody": [dict(c) for c in CUSTODY],
         "received": list(cmdb.PICKUP_2)},
    ]  # fmt: skip


def erasures() -> list[dict]:
    out = []
    for p in pickups():
        for serial in p["received"]:
            if serial == EXTRA_SERIAL:
                continue
            for k, kind in enumerate(cmdb.MEDIA[cmdb.ci(serial)["assetClass"]], 1):
                method, verification = ("purge" if kind == "ssd" else "clear"), "passed"
                if serial == CLEAR_ONLY and kind == "ssd":
                    method = "clear"
                if serial == FAILED and kind == "ssd":
                    verification = "failed"
                out.append({
                    "mediaSerial": cmdb.media_serial(serial, k), "method": method, "tool": "EraseKit",
                    "toolVersion": "4.2.1", "verification": verification, "operatorRef": "OP-117",
                    "at": "2026-11-03T14:00:00+00:00",
                })  # fmt: skip
    return out


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    ps, es = pickups(), erasures()
    conn.execute(insert(PICKUP), [{"pickup_id": p["pickupId"], "doc": p} for p in ps])
    conn.execute(insert(ERASURE), [{"media_serial": e["mediaSerial"], "doc": e} for e in es])
    return {"pickup": len(ps), "erasure": len(es)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS itad_logistics"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM itad_logistics.pickup")).scalar_one() == 0:
        load(conn, s)
