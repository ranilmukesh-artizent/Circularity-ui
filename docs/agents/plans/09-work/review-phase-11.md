# Phase 11 review (P9-11.19): medical rental

Reviewer: read-only code review (writer 85), 27 Nov 2026, on `lead-merge` (HEAD `76d6bd30`). Scope: the `P9-11.*` commits
(`afda55d6` pack, `e818a8d9` decontamination gate, `6f0b6e2a` service and safety gates, `232b9e68` valuer, `32ff3b7b` nearest
hospital and repair approval, `925a37a6` refurbish gate, `d50dc8c1` retire guardrail, `e58ce032` follow-through, and the mocks).
No test was run; every finding was checked by reading the code at the cited line. Decontamination, service and safety-notice
rules concern patient safety and regulation: To be reviewed by Kinective's Legal team before it is relied on.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P1 | The service and safety gates fail open on missing evidence. `check_service_in_date` returns None (no hold) when there is no service record, and `request_checks` does not hold a missing certification or PM date against the unit ("a date the record lacks is not held against the unit"); `check_safety_notice` returns None when there is no safety-status record or its result is not `fail`. A device whose service and field-safety status were never read is offered for re-rent as if it were in date. To be reviewed by Kinective's Legal team before it is relied on. | `services/modeler/gate_checks/medical.py:157-161`, `:114-123`, `:175-179` | Yes (code; not run) | Needs a decision, then code: a re-rent route needs a service record and a safety status on file (effect `block`, `evidence_missing`), as the decontamination gate does (`:78-93`); keep the "none for a unit in date" result only when the record exists. Test: a device with no service record, re-rent not offered. |
| 2 | P2 | A unit that is short for some requests but in date for others is not held (`short` is true only when every request fails). The proposal `service.book` is made, but the unit stays a re-rent candidate for the request it is in date for; intended, but the gate text then says nothing. Also the booking proposal names only the first short request. | `services/modeler/gate_checks/medical.py:164-165`, `:151-154` | Yes | Accept and note in the decision log, or show the covered requests in the gate reason. |
| 3 | P2 | G-DATA-3 passes whenever the case has any `sanitisationRef`; it does not read the record's result. A failed or pending sanitisation with a reference clears the disposal collection. | `services/modeler/gate_checks/data.py:36-42` | Yes | Read the evidence record (`result == "pass"`), not the reference. |
| 4 | P2 | Money in the medical valuer is `float` with no rounding: rate times days, miles times per-mile cost, repair, sums of harvest values, and net as float subtraction, all feeding the ordering and AP-MR-REPAIR. The used-car and telecom valuers use `Decimal`. Parity with the tool-fleet style, but against the Global Constraint "money in Decimal". | `services/modeler/valuers/medical_rental.py:42-57`, `:74-81`, `:112`, `:164-165` | Yes | Move to `Decimal` as `used_cars.py` does, or record the exception in the decision log. |
| 5 | P2 | Two gates implement the same assessment rule with two market readings: G-MED-REFURB reads `case.market` or `valuer.market` (a string), G-MED-1 reads `market.target` then `market.origin`. A fix to one will not reach the other. | `services/modeler/gate_checks/medical.py:208-220` vs `:231-248` | Yes | Share one helper. |

## Checked, no findings

- Agents never approve (focus 6): `service.book`, `rental.writeOff`, `view.setAlert` are `HELD_FOR_PERSON`; the hospital evidence and repair approval use `AP-MR-REPAIR`, opened by the system and decided by a person (`services/modeler/valuers/medical_rental.py:3-24`, `services/cases/approval_hold.py`); `assessment.record` is forbidden to agents.
- Decontamination (G-MED-DECON) fails closed: the record must exist, pass and be dated after check-in; an enhanced cycle is required when a diversion asks for it and no overlay can lower it (`medical.py:78-93`).
- Refurbish stays servicing (G-MED-REFURB): without an assessment the route is blocked; full refurbishment needs manufacturer status in the market (`medical.py:185-199`).
- Tenant boundary: tags are `tag_key(org, tag)` (`canonical/schema.py:93`); the actions are case scoped; no cross-org read found in the phase's code.
- The write-off posts through a held proposal and `Decimal` (`services/cases/close_medical_rental.py:39-81`, `:158`).
- Review Focus 1: the patient-safety gates are Compliance, so a diversion cannot skip them (`overlay.py:202-206`).
- Parity: no golden file changed in the range.

## Needs code

- F1 (P1): service and safety status must be on file before re-rent. F2-F5 as listed.
