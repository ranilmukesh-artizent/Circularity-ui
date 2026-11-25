# Lane B: start here (a prompt for the lane B lead)

Paste this whole file into Claude Code (Opus) at the root of your clone, or say: "Read
docs/agents/plans/09-lanes/lane-B-start.md and do what it says." It is written to you, the lead of lane B.

---

## Who you are and what you do

You are the **lead of lane B** of plan 9 in the Circularity Decision Workbench repo. You do not write feature code
yourself. You pick ready tasks, brief **Sonnet writer subagents** (each in its own git worktree), verify what they
return, merge it one commit per task, and push. You run until the phase 6 gate is green, without asking the person
anything mid-run: log, block and skip what you cannot do.

- **Your phases:** 3 tool-fleet returns (22 tasks), 4 service desk (13), 5 contract refresh (9), 6 device recommerce
  (21). 65 tasks, every one specified in full in the plan.
- **Your branch:** `feature/plan-09-lane-b` (you create it from `origin/feature/plan-09-recover`). Push only it.
- **The other lane (A):** phases 2, 7, 8 on another machine, branch `feature/plan-09-recover`, run by the integrator,
  who merges your branch after each of your phase gates.

## Step 1: get the branch and the stack (once)

Your clone exists. In Git Bash at its root (folder name `Circularity-ui`, or set `MAIN_PROJECT` to the lower-case folder
name for `wt-check.sh`):

```bash
git fetch origin
git checkout -b feature/plan-09-lane-b origin/feature/plan-09-recover
bash scripts/doctor.sh
docker compose up -d --build          # rebuilds the images: plan 9 added Python libraries
bash scripts/dev/reset.sh
bash scripts/dev/wait-idle.sh
git push -u origin feature/plan-09-lane-b
```

- Docker memory: cap the WSL VM at about 14 GB in `%UserProfile%\.wslconfig` (`[wsl2]` `memory=14GB`; under
  `[experimental]` `autoMemoryReclaim=gradual`). Check `bash scripts/dev/status.sh` and http://localhost:5173
  (sign in as `planner.a`, any password).
- No `.env` is needed. Never read, print or commit one.
- Guardrails for the unattended run: copy the deny list from `docs/agents/plans/09-lanes/README.md` ("Guardrails")
  into `.claude/settings.local.json`, and use a permission mode that does not prompt.

## Step 2: read, in this order (about 15 minutes of reading for you, once)

| File | Why it matters to lane B |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | The repo map, how to run and test, the 15 golden rules (parity, the action pipeline, agents only hold for a person, never hand-edit `fixtures/golden/`), subagent rules. |
| `docs/agents/plans/09-lanes/README.md` | Who owns which phases, how the two lanes meet, guardrails, the shared tools. |
| `docs/agents/plans/09-lanes/lane-B.md` | Your lane in full: what is already built (registry entry to file), what you need from lane A and when, the exact loop with commands, lessons from phases 0 and 1. **Section 6 is your loop.** |
| `docs/agents/plans/09-agentic-platform.md` | The plan. Read "Operating rules" (R1-R22), "Global Constraints", "Interface registry" and "Registry details", "Review Focus", "How to run this plan unattended", and each task's spec under `#### P9-3.n` … `#### P9-6.n` when you brief it. |
| `docs/agents/plans/09-run/WRITER-BRIEF.md` | What every writer follows (red-first proof, foreground checks, no subagents, scope, commit format). You point writers at it. |
| `docs/agents/dos-and-donts.md` (Tests) and `docs/agents/learnings.md` (last section, 25 Nov) | How to size checks (per merge: task tests; full suite at gates), `wait-idle.sh` before smokes, and the nine lessons of the first unattended night. |
| `docs/agents/research/2026-11-platform/` (A for TF, SD, CR, DV stories; B §5 gates; E libraries; G agent design) | The stories your tasks cite. Read the rows a task names, not the whole folder. |

## Step 3: what is already built that you build on

All on your starting branch, each verified on a full stack before it was committed:

- **Phase 0** (17 tasks and gate): gate script, story matrix, catalogue hygiene, carbon factors, model chain, workflow
  schema and export, autopilot behind a setting, mapping save, guardrail types, flow "returned" mark, role matrix,
  read-only sources, what-if over the tool-fleet queue.
- **Phase 1** (15 tasks and gate): pack format v1 (I-1, `backend/di/services/modeler/pack.py`, `packs/*.json`), gate
  catalogue and evidence (I-2, I-3), customer overlay (I-4), queue planner (I-5), **the one decider `decide_case`
  (I-6, `backend/di/services/cases/decide.py`)**, pack versions with maker-checker, case process layer and My work
  (I-20), standard valuer and `VALUERS` (I-21), record match, carbon with provenance, pack-driven views, phase 1 demo
  smoke.
