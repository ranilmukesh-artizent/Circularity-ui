"""The medical rental decontamination gate (plan 9, P9-11.6, story MR-05). Pure. Implements the check of registry entry I-2
for the catalogue gate `G-MED-DECON` (Compliance, stage 2, locked); it runs before any business rule (R20).

    check_decontamination(case, pack, gate) -> GateResult    G-MED-DECON: a decontamination record that ends after check-in

The evidence `decontamination` is the device's decontamination record (`di.services.cases.decon_evidence`: the END of the
cycle, `decon_ended_at`, and the check-in time of the rental system). The gate passes when the record ends LATER than
`checked_in_at` and the cycle did not fail. Otherwise EVERY route of the pack fails, the service route included (to protect
technicians), effect `block`, `evidence_missing: ("decontamination",)`, and the case is held until a valid record arrives:
  - no record on file, or one that ends at or before check-in, or a failed cycle, or no check-in time to compare with:
    "Decontamination record required".
`gate_hold` raises the exception `EX-MR-DECON` for the decontamination lead ("Re-run decontamination; held until the record
exists") and closes it when a valid record lands (X-07 auto-release, per tag). `work.resolve` is in `FORBIDDEN_ACTIONS`: an
agent never clears, waives or approves this gate.

Never does: read the canonical store, the clock or a session, or write a case. The CDC guideline is not re-read, and the MHRA
and NHSScotland wording is unconfirmed; the wording needs review by Kinective's Legal team before it is relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.evidence import evidence_of, parse_time
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult, gate_routes
from di.services.modeler.pack import Pack

DECON_GATE = "G-MED-DECON"
DECONTAMINATION = "decontamination"
REASON = "Decontamination record required"


def check_decontamination(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-MED-DECON (module docstring)."""
    e = evidence_of(case, DECONTAMINATION)
    checked_in = parse_time(e.value.get("checked_in_at")) if e is not None else None
    if e is not None and e.result == "pass" and checked_in is not None and e.at > checked_in:
        return GateResult(
            gate.id, True, GateEffect("block", (), gate.effect.hold_until_evidence, None), (), "Decontamination record on file"
        )
    return GateResult(
        gate.id, False, GateEffect("block", gate_routes(gate, pack), gate.effect.hold_until_evidence, gate.effect.step),
        (DECONTAMINATION,), REASON,
    )  # fmt: skip


CHECKS[DECON_GATE] = check_decontamination
