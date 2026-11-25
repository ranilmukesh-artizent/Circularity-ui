# Phase 2 review (P9-2.17)

Reviewer: `code-reviewer` subagent (Opus), 26 Nov 2026, on `feature/plan-09-recover` after the lane B merge (bcfff20).
It read the code as it stands (forbidden, pipeline, hold, fraud and fraud review, stage reasoner, checked output,
runtime, chain, intake, standing policy, decisions, proposals, Pydantic AI loop, router, exception assistant, workflow
read, Ask, catalogue, MCP catalogue tools, MCP OAuth, jobs, worker). The lead verified each finding in the code before
acting (receiving-code-review).

## Findings and what was done

| # | Severity | Finding | Verified | Action |
|---|---|---|---|---|
| 1 | High | `fraud.hold` goes through the pipeline as an agent write, so step 9b holds it as a proposal when the stage is recommend-only, the run is tainted or a model concern is open. The case then has no `fraud` record: the approval card and the standing policy see no hold. The model's caution removes the computed caution (R16 breach). | Yes: `stages/intake.py:41`, `hold.py:165` | Fixed: `CAUTION_ONLY` in `forbidden.py` (`fraud.hold`, `transit.flagDelay`); `hold_check` never holds them. Test: `test_caution_only_writes_are_never_held`. Compliance control: to be reviewed by Kinective's Legal team before it is relied on. |
| 2 | High | The worker locks `agent_run` (`FOR UPDATE`) and keeps its transaction open while the stage reasoner and the fraud review call the model; the queue branch inserts the deduped `queue.plan` job first. Another worker enqueuing the same key, or a person's accept/approve that wakes the run, waits for the model. Fits the shard 3 hang ("idle in transaction" on `job`), not proven. | Yes: `runtime.py:286`, `:336-339`, `:379` | Follow-up task P9-2.24 (commit the deterministic step before the model reads; enqueue after the reading). |
| 3 | Medium | `proposal.accept` / `proposal.reject` lock the row but do not re-check `pending`; `decide` updates unconditionally. Two people deciding at once could run the held action twice, or reject after an accept. | Yes: `actions/proposals.py:68-92`, `agents/proposals.py:75-82` | Fixed: both re-check `pending` under the lock (conflict otherwise); `decide` updates only `status = 'pending'`. Tests: `test_a_decided_proposal_is_not_decided_again`, `test_decide_updates_only_a_pending_proposal`. |
| 4 | Medium | `conflict.resolve` (risk act) was open to agents; resolving a conflict clears the "sources disagree" hold. `PERSON_ONLY_NAME` did not catch resolve/clear/waive/accept. | Yes: `forbidden.py`, `integration.py:45-49` | Fixed: `conflict.resolve` in `FORBIDDEN_ACTIONS`; `PERSON_ONLY_NAME` adds resolve, waive, clear, dismiss, accept (`check_person_only` passes: the others matching are already forbidden). Test: `test_conflict_resolve_is_a_persons`. |
| 5 | Low | `review_fraud` drops `res.tainted` and puts evidence notes from source systems straight into the prompt; an injected note cannot release a hold but can shape the stored narrative. | Yes: `fraud_review.py:97-105`, `:147-149` | Follow-up P9-2.24 (mark tainted, label the text as data). |
| 6 | Low | Ask shows text that arrives before the first workflow tool call unchecked; if that draft is refused and the retry passes, the early text stays on screen. | Yes: `ask/checked_answer.py:33-46` | Follow-up P9-2.24 (hold all text once a workflow question is detected, or send a reset). |

Checked by the reviewer with no issue: every forbidden check calls `forbidden()` (incl. `AGENT_EXEMPT`);
`decision.approveByPolicy` is refused to agents; `fraud.release`/`fraud.reject` unreachable by agents; model readings
and the fraud review only add holds, and the number and source checks retry then fall back; `workflow_read` answers the
same not-found outside the tenant; `tools.find` lists only allowed and permitted actions; the MCP OAuth metadata holds
no secret and no token is logged.

## Found by the lead during the gate (not in the review)

- The stage reasoner sees evidence status ("ready"), not its contents, and is told to raise a concern when data is
  missing: with the live model most cases get a `model_concern` hold, so standing policies rarely approve (the phase 2
  smoke needed 12 candidates). Follow-up P9-2.24.
- The fraud banner is only on the case Overview, not on the stage pages a person lands on. Follow-up P9-2.24.
- Shard 3 of the parallel suite hung 75 minutes behind an "idle in transaction" session on `job` (see finding 2).
