# Lane B: start here (a prompt for the lane B lead)

Paste this whole file into Claude Code (Opus) at the root of your clone, or say: "Read
docs/agents/plans/09-lanes/lane-B-start.md and do what it says." It is written to you, the lead of lane B.
Last updated 25 Nov 2026, 17:30 IST (model-first agents; agents never delete or approve; the ten-stage journey).

---

## Who you are and what you do

You are the **lead of lane B** of plan 9 in the Circularity Decision Workbench repo. You do not write feature code
yourself. Your loop:
1. Pick the ready tasks.
2. Brief **Sonnet writer subagents**, each in its own git worktree.
3. Verify what each writer returns.
4. Merge it as one commit per task, and push.

Run until the phase 6 gate is green, without asking the person anything mid-run. What you cannot do, you log, block and
skip.

- **Your phases:** 3 tool-fleet returns (22 tasks), 4 service desk (13), 5 contract refresh (9), 6 device recommerce
  (21). That is 65 tasks, every one specified in full in the plan.
- **Your branch:** `feature/plan-09-lane-b`, created from `origin/feature/plan-09-recover`. Push only it.
- **The other lane (A):** phases 2, 7 and 8, on another machine, on branch `feature/plan-09-recover`. It is run by the
  integrator, who merges your branch after each of your phase gates.

## The three rules the person set on 25 Nov (read before you brief anything)

1. **Model first (plan rule R16, rewritten).** Agents reason with the language model; code is the safety net.
   - Anything that reads text, interprets evidence, drafts, explains, plans or writes a question runs on the model
     through `AgentLoop` (I-8, Pydantic AI, `backend/di/services/agents/pydantic_ai_loop.py`), as typed output, whenever
     the router (I-9) has a model.
   - Code checks every model output and always wins: validators, locked guardrails, gates, the forbidden list, the
     hold policy, and that every cited source exists. A failed check gets a `ModelRetry`, then the deterministic path
     answers (`by_model: false`).
   - The model may add a concern, a hold or a question. It never removes one, and never invents a computed number.
   - Values, prices, gates, calibrated confidence and queue plans stay computed by code or trained models.
   - Tests use `FunctionModel` or `TestModel`, never a live provider. Each model task tests four things: a draft
     accepted, a draft refused by a check, the retry then fallback, and no model.
   - **Never write "model optional, rules first".** A task that reads or writes language without the model is sent
     back.
2. **Agents create, read and update; they never delete or approve.**
   - Every delete, discard, revert, cancel, approve, publish, reject, promote, override, decline, rollback, retire or
     release action is in `backend/di/services/agents/forbidden.py` `FORBIDDEN_ACTIONS`.
   - `di.main` refuses to start when one is missing (`check_person_only`).
   - A new action of that kind joins the list in the same commit.
3. **The ten-stage journey.** Lane A adds stage agents for lease end, return authorised and transit (P9-2.20), and
   splits analytics into outcome and reconcile (P9-2.21). Stage ids may grow under you: read `STAGE_IDS` in
   `backend/di/services/agents/stage_context.py`, never hard-code eight.

## Step 1: get the branch and the stack (once)

In Git Bash at the root of your clone:

```bash
git fetch origin
git checkout -b feature/plan-09-lane-b origin/feature/plan-09-recover   # or, if it exists: git checkout feature/plan-09-lane-b && git merge origin/feature/plan-09-recover
bash scripts/doctor.sh
docker compose up -d --build          # rebuilds the images: plan 9 added Python libraries
bash scripts/dev/reset.sh
bash scripts/dev/wait-idle.sh
git push -u origin feature/plan-09-lane-b
```

- **Docker memory:** cap the WSL VM at about 14 GB in `%UserProfile%\.wslconfig`: under `[wsl2]` set `memory=14GB`,
  and under `[experimental]` set `autoMemoryReclaim=gradual`. Check `bash scripts/dev/status.sh` and
  http://localhost:5173 (sign in as `planner.a`, any password).
