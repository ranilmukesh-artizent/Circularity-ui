"""The personal and patient data gate `G-DATA-3` for the medical rental pack (plan 9, P9-11.17, story MR-19; registry entry I-2).
Pure.

    check_patient_data_sanitised(case, pack, gate) -> GateResult | None

A device of a class with patient data (`classes[].attrs.patient_data`, the patient monitor) must have a sanitisation record on
file before the disposal partner collects it: the case's `sanitisationRef` (the canonical `condition.sanitisation_record_ref`,
written by the disposal partner's adapter). Without it the result fails, effect `block`, `evidence_missing:
("sanitisation_record",)`, "Sanitisation record required before collection". The writer of `disposal_collection`
(`di.services.instructions.writers`) asks this check and does not send until it passes. Sanitisation is a step of the retire route
itself, so the gate is asked at the collection and never excludes the route at decision time.

The check answers only for the medical rental pack: it returns None for a device with no patient data and for every other pack,
which keep the gate's evidence list (data wipe, controller sign-off). Never does: read the store, the clock or a session, or
write a case. HIPAA 45 CFR 164.310(d) and GDPR Art. 32 are the sources; the wording needs review by Kinective's Legal team before
it is relied on.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from collections.abc import Mapping
from typing import Any

from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack
from di.services.modeler.valuers.medical_steps import patient_data

GATE = "G-DATA-3"
PACK = "medical_rental"
RECORD = "sanitisation_record"


def check_patient_data_sanitised(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-DATA-3 (module docstring); None leaves a device with no patient data, or another pack, to the data."""
    if pack.key != PACK or not patient_data(pack, case):
        return None
    ref = case.get("sanitisationRef")
    if ref:
        return GateResult(
            gate.id,
            True,
            GateEffect("block", (), gate.effect.hold_until_evidence, None),
            (),
            f"Sanitisation record {ref} on file",
        )
    routes = tuple(str(r) for r in gate.params.get("routes") or ())
    return GateResult(
        gate.id, False, GateEffect("block", routes, gate.effect.hold_until_evidence, None), (RECORD,),
        "Sanitisation record required before collection",
    )  # fmt: skip


CHECKS[GATE] = check_patient_data_sanitised
