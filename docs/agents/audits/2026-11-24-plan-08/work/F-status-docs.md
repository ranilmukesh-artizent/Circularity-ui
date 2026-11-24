# F: status, decision and user-guide docs after the merge (24 Nov 2026)

Docs only (subagent B). No tests, no docker, no state-changing git. Behaviour checked in code at `2e985ff` before
writing: `agents/forbidden.py`, `pipeline.py` `_agent_gate`, `actions/proposals.py` (`OWN`, accept guard),
`agents/proposals.py` (`own`, `requested_by` = the acting account), `actions/modeler.py` `makers`, `org_pilot.py`
`report_guard`, `org_pack.py` `SECRET_WORDS`, `decisions.py` `_rebuild`/`revalue`, `execution/steps.py` `STEP_TPL`,
`connectors/manual.py`, `importCsv.ts`, `Records.tsx`, `SourceDrawer.tsx`, `AnalyticsPage.tsx`, `PilotReport.tsx`,
`SuggestionsPanel.tsx`, `ModelerPage.tsx`, `modeler_suggest.py`, migration 0028. All files UTF-8, LF, no BOM.

## Files changed
- `docs/backend-steps.md`: plan-8 status gains "Audit and merge (24 Nov 2026)" (F1–F10 as built, kept F5/F9/F11,
  screens added beside the gaps work, gate after the merge) and "Still open after the audit" (agent identity by header
  on a person's token, no agent CRUD path, telemetry only as `alarm`, the audit's smaller gaps, two UI checks not done
  in a browser). Earlier sections untouched.
- `docs/agents/plans/PROGRESS.md`: rows for `95a45ed`, `8fea98c`, `23c7f81`, `2e985ff` and the audit gate.
- `docs/agents/plans/08-mvp-decision-platform.md`: a Status paragraph under the header (done, audit, next).
- `docs/agents/decision-log.md`: checked the eleven 2026-11-24 rows, no duplicates or contradictions (the Gaps-B row
  "every account that may act" still holds: the requester may reject). Added five rows: `own` proposals (reject only),
  F4 gate leaves reads open, F8 scope, `model.list` kept, migration renumbering.
- `docs/guides/approvals.md`: summary table (flow makers, agent proposals, pilot report in Analytics); ground rules
  (agent refusals however the call arrives, reads open; maker-checker bullets for flows and agent proposals); section
  2 (every saver/submitter is a maker; return and rollback have no maker check, table split to match the code;
  suggestions from overrides); section 5 (`own` proposals; worked example: Admin who started the run sees it as own);
  section 7 (who reads the report, Analytics path).
- `docs/guides/users/planner.md`, `approver.md`, `admin.md`, `developer.md`, `README.md`: `own` proposals; makers;
  suggestions (Planner, Approver); Approver section 9 pilot report on Analytics and the corrected technical note (it
  said "no screen path"); Admin source drawer org field and technical note; Developer import and drawer org field.
- `docs/guides/connection-fabric.md`: Org unit in the Add source drawer and on Configuration; Manual Import "Opening
  cases from the rows" (template columns, any id, the cases message).
- `docs/guides/case-journey.md`: template cases valued by their own template, revalued on re-evaluation, own
  execution steps; hazardous-waste route among the gates, business rules after every gate.
- `README.md`: agents sentence, plan-8 screens, Status table (plans 1b/2/6/7/8 done; next plans 3–5, per-agent
  credentials).
- `docs/agents/learnings.md`, `docs/plan-fullstack-poc.md`: read, nothing now wrong; unchanged.

## Not verified
- Nothing run in a browser; UI wording is from the source (`OWN_PROPOSAL_NOTE`, `importSummary`, panel texts).
- Gate figures are quoted from the audit README (web 312 from the merge worktree has no log file).
- "Next: plans 3–5" follows AGENTS.md's order; per-agent credentials are listed as a follow-up, not scheduled.
