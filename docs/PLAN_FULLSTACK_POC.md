# Plan: from the HTML demo to a full-stack POC

**Status:** agreed 19 Nov 2026 · **Branch:** `feature/fullstack-poc` · **Scope:** Recover (Circularity) only

## 1. Why

`index.html` is a clickable demo: one 9,000-line file, all data generated in the browser from seed `20261007`, state in memory, nothing connected (README sections 12 and 13). The next step is a working POC: a real backend and database, server-side access control, and connectors that talk to source systems over HTTP the way they would in production. The source systems themselves are mocked on Postgres.

## 2. Decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Which sources are mocked as SAP | **Only the two that are SAP today: SAP S/4HANA (ERP) and SAP Ariba (procurement).** Every other source keeps its current vendor (Maximo, Sterling OMS, Manhattan WMS and so on) and gets a generic mock with that vendor's resource shapes and the paths already in `SOURCES` |
| D2 | Frontend | **React rewrite** (TypeScript, Vite), page by page, reusing the demo's CSS and design tokens |
| D3 | Backend | **Python, FastAPI**, SQLAlchemy 2 and Alembic. Python because the models named in the demo (XGBoost, LightGBM) and the agents are Python-native |
| D4 | Framework apps | Reconcile and Resolve (`framework/`) stay out of scope |
| D5 | Hosting | **Local Docker Compose.** GitHub Pages keeps serving the static demo, which stays as the reference until the React app reaches parity |
| D6 | Queue | A Postgres job table claimed with `FOR UPDATE SKIP LOCKED`, so no Redis |
| D7 | Login | Local JWT with the demo IDs (`exec`, `ops`, `planner.b@northfield.example` …). Real SSO later; Keycloak is the option if an OIDC stand-in is needed |

## 3. Architecture

```
web (React + TS)  ──REST + SSE──▶  di-api (FastAPI)  ──SQL──▶  Postgres · database "di"
                                       │ jobs
                                   di-worker  ──HTTP (OData / REST)──▶  source-sim (FastAPI)
                                                                            │ SQL
                                                                     Postgres · database "sources"
                                                                     schema per system: s4, ariba,
                                                                     maximo, sterling, manhattan …
```

| Service | Job |
|---|---|
| `web` | The product UI. Talks only to `di-api` |
| `di-api` | Auth and RBAC, cases, decisions, approvals, decision engine, audit and provenance, event stream, conflict queue, Connection Fabric, MCP server |
| `di-worker` | Same image as `di-api`. Runs sync jobs (inbound), instruction jobs (outbound) and webhook handling |
| `source-sim` | Mock source systems: SAP S/4HANA and SAP Ariba with SAP-shaped APIs, and generic mocks for every other vendor. Includes the seed, outbound events and fault injection |
| `postgres` | One server with two databases: `di` (the product) and `sources` (the mocked systems). The product never reads `sources` directly |

**The core rule.** `di` is never seeded directly. It fills only by syncing through the connectors over HTTP. Pointing a connector at a real system later means changing its base URL and credentials, not its code.

## 4. Source systems

### 4.1 SAP S/4HANA (mock)

Postgres schema `s4`, with SAP table names and columns:

| Area | Tables | Used for |
|---|---|---|
| Materials | MARA, MAKT, MARC | Product master, plant data |
| Stock and valuation | MARD, MBEW | Stock by plant and storage location, valuation |
| Purchasing | EKKO, EKPO | Purchase baseline (avoided spend) |
| Reservations | RKPF, RESB | Outbound: reserve stock for a redeploy |
| Material documents | MKPF, MSEG | Outbound: goods movements; inbound: actuals |
| Cost postings | ACDOCA | Actual cost for reconciliation |
| Plants | T001W | Plant code to site lookup (`1030` → Site 3) |

APIs at `/sap/opu/odata/sap/…`, the paths `SOURCES.erp` already lists:

