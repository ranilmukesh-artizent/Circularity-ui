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
- **Don't** give agents (MCP tools, Ask) a write that skips a person. They may read, request evidence, or hold for
  approval. `di/mcp` refuses to start if a forbidden action is mapped.
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
- **Do** await `invoke()`. It is async in both modes.
- **Don't** build HTML strings for `dangerouslySetInnerHTML`. Render React, and keep the demo's CSS classes.
- **Don't** redesign pages while switching data sources. A UI redesign is planned separately.

## Tests

- **Do** run api tests through `scripts/dev/api-test.sh` or `scripts/dev/full-suite.sh`. They hold the flock, so
  only one api pytest runs at a time.
- **Don't** run the full api suite from several agents at once. It deadlocked the shared database twice.
- **Do** run `bash scripts/dev/reset.sh` after the full suite or after clicking writes in the browser.
- **Do** keep browser checks read-only on the shared stack unless you own the stack. To test a write, reset afterwards.
- **Do** run the browser smoke in both modes for all 11 accounts after any frontend change that touches routing,
  the facade or the shell.

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
- **Don't** publish to GitHub Pages; it isn't needed.
- **Don't** imply a named vendor product is connected. Mocks are synthetic, and docs and UI must say so where it matters.
- **Don't** run formatters over the whole tree. Format only the files you changed.

## Shell on this machine (Windows + WSL)

This machine runs Docker inside WSL. The repo itself needs only Git and Docker (README, "Start it"); on Linux, macOS or
Docker Desktop run the same commands in a terminal, without `wsl ...`.

- **Do** put commands in a `.sh` file (LF endings) and run it with
  `wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/.../file.sh`. Inline `bash -lc '...'` with nested quotes breaks in PowerShell.
- **Don't** rely on Git Bash. It fails to fork here (exit 66, "Resource temporarily unavailable").
- **Do** keep scripts you want to reuse in `scripts/dev/`. The session scratchpad gets wiped.
- **Don't** pipe a command that waits on stdin (for example `cat > file` with no input). It hangs the tool call.
