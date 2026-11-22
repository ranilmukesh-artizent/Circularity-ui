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

## 6. Next

- **The plans:** queue and task CRUD, CRUD for every resource and gzip, async, OpenTelemetry (plans 2–5).
- **B18:** Playwright suites, `POST /api/admin/reset`, run book, security review.
- **Server gaps** (from B17b): the MCP agent test bench and the pipeline's agent gate (autonomy levels, run limits,
  the kill switch outside MCP). Plan 6's known gaps are in its status block in `docs/backend-steps.md`.