- `API_PRODUCT_SRV/A_Product`
- `API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod`
- `API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder` (and `…Item`)
- `API_RESERVATION_DOCUMENT_SRV/A_ReservationDocumentHeader` (POST)
- `API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader` (POST)

Behaviour the mock reproduces:
- OData v2 JSON (`{"d":{"results":[…]}}`), `$filter` (eq, ne, gt, ge, lt, le, and, `substringof`), `$select`, `$top`, `$skip`, `$orderby`, `$inlinecount=allpages`, `$format=json`
- Delta reads by `LastChangeDateTime gt datetimeoffset'…'`
- `x-csrf-token: Fetch` on a GET before any POST; a POST without a valid token is rejected with 403
- Basic auth or OAuth 2.0 client credentials (a token endpoint on the mock)
- SAP error body: `{"error":{"code":"…","message":{"lang":"en","value":"…"}}}`
- Business events (for example `sap.s4.beh.reservation.v1.Reservation.Created.v1`) written to an outbox and pushed as CloudEvents webhooks, like SAP Event Mesh

### 4.2 SAP Ariba (mock)

Postgres schema `ariba`: purchase orders, sourcing events and bids, suppliers. Ariba REST JSON (not OData), with the paths in `SOURCES.proc`:

- `/procurement-reporting-details/v2/prod/views/PurchaseOrders`
- `/sourcing-event/v2/prod/events`
- `/supplier-data/v4/prod/suppliers`

It also reproduces:
- the `apiKey` header together with an OAuth bearer token
- `PageToken` paging
- the 30-minute polling cadence

### 4.3 Every other source (generic mocks)

One schema per system: `salesforce`, `oracle_lease`, `sterling`, `maximo`, `servicenow`, `teamcenter`, `aras`, `mastercontrol`, `assetwise`, `manhattan`, `shiplane`, `optoro`, `safetyculture`, `depot_repair`, `ritchie`, `machinio`, `persefoni`.

A declarative spec per system defines:
- its resources and their Postgres tables
- its read and write paths (the same as `SOURCES[*].read` and `write`)
- its paging style and its auth style

One generic router serves every spec. Two exceptions keep their current status:
- **Sims (recycler)** stays a signed-CSV SFTP drop. The mock writes files to a folder, and DI imports them through Manual import.
- **AWS IoT** stays *not provisioned*.

### 4.4 Seed and faults

- **The seed** is a Python port of the demo's generator: same seed, same 128 live cases, about 1,400 closed decisions, and the hero cases RT-1048, RT-1049, RT-1051 and RT-1052. It writes into the source schemas as each system would hold the data. Examples: a returned motor is an EQUI record in Maximo's shape, an inspection in SafetyCulture, and stock in Manhattan and in S/4 MARD.
- **The demo's integrity checks** (one figure on every page) become backend tests that run after a full sync.
- **Fault injection** at `/_sim/faults` replaces the timer-driven simulation and the Presenter failure drill. It can add latency, return 5xx, expire a token (Ritchie Bros. starts expired, as in the demo) or make a feed stale.

## 5. Backend design (di-api, di-worker)

