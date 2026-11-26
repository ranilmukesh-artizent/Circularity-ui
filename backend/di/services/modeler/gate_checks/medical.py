"""The medical rental gates (plan 9, P9-11.6 story MR-05; P9-11.7 stories MR-06 and MR-15). Pure. Implements the checks of
registry entry I-2 for the catalogue gates `G-MED-DECON` (Compliance, stage 2, locked), `G-MED-SVC` (Compliance, stage 3,
locked) and `G-MED-FSN` (Compliance, stage 3); they run before any business rule (R20).

    check_decontamination(case, pack, gate) -> GateResult           G-MED-DECON: a decontamination record that ends after check-in
    check_service_in_date(case, pack, gate) -> GateResult | None    G-MED-SVC: certification and PM in date for the whole rental
    check_safety_notice(case, pack, gate) -> GateResult | None      G-MED-FSN: no open field safety notice on the model and serial

The evidence `decontamination` is the device's decontamination record (`di.services.cases.decon_evidence`: the END of the
cycle, `decon_ended_at`, and the check-in time of the rental system). The gate passes when the record ends LATER than
`checked_in_at` and the cycle did not fail. Otherwise EVERY route of the pack fails, the service route included (to protect
technicians), effect `block`, `evidence_missing: ("decontamination",)`, and the case is held until a valid record arrives:
  - no record on file, or one that ends at or before check-in, or a failed cycle, or no check-in time to compare with:
    "Decontamination record required".
`gate_hold` raises the exception `EX-MR-DECON` for the decontamination lead ("Re-run decontamination; held until the record
exists") and closes it when a valid record lands (X-07 auto-release, per tag). `work.resolve` is in `FORBIDDEN_ACTIONS`: an
agent never clears, waives or approves this gate.

G-MED-SVC (P9-11.7) reads the evidence `service_record` (`di.services.cases.service_evidence`) and the case's `rentalRequests`. A
request ends `start_date + days`; the unit is in date for it when `certification_expiry` and `pm_due` are both LATER than that
end. Otherwise it fails that request: "Certification ends <date>, before the rental ends <date>" (or "Preventive maintenance due
<date> ..."). The gate fails the re-rent routes (`rerent`, `service_rerent`) when the unit is short for EVERY request it could
serve; it never holds the case: the exception `EX-MR-CERT` goes to the biomedical engineer, and the case's `serviceCheck` names
"Send a different unit: <tag>" and proposes `service.book` for this one (a person books it). A failed functional or electrical
safety test blocks `rerent` only (service then re-rent is how a unit gets fixed); a cosmetic note changes nothing (MR-07).

G-MED-FSN (P9-11.7) reads the evidence `field_safety_status`: it fails while a notice that covers the model and serial is open,
"Open field safety notice <id>: re-rent held until corrected", `rerent` and `service_rerent` blocked and the case held; a later
`field_safety_status` record that passes (the correction record) makes the unit eligible again and releases the case. A gate
check returns None to leave a passing unit to the data.

G-MED-REFURB (P9-11.10, story MR-16, stage 5) reads the evidence `servicing_assessment` (`service_evidence`: the biomedical
system's `condition.servicing_assessment`, value `{assessment}`). `refurbish` needs it: with none the route fails with
`evidence_missing: ("servicing_assessment",)` ("Servicing assessment required"). An assessment of `remanufacturing` or
`full_refurbishment` fails "Would be remanufacturing or full refurbishment: needs manufacturer status in this market" unless the
case's market (`case["market"]`, else `valuer.market`) is in the gate's param `manufacturer_status_markets` (empty by default; the
pack's list is the only way in, an overlay cannot widen it: the gate is Compliance, so locked). Only `refurbish` is affected.

Never does: read the canonical store, the clock or a session, or write a case. The CDC guideline is not re-read, and the MHRA
and NHSScotland wording is unconfirmed. 42 CFR 482.41 and CMS S&C 14-07 are the hospital's duty (the flow-down through rental
contracts is unconfirmed), IEC 62353:2014 names the electrical safety test, and 21 CFR Part 7 and 806 and the EU MDR field safety
corrective actions are not re-read. The wording of all four gates needs review by Kinective's Legal team before it is relied on.
"""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from di.services.modeler.evidence import evidence_of, parse_time
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult, gate_routes
from di.services.modeler.pack import Pack

DECON_GATE = "G-MED-DECON"
DECONTAMINATION = "decontamination"
REASON = "Decontamination record required"
SVC_GATE, FSN_GATE = "G-MED-SVC", "G-MED-FSN"
REFURB_GATE, ASSESSMENT = "G-MED-REFURB", "servicing_assessment"
FULL = ("remanufacturing", "full_refurbishment")
SERVICE_RECORD, SAFETY_STATUS = "service_record", "field_safety_status"
TESTS = {"functional_test": "Functional test", "electrical_safety": "Electrical safety test (IEC 62353)"}


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


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def rental_end(start: Any, days: Any) -> date | None:
    """The day a rental ends: its start date plus its days; None for a date or a number of days that is not one."""
    first = _day(start)
    if first is None or not isinstance(days, int | float) or isinstance(days, bool) or days < 0:
        return None
    return first + timedelta(days=int(days))


