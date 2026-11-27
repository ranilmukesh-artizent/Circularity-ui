# Phase 10 review (P9-10.19): telecom network equipment

Reviewer: read-only code review (writer 85), 27 Nov 2026, on `lead-merge` (HEAD `76d6bd30`). Scope: the `P9-10.*` commits
(`ca93f95e` pack, `9c5a8952` inventory gate, `509887e4` wipe and covered gates, `0e6b8f21` export gate and approval,
`b8cfac23` valuer, `88500673` diversions, `17aef6cd` cross-region, `b70a84eb`/`4a4c2b21` follow-through and close, and the mocks).
No test was run; every finding was checked by reading the code at the cited line. The export-control, wipe and covered-equipment
rules are regulatory: To be reviewed by Kinective's Legal team before it is relied on.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P2 | G-NET-EXP passes a unit that has no confirmed class and no inferred class ("Not export controlled on file"). Unknown classification is treated as not controlled; only an inferred class counts as missing. The inventory gate (G-NET-INV) holds a unit the inventory has not written, so the case is not open to a missing record, but a record without any class clears the export gate. To be reviewed by Kinective's Legal team before it is relied on. | `services/modeler/gate_checks/network.py:182-189`, `:200-203` | Yes | Needs a decision: treat "no class on file" as needs-approval (or block resale with evidence missing `export_classification`), as for an inferred class. |
| 2 | P2 | No gate of the phase passes `as_of` to `evidence_of`, so a record's `valid_until` is never enforced (without `as_of` the newest record wins, expired or not). Today no phase-10 evidence builder sets `valid_until` (grep: only `gate_hold.py:107` copies it), so this is latent; an expiring wipe or classification would still clear the gate. | `services/modeler/evidence.py:114-125`; `services/modeler/gate_checks/network.py:93`, `:127`, `:149`, `:165`, `:200` | Yes | Pass the case's `gateNow` as `as_of` in the telecom gates (as the vehicle gates do for recall), and test an expired record. |
| 3 | P2 | The best broker bid is read from the canonical `market` record keyed by the model only (`canonical.get(s, "market", str(model))`), not by org. Bids and their end-user screening result written for one org's broker sync can clear another org's resale approval. Market records are shared by design (`SHARED_ORG` in `canonical/schema.py`), but a screening result is a compliance fact about one buyer. | `services/cases/export_evidence.py:83-85`, `:33-37` | Yes | Confirm intent in the decision log; if not shared, key the bids by org or screen again per case. |

## Checked, no findings

- Agents never approve (focus 6): `decision.approve`, `decision.override`, `work.resolve`, `mapping.answerOwner` are forbidden; the export approval item `AP-TN-EXP` is opened by the system and closed by a person's decision (`services/cases/export_approval.py:62-89`, `approval_hold.py:70`); the module never approves, classifies or screens. `requisition.reduce` is `HELD_FOR_PERSON`; `telecom.crossRegion` is a person-only read (`PERSON_ONLY_READS`, `pipeline.py:141`).
- Wipe: G-NET-CFG fails closed on a missing, failed or short-scope record (certificate, `verified`, scope of configuration, credentials, keys, logs); two failures require destroying the storage and block resale with its own text (`network.py:121-143`).
- Covered equipment: only disposal; recycling needs the `disposal_record` until it is on file (`network.py:158-168`).
- Tenant boundary: asset keys are `serial_key(org, serial)` (`canonical/schema.py:87`); the cross-region alerts read the orgs they are given (`services/cases/tn_cross_region.py:120-125`); unit cases plan within their org's open cases (`services/cases/intake.py:549-560`).
- Money in `Decimal` in the five-route valuer (`services/modeler/valuers/telecom_network.py:24-60`); bid prices compared as `float` only to pick the best (`export_evidence.py:33-37`), no arithmetic.
- Review Focus 1: diversions cannot skip a Compliance gate (`overlay.py:202-206`).
- Parity: no golden file changed in the range.

## Needs code

- F1 (decision), F2, F3 as listed.
