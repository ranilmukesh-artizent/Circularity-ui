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
| `apps/web` | React 18 + TS + Vite. Pages in `src/pages/<area>`, facade in `src/api/*.ts` (pages call only the facade). |
| `apps/web/src/api/client.ts` | HTTP client: Suspense read cache, actions, sign-in token, live stream. |
| `apps/web/src/ui/assets.gen.ts` | The demo's logos, icons and vendor logos (`scripts/dump-assets.mjs`, committed). |
| `apps/api` | `di-api` + `di-worker` (FastAPI, SQLAlchemy 2, Alembic, psycopg 3). Package `di`. |
| `apps/api/di/actions/` | Every write and read action (`POST /api/actions/{id}`), through `pipeline.invoke`. |
| `apps/api/di/screens/` | Read endpoints per page area (`/api/screens/<area>`); each docstring maps the facade exports. |
| `apps/api/di/connectors/` | Adapters to the 21 source systems, sync, webhooks, conflicts. |
| `apps/api/di/mcp/`, `di/ask/` | MCP server at `/mcp`; Ask Circularity (`POST /api/ask`, Groq). |
| `apps/source-sim` | Package `sim`: mocks of the enterprise systems (SAP S/4HANA, Ariba, Sterling, OTM, AWS IoT Core …), simulated clock, outbox, signed CloudEvents, faults. |
| `fixtures/golden/` | JSON dumped from the demo; the parity tests compare against it. Never hand-edit. |
| `docs/backend-steps.md` | The build plan B1–B18 with a status section per step. Read the step you work on. |
| `docs/agents/` | Dos and don'ts, learnings, decisions, history, testing, scripts. |
| `scripts/dev/` | Dev scripts (tests with the lock, reset, restart, unstick, status). |
| `fixtures/demo/assets/products/` | Product photos, beside the demo; `apps/web/scripts/extract-styles.mjs` copies them into the web app. |
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
  `cd apps/web; npx vite --port 5174 --strictPort` (proxies `/api` and `/mcp` to localhost:8000).
- Sign in with any ID and any password: `admin`, `exec`, `ops`/`planner.a`, `planner.b`, `planner.c`, `approver`,
  `engineer`, `finance`, `developer`, `warehouse1`, `warehouse2` (emails `<id>@northfield.example`).
- `.env` (git-ignored) holds `GROQ_API_KEY`. Without it Ask uses the demo's rule-based answers.

Shell scripts are bash; run them from the repo root in a Linux/macOS terminal, WSL or Git Bash. If Docker runs inside
WSL (as on the lead's Windows machine, see CLAUDE.md), run each through a script file:
`wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/Users/<you>/Documents/Circularity-ui/scripts/dev/<script>.sh`

## Test

The `scripts/dev` test scripts still use host `flock` and GNU `timeout` (Linux or WSL; G3 makes them portable). The
Node smoke scripts need host Node 24 and Chrome.

| What | Command | Time |
|---|---|---|
| Selected api tests | `bash scripts/dev/api-test.sh tests/test_x.py` | seconds to minutes |
| Full api + source-sim | `bash scripts/dev/full-suite.sh`, then `bash scripts/dev/reset.sh` | ~25 min + 1 min |
| Web typecheck + unit | `bash scripts/dev/web-check.sh` | ~1 min |
| Browser smoke, 11 accounts | `node apps/web/scripts/smoke-pages.mjs http://localhost:5173` | ~5 min |
| RT-1048 end to end (changes state: reset before and after) | `node apps/web/scripts/smoke-rt1048.mjs http://localhost:5173` | ~3 min |

- **One api pytest at a time.** All suites share one database and reset it. The dev scripts take a flock
  (`/tmp/di-pytest.lock`). Never call `docker compose exec api pytest` directly while anyone else may be testing.
- The api suite forces the pinned clock and no outbound instructions (`apps/api/tests/conftest.py`).
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
7. Static assets come from `src/ui/assets.gen.ts`; regenerate it with `node scripts/dump-assets.mjs`, never hand-edit.
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
- `apps/api/di/screens/<area>.py` docstrings: what each screen endpoint serves and how the facade maps to it.
- `apps/web/src/api/client.ts` docstring: how the synchronous facade works over HTTP.

## Current state (20 Nov 2026)

B1–B17 done: the web app reads only di-api; the in-browser engine is gone. Next: the plans in
`docs/agents/plans/` (the loop, queue and task CRUD, CRUD for every resource and gzip, async, OpenTelemetry), then B18
(Playwright suites, demo reset endpoint, run book, security review).

Known server gaps are listed under B17b in `docs/backend-steps.md`.
