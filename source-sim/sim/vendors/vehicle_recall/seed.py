"""The vehicle recall mock's seed: four (campaign, VIN) rows, synthetic and fixed (no randomness).

`recalls()` is pure: the bulk-list documents in seed order. The pinned cars are listed in the package docstring.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.vehicle_recall.models import RECALL, metadata

AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
CAMPAIGNS = {
    "SYN-24V-001": ("Fuel pump relay", "Relay may overheat and stall the engine; the dealer replaces it free of charge."),
    "SYN-25V-014": ("Rear brake line clip", "Clip may loosen and rub the brake line; the dealer refits it free of charge."),
}
# (campaign, car number, remedy reference or None while open, date remedied)
ROWS = (
    ("SYN-24V-001", 2, None, None),
    ("SYN-24V-001", 50, None, None),
    ("SYN-24V-001", 55, None, None),
    ("SYN-25V-014", 60, "RR-0060", "2026-08-18"),
)


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def recalls() -> list[dict]:
    out = []
    for i, (campaign, n, remedy, remedied_on) in enumerate(ROWS):
        component, summary = CAMPAIGNS[campaign]
        out.append(
            {
                "campaignId": campaign,
                "vin": vin(n),
                "status": "open" if remedy is None else "remedied",
                "component": component,
                "summary": summary,
                "remedyAvailable": True,
                "remedyRef": remedy,
                "remediedAt": remedied_on,
                "updatedAt": (AS_OF - timedelta(minutes=len(ROWS) - 1 - i)).isoformat(),
            }
        )
    return out


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [
        {"campaign_id": d["campaignId"], "vin": d["vin"], "doc": d, "updated_at": datetime.fromisoformat(d["updatedAt"])}
        for d in recalls()
    ]
    conn.execute(insert(RECALL), rows)
    return {"recall": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS vehicle_recall"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM vehicle_recall.recall")).scalar_one() == 0:
        load(conn, s)
