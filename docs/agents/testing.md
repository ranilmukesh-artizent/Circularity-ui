# Testing

From Windows, run every script below through WSL:
`wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path>/Circularity-ui/scripts/dev/<script>.sh [args]`.

## Suites

| Suite | Where | Command | Size and time (20 Nov 2026) |
|---|---|---|---|
| api (di) | `apps/api/tests` | `bash scripts/dev/full-suite.sh` (all) / `bash scripts/dev/api-test.sh tests/test_x.py` | ~3,450 tests, ~25 min |
| source-sim | `apps/source-sim/tests` | part of `full-suite.sh`; alone: `docker compose exec -T source-sim pytest -q` | 208 tests, ~1 min |
| web unit | `apps/web/src/**/*.test.ts` (vitest, jsdom) | `bash scripts/dev/web-check.sh` | 12 tests + tsc, ~1 min |
| browser smoke | `apps/web/scripts/smoke-*.mjs` (Node Playwright, installed Chrome) | `node apps/web/scripts/smoke-pages.mjs <baseUrl> [accounts…]` from `apps/web` on the host | ~5 min per mode for 11 accounts |
| CI | `.github/workflows/ci.yml` | ruff + pytest for api and source-sim; `npm run build` for web | — |

After `full-suite.sh`, run `bash scripts/dev/reset.sh` (the suite leaves test state behind and stops the worker).

## Rules

- **One api pytest at a time.** `scripts/dev/lib.sh api_lock` takes a flock on `/tmp/di-pytest.lock`. Never run
  `docker compose exec api pytest` by hand while anyone else may be testing.
- **Module resets.** Most test modules reset di to the starting state (`apps/api/tests/starting.py reset()`). Set
  `B14_PARALLEL=1` only if you run the B14 screen modules in parallel processes and reset once yourself; otherwise
  leave it unset.
- **Clock and instructions.** `tests/conftest.py` forces `DI_CLOCK=pinned` and `DI_INSTRUCTIONS=false`. The real
  loop is tested only in `tests/test_milestone_rt1048.py`, which pauses the simulated clock, removes the live api's
  webhook subscription, and needs the worker stopped (`full-suite.sh` stops it).
- **Live-server tests.** `test_stream.py` and the MCP/Ask live tests call the running api on `localhost:8000`, so the
  api must be healthy. Run `bash scripts/dev/status.sh` first.
- **Groq.** The live Ask smoke test spends real free-tier requests (about 1,000 a day). Don't loop it.

## Parity (golden files)

- `fixtures/golden/*.json` is what the demo computes, dumped headless from `index.html` by:
  - `apps/web/scripts/dump-golden.mjs` (base files: world, cases, decisions, sources, …);
  - `apps/web/scripts/golden/<area>.mjs` (screens, ask, mcp, workflow writes), all on the shared sandbox
    `apps/web/scripts/golden-sandbox.mjs` (`freshDemo`, `plain`, `writeGolden`).
- Backend tests compare endpoint and action output to these files for all 11 accounts. `starting.strict()` compares
  strictly.
- Values the demo draws unseeded, and real connector data, are excluded where they occur, with the reason in a comment.

### Regenerating golden files

1. Change `index.html` (or a dump script), never the JSON.
2. Regenerate everything from `apps/web` on the host:
   `node scripts/dump-golden.mjs;` then each `node scripts/golden/<area>.mjs` (and `node scripts/dump-assets.mjs` if
   the demo's logos or icons changed).
3. Prove the diff is only what you meant. Load `git show HEAD:<file>`, apply your intended change to the parsed JSON,
   and deep-compare it with the new file. Every file must report "only the intended change". Text diffs are too
   noisy for files this size.
4. Restart api and worker (`bash scripts/dev/restart.sh`); they read the golden files at start-up.
5. Run the full suite.

## Browser smoke scripts (apps/web/scripts)

| Script | Checks |
|---|---|
| `smoke-pages.mjs <base> [accounts]` | Signs in as each account, opens every menu link plus a few extra routes, and reports error boundaries, empty pages and console errors. Exits 1 on any failure. |
| `smoke-signin.mjs <base>` | Sign-in messages (unknown account, missing password), the login call to di-api, and that a reload keeps the session. |
| `smoke-ask.mjs <base> <account> "<question>" [route]` | Opens Ask with Ctrl+J and prints the streamed answer, the lookups and the sources. Spends Groq requests. |
| `smoke-approve.mjs <base>` | Two sessions: Planner A watches RT-1048 stage 7 while the Approver approves. Checks the live update without a reload and the hand-off in stage 8. **Changes state:** run `scripts/dev/reset.sh` afterwards. |
| `smoke-rt1048.mjs <base>` | RT-1048 through all ten stages: Planner A submits, the Approver approves, source-sim's clock advances until the systems have acknowledged every instruction, Finance confirms; a watcher follows without reloading. Exits 1 unless stage 10 is reached with no page errors. **Changes state:** `reset.sh`, then `wait-idle.sh`, before and `reset.sh` after. |

- The app (container on :5173, or a host Vite on :5174) reads only di-api; there is no other mode since B17c.
- **Last full result** (20 Nov 2026, after B17c): 0 failing pages for all 11 accounts; `smoke-rt1048.mjs` reached
  stage 10 (predicted $9,600, actual $9,230). Route counts: admin 70,
  executive 33, planner-a 41, planner-b 41, planner-c 38, approver 47, engineer 48, finance 38, developer 39,
  wm-1 29, wm-2 29.

## Known flaky tests

Cause, for all of these: the running source-sim service has its own background loops (`sim/main.py`: `scheduler.tick`
and `webhooks.deliver`, every second) working on the same tables the tests drive by hand. A test that calls
`webhooks.deliver` or advances the clock can lose a row lock or a scheduled item to the live loop.

- **`test_sim_control.py::test_events_are_delivered_as_signed_cloudevents_and_retried`:** fixed 20 Nov 2026 by
  driving delivery passes until the test's own delivery lands (tolerates the live dispatcher). Use this pattern.
- **`test_aws_iot.py::test_rule_deliveries_are_signed_cloudevents`:** can fail with `NoResultFound` right after a
  source-sim restart while the service is still delivering its backlog. Re-run once it settles.
- **`test_otm.py::test_booking_plans_a_shipment_that_is_delivered_on_the_clock`:** failed once in seven full runs
  (20 Nov 2026), passes alone; suspected race with the live `scheduler.tick`. Not fixed yet: if it fails again,
  capture the assertion and apply the same pattern (or run source-sim with its background loops off for tests).
- Browser smoke failures with "Failed to fetch" or `ERR_NETWORK_IO_SUSPENDED` while the api restarts, or while
  another agent's half-finished edit is hot-reloading. Re-run when the stack is healthy and the tree typechecks.

## Before you claim done

1. `bash scripts/dev/web-check.sh` → `tsc errors: 0`, vitest all passed.
2. The api tests for what you touched → passed. Before a commit, run the full suite with only accepted failures.
3. The browser smoke in both modes if you touched the frontend.
4. `bash scripts/dev/reset.sh` so the next person starts from the demo's state.
