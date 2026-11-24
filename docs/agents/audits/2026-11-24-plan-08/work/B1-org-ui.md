# B1: org UI gaps (U1, U3, U4, U6, U9), fix worktree

## What changed (worktree `Circularity-ui-fix`)
- `frontend/src/api/orgs.ts`: `setPilot`, `pilotReport` (+ `PilotReport`), `usePilotUnits` (Access screen `orgs.pilot`),
  `inPilot` (unit or ancestor in pilot), `routeRows`, `exportPack`, `importPack` (+ `OrgPack`, `PackImport`),
  `packFileName`, `parsePack`, `orgIdFor` (id from a name).
- `frontend/src/pages/access/AccessOrgs.tsx`: per unit **Rename** (inline, `org.update`), **Pilot mode** switch
  (`org.setPilot`; shows "Pilot via X" when an ancestor is on), **Pilot report** dialog (all report fields, routes by
  name), **Export pack** (downloads JSON); new **Import a configuration pack** panel (file + target unit, shows what
  was created and the credentials still needed). Create form: separate Name and ID (ID defaults to `orgIdFor(name)`).
  All controls only with `manageOrgs`.
- `frontend/src/pages/integration/ConnectFlow.tsx`: step 2 (Scopes) has an optional **Org unit** select ("Shared by
  every org" = not sent), passed to `connectFromCatalog`; own Suspense boundary.
- `frontend/src/api/integration.ts`: `connectFromCatalog(..., secret?, org?)` sends `org_unit_id` only when set.
- `frontend/src/layout/TopBar.tsx`: "Request tenant access" enabled; opens a dialog (port of the demo's `tenantReq`:
  tenant picker of tenants not yet visible, required reason, audit note) calling `access.requestTenant`; the toast and
  the dialog say to reload the page once approved.
- `frontend/src/api/access.ts`: `requestTenant(tenant, reason)`, `requestableTenants(all, allowed)`.

## Shared files touched
- `frontend/src/api/invalidation.ts`: `org.pilotReport`, `org.exportPack` added to the read list (invalidate nothing).
- Backend (unavoidable: no read said which units are in pilot): `backend/di/services/screens/access.py` the `orgs`
  section is now `{units, pilot: sorted(pilot_units)}` (imports `org_pilot.pilot_units`; import contracts kept);
  `backend/tests/test_screens_access.py` expected `pilot: []` + new `test_orgs_lists_the_units_in_pilot_mode`.
- Created database `di_fix_b1` (empty, migrated by the tests) for my api runs.

## Tests added
- `src/api/orgs.test.ts` (+9): actions and bodies for pilot/report/export/import, `usePilotUnits`, `inPilot`,
  `routeRows`, reads invalidate nothing, `packFileName`, `parsePack`, `orgIdFor`. Run first: 9 failed ("is not a
  function"), then 13 passed.
- `src/api/access.test.ts` (new, 2): `access.requestTenant` body, `requestableTenants`. Red (2 failed) then green.
- `src/api/fabricSources.test.ts` (+1): `org_unit_id` sent when picked, left out when empty. Red (missing key) then green.
- Backend test written together with the change (not run red first).

## Commands and results
- `FIX_DB=di_fix_b1 bash .../fixtest.sh tests/test_screens_access.py` -> `13 passed, 1 warning in 22.19s`
- `FIX_DB=di_fix_b1 bash .../fixtest.sh tests/test_screens_mcp.py tests/test_writes_access_settings.py tests/test_policy_orgs.py` -> `75 passed, 1 warning in 41.20s`
- `lint-imports` -> `Contracts: 6 kept, 0 broken.`; `ruff check` + `ruff format --check` on the two backend files -> `All checks passed!`, `2 files already formatted`
- `bash .../webcheck-fix.sh lint` -> `Test Files 38 passed (38)`, `Tests 304 passed (304)`, `EXIT 0`; re-run with explicit
  codes at the end: `TSC_EXIT=0`, `Tests 304 passed (304)`, `ESLINT_EXIT=0`, `KNIP_EXIT=0` (includes B2's files as they were then).

## Left open
- Not checked in a browser: the running stack serves the main repo, not the worktree.
- Connect dialog org select shows only for accounts that can read the org tree (Access › Organisation = Admin).
  Other `manageIntegrations` roles (Engineer, Developer) still connect sources as shared; giving them a list needs an
  org read on the integration screen (backend). The Source drawer (edit) still cannot change a source's org unit.
- The request dialog does not list "Your requests" as the demo did (the requests read is Admin-only); the server
  refuses a duplicate with its own message.
- Pilot report is reachable only from Access › Organisation (Admin), though the server also lets `approve.flows` read it.
- Export file name uses the browser's date, not the simulated clock.

## Follow-up (coordinator's three items; "own earlier requests" left as is)
1. **Org list for Engineer/Developer.** `GET /api/screens/integration/overview` now has `orgs` (depth first
   `{id, name, kind, depth}`; the whole tree for an unscoped account, else its own and granted subtrees, the rule
   `_check_org` enforces) from new `di/repositories/orgs.py visible_units(p)` (same rule as
   `screens/analytics.actor_units`, which is unchanged; it could delegate to it later). Facade `orgUnits()`; the Connect
   dialog's `OrgUnitSelect` (exported from `ConnectFlow.tsx`) reads it, shown when the list is non-empty (Developer and
   Admin connect; Engineer reads it but has no `manageIntegrations`).
2. **Source drawer.** Configuration tab shows the same select (disabled without `manageIntegrations`); `saveSource(..., org?)`
   sends `org_unit_id` only when changed (`''` -> `null`, shared); Revert resets it. `Source.org_unit_id` typed.
3. **Pilot report for Approver.** New `frontend/src/components/PilotReport.tsx` (`PilotReportModal`, `PilotReportButton`,
   shown when `mayReadPilotReport(can)`: manageOrgs or approve.flows). Access › Organisation uses it; Analytics shows a
   "Pilot report" button next to its org filter once a unit is picked (read-only).

Files: backend `di/repositories/orgs.py`, `di/services/screens/integration.py`, `tests/test_screens_integration.py`;
frontend `api/integration.ts`, `api/orgs.ts`, `api/orgs.test.ts`, new `api/fabricOrgs.test.ts`, new
`components/PilotReport.tsx`, `pages/integration/ConnectFlow.tsx`, `pages/integration/SourceDrawer.tsx`,
`pages/access/AccessOrgs.tsx`, `pages/analytics/AnalyticsPage.tsx` (shared: one import, one line).

Red first:
- `fixtest.sh tests/test_screens_integration.py -k org_units` -> `E KeyError: 'orgs'` ... `3 failed, 97 deselected`
- `webcheck-fix.sh vitest src/api/fabricOrgs.test.ts` -> `TypeError: orgUnits is not a function`, `Tests 2 failed (2)`
- `webcheck-fix.sh vitest src/api/orgs.test.ts` -> `TypeError: mayReadPilotReport is not a function`, `1 failed | 13 passed`

Green:
- di_fix_b1 was empty of sources (fresh DB), so 6 older integration tests failed for that reason; I filled it once with
  `scripts/full_sync.py` in a one-off container against di_fix_b1 (reads the shared source-sim; no reset, no faults).
- `FIX_DB=di_fix_b1 fixtest.sh tests/test_screens_integration.py tests/test_screens_access.py tests/test_source_org.py`
  -> `138 passed, 1 warning in 38.90s`
- `ruff check` / `ruff format --check` (3 backend files) -> `All checks passed!`, `3 files already formatted`;
  `lint-imports` -> `Contracts: 6 kept, 0 broken.`
- `webcheck-fix.sh lint` -> `Test Files 40 passed (40)`, `Tests 314 passed (314)`, exit 0 (tsc, eslint, knip included).
  One earlier run showed `importCsv.test.ts` failing to load while another agent was writing it; it passes on its own
  and in the final run.
- Still not checked in a browser (the stack serves the main repo).
