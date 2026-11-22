# Circularity Decision Workbench (full-stack POC)

Circularity decides what happens to every returned asset — redeploy it, resell it, re-lease it, harvest parts, recover material or exit it responsibly — with evidence from the enterprise systems a company already runs, a forecast, a human approval, and a check of what it actually returned. It is **Recover**, one app of the Artizent Decision Intelligence Framework.

This repository is the proof of concept that turns the earlier single-file demo into a working application: a React frontend, a Python backend with a Postgres database, and **mocks of the 20 enterprise systems** the decisions draw on (SAP S/4HANA, SAP Ariba, Salesforce, IBM Maximo, IBM Sterling OMS, ServiceNow and others), all running locally in Docker.

> All data is synthetic (the demo company *Northfield Industrial Leasing*, three customer tenants, eight sites, 128 returned assets). No real system is connected: the vendor systems are mocks that copy each vendor's API style. Nobody should state or imply that a named vendor product is connected.

### Who can do what

Sign in with the ID in the first row and any password. The server enforces every cell (role policy in
`fixtures/golden/policy.json`, `backend/di/core/policy.py`); the app only hides what a role cannot use.

| | Admin | Approver | Planner | Engineer | Finance | Developer | Executive | Warehouse Mgr |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Sign-in ID** | `admin` | `approver` | `planner.a` / `.b` / `.c` | `engineer` | `finance` | `developer` | `exec` | `warehouse1` / `2` |
| **Scope** | all tenants | all tenants | own tenant only | all tenants | all tenants | all tenants | all tenants | own warehouse only |
| **Decisions and cases** | | | | | | | | |
| Open the Decision Workbench (cases, assets) | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ (read) | ✓ |
| Request evidence or an inspection | ✓ | ✓ | ✓ | ✓ | – | – | – | ✓ |
| Record an inspection or test result | ✓ | – | – | ✓ | – | – | – | – |
| Save and run what-if scenarios | ✓ | ✓ | ✓ | – | – | – | – | – |
| Re-evaluate a case | ✓ | ✓ | ✓ | – | – | – | – | – |
| Submit a decision for approval | ✓ | – | ✓ | – | – | – | – | – |
| Approve, override or decline a decision | ✓ | ✓ | – | – | – | – | – | – |
| Confirm the outcome (actual vs predicted) | ✓ | – | – | – | ✓ | – | – | – |
| Advance or replay the simulated execution | ✓ | ✓ | ✓ | ✓ | – | – | – | – |
| **Connection Fabric** ([guide](docs/guides/connection-fabric.md)) | | | | | | | | |
| See it | all tabs | Event Streams, Conflict Queue | – | Overview, Source Map, Tables, Models, Monitor | Overview, Source Map, Monitor | all tabs | – | – |
| Connect, configure, sync, pause, disconnect, delete sources; edit tables; import; resolve conflicts | ✓ | – | – | – | – | ✓ | – | – |
| Build, publish and run workflows (Workflow Studio) | ✓ | – | – | – | – | ✓ | – | – |
| Comment on a source | ✓ | – | – | – | ✓ | ✓ | – | – |
| **Agents and access** | | | | | | | | |
| MCP & Tools pages | ✓ | ✓ | – | ✓ | – | ✓ | – | – |
| Run agent tools in the playground | ✓ | – | – | – | – | ✓ | – | – |
| Propose an MCP server | ✓ | – | – | – | – | ✓ | – | – |
| Approve MCP proposals and tenant-access requests | ✓ | ✓ | – | – | – | – | – | – |
| Request access to another tenant | ✓ | – | ✓ | – | – | – | – | – |
| Access & Governance (accounts, identity, delegations, autonomy, limits) | ✓ | – | – | – | – | – | – | – |
| **Everyone** | | | | | | | | |
| Home, Command Center, Tasks, Alerts, Audit, Data Checks, Reports, Settings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Analytics | ✓ | ✓ | ✓ | engineering, sustainability | ✓ | – | ✓ | – |
| Notify an owner | ✓ | – | – | – | – | – | ✓ | – |
| Acknowledge notifications | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ |

Agents (Ask Circularity, the MCP server, the workflow builder) act as the signed-in person and only read or draft;
they never approve, override, decline or change access.

---

## Start it

### Requirements

- **Git**.
- **Docker** with **Compose v2** (`docker compose`, 2.24 or later for the runtime images), at least 4 GB of memory for
  Docker and about 10 GB of free disk:
  - Windows or macOS (Intel or Apple Silicon): Docker Desktop. On Windows, Docker Engine inside WSL also works (below).
  - Linux: Docker Engine with the Compose plugin.