- **Phase 2 so far** (lane A): stage chain (I-7, P9-2.1), agent loop on Pydantic AI (I-8, P9-2.2), model router (I-9,
  P9-2.3), **hold policy (I-10, P9-2.4)**, exception assistant (P9-2.10). **Standing policy (I-11, P9-2.5)** is being
  built now; 27 of your 65 tasks wait on it. Lane A pushes it as soon as it is verified.
- Migrations 0029 to 0061 are reserved by name: a task that adds a table fills its existing empty file
  (idempotent, `IF NOT EXISTS`).

## Step 4: where to start

```bash
export PLAN_RUN=docs/agents/plans/09-run/lane-B MSYS_NO_PATHCONV=1
python scripts/dev/plan-next.py --phases 3,4,5,6 --max 3
```

Today that prints **P9-3.1, P9-3.21 and P9-6.1**: brief three writers at once. As tasks merge, more open inside phases
3 and 6 (the scheduler orders tasks that share logic files and lets the rest run side by side). When it shows nothing,
`git fetch origin && git merge origin/feature/plan-09-recover` (lane A's latest, e.g. P9-2.5), verify, and pick again.

## Step 5: run fast and in parallel (the rules that cost us hours when broken)

- **Parallel writers:** up to 3 Sonnet writers at a time (2 if Docker memory is tight); each in its own worktree
  (`isolation: "worktree"`, `run_in_background: true`). Haiku for a task that is only docs. Opus only for you and the
  one reviewer per phase gate. Writers never start agents.
- **Keep writers busy:** brief the next ready task the moment a writer returns, before you verify the returned one.
- **Light checks per merge (3 to 5 minutes):** `bash scripts/dev/lead-verify.sh <the task's tests> <its serial-only
  files>`. It reapplies reserved migrations, restarts, runs those tests, lint and web, and prints each failure's error
  and line. The full suite (`--suite`, about 10 minutes) every third merge and at gates; browser smokes (`--smoke` and
  the phase's demo smoke) only at gates. **Never run the full suite after every merge.**
- **Writers verify on their own database** (`scripts/dev/wt-check.sh <k> <tests>`, foreground, long timeout). Their
  failures on fresh databases are not always real: re-run with `lead-verify.sh` before you believe one (the lists are in
  lane-B.md section 7).
- **One merge at a time on your main stack:** never change the main tree while a check or smoke runs on it.

## Step 6: tracing and logging (so anyone can follow what happened)

- **Run log:** append one line per event to `docs/agents/plans/09-run/lane-B/RUN-LOG.md`: dispatch, merge, retry,
  block, gate. Times from `date`, never from memory.
- **In flight and blocked:** keep `lane-B/inflight.txt` (task, writer, model, time) and `lane-B/blocked.txt` (task,
  reason, decision needed) current.
- **Per task:** `python scripts/dev/plan-tick.py <task> <writer sha> "<what lead-verify ran, with counts>" "<note>"`
  ticks the box, adds the row to `lane-B/PROGRESS.md`, logs it, and writes the commit message (the writer's message, a
  "Verified by the lead" line with counts, both trailers) to `lane-B/.commit-msg.txt`. Then
  `git add -A backend frontend docs/agents`, check `git diff --cached | grep -E 'gsk_[A-Za-z0-9]{20,}'` prints nothing,
  `git commit -F docs/agents/plans/09-run/lane-B/.commit-msg.txt`, `git push origin feature/plan-09-lane-b`.
- **Test output:** `lead-verify.sh` keeps the full api output in `test-results/lead-verify-api.log`.
- **Decisions you take without the person:** one line each in `lane-B/RUN-LOG.md`, marked "Decision:".

## Step 7: phase gates and handing over

At each "Phase N gate" task: `bash scripts/dev/lead-verify.sh --suite --smoke <the phase's serial files>`,
`bash scripts/dev/story-matrix.sh <N>`, then `reset.sh`, `wait-idle.sh`, `node frontend/scripts/smoke-p9-<N>.mjs
http://localhost:5173` (and the earlier phases' demo smokes), `reset.sh`. One Opus `general-purpose` reviewer reads
the phase's commits against the Review Focus; check each finding in the code; fix real ones through a writer. Tick the
gate, add the counts to `lane-B/PROGRESS.md`, commit, push, and end `lane-B/RUN-LOG.md` with
"Phase N gate green, ready to merge". The integrator merges it into `feature/plan-09-recover`.

## Never

Push any branch but `feature/plan-09-lane-b`, force-push, rebase, stash, reset, or `checkout --`. Edit tasks of phases
1, 2, 7 or 8, `fixtures/golden/`, or migrations 0001 to 0028. Change a number the industrial demo shows. Let an agent
approve, publish, override, decline or change access. Put a client, prospect or vendor name in code, data or UI text.
