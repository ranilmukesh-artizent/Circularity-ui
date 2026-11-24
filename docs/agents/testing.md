# Testing

From Windows with Docker Desktop, run the scripts below from the repo root in Git Bash (`export MSYS_NO_PATHCONV=1`
first; see CLAUDE.md, "Git Bash pitfalls"). Where Docker runs inside WSL:
`wsl -d <distro> -u root -- bash /mnt/c/<path>/Circularity-ui/scripts/dev/<script>.sh [args]`.

## Suites

| Suite | Where | Command | Size and time (24 Nov 2026) |
|---|---|---|---|
| api (di) | `backend/tests` (140 files) | `bash scripts/dev/full-suite.sh` (all) / `bash scripts/dev/api-test.sh tests/test_x.py` | 4,460 tests: 4,458 passed, 1 skipped, 1 failed then fixed in `8fea98c` (re-run targeted); ~32 min |
| api pre-check | the 102 files safe side by side | `bash scripts/dev/parallel-suite.sh` | 4 shards on private databases, ~7-11 min; see "Parallel shards" |
| source-sim | `source-sim/tests` | part of `full-suite.sh`; alone: `docker compose exec -T source-sim pytest -q` | 271 tests, ~1 min |
| web unit | `frontend/src/**/*.test.ts(x)` (vitest, jsdom) | `bash scripts/dev/web-check.sh` | 312 tests in 39 files + tsc, ~1 min |
| browser smoke | `frontend/scripts/smoke-*.mjs` (Node Playwright, installed Chrome) | `node frontend/scripts/smoke-pages.mjs <baseUrl> [accounts…]` from `frontend` on the host | ~5 min per mode for 11 accounts |
| fresh clone | committed HEAD cloned to a temp dir, project `circfresh`, ports 15173/18000/18100/12222/15432 | `bash scripts/dev/fresh-clone.sh [--prod]` | up --wait, health, doctor, sign-in + RT-1048 screen, smoke for admin if host Node; ~5–15 min (build) |
| CI | `.github/workflows/ci.yml` | see "CI" below | ~30 min (the `stack` job) |

### Parallel shards (faster, partial)

`bash scripts/dev/parallel-suite.sh` (`N=6` for six shards, `--list` to print the shards and run nothing, `KEEP=1`
to keep the databases) runs the api test files that are safe side by side in N shards at once (default 4). Each shard
is a `docker compose run --rm --no-deps api` container on its own fresh database `di_par1..di_parN` on the stack's
postgres: dropped and created, `alembic upgrade head`, then `ensure_sources` as the worker runs at start, then pytest.
Shards are balanced by `scripts/dev/test-times.txt` (how to regenerate it: [scripts.md](scripts.md)); logs go to
`test-results/parallel/shard-<k>.log` (git-ignored).
It leaves out 38 files (24 Nov 2026): those that reset or fault the shared source-sim (every shard would see it), call
the running api (MCP, stream, webhooks, health) or need a fabric synced by the running stack; they run only in the
serial suite. With 4 shards it takes ~7-11 min (more when the machine is busy) against ~32 min serial. It does not touch the main database or the api
test lock, so it can run beside other work, but not beside `full-suite.sh` (both use the shared source-sim). It is a
pre-check: the serial `scripts/dev/full-suite.sh` stays the gate. It replaces the audit's
`docs/agents/audits/2026-11-24-plan-08/work/parallel.sh` (kept there as evidence only).

