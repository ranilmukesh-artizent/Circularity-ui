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
| `frontend` | React 18 + TS + Vite. `src/api` the facade (pages call only it), `src/pages/<area>` the pages, `src/components` shared UI (incl. `kit/`), `src/hooks`, `src/utils`, `src/layout` the app shell (sidebar, top bar, Ask panel), `src/assets`, `src/styles`. |
| `frontend/src/api/client.ts` | HTTP client: Suspense read cache, actions, sign-in token, live stream. |
| `frontend/src/assets/assets.gen.ts` | The demo's logos, icons and vendor logos (`frontend/scripts/dump-assets.mjs`, committed). |
| `backend` | `di-api` + `di-worker` (FastAPI, SQLAlchemy 2, Alembic, psycopg 3). Package `di`, in layer folders (plan 7; `backend/.importlinter` enforces the direction): |
| `backend/di/routes/` | Every HTTP endpoint, thin: auth, actions, sources, webhooks, stream, ask, health, `screens/<area>`. |
| `backend/di/schemas/` | Pydantic request and response shapes of the routes. |
| `backend/di/services/` | Business logic: `actions/` (every write and read action, `POST /api/actions/{id}` through `pipeline.invoke`), `screens/<area>` (what each page shows; each docstring maps the facade exports), `engine/`, `execution/`, `instructions/`, `cases/`, `canonical/`, `ask/`, `stream`, `auth`, `sources`, `journal`. |
| `backend/di/repositories/` | Read queries and read models, incl. the live Connection Fabric (`fabric.py`). |
| `backend/di/models/` | SQLAlchemy tables, one module per domain (mirrors the migrations). |
| `backend/di/core/` | Foundations: config, db, auth, policy, errors, clock, dates, logs, golden, state, jobs. |
| `backend/di/connectors/` | Adapters to the 21 source systems, encrypted credentials, connections, configured adapter, mappings, sync, webhooks, conflicts. |
| `backend/di/workflow/` | Workflow engine: `blocks` (settings), `engine`, `steps/`, `triggers`, `versions`, `binding` (a sync is its source's ingest workflow), `live`. |
| `backend/di/mcp/`, `di/services/ask/` | MCP server at `/mcp`; Ask Circularity (`POST /api/ask`, Groq). |
| `source-sim` | Package `sim`: mocks of the enterprise systems (SAP S/4HANA, Ariba, Sterling, OTM, AWS IoT Core …). `sim/core` (clock, db, events, faults, scheduler, webhooks, registry), `sim/routes` (admin), `sim/vendors/<system>/` one folder per mock (`routes.py`, `models.py`, `seed.py`), `sim/generic` (spec-built mocks), `sim/seed`. |
| `fixtures/golden/` | JSON dumped from the demo; the parity tests compare against it. Never hand-edit. |
| `docs/backend-steps.md` | The build plan B1–B18 with a status section per step. Read the step you work on. |
| `docs/agents/` | Dos and don'ts, learnings, decisions, history, testing, scripts. |
| `docs/agents/runbook-fabric.md` | Operating the Connection Fabric: failing source, credentials and key, webhooks, stuck runs, held records. |
| `scripts/dev/` | Dev scripts (tests with the lock, reset, restart, unstick, status). |
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
needs only `docker` and `curl`: the test lock, timeouts, psql, python and node run inside the containers. If Docker
runs inside WSL (as on the lead's Windows machine, see CLAUDE.md), run each through a script file:
`wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/Users/<you>/Documents/Circularity-ui/scripts/dev/<script>.sh`

## Test

The Node smoke scripts need host Node 24 and Chrome; the URL argument defaults to `WEB_PORT`.

| What | Command | Time |
|---|---|---|
| Selected api tests | `bash scripts/dev/api-test.sh tests/test_x.py` | seconds to minutes |
| Full api + source-sim | `bash scripts/dev/full-suite.sh`, then `bash scripts/dev/reset.sh` | ~25 min + 1 min |
| Web typecheck + unit | `bash scripts/dev/web-check.sh` | ~1 min |
| Browser smoke, 11 accounts | `node frontend/scripts/smoke-pages.mjs http://localhost:5173` | ~5 min |
| RT-1048 end to end (changes state: reset before and after) | `node frontend/scripts/smoke-rt1048.mjs http://localhost:5173` | ~3 min |
| Fresh clone of HEAD, own project `circfresh` and ports (main stack untouched; `--prod` for the runtime images) | `bash scripts/dev/fresh-clone.sh [--prod]` | ~5–15 min |

- **One api pytest at a time.** All suites share one database and reset it. The dev scripts take a flock on
  `/tmp/di-pytest.lock` inside the api container (`scripts/dev/lib.sh api_lock`). Never call `docker compose exec api pytest` directly while anyone else may be testing.
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
10. Agents (MCP, Ask) only read or hold for a person. They never approve, override, decline or change access.
11. Run api tests through `scripts/dev/api-test.sh` or `full-suite.sh` (the lock), never in parallel.
12. Restart containers after changing code they don't reload (worker always; source-sim; golden files).
13. Shell from Windows: write a `.sh` file with LF endings and run it via `wsl ... bash`. No inline `bash -lc '...'`
    with nested quotes.
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

- [docs/backend-steps.md](docs/backend-steps.md): the plan and the status of every step (B1–B18).
- [docs/agents/history.md](docs/agents/history.md): how the repo got here, with commits.
- [docs/agents/decision-log.md](docs/agents/decision-log.md): decisions and why.
- [docs/agents/learnings.md](docs/agents/learnings.md): problems already hit, with root cause and fix.
- [docs/agents/testing.md](docs/agents/testing.md): suites, parity, golden files, smoke scripts.
- [docs/agents/scripts.md](docs/agents/scripts.md): every script in the repo.
- `backend/di/services/screens/<area>.py` docstrings: what each screen endpoint serves and how the facade maps to it.
- `frontend/src/api/client.ts` docstring: how the synchronous facade works over HTTP.

## Current state (22 Nov 2026)

B1–B17 done: the web app reads only di-api; the in-browser engine is gone. Plan 1b (refactor) and plan 6 done: the
Connection Fabric runs for real (encrypted credentials, configured connections, mappings that run, canonical checks,
a workflow engine on triggers) while every vendor system stays synthetic; see the plan-6 status in
`docs/backend-steps.md` and [docs/agents/runbook-fabric.md](docs/agents/runbook-fabric.md). Plan 7 done: the folders
are `frontend/`, `backend/` and `source-sim/`, each in layer folders (routes, schemas, services, repositories,
models, core; components, hooks, utils, layout), with no change in behaviour
([plan 7](docs/agents/plans/07-restructure.md)). Next: the trial package for customers, then plans 2–5 in
`docs/agents/plans/` (queue and task CRUD, CRUD for every resource and gzip, async, OpenTelemetry), then B18
(Playwright suites, demo reset endpoint, run book, security review).

Known server gaps are listed under B17b and plan 6 in `docs/backend-steps.md`.
