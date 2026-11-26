"""The parts supplier portal mock's seed: the parts of the 8 device models, fixed (no randomness).

`parts()` is pure: the documents as the API serves them, in model then list order. The pinned prices are in the package
docstring. A harvested part is worth 70 % of the price of a new one, in whole currency units.
"""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.parts_portal.models import PART, metadata

HARVEST_SHARE = 0.7
PUMP_PARTS = (("MOT", "Pump motor", 240, 5), ("CTL", "Controller", 310, 9), ("KEY", "Keypad assembly", 45, 3))
MODELS = (  # device model (the asset management mock's), part number code, (part code, label, price, lead days) ...
    ("Synthetic Volumetric Pump V2", "V2", PUMP_PARTS),
    ("Synthetic Smart Pump S4", "S4", PUMP_PARTS),
    ("Synthetic Bedside Monitor B1", "B1", (("DSP", "Display module", 420, 7), ("PSU", "Power supply", 95, 3))),
    ("Synthetic Bedside Monitor B2", "B2", (("DSP", "Display module", 450, 7), ("PSU", "Power supply", 95, 3))),
    ("Synthetic Care Bed C3", "C3", (("ACT", "Bed actuator", 260, 6), ("HND", "Hand control", 70, 3))),
    ("Synthetic Syringe Driver D1", "D1", (("MOT", "Drive motor", 180, 5), ("CTL", "Controller", 220, 8))),
    ("Synthetic Transport Ventilator T2", "T2", (("TRB", "Turbine", 640, 12), ("CTL", "Controller", 410, 10))),
    ("Synthetic Pulse Oximeter P1", "P1", (("SNS", "Finger sensor", 60, 2), ("DSP", "Display module", 85, 4))),
)  # fmt: skip


def parts() -> list[dict]:
    return [
        {
            "partNo": f"PRT-{code}-{part}", "label": label, "price": price, "leadDays": lead,
            "harvestValue": round(price * HARVEST_SHARE), "model": model,
        }
        for model, code, items in MODELS
        for part, label, price, lead in items
    ]  # fmt: skip


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    docs = parts()
    seen: dict[str, int] = {}
    rows = []
    for d in docs:
        rows.append({"model": d["model"], "part_no": d["partNo"], "ord": seen.get(d["model"], 0), "doc": d})
        seen[d["model"]] = seen.get(d["model"], 0) + 1
    conn.execute(insert(PART), rows)
    return {"part": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS parts_portal"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM parts_portal.part")).scalar_one() == 0:
        load(conn, s)
