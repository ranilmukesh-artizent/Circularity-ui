# Lane B: tool fleet and device (phases 3, 4, 5, 6)

For the developer running lane B (Mahizhan) and for his Claude Code lead. Read `README.md` in this folder first; this
file is everything else the lane needs. Lane A (phases 2, 7, 8) runs on the integrator's machine at the same time.

## 1. What this repo is (two minutes)

- **Circularity Decision Workbench** ("DI"): decides what to do with a returned asset (redeploy, resell, re-lease,
  recover parts, recycle) and hands the decision to the enterprise systems. Full stack: FastAPI and Postgres
  (`backend/`), React and TypeScript (`frontend/`), synthetic vendor mocks (`source-sim/`), all in Docker Compose.
- **Plan 9 builds Recover** on it: packs as data (one per industry segment), gates with evidence, a customer layer, one
  decider, an agent chain, and five segments. Lane B builds the two pilot segments: the tool-fleet asset management
  service (returns, service desk, contract refresh) and device trade-in and recommerce.
- **Parity is the first rule** (AGENTS.md): the industrial demo's 128 cases, RT-1048 and every golden test stay
  unchanged. Tool-fleet and device numbers may change only where a task says so, with a decision-log row and a
  before/after report in `docs/agents/plans/09-diffs/<task id>.md` (rule R8).
- **Read before anything else**: `AGENTS.md`, `CLAUDE.md`, then in `docs/agents/plans/09-agentic-platform.md` the
  "Agent briefing", "Operating rules" (R1 to R22), "Global Constraints", "Interface registry" and "Registry details",
  and "How to run this plan unattended".

## 2. What is already built (phases 0 and 1, on the branch you start from)

Every task below was re-tested by the integrator on a full stack before its commit (counts in
`docs/agents/plans/PROGRESS.md`).

| Registry | What | Where |
|---|---|---|
| I-1 | Pack format v1; tool fleet, device and industrial as pack files | `backend/di/services/modeler/pack.py`, `packs/*.json`, `packs/pack.schema.json` |
| I-2, I-3 | Gate catalogue (41 gates), evidence, batch hold, gate recheck job | `modeler/gates.py`, `modeler/evidence.py`, `packs/gates.catalogue.json`, `cases/gate_hold.py` |
| I-4 | Customer overlay: tighten only, diversions, blocked compliance skips, rebase; maker-checker | `modeler/overlay.py`, `actions/overlays.py`, `repositories/overlays.py` |
| I-5 | Queue planner port, named demand on live cases, re-plan job | `services/engine/queue.py`, `cases/named_demand.py`, `cases/replan.py` |
| I-6 | **One decider** `decide_case` and `Decision`: intake, re-evaluation, shadow and simulation all call it | `backend/di/services/cases/decide.py` |
| | Pack versions through the pipeline with maker-checker (`managePacks`, `approve.packs`) | `actions/packs.py`, `actions/pack_impact.py`, `repositories/packs.py` |
| I-20 | Case process layer: work items, SLA timers, My work, `case.needInfo` | `cases/process.py`, `actions/work.py`, `screens/mywork.py`, `frontend/src/pages/mywork/` |
| I-21 | `VALUERS` plug-ins and the standard valuer (value lines from the pack) | `modeler/valuers/__init__.py`, `valuers/standard.py`, `valuers/amount.py` |
| | Record match to the system of record, carbon with provenance, pack-driven views | `cases/record_match.py`, `modeler/carbon.py`, `modeler/kpis.py` |

Also from phase 0: `credentials.rotate` and other admin actions forbidden to agents
(`backend/di/services/agents/forbidden.py`), a what-if over the tool-fleet queue, the contract entitlement gate
(G-CON-1, switched on in the tool-fleet pack), and migrations 0029 to 0061 reserved: every task that adds a table finds
its migration file already there, empty and chained. Fill it idempotently (`IF NOT EXISTS`).

## 3. What lane B needs from lane A, and when

Only three phase 2 tasks, named in your tasks' "Depends on":
- **P9-2.1** stage chain runtime with typed stage records (I-7);
- **P9-2.4** hold policy with typed reasons in the pipeline (I-10);
- **P9-2.5** standing policy approves within thresholds (I-11).

Lane A builds these first and pushes `feature/plan-09-recover` as soon as they are merged. Until then the scheduler
shows only the lane B tasks that do not need them (P9-3.1, P9-3.21, P9-6.1 to start). When nothing is ready, merge
lane A's branch (section 6) and pick again.

