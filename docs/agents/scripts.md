# Scripts

Every script in the repo: what it does and how to run it. Shell scripts are bash (3.2 or later): run them from the
repo root in a Linux or macOS terminal (macOS's stock bash and BSD tools are enough), WSL, or Git Bash on Windows.
`scripts/dev` needs only `docker` (Compose v2) and `curl` on the host: the test lock, `timeout`, `psql`, `python` and
`node` run inside the containers. Node scripts run on the host from `frontend`, unless noted; running the app needs no
host Node. Lint the shell scripts with shellcheck (`.shellcheckrc` at the root):
`docker run --rm -v "$PWD:/mnt:ro" -w /mnt koalaman/shellcheck:v0.11.0 -x -s bash scripts/dev/*.sh scripts/doctor.sh`.

## scripts

| Script | What |
|---|---|
| `doctor.sh` | Read-only check that this machine can run the stack: docker and its daemon, Compose v2 (2.24+ for `docker-compose.prod.yml`), the host ports (`WEB_PORT` 5173, `API_PORT` 8000, `SIM_PORT` 8100, `SFTP_PORT` 2222, `POSTGRES_PORT` 5432, from env or `.env`) free or used by this project's containers (project = `COMPOSE_PROJECT_NAME` or the folder name), Docker memory (WARN under 4 GB), free disk, CRLF in `*.sh`/`*.py`. One OK/WARN/FAIL line per check; exits 1 on any FAIL. `bash scripts/doctor.sh`. |

## scripts/dev (bash; each resolves the repo root itself)

| Script | What |
|---|---|
| `lib.sh` | Sourced by the others. `cd`s to the repo root; `api_url`/`sim_url` (the host ports Compose published, else `API_PORT`/`SIM_PORT`, else 8000/8100); `api_lock` (a flock on `/tmp/di-pytest.lock` inside the api container, held by a `flock … cat` there whose stdin is a pipe from the script: it is released when the script exits or is killed; exits 1 if the api container is not running); `wait_healthy` (api and source-sim health). |
| `api-test.sh <pytest args>` | Selected api tests behind the lock, `-x` (`API_TEST_NO_X=1` drops it and runs every test), last 40 lines, `timeout 1800` in the container. Stops the worker for the run and starts it on exit. |
| `evals-live.sh` | Plan 9 P9-2.15, by hand or nightly, never part of the gate: the agent eval datasets of `backend/tests/evals` (chain, configuration agent, injection corpus) against each enabled real model, behind the api test lock with the worker stopped. Writes `eval_score`, `eval_prev` and `eval_at` to `llm_model` (the router drops a model from a role when the score fell more than 10 points) and prints each model's scores. The key comes only from the container's environment (never printed, `.env` never read); without one it exits 1. |
| `full-suite.sh [pytest args]` | Stops the worker, resets source-sim, runs the whole api suite (~32 min, 4,460 tests on 24 Nov 2026; the script's header still says 16–25 min) and the source-sim suite, prints failures and summaries. Holds the lock. Follow with `reset.sh`. The gate before a commit. |
| `parallel-suite.sh [--list]` | A pre-check, not the gate: the api test files that are safe side by side in `N` shards (default 4) at once, each in `docker compose run --rm --no-deps api` on its own database `di_par1..N` on the stack's postgres (dropped and created, `alembic upgrade head`, `ensure_sources` as the worker does, then pytest). ~7-11 min with 4 shards. Leaves out (serial-only, 38 files on 24 Nov) the files that reset or fault the shared source-sim, call the running api (MCP, stream, webhooks, health) or need a fabric the stack has synced. Does not touch the main database or the lock, so it may run beside other work, but not beside `full-suite.sh` (shared source-sim). `--list` prints the shards and the serial-only files and runs nothing. Logs in `OUT` (default `test-results/parallel/shard-<k>.log`); `KEEP=1` keeps the databases. Exits 0 only if every shard passed. Sets `MSYS_NO_PATHCONV=1` itself. |
| `test-times.txt` | Seconds per api test file from a full serial run; `parallel-suite.sh` balances its shards with it (a file not listed counts as 30 s). Regenerate after big changes: run `MSYS_NO_PATHCONV=1 bash scripts/dev/full-suite.sh --junitxml=/tmp/api-junit.xml` (the junit is written inside the api container), then replace the lines below the two `#` header lines with the output of `docker compose exec -T api python -c "import collections as C,xml.etree.ElementTree as E;t=C.Counter();[t.update({'tests/'+c.get('classname').split('.')[1]+'.py':float(c.get('time'))}) for c in E.parse('/tmp/api-junit.xml').iter('testcase')];print('\n'.join(f'{round(v)} {k}' for k,v in t.most_common()))"` (sums each file's test times, slowest first). Run on the 24 Nov junit, it reproduces the committed file exactly. |
| `wt-check.sh <k> [test files…]` | Plan 9's unattended run: a writer's checks from its own git worktree root. pytest on its own database `di_w<k>` (dropped and created, migrated, `ensure_sources`), then ruff, ruff format, mypy and lint-imports, then tsc, vitest and eslint when `frontend/` differs from `feature/plan-09-recover` (`WT_BASE`) (`WT_WEB=1` forces, `0` skips; `WT_LINT=0` skips lint). Each step is `docker compose -p circularity-ui run --rm --no-deps` with the worktree's code mounted, so the main database, lock and tree are untouched. Refuses (exit 3) test files that call `/_sim/` or faults: the lead runs those after the merge through `api-test.sh`. Exits 0 only if every step passed. |
| `plan-next.py [--max N \| --status \| --simulate W [--fast]]` | Host Python. Plan 9's scheduler for the lead: prints the tasks that may start now (dependencies and prerequisite phases done, no earlier unticked or in-flight task on the same logic files; barrier tasks alone), reading the plan's boxes and `docs/agents/plans/09-run/inflight.txt` and `blocked.txt`. `--status` counts per phase; `--simulate` estimates the wall-clock hours of the whole plan with W writers. |
| `plan-tick.py <task> <sha> "<checks>" "<note>"` | Host Python. Plan 9 lead helper after a verified merge: ticks the task's box, adds its progress row (to `<run folder>/PROGRESS.md` for a lane, else `docs/agents/plans/PROGRESS.md`), clears it from `inflight.txt`, logs it, and writes the commit message (`<run folder>/.commit-msg.txt`, git-ignored). `PLAN_RUN` names the run folder. Fails closed: refuses a writer commit whose subject is over 72 characters or has no blank line after it. |
| `lead-verify.sh [--suite] [--smoke] [tests…]` | Plan 9 lead's checks after cherry-picking a task: `migrate-reapply.sh 0028`, `restart.sh`, the given test files through `api-test.sh`, `lint.sh`, `web-check.sh`; `--suite` adds `parallel-suite.sh` (N=3), `--smoke` adds smoke-pages for the 11 accounts after `reset.sh` and `wait-idle.sh`. One line per step; exits 0 only if all passed. |
| `web-check.sh [tsc]` | `tsc -b` (app and Node configs, tsconfig.app.json + tsconfig.node.json) in the web container, then vitest. With `tsc`, the typecheck only. |
| `lint.sh` | In the api container `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`; in the web container `npx eslint .` and `npx knip`. Runs every check, prints one ok/FAIL line each (with the last 8 lines of a failing one; at most 60 lines in all) and exits non-zero if any failed. |
| `suite-shard.sh <n> <m> [--list] \| sim` | Serial, on the main database (for parallel shards see `parallel-suite.sh`): every m-th file of the sorted `tests/test_*.py` (listed in the api container), starting at the n-th (1-based), through `api-test.sh` with `API_TEST_NO_X=1`; `--list` only prints the shard's files. `sim` runs the source-sim suite (`pytest -q` in its container). Exits 2 on bad arguments. |
| `gate-mvp.sh [test files]` | Plan 08's per-task gate: `lint.sh`, then `api-test.sh <files>` (if any), then `web-check.sh` if `git diff --name-only HEAD` or an untracked file touches `frontend/`, then the secret scan (no `gsk_` key-shaped string in `git diff HEAD`; the match is never printed). Runs every step, prints a summary, exits 0 only if all pass. `GATE_LINT`, `GATE_API`, `GATE_WEB` replace the three commands (e.g. `true`/`false` in `selftest.sh`). |
| `restart.sh [services]` | Restarts api, worker and source-sim (or the ones given) and waits for health. |
| `reset.sh` | Demo starting state: source-sim reset, `scripts/reset_starting.py` (with `PYTHONPATH=/app`), worker started. |
| `unstick.sh` | Lists non-idle db sessions, terminates sessions idle in a transaction for over 1 min, restarts the api. Use when the api hangs. |
| `gate-p9.sh [test files]` | Plan 9's per-task gate: the steps of `gate-mvp.sh` (lint, `api-test.sh <files>`, `web-check.sh` if `frontend/` changed, secret scan), then the plan-file check: `docs/agents/plans/09-agentic-platform.md` must equal `git show HEAD:<plan>` once `- [x] ` is read as `- [ ] ` (ticked boxes are the only allowed change; skipped when the plan is not in HEAD). Runs every step, prints a summary, exits 0 only if all pass. `GATE_LINT`, `GATE_API`, `GATE_WEB` replace the three commands; `GATE_PLAN` and `GATE_PLAN_BASE` (a file) replace the plan and its base. |
| `story-matrix.sh [phase]` | Plan 9's traceability check (R22): reads the first table under the "Story coverage matrix" heading of `docs/agents/plans/09-agentic-platform.md` and checks that every named test exists (`def <name>` under `backend/tests`, or the text in a `frontend/src` `*.test.ts(x)`). With a phase, only rows whose Task starts with `P9-<phase>.`. Prints `BADID`, `TWICE`, `NOTEST`, `MISSING` lines and `story-matrix: R rows, T tests, M missing`; exits 1 on any of them or when the heading is missing. `STORY_MATRIX_PLAN` and `STORY_MATRIX_ROOT` override the plan and the searched root. Host tools only. |
| `story-matrix-test.sh` | Proves `story-matrix.sh` against `scripts/dev/fixtures/story-matrix/` (a plan, a fake backend test and a fake frontend test): found, missing, bad id, repeated id, empty test list, empty phase, missing heading. `selftest.sh` calls it. |
| `selftest.sh` | Proves the scripts report failures through their exit status (a passing and a missing test, a planted type error) and that the api test lock makes a second taker wait and is released when its holder is killed, and that `gate-mvp.sh` and `gate-p9.sh` (with its plan-file check) fail when a stubbed step fails and passes with the real `api-test.sh` on `tests/test_health.py`. Every script exits non-zero on failure; `lib.sh` sets `pipefail` and offers `filtered PATTERN N cmd…`. |
| `wait-idle.sh [max_s]` | Waits until the worker has no due jobs (after a reset it syncs every source first, ~2–3 min). Use before `smoke-rt1048.mjs`. |
| `fresh-clone.sh [--prod]` | Proves the committed HEAD comes up from nothing: `git clone --no-local` of HEAD into a temp dir (uncommitted changes are not included), `docker compose up -d --build --wait` there as project `circfresh` on ports 15173/18000/18100/12222/15432 (`FRESH_WEB_PORT`, `FRESH_API_PORT` …), health checks, `scripts/doctor.sh` in the clone, sign-in as admin through the web port and `GET /api/screens/case/RT-1048` (and 401 without the token), then `smoke-pages.mjs <web> admin` from this checkout's `frontend` if host Node and Playwright are there (`FRESH_SMOKE=0` skips, `=1` requires). Always tears down (`down -v`, its images, the temp dir) and exits non-zero on any failure; does not touch the main stack. `--prod` layers `docker-compose.prod.yml` (images tagged `circfresh-*:runtime`). Needs git, docker, curl. |
| `migrate-reapply.sh [BASE]` | Behind the api test lock: `alembic downgrade <BASE>` (default `0010`; `0017` for plans 2 and 8's migrations), then `upgrade head`, then prints `alembic current`. Plan 6 reserved migrations 0011–0017 empty so parallel tracks could each fill one; every plan-6 migration is idempotent, so re-applying the chain picks up a migration that was first applied empty. Use it after filling (or changing) one of 0011 onwards on a database that already ran it. It drops and rebuilds only plan 6's tables (connections, retry columns, webhook events, mappings, failed records, conflict hash, fx rates); the fx rates come back from 0017 and the demo sources' connection rows from the api's start-up seeding or `reset.sh`; rows saved there by people or tests (connections of app-made sources, mapping versions, held records) are lost, so run `reset.sh` after it. |
| `reencrypt-secrets.sh` | Runs `backend/scripts/reencrypt_secrets.py` in the api container: re-encrypts every stored source credential with the current `DI_SECRET_KEY` (the first key of the comma-separated list). Step 3 of a key rotation (`DI_SECRET_KEY="NEW,OLD"`, recreate api and worker, run this, then keep only NEW; [runbook-fabric.md](runbook-fabric.md#credentials)). Prints counts only; exits 1 if a credential opens with none of the keys. |
| `status.sh` | Health of api and source-sim, container status, api tests running or waiting for the lock (pid, elapsed, args, read from `/proc` in the api container), non-idle db sessions. |

From Windows with Docker Desktop: `bash scripts/dev/status.sh` in Git Bash (`export MSYS_NO_PATHCONV=1` first for
scripts that pass container paths, see CLAUDE.md). With Docker inside WSL:
`wsl -d <distro> -u root -- bash /mnt/c/<path>/Circularity-ui/scripts/dev/status.sh`.

## scripts/trial and trial/ (the trial package for customers)

| Script | What it does |
|---|---|
| `scripts/trial/build.sh` | Packages the committed HEAD (`git archive`; uncommitted changes are never included): builds the runtime images (`docker-compose.prod.yml`'s targets) tagged `circularity-trial-{api,web,source-sim}:<yyyy.mm.dd>-<sha>` (`TRIAL_VERSION` overrides), saves them with `postgres:16-alpine` into `images.tar.gz`, and assembles `dist/circularity-trial-<version>/` (`trial/*` with the version in `compose.yml`, `VERSION`, `postgres-init/`, `data/golden/`, `guides/` from `docs/guides`) plus `.tar.gz` and `.zip` (zip made by Python in the api image). Fails if a `.env` would be packed. |
| `scripts/trial/check.sh [package.tar.gz]` | The clean-install check (default: the newest package in `dist/`): unpacks it into a temp dir, refuses a `.env` or a key-shaped string, removes the package's images so `start.sh` must load them, then start (project `circtrialcheck`, port `TRIAL_CHECK_PORT` 15190), sign in as planner.a through the web port, read RT-1048 and `/api/health`, check that only the web port is published, stop and start (the 128 cases are still there), `reset.sh --yes`, and `smoke-pages.mjs <web> admin` when host Node and Playwright are there (`TRIAL_SMOKE=0` skips, `=1` requires). Always runs `down -v` and removes the temp dir. |
| `trial/start.sh`, `stop.sh`, `reset.sh [--yes]`, `status.sh`, `uninstall.sh [--yes]` (`lib.sh`) | What the customer runs on macOS/Linux. `start` checks Docker, loads `images.tar.gz` if the images are missing, writes `.env` once (random Postgres password, JWT and webhook secrets, a Fernet key; `TRIAL_PORT` 5173), `docker compose up -d --wait`. `stop` keeps the data; `reset` is `down -v` then start; `uninstall` also removes the package's images. |
| `trial/*.ps1` (`lib.ps1`) and `*.cmd` | The same for Windows PowerShell 5.1+; each `.cmd` runs its `.ps1` with `-ExecutionPolicy Bypass` so it can be double-clicked. `start` opens the browser (`TRIAL_NO_BROWSER=1` stops that). |

## Python dependency locks

`backend` and `source-sim` each have `requirements.in` → `requirements.lock` and `requirements-dev.in` →
`requirements-dev.lock` (hashes for every package, transitive included); shared versions are in
`requirements/constraints.txt`. Why and when: [dos-and-donts.md](dos-and-donts.md#dependencies-python).
Re-compile with uv 0.13.5 in a throwaway container (in bash; on Windows put it in a `.sh` file and run it with Git
Bash, `MSYS_NO_PATHCONV=1` set, or through WSL if Docker runs there). Runtime first, then dev (the dev `.in` reads the
runtime lock):

```bash
cd <repo root>      # in WSL: /mnt/c/<path>/Circularity-ui
for svc in backend source-sim; do
  for f in requirements requirements-dev; do
    docker run --rm -v "$PWD:/repo" -w "/repo/$svc" --tmpfs /tmp -e UV_NO_CACHE=1 \
      ghcr.io/astral-sh/uv:0.13.5-python3.12-trixie-slim \
      uv pip compile -q "$f.in" -o "$f.lock" --generate-hashes \
        --python-version 3.12 --python-platform x86_64-unknown-linux-gnu \
        --custom-compile-command "docs/agents/scripts.md (Python dependency locks)"
  done
done
```

Check a lock installs cleanly without touching the stack:
`docker run --rm -v "$PWD:/repo:ro" -w /repo/<svc> python:3.12-slim sh -c 'pip install -q --require-hashes --no-deps -r requirements.lock -r requirements-dev.lock && pip check'`.
`zen-engine` (plan 9 P9-4.2, pinned 2.1.7, MIT, GoRules) is a binary wheel that the per-market decision tables run on
(`di.services.modeler.tables.ZenEvaluator`); `docker compose run --rm --no-deps api python -c "import zen; print(zen.ZenEngine)"`
proves an image has it.
The images install the same way (`backend/Dockerfile`, `source-sim/Dockerfile`, `frontend/Dockerfile`); rebuild after a lock change.

Images (`backend/Dockerfile`, `source-sim/Dockerfile`, `frontend/Dockerfile`): base images pinned by digest; target `dev` is what `docker-compose.yml` builds
(bind mounts, reload, dev lock, tests); target `runtime` has no dev tools, tests or scripts and runs as a non-root user
(api/source-sim uid 10001). The web app's runtime image is a separate file, `frontend/Dockerfile.runtime`, built from
the repo root (root `.dockerignore` allows only `frontend` and `fixtures/demo`): it runs `extract-styles.mjs` and
`vite build` itself, then serves `dist` from nginx-unprivileged on 8080 with a CSP
(`frontend/nginx/default.conf.template`). `frontend/Dockerfile` keeps only the dev target with context `frontend`; the
classic builder builds every stage before the target, so one file cannot serve both contexts. Some Docker installs
(e.g. Ubuntu's `docker.io` in WSL) have no buildx, so the classic builder runs them; keep the Dockerfiles free of
BuildKit-only syntax. Run the runtime images with
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` (opt-in; no host Node needed), or build
the web one alone: `docker build -f frontend/Dockerfile.runtime -t circularity-ui-web:runtime .`. To bump a base image, take a tag at least two weeks old and its index
digest from Docker Hub (`https://hub.docker.com/v2/repositories/library/<image>/tags?name=<tag>`).

## backend/scripts (run inside the api container)

| Script | What |
|---|---|
| `reset_starting.py` | Puts di back to the starting state (cases, workspace collections, delegations, grants; journal and instructions cleared; connector data kept). `docker compose exec -T -e PYTHONPATH=/app api python scripts/reset_starting.py`. |
| `reencrypt_secrets.py` | Rewrites every `source_secret` row (every version) with the current `DI_SECRET_KEY` (`di.connectors.secrets.reencrypt`) and commits; prints `N re-encrypted with the current key, M unreadable` and the source, kind and version of each unreadable row, never a key or a secret; exits 1 when one is unreadable (the rest are committed). `docker compose exec -T -e PYTHONPATH=/app api python scripts/reencrypt_secrets.py` (or `scripts/dev/reencrypt-secrets.sh`). |
| `full_sync.py` | Syncs every source once, in full, and prints records, facts, failures and open conflicts by field. `docker compose exec -T api python scripts/full_sync.py`. |

## frontend/scripts (Node)

| Script | What |
|---|---|
| `extract-styles.mjs [--force]` | Copies the demo's stylesheet into `src/styles/legacy.gen.css` and the product photos into `public/assets/products/`. Runs before `npm run dev/build/test`. |
| `dump-assets.mjs` | Writes `src/assets/assets.gen.ts` (logos, icons, vendor logos and their rules) from the demo run headless. Committed; rerun only when the demo's assets change. `npm run assets`. |
| `dump-golden.mjs` | Writes the base golden files (`fixtures/golden/*.json`) from the demo. `npm run golden`. |
| `golden-sandbox.mjs` | Shared headless sandbox for the golden scripts (`freshDemo`, `plain`, `writeGolden`). |
| `golden/<area>.mjs` | Per-area golden files: `analytics_audit` (screens reference, analytics, audit, nav, checks), `ask`, `fabric` (screens integration, mcp, access, workflows), `home_command` (home, command), `mcp_calls` (mcp.json), `product_case` (product, case, orchestration), `workflow_writes`. See `golden/README.md`. |
| `dump-po-golden.mjs` | Writes `fixtures/golden/po/*.json` from the PO Modeler prototype (`docs/reference/po-modeler/recover-app-prototype.html`), the reference plan 8's Modeler code is tested against. |
| `smoke-pages.mjs`, `smoke-signin.mjs`, `smoke-ask.mjs`, `smoke-approve.mjs`, `smoke-rt1048.mjs`, `smoke-fabric.mjs`, `smoke-modeler.mjs`, `smoke-mvp.mjs`, `smoke-p9-1.mjs` | Browser smoke checks with Chrome: see [testing.md](testing.md#browser-smoke-scripts-frontendscripts). |
| `screenshot.mjs <outDir> <account\|-> <route> [route…]` | Dev helper: screenshots routes of the running app, signed in as the account. |

## npm scripts (frontend/package.json)

| Script | Runs |
|---|---|
| `dev` | `predev` (extract-styles), then `vite --host 0.0.0.0`. |
| `build` | `prebuild` (extract-styles), then `tsc -b && vite build`. |
| `test` | `pretest` (extract-styles), then `vitest run`. |
| `typecheck` | `tsc -b`: the app (tsconfig.app.json) and the Node-side configs (tsconfig.node.json). |
| `lint`, `knip` | `eslint .`, `knip` (both run by `scripts/dev/lint.sh` in the web container). |
| `preview` | `vite preview` of a build. |
| `assets` | `dump-assets.mjs`. |
| `golden` | `dump-golden.mjs`. |

## Useful one-offs (source-sim control API, :8100 or `SIM_PORT`)

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
| `http://localhost:8000/docs` | OpenAPI for the whole api (`API_PORT` if set). |
