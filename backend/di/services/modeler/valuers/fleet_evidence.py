"""The tool fleet's evidence checks (plan 9, P9-3.6, story TF-02; later tasks add recall, telematics and life). Pure.

    contract_check(line, owner_org, serial="") -> GateResult   does the contract line give the right to dispose of the tool?
    line_value(line, contract) -> dict                         a canonical `contract_line` as the check reads it
    sample_evidence(case) -> {"contract_line": Evidence}       the complete evidence of a sample-world case

**GR-07, the contract right gate** (catalogue gate `G-CON-2`, the pack's guardrail GR-07, Compliance, locked, stage match).
The line the fleet contract system holds for the serial is the evidence `contract_line`. The check fails, and blocks every
route of the pack, with a reason that names the term:

1. no line: "No active contract for serial <serial>";
2. `theft_recovered` with `theftClaimOpen`: "Theft recovered: claim <claimRef> is open";
3. `damageChargeOpen`: "Damage charge <chargeRef> is open";
4. an `ownerOrg` other than the pack's owner org (`identity.owner`): "Owned by <ownerOrg>, not by this programme" (an owner
   not on file is not a reason);
5. a status other than `active`, unless the line is `returned` for `end_of_term` or `swap` (the contract has run its course
   and the tool is ours to place): "Contract line <lineId> is <status>, not active".

A failed check holds the case until the line changes (`hold_until_evidence`); `di.services.cases.gate_hold` opens the
exception item `no_active_contract` and a later sync of the line releases it. The result's routes are the pack's: the
check registers itself in `gates.CHECKS`, which fills them.

Never does: read the canonical store, the clock or a case (the caller passes the line), write language (the reasons are
fixed text of the line's own terms; no model step), or touch the sample world's numbers: a sample-world case is decided
with `sample_evidence`, an active line, so the gate passes there and the PO goldens keep their numbers.
"""

import dataclasses
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from di.services.modeler.evidence import Evidence, evidence_of
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult, gate_routes
from di.services.modeler.pack import Pack

GATE = "G-CON-2"
CONTRACT_LINE = "contract_line"
RETURNED_OK = ("end_of_term", "swap")  # a returned line for these reasons still gives the right to place the tool
SAMPLE_AT = datetime(2000, 1, 1, tzinfo=UTC)  # the sample world's evidence is on file from before any time it is decided at
FIELDS = {
    "line_id": "lineId", "contract_id": "contractId", "status": "status", "return_reason": "returnReason",
    "theft_claim_open": "theftClaimOpen", "claim_ref": "claimRef", "damage_charge_open": "damageChargeOpen",
    "charge_ref": "chargeRef", "cover_type": "coverType", "cover_active": "coverActive", "swap_allowed": "swapAllowed",
}  # fmt: skip


def _result(passed: bool, reason: str) -> GateResult:
    return GateResult(GATE, passed, GateEffect("block", (), True, None), (), reason)


def contract_check(line: Mapping[str, Any] | None, owner_org: str, serial: str = "") -> GateResult:
    """Whether the contract line gives the right to dispose of the tool (module docstring). `line` has the fleet contract
    system's names (`status`, `returnReason`, `theftClaimOpen`, `claimRef`, `damageChargeOpen`, `chargeRef`, `ownerOrg`)."""
    if not line:
        return _result(False, f"No active contract for serial {serial or '?'}")
    if line.get("returnReason") == "theft_recovered" and line.get("theftClaimOpen"):
        return _result(False, f"Theft recovered: claim {line.get('claimRef') or '?'} is open")
    if line.get("damageChargeOpen"):
        return _result(False, f"Damage charge {line.get('chargeRef') or '?'} is open")
    owner = line.get("ownerOrg")
    if owner and owner != owner_org:
        return _result(False, f"Owned by {owner}, not by this programme")
    status = line.get("status")
    if status != "active" and not (status == "returned" and line.get("returnReason") in RETURNED_OK):
        return _result(False, f"Contract line {line.get('lineId') or '?'} is {status or 'not on file'}, not active")
    return _result(True, f"Active contract line {line.get('lineId') or ''}".strip())


def line_value(line: Mapping[str, Any], contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A canonical `contract_line` (snake case) and its contract as the check reads them: the fleet system's names, the
    contract's `owner_org` as `ownerOrg`."""
    out = {to: line.get(src) for src, to in FIELDS.items()}
    out["serial"] = line.get("serial")
    out["ownerOrg"] = (contract or {}).get("owner_org")
    return out


def _check(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    e = evidence_of(case, CONTRACT_LINE)
    serial = str(case.get("serial") or case.get("assetId") or "")
    res = contract_check(e.value if e is not None else None, pack.owner or "", serial)
    return dataclasses.replace(
        res, gate_id=gate.id, effect=GateEffect(gate.effect.kind, gate_routes(gate, pack), gate.effect.hold_until_evidence, None)
    )


CHECKS[GATE] = _check


def sample_evidence(case: Mapping[str, Any]) -> dict[str, Evidence]:
    """The evidence a sample-world case is decided with: an active contract line for its serial, owned by the programme. (Later
    tasks add no recall, a telematics reading and the case's own life inputs.)"""
    serial = str(case.get("serial") or case.get("id") or "")
    value = {"lineId": f"FL-{serial}", "serial": serial, "status": "active", "returnReason": None, "theftClaimOpen": False,
             "claimRef": None, "damageChargeOpen": False, "chargeRef": None, "ownerOrg": None}  # fmt: skip
    return {CONTRACT_LINE: Evidence(CONTRACT_LINE, "sample", SAMPLE_AT, "pass", value)}