## 4. Once, on your machine (about 20 minutes)

In Git Bash, from the folder you keep repos in:

```bash
git clone <the repo URL> Circularity-ui     # or, in an existing clone: cd Circularity-ui && git fetch origin
cd Circularity-ui
git checkout -b feature/plan-09-lane-b origin/feature/plan-09-recover
bash scripts/doctor.sh
docker compose up -d --build
bash scripts/dev/reset.sh
bash scripts/dev/wait-idle.sh
git push -u origin feature/plan-09-lane-b
```

- **Folder name** `Circularity-ui`: the scripts expect the Compose project `circularity-ui`. With another name, set
  `MAIN_PROJECT=<folder name, lower case>` for `scripts/dev/wt-check.sh`.
- **Docker memory**: 12 to 14 GB is enough. In `%UserProfile%\.wslconfig`: `[wsl2]` `memory=14GB`, and under
  `[experimental]` `autoMemoryReclaim=gradual`, so the VM gives memory back after test peaks.
- **No `.env` needed** for this lane: Ask falls back to rule-based answers, and tests never call a model.
- **Check**: `bash scripts/dev/status.sh`, then http://localhost:5173, sign in as `planner.a` with any password.
- **Settings for an unattended run**: a permission mode that does not prompt, and deny rules in
  `.claude/settings.local.json` for `git push --force`, `git reset --hard`, `git rebase`, `git stash`, `git clean`,
  `git checkout --`, and edits to `fixtures/golden/**` and migrations `0001` to `0028` (copy the integrator's list from
  README section "Guardrails" if you like).

## 5. Start the lane

Open Claude Code in the repo folder, Opus as the lead, and paste:

```
You are the lead of lane B of plan 9 on branch feature/plan-09-lane-b. Read AGENTS.md, CLAUDE.md,
docs/agents/plans/09-lanes/README.md, docs/agents/plans/09-lanes/lane-B.md, and in
docs/agents/plans/09-agentic-platform.md the sections "Operating rules", "Interface registry", "Registry details" and
"How to run this plan unattended". Then run that loop for phases 3, 4, 5 and 6 only, with the lane B settings in
lane-B.md section 6. Do not ask me anything mid-run: log, block and skip what you cannot do, and keep going until the
phase 6 gate is green. Report progress in docs/agents/plans/09-run/lane-B/RUN-LOG.md.
```

## 6. The lane B loop (the lead follows this)

Set once in every shell: `export PLAN_RUN=docs/agents/plans/09-run/lane-B MSYS_NO_PATHCONV=1`.

1. **Pick**: `python scripts/dev/plan-next.py --phases 3,4,5,6 --max 3`. Up to three writers at a time (two if Docker memory is tight).
   Add each picked task to `$PLAN_RUN/inflight.txt` as `<task id> w<k> <model> <time from date>`.
