# Lane B: tool fleet and device (phases 3, 4, 5, 6)

For the person running lane B (Mahizhan) and for their Claude Code lead. Read `README.md` here first.

## Once, on your machine (about 20 minutes)

In Git Bash, from the folder you keep repos in:

```bash
git clone <the repo URL> Circularity-ui     # or, in an existing clone: git fetch origin
cd Circularity-ui
git checkout -b feature/plan-09-lane-b origin/feature/plan-09-recover
bash scripts/doctor.sh
docker compose up -d --build
bash scripts/dev/reset.sh
```

- Keep the folder name `Circularity-ui`: the scripts expect the Docker Compose project `circularity-ui`. With another
  folder name, set `MAIN_PROJECT=<your folder name, lower case>` for `scripts/dev/wt-check.sh`.
- Docker Desktop needs about 12 to 14 GB. In `%UserProfile%\.wslconfig`, `[wsl2] memory=14GB` is enough.
- You need no `.env` for this lane (Ask falls back to its rule-based answers; tests never call a model).
- Check the stack: `bash scripts/dev/status.sh`, then open http://localhost:5173 and sign in as `planner.a`.

## Start the lane

Open Claude Code in the repo folder (Opus as the lead) and paste:

```
You are the lead of lane B of plan 9 on branch feature/plan-09-lane-b. Read docs/agents/plans/09-lanes/README.md,
docs/agents/plans/09-lanes/lane-B.md, and in docs/agents/plans/09-agentic-platform.md the section "How to run this
plan unattended". Then run that loop for phases 3, 4, 5 and 6 only, with the lane B settings in lane-B.md. Do not ask
me anything mid-run; log, skip blocked tasks, and keep going until phase 6's gate is green.
```

## Lane B settings (the lead reads these)

- **Pick tasks** with `PLAN_RUN=docs/agents/plans/09-run/lane-B python scripts/dev/plan-next.py --phases 3,4,5,6 --max 2`.
  At most 2 writers at a time.
- **Run files**: `docs/agents/plans/09-run/lane-B/` (`inflight.txt`, `blocked.txt`, `RUN-LOG.md`, `PROGRESS.md`).
  Write lane B progress rows to `lane-B/PROGRESS.md`, not to `docs/agents/plans/PROGRESS.md`. Take times from `date`.
- **Writers** get `docs/agents/plans/09-run/WRITER-BRIEF.md` with the run branch `feature/plan-09-lane-b` and
  `WT_BASE=feature/plan-09-lane-b` for `wt-check.sh`. Agent tool: `isolation: "worktree"`, `run_in_background: true`,
  model Sonnet (Haiku for doc-only tasks).
- **Verify each merge** on your main stack: the task's own tests and the serial-only files it names through
  `scripts/dev/api-test.sh`, the golden and parity tests (`test_po_golden.py`, `test_engine.py`,
  `test_paths_agree.py`, `test_order_invariant.py`), `lint.sh`, and `web-check.sh` when `frontend/` changed. Run the
  4-shard `parallel-suite.sh` every 3 merges and at each phase gate.
- **Tick and record**: tick the task's box in the plan file, add the row to `lane-B/PROGRESS.md`, one commit per task.
- **Waiting on lane A**: tasks that need P9-2.1, P9-2.4 or P9-2.5 show as not ready until those are merged. When the
  scheduler shows nothing ready, run `git fetch origin` and `git merge origin/feature/plan-09-recover`, re-run the
  checks, and pick again.
- **Push** `feature/plan-09-lane-b` after each merge (`git push origin feature/plan-09-lane-b`). Never push another
  branch, never force-push.
- **Phase gates** 3, 4, 5, 6: the fast gate of the run section (lint, web, parallel suite, the phase's serial files,
  story matrix, `reset.sh`, `wait-idle.sh`, the phase's demo smoke, `reset.sh`), then tell the integrator the branch
  is ready to merge (a line at the end of `lane-B/RUN-LOG.md`, then push).
- **Never** edit tasks of phases 1, 2, 7 or 8, `fixtures/golden/`, or migrations 0001 to 0028.

## What lane B delivers

Tool-fleet returns (TF-01 … TF-16), the service desk (SD-01 … SD-09, SD-11), contract refresh (CR-01 … CR-08) and
device recommerce (DV-01 … DV-15), each story with its named test and its phase's demo smoke.
