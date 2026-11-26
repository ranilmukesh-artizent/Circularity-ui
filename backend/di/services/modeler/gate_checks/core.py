"""Core acceptance for the automotive cores pack (plan 9, P9-12.8, stories NS-CORE-01 and NS-CORE-03; registry entry I-2). Pure.

    core_credit(core, pack) -> {"credit": "full" | "partial" | "none", "pct": int, "failed": [check ids]}
    check_core_acceptance(case, pack, gate) -> GateResult | None        CORE-ACCEPT
    fraud_evidence(core) -> [evidence record]                           what the X-15 triage reads (source `core_ret`)

The acceptance criteria are data: the `acceptance` parameter of the pack gate `CORE-ACCEPT`, one entry per part number
(`{required: [check ids], partial_allowed: [check ids]}`), and `partial_pct` (the credit of a partial core, 50). A core is the
case's `core` (`{coreId, dealerId, declaredPartNumber, observedPartNumber, deposit, checks, receivedAt, dealerRejects}`, what
the adapter `core_ret` writes). Credit is `full` when every required check passes, `partial` when the checks that fail are all
allowed to, `none` otherwise (a part with no criteria, a failed check the part does not allow, a check the system did not
report). A `none` core closes remanufacturing (effect `block`, route `reman`) and names the failed checks; a partial one
discloses the failed checks and the share credited.

`fraud_evidence` turns the same core into the two evidence records the pack's fraud rules read: `quote_check` (the part family
declared against the family observed; a family is the part number's prefix) and `dealer_history` (the dealer's rejects in 30 and
90 days). Never does: read the store or the clock, hold a case (the hold is `fraud.hold`, released only by a person), or decide
a credit memo. Credit terms are commercial and need review by Kinective's Legal team before they are relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

GATE = "CORE-ACCEPT"
SOURCE = "core_ret"  # the source id the evidence names (and the fraud rules' `source`)
REMAN = "reman"
DEFAULT_PARTIAL_PCT = 50


def _gate_params(pack: Pack) -> Mapping[str, Any]:
    ref = next((g for g in pack.gates if g.id == GATE), None)
    return ref.params if ref is not None else {}


def family_of(part_number: Any) -> str:
    """The part family: the part number's prefix (`ALT-1450` -> `ALT`)."""
    return str(part_number or "").split("-", 1)[0].strip().upper()


def core_credit(core: Mapping[str, Any], pack: Pack) -> dict[str, Any]:
    """The credit of the core under the pack's criteria for its declared part number (module docstring)."""
    params = _gate_params(pack)
    rule = (params.get("acceptance") or {}).get(str(core.get("declaredPartNumber")))
    if rule is None:
        return {"credit": "none", "pct": 0, "failed": []}
    checks = core.get("checks") or {}
    failed = [c for c in rule.get("required", []) if checks.get(c) is not True]
    if not failed:
        return {"credit": "full", "pct": 100, "failed": []}
    if set(failed) <= set(rule.get("partial_allowed", [])):
        return {"credit": "partial", "pct": int(params.get("partial_pct", DEFAULT_PARTIAL_PCT)), "failed": failed}
    return {"credit": "none", "pct": 0, "failed": failed}


def check_core_acceptance(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """CORE-ACCEPT (module docstring); None when the case holds no core record (the gate's data answers: evidence missing)."""
    core = case.get("core")
    if pack.key != "auto_core" or not isinstance(core, Mapping):
        return None
    got = core_credit(core, pack)
    allow = GateEffect("block", (), False, None)
    if got["credit"] == "full":
        return GateResult(gate.id, True, allow, (), "Core accepted: full credit")
    if got["credit"] == "partial":
        note = f"Partial credit {got['pct']}%: {', '.join(got['failed'])} failed"
        return GateResult(gate.id, True, allow, (), note, disclosures=(note,))
    why = ", ".join(got["failed"]) or f"no acceptance criteria for {core.get('declaredPartNumber')}"
    return GateResult(gate.id, False, GateEffect("block", (REMAN,), False, None), (), f"Core rejected, no credit: {why}")


def fraud_evidence(core: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The evidence records of the core for the X-15 triage: the part family declared and observed, and the dealer's rejects."""
    at = core.get("receivedAt")
    declared, observed = family_of(core.get("declaredPartNumber")), family_of(core.get("observedPartNumber"))
    rejects = dict(core.get("dealerRejects") or {})
    return [
        {"type": "quote_check", "source": SOURCE, "at": at, "result": "pass" if declared == observed else "fail",
         "value": {"declared": {"model": declared}, "received": {"model": observed}}},
        {"type": "dealer_history", "source": SOURCE, "at": at, "result": "fail" if any(rejects.values()) else "pass",
         "value": {"dealer": core.get("dealerId"), "rejected": rejects}},
    ]  # fmt: skip


CHECKS[GATE] = check_core_acceptance
