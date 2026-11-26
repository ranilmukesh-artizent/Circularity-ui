# How we got here

From a single HTML demo to a full-stack app. Branch `feature/fullstack-poc` (PRs target `main`).
The commit hashes are from `git log`. The detailed status of each step is in `docs/backend-steps.md`.

## 1. The demo (before November 2026, merged to `main` through PRs #15–#20)

`fixtures/demo/index.html` was the whole product: a seeded world (mulberry32, 128 cases, 11 accounts, 3 customer tenants), the
decision engine, an action registry with `invoke()`, a journal, an in-browser agent runtime, and every page.

Last UI work:
- `6bbbda3` execution detail and cost trace
- `17b855a` sidebar, Home and Connection Fabric revamp
- `d542c78` stage pages
- `799e06f` CXO demo video and agent test bench

Feedback from people who saw it: too cluttered. A UI redesign with an outside UI expert is planned separately; don't
polish layouts while switching data sources.

## 2. Full-stack POC scaffold

- `0fe771e`: React frontend (`frontend`) that runs the demo's own script as an in-browser engine behind a typed
  facade (`src/api/*.ts`); service skeleton; Docker Compose in WSL.
- `a903e12`: the step plan B1–B18 (`docs/backend-steps.md`).

## 3. Backend, step by step

| Step | Commits | What |
|---|---|---|
| B1 | `803de3d` | Golden data dumped from the demo headless (`fixtures/golden`) |
| B2 | `084716d` | Seed model in source-sim, loaded from the golden files |
| B3, B4 | `9ecabf8`, `26f9872` | SAP S/4HANA and SAP Ariba mocks |
| B5 | `851b952`, `c22e601` | Mock framework; mocks for all 20 sources |
| B6 | `ffdc026` | Simulated clock, scheduled work, webhooks, fault injection |
| B7 | `aae2fd1` | Access policy, sign-in, server-side enforcement |
| B8 | `13b7fbd` | `POST /api/actions/{id}` |
| B9 | `3a381af`, `2997a7f` | Connector framework, canonical store, adapters for all 20 sources |
| B5b | `bea4aa5`, `a1b73d5` | Full vendor mocks for RT-1048's happy path; OTM replaces ShipLane |
| README | `130f438` | Removed demo leftovers; README for the full-stack app |
| Plan | `87bda2a`, `50c628f`, `fe91098` | B16b planned: Ask on Groq's free tier |
| B10 | `1766582` | Decision engine at parity for all 128 cases |
| B11 | `a41e2c1`, `b878e9c` | Cases in the database, stage machine, every read action |
| B12 | `3056e66`, `1c2df4a`, `4901524`, `fbd274a` | Workspace state store; decisions, approvals, case work, collaboration, access |
| B13 | `1f31fe0`, `683918c`, `7b01583` | Execution plan and cost trace; instructions really sent to the mocks and acknowledged from their events; RT-1048 end to end (first milestone) |
| B14 | `9a04223`, `aa3c4a0` | Read APIs for every screen, parity per account |
| B15 | `9370457`, `29f8636` | Live updates (SSE), Workflow Studio actions as worker jobs |
| B16 | `9bf5137` | MCP server with agent scopes and hard rules in code |
| B16b | `8e43e31` | Ask Circularity on Groq |
| B17a | `c4b0483` | Frontend switch (`VITE_BACKEND`), Suspense cache client, session and menu on the backend; conflicts badge decision |

## 4. B17b, B5c and B17c (20 Nov 2026)

Commits: `fbd2122` (B17b, B5c, ShipLane rename), `b47f7f9` (repo cleanup), `266dc87` (agent setup), `22bc1e9`
(plans), then B17c (engine deleted; see `git log`).


- **All page areas on the API.** Seven parallel agents worked on disjoint files: product, case, command and home,
  analytics/audit/orchestration, integration, workflows and MCP, access.
- **Case pages:** rebuilt as React; the engine-built HTML is gone.
- **Ask panel:** opens with Ctrl+J.
- **Admin settings actions:** limit, self-approve, autonomy, run limits, kill switch.
- **I18N** added to the reference lists.
- **Deadlock fix** in `di/core/state.py`.
- **ShipLane renamed** to OTM in the demo itself, with the golden files regenerated.
- **B5c:** AWS IoT Core mock and adapter. It starts not provisioned, and its topic rules are disabled until di connects it.
- **B17c:** the in-browser engine and the `VITE_BACKEND` switch deleted; assets bundled (`src/assets/assets.gen.ts`);
  RT-1048 runs through all ten stages in the browser (`scripts/smoke-rt1048.mjs`). B17 complete.

