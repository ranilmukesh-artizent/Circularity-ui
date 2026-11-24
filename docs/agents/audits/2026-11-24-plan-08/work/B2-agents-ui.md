# B2: agents UI (U2, U5, U7, U8)

All edits are in the fix worktree `Circularity-ui-fix`. I ran no git commands that change state.

## Changed
- **U5 Register an agent** (Admin only, `s.can.manage`): a "Register an agent" button on the Agents registry opens a form with id, name, kind, autonomy (read|propose|act), tools (the MCP tools plus the catalogue actions an agent may call) and org scope (none ticked means every org). It sends `agent.register`. The id is checked as the server checks it, and the form shows the server's refusal inline.
  Files: `frontend/src/pages/agents/AgentsPage.tsx`, new `pages/agents/register.ts` (`idProblem`, `registerBody`, `toolOptions`; EditModal reuses `toolOptions`), `api/agents.ts` (`registerAgent`, `NewAgent`).
- **U7 Proposals on Home**: new `pages/home/HomeProposals.tsx` reads `GET /api/screens/home/proposals` (new `api/proposals.ts` `useMyProposals`).
  - It sits at the top of Home's right column and renders nothing when the list is empty, so parity holds. It has its own Suspense and a quiet error boundary, so Home never waits for it or fails on it.
  - Accept and Reject (reason of at least 5 characters, enforced client-side too) live in a shared `pages/agents/ProposalList.tsx`, which the Agents page also uses now.
  - A refusal shows the server's own message under the list. This includes the new maker-checker `conflict`.
  - One-line edit in `pages/home/HomePage.tsx`: the import and `<HomeProposals />`.
- **U2 Model fit and promote**: new `pages/modeler/ModelsPanel.tsx` on the Modeler, for the current template.
  - "Fit a candidate" shows for `manageFlows`. "Promote" shows for `approve.flows`, and the person who fitted the candidate sees "You fitted this model, so another person promotes it." Each model shows its status, maker and promoter, and MAE active → candidate.
  - A failed read shows inline. Facade: new `api/models.ts` (`useModels`, `fitModel`, `promoteModel`, `maeChange`).
  - **No read listed the models** (the only one was the text in `learning_status`), so I added the read action `model.list {template?}` (see shared files).
- **U8 Rule suggestions**: new `pages/modeler/SuggestionsPanel.tsx` for those with `can.edit` or `can.approve`.
  - "Find suggestions" runs `flow.suggestions` on demand. It shows the share line, blocked suggestions in red, conflict checks and the simulated impact.
  - "Apply as draft" (`can.edit` only) goes through `applySuggestion`: `flow.saveDraft {graph, source:'assistant', note:'Suggested from overrides: …'}`. It never submits or publishes.
  - `ModelerPage.tsx` now shares one `applyGraph` helper between the assistant and the suggestions. A new third row holds the two panels. Facade: `api/modeler.ts` (`ruleSuggestions`, `applySuggestion`, types). Wording helpers: new `pages/modeler/learning.ts`.

