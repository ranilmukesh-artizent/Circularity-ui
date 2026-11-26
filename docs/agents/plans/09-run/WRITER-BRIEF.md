# Plan 9 writer brief (the lead points every writer here)

You are writer `<k>` on plan 9 of the Circularity repo, in your own git worktree, doing exactly one task. The lead
named `<k>` and the task in your prompt.

## Step 0, before anything else

Your worktree may start from the default branch. Run `git merge --ff-only <run branch>` (PowerShell tool for git): the
run branch your lead named, `feature/plan-09-recover` unless the prompt says otherwise (lane B:
`feature/plan-09-lane-b`). It must succeed; if not, stop and report. In lane B, also set `WT_BASE` to that branch for
`wt-check.sh`.

## Read

- `AGENTS.md` and `CLAUDE.md`.
- In `docs/agents/plans/09-agentic-platform.md`:
  - the sections "Agent briefing", "Operating rules", "Standard task cycle", "Global Constraints", "Interface
    registry" (and "Registry details") and "Review Focus";
  - your task's spec under `#### <task id>`.
- Every file in the spec's **Files** list.
- The stories and research the spec cites (`docs/agents/research/2026-11-platform/`: A and B stories, E libraries,
  G agent design).

## Work: the standard task cycle S1–S6, changed for the parallel run

- **Red first is checked.** Write the spec's tests first and run them with `WT_LINT=0`; they must fail for the
  expected reason. Quote that red summary line in your report and commit body. A report without it is sent back.
- **No subagents.** Do not start any agent (no reviewers, no auditors); the lead runs one reviewer per phase gate.
- **Checks in the foreground.** Run `wt-check.sh` as a normal (foreground) command with a long timeout. Do not use
  background runs, Monitor, timers or sleep loops to wait for it: leftover timers keep notifying the lead after you
  finish.
- **One check run at a time.** Never start a second `wt-check.sh` while one runs, and never leave one running in the
  background when you finish: the Docker host is shared by four writers.
- **Test only what you touched (26 Nov, the user: whole-repo runs are wasted time; see the plan's "Testing model").**
  Phases that passed are not tested again. Run only your task's new tests, plus the test file of a module you changed
  when that file exists; no tests of older phases, no importer sweeps, never a whole suite. Run the full
  `wt-check.sh` (lint, and web only if you changed `frontend/`, else `WT_WEB=0`) once, right before your commit.
  Iterate on one failing test with `-k <name>`. After two failed full runs, commit anyway with the failing test named
  in the body and report: the lead fixes it after the merge. A task is about an hour of code, not three of checks.
- **No smokes, no second stacks.** Browser smokes run once at the phase gate, by the lead, on the main stack.

- **Tests** run only through `bash scripts/dev/wt-check.sh <k> <api test files>` from your worktree root, in Git
  Bash. Use `WT_LINT=0` for the red-first run.
  - It lints only your changed files (mypy cached) and, when `frontend/` changed, runs tsc, `vitest related` and eslint on them.
  - `WT_AUTO=1 bash scripts/dev/wt-check.sh <k>` runs the tests your change impacts (`impacted-tests.sh`); on ALL (core,
    migrations or conftest changed) it refuses: name the files.
  - It refuses test files that call the shared source-sim (`/_sim/`, faults); the lead runs those after the merge.
    Say which in your report.
  - Never run `api-test.sh`, `full-suite.sh`, `reset.sh`, `restart.sh`, `selftest.sh`, a smoke, or
    `docker compose exec`. They act on the main stack, which belongs to the lead.
  - Never `docker compose run ... api pytest` without `-e DI_DATABASE_URL=` set to your own database: the default is
    the main `di` database, and test setup resets it under the lead's runs (26 Nov, a writer did this mid-smoke).
  - Save any check output under a file name that carries your writer number (`wt<k>-…`): writers share one
    scratchpad, and a shared name gets overwritten by a sibling.
  - For a shell-script task, run your new cases directly with stubs, and list what the lead must run.
- **Model first (R16, 25 Nov).** Anything that reads text, interprets evidence, drafts, explains, plans or writes a
  question runs on the model through `AgentLoop` (I-8) when the router has one, as typed Pydantic AI output. Code checks
  every model output and wins (validators, locked guardrails, gates, forbidden list, hold policy, cited sources exist).
  A failed check gets a `ModelRetry`, then the deterministic path answers (`by_model: false`). The model adds caution,
  never removes it, and never invents a computed number. Tests on `FunctionModel`/`TestModel`: model draft accepted,
  refused by a check, retry then fallback, no model. Never write "model optional, rules first".
- **Scope.** Change only the files in your spec, plus your tests and the registration files it names. If you need
  another file, stop and say so.
- **Migrations.** If your task has a migration, the file already exists, empty and chained: fill it, idempotent
  (`IF NOT EXISTS`, `if not exists` checks).
- **Libraries.** The libraries for phases 0–3 are installed already (`backend/requirements.in`). If yours is missing,
  stop and say so; do not edit the locks.
- **Current docs, not memory.** Before code that uses a library, framework feature or agent pattern, read its
  current official docs for the pinned version (WebFetch) and name the page in your report. Follow the spec where
  they disagree, and say so.
- **Write for the next agent:**
  - a module docstring: what it owns, what it never does, which registry entry (I-n) it implements;
  - registry names unchanged;
  - small typed files, one responsibility each;
  - story IDs in test names (R22);
  - the security tests of R21 for a new approvable object, red first.
- **Synced stack.** The lead verifies on a stack whose fabric has synced: hundreds of open conflicts, RT-1048's asset
  among them. A test that drives an agent through the pipeline and is not about holds uses
  `pytestmark = pytest.mark.usefixtures("no_synced_conflicts")` (backend/tests/conftest.py); never assume an empty
  conflict table.
- **Parity.** The industrial demo's 128 cases, RT-1048 and the golden tests stay green. Never hand-edit
  `fixtures/golden/`.
- **Names.** No client, prospect or vendor names in code, data or UI text (except the existing vendor mocks).
- **Never** tick the box or edit `PROGRESS.md`, the plan file or `docs/agents/plans/09-run/`; the lead does that.

## Commit

Commit once on your branch with `git commit -F <file>`:
- first line `<task id>: <summary>`, at most 72 characters;
- a short body, then the checks run with their summary lines;
- last line, the attribution trailer for your model, for example
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

Before committing, `git diff --cached | grep -E 'gsk_[A-Za-z0-9]{20,}'` must print nothing. Never push, stash,
reset, rebase, clean or `checkout --`. Do not start other agents.

## Report, at most 15 lines

- the commit SHA;
- the files changed;
- the wt-check summary lines;
- what the lead must run after the merge (serial-only tests, selftest);
- anything you could not do;
- any decision you took that the spec did not make, and the docs pages you read.
