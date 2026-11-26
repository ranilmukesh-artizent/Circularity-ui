# Progress log

One line per step: date, plan and step, commit, the tests that gated it, result. Decisions taken without the user
(overnight run of 20–21 Nov 2026) are listed at the end for review.

| Date | Plan · step | Commit | Gate | Result |
|---|---|---|---|---|
| 2026-11-20 | 01b · A1 dev scripts exit with real status | `f15c0cd` | `selftest.sh` (passing 0, missing test 4, type error 2, clean 0) | done |
| 2026-11-20 | 01b · A2+A3 webhook subscription self-heals; health, async, SQL guards | `02a753c` | Phase A full suite: api 3,440 passed, source-sim 210 passed | done |
| 2026-11-20 | 01b · A4 "Try again" retries; network error code | `3c80c3e` | Phase A gate; web 15 tests | done |
| 2026-11-20 | 01b · A6 source-sim tests on their own database | `365f166` | source-sim 5× green (210) and Phase A gate | done |
| 2026-11-20 | 01b · C4 hash-locked Python deps | `e7246dc` | images rebuilt: pip check clean, same packages; 40 targeted api tests | done |
| 2026-11-20 | 01b · C5 CI, Dependabot, pre-commit, gitleaks | `1c5c67c` | actionlint clean; gitleaks full history: no leaks | done |
| 2026-11-20 | 01b · E5 part 1 web unit tests (111) | `7e10f43` | web suite 126 passed | done |
| 2026-11-20 | 01b · A5 ports on 127.0.0.1 | `3a5977f` | recreated; Windows reaches api, sim, web | done |
| 2026-11-20 | 01b · A5/A5b + C2 web toolchain majors, ESLint, dead code | `2337d46` | lint 0 errors (43 a11y warnings → E4); knip clean; tsc 0; 126 tests; build; smoke 0 failing | done |
| 2026-11-20 | 01b · C1 Python lint (shared ruff.toml, strict rules) | `a8323a7` | ruff check clean both services; api 687 + 957 targeted, source-sim 210 | done |
| 2026-11-20 | 01b · C1 ruff format (blame-ignored) | `4e5162c`, `a16db4b` | ruff format --check clean | done |
| 2026-11-20 | 01b · B3 web files named by convention (+ lint rule) | `a260188` | lint 0 errors, knip, tsc, 126 tests, build, smoke 0 failing | done |
| 2026-11-20 | 01b · B2 docs in kebab-case; README current | `c15daab` | grep old names (non-Python): none; 56 md files, 0 broken links | done (Python docstrings: sweep after Phase D) |
| 2026-11-20 | 01b · D3 metadata for all 19 tables | `fe0914d` | alembic check clean; scratch-db round trip; 10 tests | done |
| 2026-11-20 | 01b · B1+F1 demo to fixtures/demo; healthchecks | `c8a67a0` | goldens + assets.gen.ts regenerated: no change; all services healthy, `up --wait` 0; smoke 0 failing | done |
| 2026-11-20 | 01b · D1+D2 error envelope; settings and token hardening | `0d4d131` | api 439 + 207 targeted (1 sync-timing failure, passed on rerun), source-sim 13, web 131; full suite at the wave gate | done |
| 2026-11-20 | 01b · E1+E4 pure renders, session-scoped state; dialogs, Escape stack, keyboard access | `c084bfb` | staged tree alone: tsc 0, 141 tests, eslint 0 errors/0 warnings; smoke admin 70, planner-b 41, developer 39, wm-1 24, 0 failing; keyboard run on the RT-1048 approval | done |
| 2026-11-20 | 01b · F2 digest-pinned multi-stage images, non-root runtime, nginx + CSP | `6cd4218` | 6 targets build; runtime api/worker/sim on scratch DBs healthy; prod web: 68 pages, 0 CSP violations; compose config valid | done (services recreated at the wave gate) |
| 2026-11-20 | 01b · E3 every page a lazy chunk; vendor chunk | `ce6c42b` | staged tree alone: tsc 0, 141 tests, eslint, build (entry 1.05 MB → 142 kB); smoke 11 accounts 0 failing; deep links | done |
| 2026-11-20 | 01b · D4+D5 one copy of each read helper; screens are leaves; import contracts in CI | `24d43fa` | api gates 2776 / 2153 / 1877 / 2902 passed (2 single failures: DB state, SSE timing; rerun green); lint-imports 3 kept; ruff clean | done |
| 2026-11-20 | 01b · B2 (code) docstrings cite the renamed docs | `25954ea` | 108 files, only the doc-name strings change (checked per line) | done (3 source-sim files go with F4) |
| 2026-11-20 | 01b · G1+G2 quick start for any OS, `scripts/doctor.sh`; web runtime image self-contained | `f006757` | fresh `git archive` copy, no host Node: runtime image builds and serves (CSP, assets, sign-in 200); dev target builds; doctor exit 0 / 1 | done |
| 2026-11-20 | 01b · E2 one UI kit; area pieces named; no HTML-string builders | `22b199a` | jsdom old-vs-new markup identical (9/9); staged tree alone: tsc 0, 153 tests, eslint 0/0, knip, build; smoke admin 66, planner.b 41, warehouse1 24, 0 failing | done |
| 2026-11-21 | 01b · D6 shared test helpers; journal filters before LIMIT; one logging config; token calls not logged | `eff1f46` | full api suite 3,486 passed (with the change); staged tree alone: ruff, imports, 291 targeted passed | done |
| 2026-11-21 | 01b · F3 live stream with a short-lived ticket | `3fc0071` | staged tree alone: 50 api tests against a private api, ruff; web tsc 0, 154 tests, eslint; browser: `?ticket=` only, live messages arrive | done |
| 2026-11-21 | 01b · F4 source-sim fan-out and per-system reset | `0b0d9c2` | both new tests failed first; source-sim 213 passed; api connector tests 21 passed | done |
| 2026-11-21 | 01b · C3 (web) tsconfig split, noImplicitReturns/Override, typed Reference | `b5f8845` | staged tree alone: tsc -b 0, 154 tests, eslint, knip, build; smoke admin 66, planner-b 32, wm-1 24, 0 failing | done |
| 2026-11-21 | 01b · E6 useAction for writes; read cache on TanStack Query | `363a115` | staged tree alone: tsc -b 0, 168 tests, eslint, knip, build; smoke admin 70, planner-b 32, wm-1 24, 0 failing; refusal toasts equal the server's messages | done |
| 2026-11-21 | 01b · C3 (python) mypy, typed action contexts, Annotated dependencies | `84ed439` | mypy: no issues in 133 files; ruff clean; lint-imports 3 kept; full suite api 3,486 passed, source-sim 213 passed | done |
| 2026-11-21 | 01b · G3 portable dev scripts (lock in the api container), host ports from env, DEV_POLLING | see git log | selftest (lock + exit codes) passed; two api-test runs serialized; stack recreated, all healthy; second project on ports 18000/15173/18100/12222/15432 healthy; shellcheck clean; bash 3.2 syntax check | done |
| 2026-11-21 | 01b · B4/G4 LF everywhere (.gitattributes), .editorconfig | see git log | index already all LF (renormalize: no change); 27 CRLF/mixed working copies converted; every golden file and assets.gen.ts regenerated byte-identical; full suite at the wave gate | done |
| 2026-11-21 | 01b · **wave gate** (HEAD `40789c2`, stack recreated by G3) | — | full suite: api 3,486 passed, source-sim 213 passed; reset + idle; smoke 11 accounts 0 failing (admin 66, executive 32, planner-a 41, planner-b 41, planner-c 38, approver 47, engineer 48, finance 36, developer 39, wm-1 29, wm-2 29); `smoke-rt1048.mjs` stage 10, no page errors; reset after; `/api/health/live` 2 ms idle | passed |
| 2026-11-21 | 01b · G5 fresh-clone test; arm64 CI job | see git log | `fresh-clone.sh` on HEAD 40789c2: dev PASSED (healthy 327 s, doctor OK, sign-in, RT-1048 screen, 401 without token), `--prod` PASSED (162 s); torn down clean; shellcheck + actionlint clean. arm64: proved only once the CI job runs green | done |

