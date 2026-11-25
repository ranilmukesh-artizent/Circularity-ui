"""The tool fleet's evidence checks (plan 9, P9-3.6, story TF-02; later tasks add recall, telematics and life). Pure.

    contract_check(line, owner_org, serial="") -> GateResult   does the contract line give the right to dispose of the tool?
    line_value(line, contract) -> dict                         a canonical `contract_line` as the check reads it
    sample_evidence(case) -> {"contract_line": Evidence}       the complete evidence of a sample-world case
    recall_check(serial, cls, recalls, released) -> (GateResult, paths, parts)   GR-12, the safety recall check (P9-3.7, below)

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

**GR-12, the safety recall check** (P9-3.7, TF-04; catalogue gate `G-TOOL-REC`, Compliance, locked, stage match). The register's
active notices whose serial range holds the tool's serial (evidence `recall_check`, `recall_check()` below): a `repair` recall
blocks release, redeploy and resell until a person releases the tool after the fix (action `recall.release`); a `replace` or
`refund` recall leaves exit and harvest only and is never released; harvest never certifies a part the notice names. The gate
does not hold the case (it still has a recommendation); it requires the step Quarantine and opens the exception
`recall_quarantine` for Quality (`gate_hold.sync_quarantine`). No model step: the notices and remedies are the register's
own fields.

Never does: read the canonical store, the clock or a case (the caller passes the line), write language (the reasons are
fixed text of the line's own terms; no model step), or touch the sample world's numbers: a sample-world case is decided
with `sample_evidence`, an active line, so the gate passes there and the PO goldens keep their numbers.
"""

import dataclasses
from collections.abc import Mapping, Sequence
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
    return {CONTRACT_LINE: Evidence(CONTRACT_LINE, "sample", SAMPLE_AT, "pass", value)} | recall_sample()


# ---------------------------------------------------------------- the safety recall check (P9-3.7, story TF-04)
RECALL = "recall_check"  # the evidence type: {recalls: [the register's notices for the serial's class], released: {...} | None}
RECALL_GATE = "G-TOOL-REC"  # catalogue gate; the pack's gate ref carries guardrail GR-12 (Compliance, locked, stage match)
QUARANTINE = "Quarantine"  # the step a failed recall check requires
PATH_ORDER = ("release", "refurb", "redeploy", "resell", "harvest", "exit")
REPAIR_BLOCKS = ("release", "redeploy", "resell")  # a repair recall: refurb does the repair, harvest and exit stay
NEVER_BACK = ("release", "refurb", "redeploy", "resell")  # a replace or refund recall: only exit and harvest stay


def _serial_key(serial: str) -> tuple[str, int | None]:
    head = serial.rstrip("0123456789")
    tail = serial[len(head) :]
    return head, int(tail) if tail else None


def _in_range(serial: str, lo: Any, hi: Any) -> bool:
    """The serial lies in the notice's range: the same prefix and a number between the two (else by text order)."""
    if not (lo and hi and serial):
        return False
    (p, n), (p1, n1), (p2, n2) = _serial_key(serial), _serial_key(str(lo)), _serial_key(str(hi))
    if n is not None and n1 is not None and n2 is not None:
        return p == p1 == p2 and n1 <= n <= n2
    return str(lo) <= serial <= str(hi)


