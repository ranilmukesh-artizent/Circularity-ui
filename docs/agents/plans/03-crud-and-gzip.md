# Plan 3: CRUD for every resource, and gzip, Implementation Plan

> **For agentic workers:** run through `scripts/dev/loop.ps1` (see `loop.md`), one task per iteration.

Gate: tests/test_gzip.py tests/test_resources.py tests/test_actions.py tests/test_mcp_server.py

**Goal:** every entity has a REST resource under `/api/v1/` with list/get/create/update/delete (or an explicit 405 that
says why), all writes go through the action pipeline, and JSON responses are gzip-compressed while streams never are.

**Architecture:** a resource registry (`apps/api/di/resources/`) declares, per resource, its read functions and the action
ids that implement create/update/delete; one generic router builds the endpoints from it. Reads reuse `di/reads` and the
screen helpers; writes call `pipeline.invoke`, so permissions, tenant scope, guards, idempotency and the journal stay in
one place. The actions B17b listed as "not available on the server yet" get handlers here.

**Tech Stack:** FastAPI, Starlette `GZipMiddleware`, SQLAlchemy 2, pytest.

**Spec:** this plan; `docs/BACKEND_STEPS.md` B17b "Still missing on the server".

## Global Constraints

- gzip needs Starlette ≥ 0.46.0 (it skips `text/event-stream` since 0.46.0). fastapi 0.115.6 pins Starlette < 0.42, so
  bump to `fastapi==0.115.14` with `starlette>=0.46,<0.47`; `mcp==2.3.0` and `sse-starlette==3.0.3` must still pass their tests.
- `GZipMiddleware(minimum_size=1000, compresslevel=5)`.
- Resource paths are plural nouns; ids are the domain ids (`RT-1048`, `WF-101`, `oms`, `CF-123`).
- Existing endpoints (`/api/actions/*`, `/api/screens/*`) stay; `/api/v1` is additive.

## Review Focus

1. `GET /api/stream` and `POST /api/ask` with `Accept-Encoding: gzip` → no `content-encoding` header, events arrive unbuffered.
2. A Planner of Customer B lists `/api/v1/cases` → only Customer B cases; `GET /api/v1/cases/RT-1048` → 403 `tenant_boundary`.
3. `DELETE` on a resource that has no delete (cases, journal) → 405 with a JSON reason, not 404.
4. `PATCH` with an unknown field → 422 naming the field; the action is not called.
5. Every write appears in `/api/journal` with the same action id the UI uses.

---

### Task 1: dependency bump and gzip
**Files:** Modify `apps/api/requirements.in` (recompile `requirements.lock`, see docs/agents/scripts.md), `apps/api/di/main.py`. Test: Create `tests/test_gzip.py`.
- [ ] Tests: `/api/screens/reference` with `Accept-Encoding: gzip` → `content-encoding: gzip`; a < 1000-byte answer → not compressed;
  `/api/stream` (read the first event, then close) and `/api/ask` → no `content-encoding`.
- [ ] Fail → bump pins, rebuild the api image, add the middleware → pass; also run `tests/test_mcp*.py` and `tests/test_stream.py`. Commit.

### Task 2: the registry and generic router
**Files:** Create `apps/api/di/resources/__init__.py` (registry), `apps/api/di/resources/router.py`. Test: `tests/test_resources.py`.
**Interfaces:** Produces
`@dataclass Resource(name: str, list: Callable[[CallContext, dict], list[dict]], get: Callable[[CallContext, str], dict | None], create: str | None, update: str | None, delete: str | None, id_field: str = "id", why_not: dict[str, str] = {})`
and `register(r: Resource) -> None`. The router serves `GET /api/v1/{name}` (`?limit&cursor` + resource filters),
`GET /api/v1/{name}/{id}`, `POST`, `PATCH /{id}`, `DELETE /{id}`; a missing action id → 405 `{code:"not_supported", message: why_not[verb]}`.
- [ ] Tests against a test-only registered resource: paging, 404, 405 with reason, 422 on unknown fields, write → `pipeline.invoke` called with the action id.
- [ ] Fail → implement → pass. Commit.

### Task 3: register the resources
One task per group; each adds its registrations and tests (list scoped per account, get, each supported write, 405s):
- [ ] cases (read; update = `decision.*`/`evidence.*` via `PATCH {action, …}`; no create/delete), and `my-tasks` (the user's "Actions on me", read-only)
- [ ] sources (create = `source.connect`, update = `source.update`, delete = `source.delete`; `PATCH {action: sync|pause|resume|reconnect|rotate}`)
- [ ] conflicts (read; `PATCH {action: resolve|escalate}`), instructions (read; `PATCH {action: resend}`)
- [ ] workflows (full CRUD via `workflow.*`), workflow runs (read; create = `workflow.run`)
- [ ] notes, comments, scenarios, requests, mcp-servers (state collections: CRUD via their actions)
- [ ] accounts and identity mappings (Admin; via `access.*`), journal (read only)

### Task 4: the missing write handlers
One task per action, each with tests for allowed, refused, the guard messages (port them from the demo's `fixtures/demo/index.html`
implementation of the same id) and the effect visible in the reads: `source.update`, `source.delete`, `source.reconnect`,
`credentials.rotate`, `source.pause`, `source.resume`, `source.connect` (from the catalogue; `iot` uses
`di.connectors.sync.connect_source`), `import.commit`, `tables.update`, `workflow.saveAsTemplate`,
`workflow.applySuggestedFix`, `workflow.reprocessFailed`, `workflow.setRunSetting`. Then remove the matching
"not available on the server yet" branches in `apps/web/src/api/integration.ts` and `workflows.ts`.
- [ ] Per action: fail → implement → pass → commit. Phase gate after the last one.
