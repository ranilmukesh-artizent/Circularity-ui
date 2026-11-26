"""The test bench mock's seed: bench results of 40 network elements and 11 power units, synthetic, computed from the serial's
number (no randomness). The pinned units are listed in the package docstring.

`results()` is pure: the documents as the API serves them, in serial order. `HANDLER` completes a wipe job (routes.py).
"""

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.network_inventory.seed import serial
from sim.vendors.test_bench.models import RESULT, metadata

SOURCE = "tn_bench"
HANDLER = "tn_bench.wipe.complete"
WIPE_HOURS = 4
SCOPE = ["configuration", "credentials", "keys", "logs"]
EQUIPMENT = range(1, 41)
POWER = range(100, 111)
TOOL, TOOL_VERSION = "WipeTool-X", "4.2"


def certificate(n: int) -> str:
    return f"WC-{n:04d}"


def _wipe(n: int) -> dict:
    if n in POWER:
        return {"status": "none", "attempts": 0, "tool": None, "toolVersion": None, "scope": [], "verifiedAt": None,
                "certificateRef": None}  # fmt: skip
    if n in (14, 15):  # 0014 failed once, 0015 twice: nothing wiped that counts
        return {"status": "failed", "attempts": n - 13, "tool": TOOL, "toolVersion": TOOL_VERSION, "scope": [],
                "verifiedAt": None, "certificateRef": None}  # fmt: skip
    return {
        "status": "verified", "attempts": 1, "tool": TOOL, "toolVersion": TOOL_VERSION, "scope": list(SCOPE),
        "verifiedAt": f"2026-10-{1 + n % 6:02d}T09:{n % 60:02d}:00Z", "certificateRef": certificate(n),
    }  # fmt: skip


def result(n: int) -> dict:
    power = n in POWER
    firmware, latest = ("5.2", "7.1") if n == 40 else ("3.2", "3.2")
    battery = {"chemistry": "lithium" if n <= 105 else "lead_acid", "damaged": n == 103} if power else None
    boards = [] if power else [
        {"boardId": f"BRD-{n:04d}-{k}", "partNumber": f"PN-BRD-{k}0", "health": "degraded" if (n + k) % 11 == 0 else "good"}
        for k in (1, 2)
    ]  # fmt: skip
    return {
        "serial": serial(n),
        "tests": {"passed": 17 if n % 7 == 0 else 18, "total": 18},
        "firmware": firmware,
        "firmwareLatest": latest,
        "wipe": _wipe(n),
        "boards": boards,
        "weightKg": float(38 + n % 5) if power else 8.0 + (n % 9) * 1.5,
        "battery": battery,
    }


def results() -> list[dict]:
    return [result(n) for n in [*EQUIPMENT, *POWER]]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = results()
    conn.execute(insert(RESULT), [{"serial": d["serial"], "doc": d} for d in rows])
    return {"result": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS test_bench"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM test_bench.result")).scalar_one() == 0:
        load(conn, s)