| Area | What it holds |
|---|---|
| Connectors | One adapter per source type: auth, paging, delta, then mapping to the seven canonical models (`CANON`, field mappings from `MAPPINGS`) with provenance per field (source, request, fetched at, confidence) |
| Canonical store | Asset & component, Condition & eligibility, Demand opportunity, Intervention, Route candidate, Decision, Outcome. Versioned as in the demo |
| Sync | Jobs per source on its interval, plus webhooks for event sources. Freshness, completeness and failed records recorded per run (Monitor tab) |
| Conflicts | When two sources disagree on a field, the source with authority (`SOURCES[*].authority`) is named and dependent routes are held, never silently resolved |
| Decision engine | Ported from `mkRoute`, `fail`, `rankRoutes`, gates, forecasts with P10/P50/P90, pool optimizer and cost trace (`EX_*`). Pure functions with tests against the demo's numbers |
| Case lifecycle | The ten stages as a state machine; each transition writes an audit entry and an event |
| Approvals | Approve, override (reason required) and decline (reason required); delegation scopes from Admin |
| Outbound | An approved instruction becomes a job that sends an idempotent write to the owning system (S/4 reservation, Maximo work order, ShipLane load, Sterling order allocation). The mock acknowledges, later emits completion, and the outcome flows back |
| Reconcile & learn | Actuals linked to the decision; predicted vs actual and model-version error computed from the database |
| Audit | Fetch log, evidence gaps, comments; append-only table |
| RBAC | The `/*RBAC-START*/` block becomes server policy: roles, pages, actions, tenant lock, warehouse lock. Enforced on every endpoint; the UI only hides what the API would refuse anyway |
| MCP | A real MCP server with the ten tools, agent scopes and `HARD_RULES` enforced in code. Agents stay rule-based first |
| Live updates | Server-sent events for the run board, event stream and notifications |

## 6. Frontend (web)

- **Stack:** React 18, TypeScript, Vite, React Router, TanStack Query.
- **Look and routes:** the demo's tokens and CSS move into `apps/web/src/styles`, so the look carries over. The routes keep the demo's hash paths (`#/product/asset/RT-1048`), so existing links and the demo script still work.
- **Porting order:**
  1. Sign-in
  2. Returned assets
  3. Case stage pages (ten stages and the Overview)
  4. Approvals
  5. Command Center
  6. Connection Fabric
  7. Analytics
  8. Audit
  9. MCP and Tools
  10. Access
  11. Home and Ask
- **Checks:** the demo's headless suites (208 role checks, 110 guided-flow checks, 88 demo-path checks) are rewritten in Playwright against the running stack.

## 7. Repository layout

```
apps/api/            di-api and di-worker (one Python package: di)
apps/source-sim/     mock source systems and the seed (package: sim)
apps/web/            React app
infra/postgres/      init scripts (databases, roles)
docker-compose.yml
.env.example
index.html           the static demo, unchanged, still on GitHub Pages
```

## 8. Phases

| # | Phase | Delivers | Effort |
|---|---|---|---|
| 0 | Foundations | Layout above, Compose stack, health checks, Alembic baseline, job table and worker loop, CI | 3–4 days |
| 1 | Mock sources | S/4HANA and Ariba mocks (section 4), generic mock framework with every other vendor, seed, outbox and webhooks, fault injection | 2 weeks |
| 2 | Connectors | Adapters, canonical store with provenance, sync jobs, freshness, conflicts, CSV import, Connection Fabric API | 2 weeks |
| 3 | Decision core | Engine port, case state machine, approvals, audit, events | 2–3 weeks |
| 4 | Outbound and reconcile | Instructions to source systems, acknowledgements, outcomes, predicted vs actual | 1–1.5 weeks |
| 5 | Auth and RBAC | JWT login with demo IDs, server-side policy, delegations, access requests | 1 week |
| 6 | Frontend | React pages in the order of section 6 | 4–5 weeks, overlapping 2–5 |
| 7 | Agents and MCP | MCP server, ten tools, scopes, hard rules | 1–1.5 weeks |
| 8 | Hardening | Playwright suites, API tests, demo reset, run book | 1 week |

**First milestone:** RT-1048 through all ten stages on synced mock data, end of phase 4, with a thin UI.

## 9. Risks and notes

- **GitHub Pages publishes the whole repository** (`.github/workflows/static.yml` uploads `.`). The new code will be public on the Pages site as well as in the repo. Never commit `.env` files.
- **Vendor names.** The mocks reproduce public API shapes; nothing is a real SAP or vendor connection. README section 13's Legal note still applies: nobody should say a named vendor product is connected.
- **Two copies of the logic during the port.** Until the React app reaches parity, the demo and the POC run the decision logic separately. The engine tests pin the backend to the demo's figures, so drift shows up as a failing test.