def _hits(serial: str, cls: str, recalls: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The active notices of the tool's class whose serial range holds the serial; a closed notice is ignored."""
    return [
        n for n in recalls
        if str(n.get("status") or "").lower() == "active"
        and (not n.get("tool_class") or not cls or n["tool_class"] == cls)
        and _in_range(serial, n.get("serial_from"), n.get("serial_to"))
    ]  # fmt: skip


def _freed(n: Mapping[str, Any], released: Mapping[str, Any] | None) -> bool:
    """A repair recall is freed by a release of its own notice; a replace or refund recall never is."""
    return n.get("remedy") == "repair" and bool(released) and (released or {}).get("recall_id") == n.get("recall_id")


def recall_check(
    serial: str, cls: str, recalls: Sequence[Mapping[str, Any]], released: Mapping[str, Any] | None
) -> tuple[GateResult, frozenset[str], frozenset[str]]:
    """GR-12: the gate result, the blocked paths and the blocked parts of a tool against the register's notices (`recalls`,
    the canonical `recall` names: recall_id, tool_class, serial_from, serial_to, remedy, affected_parts, status). An active
    notice whose range holds the serial:
      `repair`          release, redeploy and resell are blocked until `released` (recall_id, by, at, note) frees the tool;
                        refurb, harvest and exit stay; harvest never certifies a part the notice names (until released);
      `replace`/`refund` only exit and harvest stay (harvest again without the named parts); a release changes nothing.
    A result that fails blocks, does not hold the case, and requires the step Quarantine. The routes are the pack's ids."""
    hits = _hits(serial, cls, recalls)
    open_ = [n for n in hits if not _freed(n, released)]
    if not open_:
        why = (
            f"Safety recall {', '.join(str(n.get('recall_id')) for n in hits)} released by {(released or {}).get('by') or '?'}"
            if hits
            else f"No active safety recall for serial {serial or '?'}"
        )
        return GateResult(RECALL_GATE, True, GateEffect("block", (), False, None), (), why), frozenset(), frozenset()
    open_.sort(key=lambda n: n.get("remedy") == "repair")  # a replace or refund notice speaks first
    paths = {p for n in open_ for p in (REPAIR_BLOCKS if n.get("remedy") == "repair" else NEVER_BACK)}
    parts = frozenset(str(p) for n in open_ for p in n.get("affected_parts") or [])
    texts = [
        f"Safety recall {n.get('recall_id')} (repair): quarantined until Quality releases it"
        if n.get("remedy") == "repair"
        else f"Safety recall {n.get('recall_id')} ({n.get('remedy')}): never released to the fleet; only exit and safe parts"
        for n in open_
    ]
    routes = tuple(p for p in PATH_ORDER if p in paths)
    return (
        GateResult(RECALL_GATE, False, GateEffect("block", routes, False, QUARANTINE), (), "; ".join(texts)),
        frozenset(routes),
        parts,
    )


def _recall_inputs(case: Mapping[str, Any]) -> tuple[str, str, Sequence[Mapping[str, Any]], Mapping[str, Any] | None] | None:
    e = evidence_of(case, RECALL)
    if e is None:
        return None
    serial = str(case.get("serial") or case.get("assetId") or "")
    return serial, str(case.get("cls") or ""), e.value.get("recalls") or [], e.value.get("released")


def blocked_parts(case: Mapping[str, Any]) -> frozenset[str]:
    """The parts harvest never certifies for this case (the parts the recall names, until a repair recall is released)."""
    got = _recall_inputs(case)
    return recall_check(*got)[2] if got else frozenset()


def quarantine_of(case: Mapping[str, Any]) -> dict[str, Any] | None:
    """What the case panel shows of the recall: the notice (a replace or refund notice first), what it blocks now, the parts
    it names and who released it; None when no active notice names the serial."""
    got = _recall_inputs(case)
    if got is None:
        return None
    hits = _hits(got[0], got[1], got[2])
    if not hits:
        return None
    _, paths, parts = recall_check(*got)
    hits.sort(key=lambda n: n.get("remedy") == "repair")
    n = hits[0]
    rel = got[3] if _freed(n, got[3]) else None
    return {
        "recall_id": n.get("recall_id"), "remedy": n.get("remedy"), "blocked": [p for p in PATH_ORDER if p in paths],
        "affected_parts": sorted(str(p) for p in n.get("affected_parts") or []),
        "released": {"by": rel.get("by"), "at": rel.get("at"), "note": rel.get("note")} if rel else None,
    }  # fmt: skip


def _recall_gate(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    got = _recall_inputs(case)
    if got is None:
        return None  # no record: the data path holds "Recall check missing"
    res, _, _ = recall_check(*got)
    mine = {r.id for r in pack.routes}
    return dataclasses.replace(
        res,
        gate_id=gate.id,
        effect=GateEffect(res.effect.kind, tuple(p for p in res.effect.routes if p in mine), False, res.effect.step),
    )


CHECKS[RECALL_GATE] = _recall_gate


def recall_sample() -> dict[str, Evidence]:
    """The sample world has no recall: the register's answer for it is complete and empty."""
    return {RECALL: Evidence(RECALL, "sample", SAMPLE_AT, "pass", {"recalls": [], "released": None})}
