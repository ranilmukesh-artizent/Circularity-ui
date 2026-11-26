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

The configuration wipe gate (P9-10.7, story TN-06) and the covered-equipment gate (P9-10.7, story TN-09) are here too:

    check_config_wipe(case, pack, gate) -> GateResult        G-NET-CFG: a verified wipe of configuration, credentials, keys, logs
    check_covered_equipment(case, pack, gate) -> GateResult  G-NET-COV: a covered unit is disposed of only

G-NET-CFG (stage 3, locked) reads the `config_wipe` evidence, the test bench's own read of the unit
(`di.services.cases.bench_evidence`, source `tn_bench`): it passes when the wipe is `verified`, carries a certificate and its
scope holds `WIPE_SCOPE`. Otherwise (no certificate, a failed wipe, a scope that falls short) every route
of the pack fails "Configuration wipe certificate missing or failed", effect `block` with `hold` and `evidence_missing:
("config_wipe",)`; `gate_hold` raises `EX-TN-CFG` for the test bench lead ("Re-run the wipe; units held") and the case
resumes by itself when the bench reports a verified wipe. A wipe that failed `params.fail_limit` times (default 2) also
requires the step `destroy_storage`, and `resell` fails with its own text "Wipe failed twice: storage destroyed, no resale".

G-NET-COV (stage 2) reads the inventory's manufacturer and region (`inventory_match`) and the removal's programme
(`case.network.facts`). The unit is covered when the manufacturer is in `params.covered_manufacturers`, the programme is
`params.programme` and the region is in `params.regions`. A covered unit may only be disposed of: the routes of `params.blocks`
(redeploy, spare, resell, harvest) fail "Covered equipment: dispose only" (effect `block`, no hold), and recycling requires the
step `disposal_record` until a `disposal_record` evidence record is on file. The rules are data of the pack; Kinective's Legal
team reviews the wording before it is relied on (NIST SP 800-88 Rev. 2 and IEEE 2883 for the wipe; 47 CFR 1.50004 for covered
equipment: the disposal method is unconfirmed, so the gate assumes no reuse of any kind). An agent never clears, waives or
approves either gate (`work.resolve` is in `FORBIDDEN_ACTIONS`).

The export control gate (P9-10.8, stories TN-03, TN-07, TN-08) is here too:

    check_export_control(case, pack, gate) -> GateResult     G-NET-EXP: resale of a controlled or unclassified unit

G-NET-EXP (stage 4) reads the `export_classification` evidence (`di.services.cases.export_evidence`: the class the inventory
confirmed with its source, the class it only inferred from the part number, and the best broker bid with its end-user
screening). It applies to the routes of `params.routes` (`resell`); every other route carries the note "not triggered for
reuse" (`GateResult.route_notes`). The unit needs trade compliance when its confirmed class is in `params.controlled_classes`,
or when it has no confirmed class and an inferred one (`params.inferred_counts_as_missing`: an inferred class counts as
missing; the code never promotes it). A unit with a class outside the list, or with no class and no inference, passes. For a
unit that needs it:
  - no bid with `endUserScreening.result == "clear"`: `resell` fails "Destination and end-user screening not on file" (effect
    `block`, no hold);
  - else effect `require_approval` on `resell` with the step "Trade compliance approval": `resell` stays valued, and
    `gate_hold` opens the approval `AP-TN-EXP` for the role of `params.approver` (`di.services.cases.export_approval`).
Only a person approves it, classifies the unit or releases it: `decision.approve`, `decision.override`, `mapping.answerOwner`
and `work.resolve` are in `FORBIDDEN_ACTIONS`. The rules are data of the pack (15 CFR 730-774, 740.17(b)(2); Reg. (EU)
2021/821 Annex I as replaced by Delegated Reg. (EU) 2025/2003); Kinective's Legal team reviews the wording before it is
relied on.

Never does: read the canonical store, the clock or a session, confirm a serial, compute a bench pass, derive an export class, or
write a case.
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


WIPE = "config_wipe"  # the evidence type G-NET-CFG asks for (the test bench's read: di.services.cases.bench_evidence)
WIPE_SCOPE = ("configuration", "credentials", "keys", "logs")  # what a wipe must cover to clear a unit
CONFIG_GATE = "G-NET-CFG"
COVERED_GATE = "G-NET-COV"
REASON_WIPE = "Configuration wipe certificate missing or failed"
REASON_DESTROYED = "Wipe failed twice: storage destroyed, no resale"
TEXT_WIPED = "Configuration wiped, certificate on file"
REASON_COVERED = "Covered equipment: dispose only"
TEXT_UNCOVERED = "Not covered equipment"
STEP_DESTROY = "destroy_storage"
STEP_DISPOSAL = "disposal_record"
DISPOSAL = "disposal_record"  # the evidence type that clears the recycle step
RESELL = "resell"


def _wiped(value: Mapping[str, Any]) -> bool:
    return bool(
        value.get("status") == "verified" and value.get("certificate_ref") and set(WIPE_SCOPE) <= set(value.get("scope") or [])
    )