def request_checks(value: Mapping[str, Any], requests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each request (`req_id`, `ends`) with whether the unit is in date for its whole rental: {req_id, ends, ok, reason, kind,
    due, recommendation}. `value` holds `certification_expiry` and `pm_due`; a date the record lacks is not held against the
    unit. Certification is checked before preventive maintenance. Pure."""
    cert, pm = _day(value.get("certification_expiry")), _day(value.get("pm_due"))
    out = []
    for q in requests:
        end = _day(q.get("ends"))
        if end is None:
            continue
        row: dict[str, Any] = {"req_id": q.get("req_id"), "ends": end.isoformat(), "ok": True, "reason": None, "kind": None,
                               "due": None, "recommendation": None}  # fmt: skip
        if cert is not None and cert <= end:
            row |= {"ok": False, "kind": "certification", "due": cert.isoformat(),
                    "reason": f"Certification ends {cert.isoformat()}, before the rental ends {end.isoformat()}"}  # fmt: skip
        elif pm is not None and pm <= end:
            row |= {"ok": False, "kind": "pm", "due": pm.isoformat(),
                    "reason": f"Preventive maintenance due {pm.isoformat()}, before the rental ends {end.isoformat()}"
                    }  # fmt: skip
        out.append(row)
    return out


def recommend_other_unit(units: Sequence[tuple[str, Mapping[str, Any]]], ends: Any) -> str:
    """ "Send a different unit: <tag>" naming the first unit (by tag) in date for a rental that ends `ends`, with no open notice
    and no failed test; "Send a different unit" alone when none of the class is on file. Pure."""
    end = _day(ends)
    for tag, d in units:
        cert, pm = _day(d.get("certification_expiry")), _day(d.get("pm_due"))
        failed = any(str((d.get(t) or {}).get("result")) == "fail" for t in TESTS)
        if end and cert and pm and cert > end and pm > end and not d.get("correction_open") and not failed:
            return f"Send a different unit: {tag}"
    return "Send a different unit"


def proposal(case: Mapping[str, Any], checks: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The `service.book` the gate proposes for this unit (a person books it; an agent's call is held): the certification, or
    the preventive maintenance, of the first request it is short for, due by the date it ends. None when the unit is in date."""
    bad = next((c for c in checks if not c["ok"]), None)
    key = str(case.get("assetId") or "")
    if bad is None or ":" not in key:
        return None
    return {"action": "service.book", "input": {"case_id": case.get("id"), "asset_tag": key.split(":", 1)[1],
                                                 "kind": bad["kind"], "due_by": bad["due"]}}  # fmt: skip


def check_service_in_date(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-MED-SVC (module docstring); None leaves a unit that is in date, or has no service record, to the data."""
    e = evidence_of(case, SERVICE_RECORD)
    if e is None:
        return None
    routes = gate_routes(gate, pack)
    checks = request_checks(e.value, case.get("rentalRequests") or [])
    short = bool(checks) and all(not c["ok"] for c in checks)
    failed = [TESTS[t] for t in e.value.get("failed") or [] if t in TESTS] if e.result == "fail" else []
    if not short and not failed:
        return None
    reasons = ([next(c["reason"] for c in checks if not c["ok"])] if short else []) + [f"{t} failed" for t in failed]
    if not short:
        routes = tuple(r for r in routes if r == "rerent")  # a failed test: service then re-rent is how the unit is fixed
    effect = GateEffect("block", routes, gate.effect.hold_until_evidence, gate.effect.step)
    return GateResult(gate.id, False, effect, (), "; ".join(reasons))


def check_safety_notice(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-MED-FSN (module docstring); None leaves a unit with no open notice, or with the correction record, to the data."""
    e = evidence_of(case, SAFETY_STATUS)
    if e is None or e.result != "fail":
        return None
    reason = f"Open field safety notice {e.value.get('notice_id') or '(not named)'}: re-rent held until corrected"
    effect = GateEffect("block", gate_routes(gate, pack), gate.effect.hold_until_evidence, gate.effect.step)
    return GateResult(gate.id, False, effect, (SAFETY_STATUS,), reason)


def check_refurbish_servicing(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-MED-REFURB (module docstring)."""
    routes = tuple(r for r in gate_routes(gate, pack) if r == "refurbish")
    e = evidence_of(case, ASSESSMENT)
    if e is None:
        return GateResult(gate.id, False, GateEffect("block", routes, gate.effect.hold_until_evidence, None),
                          (ASSESSMENT,), "Servicing assessment required")  # fmt: skip
    result = str(e.value.get("assessment") or "")
    market = case.get("market") or (case.get("valuer") or {}).get("market")
    if result in FULL and market not in (gate.params.get("manufacturer_status_markets") or []):
        reason = "Would be remanufacturing or full refurbishment: needs manufacturer status in this market"
        return GateResult(gate.id, False, GateEffect("block", routes, gate.effect.hold_until_evidence, None), (), reason)
    ok = GateEffect("block", (), gate.effect.hold_until_evidence, None)
    return GateResult(gate.id, True, ok, (), "Servicing assessment on file")


CHECKS[DECON_GATE] = check_decontamination
CHECKS[SVC_GATE] = check_service_in_date
CHECKS[FSN_GATE] = check_safety_notice
CHECKS[REFURB_GATE] = check_refurbish_servicing
