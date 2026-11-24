# M: frontend merge (5c20ddb his + 9b14697 ours)

Worktree `Circularity-ui-merge`, `frontend/` only. Policy: where both built the same thing, his wins; ours kept only where
he has nothing. All frontend paths staged with `git add` (no commit).

## Conflicted files

| File | Result |
|---|---|
| api/access.ts | His file, byte for byte. Our `requestTenant`/`requestableTenants` dropped (his TopBar asks through `access.myAccess`). |
| api/agents.test.ts | His file (it already tests `agent.register`). |
| api/agents.ts (auto-merged, duplicated) | His file, plus `own?: boolean` on `AgentProposal` and `OWN_PROPOSAL_NOTE` (lead's F3a request). |
| api/integration.ts | His `connectFromCatalog(..., orgUnit)`. Ours kept: `saveSource(..., org)`, `org_unit_id` on `Source`, template import columns, `ImportResult`. Our `orgUnits()`/`OrgUnitOption` (overview `orgs`) dropped: SourceDrawer now uses his `useOrgUnits()`. |
| api/invalidation.ts | His list plus our `flow.suggestions` (a read). |
| api/orgs.ts, api/orgs.test.ts | His files. Our pilot/pack/`orgIdFor` helpers dropped; he has create-with-a-name. |
| layout/TopBar.tsx | His file (request access + my grants). |
| pages/access/AccessOrgs.tsx | His file; only the PilotReport import path changed (moved, below). |
| pages/agents/AgentsPage.tsx | His file (RegisterAgentDialog, ModelsPanel, his Proposals table); Accept replaced by the note when `p.own`. |
| pages/agents/register.ts, register.test.ts | His files (add/add). |
| pages/home/HomePage.tsx | His file (ProposalsCard). |
| pages/integration/ConnectFlow.tsx | His file (OrgField, defaults to the top-bar tenant). |
| pages/modeler/ModelerPage.tsx | His `ModelsPanel` from `../agents/ModelsPanel`; ours kept: `applySuggestion` and `SuggestionsPanel` in a `mdl-main mdl-lower` row (edit or approve only). |

## Ours deleted as duplicates

`api/access.test.ts`, `api/proposals.ts`, `api/proposals.test.ts`, `api/models.ts`, `api/models.test.ts`,
`pages/agents/ProposalList.tsx`, `pages/home/HomeProposals.tsx`, `pages/modeler/ModelsPanel.tsx`, our
`components/PilotReport.tsx` (replaced, below); `promoteBlock` removed from `pages/modeler/learning.ts` (+ its test).

## Moved / rewired

- His `pages/access/orgs/PilotReport.tsx` moved to `components/PilotReport.tsx` (imports adjusted, content unchanged), plus
  a small `PilotReportButton` (shown for `manageOrgs` or `approve.flows`) that opens his `PilotReportDialog`. Our
  Analytics "Pilot report" button uses it; AccessOrgs imports `PILOT_TEXT`/`PilotReportDialog` from there.
- `pages/integration/SourceDrawer.tsx`: our org unit field kept, now a local `OrgUnitSelect` over his `useOrgUnits()`
  (GET /api/screens/orgs); a saved unit the account cannot see stays shown by id. `api/fabricOrgs.test.ts` trimmed to the
  `saveSource` org test.
- `own` (lead, audit F3a): `HomeProposal.own` and `AgentProposal.own`; Home ProposalsCard and Agents › Proposals show
  "Your agent's proposal: another person accepts it." instead of Accept; Reject stays. New test in `ProposalsCard.test.tsx`.

## Ours kept (he has nothing)

SourceDrawer org unit; Records template import (`importCsv.ts` + test, `Records.tsx`); Modeler rule suggestions
(`SuggestionsPanel.tsx`, `learning.ts` `shareLine`, `api/modeler.ts` additions + `modeler.test.ts`); test updates in
`fabricRecords.test.ts`, `fabricSources.test.ts`.

## Checks (from `Circularity-ui-merge\frontend`, host Node)

- `npx tsc -b` → exit 0
- `npx vitest run` → `Test Files 39 passed (39)`, `Tests 312 passed (312)` (ours alone 314; his alone not re-run here)
- `npx eslint .` → exit 0, no output
- `npx knip` → exit 0, no output
- `grep -rln '^<<<<<<<\|^>>>>>>>\|^=======$' src` → none; no CRLF in `src`.

## Open

- Backend: the integration overview's `orgs` field (ours, audit U6) is no longer read by the frontend; the lead may drop
  it or keep it. `model.list` is no longer called by the frontend (his panel reads GET /api/screens/agents/models).
- `own` is typed optional; the Accept-hiding is untested against a live server here.
- No browser smoke run (read-only rule for subagents); Analytics pilot button and SourceDrawer org field unchecked in a browser.