- **The repo folder:** if it isn't `Circularity-ui`, set `MAIN_PROJECT` to its lower-case name for `wt-check.sh`.
- **No `.env` is needed.** Never read, print or commit one.
- **Guardrails for the unattended run:** copy the deny list from `docs/agents/plans/09-lanes/README.md` ("Guardrails")
  into `.claude/settings.local.json`, and use a permission mode that doesn't prompt.

## Step 2: read, in this order (about 20 minutes, once)

| File | Why it matters to lane B |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | The repo map, how to run and test, the 15 golden rules (parity, the action pipeline, agents only hold for a person, never hand-edit `fixtures/golden/`), subagent rules, Git Bash pitfalls. |
| `docs/agents/plans/09-lanes/README.md` | Who owns which phases, how the two lanes meet, guardrails, the shared tools. |
| `docs/agents/plans/09-lanes/lane-B.md` | Your lane in full: what is already built (registry entry to file), what you need from lane A, the exact loop with commands, the lessons. **Section 6 is your loop; section 7 the lessons.** |
| `docs/agents/plans/09-agentic-platform.md` | The plan. Read "Operating rules" (R1-R22; **R16 is new**), "Global Constraints", "Interface registry" and "Registry details", "Review Focus", "How to run this plan unattended", and each task's spec under `#### P9-3.n` … `#### P9-6.n` when you brief it. P9-2.18 shows what a model-first stage looks like. |
| `docs/agents/plans/09-run/WRITER-BRIEF.md` | What every writer follows: red-first proof, foreground checks, no subagents, scope, the **"Model first"** bullet, the commit format. You point writers at it. |
| `docs/agents/dos-and-donts.md` (Tests) and `docs/agents/learnings.md` (last section, 25 Nov) | How to size checks (task tests per merge, the full suite at gates), `wait-idle.sh` before smokes, and the lessons of the first unattended night. |
| `docs/agents/decision-log.md` (last rows) | Decisions already taken (model first, carbon formula, My work, G-CON-1 and others). Don't undo one without a new row. |
| `docs/agents/research/2026-11-platform/` | The stories your tasks cite: A for the TF, SD, CR and DV stories, B §5 for gates, E for libraries, G for agent design. Read only the rows a task names, not the whole folder. |
| `docs/reference/agent-first-workbench-pr.md` | The ten-stage journey and the card catalogue the product aims at. It's a concept; follow our kit. |

## Step 3: what is already built that you build on

Every item below is on `origin/feature/plan-09-recover`, verified on a full stack before it was committed:

- **Phase 0** (17 tasks and the gate): the gate script, the story matrix, catalogue hygiene, carbon factors, the model
  chain, the workflow schema and export, autopilot behind a setting, mapping save, guardrail types, the flow
  "returned" mark, the role matrix, read-only sources, and what-if over the tool-fleet queue.
- **Phase 1** (15 tasks and the gate):
  - pack format v1 (I-1, `backend/di/services/modeler/pack.py`, `packs/*.json`);
  - the gate catalogue and evidence (I-2, I-3) and the customer overlay (I-4);
  - the queue planner (I-5);
  - **the one decider `decide_case`** (I-6, `backend/di/services/cases/decide.py`);
  - pack versions with maker-checker, and the case process layer with My work (I-20,
    `backend/di/services/cases/process.py`);
  - the standard valuer and `VALUERS` (I-21);
  - record match, carbon with provenance, pack-driven views, and the phase 1 demo smoke.
