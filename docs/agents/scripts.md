# Scripts

Every script in the repo: what it does and how to run it. Shell scripts are bash: run them in a Linux or macOS
terminal, WSL, or Git Bash on Windows (`scripts/dev` still needs host `flock` and GNU `timeout` until G3, so Linux or
WSL for those). Node scripts run on the host from `apps/web`, unless noted; running the app needs no host Node.

## scripts

| Script | What |
|---|---|
| `doctor.sh` | Read-only check that this machine can run the stack: docker and its daemon, Compose v2 (2.24+ for `docker-compose.prod.yml`), ports 5173/8000/8100/2222/5432 free or used by this project's containers (project = `COMPOSE_PROJECT_NAME` or the folder name), Docker memory (WARN under 4 GB), free disk, CRLF in `*.sh`/`*.py`. One OK/WARN/FAIL line per check; exits 1 on any FAIL. `bash scripts/doctor.sh`. |

## scripts/dev (bash; each resolves the repo root itself)

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

From Windows with Docker in WSL: `wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path>/Circularity-ui/scripts/dev/status.sh`.

## Python dependency locks

`apps/api` and `apps/source-sim` each have `requirements.in` → `requirements.lock` and `requirements-dev.in` →
`requirements-dev.lock` (hashes for every package, transitive included); shared versions are in
`requirements/constraints.txt`. Why and when: [dos-and-donts.md](dos-and-donts.md#dependencies-python).
Re-compile with uv 0.13.5 in a throwaway container (in bash; on this Windows machine put it in a `.sh` file for WSL). Runtime first, then dev (the dev
`.in` reads the runtime lock):

```bash
cd <repo root>      # in WSL: /mnt/c/<path>/Circularity-ui
for svc in api source-sim; do
  for f in requirements requirements-dev; do
    docker run --rm -v "$PWD:/repo" -w "/repo/apps/$svc" --tmpfs /tmp -e UV_NO_CACHE=1 \
      ghcr.io/astral-sh/uv:0.13.5-python3.12-trixie-slim \
      uv pip compile -q "$f.in" -o "$f.lock" --generate-hashes \
        --python-version 3.12 --python-platform x86_64-unknown-linux-gnu \
        --custom-compile-command "docs/agents/scripts.md (Python dependency locks)"
  done
done
```

Check a lock installs cleanly without touching the stack:
`docker run --rm -v "$PWD:/repo:ro" -w /repo/apps/<svc> python:3.12-slim sh -c 'pip install -q --require-hashes --no-deps -r requirements.lock -r requirements-dev.lock && pip check'`.
The images install the same way (`apps/*/Dockerfile`); rebuild after a lock change.

Images (`apps/*/Dockerfile`): base images pinned by digest; target `dev` is what `docker-compose.yml` builds
(bind mounts, reload, dev lock, tests); target `runtime` has no dev tools, tests or scripts and runs as a non-root user
(api/source-sim uid 10001). The web app's runtime image is a separate file, `apps/web/Dockerfile.runtime`, built from
the repo root (root `.dockerignore` allows only `apps/web` and `fixtures/demo`): it runs `extract-styles.mjs` and
`vite build` itself, then serves `dist` from nginx-unprivileged on 8080 with a CSP
(`apps/web/nginx/default.conf.template`). `apps/web/Dockerfile` keeps only the dev target with context `apps/web`; the
classic builder builds every stage before the target, so one file cannot serve both contexts. Some Docker installs
(e.g. Ubuntu's `docker.io` in WSL) have no buildx, so the classic builder runs them; keep the Dockerfiles free of
BuildKit-only syntax. Run the runtime images with
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` (opt-in; no host Node needed), or build
the web one alone: `docker build -f apps/web/Dockerfile.runtime -t circularity-ui-web:runtime .`. To bump a base image, take a tag at least two weeks old and its index
digest from Docker Hub (`https://hub.docker.com/v2/repositories/library/<image>/tags?name=<tag>`).

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
