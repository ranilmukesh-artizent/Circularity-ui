# Plan 4: async everything Implementation Plan

> **For agentic workers:** run through `scripts/dev/loop.ps1` (see `loop.md`), one task per iteration.

Gate: tests/test_async_db.py tests/test_concurrency.py tests/test_screens_reference.py tests/test_stream.py

**Goal:** the api, the worker and source-sim do database and HTTP I/O asynchronously, end to end, without changing any
answer.

**Architecture:** add an async engine next to the sync one, then move outward-in in three phases. A: every endpoint
becomes `async def` and runs today's sync code through `AsyncSession.run_sync` (one connection, no blocked event loop).
B: convert the I/O-heavy paths natively (screens, actions pipeline, connectors' HTTP, stream, Ask, worker). C: delete
the sync engine except for Alembic, which stays sync on the same `postgresql+psycopg` URL.

**Tech Stack:** SQLAlchemy `[asyncio]` (stay on 2.0.x until a separate upgrade task; 2.1.9 is current), psycopg 3 async,
httpx `AsyncClient`, `pytest-asyncio==1.5.0` (or anyio's plugin), FastAPI.

**Spec:** this plan; research notes in `docs/agents/decision-log.md` (async pitfalls).

## Global Constraints

- `async_sessionmaker(engine, expire_on_commit=False)`; one `AsyncSession` per request or task, never shared across
  `asyncio.gather`; no lazy loading (`lazy="raise"` on relationships).
- The engine is created and disposed in the app lifespan (`await engine.dispose()`); tests use `NullPool` so engines do
  not cross event loops (TestClient runs its own loop).
- LISTEN/NOTIFY stays on a dedicated raw `psycopg.AsyncConnection(autocommit=True)` outside the pool.
- Golden parity: the full api suite must be green after every phase, not only at the end.

## Review Focus

1. A slow request (an `/api/ask` answer) must not delay `/api/health/live` (test: concurrent requests, health < 200 ms).
2. Reading an attribute after commit raises `MissingGreenlet` → prevented by `expire_on_commit=False`; test it.
3. Two concurrent actions on one case → the same outcome as today (row locks `FOR UPDATE` still held across awaits).
4. The worker running N jobs concurrently must not exceed the pool (pool size ≥ worker concurrency + 2).
5. A cancelled client request mid-write → the transaction rolls back, nothing half-written.

---

### Task 1: async engine and session dependency
**Files:** Modify `backend/di/core/db.py`, `requirements.in` + recompiled lock (`SQLAlchemy[asyncio]`, `pytest-asyncio==1.5.0`), `pyproject.toml`
(`asyncio_default_fixture_loop_scope = "function"`). Test: `tests/test_async_db.py`.
**Interfaces:** Produces `async_engine`, `AsyncSessionLocal`, `async def get_async_session() -> AsyncIterator[AsyncSession]`.
- [ ] Tests: a query through `get_async_session`; `expire_on_commit` honoured; `run_sync` executes a sync helper on the same connection. Fail → implement → pass. Commit.

### Task 2 (phase A): every endpoint async
One task per router module (`routers/*`, `screens/*`, `stream.py`, `ask/service.py`, `connectors/webhook.py`, `mcp/server.py`):
change `def` → `async def`, the dependency to `get_async_session`, and wrap today's body in `await session.run_sync(...)`.
- [ ] Per module: its tests green; `tests/test_concurrency.py` (create in the first of these tasks): 20 concurrent screen
  requests plus one `/api/health/live` → health answers < 200 ms. Commit per module. Full suite after the last one.

### Task 3 (phase B): native async in the hot paths
One task each, each with its module tests plus the concurrency test:
- [ ] `di/services/actions/pipeline.py` `invoke` → `async def ainvoke(...)`; `invoke` stays as a sync shim for the worker until Task 4.
- [ ] `di/repositories/*` and `di/services/screens/*` helpers used by the busiest screens (nav, home, command, case) → `async` queries.
- [ ] `di/connectors/http.py` `SourceClient` → `httpx.AsyncClient`; adapters' `call` → `async`.
- [ ] `di/services/ask/` → the Groq async client (`groq.AsyncGroq`); tool calls awaited.
- [ ] `di/services/stream.py` listener → psycopg async `notifies()` generator, no thread.

### Task 4: async worker
**Files:** Modify `backend/di/worker.py`. Test: `tests/test_worker.py`.
`asyncio` loop with `concurrency` (default 4) claimers, `LISTEN di_jobs` wake-up (plan 2), handlers awaited
(`instruction.send`, `workflow.run`, `sync.source`).
- [ ] Tests: 4 jobs run concurrently; a failing job does not stop the others; graceful stop finishes running jobs. Commit.

### Task 5 (phase C): remove the sync engine
- [ ] Delete `engine`/`SessionLocal` uses outside `migrations/` and tests' helpers; Alembic `env.py` keeps a sync engine.
  Full suite + phase gate. Commit.

### Task 6: source-sim
- [ ] Same treatment for `source-sim` (its `sim/core/db.py`, routes, scheduler); its 208 tests stay green. Commit.
