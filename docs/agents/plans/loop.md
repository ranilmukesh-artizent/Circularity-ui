# Plan 0: the agent loop Implementation Plan

> **For agentic workers:** this plan is done by a person or one supervised session, not by the loop itself. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** a Ralph-style loop that works through plans 1–5 one task per iteration, with a test gate outside the model,
a commit and a report line per task, and hard stops.

**Architecture:** `scripts/dev/loop.ps1` runs on the Windows host (where the `claude` CLI is). Each iteration starts a
fresh headless session (`claude -p`) with `docs/agents/plans/PROMPT.md`; the session does one unchecked task and stages
its changes. The loop then runs the gate (`scripts/dev/gate.sh`, inside WSL), and only on green commits with the
session's message. Red, a `BLOCKED.md`, a `STOP` file or the iteration cap ends the loop. Push happens only after a
plan's phase gate.

**Tech Stack:** PowerShell 5.1, Claude Code CLI headless mode, bash in WSL Ubuntu-24.04, the `scripts/dev/*.sh` scripts.

**Spec:** `docs/agents/plans/00-overview.md`; research notes below.

## Why this loop, not the alternatives (decision, 20 Nov 2026)

- Official `ralph-loop` plugin (anthropics/claude-plugins-official, Apache-2.0): a Stop hook that re-feeds the prompt in
  the *same* session; the only stop rule is an exact `<promise>` string the model writes, or `--max-iterations`
  (default unlimited); its hook needs bash, which is unreliable on this Windows host. Rejected: no external gate, no
  fresh context.
- Ralphy (michaelshimeles/ralphy, MIT): closest fit (task list, tests, per-task commit, retries), but auto-commits by
  default, runs tests itself with its own config, and its parallel mode would share one Postgres. Rejected for now.
- GSD / GSD Core (open-gsd/gsd-core, MIT; original archived Jun 2026): discuss→plan→execute→verify with parallel
  fresh-context executors; built for greenfield phases; its docs recommend skipping permissions. Rejected.
- Chosen: Huntley's original form (fresh `claude -p` per iteration over a prompt file), with the gate and commit done by
  the script, not the model. Never use `--dangerously-skip-permissions`.

## Global Constraints

- The loop never pushes to `main`, never force-pushes, never edits `.env`, never deletes branches.
- One api pytest at a time (`scripts/dev/lib.sh` `api_lock`); the gate uses the scripts, not raw `docker compose exec`.
- Iteration cap default 10 (`-MaxIterations`), `claude -p --max-turns 80` per iteration.
- Every iteration's transcript goes to `.loop/logs/<plan>-<n>.json` (git-ignored).

## Review Focus

1. The session commits on its own → the loop must detect a new commit made during the iteration and stop with BLOCKED.
2. The session touches files outside the repo or `.env` → gate fails (`git status` check) and nothing is committed.
3. The gate passes but the task box was not ticked → treat as no progress; two in a row → BLOCKED.
4. The stack is down (api unhealthy) → gate reports "stack down", loop stops without blaming the task.
5. A plan file is edited by the session beyond ticking its own box → gate fails (diff of the plan file allows only `- [ ]` → `- [x]` on one task).

---

### Task 1: the prompt and the progress log

**Files:**
- Create: `docs/agents/plans/PROMPT.md`, `docs/agents/plans/PROGRESS.md`
- Modify: `.gitignore` (add `.loop/`)

