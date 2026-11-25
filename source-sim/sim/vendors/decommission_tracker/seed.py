"""The decommission tracker mock's seed: 12 removal jobs and 2 site demands, synthetic, fixed (no randomness).

Eleven jobs remove three network elements each (`SN-TN-0001` ... `0033`, the ones the inventory holds as removed, at the
site the inventory gives them). Job `RJ-09` removes eight serials, `SN-TN-0201` ... `0208`, that the inventory does not
hold: `0201` joins it one simulated day after a reset, the other seven never do.
"""

from datetime import date, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.decommission_tracker.models import REMOVAL_JOB, SITE_DEMAND, metadata
from sim.vendors.network_inventory import seed as inventory

AS_OF = date(2026, 10, 7)
PROGRAMMES = ("site_swap", "decommission", "reimbursement_programme")
UNKNOWN_JOB = 9
UNKNOWN_SERIALS = range(201, 209)


def _job(j: int) -> dict:
    if j == UNKNOWN_JOB:
        site = "SITE-301"
        units = [
            {"serial": inventory.serial(n), "model": inventory.MODELS[(n - 201) % len(inventory.MODELS)][0]}
            for n in UNKNOWN_SERIALS
        ]
    else:
        first = (j - (1 if j < UNKNOWN_JOB else 2)) * 3 + 1  # job 1 -> 1..3, job 2 -> 4..6, job 10 -> 25..27
        els = [inventory.element(n) for n in range(first, first + 3)]
        site, units = els[0]["site"], [{"serial": e["serial"], "model": e["model"]} for e in els]
    return {
        "jobId": f"RJ-{j:02d}",
        "siteId": site,
        "removedAt": (AS_OF - timedelta(days=3 * (13 - j))).isoformat(),
        "programme": PROGRAMMES[(j - 1) % 3],
        "units": units,
    }


def jobs() -> list[dict]:
    return [_job(j) for j in range(1, 13)]


def demands() -> list[dict]:
    return [
        {"demandId": "SD-112", "siteId": "SITE-112", "model": "RRU-4410", "minFirmwareMajor": None,
         "needBy": "2026-11-15", "region": "North"},
        {"demandId": "SD-207", "siteId": "SITE-207", "model": "RTR-880", "minFirmwareMajor": 7,
         "needBy": "2026-11-30", "region": "East"},
    ]  # fmt: skip


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    conn.execute(insert(REMOVAL_JOB), [{"job_id": d["jobId"], "doc": d} for d in jobs()])
    conn.execute(insert(SITE_DEMAND), [{"demand_id": d["demandId"], "doc": d} for d in demands()])
    return {"removal_job": 12, "site_demand": 2}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS decommission_tracker"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM decommission_tracker.removal_job")).scalar_one() == 0:
        load(conn, s)
