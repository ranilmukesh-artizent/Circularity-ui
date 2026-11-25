# Plan 9 in two lanes

**Lane B lead: start with [lane-B-start.md](lane-B-start.md).**

Since 25 Nov 2026, plan 9 is built on two machines at once. Each lane has a lead (a Claude Code session, Opus) that runs
writers (subagents, Sonnet or Haiku) as described in `../09-agentic-platform.md`, "How to run this plan unattended".

| Lane | Phases | Who | Branch | Run folder |
|---|---|---|---|---|
| A, core | 1 (finish), 2 agent chain, 7 replay and publish, 8 Compose | the integrator's machine | `feature/plan-09-recover` | `docs/agents/plans/09-run/` |
| B, packs | 3 tool-fleet returns, 4 service desk, 5 contract refresh, 6 device | Mahizhan's machine | `feature/plan-09-lane-b` | `docs/agents/plans/09-run/lane-B/` |

Phases 9 to 13 are split later, once A and B are merged.

## Why the lanes do not wait on each other

- Phase 1 built the shared base: packs as data, the one decider (`decide_case`), the valuer plug-ins, the gate
  catalogue, the case process layer, and migrations 0029 to 0061 reserved by name for every task.
- Lane B needs only three phase 2 tasks: P9-2.1 (stage records), P9-2.4 (hold policy) and P9-2.5 (standing policy).
  Their tasks name them in "Depends on", so the scheduler waits for exactly those. Lane A does them first and pushes.
- The two lanes share only four logic files (`frontend/src/pages/case/CaseOverview.tsx`,
  `frontend/src/pages/agents/ModelsPanel.tsx`, `backend/di/services/actions/models.py`,
  `backend/di/services/screens/agents.py`) and the append-only registration files (`fields.py`, `forbidden.py`,
  `policy.py`, `worker.py`, `main.py`, `models/__init__.py`, the decision log). Keep changes there small; on a merge
  conflict, keep both sides.

## How the lanes meet

1. Lane A pushes `feature/plan-09-recover` after each of its phase gates, and as soon as P9-2.1, P9-2.4 and P9-2.5
   are merged.
2. Lane B merges `origin/feature/plan-09-recover` into `feature/plan-09-lane-b` whenever it is pushed (a merge, not a
   rebase), runs its checks, and pushes `feature/plan-09-lane-b` after each of its tasks' merges.
3. After each lane B phase gate, the integrator merges `feature/plan-09-lane-b` into `feature/plan-09-recover`, runs
   the full gate, folds `lane-B/PROGRESS.md` into `PROGRESS.md`, and pushes.
4. Nobody pushes to `main`. Each person pushes only their own lane branch.

## Guardrails for an unattended lane

Put these deny rules in `.claude/settings.local.json` (never committed) on the lane's machine, so no agent can push
another branch by force, rewrite history, or edit what must not change:

```json
{
  "permissions": {
    "deny": [
      "Bash(git reset --hard:*)",
      "PowerShell(git reset --hard:*)",
      "Bash(git rebase:*)",
      "PowerShell(git rebase:*)",
      "Bash(git stash:*)",
      "PowerShell(git stash:*)",
      "Bash(git checkout --:*)",
      "PowerShell(git checkout --:*)",
      "Bash(git clean:*)",
      "PowerShell(git clean:*)",
      "Edit(./fixtures/golden/**)",
      "Write(./fixtures/golden/**)",
      "Edit(./backend/migrations/versions/000*)",
      "Write(./backend/migrations/versions/000*)",
      "Edit(./backend/migrations/versions/001*)",
      "Write(./backend/migrations/versions/001*)",
      "Edit(./backend/migrations/versions/0020_*)",
      "Edit(./backend/migrations/versions/0021_*)",
      "Edit(./backend/migrations/versions/0022_*)",
      "Edit(./backend/migrations/versions/0023_*)",
      "Edit(./backend/migrations/versions/0024_*)",
      "Edit(./backend/migrations/versions/0025_*)",
      "Edit(./backend/migrations/versions/0026_*)",
      "Edit(./backend/migrations/versions/0027_*)",
      "Edit(./backend/migrations/versions/0028_*)",
      "Bash(git push --force:*)",
      "PowerShell(git push --force:*)"
    ]
  }
}
```

Lane B may push its own branch (`git push origin feature/plan-09-lane-b`), so plain `git push` is not denied there.

## Tools both lanes use

| Tool | What |
|---|---|
| `scripts/dev/plan-next.py --phases <list> --max 2` | the lane's ready tasks (`PLAN_RUN` for the lane's run folder) |
| `docs/agents/plans/09-run/WRITER-BRIEF.md` | what every writer follows |
| `scripts/dev/wt-check.sh <k> <tests>` | a writer's checks from its worktree, on its own database |
| `scripts/dev/lead-verify.sh [--suite] [--smoke] <tests>` | the lead's checks after a merge |
| `scripts/dev/plan-tick.py <task> <sha> "<checks>" "<note>"` | tick, progress row, log, commit message |
