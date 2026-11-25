"""Legacy depot repair log (plan 9, P9-3.1): the depot's own log of tool repair orders and teardown verdicts.

    GET {base}/repair-orders | /teardowns

Synthetic, like every mock here. Not a demo source and not Oracle Depot Repair (source `repair`): it is in
sim/core/registry.py EXTRA_SYSTEMS (source id `repairlog`). HTTP Basic (demo user `di-connector`, password
`repairlog-demo`), page paging (`?page=&page_size=`, 1-based; body `items`, `next`, `total`).

The seed is deterministic (md5) and anchored on 2026-10-07: 2,400 closed orders over the three years before it (for
each of the six tool classes and each age band, 60 orders of each of the two commonest faults, so a model that asks
for "50 or more similar repairs" has data), 900 teardown verdicts, 17 closed and graded orders for the returned serials
of the fleet contract system (sim/generic/specs/fleet_contracts.py) and 40 open orders. `CMH-48213`, a returned
serial, has only an open order: its grade is late on purpose.
"""

from datetime import timedelta
from typing import Any

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs import fleet_contracts as fleet
from sim.seed import Seed

h, frac, AS_OF = fleet.h, fleet.frac, fleet.AS_OF
BANDS = ((1, 24), (25, 36), (37, 60))  # age in months: the second is the band the plan's tests read
PER_FAMILY = 400  # closed orders per tool class: 133 + 133 + 134 over the bands
LABOUR_RATE = {"US": 78.0, "UK": 62.0, "DE": 70.0, "FR": 66.0, "AU": 74.0}
# fault codes by class: the first two are the commonest
FAULTS = {
    "CMH": ("MTR-BRUSH-WEAR", "PST-SEAL-LEAK", "CHK-LOOSE", "GBX-NOISE", "SW-FAIL"),
    "BRK": ("PST-SEAL-LEAK", "TOOL-RETAINER", "MTR-BRUSH-WEAR", "HSG-CRACK", "SW-FAIL"),
    "DCD": ("SPIN-BEARING", "WTR-SEAL-LEAK", "MTR-OVERHEAT", "FEED-JAM", "SW-FAIL"),
    "CRH": ("BAT-CONTACT", "MTR-BRUSH-WEAR", "CHK-LOOSE", "GBX-NOISE", "SW-FAIL"),
    "AGR": ("GBX-NOISE", "MTR-BRUSH-WEAR", "GUARD-DAMAGE", "SW-FAIL", "CORD-FRAY"),
    "LSR": ("MOTOR-DRIFT", "LENS-DAMAGE", "LEVEL-CAL", "BAT-CONTACT", "SW-FAIL"),
}  # fmt: skip
# the components of each class, with the rated life in run hours that teardown verdicts are judged against
COMPONENTS = {
    "CMH": (("Motor brushes", 1500), ("Piston seal", 2500), ("Chuck", 3500), ("Gearbox", 5000)),
    "BRK": (("Piston seal", 2200), ("Tool retainer", 3000), ("Motor brushes", 1500), ("Handle damper", 4000)),
    "DCD": (("Spindle bearing", 2800), ("Water seal", 1800), ("Motor", 6000), ("Feed gear", 4500)),
    "CRH": (("Battery contacts", 2000), ("Motor brushes", 1500), ("Chuck", 3500), ("Gearbox", 5000)),
    "AGR": (("Gearbox", 2600), ("Motor brushes", 1500), ("Guard", 5000), ("Cord", 3000)),
    "LSR": (("Motor", 3500), ("Lens", 6000), ("Level vial", 5000), ("Battery contacts", 2000)),
}  # fmt: skip
GRADES = "ABCD"


def _grade(cls: str, age: int, fault_rank: int, *key: object) -> tuple[str, str]:
    """A grade and bench test result: older tools and rarer faults grade lower, a D mostly fails the bench."""
    score = frac("grade", cls, *key) * 2 + age / 60 + (0.3 if fault_rank > 1 else 0.0)
    grade = GRADES[min(3, int(score * 1.1))]
    fail = frac("test", cls, *key) < {"A": 0.02, "B": 0.08, "C": 0.3, "D": 0.7}[grade]
    return grade, "fail" if fail else "pass"


