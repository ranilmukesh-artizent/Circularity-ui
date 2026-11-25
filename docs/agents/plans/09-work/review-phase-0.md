# Phase 0 review

Reviewer: one Opus `code-reviewer` over the phase 0 commits (P9-0.1 … P9-0.16), 25 Nov 2026. It read the code at
`fa4ade2`; it could not run tests or git. The lead checked each finding in the code before acting on it.

| # | Task | Finding | Lead's check | Action |
|---|---|---|---|---|
| 1 | P9-0.9 | With the setting on, the autopilot (autonomy `act`) runs `decision.submit` as the person who opened the case; the run then waits on the person's approval. The spec's test says "ends waiting on the held `decision.submit`"; the writer asserts the approval wait instead. | Confirmed in `runtime.py` and the test. `decision.submit` is not an approval and is not on the forbidden list; an `act` agent started by hand already does this (plan 8). Approval stays with a person, but self-approval (if switched on) lets the opener approve a submission an agent made in their name. | **For the person to decide:** keep (act submits, a person approves) or hold every write of an auto-started run as a proposal. Not changed. |
| 2 | P9-0.16 | `workflow.create {type:"dec"}` then `workflow.publish` makes a new decision workflow; import can too. Only save is refused. | Confirmed: `create_guard` and `publish_guard` do not call `_new_decision_draft`. | Partly: import refuses a Decision workflow (`28fe893`). Create and publish stay: the demo's golden scenario (`fixtures/golden/workflow_writes.json`) creates and publishes one, so refusing them breaks parity. Studio's Save refuses a new decision draft (P9-0.16). |
| 3 | P9-0.12 | `flow.rollback` leaves `returned` set, so a fresh draft shows a stale "Returned" mark. | Confirmed: rollback's update has no `returned=None`. | Fixed in the review-fix commit, with a test. |
| 4 | P9-0.10 | An agent's invalid `mapping.save` is held (step 9b) and only fails when a person accepts it. | Confirmed: the checks are in the handler, after the hold. | Fixed: checks moved to a `@guard`, test for an agent's bad target. |

Checked with no defect: P9-0.4 (agent route and hold share one function; `credentials.rotate` forbidden; migration
idempotent), P9-0.7 (removing `import_guard` from `org.importPack` loses only graph checks that publish runs again),
P9-0.13 (`testUser` needs `manageIdentity`, Admin only), P9-0.14 (read-only refusal before any writer call), P9-0.8
and P9-0.15 (guards match the spec).
