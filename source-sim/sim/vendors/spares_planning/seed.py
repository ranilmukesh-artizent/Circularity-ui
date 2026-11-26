"""The spares planning mock's seed: 5 catalogue models, 20 region and model targets, the six-month need, the spares pool
and 2 open requisitions, synthetic and computed (no randomness). The pinned figures are in the package docstring."""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.spares_planning.models import RECORD, REQUISITION, metadata

REGIONS = ("North", "South", "East", "West")
CATALOGUE = (  # model, new price, generation, failure rate over 12 months
    ("RRU-4410", 9800, "current", 0.12),
    ("BBU-2200", 4200, "previous", 0.18),
    ("RTR-880", 6500, "current", 0.08),
    ("PSU-48", 1100, "current", 0.05),
    ("RAD-7700", 7300, "current", 0.10),
)
CELLS = {  # model -> (target, stock) in REGIONS order
    "RRU-4410": ((4, 2), (3, 3), (2, 2), (3, 1)),
    "BBU-2200": ((2, 2), (2, 2), (1, 1), (2, 1)),
    "RTR-880": ((3, 3), (2, 1), (2, 2), (2, 2)),
    "PSU-48": ((4, 3), (5, 4), (3, 3), (4, 2)),
    "RAD-7700": ((2, 1), (2, 2), (1, 1), (2, 2)),
}
BASE_PROBABILITY = {"RRU-4410": 0.55, "BBU-2200": 0.20, "RTR-880": 0.40, "PSU-48": 0.25, "RAD-7700": 0.35}
NORTH_PSU_IDLE = (41, 50, 60)
NO_NEED = "BBU-2200"
REQUISITIONS = (
    {"reqId": "PR-3301", "region": "West", "model": "PSU-48", "quantity": 3, "status": "open", "createdAt": "2026-09-28"},
    {"reqId": "PR-3302", "region": "North", "model": "RRU-4410", "quantity": 1, "status": "open", "createdAt": "2026-10-02"},
)


def catalogue() -> list[dict]:
    return [{"model": m, "newPrice": p, "generation": g, "failureRate12m": f} for m, p, g, f in CATALOGUE]


def targets() -> list[dict]:
    return [
        {"region": r, "model": m, "target": cells[i][0], "stock": cells[i][1],
         "useProbability12m": round(BASE_PROBABILITY[m] - 0.03 * i, 2)}
        for m, cells in CELLS.items()
        for i, r in enumerate(REGIONS)
    ]  # fmt: skip


def forecast6m() -> list[dict]:
    return [
        {"region": t["region"], "model": t["model"], "need": int(t["target"] * t["useProbability12m"] + 0.5)}
        for t in targets()
        if t["model"] != NO_NEED
    ]


def stock() -> list[dict]:
    units, n = [], 0
    for t in targets():
        for k in range(t["stock"]):
            n += 1
            idle = NORTH_PSU_IDLE[k] if (t["region"], t["model"]) == ("North", "PSU-48") else 5 + (n * 7) % 25
            units.append({"serial": f"SN-SP-{n:04d}", "model": t["model"], "region": t["region"], "idleDays": idle})
    return units


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    docs = {"catalogue": catalogue(), "targets": targets(), "forecast6m": forecast6m(), "stock": stock()}
    ids = {
        "catalogue": lambda d: d["model"],
        "targets": lambda d: f"{d['region']}:{d['model']}",
        "forecast6m": lambda d: f"{d['region']}:{d['model']}",
        "stock": lambda d: d["serial"],
    }
    rows = [{"kind": kind, "rec_id": ids[kind](d), "ord": i, "doc": d} for kind, ds in docs.items() for i, d in enumerate(ds)]
    conn.execute(insert(RECORD), rows)
    conn.execute(insert(REQUISITION), [{"req_id": r["reqId"], "doc": r} for r in REQUISITIONS])
    return {"record": len(rows), "requisition": len(REQUISITIONS)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS spares_planning"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM spares_planning.record")).scalar_one() == 0:
        load(conn, s)
