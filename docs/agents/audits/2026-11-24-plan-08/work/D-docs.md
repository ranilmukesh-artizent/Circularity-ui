# D: docs after the fixes and the merge (24 Nov 2026)

Docs only. No tests, no docker, no state-changing git (read: `git log 2a3ee00..95a45ed`, `git show --stat 95a45ed`,
the decision-log diff in `95a45ed`). All files UTF-8, LF, no BOM (checked).

## Files changed
- `docs/agents/audits/2026-11-24-plan-08/README.md`
  - New section "After the fixes and the merge (24 Nov 2026)": F1–F11 status with test names or decision-log rows,
    the extra template fixes, U1–U9 status with the colleague's commit or our file, the merge record (policy,
    semantic decisions, review findings 1–5 and what was done, backup branch), verification, the evidence table
    (file → result line), and the `<!-- AFTER-SUITE ... -->` placeholder exactly as asked.
  - Statements made true: a note that scores and verdicts are for `2a3ee00`; the Findings Status column (was "open"
    for all); the UI-gaps heading "at `2a3ee00`"; agent-catalog.json "at `2a3ee00`, not regenerated"; the F4 line in
    "Agents and CRUD"; the Dover-stories "no screen" notes marked out of date (not re-scored); baseline api/sim
    "(results added when the run ends)" replaced by 4,379 / 271 passed and the four baseline smokes.
- `docs/agents/testing.md`: subsection "Parallel shards (faster, partial)" under Suites (11 lines).
- `docs/agents/learnings.md`: three 2026-11-24 entries (fresh-DB shards; Git Bash stdin/CR; renumbered migration).

## Could not verify
- **File count:** at HEAD `backend/tests` has 140 `test_*.py`; the 37 serial-only files (26 by the `_sim/|/faults`
  grep + 11 listed, no overlap) leave **103** for the shards, not the 108 in the brief. The README says "the api
  test files that are safe side by side" without a number. Please check the shard echo lines of the run.
- The migration downgrade on the dev DB, the column check and the frontend merge checks (tsc, vitest 312/39,
  eslint, knip) have no log file in `evidence/`; written as the lead's / M-frontend-merge's results.
- That the workflow/home/access/reference files fail on a fresh DB on the colleague's code: lead's statement.
- Learning (b): the symptom wording is reconstructed from `parallel.sh`'s guards and the lead's note, not from a log.
- `after-api.log` (full serial run at `95a45ed`) was still in progress; left to the AFTER-SUITE placeholder.
- `after-lint.log` / `after-web.log` / `fix-web.log` are from the fix worktree before the merge (after-web still runs
  `proposals.test.ts`, dropped in the merge); labelled so in the table.