**Known environmental failures on a fresh database** (not regressions; [learnings](learnings.md)): without
`ensure_sources`, "No table model for erp" and empty source lists; the workflow, home, access-writes and reference
screen files fail on any fresh database, also on unchanged code, because they expect a fabric the stack has synced
(they are in the script's serial-only list); MCP and other live-server tests get "Connection refused" in a one-off
container, which serves no api. Check such a failure on the base commit's code on a fresh database before you call
it a regression.

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main` and `feature/fullstack-poc`. It needs no
secret (without `GROQ_API_KEY`, Ask uses its rule-based fallback). Read-only token, superseded runs on the same ref are
cancelled, every job has a timeout, and actions and images are pinned by commit SHA or digest.

| Job | What it runs |
|---|---|
| `stack` | `docker compose up -d --build --wait` of postgres, source-sim and api (worker left stopped; `--wait` returns once their healthchecks pass), resets the simulator, then the api suite and the source-sim suite inside their containers, as `full-suite.sh` does; `docker compose down -v` always |
| `arm64` | on `ubuntu-24.04-arm`: `docker compose up -d --build --wait` of the whole stack (postgres, source-sim, api, worker, web), checks the api container is `aarch64`, api `/api/health` ok, source-sim `/health`, web `/` 200, signs in as admin through the web port and reads `/api/screens/case/RT-1048`; logs on failure, `down -v` always. No test suite (those run on amd64 in `stack`). GitHub's arm64 runners are free for public repositories; a private one needs a plan with arm64 runners, or the job waits for a runner |
| `web` | Node 24: `npm ci`, `npm test` (vitest), `npm run build`, `npm audit --audit-level=high` |
| `python-lint` | per service: `ruff check` (the ruff pinned in its requirements) and `pip-audit -r requirements.lock` |
| `secrets` | gitleaks: the PR's commits on pull requests, the full history on pushes |

Still to come: `ruff format --check` (C1), ESLint and knip (C2), mypy (C3); they sit commented out in the workflow
with a TODO naming the step. Every compose service has a healthcheck (F1): postgres (`psql` on both databases), api
(`/api/health/live`), source-sim (`/health`), web (an HTTP GET of the dev server) and worker (liveness only: PID 1 is
still `python -m di.worker`; it serves no port). api and worker start once source-sim is healthy, web once api is,
so `docker compose up -d --wait` returns when the whole stack is up. Dependabot
(`.github/dependabot.yml`) opens weekly grouped minor/patch updates for pip, npm, docker and actions.
`.pre-commit-config.yaml` runs gitleaks, ruff check, end-of-file-fixer and mixed-line-ending (LF) on commit
(`pre-commit install` once).

After `full-suite.sh`, run `bash scripts/dev/reset.sh` (the suite leaves test state behind and stops the worker).

## Rules

- **One api pytest at a time.** `scripts/dev/lib.sh api_lock` takes a flock on `/tmp/di-pytest.lock` inside the api
  container (no host `flock`; the scripts run on Linux, macOS and Git Bash). It is released when the script exits or is
  killed; two `api-test.sh` started together run one after the other, and `status.sh` lists the holder and the waiters.
  `selftest.sh` checks both. Never run `docker compose exec api pytest` by hand while anyone else may be testing.
- **Module resets.** Most test modules reset di to the starting state (`backend/tests/starting.py reset()`). Set
  `B14_PARALLEL=1` only if you run the B14 screen modules in parallel processes and reset once yourself; otherwise
  leave it unset.
- **Clock and instructions.** `tests/conftest.py` forces `DI_CLOCK=pinned` and `DI_INSTRUCTIONS=false`. The real
  loop is tested only in `tests/test_milestone_rt1048.py`, which pauses the simulated clock, removes the live api's
  webhook subscription, and needs the worker stopped (`full-suite.sh` stops it).
- **source-sim tests use their own database.** `source-sim/tests/conftest.py` points them at `sources_test`
  (created if missing, schemas and seed from the app's start-up), so the live service on `sources` (its background
  loops, di's webhook subscription) is never touched; tests delete only the subscriptions they made.
- **Live-server tests.** `test_stream.py` and the MCP/Ask live tests call the running api on `localhost:8000` inside the api container (any `API_PORT`), so the
  api must be healthy. Run `bash scripts/dev/status.sh` first.
- **Groq.** The live Ask smoke test spends real free-tier requests (about 1,000 a day). Don't loop it.
- **Shared helpers.** `backend/tests/helpers.py` holds the one in-process `client`, `h(user)` (the Authorization
  header for a demo account, signed in once per session), `call(action, body, user)`, and the golden comparisons
  `strict()` (booleans apart from numbers) and `norm()` (numbers to 1e-6, as the dump writes them). `conftest.py` also
  offers `client` and `login` as fixtures. Read golden files with `di.core.golden.load(name)`. Don't add per-file copies.

## Slowest api tests

`bash scripts/dev/api-test.sh --durations=50` over the whole api suite (20 Nov 2026, D6): `3486 passed, 1 warning in
1763.37s (0:29:23)`. The time is in the connector adapter tests (initial syncs against source-sim, and the module
teardowns that reset a simulated system); the parity tests are many but fast.

| Time | Phase | Test |
|---|---|---|
| 15.67s | teardown | `test_adapter_assetwise.py::test_unchanged_delta_reads_nothing_and_an_approval_is_picked_up` |
| 13.74s | teardown | `test_adapter_aras.py::test_unchanged_delta_reads_nothing_and_a_change_is_picked_up` |
| 13.61s | call | `test_adapters_crm_oms_fsm.py::test_sterling_initial_sync_maps_the_demo_examples` |
| 13.52s | call | `test_adapter_assetwise.py::test_initial_sync_maps_the_demo_examples` |
| 12.74s | call | `test_adapter_manhattan.py::test_initial_sync_reproduces_the_facts_and_mappings` |
| 12.06s | call | `test_adapter_persefoni.py::test_initial_sync_reproduces_the_demo_mappings` |
| 11.75s | setup | `test_adapters_maximo_safetyculture.py::test_maximo_initial_sync_maps_assets_and_service_history` |
| 11.12s | call | `test_adapter_teamcenter.py::test_initial_sync_maps_the_demo_examples` |
| 11.01s | call | `test_models_migrations.py::test_downgrade_and_upgrade_round_trip` |
| 10.69s | teardown | `test_adapter_persefoni.py::test_new_activity_is_calculated_and_picked_up` |
| 10.48s | call | `test_adapter_sims.py::test_bad_manifest_signature_fails_every_file` |
| 10.25s | teardown | `test_milestone_rt1048.py::test_steps_without_a_mock_write_are_acknowledged_by_the_simulated_adapter_on_the_clock` |
| 10.23s | call | `test_adapters_crm_oms_fsm.py::test_salesforce_initial_sync_maps_the_demo_examples` |
| 9.43s | call | `test_adapter_aws_iot.py::test_full_sync_maps_telemetry_to_the_canonical_model` |
| 8.20s | teardown | `test_adapter_mastercontrol.py::test_an_expired_certificate_shows_as_expired` |
| 7.63s | setup | `test_milestone_rt1048.py::test_rt1048_runs_from_approval_to_reconciled_on_events_and_the_clock` |
| 7.42s | call | `test_adapter_machinio.py::test_initial_sync_reproduces_the_facts` |
| 6.98s | call | `test_adapter_aras.py::test_unchanged_delta_reads_nothing_and_a_change_is_picked_up` |
| 6.85s | call | `test_adapter_aras.py::test_initial_sync_maps_the_demo_examples` |
| 6.39s | teardown | `test_adapter_manhattan.py::test_delta_picks_up_a_reservation_and_a_shipped_transfer` |

Then 20 more between 6.2s and 2.5s, the same kinds (adapter syncs, `test_connectors.py` S/4 syncs,
`test_models_migrations.py::test_alembic_check_finds_no_differences` 3.1s, `test_stream.py` 3.2s,
`test_execution.py::test_scenario[exec_other_routes]` 2.5s). Every other test takes under 2.5s.

## Parity (golden files)

- `fixtures/golden/*.json` is what the demo computes, dumped headless from `fixtures/demo/index.html` by:
  - `frontend/scripts/dump-golden.mjs` (base files: world, cases, decisions, sources, …);
  - `frontend/scripts/golden/<area>.mjs` (screens, ask, mcp, workflow writes), all on the shared sandbox
    `frontend/scripts/golden-sandbox.mjs` (`freshDemo`, `plain`, `writeGolden`).
- Backend tests compare endpoint and action output to these files for all 11 accounts. `strict()` and `norm()`
  (`tests/helpers.py`; `starting.strict()` is the same function) compare strictly.
- Values the demo draws unseeded, and real connector data, are excluded where they occur, with the reason in a comment.

### Regenerating golden files

1. Change `fixtures/demo/index.html` (or a dump script), never the JSON.
2. Regenerate everything from `frontend` on the host:
   `node scripts/dump-golden.mjs;` then each `node scripts/golden/<area>.mjs` (and `node frontend/scripts/dump-assets.mjs` if
   the demo's logos or icons changed).
3. Prove the diff is only what you meant. Load `git show HEAD:<file>`, apply your intended change to the parsed JSON,
   and deep-compare it with the new file. Every file must report "only the intended change". Text diffs are too
   noisy for files this size.
4. Restart api and worker (`bash scripts/dev/restart.sh`); they read the golden files at start-up.
5. Run the full suite.

## Browser smoke scripts (frontend/scripts)

| Script | Checks |
|---|---|
| `smoke-pages.mjs <base> [accounts]` | Signs in as each account, opens every menu link plus a few extra routes, and reports error boundaries, empty pages and console errors. Exits 1 on any failure. |
| `smoke-signin.mjs <base>` | Sign-in messages (unknown account, missing password), the login call to di-api, and that a reload keeps the session. |
| `smoke-ask.mjs <base> <account> "<question>" [route]` | Opens Ask with Ctrl+J and prints the streamed answer, the lookups and the sources. Spends Groq requests. |
| `smoke-approve.mjs <base>` | Two sessions: Planner A watches RT-1048 stage 7 while the Approver approves. Checks the live update without a reload and the hand-off in stage 8. **Changes state:** run `scripts/dev/reset.sh` afterwards. |
| `smoke-rt1048.mjs <base>` | RT-1048 through all ten stages: Planner A submits, the Approver approves, source-sim's clock advances until the systems have acknowledged every instruction, Finance confirms; a watcher follows without reloading. Exits 1 unless stage 10 is reached with no page errors. **Changes state:** `reset.sh`, then `wait-idle.sh`, before and `reset.sh` after. |
| `smoke-fabric.mjs <base>` | The Connection Fabric as Developer (plan 6 D2), one line per step: connect PostgreSQL from the catalogue (five steps, first sync with records), rotate its credential and Sync now, edit a mapping rule on SafetyCulture (Preview, Save, Revert), resolve a conflict with another value and a reason (still resolved after a reload), Manual Import, then a Salesforce ingest workflow (Convert currency EUR, Order late events, error handler; Validate, Test run, Save, Publish, Run now, History, failed records), and deletes the workflow and the source. Exits 1 on any failed step or page error; `SMOKE_SHOTS=<dir>` saves a screenshot per failure. Needs the worker running. ~2–4 min. **Changes state:** `reset.sh`, then `wait-idle.sh`, before and `reset.sh` after, holding the api test lock throughout (api-test.sh would stop the worker). |

| `smoke-modeler.mjs <base>` | The Modeler (plan 8): Planner A gives Customer A its own flow with a rule, simulates and submits; the Approver approves (shadow) and publishes; a re-evaluated case shows the exclusion. 17 checks. **Changes state:** `reset.sh` before and after. |
| `smoke-mvp.mjs <base>` | The MVP end to end (plan 8), one PASS/FAIL line per step: a new org unit, a connected source that opens cases, access asked and granted, a flow changed with the assistant, an agent's held proposal accepted, approval, outcome confirmed by Finance, a model fitted. 12 steps (1–10, with 2 and 4 in two parts). Needs the worker. **Changes state:** `reset.sh` and `wait-idle.sh` before, `reset.sh` after, holding the api test lock. |

- The app (container on :5173, or a host Vite on :5174) reads only di-api; there is no other mode since B17c.
- **Last full result** (24 Nov 2026, at `8fea98c`; `docs/agents/audits/2026-11-24-plan-08/work/S-smokes.md`):
  `smoke-pages.mjs` 0 failing routes for all 11 accounts; `smoke-rt1048.mjs` reached stage 10; `smoke-modeler.mjs`
  all 17 checks; `smoke-mvp.mjs` all 12 steps. Route counts per account vary between runs (links are collected
  800 ms after sign-in, before Home has fully rendered), so compare failures, not counts.

## Known flaky tests

- Browser smoke failures with "Failed to fetch" or `ERR_NETWORK_IO_SUSPENDED` while the api restarts, or while
  another agent's half-finished edit is hot-reloading. Re-run when the stack is healthy and the tree typechecks.
- A console 404 for `/favicon.ico` (the index has no icon link). Benign; `smoke-pages.mjs` filters it.
- Failures that show only in a parallel shard or another fresh database: see "Known environmental failures" under
  "Parallel shards".

## Before you claim done

1. `bash scripts/dev/web-check.sh` → `tsc errors: 0`, vitest all passed.
2. The api tests for what you touched → passed. `parallel-suite.sh` is a quick pre-check; before a commit, run the
   serial full suite with only accepted failures.
3. `smoke-pages.mjs` for all 11 accounts if you touched the frontend; the end-to-end smokes (rt1048, modeler, mvp)
   if you touched what they cover.
4. `bash scripts/dev/reset.sh` so the next person starts from the demo's state.
