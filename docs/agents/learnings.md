# Learnings

Problems already hit, newest first. Each entry gives the symptom, the root cause, the fix, and how to avoid it.

## 2026-11-20: A request deadlocked itself after a state reset

- **Symptom:** di-api stopped answering. The container showed unhealthy. In Postgres, one session was
  `idle in transaction` (last query `SELECT data FROM state_item WHERE collection = $1`), and others waited on
  `pg_advisory_xact_lock(hashtext($1))`.
- **Cause:** `di/state.py` seeded a collection on its first read inside the caller's transaction, holding the seed
  advisory lock and uncommitted rows. If the same request then opened a second session (`store.ensure`,
  `load_context` …) and read that collection, the second session found it unseeded and waited for the lock its own
  request held. Test resets empty the collections, so the next read reseeds them, which is why it happened under
  tests.
- **Fix:** `_ensure` now seeds in its own short transaction (`engine.begin()`) and commits at once.
- **Avoid:** never hold an advisory lock or uncommitted seed rows in a request that may open another session.
  `bash scripts/dev/unstick.sh` recovers a hung api.

## 2026-11-20: Parallel api test runs on one database

- **Symptom:** bogus failures (163 at one point), hangs, `inbox.get` totals off by one.
- **Cause:** several agents ran pytest at the same time. Each module resets the shared database
  (`tests/starting.py reset()`).
- **Fix:** `scripts/dev/lib.sh api_lock` (flock on `/tmp/di-pytest.lock`). Every dev script that runs api tests takes it.
- **Avoid:** run api tests only through the dev scripts. Restarting the api container also kills any pytest inside it.

## 2026-11-20: IoT telemetry pushed RT-1048's events out of the milestone test

- **Symptom:** `test_milestone_rt1048::test_resend_and_redelivered_events_create_nothing_twice` matched 5 of 6
  completion events.
- **Cause:** the AWS IoT Core mock's topic rules delivered telemetry to the shared outbox every simulated hour, even
  while iot was not provisioned. The test reads the latest 500 outbox events, and the early `sterling.order.allocated`
  fell out.
- **Fix:** the rules start disabled. `connect_source` enables them through EnableTopicRule; `disconnect_source`
  disables them.
- **Avoid:** a mock must not emit events for an integration nobody has connected. Check the outbox mix
  (`/_sim/outbox?limit=5000`) when you add a mock that publishes.

## 2026-11-20: Agents editing the shared dev server

- **Symptom:** blank pages and 404 module errors in other agents' browser checks
  (`missing export Legacy`, `missing export Html`).
- **Cause:** Vite hot-reloads half-finished edits from one agent into everyone's page.
- **Avoid:** give each agent disjoint files. Treat browser failures that appear mid-run as noise and re-run when the
  tree typechecks. The lead re-runs the smoke after merging.

## 2026-11-20: Reporting a subagent's claim without checking it

- **Example:** an agent reported that `escalation.send` had no handler. It has one (`di/actions/decisions.py`).
  Another reported that the "o → r" bug was not in its area; it was in the Command Center's inbox cards.
- **Avoid:** verify claims in the code before passing them on, and run the suites yourself before a commit.

## 2026-11-20: Scratchpad scripts vanished

- **Cause:** the session scratchpad directory was cleared between context windows.
- **Avoid:** keep reusable scripts in `scripts/dev/`.

## 2026-11-20: Starting-state reset script failed

- **Symptom:** `ModuleNotFoundError: No module named 'tests'`.
- **Cause:** `apps/api/scripts/reset_starting.py` imports `tests.starting`.
- **Fix:** run it with `-e PYTHONPATH=/app` (`scripts/dev/reset.sh` does).

## 2026-11-20: The "o → r" approval cards

- **Symptom:** approval card steps read "o → r".
- **Cause:** a step kind string was joined as if it were a list.
- **Fix:** `/api/screens/command/inbox` returns labelled steps (`"<step label> → <system>"`), and the engine branch
  uses the EX_STEP labels.

## 2026-11-19/20: Windows shell pitfalls

- **Quoting:** PowerShell mangles `bash -lc '...'` with inner double quotes, and the pieces get executed as commands.
  Write a `.sh` file and run `wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/.../x.sh`.
- **CRLF:** a `.sh` written with CRLF fails in bash (`$'\r': command not found`, `cd: ...\r`).
  `.gitattributes` forces LF for `*.sh`. `Set-Content` writes CRLF, so use the Write tool.
- **Git Bash:** fails with "fork: Resource temporarily unavailable" (exit 66). Use PowerShell.
- **Commit messages:** PowerShell here-strings broke them. Write the message to a file and use `git commit -F`.
- **Hanging commands:** `cat > /tmp/x` with no stdin hung a call. Avoid commands that wait on input.

## 2026-11-19: Containers don't pick up all changes

- **source-sim:** `--reload` misses edits on `/mnt/c`, so restart it (`scripts/dev/restart.sh source-sim`).
- **Worker:** never reloads; restart it after any change it runs (sync adapters, jobs).
- **Golden files:** read at start-up; restart api and worker after regenerating.

## 2026-11-19: Screen status values unknown to the frontend

- **Symptom:** the Connection Fabric passed through connector states `failing` and `auth_expired`, which the
  frontend didn't know.
- **Fix:** show them as `stale` and keep the real state in `connectorStatus` (`di/screens/integration.py
  SCREEN_STATUS`). The menu's sources-with-issues badge counts them.

## 2026-11-19: Tests that depend on order

- **Cause:** a module-level snapshot of live data (`DB_SOURCES`) was taken at import, so a later sync made it stale.
- **Fix:** a Mapping that re-queries on each access.
- **Avoid:** never snapshot live tables at import time in tests.

## B11–B13: Backend gotchas

- **Multi-statement SQL:** psycopg 3 can't run several statements with parameters in one `execute`. Split them.
- **`store.ensure`:** it committed the caller's transaction; it now uses its own session.
- **sse-starlette:** pinned to 3.0.3 so Starlette stays compatible with FastAPI 0.115, which the `mcp==2.3.0` server needs.

## Editor overwrites

- **Symptom:** an open editor in the IDE reverted edits to README.md and backend-steps.md.
- **Avoid:** re-read a file before editing it if a long time has passed, and check `git diff` before committing.