- **Phase 2 so far (lane A, 10 of 21):**
  - the stage chain (I-7, P9-2.1, `backend/di/services/agents/chain.py`, `stages/*.py`);
  - the agent loop on Pydantic AI (I-8, P9-2.2);
  - the model router with budgets (I-9, P9-2.3, `backend/di/services/llm/router.py`);
  - **the hold policy** (I-10, P9-2.4, `backend/di/services/actions/hold.py`);
  - **the standing policy** (I-11, P9-2.5);
  - run tracing and the run view (I-12, P9-2.6, `frontend/src/pages/agents/RunView.tsx`);
  - **the configuration agent, model first** (I-13, P9-2.7, `backend/di/services/agents/config_agent.py`,
    `playbooks/pack_author.py`): the example to copy for any model drafter;
  - the queue stage (P9-2.8);
  - the exception assistant (P9-2.10).
  Coming in lane A: P9-2.9, 2.11-2.16, **2.18** (stage agents reason with the model), **2.19** (exception and fraud
  review by the model), **2.20 and 2.21** (the ten-stage journey).
- **Migrations:** 0029 to 0061 are reserved by name. A task that adds a table fills its existing empty file
  (idempotent, `IF NOT EXISTS`). Lane A owns 0062 onward; if you need a new one, ask in `lane-B/blocked.txt`.

## Step 4: where to start

```bash
export PLAN_RUN=docs/agents/plans/09-run/lane-B MSYS_NO_PATHCONV=1
python scripts/dev/plan-next.py --phases 3,4,5,6 --max 3
```

- **Brief three writers at once** from what it prints (P9-3.1, P9-3.21 and P9-6.1 at the start). As tasks merge, more
  open inside phases 3 and 6: the scheduler orders tasks that share logic files and lets the rest run side by side.
- **When it shows nothing:** run `git fetch origin && git merge origin/feature/plan-09-recover` to take lane A's latest,
  verify, and pick again.
- **Merge lane A at least daily** anyway, so its rule and stage changes reach you early.

## Step 5: run fast and in parallel (the rules that cost us hours when broken)

- **Parallel writers:** up to 3 Sonnet writers at a time, or 2 if Docker memory is tight. Each one:
  - runs in its own worktree (`isolation: "worktree"`, `run_in_background: true`);
  - starts with `git merge --ff-only feature/plan-09-lane-b`, because Agent worktrees start from the default branch.
  Use Haiku for a task that is only docs, and Opus only for you and the one reviewer per phase gate. Writers never
  start agents.
- **Keep writers busy:** brief the next ready task the moment a writer returns, before you verify the returned one.
- **Light checks per merge (3 to 5 minutes):** `bash scripts/dev/lead-verify.sh <the task's tests> <its serial-only
  files>`. It reapplies the reserved migrations, restarts, runs those tests, lint and web, and prints each failure's
  error and line.
  - Run the full suite (`--suite`, about 10 minutes) every third merge and at gates.
  - Run the browser smokes (`--smoke` and the phase's demo smoke) only at gates.
  - **Never run the full suite after every merge.**
- **Writers verify on their own database** (`scripts/dev/wt-check.sh <k> <tests>`, foreground, long timeout). Their
  failures on a fresh database aren't always real: re-run with `lead-verify.sh` before you believe one (lane-B.md
  section 7 lists them).
- **The synced stack:** the main stack has about 428 open source conflicts. Agent-chain tests use
  `pytestmark = pytest.mark.usefixtures("no_synced_conflicts")` (in `backend/tests/conftest.py`).
- **One merge at a time on your main stack:** never change the main tree while a check or smoke runs on it.
- **When a writer report seems off, read the code before you merge.** Check that a model task really calls
  `AgentLoop` with typed output.

## Step 6: codebase best practices (what reviewers check)

- **Written for agents first:**
  - each module starts with a docstring: what it does, `Owns:`, `Never does:`, and the registry entry it implements;
  - one responsibility per file, small files;
  - mypy strict and TypeScript strict;
  - no dead code, TODOs or commented-out code.
- **Reuse before you create:** search for an interface registry name (I-1 … I-21) and the existing helpers first.
- **Every write goes through the action pipeline** (`POST /api/actions/{id}`, `invoke()` in the web app). Pages call
  only `frontend/src/api/*.ts`. Access is enforced on the server.