def _order(ro: int, serial: str, cls: str, market: str, age: int, fault: str, closed_on, opened: bool = False) -> dict[str, Any]:
    key = (ro, serial)
    rank = FAULTS[cls].index(fault)
    comps = []
    for name, life in COMPONENTS[cls]:
        replaced = frac("repl", name, *key) < (0.7 if rank < 2 else 0.4)
        hours = int(life * (0.5 + frac("hrs", name, *key)) * min(1.2, 0.4 + age / 36))
        comps.append({"name": name, "replaced": replaced, "runHoursAtReplacement": hours})
    labour = round(0.5 + (h("lab", *key) % 110) / 20, 1)
    parts = round(sum(25 + (life / 20) for (n, life), c in zip(COMPONENTS[cls], comps, strict=True) if c["replaced"]), 2)
    grade, test = (None, None) if opened else _grade(cls, age, rank, *key)
    done = None if opened else closed_on.isoformat()
    return {
        "roId": f"DR-{50000 + ro}", "serial": serial, "toolClass": cls, "market": market, "ageMonths": age,
        "faultCode": fault, "grade": grade, "testResult": test, "gradedAt": done, "components": comps,
        "labourHours": labour, "partsCost": parts, "labourRate": LABOUR_RATE[market],
        "status": "open" if opened else "closed", "closedAt": done,
    }  # fmt: skip


def build() -> dict[str, list[dict]]:
    orders: list[dict] = []
    n = 0
    for cls in fleet.CLASSES:
        sizes = (133, 133, PER_FAMILY - 266)
        for (lo, hi), size in zip(BANDS, sizes, strict=True):
            for k in range(size):
                n += 1
                # 60 of each of the two commonest faults, the rest spread over the other three
                fault = FAULTS[cls][0 if k < 60 else 1 if k < 120 else 2 + (k - 120) % 3]
                age = lo + h("age", n) % (hi - lo + 1)
                days = 3 + h("closed", n) % (3 * 365 - 10)  # within the three years before the anchor
                orders.append(
                    _order(
                        n,
                        f"{cls}-{60000 + n}",
                        cls,
                        fleet.MARKETS[h("m", n) % 5],
                        age,
                        fault,
                        (AS_OF - timedelta(days=days)).date(),
                    )  # fmt: skip
                )
    closed_history = list(orders)

    # the returned serials of the fleet contract system, graded now (the late one is open)
    data = fleet.build()
    line = {x["serial"]: x for x in data["lines"]}
    contract = {c["contractId"]: c for c in data["contracts"]}
    for r in data["returns"]:
        n += 1
        ln = line[r["serial"]]
        cls, market = ln["toolClass"], contract[ln["contractId"]]["market"]
        fault = FAULTS[cls][h("rf", r["serial"]) % 5]
        late = r["serial"] == "CMH-48213"
        age = ln["monthsOnContract"] + 6
        done = (AS_OF - timedelta(days=h("rg", r["serial"]) % 4)).date()
        orders.append(_order(n, r["serial"], cls, market, age, fault, done, opened=late))
    for i in range(40):  # other open orders
        n += 1
        cls = fleet.CLASSES[h("oc", i) % 6]
        orders.append(
            _order(
                n,
                f"{cls}-{70000 + i}",
                cls,
                fleet.MARKETS[h("om", i) % 5],
                1 + h("oa", i) % 60,
                FAULTS[cls][h("of", i) % 5],
                None,
                opened=True,
            )  # fmt: skip
        )

    teardowns = []
    for i in range(900):
        o = closed_history[(i * 2 + 1) % len(closed_history)]
        comp, life = COMPONENTS[o["toolClass"]][h("tdc", i) % 4]
        hours = int(life * (0.3 + frac("tdh", i) * 1.3))
        worn = hours > life * (0.85 + (frac("tdv", i) - 0.5) * 0.3)
        teardowns.append(
            {"tdId": f"TD-{80000 + i}", "serial": o["serial"], "toolClass": o["toolClass"], "component": comp,
             "runHours": hours, "verdict": "worn_out" if worn else "serviceable", "observedAt": o["closedAt"]}
        )  # fmt: skip
    return {"orders": orders, "teardowns": teardowns}


def seed(s: Seed) -> dict[str, list[dict]]:  # noqa: ARG001 - anchored on its own date, as the sandbox
    return build()


SPEC = Spec(
    source_id="repairlog",
    title="Legacy depot repair log (synthetic)",
    schema="repairlog",
    base_path="/repairlog/api",
    auth=Auth("basic"),
    paging=Paging("page", page_param="page", size_param="page_size", items_key="items", next_key="next", total_key="total"),
    resources=(
        Resource("orders", "/repair-orders", "roId", filters=("serial", "status")),
        Resource("teardowns", "/teardowns", "tdId"),
    ),
    seed=seed,
)