def check_config_wipe(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-NET-CFG (module docstring)."""
    e = evidence_of(case, WIPE)
    value = dict(e.value) if e is not None and e.result == "pass" else {}
    if _wiped(value):
        return GateResult(gate.id, True, GateEffect("block", (), gate.effect.hold_until_evidence, None), (), TEXT_WIPED)
    routes = _routes(gate, pack)
    limit = int(gate.params.get("fail_limit") or 2)
    last = dict(e.value) if e is not None else {}
    destroyed = last.get("status") == "failed" and int(last.get("attempts") or 0) >= limit
    return GateResult(
        gate.id, False, GateEffect("block", routes, gate.effect.hold_until_evidence, STEP_DESTROY if destroyed else None),
        (WIPE,), REASON_WIPE, route_reasons=((RESELL, REASON_DESTROYED),) if destroyed and RESELL in routes else (),
    )  # fmt: skip


def _programme(case: Mapping[str, Any]) -> Any:
    """The removal's programme: the newest `programme` fact of the case's network facts."""
    facts = (case.get("network") or {}).get("facts") or []
    return next((f.get("value") for f in reversed(facts) if f.get("fact") == "programme"), None)


def covered(case: Mapping[str, Any], gate: GateDef) -> bool:
    """The unit is covered equipment: a listed manufacturer under the programme in a listed region."""
    e = evidence_of(case, INVENTORY_MATCH)
    inv = e.value if e is not None else {}
    p = gate.params
    return bool(
        inv.get("manufacturer") in (p.get("covered_manufacturers") or [])
        and _programme(case) == p.get("programme")
        and inv.get("region") in (p.get("regions") or [])
    )


def check_covered_equipment(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-NET-COV (module docstring)."""
    if not covered(case, gate):
        return GateResult(gate.id, True, GateEffect("block", (), False, None), (), TEXT_UNCOVERED)
    mine = {r.id for r in pack.routes}
    blocked = tuple(r for r in gate.params.get("blocks") or [] if r in mine)
    record = evidence_of(case, DISPOSAL)
    have = record is not None and record.result == "pass"
    recycle = "recycle" in mine
    return GateResult(
        gate.id, False, GateEffect("block", blocked, False, None if have or not recycle else STEP_DISPOSAL),
        () if have or not recycle else (DISPOSAL,), REASON_COVERED,
    )  # fmt: skip


EXPORT_GATE = "G-NET-EXP"
EXPORT_EVIDENCE = "export_classification"  # the evidence type G-NET-EXP asks for (di.services.cases.export_evidence)
REASON_UNSCREENED = "Destination and end-user screening not on file"
NOT_TRIGGERED = "not triggered for reuse"
TEXT_NOT_CONTROLLED = "Not export controlled on file"
SCREENED = "clear"


def export_status(value: Mapping[str, Any], gate: GateDef) -> str | None:
    """Why the unit needs trade compliance: "controlled" (its confirmed class is on the list), "unclassified" (no confirmed
    class, one inferred from the part number), or None. The inferred class is never read as the class."""
    cls, inferred = value.get("export_class"), value.get("inferred")
    if cls:
        return "controlled" if cls in (gate.params.get("controlled_classes") or []) else None
    return "unclassified" if inferred and gate.params.get("inferred_counts_as_missing", True) else None


def export_text(value: Mapping[str, Any]) -> str:
    """The unit's classification in words: "class 5A002 (tn_inv)", or "class not confirmed (inferred 5A992 from the part)"."""
    if value.get("export_class"):
        return f"class {value['export_class']} ({value.get('class_source') or 'a source'})"
    return f"class not confirmed (inferred {value.get('inferred')} from the part number)"


def check_export_control(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-NET-EXP (module docstring)."""
    e = evidence_of(case, EXPORT_EVIDENCE)
    value = e.value if e is not None else {}
    if export_status(value, gate) is None:
        return GateResult(gate.id, True, GateEffect("require_approval", (), False, None), (), TEXT_NOT_CONTROLLED)
    routes = _routes(gate, pack)
    notes = tuple((r.id, NOT_TRIGGERED) for r in pack.routes if r.id not in routes)
    bid = value.get("bid") or {}
    if bid.get("screening") != SCREENED:
        return GateResult(
            gate.id, False, GateEffect("block", routes, False, None), (EXPORT_EVIDENCE,), REASON_UNSCREENED, route_notes=notes,
        )  # fmt: skip
    reason = f"Trade compliance approval required: {export_text(value)}, bid {bid.get('id')} screened clear"
    return GateResult(
        gate.id, False, GateEffect("require_approval", routes, False, gate.effect.step), (), reason, route_notes=notes
    )  # fmt: skip


CHECKS[INVENTORY_GATE] = check_inventory_match
CHECKS[CONFIG_GATE] = check_config_wipe
CHECKS[COVERED_GATE] = check_covered_equipment
CHECKS[EXPORT_GATE] = check_export_control
