# Circularity Decision Workbench (full-stack POC)

Circularity decides what happens to every returned asset — redeploy it, resell it, re-lease it, harvest parts, recover material or exit it responsibly — with evidence from the enterprise systems a company already runs, a forecast, a human approval, and a check of what it actually returned. It is **Recover**, one app of the Artizent Decision Intelligence Framework.

This repository is the proof of concept that turns the earlier single-file demo into a working application: a React frontend, a Python backend with a Postgres database, and **mocks of the 20 enterprise systems** the decisions draw on (SAP S/4HANA, SAP Ariba, Salesforce, IBM Maximo, IBM Sterling OMS, ServiceNow and others), all running locally in Docker.

> All data is synthetic (the demo company *Northfield Industrial Leasing*, three customer tenants, eight sites, 128 returned assets). No real system is connected: the vendor systems are mocks that copy each vendor's API style. Nobody should state or imply that a named vendor product is connected.

---

## Start it

### Requirements

- **Docker** with Compose. On Windows without Docker Desktop, use Docker inside WSL (below).
- **Node.js 20 or later**, only to run the frontend outside Docker.

### Everything (recommended)

```sh
docker compose up --build
```

| Open | What it is |
|---|---|
| http://localhost:5173 | The app (React) |
| http://localhost:8000/docs | `di-api`: the backend API (OpenAPI) |
| http://localhost:8100/docs | `source-sim`: the 20 mocked enterprise systems |
| localhost:5432 | Postgres (user and password `circ`): databases `di` and `sources` |

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

### On Windows with WSL (no Docker Desktop)

One-time setup, from PowerShell:

```powershell
wsl --install -d Ubuntu-24.04 --no-launch
wsl -d Ubuntu-24.04 -u root -- bash -lc "apt-get update && apt-get install -y docker.io docker-compose-v2 && systemctl enable --now docker"
# stop WSL adding the Windows PATH (a Windows Docker credential helper on it breaks image pulls)
wsl -d Ubuntu-24.04 -u root -- bash -lc "printf '[boot]\nsystemd=true\n\n[interop]\nappendWindowsPath=false\n' > /etc/wsl.conf"
wsl --terminate Ubuntu-24.04
```

Each time:

```powershell
wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/c/<path-to>/Circularity-ui && docker compose up -d --build"
```

Keep a WSL terminal open while you use the app (`wsl -d Ubuntu-24.04`): WSL stops the Linux VM, and the containers with it, when the last WSL session closes. The containers restart when Docker starts again.

### Frontend only (no Docker)

```sh
cd apps/web
npm install
npm run dev          # http://localhost:5173
```

Without the backend, the app runs on its built-in mock backend (see *How it works*): every screen works, nothing is saved on a server.

---

## How it works

```
 Browser ── React app (apps/web)
              │  src/api/*  typed functions; today they call the in-browser engine,
              │             after the switch-over (B17) they call di-api
              ▼
 di-api (apps/api) ─────────────── Postgres "di"
   sign-in, access policy            action journal, events, canonical store,
   POST /api/actions/{id}            provenance, conflicts, sync runs, fetch log
   connectors ─── sync jobs ── di-worker
              │  HTTP: OData, REST, SOQL, OSLC, SFTP … as each vendor speaks
              ▼
 source-sim (apps/source-sim) ──── Postgres "sources" (one schema per system)
   20 mocked systems, simulated clock, scheduled work, webhooks, fault injection
```

### The frontend (`apps/web`)

React and TypeScript (Vite). Every screen of the original demo has been rebuilt: Home, My Tasks, Alerts, Command Center, Returned assets, Asset intelligence, the ten stage pages of a case with its approval card, Analytics, Audit, Process orchestration with the live run board, Connection Fabric, Workflow Studio, MCP & Tools, Access, Reports, Data Checks and Settings, for all eight roles.

Until the frontend is switched to the backend (step B17), it gets its data from an **in-browser engine**: the original demo's own logic (`index.html`), run unchanged behind a typed API layer (`src/api/`). Pages only call `src/api/*`, and every change goes through `invoke(actionId, input)` — the same action ids the backend serves. Conventions for pages: [`apps/web/PORTING.md`](apps/web/PORTING.md).

### The backend (`apps/api`, package `di`)

| Part | What it does |
|---|---|
| **Sign-in and access** (`di/auth.py`, `di/policy.py`) | `POST /api/auth/login` takes the IDs above and returns a JWT. The access policy (roles, pages, permissions, tenant boundary, warehouse lock, Approver delegations) is enforced on every endpoint, with the same answers as the demo for all 11 accounts |
| **Actions** (`di/actions/`) | `POST /api/actions/{id}` runs the demo's 76 named actions through one pipeline: validation, permission, case scope, agent gate, guards, idempotency, the handler, the **journal** and **events**. Errors use the demo's codes and wording |
| **Connectors** (`di/connectors/`) | One adapter per source system. A sync reads each system the way that vendor's API works (paging, delta reads, auth), keeps every record as received, and maps it to canonical facts |
| **Canonical store** (`di/canonical/`) | Every value every source gave for every field, with its source field, original value, transform and request (provenance). The canonical value follows the system with **authority** over that field; when systems disagree a **conflict** is opened that names the authority |
| **Sync and webhooks** | The worker syncs each source on its interval; source changes arrive as signed webhooks and trigger a delta sync of just that source |
| **Worker** (`di/worker.py`) | Postgres job queue (no Redis): sync jobs, scheduled syncs |

