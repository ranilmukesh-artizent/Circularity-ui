"""The CPE returns mock's seed: two lots of home routers, their returns and reset records, and the forecast (pinned, no randomness)."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.cpe_returns.models import FORECAST, LOT, RESET, RETURN, metadata

LOTS = (("LOT-R7-B-W47", "2026-W47", 1, 500), ("LOT-R7-B-W48", "2026-W48", 1001, 900))  # id, week, first number, units
NO_RESET = (101, 202, 303)  # serial numbers of lot W47 with no reset record
REASONS = ("upgrade", "contract_end", "fault_swap")
FORECAST_UNITS = {"2026-W47": 600, "2026-W48": 1000}


def serial(n: int) -> str:
    return f"SN-CPE-R7-{n:04d}"


def lots() -> list[dict]:
    return [
        {"lotId": lot, "model": "R7", "grade": "B", "week": week, "serials": [serial(n) for n in range(first, first + units)]}
        for lot, week, first, units in LOTS
    ]


def returns() -> list[dict]:
    out = []
    for _lot, week, first, units in LOTS:
        day = 16 if week.endswith("W47") else 23
        for n in range(first, first + units):
            out.append({
                "serial": serial(n), "model": "R7", "reason": REASONS[n % 3], "subscriberRef": f"SUB-{n:05d}",
                "returnedAt": f"2026-11-{day + n % 5:02d}T09:00:00+00:00",
            })  # fmt: skip
    return out


def resets() -> list[dict]:
    return [
        {"serial": serial(n), "method": "factory_reset", "firmwareRefreshed": True, "at": "2026-11-24T08:00:00+00:00"}
        for _lot, _week, first, units in LOTS
        for n in range(first, first + units)
        if n not in NO_RESET
    ]


def forecast() -> list[dict]:
    return [{"model": "R7", "week": w, "units": u} for w, u in FORECAST_UNITS.items()]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    ls, rs, es, fs = lots(), returns(), resets(), forecast()
    conn.execute(insert(LOT), [{"lot_id": x["lotId"], "doc": x} for x in ls])
    conn.execute(insert(RETURN), [{"serial": x["serial"], "doc": x} for x in rs])
    conn.execute(insert(RESET), [{"serial": x["serial"], "doc": x} for x in es])
    conn.execute(insert(FORECAST), [{"week": x["week"], "doc": x} for x in fs])
    return {"lot": len(ls), "device_return": len(rs), "factory_reset": len(es), "forecast": len(fs)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS cpe_returns"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM cpe_returns.lot")).scalar_one() == 0:
        load(conn, s)
