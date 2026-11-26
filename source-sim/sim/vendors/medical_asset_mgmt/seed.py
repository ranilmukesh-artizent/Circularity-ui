"""The asset management mock's seed: 80 devices, synthetic, computed from the tag's number (no randomness).

`devices()` is pure: the documents as the API serves them, in tag order. The pinned device is in the package docstring.
"""

from datetime import date, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.medical_asset_mgmt.models import DEVICE, metadata

AS_OF = date(2026, 10, 7)  # the demo's as-of date: ages count from it
CLASSES = (  # class, code, count, price new, models
    ("infusion_pump", "IP", 50, 2300, ("Synthetic Volumetric Pump V2", "Synthetic Smart Pump S4")),
    ("patient_monitor", "PM", 8, 4200, ("Synthetic Bedside Monitor B1", "Synthetic Bedside Monitor B2")),
    ("electric_bed", "EB", 8, 3100, ("Synthetic Care Bed C3",)),
    ("syringe_driver", "SD", 6, 1900, ("Synthetic Syringe Driver D1",)),
    ("transport_ventilator", "TV", 4, 7800, ("Synthetic Transport Ventilator T2",)),
    ("pulse_oximeter", "PO", 4, 600, ("Synthetic Pulse Oximeter P1",)),
)
PINNED = {"SYN-MR-IP-0001": {"age": 3, "book": 1150, "residual": 1100}}


def _device(cls: str, code: str, k: int, price: int, models: tuple[str, ...]) -> dict:
    tag = f"SYN-MR-{code}-{k:04d}"
    pin = PINNED.get(tag)
    age = pin["age"] if pin else (k * 7) % 9 + 1  # whole years in service
    days = 0 if pin else (k * 17) % 200  # on top of the whole years
    book = pin["book"] if pin else round(price * (1 - 0.1 * age) / 10) * 10
    residual = pin["residual"] if pin else round(book * 0.9 / 10) * 10
    return {
        "tag": tag,
        "serial": f"SN-{code}-{k:05d}",
        "model": models[k % len(models)],
        "deviceClass": cls,
        "manufacturerCode": f"MFR-{'ABC'[k % 3]}",
        "inServiceDate": (AS_OF.replace(year=AS_OF.year - age) - timedelta(days=days)).isoformat(),
        "bookValue": book,
        "residualSaleValue": residual,
        "hasPatientData": cls == "patient_monitor",
    }


def devices() -> list[dict]:
    return [_device(cls, code, k, price, models) for cls, code, count, price, models in CLASSES for k in range(1, count + 1)]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [{"tag": d["tag"], "ord": i, "device_class": d["deviceClass"], "doc": d} for i, d in enumerate(devices())]
    conn.execute(insert(DEVICE), rows)
    return {"device": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS medical_asset_mgmt"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM medical_asset_mgmt.device")).scalar_one() == 0:
        load(conn, s)
