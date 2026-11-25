# Dos and don'ts

For coding agents. Each rule names the reason or the incident behind it; see [learnings.md](learnings.md).

## Parity and data

- **Do** treat `fixtures/demo/index.html` as the reference for behaviour, numbers and texts. A difference from the demo is a bug
  unless [decision-log.md](decision-log.md) records it.
- **Do** reproduce JS arithmetic exactly in Python: use `di.services.engine.jsmath` (`js_round`, `js_sum`) and the seeded
  mulberry32 draws the demo uses. Python's `round` and `sum` differ from JavaScript's.
- **Don't** hand-edit `fixtures/golden/*`. Change `fixtures/demo/index.html` or the dump script, regenerate, then prove the diff is
  only what you meant ([testing.md](testing.md#regenerating-golden-files)).
- **Don't** compare values the demo draws unseeded (some run durations, record counts, random ages). The tests list
  such exclusions with the reason; add yours the same way.
- **Do** keep real connector data out of parity comparisons. The Connection Fabric shows real sync data (428 open
  conflicts after a full sync, not the demo's 3); test those screens for shape and invariants.

## Backend

- **Do** route every write through `di.services.actions.pipeline.invoke` (journal, idempotency key, sequence, permissions,
  tenant and warehouse scope). No direct table writes from routers.
- **Do** enforce access on the server. The frontend's `can`/`canPage`/`canRoute` only shape the display.
- **Don't** give agents (MCP tools, Ask, playbooks) a write that skips a person. They may read, request evidence, or
  hold for approval. `FORBIDDEN_ACTIONS` lives in `di/services/agents/forbidden.py`: the pipeline refuses those
  non-read actions for any agent-prepared call (audit F4), the catalogue marks them not `agent_allowed`, and `di/mcp`
  refuses to start if one is mapped. **Do** add a new person-only action there in the same commit.
- **Do** make a tenant check consider every kind of caller: tenant-scoped people, accounts that see every tenant
  (Approver, Admin) and group units such as `workspace`. The F8 fix first refused the Approver the group's pilot
  report; only the full suite caught it (`8fea98c`).
- **Don't** renumber a migration that a shared database (the dev stack, a colleague's) has already run. Alembic
  stores only the revision id, so the other file of that number is skipped. If you must, say in the commit which
  databases need `alembic downgrade <previous>` with the OLD code first ([learnings](learnings.md)).
- **Do** use `di.core.state` for workspace collections (events, notes, requests, workflows …). Never seed a collection
  inside the caller's transaction (see the deadlock in learnings).
- **Don't** open a second database session inside a request that holds locks it needs, unless that session only
  reads committed data.
- **Do** use `ActionError(code, message, extra)` codes the frontend knows: `validation_error`, `out_of_scope`,
  `tenant_boundary`, `approval_required`, `limit_exceeded`, `not_found`, `conflict`, `duplicate`.
- **Do** restart the worker after changing anything it runs (`bash scripts/dev/restart.sh worker`). It never reloads.
- **Do** restart source-sim after changing it. `--reload` often misses edits on `/mnt/c`.
- **Do** restart api and worker after regenerating golden files; they are read at start-up.

## Frontend

- **Do** keep pages calling only `frontend/src/api/*.ts`. Signatures stay stable; the facade adapts endpoint shapes
  (ids instead of embedded objects, ISO timestamps).
- **Do** read through `cached(path)` / `cachedAction(id, input)` in api mode and pass view settings as query
  parameters (`withQuery`), so the cache key changes when they change.
- **Don't** call `engine()` in an api branch. Static lists come from `ref(name)`, the session from `session()`,
  and browser-only settings from `view()`/`setView()`.
- **Do** await `invoke()`. It is async (an HTTP call to di-api).
- **Don't** build HTML strings for `dangerouslySetInnerHTML`. Render React, and keep the demo's CSS classes.
- **Don't** redesign pages while switching data sources. A UI redesign is planned separately.

## Tests

- **Do** check a long run (full suite, parallel shards, smokes, a gate) at least every 5 minutes and report counts so
  far. A log that has not grown for 5 minutes is hung: look in `pg_stat_activity` on its database for a session
  `idle in transaction` and end it with `pg_terminate_backend` (26 Nov 2026: shard 3 sat 75 minutes behind one).
- **Do** run api tests through `scripts/dev/api-test.sh` or `scripts/dev/full-suite.sh`. They hold the flock, so
  only one api pytest runs at a time.
- **Don't** run the full api suite from several agents at once. It deadlocked the shared database twice.
- **Do** run api tests side by side only on private databases (`scripts/dev/parallel-suite.sh`). It is a pre-check;
  the serial `full-suite.sh` stays the gate.
- **Don't** call a failure that shows only on a fresh database a regression until the base commit's code fails or
  passes the same way on a fresh database. Some files need the stack's synced fabric.
- **Do** run `bash scripts/dev/reset.sh` after the full suite or after clicking writes in the browser.
- **Do** keep browser checks read-only on the shared stack unless you own the stack. To test a write, reset afterwards.
- **Do** run `smoke-pages.mjs` for all 11 accounts after any frontend change that touches routing, the facade or
  the shell (there is one mode since B17c).
- **Do** size checks to the step (plan 9 run, 25 Nov 2026). After each merged task: the task's own tests, its
  serial-only files, the golden and parity tests, `lint.sh`, `web-check.sh` (`scripts/dev/lead-verify.sh`, about 3 to
  5 minutes). The full api suite (`parallel-suite.sh`, 8 to 12 minutes and several GB of Docker memory) and the
  browser smokes run at phase gates and every few merges. **Don't** run the full suite after every merge: in plan 9's
  first night that cost 15 to 20 minutes per merge, about 8 to 10 hours in all, with writers idle behind it.
- **Do** run `scripts/dev/wait-idle.sh` after `reset.sh` before any browser smoke. The reset re-syncs every mock
  source (2 to 3 minutes) and instructions queue behind it; RT-1048 times out without the wait.
- **Do** add every new table that holds demo state to `backend/tests/starting.py` `reset()` in the same task, or the
  next reset keeps the old rows (plan 9: pack versions, overlays and work items survived resets until P9-1.14).

## Dependencies (Python)

- **Do** add or bump a dependency in the `.in` file, never in a `.lock`: `backend/requirements.in` or `source-sim/requirements.in` (runtime) or
  `requirements-dev.in` (pytest, ruff). Versions both services share (fastapi, uvicorn, SQLAlchemy, psycopg,
  pydantic-settings, httpx, pytest, ruff) live in `requirements/constraints.txt`; bump them there so both move.
- **Do** re-compile both locks of every service you touched (shared bump: both services) with the uv command in
  [scripts.md](scripts.md#python-dependency-locks), check that the lock diff holds only the change you meant, then
  rebuild the image (`docker compose up -d --build <svc>`; the worker shares the api image).
- **Don't** `pip install` into a running container to try something. The images install only the locks
  (`--require-hashes --no-deps`), and the next rebuild silently drops anything else.
- **Don't** pass `--upgrade` to the compile unless upgrading is the step. Without it, uv keeps every version the lock
  already has and moves only what the `.in` change forces.

## Git, secrets, scope

- **Don't** commit `.env`, `.vscode/`, `settings.local.json`, keys or tokens. Before committing, run
  `git diff --cached | Select-String -Pattern 'gsk_[A-Za-z0-9]{20,}'` and expect no match. (The bare prefix also
  matches these docs, so scan for the key's shape, and read the scan's result before you commit, not after.)
- **Do** stage explicit paths, never `git add -A`. Other agents' work may be in the tree.
- **Do** commit and push only when the user asks: one step per commit on `feature/fullstack-poc`, then a short report.
- **Do** `git fetch` and read `git log HEAD..origin/feature/fullstack-poc` before starting big work. A colleague may
  have pushed the same screens; on 24 Nov the gaps work and the audit fixes both built proposals, models, pilot, pack, rename and
  request-access screens.
- **Do** keep one version when two people built the same screen: take the one already on origin, add yours only
  where it has nothing, and delete your duplicate readers and fields (record what was dropped, as in the
  [plan-8 merge record](audits/2026-11-24-plan-08/README.md#merge-record)).
- **Don't** publish to GitHub Pages; it isn't needed.
- **Don't** imply a named vendor product is connected. Mocks are synthetic, and docs and UI must say so where it matters.
- **Don't** run formatters over the whole tree. Format only the files you changed.

## Shell on this machine (Windows + Docker Desktop)

This machine runs Docker Desktop, so `docker` works from PowerShell and Git Bash. The repo itself needs only Git and
Docker (README, "Start it"); on Linux or macOS run the same commands in a terminal. Where Docker runs inside WSL
instead, run each `.sh` file with `wsl -d <distro> -u root -- bash /mnt/c/.../file.sh`.

- **Do** put commands in a `.sh` file (LF endings) and run it with bash. Inline `bash -lc '...'` with nested quotes
  breaks in PowerShell.
- **Do** `export MSYS_NO_PATHCONV=1` in Git Bash before passing a container path (`/tmp/...`); give docker calls in a
  loop `</dev/null`; strip CRs with `tr -d '\r'`. Details in CLAUDE.md, "Git Bash pitfalls".
- **Don't** count on Git Bash for git. It sometimes fails to fork (exit 66, "Resource temporarily unavailable"); use
  PowerShell for git.
- **Do** keep scripts you want to reuse in `scripts/dev/`. The session scratchpad gets wiped.
- **Don't** pipe a command that waits on stdin (for example `cat > file` with no input). It hangs the tool call.
