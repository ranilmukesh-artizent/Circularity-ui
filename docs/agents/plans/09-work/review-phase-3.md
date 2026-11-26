# Review: plan 9 phase 3 gate (lane B, tool fleet returns)

Scope: the 24 commits whose subject starts with `P9-3.` (6405cea .. 1257cf2, incl. f1ea662/ff138ec, b36af2b, 355deea).
Read-only review (git show/log, Read, Grep); no tests run. "Verified" = the cited code was read and the defect follows
from it; runtime behaviour was not executed. Known, already-logged items (two CO2 factor sets, 3.11 constants, 4.5 fx,
`gate_hold._bound`, GR-C2, battery_soh evidence, GR-11 unlink, I-7 SLA timer) are not repeated.

## Checked and fine

- Golden files: no commit in scope touches `fixtures/`.
- R21: `recall.release` is in `FORBIDDEN_ACTIONS` (forbidden.py:38), perm `releaseQuarantine` (Admin, Approver), case scope
  so the pipeline's step 5 enforces the tenant; `nonReturnFee.post` is in `HELD_FOR_PERSON` (forbidden.py:61) as the spec
  says; `model.promote` keeps maker-checker (`promote_block`, created_by != actor) and now replaces the active model of the
  same `kind` only (models.py:424); overlay `set_param` raise-only is enforced in `overlay._set_param` (overlay.py:298) and
  `overlay.approve` stays forbidden; `model.fit` rated_life filters teardown rows by `policy.tenant_ok`.
- R16: no model/LLM call in the new valuers (tool_approval, tool_life, tool_carbon, battery, fleet_evidence, rul); text is fixed.
- R20: gates run before valuation (decide.py:512), blocked routes stamped `gateBlocked` for the queue plan; key-account
  hold is appended after gate holds (tool_approval.py:126-131). 355deea fixes the chain's valuation to report the
  recommendation (valuation.py:42-51), covered by test_paths_agree / test_stage_chain.

## Findings