2. **Brief** each writer with the Agent tool: `subagent_type: general-purpose`, `model: sonnet` (`haiku` for a task that
   is only docs or a script's doc row), `isolation: "worktree"`, `run_in_background: true`, and this prompt:
   `You are writer <k> on plan 9, lane B. Your task: <task id> <title>. First run git merge --ff-only
   feature/plan-09-lane-b in your worktree, then read and follow docs/agents/plans/09-run/WRITER-BRIEF.md exactly (k =
   <k>, run branch feature/plan-09-lane-b, WT_BASE=feature/plan-09-lane-b).` Add a line or two of task-specific
   context (registry entries, R8 if numbers may change, R21 if it adds an approvable object).
3. **Read the report**, then `git show --stat <sha>`: only the task's files (plus tests and registration files), the
   subject starts with the task id, the red-first run is quoted.
4. **Merge**: `git cherry-pick -n <sha>`. On a conflict in an append-only file (`decision-log.md`, `.importlinter`,
   `forbidden.py`, `policy.py`, `fields.py`, `worker.py`, `main.py`, `models/__init__.py`), keep both sides. A
   conflict in a logic file means two tasks overlapped: `git cherry-pick --abort` and re-queue the task.
5. **Verify**: `bash scripts/dev/lead-verify.sh <the task's test files> <serial-only files the writer listed>`. Add
   `--suite` every third merge and before a gate; add `--smoke` when the task changes a page or the menu.
6. **Commit**: `python scripts/dev/plan-tick.py <task id> <sha> "<what lead-verify ran, with counts>" "<note>"`, then
   `git add -A backend frontend docs/agents` and `git commit -F $PLAN_RUN/.commit-msg.txt`. Before the commit,
   `git diff --cached | grep -E 'gsk_[A-Za-z0-9]{20,}'` must print nothing.
7. **Push**: `git push origin feature/plan-09-lane-b`.
8. **Retry once** on a red verify: send the failure (last 40 lines) to the same writer with `SendMessage`. On a second
   failure, unstage the task's files, add it to `$PLAN_RUN/blocked.txt` with the reason, and go on with other tasks.
9. **Sync with lane A** when the scheduler shows nothing ready, or once a day: `git fetch origin`,
   `git merge origin/feature/plan-09-recover`, then `bash scripts/dev/lead-verify.sh --suite`.
10. **Phase gate** (the task named "Phase N gate"): `bash scripts/dev/lead-verify.sh --suite --smoke`, the phase's
    serial-only test files, `bash scripts/dev/story-matrix.sh <N>`, then `reset.sh`, `wait-idle.sh`,
    `node frontend/scripts/smoke-p9-<N>.mjs http://localhost:5173` and the earlier phases' demo smokes, `reset.sh`.
    One review: a `general-purpose` agent on Opus reads the phase's commits against the Review Focus; check each
    finding in the code before acting. Tick the gate, add the counts to `$PLAN_RUN/PROGRESS.md`, commit, push, and add
    "phase N gate green, ready to merge" at the end of `$PLAN_RUN/RUN-LOG.md`.

## 7. Lessons from phases 0 and 1 (each one cost time)

- **Model first (R16 changed 25 Nov, by the person).** Agents reason with the model; rules are the safety net. Read
  the new R16 in the plan before you brief a task. In lane B this touches P9-4.3 (the intake reasoner of P9-2.18 reads
  fault text), P9-6.17 (the model writes the worked-question sentence; its numbers are checked) and every Compose or
  agent step. Writers follow the brief's "Model first" rule. A task that reads or writes language without the model
  is sent back.
- **Worktrees start from the default branch**: every writer must fast-forward to the lane branch first (the brief says
  so).
- **Private-database failures are not always real**: `wt-check.sh` runs on a fresh database without the synced
  Connection Fabric. Tests such as `test_screens_home.py::test_briefing[developer]`, `test_screens_reference.py`,
  `test_workflow_open_case.py` and `test_writes_access.py` fail there and pass on the main stack. Re-run them with
  `lead-verify.sh` before you believe a failure.
- **Browser smokes need `wait-idle.sh` after `reset.sh`**: the post-reset syncs delay instructions by two to three
  minutes, and RT-1048 times out without it.
- **A task can break another task's tests through shared pack data**: P9-1.11 switched on a gate in the tool-fleet pack
  and two overlay tests broke. Run `--suite` regularly; it caught that.
- **knip fails on an unused facade export**: every action needs a caller (rule R18). If the spec gives no button
  (agent-only), add a facade test that calls it.
- **Golden parity beats a reviewer's suggestion**: `fixtures/golden/workflow_writes.json` creates and publishes a
  decision workflow, so refusing that broke parity. Check the golden tests before tightening a demo action.
- **Writers skip red-first and docs unless told**: the brief now demands the quoted red run, current docs for any
  library, foreground checks only (no Monitor or timers: their leftover wake-ups flood the lead), no subagents.
- **Commit messages**: the subject at most 72 characters, a blank line, then the body. `plan-tick.py` refuses a writer
  commit that breaks this; rewrite the message and commit.
- **Demo reset** clears plan 9's tables (`pack_version`, `customer_overlay`, `work_item`, the flow `returned` mark) since
  P9-1.14. A new plan 9 table that holds demo state must be added to `backend/tests/starting.py` `reset()` in its task.
- **Timestamps**: write times from `date`, never from memory.

## 8. Cost and models

Opus only for the lead and the one reviewer per gate; Sonnet writers; Haiku for doc-only tasks. Never let a writer
start agents. One verify per merge, `--suite` every third merge: the 3-shard suite takes 8 to 10 minutes and a lot of
memory.

## 9. What lane B delivers

Tool-fleet returns (TF-01 … TF-16), the service desk (SD-01 … SD-09, SD-11), contract refresh (CR-01 … CR-08) and
device recommerce (DV-01 … DV-15), each story with its named test (R22) and its phase's demo smoke, every phase gate
green, merged by the integrator into `feature/plan-09-recover`.