## Shared files touched
- `frontend/src/api/invalidation.ts`: added `'flow.suggestions'` to the read actions (one token on the flow.* line; B1's org line is separate).
- `backend/di/services/actions/models.py`: `model.list` read action. The guard allows `manageFlows` or `approve.flows` (else `out_of_scope`) and refuses an unknown template.
- `backend/di/repositories/model_versions.py`: `of_template()`, newest first.
- New `backend/tests/test_model_list.py`, which reuses the `outcomes` fixture of `test_model_promote.py`.

## Tests (TDD)
- New: `api/proposals.test.ts`, `api/models.test.ts`, `pages/agents/register.test.ts`, `pages/modeler/learning.test.ts`. Extended: `api/agents.test.ts` (register), `api/modeler.test.ts` (suggestions, apply, no invalidation).
- Red first: `webcheck-fix.sh vitest <5 files>` gave "Test Files 5 failed (5) · Tests 4 failed | 6 passed", for the right reasons (missing modules and functions, `flow.suggestions` invalidating). Green: "Tests 19 passed (19)".
  - `learning.ts` was written together with its test (not run red first).
- Backend red: `FIX_DB=di_fix_b2 fixtest.sh tests/test_model_list.py` gave "2 failed" (`not_found`: no action). Green: `fixtest.sh tests/test_model_list.py tests/test_model_promote.py tests/test_agent_catalog.py tests/test_screens_agents.py` gave **23 passed**. I created the private database `di_fix_b2` for this (`createdb`). Ruff check and format pass on the 3 backend files.
- Final run, the same steps as `webcheck-fix.sh lint` with exit codes printed:
  `tsc=0` · `Test Files 38 passed (38)` · `Tests 304 passed (304)` · `eslint=0` · `knip=0`.
- Read-only browser check: a throwaway Vite container from the worktree on :5179, proxying to the running api, signed in as admin. The register modal opens and shows the id hint. Its checkbox layout matches the existing Edit modal. The Modeler shows both new panels, and "Find suggestions" answered "0 decisions read".
  - The models panel showed "No action model.list." inline, because the running api is the main repo without the backend change. The rest of the page was unaffected.
  - Home rendered with no proposals panel (empty list). I stopped the container and removed the git-ignored `frontend/public/` and `frontend/src/styles/` that `extract-styles` created.

## Open
- Not exercised in a browser with data: an accept or reject on Home with a real pending proposal, a fit or promote against the new backend, and Apply as draft. Doing so writes, so I left it to the lead or the smoke tests.
- The Home proposals panel shows for any role that has pending proposals (the server filters), not only Planner and Approver.
- `model.list` appears in the agent tool catalogue as a read (`agent_allowed`). `test_agent_catalog` still passes.

## Follow-up: manual import of tool_fleet and device rows (coordinator)
- New `frontend/src/pages/integration/importCsv.ts` (+ `importCsv.test.ts`). `validateCsv(text, template, facilities, tenants)` moved here from Records.tsx.
  - For tool_fleet and device, `asset_id` must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`, with the server's message. Industrial keeps the class pattern.
  - Each row keeps its template's columns (tool_fleet `cls, ft, site, rul`; device `brand, model, band, ref, doh`), valid or rejected.
  - `templateColumnsNote(template)` is the help line. `importSummary(ok, output)` is the toast text.
- `Records.tsx`: rows are checked for the template the cases open with (industrial when "Open a case" is off).
  - Rows are checked again when the switch or the template changes, but not once loaded.
  - A help line under "Required columns" names the template's extra columns. There is no modal: the import help is that note.
  - The toast reads "Cases: N opened, N already open, N not opened." plus each failure as "asset_id: reason". With failures it stays 8 s.
- `api/integration.ts`, minimal edits only to `ImportRow`, `importInput`'s pick and `commitImport`:
  - added `TEMPLATE_IMPORT_COLUMNS`;
  - `ImportRow` takes the optional template columns;
  - pick sends the columns a row has, in both `rows` and `rejected`;
  - `commitImport` returns the new `ImportResult`, which adds `cases_failed` and `case_failures[{asset_id, code, reason}]`.
- Test added in `api/fabricRecords.test.ts`: template columns are sent in rows and rejected.
- Red: `webcheck-fix.sh vitest src/api/fabricRecords.test.ts src/pages/integration/importCsv.test.ts` gave "Test Files 2 failed (2) · Tests 1 failed | 3 passed (4)". The failures were the missing module and the template columns not sent. Green: "Test Files 2 passed (2) · Tests 10 passed (10)".
- Final, the same steps as `webcheck-fix.sh lint`: `tsc=0` · `Test Files 40 passed (40)` · `Tests 314 passed (314)` · `eslint=0` · `knip=0`.
- Not checked in a browser: loading writes, and the running api does not have agent A's backend change yet.
