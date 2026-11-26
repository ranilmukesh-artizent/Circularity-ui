# AGENTS.md

Entry point for coding agents working in this repo. Read this first; follow the links for detail.

## What this is

Circularity Decision Workbench ("DI", decision intelligence): decides what to do with returned industrial assets
(redeploy, resell, re-lease, recover parts, recycle, exit) and hands the decision to the enterprise systems.
It began as one HTML file (`fixtures/demo/index.html`, "the demo"). It is now a full-stack POC that must stay at
**parity** with that demo: same numbers, same rules, same texts, for all 11 demo accounts and all 128 cases. RT-1048 (Voltara motor,
Customer A) is the hero case. All data is synthetic; no named vendor product is really connected.

## Map

| Path | What |
|---|---|
| `fixtures/demo/index.html` | The demo. Source of truth for parity: every golden file, the web app's stylesheet and its static assets are extracted from it. |
| `frontend/src/pages/modeler/compose/`, `frontend/src/pages/mywork/` | Plan 9: Compose's five steps; My work (cases and steps waiting on you, ageing and lots). |
| `frontend` | React 18 + TS + Vite. `src/api` the facade (pages call only it), `src/pages/<area>` the pages, `src/components` shared UI (incl. `kit/`), `src/hooks`, `src/utils`, `src/layout` the app shell (sidebar, top bar, Ask panel), `src/assets`, `src/styles`. |
| `frontend/src/pages/modeler/`, `frontend/src/pages/agents/` | Plan 8: the Modeler (canvas, inspector, checks, impact, lifecycle, history, assistant) and the Agents page (registry, proposals, runs, tool catalogue). |
| `frontend/src/api/client.ts` | HTTP client: Suspense read cache, actions, sign-in token, live stream. |
| `frontend/src/assets/assets.gen.ts` | The demo's logos, icons and vendor logos (`frontend/scripts/dump-assets.mjs`, committed). |
| `backend` | `di-api` + `di-worker` (FastAPI, SQLAlchemy 2, Alembic, psycopg 3). Package `di`, in layer folders (plan 7; `backend/.importlinter` enforces the direction): |
| `backend/di/routes/` | Every HTTP endpoint, thin: auth, actions, sources, webhooks, stream, ask, health, `screens/<area>`. |
| `backend/di/schemas/` | Pydantic request and response shapes of the routes. |
| `backend/di/services/` | Business logic: `actions/` (every write and read action, `POST /api/actions/{id}` through `pipeline.invoke`), `screens/<area>` (what each page shows; each docstring maps the facade exports), `engine/`, `execution/`, `instructions/`, `cases/`, `canonical/`, `ask/`, `stream`, `auth`, `sources`, `journal`. |
| `backend/di/services/modeler/` | Plan 8, pure: template packs (`packs/`), flow graph, compile, scope, apply (business rules after the gate rules), validate, guardrails, simulate, parse, propose, suggest, telemetry facts; `valuers/` (tool fleet, device, routes adapter). Tested against `fixtures/golden/po/`. |
| `backend/di/services/modeler/` (plan 9) | Also: `packs/*.json` (nine packs: industrial, tool fleet, device, used cars, telecom network, medical rental, ITAD, rental fleet, carbon), `compose.py` (Compose's five steps), `export_dmn.py`/`export_bpmn.py` (export), `vendor_qualification.py` (downstream vendors with certificate dates), `gate_checks/`, `replay_samples/`, `rollout.py`. |
| `backend/di/services/questions/` | Plan 9: worked analytics questions of each pack, in code (`used_cars`, `telecom_network`, `medical_rental`). |
| `backend/di/services/execution/` (plan 9) | Close modules: `asset.py` (fixed-asset retire/transfer), `residual.py` (lease residual), `settlement.py` (customer credit against the ERP), `reporting.py` (close only with reporting evidence). |
| `backend/di/services/agent_credentials.py`, `oauth.py`, `oidc.py`, `scim.py`, `group_map.py`; `backend/di/routes/oauth.py`, `scim.py` | Plan 9 identity: per-agent client credentials, OAuth for outside MCP clients (S256 only, audience-bound tokens), organisation sign-in, SCIM, directory groups to roles. |
| `backend/di/services/llm/router.py` | Plan 9: the model chain (budgets, cooldowns, fallback); callers take their deterministic path when it answers nothing. |
| `backend/di/services/agents/` | Plan 8: autonomy and run limits, tool catalogue, registry, proposals that hold for a person, runtime and playbooks (`case_autopilot`). |
| `backend/di/services/agents/forbidden.py` | `FORBIDDEN_ACTIONS`, the one list of actions no agent may run: checked by the action pipeline (step 6) for every agent-prepared call, by the tool catalogue (`agent_allowed`), and at import against the MCP, playbook and Ask tool tables. |
| `backend/di/repositories/` | Read queries and read models, incl. the live Connection Fabric (`fabric.py`). |
| `backend/di/models/` | SQLAlchemy tables, one module per domain (mirrors the migrations). |
| `backend/di/core/` | Foundations: config, db, auth, policy, errors, clock, dates, logs, golden, state, jobs. |
| `backend/di/connectors/` | Adapters to the source systems, encrypted credentials, connections, configured adapter, mappings, sync, webhooks, conflicts. Plan 9: `registry.py` (adapter registry with test and production environments), `mapping_suggest.py` and `mapping.py` (suggestions, the five choices), `openapi_import.py`, `discover.py`. |
| `backend/di/workflow/` | Workflow engine: `blocks` (settings), `engine`, `steps/`, `triggers`, `versions`, `binding` (a sync is its source's ingest workflow), `live`. |
| `backend/di/mcp/`, `di/services/ask/` | MCP server at `/mcp`; Ask Circularity (`POST /api/ask`, Groq). |
| `source-sim` | Package `sim`: mocks of the enterprise systems (SAP S/4HANA, Ariba, Sterling, OTM, AWS IoT Core …). `sim/core` (clock, db, events, faults, scheduler, webhooks, registry), `sim/routes` (admin), `sim/vendors/<system>/` one folder per mock (`routes.py`, `models.py`, `seed.py`), `sim/generic` (spec-built mocks), `sim/seed`. |
| `fixtures/golden/` | JSON dumped from the demo; the parity tests compare against it. Never hand-edit. |
| `docs/backend-steps.md` | The build plan B1–B18 with a status section per step. Read the step you work on. |
| `docs/agents/` | Dos and don'ts, learnings, decisions, history, testing, scripts. |
| `docs/agents/runbook-fabric.md` | Operating the Connection Fabric: failing source, credentials and key, webhooks, stuck runs, held records. |
| `docs/agents/audits/` | Audits with their evidence (logs, junit, screenshots) and the agents' reports, one folder per audit. Latest: `2026-11-24-plan-08/` (findings F1–F11, UI gaps U1–U9, the merge record). |
| `docs/agents/research/` | Research notes behind decisions to come (e.g. `2026-11-agent-foundation.md`: agent runtime and interop). |
| `scripts/dev/` | Dev scripts (tests with the lock, reset, restart, unstick, status). Plan 9: `gate-p9.sh`, `story-matrix.sh`, `wt-check.sh`, `lead-verify.sh`. |
| `frontend/scripts/smoke-p9-*.mjs` | Plan 9 browser smokes, one per phase that has a demo (1 to 5, 8 to 11). |
| `trial/`, `scripts/trial/` | The trial package for customers (Compose on prebuilt images, start/stop/reset scripts, `START-HERE.md`) and its build and clean-install check. |
| `fixtures/demo/assets/products/` | Product photos, beside the demo; `frontend/scripts/extract-styles.mjs` copies them into the web app. |
| `docs/reference/` | Source documents (agent-first product spec, user journey deck, IFS process fit). Read-only background. |

## Run

Everything runs in Docker Compose; the host needs only Git and Docker (Docker Desktop on Windows/macOS, or Docker
Engine with Compose v2 on Linux). Services: `postgres` (5432), `source-sim` (8100, SFTP 2222), `api` (8000), `worker`,
`web` (5173).

```sh
bash scripts/doctor.sh                             # optional: Docker, Compose v2, free ports, memory, line endings
docker compose up -d --build                       # the app on :5173 reads di-api
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build   # opt-in runtime images
```

- A second dev server on the host (hot reload without the container; needs Node 24):
  `cd frontend; npx vite --port 5174 --strictPort` (proxies `/api` and `/mcp` to localhost:8000).
- Sign in with any ID and any password: `admin`, `exec`, `ops`/`planner.a`, `planner.b`, `planner.c`, `approver`,
  `engineer`, `finance`, `developer`, `warehouse1`, `warehouse2` (emails `<id>@northfield.example`).
- `.env` (git-ignored) holds `GROQ_API_KEY`. Without it Ask uses the demo's rule-based answers.
- Host ports from env or `.env` (containers keep theirs): `WEB_PORT` 5173, `API_PORT` 8000, `SIM_PORT` 8100,
  `SFTP_PORT` 2222, `POSTGRES_PORT` 5432 (`.env.example`). `DEV_POLLING=1` makes uvicorn --reload and Vite poll for
  file changes (bind mounts without change events), `0` never; unset, they poll only under a WSL2 kernel.

Shell scripts are bash (3.2 or later); run them from the repo root in a Linux/macOS terminal, WSL or Git Bash. The host
needs only `docker` and `curl`: the test lock, timeouts, psql, python and node run inside the containers. With Docker
Desktop on Windows, run them from Git Bash (see CLAUDE.md for its pitfalls). If Docker runs inside WSL instead, run
each through a script file: `wsl -d <distro> -u root -- bash /mnt/c/<path-to>/Circularity-ui/scripts/dev/<script>.sh`

## Test

The Node smoke scripts need host Node 24 and Chrome; the URL argument defaults to `WEB_PORT`.

| What | Command | Time |
|---|---|---|
| Selected api tests | `bash scripts/dev/api-test.sh tests/test_x.py` | seconds to minutes |
| Full api + source-sim (the gate) | `bash scripts/dev/full-suite.sh`, then `bash scripts/dev/reset.sh` | ~32 min + 1 min |
| api pre-check in 4 shards on private databases (not the gate; 38 files stay serial-only) | `bash scripts/dev/parallel-suite.sh` (`--list` shows the shards) | ~7-11 min |
| Web typecheck + unit | `bash scripts/dev/web-check.sh` | ~1 min |
| Browser smoke, 11 accounts | `node frontend/scripts/smoke-pages.mjs http://localhost:5173` | ~5 min |
| RT-1048 end to end (changes state: reset before and after) | `node frontend/scripts/smoke-rt1048.mjs http://localhost:5173` | ~3 min |
| Modeler and MVP end to end (change state: reset before and after) | `node frontend/scripts/smoke-modeler.mjs …`, `node frontend/scripts/smoke-mvp.mjs …` | a few min each |
| Fresh clone of HEAD, own project `circfresh` and ports (main stack untouched; `--prod` for the runtime images) | `bash scripts/dev/fresh-clone.sh [--prod]` | ~5–15 min |
| Trial package of HEAD, then its clean install (project `circtrialcheck`, port 15190) | `bash scripts/trial/build.sh`, then `bash scripts/trial/check.sh` | ~10 min + ~5 min |

- **One api pytest at a time.** All suites share one database and reset it. The dev scripts take a flock on
  `/tmp/di-pytest.lock` inside the api container (`scripts/dev/lib.sh api_lock`). Never call `docker compose exec api pytest` directly while anyone else may be testing.
  The one exception is a run on a private database (`parallel-suite.sh`, or `docker compose run --rm --no-deps -e
  DI_DATABASE_URL=…/<own db> api …`); it leaves the main database and the lock alone.
- The api suite forces the pinned clock and no outbound instructions (`backend/tests/conftest.py`).
- Details, counts, flaky tests: [docs/agents/testing.md](docs/agents/testing.md).

## Golden rules

1. Parity first. A changed number or text versus the demo is a bug unless a decision in
   [docs/agents/decision-log.md](docs/agents/decision-log.md) says otherwise.
2. Never hand-edit `fixtures/golden/`. Change the demo or the dump script, regenerate, and prove the diff is only
   what you intended ([testing.md](docs/agents/testing.md#regenerating-golden-files)).
3. Never commit `.env`, `.vscode/`, keys or tokens. Scan the staged diff for key-shaped strings (`gsk_` followed by 20+ letters/digits) before every commit.
4. Never print, log or paste `GROQ_API_KEY`.
5. Commit and push only when the user asks; one step per commit, on `feature/fullstack-poc`; report after each.
6. Pages call only `src/api/*.ts`; the facade calls only di-api (`client.ts`).
7. Static assets come from `src/assets/assets.gen.ts`; regenerate it with `node frontend/scripts/dump-assets.mjs`, never hand-edit.
8. Every write goes through the action pipeline (`POST /api/actions/{id}`, `invoke()` in the web app).
9. Enforce access on the server (tenant boundary, warehouse lock, permissions). The frontend checks are only for display.
10. Agents (MCP, Ask, playbooks) only read or hold for a person. They never approve, override, decline or change
    access. The pipeline refuses every non-read action in `services/agents/forbidden.py` when an agent prepared the
    call, whatever the headers say (audit F4); add a new action that only a person may take to that list.
11. On the main database, run api tests only through `scripts/dev/api-test.sh` or `full-suite.sh` (the lock); never
    two runs there at once. `scripts/dev/parallel-suite.sh` runs shards side by side on private databases as a
    pre-check; the serial `full-suite.sh` stays the gate.
12. Restart containers after changing code they don't reload (worker always; source-sim; golden files).
13. Shell from Windows: write a `.sh` file with LF endings and run it with bash (Git Bash with Docker Desktop;
    `wsl ... bash` where Docker runs inside WSL). No inline `bash -lc '...'` with nested quotes.
14. Don't claim a named vendor is really connected. Every mock is synthetic.
15. Verify before you report: run the tests yourself and quote the result. Don't relay a subagent's claim unchecked.

Full list: [docs/agents/dos-and-donts.md](docs/agents/dos-and-donts.md).

## Skills and agent setup

- Skills live in `.claude/skills/` (9 public skills: superpowers' TDD, systematic debugging,
  verification-before-completion, writing-plans, code review, finishing a branch; anthropics' webapp-testing and
  mcp-builder). `.claude/skills/SOURCES.md` lists their origin.
- How they are adapted to this repo: see the table in [CLAUDE.md](CLAUDE.md#skills-in-this-repo). In short, tests
  run through `scripts/dev/`, plans go to `docs/agents/plans/`, browser tests use Node Playwright with Chrome.
- `.claude/agents/` (8 subagents), `.claude/commands/` (`/feature-dev`, `/commit`, `/smart-debug`) and `.mcp.json`
  (Playwright MCP): sources and licences in `.claude/SETUP_SOURCES.md`.
- Work after B17 is planned in `docs/agents/plans/` and run by the loop in `docs/agents/plans/loop.md`.

## Where to read more

- [docs/guides/users/README.md](docs/guides/users/README.md): end-user guides per role, the case journey and approvals.
- [docs/backend-steps.md](docs/backend-steps.md): the plan and the status of every step (B1–B18).
- [docs/agents/history.md](docs/agents/history.md): how the repo got here, with commits.
- [docs/agents/decision-log.md](docs/agents/decision-log.md): decisions and why.
- [docs/agents/learnings.md](docs/agents/learnings.md): problems already hit, with root cause and fix.
- [docs/agents/testing.md](docs/agents/testing.md): suites, parity, golden files, smoke scripts.
- [docs/agents/scripts.md](docs/agents/scripts.md): every script in the repo.
- `backend/di/services/screens/<area>.py` docstrings: what each screen endpoint serves and how the facade maps to it.
- `frontend/src/api/client.ts` docstring: how the synchronous facade works over HTTP.

## Current state (24 Nov 2026)

B1–B17 done: the web app reads only di-api; the in-browser engine is gone. Plan 1b (refactor) and plan 6 done: the
Connection Fabric runs for real (encrypted credentials, configured connections, mappings that run, canonical checks,
a workflow engine on triggers) while every vendor system stays synthetic; see the plan-6 status in
`docs/backend-steps.md` and [docs/agents/runbook-fabric.md](docs/agents/runbook-fabric.md). Plan 7 done: the folders
are `frontend/`, `backend/` and `source-sim/`, each in layer folders (routes, schemas, services, repositories,
models, core; components, hooks, utils, layout), with no change in behaviour
([plan 7](docs/agents/plans/07-restructure.md)). Plan 2 done (job queue: priorities, dedupe, dead letters, reaper,
LISTEN/NOTIFY wake-up, task CRUD at `/api/v1/tasks`). Plan 8 done, the decision platform MVP
([plan 8](docs/agents/plans/08-mvp-decision-platform.md), status in `docs/backend-steps.md`): org units, the Modeler
(flows, business rules after the gate rules, guardrails, simulation, maker-checker lifecycle with shadow and
rollback, the plain-language assistant), template packs (industrial, tool fleet, device recommerce), cases opened
from data, read-only PLM (Windchill), group reporting and pilot mode, the agent foundation (registry, autonomy,
proposals that hold for a person, runtime and case autopilot, per-agent MCP tools, MCP client sources), learning
(calibration, model candidates, rule suggestions); the demo's 128 cases and RT-1048 are unchanged while the default
flows have no rules. End-user guides: [docs/guides/users/README.md](docs/guides/users/README.md).
Plan 8's UI gaps closed (24 Nov: request and revoke tenant access with grants that end, maker-checker on access,
proposals on Home, out-of-office delegation in approvals, org screens and pilot mode, Register agent and the Models
panel; then the Source drawer's org unit, template import in Records, rule suggestions in the Modeler and the
Analytics pilot report; status in `docs/backend-steps.md`). The trial package for customers: `trial/` (what they
unpack, read `trial/START-HERE.md`), built by `scripts/trial/build.sh`, checked by `scripts/trial/check.sh`.
The plan-8 audit ([docs/agents/audits/2026-11-24-plan-08/](docs/agents/audits/2026-11-24-plan-08/README.md)):
findings F1–F11 fixed or kept by a decision in the decision log (`95a45ed`, `8fea98c`); tool-fleet and device cases
opened from data are valued and ranked end to end; the gate after the merge passed (4,459 api tests, 271 source-sim,
312 web, the four browser smokes, lint).
Next: plans 3–5 (CRUD for every resource and gzip, async, OpenTelemetry), then B18; demo-ready work last.

Plan 9 (Recover, [plan](docs/agents/plans/09-agentic-platform.md)) is being built from 25 Nov 2026 by a lead with
parallel writers; progress, blocked tasks and the report are in `docs/agents/plans/09-run/`, status and known gaps in
`docs/backend-steps.md` ("Plan 9 status"). Delivered so far (26 Nov 2026, ticks in `docs/agents/plans/PROGRESS.md`):
packs as data (`modeler/packs/*.json`) with a gate catalogue, customer overlay, one decider and My work; the agent chain
on a model router; tool fleet returns, service desk and contract refresh; device recommerce; replay and staged publish;
Compose end to end with organisation sign-in, SCIM and an adapter registry; four more industries as packs (used cars,
telecom network, medical rental, ITAD) with rental fleet landing; and the phase-13 close: fixed-asset retirement,
lease residual, customer credit against the ERP, close only with reporting evidence, downstream vendor qualification,
model drift, per-agent credentials and OAuth for outside MCP clients. Still open: phase gates 3 to 13, the remaining
phase-12 packs, the final smoke and proof (13.11, 13.12, 13.14). Plan 10
([plan](docs/agents/plans/10-unified-assistant-ux.md)) is in progress: one assistant dock and a Modeler layout with a
hierarchy, frontend only. Kinective's Legal team reviews outside-client access, the accounting and reporting texts before
anything is relied on at a customer.

Known server gaps are listed under B17b, plan 6 and plan 8 in `docs/backend-steps.md`.