### The mocked systems (`apps/source-sim`)

Twenty enterprise systems, each in its own Postgres schema, seeded with the demo's world so they agree with each other (RT-1048 is motor `MTR-2041` in Warehouse 1 everywhere, wanted by sales order `SO-48102`, with planned purchase PO `49048` in S/4).

| Kind | Systems |
|---|---|
| **Full vendor mocks** (the vendor's real API style, rules and errors) | SAP S/4HANA (OData v2, CSRF), SAP Ariba, Salesforce (SOQL), ServiceNow (Table API), IBM Maximo (OSLC), IBM Sterling OMS |
| **Being upgraded to full vendor mocks** (step B5b) | Oracle Transportation Management (replaces the demo's fictional ShipLane TMS), Oracle Depot Repair, Oracle Lease and Finance Management, Manhattan Active WM, Optoro, Siemens Teamcenter, Aras Innovator, Bentley AssetWise, MasterControl, Persefoni, Ritchie Bros. Market Data, Machinio, Sims Lifecycle Services (a real SFTP server on port 2222) |
| **Generic mock** | SafetyCulture |
| **Not provisioned** (as in the demo) | AWS IoT Core |

Every change a mock makes is stamped with a **simulated clock** that starts at the demo's as-of time (7 Oct 2026, 09:00 UTC), recorded as an event and delivered to subscribers as a signed CloudEvent. Work that takes time (a repair, a shipment) is scheduled on that clock.

Controlling the simulation (`/_sim`, see http://localhost:8100/docs):

```sh
curl localhost:8100/_sim/clock                                                       # simulated time
curl -X POST localhost:8100/_sim/clock/advance -H 'content-type: application/json' -d '{"days": 3}'
curl -X POST localhost:8100/_sim/faults -H 'content-type: application/json' -d '{"system": "erp", "kind": "unavailable", "minutes": 30}'
curl -X POST localhost:8100/_sim/faults/demo                                         # the demo's starting fault: Ritchie Bros. token expired
curl -X POST localhost:8100/_sim/reset                                               # every system back to the seed, clock reset
```

Demo credentials of each mocked system are in its module docstring (`apps/source-sim/sim/s4`, `sim/ariba`, `sim/vendors/*`, `sim/generic/specs/*`).

### Where the data comes from

The original single-file demo, `index.html`, is the specification. `apps/web/scripts/dump-golden.mjs` runs its logic headless and writes `fixtures/golden/*.json` (the 128 cases, 1,400 closed decisions, policy, actions, figures and a scripted RT-1048 journey). The mocks are seeded from those files, and the backend's tests compare against them, so the backend gives the demo's answers.

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

Until the switch-over (step B17), the frontend runs on its in-browser engine, so steps 1–2 do not yet reach the backend.

---

## Develop

```sh
# tests (in the running containers)
docker compose exec api pytest
docker compose exec source-sim pytest
cd apps/web && npm test && npm run build

# sync every source once and summarise conflicts
docker compose exec -e PYTHONPATH=/app api python scripts/full_sync.py

# a database migration
docker compose exec api alembic revision --autogenerate -m "what changed"

# regenerate the golden data after changing index.html on purpose
cd apps/web && npm run golden
```

The source-sim and api tests use the same databases as the running services; run `curl -X POST localhost:8100/_sim/reset` afterwards. Stop the worker while running the connector tests (`docker compose stop worker`), so scheduled syncs do not race them.

CI (`.github/workflows/ci.yml`) runs the Python tests against Postgres and builds the frontend.

### Repository

```
apps/web/              React app (Vite, TypeScript); PORTING.md has the page conventions
apps/api/              di-api and di-worker (FastAPI, SQLAlchemy, Alembic), package `di`
apps/source-sim/       the mocked enterprise systems, package `sim`
fixtures/golden/       the demo's computed data, the backend's test reference
infra/postgres/        database init
docker-compose.yml
index.html             the original single-file demo: the specification and the frontend engine's source
assets/products/       product photos
framework/             the framework overview and the Reconcile and Resolve concept pages (static)
docs/PLAN_FULLSTACK_POC.md   decisions and architecture
docs/BACKEND_STEPS.md        the backend build, step by step, with the status of each step
```

---

## Status

| Step | | Status |
|---|---|---|
| Frontend | every screen in React, on the in-browser engine | done |
| B1–B4 | golden data, seed, SAP S/4HANA and SAP Ariba mocks | done |
| B5, B5b | the other 18 mocks; upgrading 13 to full vendor mocks | full mocks for 6; upgrade in progress |
| B6 | simulated clock, scheduled work, webhooks, faults | done |
| B7 | sign-in and the access policy | done |
| B8 | the action endpoint and journal | done (handlers arrive with B10–B13) |
| B9 | connectors, canonical store, provenance, conflicts | done |
| B10–B13 | decision engine, case lifecycle, approvals, instructions to the systems and reconciliation | next |
| B14–B16 | read APIs for every screen, live updates, MCP server | to do |
| B17 | switch the frontend to the backend | to do |
| B18 | browser tests, run book, security review | to do |

Details, decisions and known limits of each step: [`docs/BACKEND_STEPS.md`](docs/BACKEND_STEPS.md).
