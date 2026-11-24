# M-review: merge of colleague 2a3ee00..5c20ddb with our staged side (read-only)

Repo copy `Circularity-ui-merge` at 5c20ddb plus the index. Nothing run (no tests, no docker); the scenarios come from reading the code.

## Findings, most severe first

1. **HIGH: a dev DB that applied our old migration skips his 0027.** `backend/migrations/versions/0028_proposal_requester.py:14-15`.
   Before the merge, ours was `0027_proposal_requester.py` with `revision = "0027"` (9b14697). The lead's working tree still has that file.
   If a database was upgraded on it, `alembic_version` is `0027`. On restart, `alembic upgrade head` (docker-compose.yml:84) treats his
   `0027_access_grants` as already applied and runs only 0028. That leaves `tenant_grant` without `expires_at` or `revoked_at`. Then
   `load_context` (`core/auth.py:89`) fails on every signed-in request. Fix: on such databases run `alembic stamp 0026 && alembic upgrade head`
   (both migrations use IF NOT EXISTS), or make 0028 also add the four 0027 columns IF NOT EXISTS. Note it in the runbook or learnings.
2. **HIGH (ours, shows only after the merge): the F4 gate refuses agent reads, which breaks Ask parity.** `services/actions/pipeline.py:133`
   refuses every agent-prepared call to a forbidden prefix, reads included. Ask's fallback runs `access.lookup` with
   `preparer="briefer"` (`services/ask/fallback.py:94,116,947`). The demo starter "Who can approve above $5,000?" now answers
   approval_required instead of the golden answer (`fixtures/golden/ask.json`, compared by `tests/test_ask.py:49`). Fix: `if forbidden(a.id) and a.risk != "read"`.
   AGENTS rule 10 allows agents to read; his `access.grants` and `access.myAccess` keep their own guards.
3. **MEDIUM: our test conflicts with his two-step promotion.** `backend/tests/test_model_list.py:14` calls `model.promote` without
   `model.propose`. His `promote_block` (`services/actions/models.py`) now returns conflict "Propose MV-xxx for promotion first."
   The test fails. Fix: `call("model.propose", {"id": a["id"]}, "planner-a")` before the promote. Approver and planner-a are different
   people, so maker-checker holds.
4. **MEDIUM: duplicated backend reads that nothing calls, and docstrings that now describe code that does not exist.** The merge kept his frontend readers and dropped ours:
   - `services/screens/access.py:193` adds `orgs.pilot`. The docstring at :39 names `usePilotUnits`, which is not in `frontend/src/api/orgs.ts`.
     His `GET /api/screens/orgs` already serves `pilot`/`pilot_via` per unit, including inheritance. Ours lists only each unit's own setting.
   - `services/screens/integration.py:269` adds `orgs: visible_units(p)`. The docstring at :70 names an `orgUnits` export that does not exist.
     ConnectFlow and our SourceDrawer both use his `useOrgUnits()` instead.
   - `model.list` (`services/actions/models.py:9`, `repositories/model_versions.py:50`, "the Modeler's models panel") has no caller.
     The Modeler shows his `ModelsPanel` (GET `/api/screens/agents/models`). `model.list` also returns raw `metrics`, which includes his
     `proposal`; his screen strips it out. Fix: delete the three, along with their tests
     (`test_screens_access.py:57,84-86`, `test_screens_integration.py:178`, `test_model_list.py`), or keep them and correct the docstrings.
5. **LOW: proposal docstrings miss our `own` flag.** `services/agents/proposals.py:7-8` ("pending proposals a person may decide") and
   `services/screens/agents.py:16` ("accept or reject them"). The lists now also include the person's own agent proposals, which that person
   can only reject (`own: true`, F3a). Home and the Agents page hide Accept for those correctly. Say so in both docstrings.

## Checked, fine
- His new actions under our F4 gate: `access.revokeGrant`, `access.grants`, `access.myAccess` (`access.`), `org.update` and `model.propose` are in `agents/forbidden.py`. `org.previewPack` is a read and correctly not listed.
- `agent.register`/`agent.update` (his) use `catalog.agent_allowed`, which now imports from `agents/forbidden.py`. That is the same list the pipeline gate uses.
- Agent-prepared `model.propose`: the pipeline refuses it at step 6 with approval_required, before his guard. His test checks only the code (`test_agent_screens_gaps.py:145`).
- Tenant grants that end or are revoked: every reader goes through `ctx.grants` (live only). That covers our `repositories/orgs.visible_units`, `analytics`, `fabric_sources._check_org` and the case scope. Agent runs reload the context on each step (`runtime._context`). Proposals check `may_decide` against the current context.
- Out-of-office approvals: the delegate must hold the Approver role. They act through the normal pipeline, approve guard, limits and case scope. Nothing of ours (F2/F1 revaluation, template STEP_TPL) reads `approval.by`, so `delegate` and `onBehalfOf` do not break our code.
- Maker-checker on access (his) and on proposals (ours, F3a) do not overlap. His tests hold as planner-a and accept as admin. `smoke-mvp.mjs` step 7 has Admin start the run and planner-a accept. Both still pass under F3a.
- `proposal.held` event and `why` (his), together with `requested_by` (ours), sit in one `hold()` INSERT (`agents/proposals.py:41-60`). `_COLS` includes the new column.
- Frontend: `own`, `why`, `org_unit_id` (sources), `cases_failed`/`case_failures`, `flow.suggestions`, `org.previewPack`, `access.*` and `model.propose` each exist on the server. Nothing imports the old `pages/access/orgs/PilotReport` path. `SourceDrawer`'s `org_unit_id: null` passes `validate` (None is accepted).
- `_clean`'s wider SECRET_WORDS (ours) do not match any input key of his new actions.