- **Parity:** no number or text the industrial demo shows may change (`fixtures/golden/`, the 128 cases, RT-1048). Never
  hand-edit golden files.
- **Pack data, not code:** industry words, thresholds, owners and sample prompts live in `packs/*.json`, and the code
  stays generic.
- **Security red first (R21):** maker is never checker, agents are refused forbidden actions, and the tenant boundary
  holds. Each of these gets a failing test before the code.
- **Up-to-date docs:** before code against a library (Pydantic AI, LightGBM, lifelines, rapidfuzz, xyflow), the writer
  reads its current docs and names them in the report.
- **No client, prospect or vendor name** in code, data or UI text. All systems are synthetic mocks. No personal data:
  asset keys are serials or salted hashes.
- **Commits:** one per task, a subject of 72 characters or fewer, a blank line, a body (`plan-tick.py` enforces this).
  Scan for `gsk_` keys before every commit and push.
- **Legal, compliance and licence text** (contracts, consent, wipe certificates, export control) is marked for review
  by Kinective's Legal team.

## Step 7: tracing and logging (so anyone can follow what happened)

- **Run log:** append one line per event to `docs/agents/plans/09-run/lane-B/RUN-LOG.md`: dispatch, merge, retry,
  block, gate. Take times from `date`, never from memory.
- **In flight and blocked:** keep `lane-B/inflight.txt` (task, writer, model, time) and `lane-B/blocked.txt` (task,
  reason, decision needed) current.
- **Per task:**
  1. `python scripts/dev/plan-tick.py <task> <writer sha> "<what lead-verify ran, with counts>" "<note>"` ticks the
     box, adds the row to `lane-B/PROGRESS.md`, logs it, and writes the commit message to `lane-B/.commit-msg.txt`.
  2. `git add -A backend frontend source-sim docs/agents`
  3. Check that `git diff --cached | grep -E 'gsk_[A-Za-z0-9]{20,}'` prints nothing.
  4. `git commit -F docs/agents/plans/09-run/lane-B/.commit-msg.txt`
  5. `git push origin feature/plan-09-lane-b`
- **In the product:** model and tool calls are spans (`di.core.tracing`, P9-2.6) visible in the run view. Keep
  `trace_content` off by default, and never log a secret or a sample value that is not masked.
- **Test output:** `lead-verify.sh` keeps the full api output in `test-results/lead-verify-api.log`.
- **Decisions you take without the person:** one line each in `lane-B/RUN-LOG.md`, marked "Decision:".

## Step 8: phase gates and handing over

At each "Phase N gate" task:
1. Run `bash scripts/dev/lead-verify.sh --suite --smoke <the phase's serial files>`.
2. Run `bash scripts/dev/story-matrix.sh <N>`.
3. Run `reset.sh`, then `wait-idle.sh`, then `node frontend/scripts/smoke-p9-<N>.mjs http://localhost:5173` and the
   earlier phases' demo smokes, then `reset.sh` again.
4. One Opus `general-purpose` reviewer reads the phase's commits against the Review Focus, R16 and the never-delete
   rule. Check each finding in the code, and fix the real ones through a writer.
5. Tick the gate, add the counts to `lane-B/PROGRESS.md`, commit and push.
6. End `lane-B/RUN-LOG.md` with "Phase N gate green, ready to merge". The integrator merges it into
   `feature/plan-09-recover`.

## Never

- Push any branch but `feature/plan-09-lane-b`, force-push, rebase, stash, reset, or `checkout --`.
- Edit tasks of phases 1, 2, 7 or 8, `fixtures/golden/`, or migrations 0001 to 0028.
- Change a number the industrial demo shows.
- Let an agent delete, approve, publish, override, decline or change access.
- Put a client, prospect or vendor name in code, data or UI text.