- No Node.js or Python on the host to run the app. Node.js 24 (`.nvmrc`) only for the frontend outside Docker and the
  browser smoke scripts.

What is proved: CI (`.github/workflows/ci.yml`, GitHub's Linux amd64 runners) brings up postgres, source-sim and the
api in Docker and runs their test suites, plus the web tests and build; the whole stack is developed on Windows with
Docker inside WSL. macOS and Docker Desktop are expected to work but are not tested. For arm64 (Apple Silicon, ARM
Linux), CI has an `arm64` job on GitHub's `ubuntu-24.04-arm` runner that builds and starts the whole stack, checks its
health and reads a screen after signing in (no test suites); arm64 counts as proved only once that job has run green
on GitHub. `scripts/dev/fresh-clone.sh` checks that the committed HEAD comes up from a fresh clone on your machine.

### Quick start (any OS)

```sh
git clone <repo-url> Circularity-ui
cd Circularity-ui
bash scripts/doctor.sh          # optional check: Docker, Compose v2, free ports, memory, disk, line endings
docker compose up -d --build    # first build takes a few minutes
```

On Windows, run these in Git Bash (or PowerShell, without the `bash scripts/doctor.sh` line). Clone with LF line
endings for the scripts and Python files the containers run: `git config --global core.autocrlf input` before
cloning (the doctor warns if a `.sh` or `.py` file has CRLF).

Then open http://localhost:5173 and sign in (IDs below). `docker compose ps` shows each service's health; the first
start seeds the mocks and the worker then syncs every source, which takes a few minutes.

| Open | What it is |
|---|---|
| http://localhost:5173 | The app (React) |
| http://localhost:8000/docs | `di-api`: the backend API (OpenAPI) |
| http://localhost:8100/docs | `source-sim`: the 20 mocked enterprise systems |
| localhost:5432 | Postgres (user and password `circ`): databases `di` and `sources` |

Every page reads `di-api` and updates live from its event stream; Ask Circularity (Ctrl+J) answers through `POST /api/ask`. The status page shows the API, the `di` database migration and source-sim; all three should read **OK**.

Optional: copy `.env.example` to `.env` to set `GROQ_API_KEY` (Ask Circularity on a language model; without it Ask
uses the demo's prepared answers) or change the defaults (database user and password, the host ports, the bind
address, file watching, signing secrets). The stack runs without a `.env`.

- Host ports, when one is taken on your machine: `WEB_PORT` (5173), `API_PORT` (8000), `SIM_PORT` (8100),
  `SFTP_PORT` (2222), `POSTGRES_PORT` (5432), in `.env` or the environment, e.g.
  `WEB_PORT=15173 API_PORT=18000 docker compose up -d`. The containers keep their own ports.
- `DEV_POLLING=1`: hot reload polls for file changes, for bind mounts that deliver no change events (a Windows drive
  without WSL 2's own file system, some VMs). `DEV_POLLING=0` never polls; unset, the api, source-sim and web poll
  only under a WSL2 kernel. Apply it with `docker compose up -d`.

Sign in with any of these IDs and **any password**:

| ID | Account |
|---|---|
| `ops` | Planner · Customer A (owns the demo record RT-1048) |
| `planner.b@northfield.example`, `planner.c@northfield.example` | Planner · Customer B, C |
| `approver` | Approver |
| `engineer` | Engineer |
| `finance` | Finance |
| `developer` | Developer (integration) |
| `exec` | Executive |
| `warehouse1`, `warehouse2` | Warehouse Manager · Warehouse 1, 2 |
| `admin` | Admin |

Stop with `docker compose down`; add `-v` to delete the database as well.

The runtime images (no dev tools, non-root users, the web app built inside its image and served by nginx with a CSP)
are opt-in and also need nothing on the host but Docker:
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` (see the comments in
`docker-compose.prod.yml`).

### Windows option: Docker inside WSL (no Docker Desktop)

One-time setup, from PowerShell:

```powershell
wsl --install -d Ubuntu-24.04 --no-launch
wsl -d Ubuntu-24.04 -u root -- bash -lc "apt-get update && apt-get install -y docker.io docker-compose-v2 && systemctl enable --now docker"
# stop WSL adding the Windows PATH (a Windows Docker credential helper on it breaks image pulls)
wsl -d Ubuntu-24.04 -u root -- bash -lc "printf '[boot]\nsystemd=true\n\n[interop]\nappendWindowsPath=false\n' > /etc/wsl.conf"
wsl --terminate Ubuntu-24.04
```

Then, each time, run the quick start's commands inside WSL:
`wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/c/<path-to>/Circularity-ui && docker compose up -d --build"`.
Keep a WSL terminal open while you use the app: WSL stops its VM, and the containers with it, when the last WSL
session closes (the services have `restart: unless-stopped`, so they come back when Docker starts again).

### Frontend only (no Docker)

```sh
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The app has no built-in backend: the dev server proxies `/api` and `/mcp` to `di-api` on http://localhost:8000 (`API_PROXY_TARGET` overrides it), so start the backend with Docker as above. Without it, sign-in fails and no page has data.

---

## How it works

```
 Browser ── React app (frontend)
              │  src/api/*  typed functions over di-api (HTTP), kept live by its
              │             event stream (GET /api/stream)
              ▼
 di-api (backend) ─────────────── Postgres "di"
   sign-in, access policy            action journal, events, canonical store,
   POST /api/actions/{id}            provenance, conflicts, sync runs, fetch log
   connectors ─── sync jobs ── di-worker
              │  HTTP: OData, REST, SOQL, OSLC, SFTP … as each vendor speaks
              ▼
 source-sim (source-sim) ──── Postgres "sources" (one schema per system)
   20 mocked systems, simulated clock, scheduled work, webhooks, fault injection
```

### The frontend (`frontend`)

React and TypeScript (Vite). Every screen of the original demo has been rebuilt: Home, My Tasks, Alerts, Command Center, Returned assets, Asset intelligence, the ten stage pages of a case with its approval card, Analytics, Audit, Process orchestration with the live run board, Connection Fabric, Workflow Studio, MCP & Tools, Access, Reports, Data Checks and Settings, for all eight roles.

The source is in `frontend/src`: `api/` (the typed API layer), `pages/<area>/`, `components/` (shared UI),
`hooks/`, `utils/`, `layout/` (the app shell: sidebar, top bar, the Ask panel), `assets/` and `styles/`.

Pages only call the typed API layer (`src/api/*`), which reads `di-api` through a cache that the live event stream keeps current, and every change goes through `invoke(actionId, input)` (`POST /api/actions/{id}`). Ask Circularity (Ctrl+J) answers through `POST /api/ask`. Conventions for pages: [`frontend/porting.md`](frontend/porting.md).

### The backend (`backend`, package `di`)

The package is in layer folders: `routes/` (every HTTP endpoint, thin), `schemas/` (request and response shapes),
`services/` (business logic), `repositories/` (read queries), `models/` (database tables, one module per domain) and
`core/` (config, database, sign-in, access policy, errors, clock), plus `connectors/`, `workflow/` and `mcp/`. The
dependency direction is checked by `lint-imports` (`backend/.importlinter`): routes over services over repositories,
and core imports nothing above it.

| Part | What it does |
|---|---|
| **Sign-in and access** (`di/core/auth.py`, `di/core/policy.py`) | `POST /api/auth/login` takes the IDs above and returns a JWT. The access policy (roles, pages, permissions, tenant boundary, warehouse lock, Approver delegations) is enforced on every endpoint, with the same answers as the demo for all 11 accounts |
| **Actions** (`di/services/actions/`) | `POST /api/actions/{id}` runs the demo's 76 named actions through one pipeline: validation, permission, case scope, agent gate, guards, idempotency, the handler, the **journal** and **events**. Errors use the demo's codes and wording |
| **Connectors** (`di/connectors/`) | One adapter per source system. A sync reads each system the way that vendor's API works (paging, delta reads, auth), keeps every record as received, and maps it to canonical facts |
| **Canonical store** (`di/services/canonical/`) | Every value every source gave for every field, with its source field, original value, transform and request (provenance). The canonical value follows the system with **authority** over that field; when systems disagree a **conflict** is opened that names the authority |
| **Sync and webhooks** | The worker syncs each source on its interval; source changes arrive as signed webhooks and trigger a delta sync of just that source |
| **Worker** (`di/worker.py`) | Postgres job queue (no Redis): sync jobs, scheduled syncs |

### The mocked systems (`source-sim`)

Twenty enterprise systems, each in its own Postgres schema, seeded with the demo's world so they agree with each other (RT-1048 is motor `MTR-2041` in Warehouse 1 everywhere, wanted by sales order `SO-48102`, with planned purchase PO `49048` in S/4).

| Kind | Systems |
|---|---|
| **Full vendor mocks** (the vendor's real API style, rules and errors) | SAP S/4HANA (OData v2, CSRF), SAP Ariba, Salesforce (SOQL), ServiceNow (Table API), IBM Maximo (OSLC), IBM Sterling OMS, Oracle Transportation Management (replaces the demo's fictional ShipLane TMS), Oracle Depot Repair, Oracle Lease and Finance Management, Manhattan Active WM, Optoro, Siemens Teamcenter, Aras Innovator, Bentley AssetWise, MasterControl, Persefoni, Ritchie Bros. Market Data, Machinio, Sims Lifecycle Services (a real SFTP server on port 2222) |
| **Generic mock** | SafetyCulture |
| **Not provisioned** (as in the demo) | AWS IoT Core |

Every change a mock makes is stamped with a **simulated clock** that starts at the demo's as-of time (7 Oct 2026, 09:00 UTC), recorded as an event and delivered to subscribers as a signed CloudEvent. Work that takes time (a repair, a shipment) is scheduled on that clock.

Each system answers at http://localhost:8100 below its own path: `/sap/opu/odata/sap` for S/4HANA, `/ariba/api` for Ariba, `/salesforce/services/data/v59.0` for Salesforce, `/maximo/api` for Maximo, and so on; `GET /_sim/systems` lists them all.

Controlling the simulation (`/_sim`, see http://localhost:8100/docs):

```sh
curl localhost:8100/_sim/clock                                                       # simulated time
curl -X POST localhost:8100/_sim/clock/advance -H 'content-type: application/json' -d '{"days": 3}'
curl -X POST localhost:8100/_sim/faults -H 'content-type: application/json' -d '{"system": "erp", "kind": "unavailable", "minutes": 30}'
curl -X POST localhost:8100/_sim/faults/demo                                         # the demo's starting fault: Ritchie Bros. token expired
curl -X POST localhost:8100/_sim/webhooks -H 'content-type: application/json' -d '{"url": "http://source-sim:8100/_sim/sink"}'
curl localhost:8100/_sim/sink                                                        # events received by the demo sink
curl -X POST localhost:8100/_sim/reset                                               # every system back to the seed, clock reset
```

Demo credentials of each mocked system are in its module docstring (`source-sim/sim/vendors/*`, e.g. `sim/vendors/s4`, `sim/vendors/ariba`). The generic specs (`sim/generic/specs/*`, e.g. SafetyCulture) follow `sim/generic/spec.py`: API key `<id>-demo-key`; Basic `di-connector` / `<id>-demo`; OAuth `di-connector` / `<id>-demo-secret`.

### Where the data comes from

The original single-file demo, `fixtures/demo/index.html`, is the specification. `frontend/scripts/dump-golden.mjs` runs its logic headless and writes `fixtures/golden/*.json` (the 128 cases, 1,400 closed decisions, policy, actions, figures and a scripted RT-1048 journey). The mocks are seeded from those files, and the backend's tests compare against them, so the backend gives the demo's answers.

---

## Try it

1. Sign in as `ops` and open **Returned assets**: RT-1048 is marked *Start here*. Follow its ten stages; submit it for review.
2. Sign in as `approver`, open RT-1048 at *Approve*, and approve it.
3. Watch a source change flow into the backend: move a unit in the S/4 mock and read the backend's canonical record —

```sh
# as the Developer, see the connected systems and their sync state
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'content-type: application/json' -d '{"username":"developer","password":"x"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/sources
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/canonical/demand/PO-49048     # $12,000 purchase baseline, with provenance
```

---

## Develop

The test and maintenance scripts are in `scripts/dev/`. They are bash (3.2 or later) and run from the repo root on Linux, macOS (its stock bash) and Git Bash on Windows; the host needs only `docker` and `curl`, since the test lock, timeouts, `psql`, `python` and `node` run inside the containers. If your Docker runs inside WSL, run them there: `wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path-to>/Circularity-ui/scripts/dev/<script>.sh`. They find the published ports themselves, so they follow `API_PORT` and friends. They take the shared test lock and stop the worker while tests run, so scheduled syncs do not race them. Every script is listed in [`docs/agents/scripts.md`](docs/agents/scripts.md); suites and CI in [`docs/agents/testing.md`](docs/agents/testing.md).

```sh
# tests (in the running containers)
bash scripts/dev/api-test.sh tests/test_milestone_rt1048.py   # selected api tests (here the first milestone: RT-1048 end to end)
bash scripts/dev/full-suite.sh                                # the whole api suite (~25 min) and the source-sim suite
bash scripts/dev/web-check.sh                                 # tsc and vitest in the web container
bash scripts/dev/reset.sh                                     # afterwards: the demo's starting state, worker started
cd frontend && npm test && npm run lint && npm run build      # the frontend on the host (Node 24)

# sync every source once and summarise conflicts
docker compose exec -T -e PYTHONPATH=/app api python scripts/full_sync.py

# a database migration
docker compose exec api alembic revision --autogenerate -m "what changed"

# regenerate the golden data after changing fixtures/demo/index.html on purpose
cd frontend && npm run golden
```

The tests use the same databases as the running services, so run `scripts/dev/reset.sh` after them. To delete everything, database volume included: `docker compose down -v`.

CI (`.github/workflows/ci.yml`) brings the stack up and runs the api and source-sim suites in their containers, the web tests and build, linters, and dependency and secret scans; an arm64 job starts the whole stack on an arm64 runner and smoke-checks it.

### Repository

```
frontend/              React app (Vite, TypeScript); porting.md has the page conventions
  src/api/             the typed API layer over di-api (pages call only this)
  src/pages/<area>/    the pages, one folder per area
  src/components/      shared UI (kit/ holds the small building blocks)
  src/hooks/ src/utils/ src/layout/ src/assets/ src/styles/
backend/               di-api and di-worker (python -m di.worker): FastAPI, SQLAlchemy, Alembic; package `di`
  di/routes/           every HTTP endpoint (thin)        di/schemas/       request and response shapes
  di/services/         business logic                    di/repositories/  read queries and read models
  di/models/           database tables, per domain       di/core/          config, db, auth, policy, errors …
  di/connectors/ di/workflow/ di/mcp/                    the Connection Fabric, the workflow engine, the MCP server
source-sim/            the mocked enterprise systems, package `sim`
  sim/core/  sim/routes/  sim/vendors/<system>/ (routes.py, models.py, seed.py)  sim/generic/  sim/seed/
fixtures/golden/       the demo's computed data, the backend's test reference
fixtures/demo/index.html         the original single-file demo: the specification and the source of the golden data
fixtures/demo/assets/products/   product photos
infra/postgres/        database init
scripts/doctor.sh      checks this machine can run the stack (read-only)
scripts/dev/           test and maintenance scripts (bash)
docker-compose.yml
docker-compose.prod.yml  opt-in: the runtime images (no dev tools, non-root, the web app built and served by nginx;
                         the web image is frontend/Dockerfile.runtime, built from the repo root)
docs/reference/        source documents: the agent-first product spec, the user journey deck, the IFS process fit
docs/guides/           user guides: the Connection Fabric (connectors, Workflow Studio, AI builder) and a
                       step-by-step workflow tutorial for demos
docs/plan-fullstack-poc.md   decisions and architecture
docs/backend-steps.md        the backend build, step by step, with the status of each step
docs/agents/           working notes for agents: scripts, testing, plans, decisions
```

---

## Status

| Step | | Status |
|---|---|---|
| Frontend | every screen in React | done |
| B1–B4 | golden data, seed, SAP S/4HANA and SAP Ariba mocks | done |
| B5, B5b | the other 18 mocks; 19 of the 20 as full vendor mocks | done |
| B5c | AWS IoT Core as a full vendor mock with a connector (starts not provisioned, as in the demo; `POST /api/sources/iot/connect`) | done |
| B6 | simulated clock, scheduled work, webhooks, faults | done |
| B7 | sign-in and the access policy | done |
| B8 | the action endpoint and journal | done (handlers arrive with B10–B13) |
| B9 | connectors, canonical store, provenance, conflicts | done |
| B10 | decision engine: routes, gates, ranges, ranking, what-if, pool optimiser | done |
| B11 | cases in the database, the stage machine, every read action | done |
| B12 | decisions, approvals, evidence, collaboration, access and identity actions | done |
| B13 | instructions really sent to the mocks, acknowledged from their events on the simulated clock; outcomes and reconciliation (first milestone: RT-1048 end to end) | done |
| B14 | read APIs for every screen (`/api/screens/*`, `/api/checks`), scoped to the account | done |
| B15 | live updates (`GET /api/stream`, Server-Sent Events) and Workflow Studio actions with runs as worker jobs | done |
| B16 | MCP server at `/mcp`: the ten agent tools, agent scopes and hard rules in code, every call logged | done |
| B16b | Ask Circularity on a language model (Groq free tier; `POST /api/ask`, read-only, falls back to the demo's answers) | done |
| B17 | the frontend on the backend: every page reads di-api, live updates, the Ask Circularity panel; the in-browser engine deleted; RT-1048 end to end in the browser | done |
| next | the plans in `docs/agents/plans/`: agent loop, queue and task CRUD, CRUD for every resource and gzip, async, OpenTelemetry | planned |
| B18 | browser tests, run book, security review | to do |

Details, decisions and known limits of each step: [`docs/backend-steps.md`](docs/backend-steps.md).
