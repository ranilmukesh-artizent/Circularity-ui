# Plan 2: the job queue and task CRUD Implementation Plan

> **For agentic workers:** run through `scripts/dev/loop.ps1` (see `loop.md`), one task per iteration.

Gate: tests/test_jobs.py tests/test_worker.py tests/test_tasks_api.py

**Goal:** a hardened Postgres job queue (priorities, delayed runs, dead letters, stale-lock recovery, instant wake-up)
and CRUD over it at `/api/v1/tasks`.

**Architecture:** keep the hand-rolled queue (`backend/di/core/jobs.py`, table `job`, worker `di/worker.py`); the research
(20 Nov 2026) found no library worth a second schema owner for this POC (procrastinate 3.12, pgqueuer 2.0 considered).
Add columns and a trigger with an Alembic migration, a `NOTIFY di_jobs` wake-up the worker listens to (polling stays as
the fallback), and a router over the same functions.

**Tech Stack:** SQLAlchemy 2, psycopg 3, Alembic, FastAPI, pytest.

**Spec:** this plan; `docs/agents/decision-log.md` (D6: no Redis).

## Global Constraints

- "Task" here means a background job. The user's to-do items ("Actions on me") are served read-only in plan 3.
- Existing job kinds (`sync.source`, `instruction.send`, `workflow.run`, …) keep working unchanged; default priority 100.
- Task CRUD is Admin and Developer only (`manageIntegrations` or `all`); other accounts get 403 `out_of_scope`.

## Review Focus

1. Two workers claim at once → each job runs once (test with two threads calling `claim`).
2. A worker dies mid-job → after `stale_after` the reaper requeues it; after `max_attempts` it is `dead`, not lost.
3. Cancelling a running job → refused with 409; only `queued` jobs can be cancelled.
4. Retrying a `dead` job → back to `queued` with `attempts` reset and `last_error` kept in `history`.
5. Enqueue with the same `dedupe_key` twice while the first is queued → one job (unique partial index).

---

### Task 1: schema
**Files:** Create `backend/migrations/versions/0018_job_queue.py`; Modify `backend/di/models/` (`Job`). Test: `tests/test_jobs.py`.
Columns: `priority int not null default 100`, `max_attempts int not null default 5`, `heartbeat_at timestamptz`,
`dedupe_key text`, `history jsonb not null default '[]'`; status adds `dead`, `cancelled`; partial unique index on
`dedupe_key where status in ('queued','running')`; index `(status, priority, run_after, id)`; trigger
`AFTER INSERT ... EXECUTE pg_notify('di_jobs', NEW.kind)`.
- [x] Test: migration up/down round-trips; inserting two queued jobs with one `dedupe_key` raises `IntegrityError`. Fails → implement → passes. Commit.

### Task 2: queue functions
**Files:** Modify `backend/di/core/jobs.py`. Test: `tests/test_jobs.py`.
**Interfaces:** Produces
`enqueue(session, kind: str, payload: dict | None = None, *, priority: int = 100, run_after: datetime | None = None, max_attempts: int = 5, dedupe_key: str | None = None) -> Job`
(returns the existing queued job on a dedupe hit); `claim(session) -> ClaimedJob | None` ordered by `priority, run_after, id`;
`heartbeat(session, job_id: int) -> None`; `fail(...)` marks `dead` at `max_attempts` and appends `{at, error}` to `history`;
`reap_stale(session, stale_after: timedelta = timedelta(minutes=5)) -> int`; `cancel(session, job_id) -> bool`;
`retry(session, job_id) -> bool`.
- [x] Tests (one each): priority order; delayed `run_after` not claimed early; dead after `max_attempts`; reaper requeues a
  running job whose `heartbeat_at` is older than `stale_after`; two concurrent claimers never get the same id; dedupe hit.
- [x] Fail → implement → pass. Commit.

### Task 3: worker wake-up and heartbeats
**Files:** Modify `backend/di/worker.py`. Test: Create `tests/test_worker.py`.
The worker `LISTEN di_jobs` on a dedicated psycopg connection (autocommit) and wakes on a notification or after
`poll` seconds; it heartbeats long jobs every 30 s from a thread; `periodic()` calls `reap_stale`.
- [x] Test: a job enqueued while the worker waits is picked up in < 1 s (worker loop run in a thread with `poll=30`). Fails → implement → passes. Commit.

### Task 4: task CRUD
**Files:** Create `backend/di/routes/tasks.py`; Modify `backend/di/main.py`. Test: Create `tests/test_tasks_api.py`.
**Interfaces:** `GET /api/v1/tasks?status=&kind=&limit=50&cursor=` → `{items: [Task], next_cursor}`; `GET /api/v1/tasks/{id}`;
`POST /api/v1/tasks` `{kind, payload, priority?, run_after?, dedupe_key?}` (kind must be a registered `HANDLERS` key) → 201;
`PATCH /api/v1/tasks/{id}` `{action: "retry"|"cancel"|"reprioritise", priority?}`; `DELETE /api/v1/tasks/{id}` = cancel.
`Task` = `{id, kind, payload, status, priority, attempts, max_attempts, run_after, last_error, history, created_at, updated_at}`.
Every write is journalled through the action pipeline (`task.enqueue`, `task.retry`, `task.cancel`, `task.reprioritise`
registered in `di/services/actions/`), so audit and permissions stay in one place.
- [x] Tests: 403 for planner-a; unknown kind → 422; cancel running → 409; retry dead → queued; list paging; journal row per write.
- [x] Fail → implement → pass. Phase gate (`loop.md`). Commit.
