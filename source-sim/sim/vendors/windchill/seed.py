"""The Windchill mock's seed: 8 assemblies and the 40 parts they use, all synthetic and computed (no randomness).

Numbers are Windchill-style ten-digit numbers (0000100001 ...), except 5 parts that carry part numbers of the Aras
mock's spare parts (sim/vendors/aras/seed.py EX_BOM), so a where-used across the two PLM systems finds them. Each
assembly uses 6 parts: 5 of its own and one shared with another assembly, so some parts have two parents. Versions,
iterations and lifecycle states vary by position (a few parts are in work or obsolete); the costs are per unit.
The demo seed is not used: this system is not one of the demo's sources.
"""

from dataclasses import dataclass

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.windchill.models import USAGE, WTPART, metadata

FIRST = 100001  # the first part's object number and number
STATES = {"INWORK": "In Work", "RELEASED": "Released", "OBSOLETE": "Obsolete"}
ASSEMBLY_NAMES = (
    "Gear motor drive unit", "Hydraulic power unit", "Conveyor drive module", "Control cabinet",
    "Compressor skid", "Cooling fan unit", "Spindle head", "Pump and valve block",
)  # fmt: skip
# (number or None for a Windchill number, name); the 5 numbers are the Aras mock's (sim/vendors/aras/seed.py EX_BOM)
PART_NAMES: tuple[tuple[str | None, str], ...] = (
    ("VLT-SK-250M", "Seal kit"), (None, "Drive shaft"), (None, "Coupling half"), (None, "Key and keeper set"),
    (None, "Gear set"), (None, "Motor mounting plate"), (None, "Brake module"), (None, "Fan guard"),
    ("VLT-TB-55", "Terminal block and gasket"), (None, "Pressure relief valve"), (None, "Hose assembly"),
    (None, "Filter element"), (None, "Reservoir cap"), (None, "Level sensor"), (None, "Pressure gauge"),
    (None, "Mounting bracket"), ("HH-SSK-9", "Shaft seal kit"), (None, "Return roller"), (None, "Belt tensioner"),
    (None, "Drive pulley"), (None, "Contactor"), (None, "Circuit breaker"), (None, "Cable harness"),
    (None, "Relay module"), ("OC-PS-24", "Power supply 24 V 10 A"), (None, "Pressure switch"), (None, "Intake valve"),
    (None, "Oil separator"), (None, "Fan blade"), (None, "Fan motor"), (None, "Shroud"), (None, "Vibration damper"),
    ("TT-CB-18", "Carbon brushes (pair)"), (None, "Tool holder"), (None, "Drawbar spring"), (None, "Spindle bearing"),
    (None, "Valve body"), (None, "Solenoid coil"), (None, "Check valve"), (None, "Manifold gasket"),
)  # fmt: skip
ARAS_NUMBERS = tuple(n for n, _ in PART_NAMES if n)


@dataclass(frozen=True)
class Assembly:
    number: str
    name: str
    uses: tuple[tuple[str, int], ...]  # (child number, quantity) in line order


def _number(n: int) -> str:
    return f"{n:010d}"


def _version(n: int) -> tuple[str, str, str]:
    """(version, iteration, state) of the part with object number n."""
    i = n - FIRST
    state = "OBSOLETE" if i % 11 == 10 else "INWORK" if i % 7 == 6 else "RELEASED"
    return "ABC"[i % 3], str(1 + i % 2), state


def _part_numbers() -> list[str]:
    start = FIRST + len(ASSEMBLY_NAMES)
    return [num or _number(start + i) for i, (num, _name) in enumerate(PART_NAMES)]


def _assemblies() -> tuple[Assembly, ...]:
    nums = _part_numbers()
    out = []
    for k, name in enumerate(ASSEMBLY_NAMES):
        own = [(nums[(5 * k + j) % 40], 1 + (k + j) % 3) for j in range(5)]
        out.append(Assembly(_number(FIRST + k), name, (*own, (nums[(5 * k + 12) % 40], 1))))
    return tuple(out)


ASSEMBLIES = _assemblies()


def parts() -> list[dict]:
    """The WTPart rows: the 8 assemblies first, then the 40 parts."""
    rows = []
    named = [(a.number, a.name) for a in ASSEMBLIES] + list(zip(_part_numbers(), (n for _, n in PART_NAMES), strict=True))
    for i, (number, name) in enumerate(named):
        n = FIRST + i
        version, iteration, state = _version(n)
        cost = 1800.0 + (n * 7919) % 42000 if i < len(ASSEMBLIES) else 40.0 + (n * 3571) % 2400
        rows.append(
            {"id": f"OR:wt.part.WTPart:{n}", "number": number, "name": name, "version": version,
             "iteration": iteration, "state": state, "unit_cost": float(cost)}
        )  # fmt: skip
    return rows


def usages() -> list[dict]:
    rows = []
    for k, a in enumerate(ASSEMBLIES):
        for line, (child, qty) in enumerate(a.uses, 1):
            rows.append(
                {"id": f"OR:wt.part.WTPartUsageLink:{200001 + 10 * k + line}", "parent_id": f"OR:wt.part.WTPart:{FIRST + k}",
                 "child_number": child, "quantity": float(qty), "line_number": line * 10}
            )  # fmt: skip
    return rows


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    p, u = parts(), usages()
    conn.execute(insert(WTPART), p)
    conn.execute(insert(USAGE), u)
    return {"WTPart": len(p), "WTPartUsageLink": len(u)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS windchill"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM windchill.wtpart")).scalar_one() == 0:
        load(conn, s)
