"""The network inventory match gate (plan 9, P9-10.6, story TN-05). Pure. Implements the check of registry entry I-2 for the
catalogue gate `G-NET-INV` (Data quality, stage match); it runs before any business rule (R20).

    check_inventory_match(case, pack, gate) -> GateResult    G-NET-INV: the serial is in the inventory, with the model and site

The evidence `inventory_match` is the inventory's record of the unit (`di.services.cases.inventory_evidence`: serial, model,
site). The case's `network` holds the removal's model and site (`di.services.cases.intake`). The gate passes when the record
is on file and both agree. Otherwise every route of `params.routes` fails, effect `block` with `hold` (no route is valued),
`evidence_missing: ("inventory_match",)`, the step of the gate's `on_fail`, and the reason says which:
  - "Serial not in network inventory";
  - "Model differs: inventory <a>, removal <b>";
  - "Site differs: inventory <a>, removal <b>".
`gate_hold` raises the exception `EX-TN-INV` for the inventory lead ("Field team to confirm serial and site") and the case
resumes by itself, and the exception closes, when the element appears or is corrected in the inventory (a recheck). An agent
never clears it (`work.resolve` is in `FORBIDDEN_ACTIONS`).

Never does: read the canonical store, the clock or a session, confirm a serial, or write a case.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.evidence import evidence_of
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

INVENTORY_GATE = "G-NET-INV"
INVENTORY_MATCH = "inventory_match"
REASON_UNKNOWN = "Serial not in network inventory"
TEXT_MATCHED = "Unit matches network inventory"


def _routes(gate: GateDef, pack: Pack) -> tuple[str, ...]:
    """The routes the gate affects: the ref's `params.routes` that the pack has (every route of the pack by default)."""
    mine = [r.id for r in pack.routes]
    want = gate.params.get("routes")
    return tuple(r for r in mine if not want or r in want)


def mismatch(inventory: Mapping[str, Any], network: Mapping[str, Any]) -> str | None:
    """Why the inventory's record disagrees with the removal (model first, then site), or None when they agree."""
    for field in ("model", "site"):
        if inventory.get(field) != network.get(field):
            return f"{field.capitalize()} differs: inventory {inventory.get(field)}, removal {network.get(field)}"
    return None


def check_inventory_match(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-NET-INV (module docstring)."""
    e = evidence_of(case, INVENTORY_MATCH)
    why = REASON_UNKNOWN if e is None else mismatch(e.value, case.get("network") or {})
    if why is None:
        return GateResult(gate.id, True, GateEffect("block", (), gate.effect.hold_until_evidence, None), (), TEXT_MATCHED)
    step = gate.effect.on_fail.step if gate.effect.on_fail else gate.effect.step
    return GateResult(
        gate.id, False, GateEffect("block", _routes(gate, pack), gate.effect.hold_until_evidence, step),
        (INVENTORY_MATCH,), why,
    )  # fmt: skip


CHECKS[INVENTORY_GATE] = check_inventory_match
