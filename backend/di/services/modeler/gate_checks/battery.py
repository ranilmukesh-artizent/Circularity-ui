"""The dangerous-goods lane gate for battery-bearing equipment (plan 9, P9-10.16, story TN-23). Pure.
Implements the check of registry entry I-2 for the catalogue gate `G-BAT-4`; it runs before any business rule (R20).

    check_battery_lane(case, pack, gate) -> GateResult | None   G-BAT-4

The case's `battery` is the test bench's read of the unit (`chemistry`, `damaged`: the facts `condition.battery_chemistry` and
`condition.battery_damaged`). A unit with no battery fact is left to the gate's data (None).
  - `chemistry == "lithium"`: every shipping route of the pack takes the dangerous-goods lane. The result fails with effect
    `require_step` and the step `dg_lane`, routes the pack's.
  - `damaged` true as well: `resell` fails "Damaged lithium battery: no resale" (effect `block`, step `dg_lane` kept), and a
    standard lane is refused for the rest by the same step.
Never does: read the store or the clock, choose a carrier, or write a case. The ADR and IATA special provisions are unconfirmed in
the pack; the wording needs review by Kinective's Legal team before it is relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

BATTERY_GATE = "G-BAT-4"
STEP_DG = "dg_lane"
REASON_DAMAGED = "Damaged lithium battery: no resale"
REASON_LITHIUM = "Lithium battery: dangerous-goods lane only"
RESELL = "resell"


def check_battery_lane(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-BAT-4 (module docstring); None when the case holds no battery fact for a lithium unit."""
    b = case.get("battery")
    if not isinstance(b, Mapping) or str(b.get("chemistry") or "").lower() != "lithium":
        return None
    routes = tuple(r.id for r in pack.routes)
    if b.get("damaged") is True:
        return GateResult(
            gate.id, False, GateEffect("block", (RESELL,) if RESELL in routes else (), False, STEP_DG), (), REASON_DAMAGED,
            route_reasons=((RESELL, REASON_DAMAGED),),
        )  # fmt: skip
    return GateResult(gate.id, False, GateEffect("require_step", routes, False, STEP_DG), (), REASON_LITHIUM)


CHECKS[BATTERY_GATE] = check_battery_lane
