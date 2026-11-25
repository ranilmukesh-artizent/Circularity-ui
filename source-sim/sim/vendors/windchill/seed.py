"""The Windchill mock's seed: 8 assemblies and the 40 parts they use, all synthetic and computed (no randomness).

Numbers are Windchill-style ten-digit numbers (0000100001 ...), except 5 parts that carry part numbers of the Aras
mock's spare parts (sim/vendors/aras/seed.py EX_BOM), so a where-used across the two PLM systems finds them. Each
assembly uses 6 parts: 5 of its own and one shared with another assembly, so some parts have two parents. Versions,
iterations and lifecycle states vary by position (a few parts are in work or obsolete); the costs are per unit.
The demo seed is not used: this system is not one of the demo's sources.

Tool classes (plan 9, P9-3.3): six more assemblies `TF-CMH` ... `TF-LSR` (one per class of the tool fleet pack) and
their 21 wear parts `TF-<class>-<nn>`, added after the 48 rows above (the industrial rows and their object numbers are
unchanged). Soft attributes, served on the Parts entity set when a part has them:
ASSUMPTION: RatedLifeHours, CriticalityWeight (the weights of a class sum to 1.0) and Critical (bool) sit on a wear
    part; EndOfPartsDate (ISO date) and SuccessorNumber on the class assembly (only CMH and CRH have them); ToolClass
    on both.
ASSUMPTION: the rated lives are illustrative (CMH from the research story A 1.5, the others made up in the same
    range); they are the table the tool fleet pack carries (P9-3.9).
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
# P9-3.3: class -> (assembly name, unit cost, end of parts (date, successor) or None,
#                   wear parts (name, unit cost, rated life h, criticality weight, critical))
TOOL_CLASSES: dict[str, tuple[str, float, tuple[str, str] | None, tuple[tuple[str, float, float, float, bool], ...]]] = {
    "CMH": ("Combihammer, 12 kg class", 1450.0, ("2028-06-30", "TF-CMH2"),
            (("Motor armature", 260.0, 1200, 0.4, True), ("Gearbox", 180.0, 1500, 0.3, True),
             ("Electronics module", 120.0, 2000, 0.2, True), ("Piston and seal kit", 90.0, 600, 0.1, False))),
    "BRK": ("Demolition breaker, 30 kg class", 1900.0, None,
            (("Motor", 380.0, 1000, 0.35, True), ("Impact mechanism", 320.0, 800, 0.35, True),
             ("Chisel holder", 110.0, 500, 0.2, False), ("Handle and vibration damper", 70.0, 300, 0.1, False))),
    "DCD": ("Diamond core drill rig", 3200.0, None,
            (("Drill motor", 900.0, 1500, 0.4, True), ("Gearbox", 420.0, 1800, 0.25, True),
             ("Drill stand", 380.0, 3000, 0.15, False), ("Control electronics", 210.0, 2500, 0.2, True))),
    "CRH": ("Cordless rotary hammer, 22 V", 620.0, ("2027-03-31", "TF-CRH2"),
            (("Brushless motor", 160.0, 1800, 0.5, True), ("Electronics module", 95.0, 2500, 0.3, True),
             ("Chuck assembly", 45.0, 900, 0.2, False))),
    "AGR": ("Angle grinder, 230 mm", 260.0, None,
            (("Armature", 70.0, 300, 0.5, True), ("Gear set", 38.0, 450, 0.3, True),
             ("On/off switch", 22.0, 600, 0.2, False))),
    "LSR": ("Rotating construction laser", 1100.0, None,
            (("Laser module", 320.0, 5000, 0.5, True), ("Rotor head", 170.0, 4000, 0.3, True),
             ("Receiver", 110.0, 3000, 0.2, False))),
}  # fmt: skip
SOFT_KEYS = ("rated_life_hours", "criticality_weight", "critical", "end_of_parts_date", "successor_number", "tool_class")


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


def _tool_number(cls: str, i: int | None = None) -> str:
    return f"TF-{cls}" if i is None else f"TF-{cls}-{i:02d}"


def tool_parts(first: int) -> list[dict]:
    """The tool classes' rows (object numbers from `first`): the 6 assemblies, then their 21 wear parts."""
    soft = dict.fromkeys(SOFT_KEYS)
    asm, wear = [], []
    for cls, (name, cost, eop, comps) in TOOL_CLASSES.items():
        end, succ = eop or (None, None)
        asm.append({"number": _tool_number(cls), "name": name, "unit_cost": cost, "tool_class": cls,
                    "end_of_parts_date": end, "successor_number": succ})  # fmt: skip
        for i, (cname, ccost, hours, weight, critical) in enumerate(comps, 1):
            wear.append({"number": _tool_number(cls, i), "name": cname, "unit_cost": ccost, "tool_class": cls,
                         "rated_life_hours": float(hours), "criticality_weight": weight, "critical": critical})  # fmt: skip
    return [
        {"id": f"OR:wt.part.WTPart:{first + i}", "version": "A", "iteration": "1", "state": "RELEASED"} | soft | r
        for i, r in enumerate(asm + wear)
    ]


def tool_usages(first: int) -> list[dict]:
    """The usage links of the 6 tool assemblies (the first has object number `first`): each uses its wear parts once."""
    rows = []
    for k, (cls, (_name, _cost, _eop, comps)) in enumerate(TOOL_CLASSES.items()):
        for line in range(1, len(comps) + 1):
            rows.append(
                {"id": f"OR:wt.part.WTPartUsageLink:{300001 + 10 * k + line}", "parent_id": f"OR:wt.part.WTPart:{first + k}",
                 "child_number": _tool_number(cls, line), "quantity": 1.0, "line_number": line * 10}
            )  # fmt: skip
    return rows


def parts() -> list[dict]:
    """The WTPart rows: the 8 assemblies first, then the 40 parts, then the tool classes (P9-3.3)."""
    rows = []
    named = [(a.number, a.name) for a in ASSEMBLIES] + list(zip(_part_numbers(), (n for _, n in PART_NAMES), strict=True))
    for i, (number, name) in enumerate(named):
        n = FIRST + i
        version, iteration, state = _version(n)
        cost = 1800.0 + (n * 7919) % 42000 if i < len(ASSEMBLIES) else 40.0 + (n * 3571) % 2400
        rows.append(
            {"id": f"OR:wt.part.WTPart:{n}", "number": number, "name": name, "version": version,
             "iteration": iteration, "state": state, "unit_cost": float(cost)}
            | dict.fromkeys(SOFT_KEYS)
        )  # fmt: skip
    return rows + tool_parts(FIRST + len(rows))


def usages() -> list[dict]:
    rows = []
    for k, a in enumerate(ASSEMBLIES):
        for line, (child, qty) in enumerate(a.uses, 1):
            rows.append(
                {"id": f"OR:wt.part.WTPartUsageLink:{200001 + 10 * k + line}", "parent_id": f"OR:wt.part.WTPart:{FIRST + k}",
                 "child_number": child, "quantity": float(qty), "line_number": line * 10}
            )  # fmt: skip
    return rows + tool_usages(FIRST + len(ASSEMBLIES) + len(PART_NAMES))


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
    elif not conn.execute(text("SELECT 1 FROM windchill.wtpart WHERE number = 'TF-CMH'")).first():
        reset(conn, s)  # a database from before P9-3.3: no tool classes (and no soft attribute columns)