| # | Finding | File:line | Severity | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | Smoke `smoke-p9-3.mjs` has 13 steps (1-10, 13, 15, 17); steps 11 (CO2e + GR-06 refusal), 12 (policy vs fleet manager), 14 (follow-through) and 16 (battery) are missing. The gate (P9-3.22 step 6) requires "all 17 steps PASS, none SKIP". | frontend/scripts/smoke-p9-3.mjs:119-475 (step list) | High (gate) | yes | Add steps 11, 12, 14, 16 before running the gate. |
| 2 | The tool-fleet panel of a battery case (cls `BAT`) will 500: `_paths` plans the case in the tools' queue (`intake.tool_queue(s, owner, v)` with v.cls BAT) and the planner values it with `tool_fleet._value`, which does `CLS[c["cls"]]` (KeyError). `replan.queue_plan` (screen `_plan`) does the same. Decide uses `_battery`, so only the read paths break; test_tf_battery never calls the screen. | backend/di/services/screens/toolfleet.py:158; backend/di/services/cases/replan.py:61-62; backend/di/services/modeler/valuers/tool_fleet.py:205 | Medium | yes (by reading; not executed) | For `cls == BAT` serve `paths` from `case["routes"]`/battery.decide and `plan: null`; add a screen test for a BAT case. |
| 3 | After `decision.override` the order actually taken is the chosen route's, but the named-demand "held" set and the queue's `sent` input read the recommendation (`rec_index`), not `chosen`. The overridden route's order is offered to other returns (double booking); the recommendation's order is wrongly withheld. | backend/di/repositories/tool_demand.py:55-57; backend/di/services/cases/intake.py:490-501; backend/di/services/cases/replan.py:57-60 (writers use `chosen`: writers_fleet.py fleet_issue/parts_issue) | Medium | yes | Read `chosen or recommendation` in `_held`, `tool_input` and `queue_plan`; add an override test to test_tf_queue. |
| 4 | GR-15 (young write-off) reads the case document's `age`, which intake sets to `known.get("age", 0)`; a contract-feed return carries no age fact, so every exit/harvest recommendation of such a case holds for Service operations with "Write-off at 0 months". When an asset record has `install_date`, `age` is in years (intake.py:341) while GR-15 compares months. Unit tests pass `{"age": 18}` directly, so they do not see it. | backend/di/services/modeler/valuers/tool_approval.py:112-114; backend/di/services/cases/intake.py:341, 357 | Medium | yes | Use a months figure from evidence (`contract_line.months_on_contract` or the valuer's `age`), and skip GR-15 when unknown (or hold with "age unknown"); add an intake-level test. |
| 5 | `nonReturnFee.post` tenant check is skipped when the line has no case: `org = item.org_unit_id or org_of(serial)` is None for a lost tool never returned (the usual non-return), and the guard only checks `if org and ...`. Any tenant-scoped Planner/Finance can post another tenant's fee; the item is also opened with `org_unit_id=None`. The contract's `owner_org` is on file. | backend/di/services/actions/fleet_fees.py:41-44; backend/di/services/instructions/fees.py:73-77, 105 | Medium | yes | Resolve the org from `contract.owner_org` of the line (canonical `contract`), fall back to the case owner; refuse when unknown for a tenant-scoped actor. Extend test_non_return_fee_tenant_boundary with a line that has no case. |
| 6 | Two active repair recalls on one serial: `recall.release` records one `recall_id`; `quarantine_of` then shows `hits[0]` as released, so the guard answers "not quarantined" and the second recall can never be released (gate still fails). | backend/di/services/modeler/valuers/fleet_evidence.py:154-156, 209-221; backend/di/services/actions/tool_quarantine.py:46 | Low | yes | Keep releases per recall id (list) and pick the first unreleased repair notice in `quarantine_of`. |
| 7 | `parts_issue` PATCHes an open repair order already `part_issued` from another serial (only "issued from this serial" is skipped), overwriting the other tool's issue. | backend/di/services/instructions/writers_fleet.py:137 | Low | yes | Raise `Refused` when the order is `part_issued` from another serial. |
| 8 | A contract-line write re-checks only cases already held (`gateHold` object); a line that turns bad (damage charge, theft claim) on an open, unheld case is not re-gated until its next re-evaluation. | backend/di/services/canonical/store.py:151 | Low | yes | Enqueue `case.reevaluate`/`gateRecheck` for every open tool-fleet case of the serial on a `contract_line` write. |
| 9 | With instructions off, `nonReturnFee.post` closes the item and spends the journal idem key while nothing is sent; a later post (instructions on) is a `duplicate`. | backend/di/services/instructions/fees.py:137-157; backend/di/services/actions/fleet_fees.py:49 | Low | yes | Refuse (or keep the item open) when `queue.enabled()` is false, or key idem on the instruction. |
| 10 | `RulModel.predict`: `surv(used)/surv(used)` divides by 0.0 when `exp(-(u/scale)^shape)` underflows (large hours). Only tests call `predict` today. | backend/di/services/models/rul.py:91 | Low | yes | Compute the ratio in log space: `exp(-((u+T)/λ)^k + (u/λ)^k)`. |
| 11 | Fee journal reference truncated to 16 chars (`FEE-{line_id}`[:16]); two long line ids sharing a 12-char prefix get the same reference. | backend/di/services/instructions/writers_fleet.py:115 | Low | yes | Use a hash suffix or the instruction id when the id is long. |
| 12 | GR-06 recycling guard is tested only as a pure function on a hand-built dict; the spec's test (`outcome.confirm` refused, then confirms with the certificate) is not run through the action. | backend/tests/test_tf_carbon.py:101-105 | Low (test quality) | yes | Add an action-level test through `outcome.confirm`. |
| 13 | `docs/agents/plans/09-diffs/P9-3.12.md` is empty (0 bytes) although the decision-log row (R8) points to it for the changed cases. | docs/agents/plans/09-diffs/P9-3.12.md; docs/agents/decision-log.md:117 | Low (R8 docs) | yes | Write the rule table as P9-3.6.md does (or the diff script output). |
| 14 | Spec deviations not logged: 3.14 gate G-REP-3 (factor provenance) not on the tool_fleet pack; 3.16 key account is a valuer param (`valuer.params.approval.key_account`), not a pack diversion, so a customer overlay cannot add key-account conditions; 3.17 tolerance lives at `valuer.params.follow_through.variance_tolerance`, not `valuer.varianceTolerance`. | backend/di/services/modeler/packs/tool_fleet.json:796-797 (no G-REP-3 ref) | Low | yes | Log the three as decisions, or align with the spec. |
| 15 | GR-07 fails every `service_order` and `pool_excess` return (their lines are `returned` for `repair` / `early_termination`, not in `RETURNED_OK`), so two of the four return kinds of P9-3.4 never get a route. It is in the P9-3.6 diff table; confirm it is intended. | backend/di/services/modeler/valuers/fleet_evidence.py:53, 79; source-sim/sim/generic/specs/fleet_contracts.py:42-43 | Info | yes | Confirm with the person; if not intended, add `repair` (and decide on `early_termination`) to `RETURNED_OK`. |

## Needs code (BLOCKED.md)

- #1 smoke steps 11, 12, 14, 16 (blocks the gate's step 6).
- #2 battery case panel 500.
- #3 override vs recommendation in held demand and queue.
- #4 GR-15 age unit / default.
- #5 non-return fee tenant boundary without a case.
- #6, #7, #8, #9, #10, #11 (Low; can wait past the gate).
- #12 action-level GR-06 test; #13 P9-3.12 diff note; #14 decision-log rows (docs/tests, no product code).
