# Scripts

Every script in the repo: what it does and how to run it. Shell scripts run inside WSL. Node scripts run on the host
from `apps/web`, unless noted.

## scripts/dev (bash, WSL; each resolves the repo root itself)

| Script | What |
|---|---|
| `lib.sh` | Sourced by the others. `cd`s to the repo root; `api_lock` (flock `/tmp/di-pytest.lock`); `wait_healthy` (api :8000 and source-sim :8100). |
| `api-test.sh <pytest args>` | Selected api tests behind the lock, `-x`, last 40 lines. |
| `full-suite.sh [pytest args]` | Stops the worker, resets source-sim, runs the whole api suite (~25 min) and the source-sim suite, prints failures and summaries. Holds the lock. Follow with `reset.sh`. |
| `web-check.sh [tsc]` | `tsc --noEmit` in the web container, then vitest. With `tsc`, the typecheck only. |
| `restart.sh [services]` | Restarts api, worker and source-sim (or the ones given) and waits for health. |
| `reset.sh` | Demo starting state: source-sim reset, `scripts/reset_starting.py` (with `PYTHONPATH=/app`), worker started. |
| `unstick.sh` | Lists non-idle db sessions, terminates sessions idle in a transaction for over 1 min, restarts the api. Use when the api hangs. |
| `selftest.sh` | Proves the scripts report failures through their exit status (a passing and a missing test, a planted type error). Every script exits non-zero on failure; `lib.sh` sets `pipefail` and offers `filtered PATTERN N cmd…`. |
| `wait-idle.sh [max_s]` | Waits until the worker has no due jobs (after a reset it syncs every source first, ~2–3 min). Use before `smoke-rt1048.mjs`. |
| `status.sh` | Health of api and source-sim, container status, api tests running or waiting for the lock, non-idle db sessions. |

From Windows: `wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path>/Circularity-ui/scripts/dev/status.sh`.

## apps/api/scripts (run inside the api container)

| Script | What |
|---|---|
| `reset_starting.py` | Puts di back to the starting state (cases, workspace collections, delegations, grants; journal and instructions cleared; connector data kept). `docker compose exec -T -e PYTHONPATH=/app api python scripts/reset_starting.py`. |
| `full_sync.py` | Syncs every source once, in full, and prints records, facts, failures and open conflicts by field. `docker compose exec -T api python scripts/full_sync.py`. |

## apps/web/scripts (Node)

| Script | What |
|---|---|
| `extract-styles.mjs [--force]` | Copies the demo's stylesheet into `src/styles/legacy.gen.css` and the product photos into `public/assets/products/`. Runs before `npm run dev/build/test`. |
| `dump-assets.mjs` | Writes `src/ui/assets.gen.ts` (logos, icons, vendor logos and their rules) from the demo run headless. Committed; rerun only when the demo's assets change. `npm run assets`. |
| `dump-golden.mjs` | Writes the base golden files (`fixtures/golden/*.json`) from the demo. `npm run golden`. |
| `golden-sandbox.mjs` | Shared headless sandbox for the golden scripts (`freshDemo`, `plain`, `writeGolden`). |
| `golden/<area>.mjs` | Per-area golden files: `analytics_audit` (screens reference, analytics, audit, nav, checks), `ask`, `fabric` (screens integration, mcp, access, workflows), `home_command` (home, command), `mcp_calls` (mcp.json), `product_case` (product, case, orchestration), `workflow_writes`. See `golden/README.md`. |
| `smoke-pages.mjs`, `smoke-signin.mjs`, `smoke-ask.mjs`, `smoke-approve.mjs`, `smoke-rt1048.mjs` | Browser smoke checks with Chrome: see [testing.md](testing.md#browser-smoke-scripts-appswebscripts). |

## npm scripts (apps/web/package.json)

| Script | Runs |
|---|---|
| `dev` | `predev` (extract-styles), then `vite --host 0.0.0.0`. |
| `build` | `prebuild` (extract-styles), then `tsc --noEmit && vite build`. |
| `test` | `pretest` (extract-styles), then `vitest run`. |
| `typecheck` | `tsc --noEmit`. |
| `assets` | `dump-assets.mjs`. |
| `golden` | `dump-golden.mjs`. |

## Useful one-offs (source-sim control API, :8100)

| Endpoint | What |
|---|---|
| `POST /_sim/reset` | Reset every mock to its seed (`?system=<id>` for one). |
| `GET /_sim/outbox?limit=N` | The latest events the mocks emitted. |
| `POST /_sim/clock/advance` | Advance the simulated clock; body `{"hours": n}`. |
| `DELETE /_sim/faults?system=<id>` | Clear injected faults. |

## di-api endpoints for operators

| Endpoint | What |
|---|---|
| `POST /api/sources/iot/connect` | Connect AWS IoT Core (Admin or Developer). It goes live, its topic rules are enabled, and a full sync is queued. |
| `POST /api/sources/iot/disconnect[?purge=true]` | Back to not provisioned. With `purge`, everything it synced is removed. |
| `GET /api/health` | Health. |
| `http://localhost:8000/docs` | OpenAPI for the whole api. |