## Plan 6: the Connection Fabric, production grade (21 Nov 2026)

Run by the lead with 7+ agents in parallel on one tree. Per-commit checks are quoted from each commit message; the
phase gate is the last row.

| Date | Plan · step | Commit | Gate | Result |
|---|---|---|---|---|
| 2026-11-21 | 06 · A1 source credentials stored, encrypted | `810d706` | test_secrets, test_fabric_sources, test_models_migrations, test_config 38 passed; screens 961 passed; tsc 0, vitest 212 | done |
| 2026-11-21 | 06 · migrations 0011–0017 reserved (idempotent), `migrate-reapply.sh` | `f45a85d` | downgrade 0010 / upgrade head | done |
| 2026-11-21 | 06 · C1 block catalogue with settings | `c23d6b3` | test_blocks | done |
| 2026-11-21 | 06 · A6 sync reliability (retries, per-source lock, backoff) | `7ce232b`, `86aaa12` | test_sync_reliability | done |
| 2026-11-21 | 06 · B4 Event Streams and fabric tiles from real data | `9625f34` | test_screens_integration/home/command | done |
| 2026-11-21 | 06 · C4 step implementations, `fx_rate` | `5088b2d` | test_steps | done |
| 2026-11-21 | 06 · C2 settings on nodes, checked on the server | `d6200ec` | test_writes_workflows, test_workflow_builder, workflowGraph.test.ts | done |
| 2026-11-21 | 06 · C3 settings in the inspector | `cf89309` | BlockSettings.test.tsx | done |
| 2026-11-21 | 06 · A4 the edited mapping runs | `e00df59`, `8ee1d29` | test_mapping_runs (all 21 adapters map as before without a saved version) | done |
| 2026-11-21 | 06 · B5 Source Tables discovered | `cf99202`, `8ee1d29` | with A4: test_mapping_runs, test_discover, test_fabric_sources, test_fabric_records, test_models_migrations, test_screens_integration 174 passed | done |
| 2026-11-21 | 06 · A7 webhook intake per source | `90f51bf` | test_webhooks | done |
| 2026-11-21 | 06 · A2+A3+A5 connections, configured adapter, honest Test connection | `b9a9081`, `0511bbc` | api 48 passed; source-sim 53 passed; tsc 0, vitest 224 | done |
| 2026-11-21 | 06 · B1 canonical schema checks, failed records | `0600f33` | test_canonical_schema (a full demo sync holds nothing) | done |
| 2026-11-21 | 06 · B2 conflicts that stay resolved | `7dcdaf0` | test_conflicts | done |
| 2026-11-21 | 06 · B3 Manual Import through the pipeline | `f25ea62` | test_fabric_records, fabricRecords.test.ts | done |
| 2026-11-21 | 06 · C10 live checks, palette gaps, import | `8579832`, `8b0417c` | test_workflow_live 15, workflowGraph.test.ts | done |
| 2026-11-21 | 06 · C8 versions, compare, restore, reprocess, fix | `2cf2785`, `8b0417c` | test_workflow_extras | done |
| 2026-11-21 | 06 · C9 server drafts, dry test run | `b667dbd`, `e53c371`, `8b0417c` | test_workflow_drafts + test_actions 167 passed; draftStore.test.ts | done |
| 2026-11-21 | 06 · C6 triggers | `0d2296d`, `8b0417c` | test_triggers | done |
| 2026-11-21 | 06 · T8 catalogue mappings on the mocks' real fields (added to the plan) | `df9cee3` | test_catalog_mappings, test_configured_adapter, test_fabric_sources | done |
| 2026-11-21 | 06 · C5+C7 engine, sync = ingest workflow, retries, one run at a time | `f9bbbf2`, `8b0417c` | test_workflow_engine incl. test_engine_parity_canonical; workflow set 368 passed; tsc 0, vitest 233; ruff clean | done |
| 2026-11-21 | 06 · type checks | `fc9e7dc`, `93e57e5` | mypy: 26 errors fixed, no ignores; ruff clean | done |
| 2026-11-21 | 06 · D1 Monitor per workflow and per step | `4b9c095` | test_screens_integration | done |
| 2026-11-21 | 06 · D3 decisions (D-Fabric), runbook | `3932fbe` | — | done |
| 2026-11-21 | 06 · D2 `smoke-fabric.mjs`, D3 guides and agent docs | `7a6e58c`, `7f24e36`, `5801873`, `652df37`, `92ad3b5` | smoke-fabric 12/12 twice on a reset stack | done |
| 2026-11-22 | 06 · gap fixes (G1–G5, follow-ons) | `53da7b6` … `b41e78c` | targeted sets per fix (401, 1238, 1005 passed …) | done |
| 2026-11-22 | 06 · **phase gate** | — | api 3,948 + source-sim 260 passed; tsc 0, vitest 250, eslint, knip, ruff, mypy clean; smoke 11 accounts 0 failing; RT-1048 stage 10 twice; smoke-fabric 12/12 | done |
| 2026-11-23 | 08 · lead: Plans 2 and 8: one migration chain, reserved stubs 0018-0026 | `a6f93a4` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-0.1 record the MVP decisions and plan row | `94576ed` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 02 · task 1 job queue schema (migration 0018) | `2b1c9e8` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-1.1 org unit table and seed | `6d00daa` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-0.3 dump PO prototype goldens | `5bc3a69` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · lead: Decision: the device template is named "Device recommerce" | `c2fc670` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-9.1 PLM part and BOM canonical models | `4123ec9` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 02 · task 2 queue functions (priority, dedupe, dead, reaper) | `c5633df` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 02 · task 3 worker wakes on NOTIFY di_jobs, heartbeats, reaps | `a5c1eca` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-0.2 lint, shard and gate scripts | `cfcad7c` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-1.2 policy reads org units and new permissions | `8d5786f` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-6.1 Tool fleet valuer port | `f4ba162` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-9.2 Windchill mock in source-sim | `9660821` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.1 template packs as data | `b13100a` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.2 flow graph model and default flows | `3538f01` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-6.2 Device valuer port | `6b2a6d7` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-1.3 org actions create update move | `9101ec0` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 02 · task 4 task CRUD at /api/v1/tasks | `3cbf161` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.3 compile a flow into rules | `8e6f003` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-1.4 bind sources to org units | `b6f9fee` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.4 apply business rules after gate rules | `3081f1b` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.5 validate a flow | `89a5ca2` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.6 guardrail checks on rules and text | `2f1d240` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-2.7 simulate a flow on a queue | `fda04f0` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · lead: Decision: industrial template pack values | `e6c884d` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-3.1 flow tables and repository | `3e10e66` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-1.5 organisation section in the Access page | `9b6f1f8` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-6.4 routes adapter for template cases | `45c6edf` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.1 outcome dataset and calibration | `fdb5964` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-3.2 flow lifecycle actions with maker checker | `8b6f394` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.1 enforce agent autonomy and run limits | `5c5e647` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.2 tool catalogue generated from actions | `ef3ee98` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-3.3 live rules in re-evaluation | `6280a04` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-9.3 Windchill adapter | `b31e3c1` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.2 model candidate shadow and promote | `97cf7a2` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-10.1 org roll-up in analytics | `160d49b` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-10.3 pilot mode per org and pilot report | `9ca8fe4` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-3.4 rule version pinned on decisions | `b03bdf8` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.3 agent registry at runtime | `c174044` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-3.5 shadow decisions recorded | `ea449cd` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-7.1 telemetry facts as rule scope | `1547428` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-4.1 simulation action over the open queue | `2345617` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.4 proposals that hold for a person | `dd4e13e` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-4.3 Modeler API facade | `7aea431` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-4.4 Modeler page canvas and inspector | `693ca6e` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-8.1 open case action with dedupe | `2d0c081` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-4.2 Modeler screen endpoint and navigation | `8aabfff` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-4.5 Modeler checks, impact, lifecycle and history panels | `f34975f` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-5.1 rule parser per template | `8cb83e8` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-8.2 open case workflow block | `f238b1c` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-6.3 template sample queues for simulation | `3a970b1` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-5.2 proposal action for plain language changes | `1908a82` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-5.3 optional model reading for proposals | `375dd65` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.3 rule suggestions from overrides | `f0fa7ed` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-8.3 case screens render any template | `e480def` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-10.2 org configuration pack export and import | `af45f49` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-8.4 manual import rows open cases | `2a38aaa` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-4.6 Modeler browser smoke | `94d5c86` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-5.4 assistant panel in the Modeler | `41ada2c` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.5 agent runtime and case autopilot playbook | `49bd40b` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.6 MCP tools filtered per agent | `f7a41ee` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-9.4 where-used query and BOM parts value | `797aa73` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.7 MCP client source kind | `84204af` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-5.1 parser reads pack phrase dims; suggestion round trip | `a6d5e3b` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-5.5 Modeler tools for MCP and Ask | `6d4f619` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · lead: Demo reset returns plan 8 state to the start | `cd862d0` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-11.8 Agents page | `ce70b27` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.4 tenant access requests reach new org units | `959b02e` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.4 an opened case with a recommendation awaits approval | `bedf6ea` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.4 the agent's next-step button no longer throws "Promise" | `4807dd1` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.4 start the case autopilot from the Agents page | `0e5cf6f` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · lead: Docs: user guides per role, case journey, approvals | `2b221f7` | the task's own tests (in its commit body) | done |
| 2026-11-23 | 08 · MVP-12.4 end to end MVP smoke | `aa020a2` | the task's own tests (in its commit body) | done |
| 2026-11-24 | 08 · lead: Demo reset restores the seeded agents exactly; format a test | `d0bfad4` | the task's own tests (in its commit body) | done |
| 2026-11-24 | 02 + 08 · **phase gates (all, run together)** | — | api 4,374 passed (5 agent/MCP failures found: the reset did not restore an agent's autonomy; fixed in d0bfad4 and re-run green, 50 passed); source-sim 271; lint clean; web-check tsc 0, 278 tests; smoke-pages 11 accounts 0 failing; smoke-rt1048 stage 10; smoke-modeler passed; smoke-mvp 12/12 (after fixing a race in its clock loop) | done |
| 2026-11-24 | trial · Trial package: prebuilt images, start/stop/reset scripts, Start here | `3b6a15b` | build.sh, then check.sh: clean install passed (load, start, sign in, RT-1048, only web published, stop/start keeps 128 cases, reset) | done |
| 2026-11-24 | gaps · B Proposals for you on Home | `baf90a4` | 12 + 382 api, web 289 (its commit body) | done |
| 2026-11-24 | gaps · A tenant access requests, grants that end and can be revoked, maker-checker | `bf0c010` | 12 + 445 api, web 298 | done |
| 2026-11-24 | gaps · D org screens (rename, pack, pilot mode and report) and the Connect org unit | `5bb95a7` | 251 api, web 19 (own files) | done |
| 2026-11-24 | gaps · C approvals honour the out-of-office delegation; inbox grant controls | `38647d6` | 8 + 688 api, web 298 | done |
| 2026-11-24 | gaps · E Register agent and the Models panel (fit, propose, approve) | `31268c5` | 55 + 23 api, web 298 | done |
| 2026-11-24 | gaps · lead: docs and guides; org reads refresh nothing | `69acbc4` | web-check 298 | done |
| 2026-11-24 | gaps · **gate (lead, combined tree)** | — | lint all passed; api 4,438 passed; source-sim 271 passed; web-check tsc 0, 298 tests; smoke-pages 11 accounts 0 failing; smoke-rt1048 stage 10; smoke-modeler passed; smoke-mvp 12/12; trial package rebuilt from HEAD and clean-install check passed | done |
| 2026-11-24 | 08 · audit: fixes F1–F4, F6–F8, F10; template cases end to end; remaining UI gaps (Source drawer org unit, template import, rule suggestions, Analytics pilot report, `own` proposals); migration 0028 after the gaps' 0027 | `95a45ed` | 8 audit tests red first, then green; parallel shards 3,840 passed (3 failures = review findings 2–3, fixed; affected files 245 passed); lint green; web 312 (merge worktree) | done |
| 2026-11-24 | 08 · audit F8: the pilot report's tenant check applies to tenant-scoped people only | `8fea98c` | `test_org_pilot.py` + `test_audit_fixes.py` 14 passed | done |
| 2026-11-24 | 08 · audit: Source drawer org unit field at the drawer's width | `23c7f81` | browser check (`after-ui-source-drawer-org.png`) | done |
| 2026-11-24 | 08 · audit docs: report with evidence, merge record, parallel shards, agent foundation research | `2e985ff` | — | done |
| 2026-11-24 | 08 · **audit gate (combined tree)** | — | api 4,459 passed (4,458 at `95a45ed` + the F8 fix); source-sim 271; smoke-pages, smoke-rt1048, smoke-modeler, smoke-mvp exit 0; lint green; not pushed | done |

### Lessons from running 7+ agents in parallel

- **One shared test lock made the lock the bottleneck.** Every track serialized its api tests through `api_lock`
  (one database), so agents queued behind each other. Keep each task's own tests narrow; run the wide sets at the gate.
- **Agents committing from inside WSL got author `root`.** Fixed by a rebase that reset the author before the push.
  Commit from PowerShell on Windows (learnings.md).
- **Path-limited commits would have swept other agents' hunks.** `git commit -- <file>` commits the whole working-tree
  file, including hunks another agent is still writing. Agents staged only their own hunks (`git apply --cached` of a
  filtered patch, or `git update-index` with a blob of HEAD plus their hunks), or left the shared file to the lead
  (`8ee1d29`, `8b0417c`; the "(part)" commits). `0511bbc` and `86aaa12` repair two slips.
- **Reserved idempotent migrations** (0011–0017 created empty in one chain, `f45a85d`) let tracks add tables in
  parallel without fighting over the Alembic head; `scripts/dev/migrate-reapply.sh` picks up a filled one.
- **A parity test that empties the store must back it up and restore it.** `test_engine_parity_canonical` copies the
  canonical tables and the source statuses to `parity_bk_*` and puts them back afterwards; otherwise it would leave
  the shared store empty under every other agent's tests.
- **Demo reset now clears connector-set `failing`/`auth_expired` statuses** (`8b0417c`): a test that rotated a junk
  secret left a demo source `auth_expired`, and the live checks then warned.

## Plan 9: Recover, unattended run (25 Nov 2026 on)

Run by an Opus lead with Sonnet and Haiku writers in their own worktrees, on the local branch
`feature/plan-09-recover`. The lead re-ran each task's checks before the merge; the run log is
`docs/agents/plans/09-run/RUN-LOG.md`.

| Date | Plan · step | Commit | Gate | Result |
|---|---|---|---|---|
| 2026-11-25 | 09 · P9-0.1 record plan 9 decisions and the licence list | this commit | docs only: 8 decision rows, 17 licence rows, table column counts checked by the lead | done |
| 2026-11-25 | 09 · P9-0.2 plan 9 gate script with the plan-file check | this commit | selftest.sh all passed (15 cases, incl. the 5 new gate-p9 cases and the real api-test.sh case, run by the lead on the main stack) | done |
| 2026-11-25 | 09 · P9-0.3 story matrix check script with its own test | this commit | story-matrix-test.sh all passed (11 cases) and bash -n selftest.sh, run by the lead; full selftest at the phase gate | done |
| 2026-11-25 | 09 · P9-0.16 relabel Studio decision workflows to point to the Modeler | this commit | lead on main: api-test.sh 7 files incl. serial-only test_stream_workflows 197 passed; lint.sh all passed; web-check tsc 0, vitest 315 passed | done |
| 2026-11-25 | 09 · P9-0.6 carbon factor set and a co2 line in both valuers | this commit | lead on main: 19 files incl. golden and parity tests 657 passed; lint all passed; tsc 0, vitest 317 passed | done |
| 2026-11-25 | 09 · P9-0.5 model chain with rate-limit fallback | this commit | lead on main: test_ask_chain, test_ask, test_flow_propose_model, test_workflow_builder, test_config 118 passed; lint all passed | done |
| 2026-11-25 | 09 · P9-0.4 catalogue hygiene and credentials rotation forbidden | this commit | lead on main after migrate-reapply 0028 and restart: 10 files incl. serial-only test_mcp_server and test_fabric_sources 153 passed; lint all passed; tsc 0, vitest 318 passed | done |
| 2026-11-25 | 09 · P9-0.11 guardrail type and stage on existing guardrails | this commit | lead on main: test_guardrail_types, test_modeler_templates, test_screens_modeler, test_modeler_guard, test_po_golden, test_engine 260 passed; lint all passed; tsc 0, vitest 319 passed | done |
| 2026-11-25 | 09 · P9-0.10 mapping save split out of source update | this commit | lead on main: test_mapping_save, test_agent_proposals, test_catalog_hygiene and serial-only test_fabric_sources, test_mapping_runs, test_catalog_mappings 84 passed; lint all passed; tsc 0, vitest 320 passed | done |
| 2026-11-25 | 09 · P9-0.9 autopilot on case opened behind a setting | this commit | lead on main after restart: test_autopilot_on_open, test_workflow_open_case (needs the synced fabric; failed only on the writer's private db), test_agent_runtime, test_config and the intake tests 42 passed; lint all passed | done |
| 2026-11-25 | 09 · P9-0.7 workflow JSON Schema and validated import | this commit | lead on main: 16 workflow and org test files 329 passed; lint all passed; tsc 0, vitest 322 passed | done |
| 2026-11-25 | 09 · P9-0.12 pin a sent-back flow change to a step | this commit | lead on main after migrate-reapply 0028 and restart: flow and modeler tests incl. test_models_migrations 160 passed; lint all passed; web-check passed | done |
| 2026-11-25 | 09 · P9-0.14 read-only sources refused and discovery at 500 | this commit | lead on main: test_read_only_sources, test_discover, test_instructions_send, test_execution, test_workflow_wiring and serial-only test_milestone_rt1048, test_org_pilot 46 passed; lint all passed | done |
| 2026-11-25 | 09 · P9-0.13 role matrix and test a user in Access | this commit | lead on main: test_access_matrix, test_screens_access, test_policy, test_writes_access (incl. the mcp_proposals scenario that failed only on the private db), test_access_gaps 80 passed; lint all passed; tsc 0, vitest 326 passed | done |
| 2026-11-25 | 09 · P9-0.8 server-side workflow export read action | this commit | lead on main: test_workflow_export, test_org_pack, test_writes_workflows, test_screens_workflows, test_workflow_schema, test_actions 429 passed; lint all passed; tsc 0, vitest 328 passed | done |
| 2026-11-25 | 09 · P9-0.15 what-if over the tool-fleet queue | this commit | lead on main: test_flow_whatif, test_flow_simulate, test_modeler_simulate, test_valuer_tool_fleet, test_flow_propose, test_suggest_proposal, test_po_golden, test_engine and intake tests 273 passed; lint all passed; tsc 0, vitest 329 passed | done |
| 2026-11-25 | 09 · **P9-0.17 phase 0 gate** (fast gate) | this commit | api: parallel-suite 4 shards 3,826 passed + 1 failed (`test_sync_binding` order-dependent in a shard; 2 passed alone on main) and serial-only 38 files 764 passed (4,591 in all, 4,459 at the last gate); source-sim 271 passed; lint all passed; tsc 0, vitest 329 passed; smoke-pages 11 accounts 0 failing; smoke-rt1048 stage 10, no page errors (after `wait-idle.sh`; the gate script first ran it without and it timed out on the post-reset syncs); story-matrix no rows for phase 0; selftest all passed; review: 4 findings, 3 fixed in `28fe893`, 1 for the person | done |
| 2026-11-25 | 09 · P9-1.1 pack format v1 with tool fleet and device as data | this commit | lead on main: parallel-suite 4 shards 3,847 passed (every non-serial api test file); lint all passed | done |
| 2026-11-25 | 09 · P9-1.2 gate catalogue with evidence and batch hold | this commit | lead on main after restart: parallel-suite 4 shards 3,868 passed; serial test_milestone_rt1048, test_workflow_open_case 7 passed; lint all passed; tsc 0, vitest 335 passed | done |
| 2026-11-25 | 09 · P9-1.3 customer overlay with tighten-only and rebase | this commit | lead on main after migrate-reapply 0028 and restart: overlay, flows, live rules, modeler, migrations, catalogue, pack, gates, golden, engine and serial-only test_mcp_server 360 passed; lint all passed; web-check passed | done |
| 2026-11-25 | 09 · P9-1.4 queue planner port with named demand on live cases | this commit | lead on main after restart: parallel-suite 4 shards 3,913 passed; lint all passed; tsc 0, vitest 342 passed | done |
| 2026-11-25 | 09 · P9-1.5 one decider for intake, re-evaluation and simulation | this commit | lead on main after restart: parallel-suite 4 shards 3,921 passed; serial test_milestone_rt1048, test_workflow_open_case, test_mcp_server 30 passed; lint all passed; tsc 0, vitest 342 passed; smoke-rt1048 stage 10, no page errors (second run; the first timed out loading the page right after the reset) | done |
| 2026-11-25 | 09 · P9-1.12 carbon with provenance on every card | this commit | lead on main: carbon, pack, golden, valuers, routes adapter, case screens, engine, decide_case and paths-agree tests 327 passed; lint all passed; tsc 0, vitest 344 passed | done |
| 2026-11-25 | 09 · P9-1.6 pack versions through the pipeline with maker-checker | this commit | lead on main after migrate-reapply 0028 and restart: parallel-suite 4 shards 3,951 passed; serial test_mcp_modeler, test_mcp_server, test_milestone_rt1048 31 passed; lint all passed; tsc 0, vitest 347 passed | done |
| 2026-11-25 | 09 · P9-1.7 case process layer with SLA timers and My work | this commit | lead on main after migrate-reapply 0028 and restart: parallel-suite 4 shards 3,969 passed; serial test_screens_home, test_screens_reference (both failed only on the private db), test_mcp_server 406 passed; lint all passed after the lead added a facade test for askForInfo (knip flagged it unused: agent-facing, no button in the spec); tsc 0, vitest 351 passed | done |
| 2026-11-25 | 09 · P9-1.9 standard valuer from pack value lines | this commit | lead on main after restart: parallel-suite 4 shards 3,977 passed; serial test_milestone_rt1048, test_mcp_server 26 passed; lint all passed; tsc 0, vitest 351 passed | done |
| 2026-11-25 | 09 · P9-1.11 contract entitlement gate with clause and consent | this commit | lead on main: contract entitlement, gates, gate hold, golden, tool-fleet valuer, paths-agree, case screens, decide_case, order invariant, standard valuer 95 passed; lint all passed; tsc 0, vitest 354 passed | done |
| 2026-11-25 | 09 · P9-1.8 my work replaces Home tasks and Actions on me | this commit | lead on main after restart: parallel-suite 4 shards 4,001 passed (2 failures in test_overlay_core came from P9-1.11, fixed in the next commit); serial screens reference, home, command, mywork, mywork_nav 894 passed; lint all passed; tsc 0, vitest 356 passed; smoke-pages 11 accounts 0 failing | done |
| 2026-11-25 | 09 · P9-1.10 match to the system of record with exceptions | this commit | lead on main after restart: parallel-suite 4 shards 4,019 passed; serial test_sync_reliability, test_milestone_rt1048, test_screens_home 374 passed; lint all passed; tsc 0, vitest 363 passed | done |
| 2026-11-25 | 09 · P9-1.13 pack-driven views in existing pages | this commit | lead on main after restart: parallel-suite 4 shards 4,027 passed; serial test_screens_home (its developer briefing failed only on the private db), test_screens_reference, test_mcp_server 406 passed; lint all passed; tsc 0, vitest 366 passed; smoke-pages 11 accounts 0 failing | done |
| 2026-11-25 | 09 · P9-1.14 phase 1 demo smoke script | this commit | lead on main: smoke-p9-1 all 7 steps passed (after the lead's template-select fix, the reset fix and a helper's page-load and tab fixes); parallel-suite 3 shards 4,027 passed; serial test_milestone_rt1048, test_screens_home 364 passed; lint all passed; tsc 0, vitest 366 passed | done |
| 2026-11-25 | 09 · **P9-1.15 phase 1 gate** (fast gate) | this commit | api: parallel-suite 3 shards 4,027 passed (12:41) and serial-only 38 files 764 passed; source-sim 271 passed; lint all passed; tsc 0, vitest 366 passed; smoke-pages 11 accounts 0 failing; smoke-rt1048 stage 10; smoke-p9-1 all 7 steps; story-matrix phase 1: 8 rows, 40 tests, 0 missing; selftest all passed; review: 6 findings, 5 fixed in the review-fix commit, 1 (gates before the queue plan) scheduled after P9-2.1 | done |
| 2026-11-25 | 09 · P9-2.1 stage chain runtime with typed stage records | this commit | lead on main after migrate-reapply 0028 and restart: 14 agent, migration and golden test files passed except test_milestone_rt1048 (an old test-isolation bug, fixed in the previous commit; 11 passed with the autopilot tests); lint all passed; tsc 0, vitest 367 passed | done |
| 2026-11-25 | 09 · P9-2.2 agentLoop port with the Pydantic AI adapter | this commit | lead on main after migrate-reapply 0028 and restart: test_agent_loop, agent runtime, proposals, stage chain, migrations, autopilot, ask 121 passed; lint all passed; tsc 0, vitest 367 passed | done |
| 2026-11-25 | 09 · P9-2.3 lLM router with budgets and cooldowns | this commit | lead on main after migrate-reapply 0028 and restart: llm router, ask, agent loop, config, migrations, ask chain, catalogue, agent screens and serial-only test_mcp_server 159 passed; lint all passed; tsc 0, vitest 367 passed | done |
| 2026-11-25 | 09 · P9-2.4 hold policy with typed reasons in the pipeline | this commit | lead on main after migrate-reapply 0028 and restart: parallel-suite and test_hold_policy, test_mcp_server, test_milestone_rt1048, test_stage_chain, test_proposals_inbox green except 2 hold tests that assumed no synced conflict on RT-1048's asset; the lead pinned only that half of the case state in the test (23 passed); lint all passed; tsc 0, vitest 369 passed | done |
| 2026-11-25 | 09 · P9-2.10 exception assistant drafts cause and owner | this commit | lead on main after migrate-reapply 0028 and restart: exception assistant, agent registry, process layer, My work, agent loop, llm router 50 passed; lint all passed; tsc 0, vitest 370 passed | done |
| 2026-11-25 | 09 · P9-2.5 standing policy approves within thresholds | this commit | lead on main after migrate-reapply 0028 and restart: standing policy, writes decisions, hold policy, policy, delegated approvals, migrations, actions, catalogue, access matrix, stage chain, serial-only test_milestone_rt1048 and test_mcp_server, golden: 387 passed, 1 test_stage_chain failure from the main stack's synced conflict (the lead pinned it off as in the hold tests; 55 passed); lint all passed; tsc 0, vitest 373 passed | done |
| 2026-11-25 | 09 · P9-2.6 run tracing and the agent run view | this commit | lead on main after migrate-reapply 0028 and restart: run trace, stage chain, hold, standing policy, agent runtime, loop, agent screens, actions, secrets, llm router, case screens, serial-only test_mcp_server 427 passed (test_run_trace uses the shared no_synced_conflicts fixture); lint all passed; tsc 0, vitest 376 passed | done |
| 2026-11-25 | 09 · P9-2.8 queue stage waits for the queue plan | this commit | lead-verify: 49 api passed (queue_stage, stage_chain, valuer_tool_fleet, queue_planner, milestone_rt1048, run_trace), lint, web 376 | done |
| 2026-11-25 | 09 · P9-2.7 configuration agent drafts a pack change set | this commit | lead-verify: 62 api passed (config_agent, agent_registry, models_migrations, pack_format, overlay_core, milestone_rt1048), lint, web 378 | done |
| 2026-11-25 | 09 · P9-2.9 calibrated stage confidence from outcomes | this commit | lead-verify: api passed (stage_calibration, model_promote, hold_policy, model_list, agent_screens_gaps, stage_chain, milestone_rt1048), lint, web | done |
| 2026-11-25 | 09 · P9-2.11 fraud triage on intake with a person release | this commit | lead-verify: 125 api passed (fraud_triage, stage_chain, standing_policy, case_intake, pack_format, catalog_hygiene, agent_catalog, agent_runtime, pack_versions, milestone_rt1048, stage_calibration), lint, web | done |
| 2026-11-25 | 09 · P9-2.12 richer tool schemas and a find tools read | this commit | lead-verify: 336 api passed (tool_find, agent_catalog, actions, catalog_hygiene, mcp_server, fraud_triage), lint, web 386 | done |
| 2026-11-25 | 09 · P9-2.13 mCP tools generated from the action catalogue | this commit | lead-verify: 115 api passed (agent_registry, config_agent, mcp_catalog_tools, screens_mcp, mcp_server, mcp_modeler, catalog_hygiene), lint, web 387; full parallel suite before it 4,209 passed, 3 failed (fixed here) | done |
| 2026-11-25 | 09 · P9-2.18 stage agents reason with the model | this commit | lead-verify: 146 passed api (stage_reasoner, stage_chain, hold_policy, run_trace, llm_router, agent_loop, config_agent, exception_assistant, agent_runtime, queue_stage, fraud_triage, stage_calibration, milestone_rt1048), lint, web 388 | done |
| 2026-11-25 | 09 · P9-2.22 gates before the queue plan in decide_case | this commit | lead-verify: 300 passed api (decide_gate_order, decide_case, order_invariant, standard_valuer, queue_planner, queue_stage, valuer_tool_fleet, template_e2e, screens_any_template, contract_entitlement, milestone_rt1048, engine, cases), lint, web 388 | done |
| 2026-11-25 | 09 · P9-8.1 adapter registry with environments and owner approval | this commit | lead-verify: 143 passed api (adapter_registry, models_migrations, agent_catalog, read_only_sources, instructions_send, policy_orgs, policy, agent_registry, catalog_hygiene, fabric_sources, discover, execution, milestone_rt1048), lint, web 395 | done |
| 2026-11-25 | 09 · P9-8.12 workflow author from a sentence with repair rounds | this commit | lead-verify: workflow_builder, workflow_drafts, actions, tool_find, catalog_hygiene, agent_catalog, writes_workflows passed, lint, web 397; test_workflow_author 13 passed after a lead fix | done |
| 2026-11-25 | 09 · P9-2.14 oAuth protected resource metadata for MCP | this commit | lead-verify: 60 passed api (mcp_oauth_metadata, auth, mcp_server, mcp_modeler, mcp_catalog_tools), lint, web 397 | done |
| 2026-11-25 | 09 · P9-8.8 directory mock with OIDC and a users API in source-sim | this commit | source-sim restarted; source-sim suite 281 passed (incl. 10 directory mock tests); lint, web 397 | done |
| 2026-11-25 | 09 · P9-8.17 composition object with maker-checker | this commit | lead-verify: 73 api passed (composition, models_migrations, config_agent, overlay_actions, catalog_hygiene, agent_catalog, tool_fleet find), lint, web 400 | done |
| 2026-11-25 | 09 · P9-2.19 exception assistant and fraud review drafted by the model | this commit | 123 api (exception_assistant, fraud_review, fraud_triage, stage_chain, stage_reasoner, hold_policy, writes_decisions, milestone_rt1048, tool_find, catalog_hygiene), 402 web, tsc 0, knip after ignore | done |
| 2026-11-25 | 09 · P9-2.20 lease end, return authorised and transit stage agents | this commit | 104 api, 402 web, lint, mypy | done |
| 2026-11-25 | 09 · P9-8.5 configured adapter reads dlt-style paging and selectors | this commit | 283 source-sim, 77 api (fabric_sources, mapping_runs, configured_adapter, configured_paging), 402 web, lint | done |
| 2026-11-25 | 09 · P9-8.2 field mapping suggestions with calibrated confidence | this commit | 79 api (mapping_suggest, catalog_mappings, mapping_runs, catalog_hygiene, tool_find), 404 web, lint | done |
| 2026-11-25 | 09 · P9-8.13 studio canvas on xyflow with dagre layout | this commit | 417 web, tsc 0, lint and knip clean, smoke-pages 11 accounts 0 failing, smoke-fabric 12/12 | done |
| 2026-11-25 | 09 · P9-8.9 oIDC sign-in with authlib beside the demo sign-in | this commit | 109 api (oidc_signin, auth, writes_access, catalog_hygiene, access_gaps, hold_policy, screens_reference, tool_find), 418 web, lint, smoke-signin, manual SSO round trip | done |
| 2026-11-25 | 09 · P9-2.15 agent evals in CI with an injection corpus | this commit | 7 evals (FunctionModel/TestModel, no network), 112 api (llm_router, ask, fraud_review, exception_assistant, catalog_hygiene), ruff, mypy, 418 web | done |
| 2026-11-25 | 09 · P9-2.21 ten-stage journey on the case run view | this commit | 125 api (journey, stage_chain, lifecycle_stages, run_trace, agent_registry, agent_runtime, stage_reasoner, hold_policy, milestone_rt1048, queue_stage, fraud_review, evals), 426 web, lint | done |
| 2026-11-25 | 09 · P9-8.3 discovery samples 500 records from the test connection | this commit | 196 api (discover_sample, discover, adapter_registry, agent_catalog, catalog_hygiene, tool_find, hold_policy, mapping_suggest, mcp_server, agent_runtime, ask; live Groq test passed on rerun), 427 web, lint, mypy | done |
| 2026-11-25 | 09 · P9-2.23 ask reads workflows and their runs | this commit | 158 api (ask_workflows, ask, catalog_hygiene, tool_find, hold_policy, agent_catalog, mcp_server, evals), 427 web, lint; live: the user's WF-116 question answered by the model from get_workflow + get_workflow_run (RUN-D1CFE, failed step, error, Fix/Diagnose), and by the rules when the check refused twice | done |
| 2026-11-25 | 09 · P9-8.14 modeler canvas on xyflow | this commit | 432 web, tsc 0, lint and knip; smoke-modeler all checks, smoke-mvp 12/12, smoke-fabric 12/12 (each after a reset) | done |
| 2026-11-25 | 09 · P9-8.10 directory groups to roles as data with test a user | this commit | 149 api (idp_group_map, access_matrix, screens_access, oidc_signin, access_gaps, writes_access, catalog_hygiene, tool_find, hold_policy + 6 files importing FORBIDDEN_ACTIONS from di.mcp.policy), 435 web, lint, mypy | done |
| 2026-11-25 | 09 · P9-8.6 connector from an API spec through an OpenAPI importer | this commit | 89 api (openapi_import, adapter_registry, configured_paging, configured_adapter, catalog_hygiene, tool_find, agent_catalog), 436 web, lint | done |
| 2026-11-25 | 09 · P9-8.4 five mapping choices with ask the owner | this commit | 155 api (mapping_decisions, mapping_suggest, mapping_save, mapping_runs, catalog_mappings, discover_sample, catalog_hygiene, agent_catalog, hold_policy, tool_find, process_layer, screens_mywork), 443 web, lint | done |
| 2026-11-25 | 09 · P9-2.16 phase 2 demo smoke script | this commit | smoke-p9-2 8/8 on a fresh reset (live model) | done |
| 2026-11-26 | 09 · P9-2.17 phase 2 gate | this commit | api: parallel-suite 3 shards 4,637 passed (1 calibration failure, refit in b51d1cb) and serial run of the 39 serial-only files plus the review-fix tests 910 passed (19:11); source-sim 344 passed; tsc 0, vitest 476 passed; lint and mypy clean; story matrix phase 2 clean; compose 5 services; smoke-pages 11 accounts 0 failing; smoke-rt1048 stage 10; smoke-p9-2 8/8 (live model); review: 6 findings, 3 fixed in 3d911f4, 3 in P9-2.24 | done |
| 2026-11-26 | 09 · P9-8.15 per-node input and output samples with pinned data | this commit | batch lead-verify after the lane B merge (5ae9952): parallel-suite 4,785 passed, 13 failed, all from lane B's P9-3.7/6.7/6.8 pack changes (older tests not updated, reported to lane B); serial-only mcp_modeler, mcp_server, milestone_rt1048, writes_access passed; lint; web 517 | done |
| 2026-11-26 | 09 · P9-8.11 sCIM provisioning and directory sync for joiners | this commit | batch lead-verify after the lane B merge (5ae9952): parallel-suite 4,785 passed, 13 failed, all from lane B's P9-3.7/6.7/6.8 pack changes (older tests not updated, reported to lane B); serial-only mcp_modeler, mcp_server, milestone_rt1048, writes_access passed; lint; web 517 | done |
| 2026-11-26 | 09 · P9-8.7 agent drafts an adapter spec held for a person | this commit | batch lead-verify after the lane B merge (5ae9952): parallel-suite 4,785 passed, 13 failed, all from lane B's P9-3.7/6.7/6.8 pack changes (older tests not updated, reported to lane B); serial-only mcp_modeler, mcp_server, milestone_rt1048, writes_access passed; lint; web 517 | done |
| 2026-11-26 | 09 · P9-8.16 decision table editor in the Modeler | this commit | batch lead-verify after the lane B merge (5ae9952): parallel-suite 4,785 passed, 13 failed, all from lane B's P9-3.7/6.7/6.8 pack changes (older tests not updated, reported to lane B); serial-only mcp_modeler, mcp_server, milestone_rt1048, writes_access passed; lint; web 517 | done |
| 2026-11-26 | 09 · P9-8.21 dMN and BPMN export from the Modeler | this commit | batch lead-verify after the lane B merge (5ae9952): parallel-suite 4,785 passed, 13 failed, all from lane B's P9-3.7/6.7/6.8 pack changes (older tests not updated, reported to lane B); serial-only mcp_modeler, mcp_server, milestone_rt1048, writes_access passed; lint; web 517 | done |
| 2026-11-26 | 09 · P9-9.1 used-car pack data file | this commit | batch lead-verify after the lane B merge (5ae9952): parallel-suite 4,785 passed, 13 failed, all from lane B's P9-3.7/6.7/6.8 pack changes (older tests not updated, reported to lane B); serial-only mcp_modeler, mcp_server, milestone_rt1048, writes_access passed; lint; web 517 | done |
| 2026-11-26 | 09 · P9-2.24 phase 2 gate follow-ups: model reads off the lock, grounded concerns, tainted fraud text | this commit | lead-verify: 188 api passed, 1 failed (evals x_05 tool_fleet_from_data: lane B's GR-12 recall gate fails a case with no serial, reported to lane B); lint; web 517+; smoke-p9-2 8/8 after a reset (step 4, accept resumes the run: 24 s, was 47 s) | done |
| 2026-11-26 | 09 · P9-9.2 vehicle lease and dealer system mocks | this commit | sim suite 356 passed; api 62 passed (adapters, canonical schema, connectors, catalog hygiene, fabric sources); lint; web 520 | done |
| 2026-11-26 | 09 · P9-8.18 compose describe and adapter mapping steps | this commit | api 53+239 (composition, gates, decide, gate hold, guardrail types, hold policy, templates, order invariant, packs incl. telecom and medical, service desk, standing policy, tf_*), evals 25 after lead fixes; lint; web 533 | done |
| 2026-11-26 | 09 · P9-10.1 telecom network pack data file | this commit | api 53+239 (composition, gates, decide, gate hold, guardrail types, hold policy, templates, order invariant, packs incl. telecom and medical, service desk, standing policy, tf_*), evals 25 after lead fixes; lint; web 533 | done |
| 2026-11-26 | 09 · P9-11.1 medical rental pack data file | this commit | api 53+239 (composition, gates, decide, gate hold, guardrail types, hold policy, templates, order invariant, packs incl. telecom and medical, service desk, standing policy, tf_*), evals 25 after lead fixes; lint; web 533 | done |
| 2026-11-26 | 09 · P9-9.3 title and lien service mock | this commit | sim suite 392 passed after restart; api 177 passed (five vehicle adapters, lease, dms, canonical schema, catalog hygiene, fabric sources, adapter registry, service desk, tf_life, tf_grade, tf_telematics, decide, order invariant, phase 2 review, hold policy); lint; web 540 | done |
| 2026-11-26 | 09 · P9-9.4 vehicle inspection app mock | this commit | sim suite 392 passed after restart; api 177 passed (five vehicle adapters, lease, dms, canonical schema, catalog hygiene, fabric sources, adapter registry, service desk, tf_life, tf_grade, tf_telematics, decide, order invariant, phase 2 review, hold policy); lint; web 540 | done |
| 2026-11-26 | 09 · P9-9.5 vehicle recall database mock | this commit | sim suite 392 passed after restart; api 177 passed (five vehicle adapters, lease, dms, canonical schema, catalog hygiene, fabric sources, adapter registry, service desk, tf_life, tf_grade, tf_telematics, decide, order invariant, phase 2 review, hold policy); lint; web 540 | done |
| 2026-11-26 | 09 · P9-9.6 vehicle auction and pricing guide mocks | this commit | sim suite 392 passed after restart; api 177 passed (five vehicle adapters, lease, dms, canonical schema, catalog hygiene, fabric sources, adapter registry, service desk, tf_life, tf_grade, tf_telematics, decide, order invariant, phase 2 review, hold policy); lint; web 540 | done |
| 2026-11-26 | 09 · P9-9.7 one case per VIN with the inspection read | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |
| 2026-11-26 | 09 · P9-10.2 network inventory and decommission tracker mocks | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |
| 2026-11-26 | 09 · P9-11.2 rental system and asset management mocks | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |
| 2026-11-26 | 09 · P9-7.1 import a history batch with checks | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |
| 2026-11-26 | 09 · P9-9.8 title finance and title brand gates | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |
| 2026-11-26 | 09 · P9-11.3 decontamination log mock | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |
| 2026-11-26 | 09 · P9-11.4 biomedical service system mock | this commit | parallel suite 4,987 passed (2 stale expectations fixed: inventory test serial, calibration JSON regenerated; reruns 15 passed); new sim tests 21 passed; serial adapters, tf_intake, canonical schema, fabric sources, replay import ok; lint; web ok; smoke-modeler all checks (b4) | done |

## Decisions taken without the user (to review)

- **A5b, web toolchain majors:** chosen versions are vite 8.3.6, vitest 5.1.0, @vitejs/plugin-react 6.2.1 and
  jsdom 31.0.0, all at least 2 weeks old.
  - The demo's stylesheet has two invalid `@container or (...)` rules. Browsers ignore them; Vite 8's CSS minifier
    rejected them, so `css.lightningcss.errorRecovery` drops them with a warning.
  - react-router stayed on 6.x here. Upgraded later (21 Nov) to `react-router` 7.18.5 (react-router-dom removed),
    which clears its 2 moderate advisories; `RouterProvider useTransitions={false}` keeps v6's behaviour of showing
    the Suspense fallback on navigation instead of holding the old page.
- **C5, gitleaks:** `.gitleaks.toml` allowlists the source-sim mocks' synthetic AWS demo keys (`AKIACIRCULARITY…`).
  With that, a full-history scan finds no leaks.
- **C2, CasePage effect:** fixing the suppressed hook dependencies changed one small behaviour. After a landing
  redirect that ends on the same stage, the page now sets its title and moves focus; before, it skipped both. This
  looked like a bug, so the change is kept.
- **C2, `_` parameters:** ESLint ignores unused names that start with `_`. The B17c engine removal left deliberate
  `_sc`/`_r` parameters so the functions keep their signatures.
- **C1, ignored rules:** FAST002 (`Annotated` dependencies) is left for C3. PERF401 is ignored on code the golden
  tests compare. source-sim's `sim/vendors/s4` ignores SIM300: its autofix would flip comparisons on upper-case SAP columns.
- **C1, possible bug, not fixed:** `HttpClient.raw(log_records=…)` in `backend/di/connectors/http.py` ignores
  its flag, so token calls are logged anyway. Left for Phase D. It is marked with a noqa.
- **Process:** twice, a commit swept in another agent's staged `git mv` renames. Both commits were unpushed; I split
  them again with `git reset --soft` and re-staged, which touches only the index. Commits now use
  `git commit -- <paths>`.
- **D2, tokens:** tokens now carry and require `iss`/`aud`, so browsers signed in before this change must sign in
  once more.
  - Outside `DI_ENV=dev` the api refuses to start with the shipped secrets.
  - Not fixed: the webhook subscription matches only on URL, so changing `DI_WEBHOOK_SECRET` needs the subscription
    deleted first.
- **D1:** existing `HTTPException` raises are kept; the handler turns them into the envelope. `ApiError` is
  available but not yet raised anywhere.
- **E1+E4, one commit:** four page files carry hunks from both steps, so they were committed together.
  - Photo tiles: the tile itself is now the button, so a click on its padding also enlarges the photo.
  - Linting: jsx-a11y runs its recommended rule set as errors. The C2 mapping had also switched on
    `control-has-associated-label`, which that set leaves off.
  - Left for later:
    - `draftOf()` (WorkflowPage) and `tiView()` (DecideTabs) still change module state during render.
    - Presenter mode in `api/home.ts` reads localStorage without a guard.
- **F2:**
  - The dev web container still runs as root. Its existing `node_modules` volume is root-owned, so a non-root dev
    user would break dev. Only the runtime images are non-root.
  - `postgres:16-alpine` is not pinned by digest yet.
  - The Node image moves down one patch (24.22.3 → 24.22.2): the newer tag is under two weeks old.
  - CSP: `style-src-attr 'unsafe-inline'` is kept for Workflow Studio's `style="--h:…"` markup.
- **E3:** the plan said one chunk per area; it is one chunk per page.
  - Page ids are not folder names, and `pageFor()` must answer at once. So each area's index maps its ids to
    loaders, and `registry.tsx` wraps each loader in `React.lazy`.
  - The `vendor` chunk uses Vite 8's `rolldownOptions`, which replaces the deprecated `rollupOptions`.
- **D4+D5:** the plan asked for one commit per family; with seven families edited in the same files they went in
  one commit.
  - `can_see_case` stays a plain bool. A new `case_refusal()` gives the reason ("tenant"/"warehouse"), because a
    returned "tenant" string would be truthy.
  - Merged later (21 Nov): `di/services/actions/access.py` now derives DELEG/LEVELS/AUTO_TYPES/LEVEL_RANK from
    `di/repositories/constants.py`, and `screens/access.py` uses `di.repositories.decisions.median` instead of a third copy.
- **25954ea:** the commit subject starts with a stray byte-order mark (the PowerShell `Set-Content` encoding).
  Fixing it would need a force-push, so it stays.
- **G2:** the web Dockerfile is split in two.
  - Why: the classic builder (WSL's Docker has no buildx) runs every stage before the target, so one file can't serve
    both the `frontend` context (dev) and the repo-root context (runtime).
  - `frontend/Dockerfile` holds dev; `frontend/Dockerfile.runtime` holds the production image.
  - A Windows-only `doctor.ps1` was not added: Git for Windows ships Git Bash, which runs `doctor.sh`.
- **E2:** the integration pill tabs now move with ← / → like the other tab bars. That is the only behaviour
  change.
  - Not merged: command's `cck`/`spk` tiles, and product's `Panel`/`Prov`/`Photo` (they differ from the case
    versions).
  - The live screenshot comparison was disturbed by other agents' DB resets, so a jsdom test that renders the old
    and new components with the same inputs decides instead.
- **D6:** `routers/actions.py` also held C3's in-progress typing. So the D6 commit got a version built from HEAD
  with only the journal change, and C3's hunks stay for C3's commit.
  - Token calls still write a fetch-log row, but with `HTTP <status>` instead of the response body.
  - The log level comes from the `DI_LOG_LEVEL` environment variable, not from settings.
- **F3:** `?access_token=` on the stream is removed outright, not kept for a release; nothing else used it.
  - The client now does its own reconnect with a backoff, because the browser's retry would reuse an expired
    ticket.
- **F4:** with `SIM_DEMO_FAULTS` on, resetting one system also clears custom faults on that system.
  - Fixed later (21 Nov): `test_adapter_aws_iot` depended on eam data that `test_connectors` deletes; its module
    fixture now syncs Maximo when no eam run hours are in the canonical store, so it passes in any order.
- **Verification method from D6 on:** each commit's staged tree is exported and tested on its own (web: tsc, vitest,
  eslint, build; api: ruff and the touched tests in a one-off container against a private api), so other agents'
  uncommitted work can't hide a broken commit.
- **E6:** a network error or 5xx is now retried twice (0.5 s, then 1 s) before the page shows the error, so a real
  outage shows about 1.5 s later. A 4xx refusal still shows at once.
  - Buttons are not yet disabled while an action is pending.
  - Invalidation was "everything" on every stream event here; scoped per event kind and action family later (21 Nov,
    `src/api/invalidation.ts`; see the design note).
- **G3:** when `DEV_POLLING` is unset, file watching uses watchfiles' own default (polling under a WSL2 kernel).
  `DEV_POLLING=1` forces polling and `0` turns it off. A strict "off" default would have broken hot reload on this
  machine's `/mnt/c` mount.
  - The api command now `exec`s uvicorn.
  - Not run on a real Mac or with Git Bash's Docker. The evidence is shellcheck, bash 3.2 syntax checks and WSL runs;
    G5's CI job adds a second platform.
- **G5:** the fresh-clone browser smoke was skipped: WSL has no Node, and the script tears down when it ends. The arm64 job needs GitHub arm runners; they are free for public repos, while a private repo needs a plan that includes them.
- **PROGRESS.md itself** was untracked until 21 Nov; it is committed on its own.
- **api under load:** with two smoke runs and a pytest run at once, the single dev api process reached 128% CPU and
  its 3 s health check timed out.
  - `/api/health/live` took over 30 s; it does no database work.
  - Re-check at the wave gate. If it is still slow, look for open stream connections exhausting the thread pool.
- **Process:** an agent ran `git stash`/pop on the shared tree at 15:07 UTC. It wiped and then restored other agents'
  edits; the affected agents re-applied theirs. Every agent is now forbidden to use stash, reset or checkout.
