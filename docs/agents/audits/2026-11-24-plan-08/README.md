# Audit of plan 8 (decision platform MVP), phases 0–12, 24 Nov 2026

What was asked: [plan 8](../../plans/08-mvp-decision-platform.md) (72 tasks) and the stories in
[business-reviews/dover-user-stories.md](../../../../business-reviews/dover-user-stories.md). What was built:
commits `1508f1b..2a3ee00` on `feature/fullstack-poc` (76 commits, 273 files, +31,892 / −313).

Method:
1. Commits were mapped to task IDs.
2. Each task's Files, Interfaces, Tests and Done-when were checked against the code at `2a3ee00` (three read-only
   reviews: phases 0–3, 4–8, 9–12).
3. Every serious finding was re-read in the code before it was listed here.
4. The suites were run on this machine (Docker Desktop), with full logs in [evidence/](evidence/).

Scoring: a task is **met** when its files, interfaces and tests exist and do what the spec says; **partial** when
something in the spec is missing or weaker; **missing** when it was not built.

The scores, verdicts and gaps below describe `2a3ee00`, before any fix. What was fixed since, how it was merged with
the colleague's work (`2a3ee00..5c20ddb`) and what was verified is in
[After the fixes and the merge](#after-the-fixes-and-the-merge-24-nov-2026) at the end.

## Summary

| Area | Score | Basis |
|---|---|---|
| Tasks built | 9/10 | 53 of 59 build tasks met, 6 partial, 0 missing; no stubs (`TODO`, `NotImplementedError`, `not_implemented`) in any touched file |
| Fidelity to spec and PO prototype | 7.5/10 | Parser, `buildProposal`, rng, valuers and `dDecide` match the prototype; findings F1–F4 below |
| Process (plan rules R1–R17) | 4/10 | Run by 7+ parallel agents, not sequentially; phase gates 0.4 … 11.9 ran once together at the end (`PROGRESS.md:150`); the MVP-8.5 manual check has no record |
| UI for what was built | 6/10 | 9 backend features have no screen (U1–U9) |
| Governance (approvals, agents) | 6/10 | Agents cannot approve or publish; kill switch, autonomy, run limits, the "propose" hold and pilot holding all work. F3 and F4 are the gaps |
| Dover stories A–Z | ~63% (was ~36%) | Stage table below |
| Dover edge cases | ~48% (13.5 of 28) | Edge-case table below |

## Phase-by-phase

### Phase 0: harness
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 0.1 | met | `docs/agents/decision-log.md` (8 rows, `94576ed`); `00-overview.md:17` | — |
| 0.2 | met | `scripts/dev/gate-mvp.sh`, `lint.sh`, `suite-shard.sh`; `selftest.sh` +3 cases | — |
| 0.3 | met | `frontend/scripts/dump-po-golden.mjs`; `fixtures/golden/po/README.md:6` (prototype SHA-256); `test_po_golden.py` | — |
| 0.4 | partial | `PROGRESS.md:150` | No gate for phase 0 on its own; one combined gate at the end |

### Phase 1: org units
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 1.1 | met | `0019_org_unit.py`; `test_org_units.py` | — |
| 1.2 | met | `core/orgs.py`; `policy.py` (`EXTRA_PERMS`, `EXTRA_PAGES`, `tenant_ok` by subtree); `test_policy_orgs.py` | — |
| 1.3 | met | `actions/orgs.py`; `test_writes_orgs.py` | — |
| 1.4 | met | `0020_source_org.py`; `fabric_sources.py` `_check_org`/`_bind_org` | No test refuses an org outside the actor's subtree |
| 1.5 | met | `AccessOrgs.tsx`, `orgs.ts`, `orgs.test.ts` | No rename in the UI (U4) |
| 1.6 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 2: rule core (pure)
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 2.1 | met | `modeler/templates.py`, `packs/industrial.json`; `test_modeler_templates.py` | Adds the `alarm` dim (MVP-7.1) |
| 2.2 | met | `modeler/flow.py`; `test_modeler_flow.py` | — |
| 2.3 | met | `modeler/compile.py`; `test_modeler_compile.py` (5 golden cases) | — |
| 2.4 | partial | `modeler/apply.py`; `test_modeler_apply.py` | F5 (waiver); the golden never exercises `prefer`/`require` |
| 2.5 | met | `modeler/validate.py`; `test_modeler_validate.py` | — |
| 2.6 | met | `modeler/guard.py`; `test_modeler_guard.py` | Text-guard order differs (F10; blocked either way) |
| 2.7 | met | `modeler/simulate.py`; `test_modeler_simulate.py` | No golden `fSim` comparison |
| 2.8 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 3: flows, lifecycle, live rules, shadow
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 3.1 | met | `0021_decision_flow.py`; `repositories/flows.py`; `test_flows_repo.py` | The migration seed imports app code (F11) |
| 3.2 | met | `actions/modeler.py` (9 actions); `test_writes_flows.py` | F3b (maker = first editor only) |
| 3.3 | partial | `repositories/live_rules.py`; `decisions.py` `_rebuild`/`_rerank` | F2 (hazard gate after business rules) |
| 3.4 | met | `decisions.py` `submitted.flowVer`; `screens/case.py:404` | — |
| 3.5 | met | `0022_shadow_decision.py`; `_record_shadow`; `test_shadow.py` | `shadow_stats` counts earlier shadow rounds too |
| 3.6 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 4: simulation and the Modeler page
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 4.1 | met | `actions/modeler_sim.py:37-114`; `test_flow_simulate.py` | — |
| 4.2 | met | `screens/modeler.py`; `nav.py` `EXTRA_NAV`; `test_screens_modeler.py` | — |
| 4.3 | met | `frontend/src/api/modeler.ts`; `modeler.test.ts` | — |
| 4.4 | met | `ModelerPage.tsx`, `FlowCanvas.tsx`, `FlowInspector.tsx`; `flowEdit.test.ts` | — |
| 4.5 | met | `ChecksPanel`, `ImpactPanel`, `LifecycleBar`, `HistoryPanel` | — |
| 4.6 | met | `frontend/scripts/smoke-modeler.mjs` | One decline is a raw POST, not a click |
| 4.7 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 5: assistant
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 5.1 | met | `modeler/parse.py` (regexes match prototype 2415–2433) | — |
| 5.2 | met | `modeler/propose.py`; `test_flow_propose.py` vs `po/proposals` | — |
| 5.3 | met | `services/ask/modeler_read.py`; `test_flow_propose_model.py` | — |
| 5.4 | met | `AssistantPanel.tsx`, `proposal.ts` | — |
| 5.5 | met | `mcp/tools.py` `MODELER_TOOLS`; `test_mcp_modeler.py` | — |
| 5.6 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 6: tool-fleet and device templates
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 6.1 | met | `valuers/rng.py`, `valuers/tool_fleet.py`; `test_valuer_tool_fleet.py` | — |
| 6.2 | met | `valuers/device.py:218-246` | — |
| 6.3 | partial | `modeler_sim.py:95-104` | F1 (crash once a tool-fleet case is open) |
| 6.4 | met | `valuers/routes_adapter.py`; `test_routes_adapter.py` | Only 5 cases checked; F6 |
| 6.5 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 7: telemetry
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 7.1 | met | `modeler/facts.py`; `live_rules.refresh_scope_facts`; `test_telemetry_scope.py` | See "IoT" below |
| 7.2 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 8: case intake
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 8.1 | met | `cases/intake.py`; `actions/cases_intake.py`; `test_case_intake.py` | — |
| 8.2 | met | `workflow/steps/flow.py` `x_case`; `test_workflow_open_case.py` | "Only if" is equality only |
| 8.3 | met | `engine/predictor.py` `engine_class`; `test_screens_any_template.py` | — |
| 8.4 | partial | `connectors/manual.py` `open_cases`; `Records.tsx` | Every refusal counts as "already open" |
| 8.5 | partial | — | The "128 + opened" manual check is not recorded |

### Phase 9: PLM (read-only)
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 9.1 | met | `canonical/schema.py:40-53` (`part_key`, `bom_key`) | — |
| 9.2 | met | `source-sim/sim/vendors/windchill/*`; `tests/test_windchill.py` | — |
| 9.3 | met | `adapters/windchill.py`; `test_adapter_windchill.py` | Registered on reconnect, not at start |
| 9.4 | met | `repositories/plm.py`; `predictor.py:177-183`; exact-number tests | — |
| 9.5 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 10: group reporting, org pack, pilot mode
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 10.1 | met | `screens/analytics.py:171-198`; `AnalyticsPage.tsx:141` | — |
| 10.2 | met | `org_pack.py`; `test_org_pack.py:77` | F7 (secret filter by key name); no UI (U3) |
| 10.3 | met | `instructions/send.py:57,111-128`; `test_org_pilot.py:87` | F8 (no tenant check on the report); no UI (U1) |
| 10.4 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 11: agent foundation
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 11.1 | met | `pipeline.py:197-205`; `agents/limits.py` | — |
| 11.2 | met | `agents/catalog.py`; `GET /api/agents/tools` | 77 of 125 actions marked agent-allowed, but no path runs them (see "Agents and CRUD") |
| 11.3 | met | migration 0023; `actions/agents.py` | F9 (seeded agents at `act`) |
| 11.4 | met | `pipeline.py:212-215`; `actions/proposals.py` | F3a (self-accept); proposals not on Home (U7) |
| 11.5 | met | `agents/runtime.py`, `playbooks/case_autopilot.py` | — |
| 11.6 | met | `mcp/policy.py:148-157` | — |
| 11.7 | met | `connectors/mcp_client.py`; `test_mcp_client_source.py` | — |
| 11.8 | partial | `AgentsPage.tsx` | No register form (U5) |
| 11.9 | partial | `PROGRESS.md:150` | Combined gate only |

### Phase 12: learning and final gate
| ID | Verdict | Evidence | Gap |
|---|---|---|---|
| 12.1 | met | `calibration.py:37-42` (median ratio, clipped 0.5–1.5, ≥5 rows) | — |
| 12.2 | met | `actions/models.py` (fitter ≠ promoter) | Error measured on the fitted rows; no UI (U2) |
| 12.3 | met | `modeler/suggest.py`; `modeler_suggest.py` | No UI (U8) |
| 12.4 | partial | `frontend/scripts/smoke-mvp.mjs` | 4 of 12 steps call the API, not the UI |
| 12.5 | met | `2a3ee00`; `docs/backend-steps.md:816+` | Gate figures were the build's own claim; re-run below |

## Findings

Found at `2a3ee00`; the Status column is the state at `95a45ed` (details and tests in the last section).

| ID | Severity | Finding | Evidence | Status |
|---|---|---|---|---|
| F1 | serious | Opening a tool-fleet case breaks the tool-fleet Modeler screen, simulation and proposals (KeyError `status`) | `cases/intake.py:204` copies 7 fields, no `status`; `valuers/tool_fleet.py:821` reads `c["status"]`; `modeler_sim.py:96` adds open cases to the queue | fixed |
| F2 | serious | Battery/IT lots: business rules run before the hazardous-waste exclusion, so a case can end with no eligible route, no waiver, no recommendation | `actions/decisions.py:158-170` | fixed |
| F3a | serious | A person can accept a proposal their own agent call created | `actions/proposals.py:37-54` checks permission and tenant only; `agent_proposal` has no requester | fixed |
| F3b | serious | Flow maker = first editor only; a second editor can approve and publish their own changes | `actions/modeler.py:185` sets `maker` only on the first save; guards at 251, 285 | fixed |
| F4 | serious | `POST /api/actions/{id}` takes the agent name, run id and "confirmed" from client headers; forbidden actions are not refused in the pipeline | `routes/actions.py:32-48`; `pipeline.py:197-205`; `FORBIDDEN_ACTIONS` only checked against the MCP tool table (`mcp/policy.py:53`) | fixed (attribution still by header; follow-up) |
| F5 | minor | Waiver: Python reports `waived=False` when nothing was eligible before the rules; the prototype says `true` | `modeler/apply.py:59-62`; prototype line 1041 | kept by decision |
| F6 | minor | Tool-fleet/device cases are ranked by the engine's rules, not by the valuer the simulation uses | `cases/intake.py:200-215`; `modeler_sim.py:83-92` | fixed |
| F7 | minor | Org pack drops secrets by key name only (`secret`, `password`, `token`, `credential`); `api_key` would be exported | `services/actions/org_pack.py` | fixed |
| F8 | minor | `org.pilotReport` has no tenant check | `services/actions/orgs.py` | fixed |
| F9 | minor | The 9 seeded agents have autonomy `act`, so their writes are never held | migration 0023 seed | kept by decision |
| F10 | nit | Tool-fleet text guards checked in a different order from the prototype (blocked either way) | `templates.py` `TOOL_FLEET_GUARDS` | fixed |
| F11 | nit | Migration 0021 builds its seed from app code | `0021_decision_flow.py` | kept by decision |

## UI gaps at `2a3ee00` (backend works, nothing calls it)

All nine have a screen at `95a45ed`; see the last section.

U1 pilot mode and pilot report · U2 model fit and promote · U3 org pack export/import · U4 rename an org unit ·
U5 register an agent · U6 org unit when connecting a source · U7 agent proposals for Planners and Approvers
(`GET /api/screens/home/proposals` unused) · U8 rule suggestions (`flow.suggestions`) · U9 the "request access" menu item.

## Agents and CRUD across the studios

Evidence: [evidence/agent-catalog.json](evidence/agent-catalog.json) (generated from the live registry at
`2a3ee00`; not regenerated after the merge, which added `model.propose`, `model.list` and the colleague's `access.*`
and `org.*` actions).
- **Catalogue:** 125 actions, 77 marked agent-allowed.
- **What agents can actually run:**
  - External agents use MCP: 12 tools reaching 10 actions (`case.evidence`, `case.routes`, `pool.optimize`,
    `demand.find`, `analytics.models`, `evidence.request`, `decision.submit` (held), `instruction.resend`,
    `flow.get`, `flow.propose`).
  - The case autopilot uses 5 actions (`case.evidence`, `evidence.request`, `case.reevaluate`, `decision.submit`,
    `instruction.resend`).
- **No CRUD in the studios:** no agent can create, edit or delete workflows (Workflow Studio), sources or mappings
  (Connection Fabric), org units, tasks or Modeler drafts. The other 67 "allowed" catalogue actions have no path
  except the HTTP headers of F4. Since the F4 fix that path never runs a forbidden action for an agent; the other
  allowed actions still go through it.

## IoT, end to end

The AWS IoT Core adapter (`connectors/adapters/aws_iot.py`, synthetic mock) writes `asset.run_hours`, `iot_thing`
and `condition.{duty_cycle_pct, vibration_mm_s, vibration_zone, bearing_temp_c, telemetry_events, telemetry_at}`.

| Field | Used by | Effect |
|---|---|---|
| `vibration_mm_s`, `bearing_temp_c` | `modeler/facts.py` via `repositories/live_rules.py:31-48` | A yes/no `alarm` fact (≥ 7.1 mm/s or ≥ 90 °C) rules can be scoped on |
| `run_hours`, `duty_cycle_pct` | `canonical/schema.py:74,83` (field authority) | Conflicts against Maximo's meter; the value itself is not read |
| the rest | nothing | — |

The engine, the valuers and the screens read no telemetry. For the 26 Nov demo, telemetry is presented as
ingested from a mocked device platform and usable in rules (the `alarm` fact). Using it in the condition score is a
follow-up.

## Dover stories, re-scored

Scored at `2a3ee00`, not re-scored since. The "no screen" notes for A, M and Q and "no org field in Connect" (C) are
out of date: those screens now exist (U1–U8 in the last section).

| Stage | Before | Now | Why |
|---|---|---|---|
| A pilot | 0.2 | 0.6 | Pilot mode and report on the server; no screen |
| B org model | 0.1 | 0.85 | Org tree, create/move at run time, roll-ups |
| C connect per org | 0.4 | 0.7 | Sources bound to org units, Windchill mock; no org field in Connect |
| D canonical BOM | 0.3 | 0.55 | Part/BOM model, where-used; no ECO/MBOM |
| E identity | 0.2 | 0.6 | `part_key` per org unit |
| F intake | 0.1 | 0.7 | `case.open`, workflow block, import; no seeded automatic trigger |
| G condition | 0.3 | 0.3 | Telemetry only as the `alarm` fact |
| H decide | 0.4 | 0.55 | BOM parts value for opened cases; no reman/exchange routes |
| I rules (Modeler) | 0 | 0.85 | Full lifecycle; F2, F3b |
| J approve | 0.5 | 0.5 | Per role, not per org; delegation unused |
| K execute | 0.6 | 0.6 | No PLM change request, no exchange order |
| L confirm | 0.7 | 0.9 | Dead letters and replay (plan 2) |
| M learn | 0.1 | 0.55 | Calibration, model candidates, rule suggestions; no screens |
| N report | 0.5 | 0.8 | Org roll-up in Analytics |
| O agents | 0.4 | 0.7 | Registry, per-agent tools, proposals, MCP client; F3a, F4 |
| P chat edits rules | 0.2 | 0.75 | Modeler assistant |
| Q roll out | 0.1 | 0.55 | Org pack export/import; no screen |
| Z scale | 0.2 | 0.35 | Queue priorities; no async (plan 4), no 500-unit lots |

Edge cases covered: 1, 4, 11, 14, 17, 18, 20, 22, 25, 26, 28; partly: 3, 5, 9, 12, 27.

## Test evidence

Baseline at `2a3ee00` (before any fix), this machine:
- lint: all 6 checks passed ([evidence/baseline-lint.log](evidence/baseline-lint.log))
- web: tsc 0 errors, vitest 278 passed ([evidence/baseline-web.log](evidence/baseline-web.log))
- api: 4,379 passed in 40 min 44 s ([evidence/baseline-api.log](evidence/baseline-api.log),
  [evidence/baseline-api-junit.xml](evidence/baseline-api-junit.xml))
- source-sim: 271 passed ([evidence/baseline-sim.log](evidence/baseline-sim.log))
- smokes: pages (11 accounts, 0 failing routes), RT-1048 (stage 10), Modeler (all checks), MVP (all 12 steps)
  (`evidence/baseline-smoke-*.log`)

After the fixes and the merge: see the next section.

Security, compliance and privacy are out of scope for this audit. Anything touching them needs review by
Kinective's Legal team before it is relied on.

## After the fixes and the merge (24 Nov 2026)

`95a45ed` ("Plan-8 audit fixes, template cases end to end, remaining UI gaps") sits on top of the colleague's eight
commits `2a3ee00..5c20ddb` (trial package; Gaps-A tenant access requests and grants that end; Gaps-B proposals on
Home; Gaps-C out-of-office approvals; Gaps-D org screens and the Connect dialog's org unit; Gaps-E register agent and
Models panel; their docs and final gate). The fixes were built in a separate worktree by agents whose reports are in
[work/](work/) (A-templates, B1-org-ui, B2-agents-ui), then merged by the lead (M-frontend-merge) and reviewed by an
independent read-only agent (M-review).

### Findings F1–F11

The tests named here are in `backend/tests/test_audit_fixes.py` unless another file is given. The eight marked
"red first" failed against the `2a3ee00` code ([evidence/repro-before-fix.log](evidence/repro-before-fix.log):
`8 failed`).

| ID | Status | Test or decision |
|---|---|---|
| F1 | fixed | `test_f1_tool_fleet_modeler_works_with_an_opened_case` (red first); end to end in `test_template_e2e.py::test_template_case_end_to_end[tool_fleet\|device]` |
| F2 | fixed: the hazardous-waste exclusion runs before the business rules (`actions/decisions.py` `_rebuild`) | `test_f2_hazard_exclusion_comes_before_business_rules` (red first) |
| F3a | fixed: `agent_proposal.requested_by` (migration 0028); the requester still sees the proposal, marked `own`, and can only reject it | `test_f3a_requester_does_not_accept_own_agents_proposal` (red first); `frontend/src/pages/home/ProposalsCard.test.tsx`; decision-log row "Audit F3a/F3b/F4" |
| F3b | fixed: everyone who saved or submitted a draft is a maker | `test_f3b_every_editor_is_a_maker` (red first); same decision-log row |
| F4 | fixed: an agent-prepared call never runs a forbidden action (pipeline step 6, `services/agents/forbidden.py`); reads stay open | `test_f4_agent_prepared_forbidden_action_refused` (red first); Ask parity in `test_ask.py`. The agent is still named by a header on a person's token: per-agent credentials are the follow-up in the same decision-log row |
| F5 | kept by decision | decision-log row "Audit F5: `waived` stays true only when the rules caused nothing eligible" |
| F6 | fixed: template cases are valued and ranked by their template's valuer, as the simulation ranks them | `test_f6_device_case_ranked_like_the_simulation` (red first) |
| F7 | fixed: the org pack also drops key-named settings (`api_key` …) | `test_f7_pack_drops_key_named_settings` (red first) |
| F8 | fixed: `org.pilotReport` checks the tenant of a tenant-scoped person (`8fea98c`: an account that sees every tenant reads the group's report; the full suite caught the first version refusing it) | `test_f8_pilot_report_needs_the_tenant` (red first); `test_org_pilot.py::test_pilot_report_counts` |
| F9 | kept by decision | decision-log row "Audit F9: the nine seeded agents keep autonomy `act`" |
| F10 | fixed: tool-fleet text guards in the prototype's order | `test_f10_text_guards_in_the_prototypes_order` (written with the fix, not in the red-first run) |
| F11 | kept by decision | decision-log row "Audit F11: migration 0021 keeps building its seed from app code" |

Found and fixed while proving the templates end to end ([work/A-templates.md](work/A-templates.md)), each with a test
in `test_template_e2e.py`: a template case honours the business rules in its record (`rulesApplied`, the rule's
reason); manual import opens tool-fleet and device cases (`test_import_rows_open_template_cases`); a refused row
counts as failed with the intake's reason, not as "already open" (task 8.4); a template re-evaluation records a shadow
decision when the flow is in shadow (`test_template_reevaluation_records_a_shadow_decision`). `95a45ed` also adds
execution step templates for every route.

### UI gaps U1–U9

| ID | Status | Where |
|---|---|---|
| U1 pilot mode and report | done by the colleague's screen; ours adds an Analytics "Pilot report" button | `5bb95a7` Access › Organisation; his `PilotReport.tsx` moved to `frontend/src/components/` |
| U2 model fit and promote | done by the colleague's screen (two steps: `model.propose`, then `model.promote` by another person) | `31268c5` Models panel on Agents and the Modeler; our `model.list` kept as a read for agents and API clients (`test_model_list.py`) |
| U3 org pack export/import | done by the colleague's screen (import previews with `org.previewPack`) | `5bb95a7` |
| U4 rename an org unit | done by the colleague's screen | `5bb95a7` |
| U5 register an agent | done by the colleague's screen | `31268c5` Register agent dialog |
| U6 org unit when connecting a source | done: his Connect dialog field; ours adds the field to the Source drawer | `5bb95a7`; `SourceDrawer.tsx`, `fabricOrgs.test.ts` (`95a45ed`) |
| U7 proposals for Planners and Approvers | done by the colleague's Home card; ours shows the `own` note instead of Accept (F3a) | `baf90a4` ProposalsCard; `ProposalsCard.test.tsx` |
| U8 rule suggestions | done (ours): Modeler panel; "Apply as draft" never submits | `SuggestionsPanel.tsx`; `modeler.test.ts`, `learning.test.ts` |
| U9 request access | done by the colleague's screen (top-bar request plus "my grants") | `bf0c010` |

Checked in a browser after the merge ([work/S-smokes.md](work/S-smokes.md)): the Analytics pilot button (screenshot
`after-ui-pilot-report.png`) and the Source drawer org field (`after-ui-source-drawer-org.png`; widened to the
drawer's width in the docs commit). Not yet checked in a browser: the `own` note with a live proposal (covered by
`ProposalsCard.test.tsx`) and Apply as draft (covered by `learning.test.ts`).

### Merge record

- Base: the colleague's `2a3ee00..5c20ddb` (8 commits); ours on top as one commit, `95a45ed` (56 files,
  +1,273 / −148). 17 files conflicted: 3 backend, 14 frontend.
- Policy: where both built the same screen, his was kept and ours dropped; ours was added only where he had none
  ([work/M-frontend-merge.md](work/M-frontend-merge.md) lists every file). Dropped as duplicates: our proposals,
  models, pilot, pack, rename and request-access code.
- Semantic decisions:
  - His `model.propose` added to our `FORBIDDEN_ACTIONS`, which moved to `services/agents/forbidden.py`; the pipeline
    gate and `catalog.agent_allowed` read the same list.
  - Migrations: his `0027_access_grants` first, ours renumbered `0027` → `0028_proposal_requester`.
  - Proposals: the person an agent acted for still sees the proposal, marked `own`, and can only reject it (accept
    refused, F3a). His Home inbox tests and our F3a test both hold.
  - Our duplicate backend fields (`orgs.pilot` on the access screen, `orgs` on the integration overview) removed:
    his `GET /api/screens/orgs` serves them.
  - `model.list` kept as a read action for agents and API clients.
- Independent review ([work/M-review.md](work/M-review.md)) and what was done:
  1. Migration clash on a database that ran our old `0027`: on the dev database the lead ran `alembic downgrade 0026`
     with the old code before switching; `upgrade` then ran `0027` and `0028`, and `tenant_grant.expires_at`,
     `tenant_grant.revoked_at` and `agent_proposal.requested_by` exist (lead's check; no log file).
  2. Our F4 gate refused agent reads (Ask's `access.lookup`): fixed, the gate applies only to non-read actions.
  3. `test_model_list` promoted without `model.propose`: fixed, it proposes first.
  4. Dead fields and docstrings: removed or corrected.
  5. Docstrings did not mention `own`: fixed.
- Our pre-merge work is kept on the local branch `backup/audit-fixes-pre-merge` (`9b14697`) and in a stash.

### Verification

- **Parallel shards** ([work/parallel.sh](work/parallel.sh); see "Parallel shards" in `docs/agents/testing.md`): the
  api test files that are safe side by side, in 4 shards, each on its own fresh database (`di_p1..4`, migrated,
  sources registered as the worker does at start); about 7 min wall time against about 40 min serial. Result: 3,840
  passed, 3 failed, 1 skipped; the 3 failures are exactly review findings 2 and 3. After those fixes the affected
  files re-ran green (`merge-targeted-2.log`).
- **Left to the serial suite:** 37 files that reset or fault the shared source-sim, call the running api, or need a
  fabric synced by the running stack. The workflow, home, access and reference files among them also fail on a fresh
  database with the colleague's unmerged code (environmental; checked by the lead).
- **Backend lint:** ruff, format, mypy (270 files), import contracts (6 kept): all green after one reformat.
- **Frontend** (merge worktree, host Node; [work/M-frontend-merge.md](work/M-frontend-merge.md), no log file): tsc 0,
  vitest 312 passed in 39 files, eslint and knip clean.

| Evidence file | Result line |
|---|---|
| [repro-before-fix.log](evidence/repro-before-fix.log) | `8 failed, 1 warning in 22.18s` (the F tests against the `2a3ee00` code) |
| [fix-targeted-1.log](evidence/fix-targeted-1.log) | `27 failed, 717 passed, 1 warning, 5 errors` (first run in the fix worktree: 4 old tests still expected self-accept, updated in `95a45ed`; 23 + 5 MCP tests got "Connection refused": no api in a one-off container) |
| [fix-lint-backend.log](evidence/fix-lint-backend.log) | ruff `Found 3 errors` (import order), `2 files would be reformatted`; mypy `no issues found in 268 source files`; `Contracts: 6 kept, 0 broken.` (fixed before the merge) |
| [fix-web.log](evidence/fix-web.log), [after-web.log](evidence/after-web.log) | `Tests 314 passed (314)` (fix worktree, before the merge) |
| [after-lint.log](evidence/after-lint.log) | `lint: all passed` (before the merge) |
| [merge-lint-backend.log](evidence/merge-lint-backend.log) | ruff check `All checks passed!`; format `1 file would be reformatted` (`models.py`); mypy `no issues found in 270 source files`; `Contracts: 6 kept, 0 broken.` |
| [merge-lint-backend-2.log](evidence/merge-lint-backend-2.log) | `All checks passed!` · `446 files already formatted` · `Success: no issues found in 270 source files` · `Contracts: 6 kept, 0 broken.` |
| [par-merge-1.log](evidence/par-merge-1.log) | `20 passed, 1 warning in 401.28s (0:06:41)` |
| [par-merge-2.log](evidence/par-merge-2.log) | `944 passed, 1 warning in 399.20s (0:06:39)` |
| [par-merge-3.log](evidence/par-merge-3.log) | `1 failed, 1702 passed, 1 warning in 373.58s (0:06:13)` (`test_model_list.py::test_lists_the_models_newest_first`, review finding 3) |
| [par-merge-4.log](evidence/par-merge-4.log) | `2 failed, 1174 passed, 1 skipped, 1 warning in 347.53s (0:05:47)` (`test_ask.py`, "Who can approve above $5,000?" as starter and eval, review finding 2) |
| [merge-targeted-2.log](evidence/merge-targeted-2.log) | `245 passed, 1 skipped, 1 warning in 59.53s` (the affected files after the fixes) |
| [after-api.log](evidence/after-api.log) | `1 failed, 4458 passed, 1 skipped, 1 warning in 1922.30s (0:32:02)` (the full serial run at `95a45ed`; the one failure, `test_org_pilot.py::test_pilot_report_counts`, was our F8 check refusing the Approver the group report, fixed in `8fea98c`: `test_org_pilot.py` + `test_audit_fixes.py` `14 passed`) |
| [after-sim.log](evidence/after-sim.log) | `271 passed, 1 warning in 57.37s` (source-sim) |
| [after-smoke-pages.log](evidence/after-smoke-pages.log) | `pages exit 0` (11 accounts, 0 failing routes) |
| [after-smoke-rt1048.log](evidence/after-smoke-rt1048.log) | `rt1048 exit 0` (RT-1048 to stage 10) |
| [after-smoke-modeler.log](evidence/after-smoke-modeler.log) | `modeler exit 0` (17 checks) |
| [after-smoke-mvp.log](evidence/after-smoke-mvp.log) | `mvp exit 0` (12 steps) |
| `after-ui-*.png` | Analytics pilot report, Source drawer org unit, planner.a Home: rendered, no console errors but the favicon 404 |

**Gate result:** after `8fea98c` every suite and smoke that passed at the baseline passes on the combined code:
4,459 api tests (4,458 + the fixed one) and 271 source-sim, the four smokes, lint and the web checks. Not pushed.