## 5. Plan 6, the Connection Fabric for real (21 Nov 2026)

Commits: `832b681` (the plan), `810d706` … `93e57e5` (the work), `3932fbe` (decisions and runbook); task → commit list
in `docs/agents/plans/06-fabric-production.md`, one line per task in `docs/agents/plans/PROGRESS.md`. Before it: plan
1b (refactor, `PROGRESS.md`) and the Fabric/Workflow Studio controls on the server (decision log, 21 Nov).

- **User request:** "all the things under the connector menu should be production grade". Ran before plan 2.
- **Connections:** encrypted per-source credentials (`DI_SECRET_KEY`), a connection row per source, a configured
  adapter that really syncs catalogue and hand-made sources against new source-sim mocks, an honest Test connection,
  sync retries and backoff, per-source webhooks with dedupe.
- **Data:** versioned mappings that the sync applies, canonical schema checks with held records, conflicts that stay
  resolved, Manual Import through the pipeline, discovered Source Tables, Event Streams and tiles from real data.
- **Workflows:** block settings, step implementations and an engine (`di/workflow/`); a source's sync is the run of
  its ingest workflow, with canonical data proven identical; triggers, versions, server drafts, a dry test run,
  Reprocess and Apply fix for real, one run at a time with a reaper; the Monitor per workflow and step.
- **How:** 7+ agents in parallel on one tree, migrations reserved in advance; the lessons are in `PROGRESS.md`.
  Parity changes on purpose: decision-log *D-Fabric*. Vendors stay synthetic.

## 6. Plan 7, the folder restructure (22 Nov 2026)

Commits `9854f18`, `62dbfed`. `frontend/`, `backend/`, `source-sim/` replace `apps/*`; inside, layer folders
(routes, schemas, services, repositories, models, core; components, hooks, utils, layout; sim core/routes/vendors).
Behaviour unchanged; five parallel sessions, one per area.

## 7. Plans 2 and 8, the job queue and the decision platform MVP (23–24 Nov 2026)

Commits `a6f93a4` (one migration chain, reserved stubs 0018–0026) … `d0bfad4`; one commit per task, listed in
`docs/agents/plans/PROGRESS.md`; status and known gaps in `docs/backend-steps.md` ("Plan 8 status").

