# Phase 12 review (P9-12.13): next segments

Reviewer: read-only code review (writer 85), 27 Nov 2026, on `lead-merge` (HEAD `76d6bd30`). Scope: the `P9-12.*` commits
(`691e0107` standard valuer, `7a62201d`/`6d125883` ITAD, `3c40f87a`/`a1b11ec5` rental fleet, `e31cbf61` telecom CPE, `d073933a`
battery, `d3391be3`/`140458e8` cores, `5f857e2d`/`810d1ddd` medical capital, `82583879`/`e15cd015` retail returns, `15d90cec`
industrial pack format). No test was run; every finding was checked by reading the code at the cited line. Data security,
battery, regulatory-assessment and export rules are compliance matters: To be reviewed by Kinective's Legal team before it is
relied on.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P1 | G-DATA-1 (locked, "every disk is sanitised before an asset leaves our control") does not apply to an asset with no media list: `check_media_sanitised` returns None when `asset.media` is empty or absent. An ITAD asset whose media were never reported can be resold, harvested or recycled with no sanitisation record at all. To be reviewed by Kinective's Legal team before it is relied on. | `services/modeler/gate_checks/data.py:113-120` | Yes (code; not run) | Needs code: for the `itad` pack a missing media list fails the leaving routes with `evidence_missing: ("media_inventory",)`; test an asset with no media. |
| 2 | P1 | G-DATA-2 is cleared by any `destruction_record` evidence: `evidence_of(case, DESTRUCTION) is not None` ignores the record's result and the media serial. One record for disk A clears the destruction step for failed disk B, and a failed destruction record clears it too. To be reviewed by Kinective's Legal team before it is relied on. | `services/modeler/gate_checks/data.py:143-150` | Yes | Needs code: require `result == "pass"` and one destruction record per failed `mediaSerial`; test two failed disks with one record. |
| 3 | P2 | A media record with no `type` is treated as an `hdd`, for which `clear` is enough to leave; an SSD with a missing type leaves on the weaker method. | `services/modeler/gate_checks/data.py:84-87` | Yes | Treat an unknown type as the strict set (`purge` or `destruct`). |
| 4 | P2 | Battery gates fail open on unknown facts: a pack with no `damaged` flag and no thermal event is treated as undamaged (`not b.get("damaged")` returns None); an unknown `market` is "not required" for the passport. A lithium pack of unknown state can take a reuse lane. | `services/modeler/gate_checks/battery.py:92-93`, `:145` | Yes | Treat a missing damage reading as unknown (require the dangerous-goods step or a read); treat a missing market as the strictest. |
| 5 | P2 | `assessment.record` has no stage check and no second person. It can be recorded after approval or on a closed case (and it revalues the case), and the same person may record "servicing" for a unit whose route they then push. `FORBIDDEN_ACTIONS` keeps agents out, but a regulatory call by one Engineer or Admin is not maker-checked. To be reviewed by Kinective's Legal team before it is relied on. | `services/actions/assessments.py:48-57`, `:60-82`; `core/policy.py:57` | Yes | Refuse after `approved`; consider a checker for `servicing` on a unit the gate would otherwise block. |
| 6 | P2 | The standard valuer (every pack built on it: ITAD, rental fleet, CPE, cores, capital, retail returns) computes money in `float` with JS-style rounding (`js_round`, `js_sum`), not `Decimal`. Same style as the tool-fleet valuer; against the Global Constraint "money in Decimal". | `services/modeler/valuers/standard.py:25`, `:119-122` | Yes | Record the exception (parity with the demo's arithmetic) or move to `Decimal`. |
| 7 | P2 | Parity of the industrial pack is checked against `tests/fixtures/industrial_decisions.json`, taken from the code "before the pack got its full format", not from the demo; only the stored cases are compared with the golden file. A drift that predates the fixture is not seen. Also the industrial pack's KPIs and analytics are switched off by a `valuer.kind == "industrial"` branch in shared code. | `backend/tests/test_ns_ind_parity.py:1-6`, `:51-70`; `services/modeler/kpis.py:181`, `:219` | Yes | Compare the re-valued route and net to the golden file where the demo allows it, or say in the decision log why the baseline is the code's own; move the KPI switch into the pack data. |

## Checked, no findings

- Agents never approve: `assessment.record`, `fraud.release`, `lot.approve`, `work.resolve` are forbidden; `rentalFleet.chargeDamage`, `case.attachReporting` are `HELD_FOR_PERSON` (`services/agents/forbidden.py`). A case held for fraud review (a core with a fraud hold) is approved or overridden only after a person runs `fraud.release` (`services/actions/decisions.py:345`, `:366`, `:376`).
- Money in the rental fleet close is `Decimal` (`services/cases/close_rental_fleet.py:33-64`, `:120`).
- Parity: no file under `fixtures/golden/` changed in the range; the replay refuses the industrial pack (`services/replay/run.py:135`); the 15d90cec diff touches the pack file, two KPI lines and the new test only.
- Tenant boundary: new cases are keyed `serial_key(org, serial)`/`tag_key(org, tag)`; `assessment.record` is `scope="case"`; no cross-org read was found in the phase's new modules.
- ITAD data gate: a failed media verification excludes harvest ("no parts sale") and a failing route names the media serial (`data.py:121-142`).

## Needs code

- F1 and F2 (P1): ITAD sanitisation gates. F3-F7 as listed.