**Interfaces:**
- Produces: the session contract the loop relies on: the session (a) reads `AGENTS.md`, `00-overview.md` and the plan
  named in `.loop/CURRENT_PLAN`; (b) does the first task whose boxes are not all ticked, only that task; (c) runs that
  task's own test commands; (d) ticks the task's boxes; (e) appends one line to `PROGRESS.md`
  (`| date | plan | task | tests run | result |`); (f) stages everything with `git add` of the files it changed; (g) writes
  the commit message to `.loop/COMMIT_MSG` (first line ≤ 72 chars, the repo's attribution trailer last); (h) never
  runs `git commit` or `git push`; (i) if it cannot finish, writes `BLOCKED.md` at the repo root with what and why;
  (j) ends its last message with exactly one of `LOOP:TASK_DONE`, `LOOP:PLAN_DONE`, `LOOP:BLOCKED`.

- [ ] **Step 1:** write `PROMPT.md` stating (a)–(j) as numbered rules, plus: use the skills `test-driven-development`,
  `systematic-debugging` on any failure, `verification-before-completion` before the final line.
- [ ] **Step 2:** create `PROGRESS.md` with the table header only; add `.loop/` to `.gitignore`.
- [ ] **Step 3:** commit (`docs: loop prompt and progress log`).

### Task 2: the gate

**Files:**
- Create: `scripts/dev/gate.sh`
- Test: `scripts/dev/gate.test.sh`

**Interfaces:**
- Consumes: `lib.sh` (`api_lock`, `wait_healthy`).
- Produces: `bash scripts/dev/gate.sh <plan-file>` → exit 0 green, 1 red, 2 stack down; prints a ≤ 30-line summary.
  It runs: `wait_healthy` (2 if not), `web-check.sh`, then the api tests listed on the plan's `Gate:` line
  (one line in each plan header, e.g. `Gate: tests/test_jobs.py tests/test_worker.py`) through `api-test.sh`, then
  `git diff --cached --name-only` must not contain `.env*`, and the plan file's staged diff may only tick boxes.

- [ ] **Step 1:** write `gate.test.sh` with three cases against a throwaway plan in `/tmp/gate-fixture` (not in the
  repo): staged `.env` → exit 1; a staged plan edit that changes text, not just a box → exit 1; a clean staged change →
  exit 0 (stub `web-check.sh`/`api-test.sh` via `GATE_WEB` and `GATE_API` env vars pointing at `true`).
- [ ] **Step 2:** run it; expect failures (script missing).
- [ ] **Step 3:** implement `gate.sh`; `GATE_WEB`/`GATE_API` default to the real scripts.
- [ ] **Step 4:** run `gate.test.sh`; expect 3 passes. Commit.

### Task 3: the loop

**Files:**
- Create: `scripts/dev/loop.ps1`
- Test: `scripts/dev/loop.test.ps1`

**Interfaces:**
- Consumes: `PROMPT.md` contract (Task 1), `gate.sh` (Task 2).
- Produces: `powershell -File scripts/dev/loop.ps1 -Plan docs/agents/plans/01-b17c.md [-MaxIterations 10] [-MaxTurns 80] [-Claude claude]`.
  Per iteration: stop if `STOP` or `BLOCKED.md` exists; record `HEAD`; write `.loop/CURRENT_PLAN`; run
  `& $Claude -p (Get-Content PROMPT.md -Raw) --max-turns $MaxTurns --output-format json --permission-mode acceptEdits --allowedTools <list>`
  into `.loop/logs/`; if `HEAD` moved → BLOCKED ("session committed"); run the gate through
  `wsl -d Ubuntu-24.04 -u root -- bash <repo>/scripts/dev/gate.sh <plan>`; green → `git commit -F .loop/COMMIT_MSG`
  and append `total_cost_usd` from the JSON to the PROGRESS line; red → write `BLOCKED.md` with the gate output and
  stop; `LOOP:PLAN_DONE` → run `full-suite.sh` and the smoke scripts (phase gate), then `git push origin HEAD` only if
  the branch is not `main`, then stop.
  `--allowedTools`: `Read,Edit,Write,Glob,Grep,Skill,Bash(git add:*),Bash(git status:*),Bash(git diff:*)` plus
  `PowerShell(wsl -d Ubuntu-24.04 -u root -- bash *scripts/dev/*:*)` and `PowerShell(node scripts/*:*)`.
- [ ] **Step 1:** write `loop.test.ps1`: a stub `-Claude` script that ticks one box, stages a file and writes
  `COMMIT_MSG` → one commit appears in a temp git repo; a stub that runs `git commit` itself → `BLOCKED.md`; a stub with
  a red gate (`GATE_*` = `false`) → no commit and `BLOCKED.md`; `STOP` file → zero iterations.
- [ ] **Step 2:** run; expect failures. **Step 3:** implement `loop.ps1`. **Step 4:** run; expect 4 passes. Commit.

### Task 4: supervised dry run

- [ ] **Step 1:** add the `Gate:` line to plans 1–5 (already present below; check).
- [ ] **Step 2:** run `loop.ps1 -Plan docs/agents/plans/01-b17c.md -MaxIterations 1` with the user watching.
- [ ] **Step 3:** review the commit, the PROGRESS line and the log with the user; adjust `PROMPT.md` ("signs") if needed. Commit.
