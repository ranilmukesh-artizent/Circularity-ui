# K: final combined check (28 Nov 2026, branch feature/ai-engine)

| Step | Result | Counts |
|---|---|---|
| 1 web-check | PASS (after 1 fix) | first run: 1 tsc error; rerun: tsc errors 0, 167 test files, 1183 tests passed |
| 2 backend static | PASS (after 1 fix) | ruff check: all passed; ruff format --check: 1 file needed formatting, fixed, now clean; `mypy` as the repo runs it (package `di`): no issues in 632 files; lint-imports: 6 kept, 0 broken |
| 3 api tests (12 files, one run) | PASS | 1032 passed, 1 warning, 206 s |
| 4 restart worker + reset | PASS | reset to 15 demo cases in 5 packs, 3 agent runs |
| 5 smoke-pages | PASS | 11 accounts, 0 failing routes (admin 74, executive 36, planner-a 38, planner-b 36, planner-c 36, approver 51, engineer 45, finance 41, developer 41, wm-1 27, wm-2 27) |
| 6 smoke-p9-8 (SIM_PORT=8100) | PASS | all 12 steps passed (step 12 prints "skipped: no table", as the script allows) |
| 7 reset | PASS | |

## Fixes
- `frontend/src/layout/assistant/modes/SetupMode.tsx:108`: the sample-prompt shortcut built `{ ok: false, error: { code: 'sample' } }`, and `'sample'` is not an `ActionError` code, so tsc failed (TS2322). Changed the code to `'not_found'` (the value is only a placeholder; the branch never reads it).
- `backend/di/services/screens/nav.py`: `ruff format` reflowed the `navigation(...)` signature (formatting only).

## Failures left
- None in the requested steps.
- Note: running `mypy` with the changed files named explicitly also checks tests and reports 9 errors in `tests/helpers.py` (pre-existing), `tests/test_analytics_rows.py` (lines 67, 74, 179, 180, 227) and `tests/test_analytics_pack_headline.py` (lines 102, 172, 208). The repo's own `mypy` (`files = ["di"]`) does not cover tests, so this is not a gate failure. Not fixed.

## Screenshots (admin, 1440x900, light, full page), in `docs/agents/plans/11-work/shots/`
- `home.png`: Home with the regrouped menu (Decide, Understand, Advanced), greeting, tiles, proposals and Key figures. The first capture (4 s wait) showed grey placeholders; recaptured after 20 s, fully loaded.
- `setup.png`: Set up with the five stops (Business flow, Systems, Agents, Approve, Publish) and the template screen (starting from Industrial returns, Change, sample prompts).
- `analytics.png`: Analytics in its new order: per-pack headline, pack panels for tool fleet and device, then the charts, each with a "View data" button; no inline drill panel.
- `analytics-view-data.png`: the flow chart's "View data" drawer open: "Where returned assets go: class, route and outcome", 1,400 rows, total, paging, Export CSV. The drawer sits mid-page because of the full-page capture of a fixed overlay.