- **User request:** run plan 8 (pushed by a teammate: the MVP plan, the PO's Modeler prototype, the Dover stories),
  plan 2 first, "as fast as possible without breaking", on `feature/fullstack-poc`.
- **Plan 2:** a hardened job queue (priorities, dedupe, dead letters, stale-lock reaper, LISTEN/NOTIFY) and task
  CRUD.
- **Plan 8:** org units, the Modeler (flows, business rules after the gate rules, guardrails, simulation, maker-checker
  with shadow and rollback, the assistant), three template packs, cases opened from data, read-only PLM, group
  reporting and pilot mode, the agent foundation, learning. Ported logic is tested against reference data dumped
  from the PO prototype.
- **How:** up to six sessions in parallel on one tree (path-limited commits, the shared api test lock, reserved
  migrations), the lead running every phase gate together at the end. The end-to-end MVP smoke found four real bugs
  (access to new orgs, opened cases stuck, a "Promise" crash on the agent button, nothing starting the autopilot) and
  the gate found the reset not restoring agents; all fixed with tests. End-user guides per role were written from
  the code (`docs/guides/users/`).

## 8. Plan 8's UI gaps and the trial package (24 Nov 2026)

Commits `3b6a15b` (trial package), `baf90a4`, `bf0c010`, `5bb95a7`, `38647d6`, `31268c5` (gaps B, A, D, C, E), then
the lead's gate and docs. User request: "complete everything and push it".

- **Gaps:** tenant access requested in the app, grants that end and can be revoked and reach an open session at once,
  maker-checker on access and MCP proposals; "Proposals for you" on Home; out-of-office delegation used in approvals;
  org screens (rename, pack export/import with a preview, pilot mode and report) and the Connect dialog's org unit;
  Register agent and the Models panel (fit, propose, approve promotion).
- **Trial package:** `trial/` and `scripts/trial/` (build from HEAD, clean-install check).
- **How:** five agents in parallel on disjoint files, as in plan 8; the lead ran lint, the full suite and the smokes
  on the combined tree.
- Commits: `2a3ee00` (MVP-12.5 gate) … `5c20ddb` (final gate), with `69acbc4` (guides, status, decisions).

## 9. The plan-8 audit, its fixes and the merge (24 Nov 2026)

Commits `95a45ed` (audit fixes, template cases end to end, remaining UI gaps), `8fea98c` (F8 fix), `23c7f81` (Source
drawer org field width), `2e985ff` (audit docs, evidence, research). Audit, findings and merge record:
`docs/agents/audits/2026-11-24-plan-08/README.md`.

- **What:** an audit of plan 8 against what was asked (phases 0–12, the stories), fixes for what it found, then the
  merge with the colleague's gaps work, which had reached origin meanwhile.
- **Fixes:** F1–F11 fixed or kept by a decision-log row. Tool-fleet and device cases opened from data are valued and
  ranked by their template's valuer, as the simulation ranks them; the hazardous-waste exclusion runs before the
  business rules; the person an agent acted for cannot accept that agent's proposal (`own`, migration 0028); every
  editor of a flow draft is a maker; an agent-prepared call never runs a forbidden non-read action (pipeline step 6,
  `services/agents/forbidden.py`); the pilot report checks the tenant of tenant-scoped people.
- **UI:** the Source drawer's org unit, template import in Records, rule suggestions in the Modeler, the Analytics
  pilot report button, "Your agent's proposal" instead of Accept.
- **Merge:** where both sides built the same screen, the colleague's was kept and ours dropped; migrations renumbered
  (his `0027_access_grants`, ours `0028_proposal_requester`; the dev database was downgraded first). An independent
  review found five issues, all fixed before the commit.
- **How:** fix agents in a separate worktree on disjoint files, each with a report in the audit's `work/`; api tests
  in 4 shards on private databases (~7 min, now `scripts/dev/parallel-suite.sh`) as a pre-check, then the serial suite
  as the gate: 4,458 passed + the F8 one fixed in `8fea98c`, 271 source-sim, 312 web, the four browser smokes.
- **Research:** `docs/agents/research/2026-11-agent-foundation.md` (keep the in-house agent runtime; MCP first, then
  OpenAPI/CLI and an A2A card).

## 10. Plan 9, Recover on the agentic core (25–26 Nov 2026, in progress)

Plan: [docs/agents/plans/09-agentic-platform.md](plans/09-agentic-platform.md); status and known gaps in
`docs/backend-steps.md` ("Plan 9 status"); per-task commits in `docs/agents/plans/PROGRESS.md`; the run's merges in
`docs/agents/plans/09-run/RUN-LOG.md`.

- **What:** packs as data (industrial, tool fleet, device, then used cars, telecom network, medical rental, ITAD,
  rental fleet), a gate catalogue, one decider, a stage chain of agents on an LLM router, replay and staged publish,
  Compose with organisation sign-in, SCIM and an adapter registry, and the phase-13 close (fixed-asset retirement, lease
  residual, customer credit, reporting evidence, vendor qualification, model drift, per-agent credentials, OAuth for
  outside MCP clients).
- **How:** a lead with parallel writers in two lanes, one task per commit, tests by the change's impact and a gate per
  phase (the lead runs the shards and the browser smokes); writers' rules in `docs/agents/plans/09-run/WRITER-BRIEF.md`.
- **Still open when this entry was written:** the phase gates 3 to 13, the remaining phase-12 packs, the final smoke
  and proof. Plan 10 (one assistant, a Modeler layout; `docs/agents/plans/10-unified-assistant-ux.md`) is in progress.
- **Legal:** outside-client access and the accounting and reporting texts are reviewed by Kinective's Legal team before a
  customer relies on them.

## 11. Next

- **Agents:** per-agent credentials instead of a person's token plus a header; MCP tools generated from the action
  catalogue, with OAuth for outside clients (the research above).
- **The plans:** CRUD for every resource and gzip, async, OpenTelemetry (plans 3–5).
- **B18:** Playwright suites, `POST /api/admin/reset`, run book, security review.
- **Demo-ready work last** (the user's order).
