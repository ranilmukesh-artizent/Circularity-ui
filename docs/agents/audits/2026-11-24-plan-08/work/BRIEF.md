# Shared brief for the agents fixing the plan-8 audit (24 Nov 2026)

Read first: `docs/agents/audits/2026-11-24-plan-08/README.md` (the audit: findings F1–F11, UI gaps U1–U9) in the MAIN
repo `C:\repos\astra-prism-DI\ayush-ui\Circularity-ui`, and `AGENTS.md` there (golden rules).

## Where to work
- **Edit code only in the fix worktree** `C:\repos\astra-prism-DI\ayush-ui\Circularity-ui-fix` (detached HEAD, same
  code as `feature/fullstack-poc` plus the lead's fixes). The main repo is bind-mounted into the running stack, and a
  full baseline test run is going on there: **do not edit files in the main repo**, except your own report file below.
- **No git commands that change state** (no commit, stash, reset, checkout, add). The lead merges and commits.
- **Do not run** `docker compose exec api pytest`, `scripts/dev/*.sh` that run tests, or anything that resets the main
  stack (`reset.sh`, `_sim/reset`). Read-only `curl` against http://localhost:8000 and :5173 is fine.
- Several agents share the worktree: **touch only the files your brief names**. If you must change a shared file
  (e.g. `frontend/src/api/invalidation.ts`, `frontend/src/api/client.ts`, a backend module outside your list), make
  the smallest possible Edit and list it in your report under "Shared files touched".
- Python edits: write files as UTF-8 (`PYTHONUTF8=1`, or the Edit tool). Never open() without encoding on Windows.

## How to test (all from Git Bash)
- api tests from the worktree in a one-off container, against YOUR private database:
  `FIX_DB=<your db> bash /c/repos/astra-prism-DI/ayush-ui/Circularity-ui/docs/agents/audits/2026-11-24-plan-08/work/fixtest.sh tests/test_x.py`
  One run at a time per database. The tests reset their own database; source-sim is shared (avoid tests that set sim
  faults or reset it).
- web checks from the worktree (tsc + vitest; `lint` adds eslint + knip; `vitest <file>` runs one file):
  `bash /c/repos/astra-prism-DI/ayush-ui/Circularity-ui/docs/agents/audits/2026-11-24-plan-08/work/webcheck-fix.sh [lint]`
- TDD: write the failing test first, run it, see it fail for the right reason, then fix, then run it green. Quote
  the commands and results in your report.

## Product rules that matter here
- Pages call only `frontend/src/api/*.ts`; the facade calls only di-api; every write goes through
  `POST /api/actions/{id}` (`invoke()` / `useAction` in the web app). Access is enforced on the server.
- Product-neutral wording: no customer or vendor names in UI text. Short, plain labels.
- Keep the demo's existing screens and numbers unchanged (parity); add controls, don't restyle.
- Agents (MCP, Ask) only read or hold for a person.

## Report
Write `docs/agents/audits/2026-11-24-plan-08/work/<your-id>.md` in the MAIN repo (the only main-repo file you write):
what you changed (file list), tests added, the exact commands run and their final result lines, anything left open,
shared files touched. Keep it under ~60 lines. Your final message to the lead: 5–10 lines, pointing at the report.
