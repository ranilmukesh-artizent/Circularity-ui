# Learnings

Problems already hit, newest first. Each entry gives the symptom, the root cause, the fix, and how to avoid it.

## 2026-11-22: The dev api hung on reload while a browser was open

- **Symptom:** after a code change the dev api stopped answering for minutes; its log ended with uvicorn's "Waiting
  for connections to close".
- **Cause:** `uvicorn --reload` waits for every open connection to close before it restarts, and the browser's live
  stream (SSE) never closes by itself.
- **Fix:** the dev api's command adds `--timeout-graceful-shutdown 3` (`docker-compose.yml`, `29704d4`): uvicorn
  0.34.0 cancels the open connections after 3 s ("timeout graceful shutdown exceeded") and the api answers again about
  15 s after the change, start-up included. Production (no `--reload`) is unchanged.
- **Avoid:** a change to a service's `command` (or its environment) reaches the container only when it is recreated:
  `docker compose up -d api`. `docker compose restart` and `scripts/dev/restart.sh` keep the old command.

## 2026-11-21: Commits from inside WSL had author `root`

- **Symptom:** plan-6 commits made by agents showed `root <root@…>` as author in `git log`.
- **Cause:** they ran `git commit` inside WSL as `-u root`, where git uses root's identity, not the Windows user's.
- **Fix:** a rebase that reset the author on those commits, before the push (unpushed, so no force-push).
- **Avoid:** run git from PowerShell on Windows (CLAUDE.md); use WSL only for `bash scripts/dev/*.sh`. Check
  `git log --format="%h %an %s"` before a push.

## 2026-11-21: PowerShell `Set-Content` mangled UTF-8 docs

- **Symptom:** a file edited with `Get-Content … | Set-Content` gained a byte-order mark and its non-ASCII characters
  (`…`, `→`, `·`, `•`) turned into mojibake; one earlier commit subject (`25954ea`) starts with a stray BOM.
- **Cause:** Windows PowerShell 5.1 reads files without a BOM as the ANSI code page and `Set-Content -Encoding utf8`
  writes a BOM.
- **Fix:** restore the file from git (`git show HEAD:<path>`) and redo the change.
- **Avoid:** edit with the Edit tool, or `sed` in WSL; never round-trip a repo file through `Set-Content`/`Out-File`.

## 2026-11-21: A rotated junk secret broke the live-check replay

- **Symptom:** workflow check tests that replay the demo's checks failed after other tests: the checks warned about a
  demo source (proc) being `auth_expired`.
- **Cause:** a test rotated a junk secret on a demo source; the next sync got a 401 and set the source
  `auth_expired`. The demo reset put back credentials but not connector-set statuses, and plan 6 made the workflow
  checks read the live source state (`di/workflow/live.py`).
- **Fix:** `reset_sources` (`di/connectors/sync.py`) returns demo sources left `failing` or `auth_expired` to their
  starting status and clears their retry schedule (`8b0417c`).
- **Avoid:** a test that breaks a demo source must restore it, and the reset must undo every state a sync can set.

## 2026-11-21: Shared-index commits swept other agents' hunks

- **Symptom:** commits that held another agent's unfinished lines (`86aaa12` took back an A3 line committed with A6)
  or that dropped a just-committed change (`0511bbc` put back A7's `webhook_event` model that the A2 commit's
  `models.py`, staged from an older HEAD, had removed).
- **Cause:** all agents share one working tree and one index. `git commit -- <path>` commits the whole working-tree
  file, so it takes every agent's hunks in it; a file staged from an old HEAD drops what landed since.
- **Fix:** stage only your own hunks (`git apply --cached` of a patch filtered to them, or `git update-index
  --cacheinfo` with a blob of HEAD plus your hunks) and commit the index without paths (a path list would take the
  working-tree file again), or leave a shared file to the lead, who commits it once all its hunks are done
  (`8ee1d29`, `8b0417c`). A file only you changed can still go by `git commit -- <path>`.
- **Avoid:** before a commit, `git diff --cached --stat` must list only your files and `git diff --cached <file>`
  only your hunks, staged on the current HEAD.

## 2026-11-21: The 2-minute window in `run_active`

- **Symptom:** reading the query, a workflow run longer than 2 minutes seems to stop counting as active, so the
  reaper or a second Run now would close or double it.
- **Cause / design:** `run_active` (`di/actions/workflows.py`) counts a `job` row in `running` only while
  `locked_at` is under 2 minutes old: that covers a claimed job that is still starting. A run past its start is seen
  by its advisory lock (`RUN_LOCK`, `hashtext('wf:'||id)`), which the job holds on its own connection for the whole
  run and loses when its worker dies.
- **Avoid:** never extend the 2-minute window to cover long runs; a run that holds no lock and has no fresh job is
  lost and `reap_lost_run` closes it ("worker lost").

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
- **Fix:** `scripts/dev/lib.sh api_lock` (flock on `/tmp/di-pytest.lock`; since G3 inside the api container, so it needs no host
  `flock` and works on macOS and Git Bash). Every dev script that runs api tests takes it.
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
