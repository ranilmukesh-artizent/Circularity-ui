"""The trade-in register mock's seed: 12 trade-ins, synthetic, computed from the tag's number (no randomness).

`tradeins()` is pure: the documents as the API serves them, in tag order.
"""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.medical_tradein.models import TRADEIN, metadata

COUNT = 12
CLASSES = ("imaging_system", "patient_monitor", "infusion_pump", "ventilator")
MODELS = {"imaging_system": "CT-64 X2", "patient_monitor": "PM-12 V3", "infusion_pump": "IP-200", "ventilator": "VT-7 P1"}
PATIENT_DATA = ("imaging_system", "patient_monitor")


def tradein(n: int) -> dict:
    cls = CLASSES[n % len(CLASSES)]
    market = "US" if n % 2 else "EU"
    return {
        "tag": f"SYN-MC-{n:04d}",
        "deviceClass": cls,
        "model": MODELS[cls],
        "udi": None if n % 5 == 0 else f"(01)0000000{n:04d}(11)260101",
        "singleUse": n % 6 == 0,
        "hasPatientData": cls in PATIENT_DATA,
        "market": market,
        "targetMarket": ("EU" if market == "US" else "US") if n % 3 == 0 else market,
        "serviceRecordRef": None if n % 4 == 0 else f"SR-{n:04d}",
        "recallsClosed": n % 7 != 0,
    }


def tradeins() -> list[dict]:
    return [tradein(n) for n in range(1, COUNT + 1)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = tradeins()
    conn.execute(insert(TRADEIN), [{"tag": d["tag"], "doc": d} for d in rows])
    return {"tradein": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS medical_tradein"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM medical_tradein.tradein")).scalar_one() == 0:
        load(conn, s)
