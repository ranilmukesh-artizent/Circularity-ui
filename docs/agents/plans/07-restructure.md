# Plan 7: folder restructure (frontend and backend, layer folders)

**Goal:** separate top-level folders `frontend/`, `backend/` and `source-sim/`, and inside them separate folders for
models, schemas, routes, services and the rest, with no change in behaviour (parity, every test, every smoke).

**Asked by the user, 22 Nov 2026:** "Maintain separate folders for frontend and backend … Use separate folders for
models, schemas, routes etc. Dont have everything in one folder." Done before the trial package (which builds from
these paths).

## Target layout

```
backend/di/                     (was apps/api/di)
  main.py  worker.py            entry points (uvicorn di.main:app, python -m di.worker) stay where they are
  core/                         config, db, deps, auth, policy, errors, clock, logs, golden, state, jobs
  models/                       SQLAlchemy tables, one module per domain; __init__ re-exports every table
  schemas/                      Pydantic request and response shapes, one module per route area
  routes/                       every HTTP endpoint: auth, actions, sources, webhooks, stream, ask, screens/<area>
  services/                     business logic: actions/, engine/, execution/, instructions/, cases/, canonical/,
                                ask/, screens/<area> (what each page shows), stream
  repositories/                 read queries and read models (was reads/), incl. the live Connection Fabric
  connectors/  workflow/  mcp/  subsystems kept as units; their endpoints live in routes/
frontend/src/                   (was apps/web/src)
  api/                          the facade and the HTTP client (pages call only these, golden rule 6)
  pages/<area>/                 one folder per page area
  components/                   shared UI (was ui/), incl. kit/
  hooks/                        shared React hooks
  utils/                        plain helpers (csv, download, keys …)
  layout/                       the app shell (was app/: App, Sidebar, TopBar, AskPanel)
  assets/                       generated static assets (assets.gen.ts)
  styles/
source-sim/sim/                 (was apps/source-sim/sim)
  core/                         clock, config, db, events, faults, scheduler, webhooks, registry
  routes/                       admin and mock endpoints shared by all systems
  vendors/<system>/             one folder per mocked system: routes.py, models.py, seed.py (+ its own services)
```

Source-sim keeps one folder per mocked system: each folder is one vendor's whole mock, and splitting 20 systems
across shared layer folders would scatter them. Inside each, the same names: `routes.py`, `models.py`, `seed.py`.

## Rules for every session

- Moves only: no change to a number, a text, an endpoint path, a response shape or an action id.
- Thin routes: an endpoint reads its input (a schema or query parameters), checks the page permission, calls one
  service function and returns its result. Logic, SQL and shaping go to services or repositories.
- Keep the public names tests and the frontend use; when a function moves, update its callers (no re-export shims,
  except the `models` package and the stub routes during the move).
- `git mv` (or a plain move that git sees as a rename) so history follows.
- `lint-imports` (backend/.importlinter) is the layering gate: routes are leaves, screen services do not import each
  other, routes > screen services > repositories > stores and engine, core and models import nothing above them.

## Phases

1. **Baseline (lead, done):** backend modules moved into `core/`, `services/`, `repositories/`, `routes/` by script
   with every import, mock string and doc path rewritten; `models.py` split into `models/`; `routes/screens/<area>.py`
   and `routes/{stream,webhooks,ask}.py` stubs; new contracts.
2. **Parallel (disjoint files):**
   - S1 screens: access, analytics, audit, checks, command, home, nav, reference.
   - S2 screens: case, integration (+ move `Fabric` and its loaders into `repositories/`), mcp, orchestration,
     product, workflows.
   - R routes and schemas: routes/auth, actions, sources; stream, webhooks, ask out of core/connectors/services into
     routes + schemas; `core/stream.py` to `services/stream.py`; core's upward imports (policy's clock helpers).
   - SIM: source-sim as above.
   - F: frontend as above.
3. **Top-level rename (lead):** `apps/web` → `frontend`, `apps/api` → `backend`, `apps/source-sim` → `source-sim`,
   with compose, Dockerfiles, CI, scripts and docs.
4. **Check (lead):** full api and source-sim suites, web check, lint-imports, smoke-pages 11 accounts, RT-1048,
   smoke-fabric, fresh clone (dev and prod). Then commit and push.

## Decisions taken while doing it

- Services raise `di.core.errors.ApiError` (or return None, or a `NotFound` the route maps) instead of FastAPI's
  `HTTPException`, so they do not depend on the web framework; both answer the same `{ok: false, error: {code,
  message}}` body at the same status. A few older helpers (`repositories/context.load_case`, services/auth, journal,
  sources, stream) still raise `HTTPException`; they are called only from requests.
- `Fabric` (the live Connection Fabric loader) moved from the integration screen to `repositories/fabric.py`, with
  `held_conflicts` (the menu badge rule, from the nav screen); repositories no longer import screen services.
- New modules: `core/dates.py` (the demo clock helpers `AS_OF`, `ms`, `iso`, `add_days`, re-exported by
  `repositories/common`), `services/{auth,health,journal,sources,stream}.py`, `routes/health.py`.
- The case lifecycle's call to the case-triggered workflows is an allowed exception in the layers contract (a lazy,
  savepointed call-out, not a read dependency).
- Source-sim: `mock.py` (the Mock contract and discovery) is in `core/`; OData lives in `vendors/s4/odata/` (only S/4
  uses it; Aras has its own OData v4); `generic/` stays top-level (it builds several systems from specs, its builder in
  `generic/routes.py`); the three `@app` routes in `main.py` (`/health`, `/_sim/systems`, `/_sim/reset`) stay there
  because they read main's start-up state. S/4 and Ariba now declare `MOCK` like every vendor.
- Frontend: `theme.ts`, `askBus.ts`, `keys.ts` are `utils/` (stores and helpers, not components); `hooks/` holds only
  real hooks (`useAction`, `useTick`); `api/useBackend` stays in the facade.

## Status

- [x] Phase 1 baseline
- [x] Phase 2: S1, S2, R, SIM, F
- [x] Phase 3 top-level rename, docs
- [ ] Phase 4 full check, commit, push
