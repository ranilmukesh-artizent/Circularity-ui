# Plan 8: Decision platform MVP (Modeler, business rules, templates, multi-org, case intake, agent foundation) Implementation Plan

> **For agentic workers (Ralphy, Claude Code, Codex or any CLI agent):** this file is the PRD. Do **one** task per
> iteration: the first line under "Task list" that starts with `- [ ]`. Read "Operating rules" and the task's spec
> section (same id, under "Task specs") before you touch code. Steps are numbered, not checkboxes; only the Task list
> has checkboxes.

**Goal:** turn the full-stack POC into an end-to-end MVP that a multi-company industrial group, a tool-fleet provider
and a device trade-in operator can each pilot. Business owners model their decision process and rules (the PO's
Modeler), every rule is checked against locked guardrails, simulated on the open queue and approved maker-checker
before it changes live decisions. Cases open from source data. Agents read, propose and run playbooks under enforced
autonomy, and a person approves every commit.

**Architecture:**
- **Rule layer.** It sits after the existing gate rules in the pure engine (`backend/di/services/engine/`). Flows and
  rules are versioned data bound to an organisation unit and a template pack.
- **Modeler logic** is pure functions in `backend/di/services/modeler/`, ported one to one from the PO prototype and
  tested against goldens dumped from it.
- **Writes and agents.** Every write goes through the action pipeline. Agents use the same actions through a generated
  tool catalogue, with proposals that hold for a person.

**Tech stack:** FastAPI, SQLAlchemy 2, Alembic, psycopg 3, pytest (backend); React 18 + TypeScript + Vite + vitest
(frontend); Node Playwright with Chrome (smoke scripts); Docker Compose; the `mcp` Python SDK already in the repo.

**Spec:** the sources below are the spec, and each task cites what it implements.
- `docs/reference/po-modeler/recover-app-prototype.html`: the PO's prototype, copied verbatim from the PO's file
  on 23 Nov 2026 (386,432 bytes).
- `business-reviews/dover-user-stories.md`: the user stories, journey A→Z, 28 edge cases and the gap table.
- `AGENTS.md` and `CLAUDE.md`: repo rules.
- `docs/agents/decision-log.md`: decisions so far.
- Public sources in "Sources" at the end.

Gate (per task): the tests named in the task's spec, through `scripts/dev/gate-mvp.sh` (created in MVP-0.2).

---

## How to run this plan with Ralphy (for the human, before the first iteration)

These Ralphy facts were verified in `ralphy.sh` (michaelshimeles/ralphy, README v4.7.x, fetched 23 Nov 2026):
- **Task selection.** Tasks are lines matching `^- \[ \]` (column 0) in the PRD file.
  - The task name is cut to 50 characters (`get_next_task_markdown`).
  - Completion is a `sed` that rewrites the first 50 characters (`mark_task_complete_markdown`).
  - So every task title below starts with a unique id and has no `/ & \ * [ ]`.
- **What the agent sees.** In markdown mode the prompt is `@<PRD> @.ralphy/progress.txt` plus fixed steps: implement,
  write tests, run tests, run lint, tick the box, append progress, commit, "ONLY WORK ON A SINGLE TASK".
  - In `build_prompt` the markdown branch *assigns* the prompt (`prompt="@${PRD_FILE} …"`), so the `.ralphy/config.yaml`
    rules are dropped in the bash version. **The rules this plan needs are therefore inside this file**, and Claude
    and Codex also load `AGENTS.md`/`CLAUDE.md` themselves.
- **Commits and parallel mode.**
  - Ralphy asks the agent to commit after each task. The user chose this loop, so per-task commits on the working
    branch are authorised for this plan; **pushing is not**.
  - `--parallel` uses worktrees and stashes local changes before merging. **Do not use it:** one Postgres, one api
    pytest at a time (AGENTS.md rule 11), and `git stash` is forbidden here (`PROGRESS.md`, 21 Nov 2026).
- **Permissions.** With Claude, Ralphy runs `claude --dangerously-skip-permissions`; `loop.md` forbids that flag on the
  lead's machine. Run Ralphy only on the dedicated build machine, with no real credentials, no `.env` holding real
  keys and no push rights to `main`.

Before the first iteration:
1. On the lead's machine, commit and push `docs/agents/plans/08-mvp-decision-platform.md`,
   `docs/reference/po-modeler/recover-app-prototype.html` and `business-reviews/dover-user-stories.md` to
   `feature/fullstack-poc`. The work stays on that branch (the user's choice, 23 Nov 2026).
2. On the build machine: `git checkout feature/fullstack-poc`, `bash scripts/doctor.sh`, `docker compose up -d --build`,
   then `bash scripts/dev/reset.sh`.
3. Recommended first: run `docs/agents/plans/02-queue-and-tasks.md` (4 tasks: priorities, dead letters). Agent runs
   (Phase 11) and case intake (Phase 8) enqueue jobs, and the decision log (22 Nov 2026) already asks for priorities.
4. Run: `ralphy --prd docs/agents/plans/08-mvp-decision-platform.md --max-iterations 5 --max-retries 2`.
   - Never `--parallel`, `--fast`, `--no-tests` or `--no-lint`.
   - Re-run after reviewing each batch of 5.
5. After every phase gate task, review the commits and `docs/agents/plans/PROGRESS.md`, then push the branch yourself.

---

## Operating rules (the agent reads these every iteration)

R1. **Which task.** The next task is the first line under "Task list" starting with `- [ ]`. Do only that task. Do not
    reorder, merge, split or skip tasks. Do not edit this file except to tick your task's box (`- [ ]` → `- [x]`).
R2. **Read first:**
    - `AGENTS.md`;
    - this file's "Global Constraints", "Domain spec" and your task's spec section;
    - every file listed under the task's **Files**.
    If the task cites prototype lines, read them in `docs/reference/po-modeler/recover-app-prototype.html`.
R3. **Test first** (`.claude/skills/test-driven-development`).
    - Write the tests named in the spec and run them. They must fail for the expected reason.
    - Implement, then run them again until they pass.
    - Never weaken an existing test to make it pass. If an existing test fails because of your change and the spec says
      the behaviour changes, update that test and say so in the commit body. Otherwise fix your code.
R4. **Commands.** Run everything through the repo scripts from the repo root:
    - `bash scripts/dev/gate-mvp.sh <test files>` (after MVP-0.2);
    - `bash scripts/dev/api-test.sh <files>`;
    - `bash scripts/dev/web-check.sh`;
    - `bash scripts/dev/lint.sh`.
    Never run `docker compose exec api pytest` directly. Never run two api test runs at once.
R5. **Layering.** Follow `backend/.importlinter`:
    - routes are leaves;
    - screen services are used only by routes and never import each other;
    - `di.core` and `di.models` import nothing above them;
    - the engine and `di.services.modeler` are pure (no `Session`, no I/O).
    Every new screen module is added to the `screens-independent` contract list.
R6. **Writes.** Every write is an action in the action pipeline:
    - an `ActionDef` declared with `ACTIONS.setdefault(...)`, as `backend/di/services/actions/fabric_sources.py:75` does;
    - a handler attached with `@implement`;
    - refusals through `@guard` or `ActionError`.
    Pages call only `frontend/src/api/*.ts`, and writes use `invoke()`.
R7. **Agents never approve, publish, override, decline or change access** (AGENTS.md rule 10). Add every new such action
    to `FORBIDDEN_ACTIONS` in `backend/di/mcp/policy.py:41`.
R8. **Parity.**
    - The demo's 128 cases and every golden parity test must stay green unless a task says a behaviour changes. When it
      does, that task also adds the decision-log row.
    - Never hand-edit `fixtures/golden/`. The PO goldens under `fixtures/golden/po/` are produced only by
      `frontend/scripts/dump-po-golden.mjs`.
R9. **Data.**
    - All data is synthetic.
    - No client or vendor names in product data, seed or UI text, except the existing vendor mocks (AGENTS.md rule 14).
    - Market references (e.g. tool-fleet, device trade-in) appear only as generic template names.
R10. **Secrets.** Never print, log or commit `.env`, keys or tokens. Before committing, run
     `git diff --cached | grep -E 'gsk_[A-Za-z0-9]{20,}'`; it must print nothing.
R11. **Git.**
     - Commit once, at the end of the task, with `git commit -F <file>`. The first line is ≤ 72 characters, starts with
       the task id (e.g. `MVP-2.3: compile a flow into rules`), and the last line is the attribution trailer.
     - Never push, force, rebase, stash, reset, `checkout --` or delete branches.
R12. **Progress.**
     - Append one line to `docs/agents/plans/PROGRESS.md`: `| date | 08 · <task id> <title> | <short sha after commit: write "this commit"> | <tests run with counts> | done |`.
     - Also append to `.ralphy/progress.txt` as Ralphy asks.
R13. **If blocked**, write `BLOCKED.md` at the repo root and do not tick the box. Blocked means any of:
     - a test outside your task fails and the cause is not your task;
     - the stack is down after `bash scripts/dev/restart.sh`;
     - the spec contradicts the code;
     - a decision is needed that this file does not make.
     Write what you ran, the output (last 40 lines), and the decision needed. Then stop.
R14. **Restarts.** Restart what does not reload after a change: the worker always, source-sim after mock changes, and
     the api after golden or migration changes (`bash scripts/dev/restart.sh`). Run `bash scripts/dev/reset.sh` after
     any browser smoke that writes.
R15. **Size.** Prefer small focused files (one responsibility each). Type everything (mypy strict as configured,
     TypeScript strict). No dead code, no TODOs, no commented-out code.
R16. **Copy texts verbatim.** Messages the Domain spec quotes from the prototype are copied exactly, including
     punctuation, so the goldens compare.
R17. **Done means:**
     - the task's tests pass;
     - `bash scripts/dev/lint.sh` passes;
     - `bash scripts/dev/web-check.sh` passes if `frontend/` changed;
     - the box is ticked, the progress lines are written and one commit is made.
     Quote the test summary line in the commit body.

## Standard task cycle (every task follows it; a task lists only what is specific to it)

- S1. Read (R2).
- S2. Write the failing tests named in the spec.
- S3. Run `bash scripts/dev/gate-mvp.sh <those test files>` and confirm they fail for the expected reason.
- S4. Implement exactly the interfaces in the spec.
- S5. Run S3 again until it is green, then run the spec's extra checks.
- S6. `bash scripts/dev/lint.sh`, and `bash scripts/dev/web-check.sh` if the frontend changed.
- S7. Tick the box, write the progress lines and commit (R11, R12).

## Global Constraints

- Branch `feature/fullstack-poc` (the user's choice, 23 Nov 2026: no separate MVP branch). Python 3 as in the api image, Node 24 for the host smoke scripts (AGENTS.md).
- **Migrations:**
  - continue from `0018` (plan 2's `0018_job_queue.py`); the numbers below are reserved and already exist as empty,
    idempotent stubs (re-apply a filled one with `bash scripts/dev/migrate-reapply.sh 0017`);
  - one file per task, `backend/migrations/versions/00NN_<name>.py`, with `revision = "00NN"` and
    `down_revision = "00NN-1"`;
  - idempotent SQL as `0017_fx_rate.py` does;
  - the SQLAlchemy `Table` goes in `backend/di/models/<domain>.py` (`tests/test_models_migrations.py` compares them).
- **New permissions** (declared in code beside the golden ones, MVP-1.2):
  - `manageOrgs`: Admin.
  - `manageFlows`: Admin, Planner.
  - `approve.flows`: Admin, Approver.
  - `manageAgents`: Admin.
  - `openCases`: Admin, Developer, Planner.
- **New pages:**
  - `modeler`: Admin, Planner, Approver, Executive (read-only for Executive).
  - `agents`: Admin, Developer.
  - The Access page gains an `orgs` section (Admin).
- **Template keys:** `industrial`, `tool_fleet`, `device`.
  - `industrial` uses the existing engine and the 7 routes in `fixtures/golden/world.json` (`redeploy, resale,
    intparts, relase, material, extparts, exit`).
  - `tool_fleet` and `device` come from the PO prototype; their names are taken from the PO golden `templates.json`.
- **Business-rule exclusions** use the gate index `2` (`GATES[2] == "Policy & certification"`,
  `backend/di/services/engine/routes.py:14`), with the prototype's reason texts (Domain spec D4).
- **Org units:**
  - the seeded ids equal today's tenant strings: `Customer A`, `Customer B`, `Customer C` (kind `customer`), under one
    root `workspace` (kind `group`, name `Workspace`);
  - `case_record.owner` keeps holding an org unit id.
- **Language-model use** stays optional and behind the existing provider settings (`GROQ_API_KEY`, `ASK_PROVIDER`). The
  deterministic path must give a complete answer without a key, as `workflow.plan` does
  (`backend/di/services/actions/workflow_builder.py:46-51`).
- **Synthetic data only.** No new outside service (decision D6). No new Python or npm dependency unless the task
  names it.

## Review Focus

1. **A published rule set excludes every eligible route of a case** → the rules are waived and the case keeps its
   gate-rule result, marked `waived: true` (prototype `applyRules`, line 1041). Test: MVP-2.4
   `test_all_excluded_is_waived`.
2. **A Planner scoped to Customer A edits or simulates a flow bound to Customer B** → `tenant_boundary`, with the
   pipeline's message. Test: MVP-3.2 `test_planner_cannot_touch_other_org_flow`.
3. **The maker approves their own draft** → refused with the prototype's text (Domain spec D7). Test: MVP-3.2
   `test_maker_cannot_approve`.
4. **A flow published while a decision is awaiting approval** → the submitted decision keeps the routes and the
   recommendation it was submitted with. Only a re-evaluation applies the new rules, and the case records the
   `flow_ver` it was evaluated with. Test: MVP-3.4 `test_publish_does_not_rewrite_submitted_decision`.
5. **The same source record arrives twice** (a webhook replay or a re-sync) → one case, not two, and the second call
   answers `duplicate`. Test: MVP-8.1 `test_open_case_is_idempotent`.

---

## Source map (what the plan relies on, verified 23 Nov 2026 on `62dbfed`)

| Fact | Where |
|---|---|
| Tenants are three fixed strings from `world.json` | `backend/di/core/policy.py:72-73`; `fixtures/golden/world.json` `tenants` |
| Tenant check, used by the pipeline step 5 | `policy.py:160-168`; `backend/di/services/actions/pipeline.py:163-178` |
| Agent autonomy and run limits are not enforced | `pipeline.py:185` (comment only); settings actions `access.setAutonomy`, `access.setRunLimits` in `fixtures/golden/actions_catalog.json` |
| Agent gate: a commit needs `confirmed`, and decisions are never approved by agents | `pipeline.py:112-120` |
| Actions can be declared in code | `fabric_sources.py:75-78`, `workflow_builder.py:77-85` |
| Gate rules, in order, excluding at gate indexes | `backend/di/services/engine/gates.py:29-66`; `routes.py:14` `GATES`, `fail` `:53`, `rank_routes` `:63` |
| `build_routes` calls the gate rules; `evaluate` re-ranks drafts | `backend/di/services/engine/evaluate.py:23-146` |
| A live re-evaluation rebuilds routes with `FormulaPredictor(rnd)` | `backend/di/services/actions/decisions.py:140-150` |
| Cases open only from the engine's book, once | `backend/di/services/cases/store.py:6-9, 44-64` |
| Sources have no org column | `backend/di/models/connectors.py:24-43` |
| Canonical namespaces | `backend/di/services/canonical/schema.py:34` |
| Workflow versions pattern (state collection) | `backend/di/workflow/versions.py` |
| Workspace JSON state collections | `backend/di/core/state.py` (`register`, `get`, `put`, `add`, `next_number`) |
| MCP: tools, forbidden actions, agents | `backend/di/mcp/tools.py:35-51`, `backend/di/mcp/policy.py:41-44` |
| No MCP client in the app (only in tests) | `backend/tests/test_mcp_server.py` is the only `ClientSession` user |
| Test helpers: `h(user)`, `call(action, body, user)` | `backend/tests/helpers.py:16-27` |
| Test env: pinned clock, no instructions, no triggers | `backend/tests/conftest.py:13-16` |
| Pages register through `src/pages/<area>/index.tsx` | `frontend/src/pages/registry.tsx` |
| Navigation is the golden `NAV`, filtered by `policy.can_page` | `backend/di/services/screens/nav.py:106-136` |
| Learning "retraining" is display text only | `backend/di/services/screens/orchestration.py:599-605` |
| Lint in CI: ruff check, ruff format --check, mypy, lint-imports, eslint, knip | `.github/workflows/ci.yml:43-44, 129-130, 159-167`; `backend/requirements-dev.lock` (ruff 0.8.4, mypy 2.4.1, import-linter 2.15) |

## Domain spec (extracted from the PO prototype; line numbers refer to `docs/reference/po-modeler/recover-app-prototype.html`)

**D1. Flow graph** (lines 1013-1014).
- A node is `{id, t, x, y, label, sub, h, lock, rid?, action?, path?, scope?, owner?, ai?, src?}`.
- Node types `t`: `trigger, agent, gate, guard, rule, decision, approval, path, execute, learn, step`.
- `lock` is true for `trigger, agent, gate, guard, decision, approval, execute, learn`.
- An edge is `{id: a + ">" + b, a, b, l}`.
- Default tool-fleet flow: `tplEquip` (lines 1015-1026). Default device flow: `tplDevice`, which the golden dump records.

**D2. Paths** (tool fleet, lines 799-806).
- `release` Re-issue to fleet · Fleet contract system · Fleet desk
- `refurb` Refurbish → place · Repair center work orders (ERP service) · Repair center lead
- `redeploy` Tool pool · ERP stock transfer (tool pool) · Tool pool planner
- `resell` Pre-owned sale · Pre-owned sales channel · Remarketing lead
- `harvest` Harvest parts · Repair center teardown + spare parts (ERP) · Service parts planner
- `exit` Recycle · Recycler portal + circularity ledger · Sustainability lead

Device channels: `buynow, offers, auction, market` (line 2421). Their names come from the golden.

**D3. Guardrails** (`[id, text, owner]`). Tool fleet `GUARDS_E` (line 2325):
- GR-01 "Grade C and D tools are never issued to a fleet without refurbishment" (Fleet desk)
- GR-02 "Refurbishment always ends in a named fleet contract, sales order or pool request" (Repair center lead)
- GR-03 "Harvested parts are certified only at or above the fit-for-use threshold" (Quality)
- GR-04 "The holding cost rate is set by Finance" (Finance)
- GR-05 "Every decision is approved by a named owner before execution" (Governance board)
- GR-06 "Recycling only through a certified recycler, certificate and CO2 record on file" (Sustainability lead)

Device `GUARDS_D` (line 2326): GR-D1 … GR-D6, verbatim from the golden.

Industrial guardrails: the existing gate texts as locked guardrails.
- GR-I1 = `gates.DATA_ERASURE`
- GR-I2 = `gates.SAFETY_RATED`
- GR-I3 = `gates.CONSENT`
- GR-I4 = `gates.HAZARDOUS`
- GR-I5 "Every decision is approved by a named owner before execution" (owner "Governance board"; the same text as
  GR-05)

**D4. Rule semantics** (`inScope` 1027-1034, `applyRules` 1035-1043).
- A rule is `{id, scope, action: exclude|require|prefer, path, text}`. Rules apply in order, only to cases in scope.
- **exclude:** an eligible path becomes ineligible with the reason `"Excluded by business rule " + id + ": " + text`.
  The flow pseudo-rule `id == "FLOW"` gives `"Path removed from the published process flow"` and is not listed in `ids`.
- **require:** every other eligible path becomes ineligible with the reason
  `"Business rule " + id + " sends this return to " + pathName.toLowerCase()`.
- **prefer:** if the path is eligible it becomes the preference.
- **No path eligible after all rules:** restore every path's eligibility and reason, and return
  `{ids: [], pref: null, waived: true}`.
- **Scope dimensions.**
  - Set dimensions match if the list is empty or contains the case's value.
  - `rulMax`: the case's life is below it. `rulMin`: the case's life is at or above it.
  - Device dimensions: `brand, grade, band, dohMin, qtyMin` (line 2415-2420).
- **Rule text** (`ruleTextE` 1046-1050): `"<scope words or 'every return'>: never|only|prefer <path name lower>"`.

**D5. Compile** (`compileEquip` 1052-1057).
- A rule node counts only if all of these hold: it has a path; it is reachable from the gate; the decision is reachable
  from it; and it breaks no guardrail.
- Every path that is not reachable from the approval node adds `{id: "FLOW", scope: {}, action: "exclude", path: k,
  text: "removed from flow"}`.

**D6. Validate** (`fValidate` 2389-2407). Checks are `[level ok|warn|fail, message, node_id]`, with the messages copied
verbatim:
- unconnected steps;
- guardrail bypass;
- approval bypass;
- paths not offered;
- a rule with no path;
- a rule that breaks a guardrail ("Blocked, not warned.");
- an inactive rule;
- an active rule;
- conflicts between rules on the same path with opposite actions where one is exclude and the scopes overlap.

**D7. Lifecycle** (lines 2387, 2571-2576).
- `touch()`: the first edit of a published flow makes it a draft, records the maker, and sets `dver = ver + 1`.
- **submit:** status `review`, with the log line "Submitted <name> v<dver> for approval".
- **approve:** refused if the actor is the maker: "Maker-checker: you made these changes, so you cannot approve them."
  Otherwise status `shadow`, the checker is recorded, and the log reads "Approved <name> v<dver> (maker <name>); shadow
  run started".
- **reject:** back to `draft`.
- **discard:** the draft is reset to the published graph.
- **publish:** the old published graph goes to history, then `ver = dver` and status `pub`; "Published <name> v<ver>".
- **rollback:** the last history entry is restored; "Rolled back <name> from v<a> to v<b>".

**D8. Guardrail checks on rules and text.**
- `ruleGuardE` (line 1051): `release` with action ≠ exclude and a scope grade containing C or D breaks GR-01.
- `textGuard` (2434-2437), equip:
  - `/fit-for-use|threshold/` with `/lower|reduce|change|set|relax|raise/` → GR-03;
  - `/holding cost/` → GR-04;
  - `/auto-?approv|without approval|skip approval/` → GR-05;
  - `/refurb/` with `/to stock/` → GR-02.
- `textGuard`, device: GR-D1, D2, D4, D5, D6 patterns as written there.

**D9. Simulate** (`fSim` 2408-2413).
- Equip: `{kind: "equip", n, flips: cases whose best path changes, dv: Σ(candidate best net − base best net)}`.
- Device: `{kind: "device", n, u, flips, dv, cash, dd, days, dl}` as written there.

**D10. Assistant** (`parseEquip` 2424-2433, `parseDevice` 2415-2423, `buildProposal` 2446-2460).
- A text guard hit gives a `blocked` proposal with the message on line 2447.
- "add … step before|for|after …" gives a `step` proposal.
- Otherwise the text parses into `{path, action, scope}`. No path gives an `unclear` proposal (the message on line 2454).
- A rule proposal gets the next `rid` (`T.pre + "-" + nn`), is inserted between the last node feeding the decision
  and the decision, is validated (only the checks on it and the conflicts), and is simulated against the current
  draft.
- Action words: `never|no|not|don't|do not|exclude|stop|avoid|block` → exclude; `only|must|always|allow` → require;
  anything else → prefer.

**D11. Valuation.**
- Tool fleet: `value(c, k, p)` (928-1008), `decide`/`decide1` (1102-1117), cases from `mkCase` (1118), random draws
  from `rng(seed)` (mulberry32, line 791) with `R = rng(26110)`.
- Device: `dLots` (2337, `rng(4242)`), `dScore`/`dDecide` (2347-).

---

## Task list (Ralphy reads only this list; one task per iteration, top to bottom)

- [x] MVP-0.1 Record the MVP decisions and plan row
- [x] MVP-0.2 Lint, shard and gate scripts for this plan
- [x] MVP-0.3 Dump PO prototype goldens
- [x] MVP-0.4 Phase 0 gate
- [x] MVP-1.1 Org unit table and seed
- [x] MVP-1.2 Policy reads org units and new permissions
- [x] MVP-1.3 Org actions create update move
- [x] MVP-1.4 Bind sources to org units
- [x] MVP-1.5 Organisation section in the Access page
- [x] MVP-1.6 Phase 1 gate
- [x] MVP-2.1 Template packs as data
- [x] MVP-2.2 Flow graph model and default flows
- [x] MVP-2.3 Compile a flow into rules
- [x] MVP-2.4 Apply business rules after gate rules
- [x] MVP-2.5 Validate a flow
- [x] MVP-2.6 Guardrail checks on rules and text
- [x] MVP-2.7 Simulate a flow on a queue
- [x] MVP-2.8 Phase 2 gate
- [x] MVP-3.1 Flow tables and repository
- [x] MVP-3.2 Flow lifecycle actions with maker checker
- [x] MVP-3.3 Live rules in re-evaluation
- [x] MVP-3.4 Rule version pinned on decisions
- [x] MVP-3.5 Shadow decisions recorded
- [x] MVP-3.6 Phase 3 gate
- [x] MVP-4.1 Simulation action over the open queue
- [x] MVP-4.2 Modeler screen endpoint and navigation
- [x] MVP-4.3 Modeler API facade
- [x] MVP-4.4 Modeler page canvas and inspector
- [x] MVP-4.5 Modeler checks impact lifecycle panels
- [x] MVP-4.6 Modeler browser smoke
- [x] MVP-4.7 Phase 4 gate
- [x] MVP-5.1 Rule parser per template
- [x] MVP-5.2 Proposal action for plain language changes
- [x] MVP-5.3 Optional model reading for proposals
- [x] MVP-5.4 Assistant panel in the Modeler
- [x] MVP-5.5 Modeler tools for MCP and Ask
- [x] MVP-5.6 Phase 5 gate
- [x] MVP-6.1 Tool fleet valuer port
- [x] MVP-6.2 Device valuer port
- [x] MVP-6.3 Template sample queues for simulation
- [x] MVP-6.4 Routes adapter for template cases
- [x] MVP-6.5 Phase 6 gate
- [x] MVP-7.1 Telemetry facts as rule scope
- [x] MVP-7.2 Phase 7 gate
- [x] MVP-8.1 Open case action with dedupe
- [x] MVP-8.2 Open case workflow block
- [x] MVP-8.3 Case screens render any template
- [x] MVP-8.4 Manual import rows open cases
- [x] MVP-8.5 Phase 8 gate
- [x] MVP-9.1 PLM part and BOM canonical models
- [x] MVP-9.2 Windchill mock in source-sim
- [x] MVP-9.3 Windchill adapter
- [x] MVP-9.4 Where-used query and BOM parts value
- [x] MVP-9.5 Phase 9 gate
- [x] MVP-10.1 Org roll-up in analytics
- [x] MVP-10.2 Org configuration pack export and import
- [x] MVP-10.3 Pilot mode per org and pilot report
- [x] MVP-10.4 Phase 10 gate
- [x] MVP-11.1 Enforce agent autonomy and run limits
- [x] MVP-11.2 Tool catalogue generated from actions
- [x] MVP-11.3 Agent registry at runtime
- [x] MVP-11.4 Proposals that hold for a person
- [x] MVP-11.5 Agent runtime and case autopilot playbook
- [x] MVP-11.6 MCP tools filtered per agent
- [x] MVP-11.7 MCP client source kind
- [x] MVP-11.8 Agents page
- [x] MVP-11.9 Phase 11 gate
- [x] MVP-12.1 Outcome dataset and calibration
- [x] MVP-12.2 Model candidate shadow and promote
- [x] MVP-12.3 Rule suggestions from overrides
- [x] MVP-12.4 End to end MVP smoke
- [x] MVP-12.5 Final gate and status

---

## Task specs

### Phase 0: ground rules and harness

#### MVP-0.1 Record the MVP decisions and plan row
**Files:** Modify `docs/agents/decision-log.md` (add rows at the top of the table, newest first); modify
`docs/agents/plans/00-overview.md` (add a row for plan 8).

**Content:** one decision-log row per decision below. Date `2026-11-23`. Each row gives why, the alternatives and
where it lives ("plan 8, MVP-x.y").
1. **Editable business rules and template packs.** This is a deliberate parity change.
   - The demo's cases evaluate with no business rules while the published flows have no rule nodes.
   - The seeded default flows contain no rule nodes for `industrial`.
   - The PO prototype is the spec.
2. **Org units replace the fixed tenants.** The seeded ids equal `Customer A/B/C` under `workspace`, so no data
   migrates.
3. **Business rules run after the gate rules.** Exclusions use gate index 2 with the prototype's reasons; prefer changes
   the recommendation only among eligible routes; and a waiver applies when nothing is left eligible.
4. **A flow is bound to (template, org unit).** The nearest ancestor's published flow applies.
5. **Lifecycle** draft → review → shadow → published, with maker ≠ checker and rollback. New permissions as listed in
   Global Constraints.
6. **Agent runtime** in-house on the job queue, with proposals that hold for a person.
   - Alternatives: LangGraph (Postgres checkpointer), Orkes/Temporal.
   - Deferred because the pipeline already gives preparer/confirmed and D6 says no new service.
7. **Telemetry becomes rule scope facts** (an alarm flag), not engine changes.
8. **The PLM is read-only in the MVP** (a Windchill mock and adapter, no PLM writes), from the Dover stories' "read-only
   testbed".

The `00-overview.md` row: `| 8 | 08-mvp-decision-platform.md | the decision platform MVP (Modeler, rules, templates,
multi-org, intake, agent foundation) | per phase: the phase gate task |`.

**Tests:** none (documentation). **Done when:** both files render as valid markdown tables (`grep -c '^| 2026-11-23'
docs/agents/decision-log.md` prints 8).

#### MVP-0.2 Lint, shard and gate scripts for this plan
**Files:**
- Create `scripts/dev/lint.sh`, `scripts/dev/suite-shard.sh`, `scripts/dev/gate-mvp.sh`.
- Modify `docs/agents/scripts.md` (one row each).

**Interfaces:**
- `bash scripts/dev/lint.sh` runs, and exits non-zero if any fails (prints ≤ 60 lines):
  - in the api container: `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`;
  - in the web container: `npx eslint .` and `npx knip`.
- `bash scripts/dev/suite-shard.sh <n> <m>`:
  - lists `tests/test_*.py` in the api container, sorted;
  - runs every m-th file starting at n (1-based) through `scripts/dev/api-test.sh` without `-x`. Add `--no-x` handling:
    `api-test.sh` keeps `-x` by default, and `API_TEST_NO_X=1` drops it.
  - `bash scripts/dev/suite-shard.sh sim` runs the source-sim suite (`docker compose exec -T source-sim pytest -q`).
- `bash scripts/dev/gate-mvp.sh <test files…>` = `lint.sh`, then `api-test.sh <files>` (if any), then `web-check.sh`
  if `git diff --name-only HEAD` touches `frontend/`, then the secret scan (R10). It exits 0 only if all pass.
- The environment variables `GATE_LINT`, `GATE_API` and `GATE_WEB` override the three commands (default: the real
  scripts), as `loop.md` Task 2 specifies for its gate.

**Tests:**
- Extend `scripts/dev/selftest.sh` with three cases:
  - `GATE_LINT=true GATE_WEB=true GATE_API=false bash scripts/dev/gate-mvp.sh tests/test_health.py` exits 1;
  - with all three set to `true` it exits 0;
  - with `GATE_LINT=true GATE_WEB=true` and the real `GATE_API`, `gate-mvp.sh tests/test_health.py` exits 0.
- Run `bash scripts/dev/selftest.sh`.

**Done when:** `lint.sh` exits 0 on the current tree. If it does not, fix only formatting (`ruff format`) in files the
check names, and list them in the commit body. A mypy or eslint error in existing code → R13 (BLOCKED.md).

#### MVP-0.3 Dump PO prototype goldens
**Files:**
- Create `frontend/scripts/dump-po-golden.mjs` and `fixtures/golden/po/*.json` (generated).
- Create `fixtures/golden/po/README.md`.
- Create `backend/tests/test_po_golden.py`.

**Interfaces:** `node frontend/scripts/dump-po-golden.mjs` loads `docs/reference/po-modeler/recover-app-prototype.html`
from a `file://` URL in Node Playwright (`channel: 'chrome'`, as `frontend/scripts/smoke-pages.mjs`). It evaluates in
the page and writes:
- `templates.json`: for each `TPL[k]`, `{key, name, pre, paths, guards, dims}`, plus `ACTORS`, `CLSWORDS`, `FUNCS`,
  `SITES`.
- `flows.json`: `tplEquip()` and `tplDevice()` (nodes, edges).
- `equip_cases.json`: every case in `CASES` (all fields) and `openCases()` ids.
- `equip_decisions.json`: for each open case, `decide(c, P, liveRules())` with `best.k`, `best.net`, and per path
  `{k, ok, net, why}`.
- `device_lots.json` and `device_decisions.json`: `dLots()` and `dDecide(l, base)` per lot.
- `compile_cases.json`: `compileEquip` over the default flow and over 4 edited flows the script builds (r1 disconnected
  from the gate; the `p-harvest` node removed; a rule with `path: "release", scope: {grade: ["C"]}` added; a rule with
  no path).
- `validate_cases.json`: `fValidate` over the same 5 flows.
- `apply_cases.json`: `applyRules` on 6 open cases × the rules from `compile_cases`, including one rule set that
  excludes every path (the waiver).
- `parse_cases.json`: `parseEquip` and `parseDevice` over these sentences:
  - "Never recycle construction lasers";
  - "Prefer tool pool for grade A or B from Repair center";
  - "Only harvest parts for breakers under 30% life";
  - "Lower the fit-for-use threshold to 60";
  - "Skip approval for grade A";
  - "Lots over 45 days on hand: Auction only";
  - "Never list grade D on Buy Now";
  - "Samsung under 24 months prefer offers".
- `textguard_cases.json`: `textGuard` with `MD.tpl` set to each template, over the same sentences.
- `sim_cases.json`: `fSim` for the 4 edited equip flows against `PUB.equip`, and for one device rule ("Lots over 45 days
  on hand: Auction only").
- `proposals.json`: `buildProposal(text)` for the 8 sentences (kind, rid, label, msg, the sim summary), with
  `Date.now` stubbed to `1767225600000`.

Set `MD.actor = "pshah"` before proposals. Record the prototype's SHA-256 in `README.md`.

**Tests:** `test_po_golden.py` asserts:
- `templates.json` has the keys `equip` and `device`;
- equip has 6 paths in the D2 order and 6 guards whose ids are `GR-01`…`GR-06` with the D3 texts;
- device has 4 paths `buynow, offers, auction, market` and 6 guards `GR-D1`…`GR-D6`;
- `equip_cases.json` is non-empty;
- `apply_cases.json` contains at least one `waived: true`;
- every sentence appears in `parse_cases.json`.

**Done when:** running the dump twice gives byte-identical files (the script sorts keys).

#### MVP-0.4 Phase 0 gate
Run, in order:
1. `bash scripts/dev/suite-shard.sh 1 4`, `2 4`, `3 4`, `4 4` and `bash scripts/dev/suite-shard.sh sim`;
2. `bash scripts/dev/reset.sh`;
3. `bash scripts/dev/web-check.sh`;
4. `node frontend/scripts/smoke-pages.mjs http://localhost:5173`.

Record the counts in `PROGRESS.md`. Any failure → R13. Commit only `PROGRESS.md`.

### Phase 1: organisation units (stories B, C, J, N, Q; edge cases 1-4)

#### MVP-1.1 Org unit table and seed
**Files:**
- Create `backend/migrations/versions/0019_org_unit.py` and `backend/di/models/org.py`.
- Modify `backend/di/models/__init__.py`.
- Test: create `backend/tests/test_org_units.py`.

**Interfaces:**
- Table `org_unit(id text primary key, parent_id text null references org_unit(id), kind text not null check (kind in
  ('group','segment','company','site','customer')), name text not null, created_at timestamptz not null default
  now())`.
- Index on `parent_id`.
- Seed (on conflict do nothing): `('workspace', null, 'group', 'Workspace')`, then `('Customer A','workspace','customer',
  'Customer A')`, and the same for B and C.

**Tests:**
- `test_seeded_org_units` (4 rows, parents as seeded);
- `test_migration_round_trip` (downgrade to 0017 and upgrade to head keep the rows);
- `test_models_match_migrations` stays green.

#### MVP-1.2 Policy reads org units and new permissions
**Files:**
- Create `backend/di/core/orgs.py`.
- Modify `backend/di/core/policy.py`, `backend/di/core/auth.py` (`load_context`).
- Test: create `backend/tests/test_policy_orgs.py`.

**Interfaces:**
- `orgs.OrgUnit(id: str, parent_id: str | None, kind: str, name: str)` (frozen dataclass).
- `orgs.subtree(units: dict[str, OrgUnit], root: str) -> set[str]` and
  `orgs.ancestors(units: dict[str, OrgUnit], uid: str) -> list[str]` (nearest first, including `uid`).
- `policy.Context.org_units: dict[str, OrgUnit] | None = None`. `load_context` fills it from `org_unit`.
- `policy.tenants(ctx: Context | None = None) -> list[str]`: ids of the units of kind `customer` or `company`. Without a
  context, it returns the seeded order `Customer A, B, C` (so the golden paths are unchanged).
- `policy.tenant_ok(a, tenant, ctx)`: true if `tenant` is in the subtree of any unit in `allowed_tenants(a, ctx)`.
- `EXTRA_PERMS: dict[str, tuple[str, ...]]` with the Global Constraints permissions. `policy.can()` and `permissions()`
  include them.
- `EXTRA_PAGES: dict[str, tuple[str, ...]]` = `{"modeler": ("Admin","Planner","Approver","Executive"), "agents":
  ("Admin","Developer")}`, and `("access","orgs")` for Admin. `can_page` honours them.

**Tests:**
- `test_planner_a_still_sees_only_customer_a` (parity);
- `test_grant_on_group_sees_children`: grant `workspace` to `planner.b` through `tenant_grant`, and `tenant_ok` is true
  for `Customer C`;
- `test_new_permissions` (Planner can `manageFlows`, cannot `approve.flows`; Approver the reverse; Executive neither);
- `test_can_page_modeler`.
- Also run `tests/test_policy.py tests/test_auth.py tests/test_screens_access.py`.

#### MVP-1.3 Org actions create update move
**Files:**
- Create `backend/di/services/actions/orgs.py` and register its import where the other action modules are imported
  (follow `fabric_sources.py`).
- Test: create `backend/tests/test_writes_orgs.py`.

**Interfaces:** actions, perm `manageOrgs`, risk `commit`, journaled:
- `org.create {id, parent_id, kind, name}`. Ids are matched by `^[A-Za-z0-9 ._-]{2,64}$`. An existing id →
  `conflict` "Org unit <id> already exists.".
- `org.update {id, name}`.
- `org.move {id, parent_id}`. A cycle → `conflict` "An org unit cannot move under itself or its own children.";
  moving `workspace` → `conflict` "The workspace root cannot move.".
- Read `org.tree {}` (risk read): `{units: [{id, parent_id, kind, name, children: [...]}]}`.

**Tests:**
- `test_create_company_under_group`;
- `test_move_sub_company` (edge case 1: its cases stay visible to a grant on the new parent);
- `test_cycle_refused`;
- `test_planner_refused_out_of_scope`;
- `test_journal_row_per_write`.

#### MVP-1.4 Bind sources to org units
**Files:**
- Create `backend/migrations/versions/0020_source_org.py`.
- Modify `backend/di/models/connectors.py`, `backend/di/services/actions/fabric_sources.py` (`source.update` accepts
  `org_unit_id`), and `backend/di/services/screens/integration.py` (each source row carries `org_unit_id`).
- Test: create `backend/tests/test_source_org.py`.

**Interfaces:**
- `source_system.org_unit_id text null references org_unit(id)`. Null = shared by every org (all demo sources).
- `source.update` validates that the id exists and is in the actor's allowed subtree (Admin: any).
- A second instance of a type (`erp_2`, `fabric_sources.py:376-382`) may bind to a different org.

**Tests:**
- `test_new_source_bound_to_company`;
- `test_unknown_org_refused` (validation_error);
- `test_demo_sources_unbound` (parity);
- also run `tests/test_fabric_sources.py tests/test_screens_integration.py`.

#### MVP-1.5 Organisation section in the Access page
**Files:**
- Create `frontend/src/api/orgs.ts` and `frontend/src/api/orgs.test.ts`.
- Modify the Access page area under `frontend/src/pages/access/`: add the `orgs` section following that area's
  section pattern.
- Modify `backend/di/services/screens/access.py` and its route: the `orgs` section data = `org.tree`.

**Interfaces:**
- `orgs.ts` exports `useOrgTree(): OrgNode[]` (read cache), `createOrg(input)`, `moveOrg(id, parentId)` and
  `renameOrg(id, name)`, each calling `invoke('org.*', …)`.
- The section shows an indented tree, a create form (parent select, kind select, name) and a move select per row.
  Admin only.

**Tests:**
- vitest `orgs.test.ts`: invoke is called with the right action ids and bodies; the read cache is invalidated after a
  write.
- `node frontend/scripts/smoke-pages.mjs http://localhost:5173` stays green.

#### MVP-1.6 Phase 1 gate
Same as MVP-0.4, plus `node frontend/scripts/smoke-rt1048.mjs http://localhost:5173` with `reset.sh` before and after.
Record the counts.

### Phase 2: decision policy core, pure (stories H, I; Domain spec D1-D9)

All modules in `backend/di/services/modeler/` are pure: no `Session`, no clock, and no I/O beyond reading the packaged
JSON. Tests compare against `fixtures/golden/po/*` through `di.core.golden.load("po/<name>")`; extend `golden.load` to
accept a subfolder if it does not already.

#### MVP-2.1 Template packs as data
**Files:**
- Create `backend/di/services/modeler/__init__.py`, `backend/di/services/modeler/templates.py` and
  `backend/di/services/modeler/packs/industrial.json`.
- Test: `backend/tests/test_modeler_templates.py`.

**Interfaces:**
- `PathDef(id: str, name: str, app: str, owner: str, lead_days: int | None)`.
- `Guardrail(id: str, text: str, owner: str, forbids: tuple[Forbid, ...], protects: tuple[TextPattern, ...])`.
  - `Forbid(path: str, actions: tuple[str, ...], scope_any: dict[str, tuple[str, ...]])`: a rule breaks the guardrail
    if its path matches, its action is in `actions`, and for each key its scope list shares a value with `scope_any`.
  - `TextPattern(all_of: tuple[str, ...])`: regexes that must all match the lowercased text.
- `ScopeDim(key: str, label: str, kind: Literal["set","min","max"], values: tuple[str, ...])`.
- `Template(key, name, pre, paths, guardrails, dims, actors: tuple[tuple[str,str,str], ...])`.
- `load_template(key: str) -> Template` and `TEMPLATE_KEYS = ("industrial", "tool_fleet", "device")`.
  - `tool_fleet` and `device` are built from `fixtures/golden/po/templates.json`.
  - GR-01's `forbids` = `Forbid("release", ("require","prefer"), {"grade": ("C","D")})` (D8).
  - The `protects` patterns are the D8 text regexes.
  - The `industrial` pack: the 7 routes with names from `world.json` routes; guardrails GR-I1…I5 (D3), with
    `forbids: ()` and `protects` for GR-I5 = the GR-05 pattern; dims `cls` (world classes), `grade` (A-D),
    `site` (world site ids), `owner` (org unit id).

**Tests:**
- `test_tool_fleet_pack_matches_golden` (paths, guard ids and texts);
- `test_device_pack_matches_golden`;
- `test_industrial_paths_are_world_routes`;
- `test_unknown_template_raises_keyerror`.

#### MVP-2.2 Flow graph model and default flows
**Files:** Create `backend/di/services/modeler/flow.py`. Test: `backend/tests/test_modeler_flow.py`.

**Interfaces:**
- `Node` and `Edge` TypedDicts per D1.
- `Flow = TypedDict("Flow", {"nodes": list[Node], "edges": list[Edge]})`.
- `default_flow(t: Template) -> Flow`:
  - `tool_fleet` and `device` return the golden `flows.json` graphs;
  - `industrial` builds the D1 shape: trigger "Asset returned", gate "Guardrail gate", decision "Choose best route",
    approval "Owner approves", one path node per route (`id "p-"+route`), execute, learn, with the edges as in
    `tplEquip` minus the agent and rule nodes.
- `reach(f: Flow, start: str, skip: str | None = None) -> set[str]` (port of `fReach`).
- `node_label(n: Node) -> str`.

**Tests:**
- `test_default_flows_equal_golden`;
- `test_industrial_default_has_no_rule_nodes` (parity);
- `test_reach_skips_node`.

#### MVP-2.3 Compile a flow into rules
**Files:** Create `backend/di/services/modeler/compile.py`. Test: `backend/tests/test_modeler_compile.py`.

**Interfaces:**
- `CompiledRule(id: str, scope: dict[str, Any], action: str, path: str, text: str)` (frozen dataclass).
- `compile_flow(t: Template, f: Flow) -> list[CompiledRule]` (D5).
- `rule_text(t: Template, rule_like: Mapping[str, Any]) -> str` (D4 rule text, generalised over the dims; the scope
  words for `tool_fleet` use `CLSWORDS`).

**Tests:**
- `test_compile_matches_golden` (all 5 `compile_cases`);
- `test_industrial_default_compiles_to_nothing`.

#### MVP-2.4 Apply business rules after gate rules
**Files:**
- Create `backend/di/services/modeler/apply.py` and `backend/di/services/modeler/scope.py`.
- Modify `backend/di/services/engine/evaluate.py` and `backend/di/services/engine/routes.py`.
- Test: `backend/tests/test_modeler_apply.py`.

**Interfaces:**
- `scope.in_scope(case: Mapping[str, Any], scope: Mapping[str, Any], dims: Sequence[ScopeDim]) -> bool` (D4).
- `apply.RuleOutcome(ids: list[str], preferred: str | None, waived: bool)`.
- `apply.apply_rules(case, routes: list[Route], rules: Sequence[CompiledRule], t: Template) -> RuleOutcome`:
  - mutates the routes;
  - exclusions call `routes.fail(r, 2, reason)` with the D4 texts (the path name from the template);
  - the waiver restores `excluded`, `failGate`, `failReason` and `gates` from a snapshot taken before.
- `routes.rank_routes(routes, blocked=None, prefer: str | None = None)`: when `prefer` names an eligible route, that
  route gets rank 1 and is the recommendation; the others keep net order. `prefer=None` behaves exactly as today.
- `evaluate.build_routes(case, p, rules: Sequence[CompiledRule] | None = None, template: Template | None = None)` and
  `evaluate.evaluate(case, drafts, rules: bool, business: Sequence[CompiledRule] | None = None, template=None)`:
  - business rules run after the gate rules;
  - the case dict gains `rulesApplied: list[str]`, `rulesWaived: bool` and `preferred`;
  - with `None` nothing changes.

**Tests:**
- `test_apply_matches_golden`: map golden equip paths onto stub routes with the golden `ok`/`why`, and the outcomes
  match;
- `test_exclude_reason_text`;
- `test_require_excludes_others`;
- `test_prefer_changes_recommendation_only_if_eligible`;
- `test_all_excluded_is_waived` (Review Focus 1);
- `test_none_rules_keeps_engine_output` (parity on the 128 book cases: re-run `book` with `business=None` and compare
  to the stored cases);
- also run `tests/test_engine.py`.

#### MVP-2.5 Validate a flow
**Files:** Create `backend/di/services/modeler/validate.py`. Test: `backend/tests/test_modeler_validate.py`.

**Interfaces:**
- `Check(level: Literal["ok","warn","fail"], msg: str, node_id: str | None)`.
- `validate_flow(t: Template, f: Flow) -> list[Check]` (D6, messages verbatim).
- `blocking(checks) -> list[Check]` (the `fail` entries).

**Tests:**
- `test_validate_matches_golden` (5 flows);
- `test_guardrail_bypass_fails` (an edge from the trigger straight to a path node);
- `test_conflict_warns`.

#### MVP-2.6 Guardrail checks on rules and text
**Files:** Create `backend/di/services/modeler/guard.py`. Test: `backend/tests/test_modeler_guard.py`.

**Interfaces:**
- `rule_breaks(t: Template, rule_like: Mapping[str, Any]) -> str | None` (the first guardrail id whose `forbids`
  match).
- `text_breaks(t: Template, text: str) -> str | None` (the first guardrail whose `protects` pattern matches).
- `compile.py` and `validate.py` use `rule_breaks`.

**Tests:**
- `test_textguard_matches_golden` (every sentence × template);
- `test_release_grade_c_breaks_gr01`.

#### MVP-2.7 Simulate a flow on a queue
**Files:** Create `backend/di/services/modeler/simulate.py`. Test: `backend/tests/test_modeler_simulate.py`.

**Interfaces:**
- `Decider = Callable[[Mapping[str, Any], Sequence[CompiledRule]], Decision]`, where
  `Decision(best: str | None, net: float, extra: dict)`.
- `Flip(case_id: str, from_path: str | None, to_path: str | None, dv: float)`.
- `SimResult(kind: str, n: int, flips: list[Flip], dv: float, extra: dict[str, float])`.
- `simulate(t, base: Sequence[CompiledRule], cand: Sequence[CompiledRule], queue: Sequence[Mapping], decide: Decider)
  -> SimResult` (D9). Equip-style dv for `tool_fleet` and `industrial`; device extras (`u, cash, dd, days, dl`) for
  `device`.

**Tests:** `test_simulate_with_stub_decider` (2 cases, 1 flip, dv exact). The golden comparison waits for the valuers
(MVP-6.1/6.2 add `test_sim_matches_golden`).

#### MVP-2.8 Phase 2 gate
Same as MVP-0.4.

### Phase 3: flow storage, lifecycle, live rules (story I; Review Focus 2-4)

#### MVP-3.1 Flow tables and repository
**Files:**
- Create `backend/migrations/versions/0021_decision_flow.py`, `backend/di/models/modeler.py` and
  `backend/di/repositories/flows.py`.
- Test: `backend/tests/test_flows_repo.py`.

**Interfaces:**
- Tables:
  - `decision_flow(id bigserial pk, template_key text not null, org_unit_id text not null references org_unit(id),
    name text not null, status text not null check (status in ('draft','review','shadow','pub')), ver int not null,
    dver int null, maker text null, checker text null, draft jsonb null, published jsonb not null, updated_at
    timestamptz not null default now(), unique (template_key, org_unit_id))`;
  - `decision_flow_version(flow_id bigint references decision_flow(id), ver int, graph jsonb, published_by text,
    published_at timestamptz, note text, primary key (flow_id, ver))`.
- Seed one published flow per template on `workspace` with `default_flow`, `ver 1`. The name comes from the template.
- Repository (reads only):
  - `get_flow(s, flow_id) -> FlowRow | None`;
  - `flow_for(s, template_key, org_unit_id) -> FlowRow | None` (nearest ancestor with a row; uses `orgs.ancestors`);
  - `flows(s, org_ids: set[str]) -> list[FlowRow]`;
  - `versions(s, flow_id) -> list[VersionRow]`.

**Tests:**
- `test_seeded_flows`;
- `test_flow_for_uses_nearest_ancestor` (a company row overrides `workspace`);
- `test_models_match_migrations`.

#### MVP-3.2 Flow lifecycle actions with maker checker
**Files:** Create `backend/di/services/actions/modeler.py`. Test: `backend/tests/test_writes_flows.py`.

**Interfaces** (all journaled; org scope checked against the flow's `org_unit_id` with `policy.tenant_ok`, which answers
`tenant_boundary` like the pipeline):
- `flow.saveDraft {flow_id, graph}`: perm `manageFlows`, risk act.
  - Performs `touch()` (D7).
  - Stores `draft`.
  - Answers `{checks}` from `validate_flow`.
- `flow.fork {template_key, org_unit_id}`: perm `manageFlows`, risk act. It creates a flow row for that org from the
  nearest ancestor's published graph. If the org already has one → `conflict`.
- `flow.submit {flow_id}`: perm `manageFlows`. Draft → review. Refused while `blocking(checks)` is non-empty: `conflict`
  "Fix the blocking checks before submitting.".
- `flow.approve {flow_id}`: perm `approve.flows`. Review → shadow. If the actor is the maker → `conflict` with the D7
  text.
- `flow.reject {flow_id, reason}`: perm `approve.flows`. Review or shadow → draft. The reason must be ≥ 15 characters,
  as override reasons are.
- `flow.publish {flow_id}`: perm `approve.flows`. Shadow → pub:
  - insert a `decision_flow_version` row for the old published graph;
  - `published = draft`, `ver = dver`, `draft = null`, `maker = checker = null`.
  - If the actor is the maker → the D7 conflict text.
- `flow.discard {flow_id}`: perm `manageFlows`. Back to the published graph, status pub.
- `flow.rollback {flow_id}`: perm `approve.flows`. Restores the latest version row. Refused with no history: `conflict`
  "No earlier version to roll back to.".
- `flow.get {flow_id}` (read): `{flow, template, checks, compiled}`.
- Add `flow.approve`, `flow.publish`, `flow.reject` and `flow.rollback` to `FORBIDDEN_ACTIONS`.

**Tests:**
- `test_full_lifecycle` (planner.a saves → submits; approver approves → publishes; the version row exists);
- `test_maker_cannot_approve` (Admin makes and approves → refused with the D7 text);
- `test_planner_cannot_touch_other_org_flow` (fork for `Customer B` as planner.a → `tenant_boundary`);
- `test_submit_refused_with_blocking_checks`;
- `test_rollback`;
- `test_agent_cannot_publish` (an MCP-prepared call is refused by the agent gate or `FORBIDDEN_ACTIONS`).

#### MVP-3.3 Live rules in re-evaluation
**Files:**
- Create `backend/di/repositories/live_rules.py`. It reads the database, so it does not belong in the pure
  `di.services.modeler`. The repositories layer may import `di.services.modeler`, which is outside the layers contract.
- Modify `backend/di/services/actions/decisions.py` (`_rebuild` and the evaluate paths).
- Test: `backend/tests/test_live_rules.py`.

**Interfaces:**
- `live_rules(s, case: Mapping) -> tuple[Template, list[CompiledRule], int]`:
  - the template is `case.get("template") or "industrial"`;
  - the flow is `flow_for(template, case["owner"])`;
  - it returns the compiled rules of its published graph and that flow's `ver`.
- `_rebuild` passes them to `build_routes`.
- `case.reevaluate` stores `case["flowVer"]`.

**Tests:**
- `test_published_rule_excludes_on_reevaluate`: publish "exclude material for Customer A grade C"; re-evaluate a
  Customer A grade-C case; `material` is excluded with the D4 reason.
- `test_other_org_unaffected`.
- `test_default_flows_change_nothing` (parity: re-evaluate RT-1048 with the default flows; same result as before this
  task).
- Also run `tests/test_writes_decisions.py tests/test_milestone_rt1048.py`.

#### MVP-3.4 Rule version pinned on decisions
**Files:** Modify `backend/di/services/actions/decisions.py` (submit stores `flowVer`). Test:
`backend/tests/test_live_rules.py`.

**Behaviour:** `decision.submit` and approve keep the stored routes. Publishing a flow never rewrites an open decision;
only `case.reevaluate` applies new rules. The decision payload and the case screen show `flowVer`.

**Tests:** `test_publish_does_not_rewrite_submitted_decision` (Review Focus 4); `test_decision_records_flow_ver`.

#### MVP-3.5 Shadow decisions recorded
**Files:**
- Create `backend/migrations/versions/0022_shadow_decision.py`.
- Modify `backend/di/models/modeler.py`, `backend/di/services/actions/decisions.py` and
  `backend/di/repositories/flows.py`.
- Test: `backend/tests/test_shadow.py`.

**Interfaces:**
- Table `shadow_decision(id bigserial pk, flow_id bigint, dver int, case_id text, live_route text, shadow_route text,
  live_net numeric, shadow_net numeric, at timestamptz default now())`.
- When the case's flow is in `shadow`, each re-evaluation also evaluates the routes with the draft's compiled rules (on
  a deep copy) and inserts a row. The live result is unchanged.
- `shadow_stats(s, flow_id) -> {n, agree, disagree, dv}`.

**Tests:** `test_shadow_row_written_live_unchanged`; `test_shadow_stats`.

#### MVP-3.6 Phase 3 gate
Same as MVP-1.6.

### Phase 4: simulation and the Modeler page (stories I, P)

#### MVP-4.1 Simulation action over the open queue
**Files:** Modify `backend/di/services/actions/modeler.py`. Test: `backend/tests/test_flow_simulate.py`.

**Interfaces:**
- `flow.simulate {flow_id, graph?}` (read; perm `manageFlows` or `approve.flows`).
- The queue = the live cases visible to the actor whose template and nearest flow is this flow, stage not closed
  (`closed`, `executed` and `cancelled` are taken from `backend/di/services/cases/lifecycle.py`).
- Decider for `industrial`, per case:
  - `drafts = [evaluate.draft_of(r, keep_exclusion=True) for r in case["routes"]]`;
  - `evaluate.evaluate(case, drafts, rules=False, business=rules, template=t)`;
  - best = recommendation id, net = its net.
  - This is deterministic (no predictor draws).
- Base = the published compiled rules; candidate = the compiled `graph` (or the draft).
- Answer `SimResult` as JSON, with per-flip `{case_id, from, to, dv}`.

**Tests:**
- `test_simulate_no_change_is_zero`;
- `test_simulate_excluding_resale_flips_cases` (the count equals the cases whose recommendation was resale and that are
  in scope);
- `test_simulate_respects_tenant` (planner.a sees only Customer A cases).

#### MVP-4.2 Modeler screen endpoint and navigation
**Files:**
- Create `backend/di/services/screens/modeler.py` and `backend/di/routes/screens/modeler.py`.
- Modify `backend/di/main.py` (mount), `backend/.importlinter` (independence list), and
  `backend/di/services/screens/nav.py`: append a code-declared leaf entry `{"id": "modeler", "label": "Modeler", "sub":
  "Decision process and business rules", "icon": <an icon id already in assets>, "sec": <the section the Workflow
  Studio entry uses>, "leaf": true}`, shown through `can_page`.
- Test: `backend/tests/test_screens_modeler.py`.

**Interfaces:** `GET /api/screens/modeler?template=<key>&org=<id>` answers
`{templates: [{key, name}], orgs: [ids the actor may see], flow: {id, name, status, ver, dver, maker, checker, graph
(draft or published), published}, template: {paths, guardrails, dims, actors}, checks, compiled, versions, shadow,
log}`.
- `log` = journal rows of `flow.*` actions for this flow, newest first: `{at, actor, role, action, note}`.

**Tests:**
- `test_modeler_screen_for_planner`;
- `test_executive_read_only` (no write buttons flagged: `can: {edit:false, approve:false}`);
- `test_nav_shows_modeler_for_allowed_roles`;
- `test_warehouse_manager_no_access` (403 `out_of_scope`);
- also run `tests/test_screens_home.py` (the nav badge counts are unchanged).

#### MVP-4.3 Modeler API facade
**Files:** Create `frontend/src/api/modeler.ts` and `frontend/src/api/modeler.test.ts`.

**Interfaces:**
- `useModeler(template: string, org: string): ModelerScreen` (read cache over the endpoint).
- Writes: `saveDraft(flowId, graph)`, `forkFlow(template, org)`, `submitFlow`, `approveFlow`,
  `rejectFlow(flowId, reason)`, `publishFlow`, `discardFlow`, `rollbackFlow`.
- `simulateFlow(flowId, graph?) => Promise<SimResult>`.
- Every write invalidates the modeler read and the cases reads (follow `frontend/src/api/invalidation.ts`).
- Types in `frontend/src/api/types.ts`: `FlowNode`, `FlowEdge`, `FlowGraph`, `Check`, `SimResult`, `ModelerScreen`
  (the fields of MVP-4.2).

**Tests:** vitest: each write invokes the right action with the right body; invalidation is called.

#### MVP-4.4 Modeler page canvas and inspector
**Files:**
- Create `frontend/src/pages/modeler/index.tsx` (registers `modeler`), `ModelerPage.tsx`, `FlowCanvas.tsx`,
  `FlowInspector.tsx` and `flowEdit.ts` (pure graph edits) with `flowEdit.test.ts`.

**Interfaces:** `flowEdit.ts`:
- `addRule(g, rid, owner): FlowGraph`: inserts between the node feeding the decision and the decision, as D10 does.
- `removeNode(g, id)`: refused for `lock` nodes, which returns `g` unchanged.
- `connect(g, a, b)`, `disconnect(g, edgeId)`, `moveNode(g, id, x, y)` and `updateRule(g, id, patch)`.
- `nextRid(g, pre)`: max existing number + 1, two digits.

The page:
- the template and org pickers;
- the canvas: absolute-positioned nodes at `x, y`, SVG edges, drag to move, click to select; the locked nodes show a
  lock icon; the fixed band label "Core prediction and agents · fixed" from the golden `band`;
- the inspector: a rule's action (exclude/require/prefer), path (select of the template paths), scope fields per dim
  (multi-select for `set`, a number for `min`/`max`) and owner; for other nodes, a read-only label/sub and the next-step
  connections.
- Edits autosave as a draft through `saveDraft` after 2 s (as workflow drafts do, decision log 2026-11-21). Read-only
  for Executive.

**Tests:**
- `flowEdit.test.ts`: `addRule` places the rule between the gate chain and the decision; `removeNode` on a lock node is
  a no-op; `nextRid` gives `BR-03` after BR-01 and BR-02.
- `web-check.sh` green.

#### MVP-4.5 Modeler checks impact lifecycle panels
**Files:** Create `frontend/src/pages/modeler/ChecksPanel.tsx`, `ImpactPanel.tsx`, `LifecycleBar.tsx` and
`HistoryPanel.tsx`; modify `ModelerPage.tsx`.

**Behaviour:**
- **ChecksPanel** lists the checks with ok, warn and fail icons; clicking one selects its node.
- **ImpactPanel** runs `simulateFlow` on demand ("Simulate on open queue") and shows "N of M open decisions change ·
  ±$X queue net" (the prototype's `propHtml` wording, line 2462) plus the flips list. When dv < 0 it shows the
  prototype's trade-off note (line 2465).
- **LifecycleBar** shows a status pill (draft, review, shadow, published) and the buttons the actor may use (from the
  screen's `can`).
  - Reject asks for a reason (≥ 15 characters).
  - Shadow shows the shadow stats.
- **HistoryPanel** shows the versions with Rollback, and the log.

**Tests:** vitest for the impact text formatter (`formatImpact(sim)` with the prototype wording for dv ≥ 0 and dv < 0).
`web-check.sh` green.

#### MVP-4.6 Modeler browser smoke
**Files:** Create `frontend/scripts/smoke-modeler.mjs` (pattern: `smoke-approve.mjs`).

**Journey:**
1. planner.a opens `#/modeler` and adds a rule "exclude resale for grade C" through the inspector.
2. Simulate shows "N of M".
3. Submit.
4. approver approves → shadow → publish.
5. planner.a re-evaluates one Customer A grade-C case whose recommendation was resale. Its case page shows "Excluded by
   business rule BR-01".

The script exits non-zero on any missing text. It does not reset anything itself; the command below wraps it in
`reset.sh`.

**Done when:** `bash scripts/dev/reset.sh && node frontend/scripts/smoke-modeler.mjs http://localhost:5173 && bash
scripts/dev/reset.sh` passes.

#### MVP-4.7 Phase 4 gate
Same as MVP-1.6, plus `smoke-modeler.mjs`.

### Phase 5: the Modeler assistant (plain language → checked proposal) (story P; D10)

#### MVP-5.1 Rule parser per template
**Files:** Create `backend/di/services/modeler/parse.py`. Test: `backend/tests/test_modeler_parse.py`.

**Interfaces:** `parse_rule(t: Template, text: str) -> ParsedRule(path: str | None, action: str, scope: dict)`.
- `tool_fleet` ports `parseEquip` and `device` ports `parseDevice` exactly.
- `industrial` uses the same structure over its vocabulary:
  - class words from `world.json` classes (`label`, `plural`, key);
  - sites by id or name;
  - grades as in D10;
  - path words from the route names, plus `recycl|scrap|material` → `material`, `exit` → `exit`, `lease` → `relase`,
    `parts` → `intparts` (and `extparts` when "sell" or "external" occurs);
  - owner org ids by exact name.

**Tests:** `test_parse_matches_golden` (tool_fleet, device); `test_industrial_parse_examples` (4 sentences with
expected outputs written in the test).

#### MVP-5.2 Proposal action for plain language changes
**Files:** Modify `backend/di/services/actions/modeler.py`; create `backend/di/services/modeler/propose.py`. Test:
`backend/tests/test_flow_propose.py`.

**Interfaces:**
- `propose.build_proposal(t, draft: Flow, text: str, actor_role: str, decide_queue: Callable[[list[CompiledRule]],
  SimResult] | None) -> Proposal`, a port of D10. `Proposal(kind: Literal["rule","step","blocked","unclear"], text,
  graph: Flow | None, node_id, rid, label, guard: str | None, checks: list[Check], sim: SimResult | None, msg: str)`.
- Action `flow.propose {flow_id, text}`: risk read, perm `manageFlows`, not journaled. It returns the proposal and saves
  nothing.
- Applying it is the person's own `flow.saveDraft` with `graph = proposal.graph` and `source: "assistant"`, recorded in
  the journal input. Add `note` to the `saveDraft` input: "Proposed by the assistant: <text>".

**Tests:**
- `test_proposals_match_golden` (tool_fleet: kind, rid, label, msg for the 8 sentences);
- `test_blocked_proposal_changes_nothing`;
- `test_apply_proposal_via_save_draft` (the journal has the note).

#### MVP-5.3 Optional model reading for proposals
**Files:** Create `backend/di/services/ask/modeler_read.py`. It calls the model provider, so it lives beside the Ask
provider code, not in the pure `di.services.modeler`. Modify `flow.propose` in `backend/di/services/actions/modeler.py`
to merge its answer before `build_proposal`. Test: `backend/tests/test_flow_propose_model.py`.

**Interfaces:** `model_rule(text, t) -> dict`. Same pattern as `workflow_builder.model_slots`:
- one short JSON request through the existing Groq client;
- it may fill only `path`, `action` and `scope` keys that the parser left empty;
- every value is checked against the template's paths and dims;
- any failure → `{}`;
- the key is never logged.

The proposal answer adds `read_by: "rules" | "rules+model"`.

**Tests:** with the provider stubbed (monkeypatch), an ambiguous sentence gets its path from the stub; with the stub
raising, the deterministic answer is unchanged; with no key, the model is never called.

#### MVP-5.4 Assistant panel in the Modeler
**Files:** Create `frontend/src/pages/modeler/AssistantPanel.tsx`; modify `modeler.ts` (`proposeChange(flowId,
text)`) and `ModelerPage.tsx`.

**Behaviour:**
- **Chat.** It opens with the prototype's opening line for the template (`chat()`, line 2438).
- **On send.** It calls `proposeChange` and shows the proposal:
  - the label;
  - the checks list: "Fits the process …", "Passes all N locked guardrails", the conflicts or "No conflict with existing
    rules", "Prediction models and agents unchanged" (line 2464);
  - the impact.
- **Buttons.** "Approve · AI applies it" calls `saveDraft(graph)` with the note; Dismiss clears the proposal. A proposed
  node is drawn dashed on the canvas until it is applied or dismissed.
- **Blocked proposals** show the message in red.

**Tests:** vitest for `proposalChecks(p)` (the list of lines); `web-check.sh` green. Extend `smoke-modeler.mjs` with:
type "Never recycle construction lasers" in a `tool_fleet` flow on `workspace` as admin, then expect "Proposed change".

#### MVP-5.5 Modeler tools for MCP and Ask
**Files:**
- Modify `backend/di/mcp/tools.py` (two tools), `backend/di/mcp/policy.py` and `backend/di/services/ask/tools.py`.
- Test: extend `backend/tests/test_mcp_server.py` and `backend/tests/test_ask.py`.

**Interfaces:**
- MCP `get_decision_flow {template, org}` (read) → the `flow.get` output.
- MCP `propose_rule_change {flow_id, text}` (read; returns the proposal; never applies it).
- Ask: `get_decision_flow` as a read tool.
- `ACTIONS_OF` gets `flow.get` and `flow.propose`. The policy's assertion that no forbidden action is reachable still
  holds.

**Tests:**
- `test_mcp_lists_flow_tools`;
- `test_mcp_propose_does_not_change_draft`;
- `test_mcp_cannot_publish` (calling any tool that maps to `flow.publish` is impossible; assert `flow.publish` is in
  `FORBIDDEN_ACTIONS`).

#### MVP-5.6 Phase 5 gate
Same as MVP-4.7.

### Phase 6: tool-fleet and device template packs with valuation (market fit for tool-fleet and device trade-in operators; D11)

#### MVP-6.1 Tool fleet valuer port
**Files:**
- Create `backend/di/services/modeler/valuers/__init__.py`, `backend/di/services/modeler/valuers/rng.py` and
  `backend/di/services/modeler/valuers/tool_fleet.py`.
- Test: `backend/tests/test_valuer_tool_fleet.py`.

**Interfaces:**
- `rng.mulberry32(seed: int) -> Callable[[], float]` (bit-exact port of line 791, using 32-bit masks).
- `tool_fleet.value(case, path, params) -> PathValue` and `tool_fleet.decide(case, params, rules) -> Decision`: ports of
  `value`/`decide1`/`decide` (lines 928-1117), including `applyRules` through `apply.apply_rules` on PathValue-shaped
  routes. Constants (`P`, `BASEP`, the capacity slots) come from the golden or the prototype, copied verbatim and cited
  by line.
- `tool_fleet.sample_queue() -> list[dict]`: the golden `equip_cases.json` open cases.

**Tests:**
- `test_rng_matches_js` (the first 5 values of `rng(26110)` hard-coded from the golden dump; add them to the dump if
  missing);
- `test_decisions_match_golden` (best path and net for every open case, nets to the cent);
- `test_sim_matches_golden` (tool_fleet rows of `sim_cases.json`).

#### MVP-6.2 Device valuer port
**Files:** Create `backend/di/services/modeler/valuers/device.py`. Test: `backend/tests/test_valuer_device.py`.

**Interfaces:**
- `device.score(lot, channel) -> ChannelValue` and `device.decide(lot, rules) -> Decision` (`dScore`/`dDecide`,
  lines 2347-).
- `device.sample_lots() -> list[dict]` (golden `device_lots.json`).

**Tests:** `test_device_decisions_match_golden`; `test_device_sim_matches_golden`.

#### MVP-6.3 Template sample queues for simulation
**Files:**
- Modify `backend/di/services/actions/modeler.py` (`flow.simulate` for `tool_fleet` and `device` uses the sample
  queue plus any live cases of that template) and `backend/di/services/screens/modeler.py` (`queue: [{id, label, best,
  net}]`).
- Test: extend `backend/tests/test_flow_simulate.py`.

**Tests:** `test_tool_fleet_simulation_equals_golden` (via the action); `test_device_simulation_equals_golden`.

#### MVP-6.4 Routes adapter for template cases
**Files:** Create `backend/di/services/modeler/valuers/routes_adapter.py`. Test:
`backend/tests/test_routes_adapter.py`.

**Interfaces:** `to_routes(t: Template, values: Sequence[PathValue | ChannelValue]) -> list[Route]`.
- It produces the engine's `Route` dicts (`mk_route` fields): `id = path`, `plan = path name`, terms from the value
  lines (label, amount, kind `"sale"|"prep"|"fees"|"risk"|"purchase"|"lease"|"parts"|"material"`, mapped as the test
  table states), `excluded`/`failGate 2`/`failReason = why` when not ok.
- `rank_routes` then gives the recommendation. Used by intake (MVP-8.1) for non-industrial templates.

**Tests:** `test_adapter_keeps_best_path` (the recommendation equals the valuer's best for 5 golden cases);
`test_adapter_excluded_reason`.

#### MVP-6.5 Phase 6 gate
Same as MVP-4.7.

### Phase 7: telemetry as rule scope (story G; edge cases 11-13)

#### MVP-7.1 Telemetry facts as rule scope
**Files:**
- Create `backend/di/services/modeler/facts.py`.
- Modify `backend/di/services/modeler/templates.py` (industrial dim `alarm`, kind `set`, values `("yes","no")`) and
  the case-facts assembly used by `live_rules`/`in_scope`.
- Test: `backend/tests/test_telemetry_scope.py`.

**Interfaces:** `case_scope_facts(case, telemetry: Mapping[str, Any] | None) -> dict`. It adds `alarm: "yes"` when the
latest `vibration_mm_s ≥ 7.1` or `bearing_temp_c ≥ 90` (the mock's alarm thresholds, `docs/backend-steps.md:231`; read
the exact canonical field names from `backend/di/connectors/adapters/aws_iot.py`), otherwise `"no"`. With no telemetry
the key is absent (edge case 11: rules scoped on `alarm` simply do not match).

**Tests:**
- `test_alarm_yes_from_vibration`;
- `test_no_telemetry_no_alarm_key`;
- `test_rule_never_redeploy_on_alarm` (connect IoT in the test with `POST /api/sources/iot/connect`, sync, publish the
  rule, re-evaluate → redeploy excluded for the alarmed asset only).

#### MVP-7.2 Phase 7 gate
Same as MVP-4.7.

### Phase 8: case intake from data (story F; edge cases 22, 24)

#### MVP-8.1 Open case action with dedupe
**Files:**
- Create `backend/di/services/cases/intake.py`.
- Modify `backend/di/services/cases/store.py` (`insert_new(s, case)`, public) and add an action in
  `backend/di/services/actions/cases_intake.py`.
- Test: `backend/tests/test_case_intake.py`.

**Interfaces:** action `case.open {org_unit_id, template_key, asset_key, reason, facts?}`:
- perm `openCases`, risk act, idem `f"{asset_key}:{reason}"` (Review Focus 5);
- `reason ∈ {rma, lease_end, trade_in, contract_end, iot_alarm, manual}`.

`intake.open_case(s, input, actor) -> Case`:
- **Id.** The next free `RT-<n>` above the highest existing number.
- **Owner and template.** `owner = org_unit_id`; `template = template_key`.
- **Base fields.** `stage` is the first stage in `lifecycle.py`. `cls`, `grade`, `age`, `qty`, `spec` and `demand` come
  from `facts` or the canonical store for `asset_key` (asset and condition models).
- **Routes.**
  - `industrial`: `build_routes(case, FormulaPredictor(mulberry32(int(hashlib.sha256(case_id.encode()).hexdigest()[:8],
    16))), rules, template)`. Use a stable hash; Python's `hash()` differs per process.
  - Other templates: the valuer plus `to_routes`.
  - Then the live rules.
- **Log.** A stage log row "Case opened from <reason>".
- **Event.** It emits the event `case.opened` (follow how the actions emit events).

**Tests:**
- `test_open_industrial_case` (it appears in `cases.list` for the owner's planner);
- `test_open_case_is_idempotent` (the second call → `duplicate`);
- `test_open_tool_fleet_case_uses_valuer`;
- `test_unknown_org_refused`;
- `test_planner_other_org_refused` (`tenant_boundary`).

#### MVP-8.2 Open case workflow block
**Files:**
- Modify `backend/di/workflow/blocks.py` (new block `x_case`, label "Open case", settings `{template, reason,
  asset_field, org_unit_id, only_if: <field>=<value> optional}`) and `backend/di/workflow/steps/flow.py` (the step).
- Modify the frontend palette data if it is defined there; follow how `x_audit` was added (decision log 2026-11-22).
- Test: `backend/tests/test_workflow_open_case.py`.

**Behaviour:**
- For each record passing the step, call `intake.open_case` as the system actor, with the workflow's publisher recorded
  as `by`.
- In a dry run nothing opens; the step reports "Would open N cases".
- Duplicates count as skipped.

**Tests:**
- `test_published_ingest_with_open_case_opens_cases` (Optoro `rl` returns: publish an ingest workflow with the block,
  run a sync, and N cases open where N = records passing `only_if`);
- `test_resync_opens_no_duplicates`;
- `test_dry_run_opens_nothing`.

#### MVP-8.3 Case screens render any template
**Files:** Modify whatever `backend/tests/test_screens_case.py`-covered code fails for a `tool_fleet` case (class
lookups in `backend/di/services/screens/case.py`, `product.py` and `command.py`), using the template's path names and a
generic class label. Test: `backend/tests/test_screens_any_template.py`.

**Tests:**
- For one opened `tool_fleet` case and one `device` case, every case-screen endpoint the case page calls answers 200
  and includes the routes, with `plan` equal to the template path names;
- the demo cases' screens are unchanged (`tests/test_screens_case.py` green).

#### MVP-8.4 Manual import rows open cases
**Files:** Modify `backend/di/connectors/manual.py` (`import.commit` accepts `open_cases: {template, reason, org_unit_id,
asset_field}`) and the import modal in the frontend integration page. Test: extend `backend/tests/test_fabric_records.py`.

**Behaviour:** after the facts are stored, each row opens a case through `intake.open_case`, with dedupe. The answer adds
`cases_opened` and `cases_skipped`. This covers edge case 24 (a bulk end-of-lease file).

**Tests:** `test_import_opens_cases`; `test_import_twice_opens_once`.

#### MVP-8.5 Phase 8 gate
Same as MVP-4.7, plus a manual check written in `PROGRESS.md`: the case count in `cases.list` for admin is 128 +
the opened cases.

### Phase 9: PLM depth, read-only (stories C, D, H for multi-PLM groups; edge cases 5-10)

#### MVP-9.1 PLM part and BOM canonical models
**Files:**
- Modify `backend/di/services/canonical/schema.py` (`MODELS` adds `part` and `bom`) and
  `backend/di/services/canonical/fields.py` (fields: `part.number`, `part.revision`, `part.state`, `part.name`,
  `part.unit_cost`, `part.org_unit_id`; `bom.parent`, `bom.child`, `bom.qty`, `bom.parent_revision`,
  `bom.harvestable`).
- Test: extend `backend/tests/test_canonical_schema.py`.

**Rules:**
- Keys are `<org_unit_id or "shared">:<part number>` (edge case 4: the same number in two orgs never collides).
- Revisions are stored per key (edge case 5).

**Tests:** `test_part_keys_per_org`; `test_bom_line_fields`; the existing schema tests stay green.

#### MVP-9.2 Windchill mock in source-sim
**Files:** Create `source-sim/sim/vendors/windchill/{__init__,routes,models,seed}.py` following an existing vendor
folder (e.g. `source-sim/sim/vendors/teamcenter/`); register it in `source-sim/sim/core/registry.py`. Test: create
`source-sim/tests/test_windchill.py`.

**Endpoints** (shapes after the PTC Windchill REST Services ProdMgmt domain; see Sources):
- `GET /Windchill/servlet/odata/ProdMgmt/Parts?$top=&$skip=` → `{value: [{ID, Number, Name, Version, Iteration,
  State: {Value}, UnitCost}]}`;
- `POST /Windchill/servlet/odata/ProdMgmt/Parts('<ID>')/PTC.ProdMgmt.GetPartStructure` → `{value: [{Number, Uses:
  [{Quantity, Part: {Number, Version}}]}]}`.

Seed 40 synthetic parts and 8 assemblies whose numbers overlap 5 of the Aras mock's part numbers, so where-used across
systems is testable.

**Tests:** paging; the structure for one assembly; deterministic seed. Run with `bash scripts/dev/suite-shard.sh sim`.

#### MVP-9.3 Windchill adapter
**Files:**
- Create `backend/di/connectors/adapters/windchill.py` (pattern: `adapters/teamcenter.py`).
- Register it as source id `plm_wc` with type `plm`, vendor "PTC Windchill", status `disconnected` at start, so the
  demo screens and counts are unchanged (decision-log pattern of the IoT source, 2026-11-20).
- Modify the adapter registry.
- Test: `backend/tests/test_adapter_windchill.py`.

**Behaviour:** after `source.reconnect` or bind, a sync maps the parts to `part.*` and the structures to `bom.*` for
the source's `org_unit_id`.

**Tests:**
- `test_sync_maps_parts_and_bom`;
- `test_demo_counts_unchanged_while_disconnected` (run `tests/test_screens_integration.py` too);
- `test_two_orgs_two_windchill_instances_do_not_collide`.

#### MVP-9.4 Where-used query and BOM parts value
**Files:**
- Create `backend/di/repositories/plm.py`.
- Modify `backend/di/services/engine/predictor.py` (add `BomPartsPredictor`, wrapping a `Predictor`).
- Modify `backend/di/services/cases/intake.py` (an industrial case whose asset has a `bom_ref` with BOM facts uses
  `BomPartsPredictor`).
- Test: `backend/tests/test_bom_parts_value.py`.

**Interfaces:**
- `where_used(s, org_unit_id, part_number) -> list[{parent, parent_revision, qty}]`.
- `BomPartsPredictor(base, lines: list[BomLine], demand: Mapping[str, int])` overrides `parts_value(a, internal)` as
  `round(Σ unit_cost × qty × min(1, demand[part] / qty) × max(a.gf, 0.5) × (1.0 if internal else 0.8))` over the
  harvestable lines. `demand[part]` = the count of `where_used` parents among active assemblies. Every other estimate
  delegates to `base`. Demo book cases never use it (parity).

**Tests:**
- `test_parts_value_from_bom` (exact number for a 3-line BOM);
- `test_no_demand_no_value`;
- `test_book_cases_unchanged`.

#### MVP-9.5 Phase 9 gate
Same as MVP-4.7.

### Phase 10: group reporting and onboarding the next company (stories N, Q)

#### MVP-10.1 Org roll-up in analytics
**Files:** Modify `backend/di/services/screens/analytics.py` (optional `org` query: the subtree's cases) and the
Analytics page filter (an org select listing the actor's units). Test: extend `backend/tests/test_screens_analytics.py`.

**Tests:**
- `test_analytics_org_subtree` (`workspace` = all; `Customer A` = only A);
- the default (no `org`) is unchanged (parity).

#### MVP-10.2 Org configuration pack export and import
**Files:** Create `backend/di/services/actions/org_pack.py`. Test: `backend/tests/test_org_pack.py`.

**Interfaces:**
- `org.exportPack {org_unit_id}` (read; perm `manageOrgs`) → `{version: 1, org, sources: [connection settings without
  secrets], mappings, workflows (published graphs), flows (published graphs per template)}`.
- `org.importPack {pack, target_org_unit_id}` (commit; perm `manageOrgs`): it creates the sources (status
  `disconnected`, no secrets; edge case: credentials are re-entered by a person), the mappings, the workflows as drafts
  (never published), and the flows via `flow.fork` plus a draft.
- It answers `{created: {...}, needs: ["credentials for <source>", …]}`.

**Tests:**
- `test_export_has_no_secrets` (scan for the stored secret's last 4 characters → absent);
- `test_import_creates_drafts_only`;
- `test_import_into_other_org_scoped`.

#### MVP-10.3 Pilot mode per org and pilot report
Implements Dover stories §3 A: a read-only testbed that ends in a value report.

**Files:**
- Create `backend/di/services/actions/org_pilot.py`.
- Modify the instruction sending path in `backend/di/services/instructions/` (the function that sends one instruction;
  find it from `instructions/__init__.py`).
- Test: `backend/tests/test_org_pilot.py`.

**Interfaces:**
- State collection `org_settings` (`di.core.state.register`, no migration), one item per org unit id: `{pilot: bool}`.
- `org.setPilot {org_unit_id, on}`: perm `manageOrgs`, commit, journaled.
- **Sending.** When the case's owner, or any ancestor of it, has `pilot: true`, the instruction is not sent. It is
  marked held with the note "Pilot mode: not sent to <target>", and the run continues as if acknowledged by the
  simulated adapter. Pilot mode never sends.
- `org.pilotReport {org_unit_id}` (read; perm `manageOrgs` or `approve.flows`) answers `{cases_opened, decisions_submitted,
  decisions_approved, recommended_net_total, rules_applied_count, instructions_held, by_route: {route: count}}` over
  the org's subtree.

**Tests:**
- `test_pilot_holds_instructions` (no outbound write reaches the mock: source-sim has no new record);
- `test_pilot_off_sends`;
- `test_pilot_report_counts`;
- `test_child_of_pilot_org_is_pilot`.

#### MVP-10.4 Phase 10 gate
Same as MVP-4.7.

### Phase 11: agent foundation (story O; edge cases 25-28)

#### MVP-11.1 Enforce agent autonomy and run limits
**Files:** Modify `backend/di/services/actions/pipeline.py` (step 8). Read where `access.setAutonomy` and
`access.setRunLimits` store their settings (`backend/di/services/actions/access.py`). Test:
`backend/tests/test_agent_autonomy.py`.

**Behaviour:** when `ctx.preparer` is set:
- **Autonomy level.** Read the stored level for the actor's role and the action type. A level that does not allow the
  action's risk → `approval_required` "<agent> may only prepare this; a person must confirm it.".
- **Run limits.** Count the run's journaled actions (`run_id`). Over `actions` → `conflict` "Run limit reached: <n>
  actions.". A bulk input over `bulk` → `conflict` "Bulk limit reached: <n> items.".
- **Kill switch.** A stopped agent (`agent.setEnabled`) → `out_of_scope` "<agent> is stopped.".

People's own calls are unaffected.

**Tests:** one per refusal; `test_person_unaffected`; also run `tests/test_writes_access_settings.py
tests/test_mcp_server.py`.

#### MVP-11.2 Tool catalogue generated from actions
**Files:** Create `backend/di/services/agents/catalog.py` and `backend/di/routes/agents.py` (mount in `main.py`).
Test: `backend/tests/test_agent_catalog.py`.

**Interfaces:**
- `catalog() -> list[{name, action, title, description, risk, input_schema (JSON Schema draft 2020-12 from
  ActionDef.input: t → type, req → required), agent_allowed: bool}]`, where `agent_allowed` is false for
  `FORBIDDEN_ACTIONS` and risk `system`.
- `GET /api/agents/tools` (signed in; filtered to the actor's permissions).

**Tests:** every action id appears once; `decision.approve` is not agent-allowed; the schema of `case.open` lists the
required fields.

#### MVP-11.3 Agent registry at runtime
**Files:**
- Create `backend/migrations/versions/0023_agent_identity.py`, `backend/di/models/agents.py` and
  `backend/di/services/actions/agents.py`.
- Modify `backend/di/mcp/policy.py` (the `X-Agent` header is accepted if it is in the registry and enabled).
- Test: `backend/tests/test_agent_registry.py`.

**Interfaces:**
- Table `agent_identity(id text pk, name text, kind text check (kind in ('internal','external')), org_scope text[] not
  null default '{}', tools text[] not null default '{}', autonomy text not null default 'propose' check (autonomy in
  ('read','propose','act')), enabled bool not null default true, created_by text, created_at timestamptz default
  now())`, seeded with the 9 golden agents (`AGENTS_BY_ID`), `kind internal`, all tools of `ACTIONS_OF` for that agent.
- Actions `agent.register` and `agent.update` (perm `manageAgents`, commit, journaled). `agent.setEnabled` keeps
  working and now writes the row too.

**Tests:**
- `test_seeded_agents`;
- `test_register_external_agent_and_call_read_tool`;
- `test_unknown_agent_refused`;
- `test_org_scope_limits_cases` (edge case 25).

#### MVP-11.4 Proposals that hold for a person
**Files:**
- Create `backend/migrations/versions/0024_agent_proposal.py` and `backend/di/services/agents/proposals.py`.
- Modify `pipeline.py` (step 8: an agent with autonomy `propose` calling a non-read action → insert a proposal and
  answer `{"ok": true, "output": {"held": proposal_id}}`).
- Add actions `proposal.accept` and `proposal.reject`; the inbox reads them.
- Test: `backend/tests/test_agent_proposals.py`.

**Interfaces:**
- Table `agent_proposal(id bigserial pk, agent text, action text, input jsonb, case_id text null, run_id text null,
  status text check (status in ('pending','accepted','rejected','expired')), created_at, decided_by text null,
  decided_at null, result jsonb null)`.
- `proposal.accept {id}`: perm = the held action's own permission. It invokes the action as the person with
  `preparer=agent` and `confirmed=True`, and stores the result.
- `proposal.reject {id, reason}`.
- `GET /api/screens/home` inbox gains `proposals` for the actor (in scope only).

**Tests:**
- `test_propose_holds` (edge case 26);
- `test_accept_runs_as_person`;
- `test_accept_needs_permission`;
- `test_reject`;
- `test_decision_actions_never_held_but_refused` (`decision.approve` stays refused, not held).

#### MVP-11.5 Agent runtime and case autopilot playbook
**Files:**
- Create `backend/migrations/versions/0025_agent_run.py`, `backend/di/services/agents/runtime.py` and
  `backend/di/services/agents/playbooks/case_autopilot.py`.
- Register the job kind `agent.step` in `backend/di/worker.py`.
- Test: `backend/tests/test_agent_runtime.py`.

**Interfaces:**
- Tables:
  - `agent_run(id text pk, agent text, playbook text, case_id text null, status text check (status in
    ('running','waiting','done','failed','stopped')), step int, state jsonb, created_at, updated_at)`;
  - `agent_run_step(run_id, n, tool, input jsonb, output jsonb, at)`.
- `runtime.start(s, agent, playbook, case_id) -> run_id` enqueues `agent.step`.
- `runtime.step(s, run_id)` runs the next playbook step through `pipeline.invoke` with `preparer=agent` and
  `run_id=run_id`. A `held` answer → status `waiting` with the proposal id in `state`. When the proposal is accepted
  (MVP-11.4 hooks `proposal.accept` to enqueue `agent.step`), the run resumes.

`case_autopilot` steps (all existing actions):
1. `case.evidence`;
2. `evidence.request` if evidence is missing;
3. `case.reevaluate`;
4. `decision.submit` (held for a person);
5. after acceptance, wait for approval: status `waiting`, resumed by `runtime.resume_waiting(s, case_id)`, which the
   `decision.approve` handler calls (no polling; `jobs.enqueue` has no delay parameter today, `backend/di/core/jobs.py:20`);
6. `instruction.resend` only if an instruction failed;
7. done.

The runtime never calls forbidden actions (assert at load).

**Tests:**
- `test_autopilot_runs_to_hold`;
- `test_accept_resumes`;
- `test_stopped_agent_stops_run` (kill switch mid-run → status `stopped`);
- `test_run_limit_stops_run`.

#### MVP-11.6 MCP tools filtered per agent
**Files:** Modify `backend/di/mcp/__init__.py` and `backend/di/mcp/tools.py` (`tools/list` returns only the registry
row's `tools` for the calling agent; `tools/call` refuses others with the existing refusal shape). Test: extend
`backend/tests/test_mcp_server.py`.

**Tests:** an external agent registered with only `get_case_evidence` lists 1 tool; calling `find_demand` is refused.

#### MVP-11.7 MCP client source kind
**Files:**
- Create `backend/di/connectors/mcp_client.py`.
- Modify `backend/di/services/actions/fabric_sources.py` (`source.update` `mode=mcp` with `{url, tool, arguments,
  resource_key}`) and `backend/di/connectors/sync.py`.
- Add a tiny MCP server to source-sim at `/mcp-demo` exposing one read tool `list_returns`, following the repo's server
  pattern.
- Test: `backend/tests/test_mcp_client_source.py`.

**Behaviour:**
- A sync connects with the `mcp` SDK's streamable HTTP client (the same SDK `tests/test_mcp_server.py` uses) and calls
  the configured tool.
- The JSON items become records for the mapping and canonical pipeline exactly as the configured adapter's records do.
- A failure follows sync reliability (the source fails and retries; edge case 27).

**Tests:** `test_mcp_source_sync_maps_records`; `test_mcp_source_down_marks_failing`.

#### MVP-11.8 Agents page
**Files:**
- Create `backend/di/services/screens/agents.py` and `backend/di/routes/screens/agents.py` (add to the importlinter
  list).
- Create `frontend/src/api/agents.ts` (+ test) and `frontend/src/pages/agents/{index.tsx,AgentsPage.tsx}`.

**Page:**
- the registry table (enable or disable, autonomy, tools and org scope edits through `agent.update`);
- runs (status, steps, waiting-for-person link);
- proposals (accept or reject);
- the tool catalogue (read).
- The nav entry is code-declared as in MVP-4.2.

**Tests:** `test_screens_agents.py` (Admin 200; Planner 403); vitest for `agents.ts`.

#### MVP-11.9 Phase 11 gate
Same as MVP-4.7.

### Phase 12: learning foundation and the end-to-end proof (story M)

#### MVP-12.1 Outcome dataset and calibration
**Files:** Create `backend/di/repositories/outcomes.py` and `backend/di/services/engine/calibration.py` (pure). Test:
`backend/tests/test_calibration.py`.

**Interfaces:**
- `outcome_rows(s) -> list[{case_id, template, cls, route, predicted_net, actual_net, confirmed_at}]` from the data
  `outcome.confirm` stores (`backend/di/services/actions/execution.py:53-66`).
- `fit(rows, min_n=5) -> dict[(template, route, cls), float]`: the median of actual/predicted per key with at least
  `min_n` rows, clipped to [0.5, 1.5].
- `CalibratedPredictor(base, factors, cls)` scales the route's value estimates by the factor.

**Tests:** exact factors for a synthetic set; fewer than `min_n` → no factor; clipping.

#### MVP-12.2 Model candidate shadow and promote
**Files:**
- Create `backend/migrations/versions/0026_model_version.py` and `backend/di/services/actions/models.py`.
- Modify `backend/di/services/screens/orchestration.py:599-605`: replace the display text with the real candidate
  status.
- Test: `backend/tests/test_model_promote.py`.

**Interfaces:**
- Table `model_version(id text pk, template text, factors jsonb, status text check (status in
  ('candidate','active','retired')), created_by text, approved_by text null, metrics jsonb, created_at)`.
- `model.fit {}`: perm `manageFlows`, act. It creates a candidate, with metrics = the mean absolute error of the active
  model vs the candidate on the outcome rows.
- `model.promote {id}`: perm `approve.flows`, commit, maker ≠ checker with the D7 wording adapted ("Maker-checker: you
  created this model, so you cannot promote it."). Add it to `FORBIDDEN_ACTIONS`.
- An active model wraps the predictor for intake cases only (book cases unchanged).

**Tests:** `test_fit_creates_candidate_with_metrics`; `test_maker_cannot_promote`; `test_promote_affects_new_intake_only`.

#### MVP-12.3 Rule suggestions from overrides
**Files:** Create `backend/di/services/modeler/suggest.py` (pure) and a read action `flow.suggestions {flow_id}`. Test:
`backend/tests/test_rule_suggestions.py`.

**Behaviour:**
- Group the journaled `decision.override` rows by (template, from route, to route) and by each scope dimension's value.
- When ≥ 3 overrides share a (to route, dimension value) and form ≥ 60 % of that value's decisions, suggest the text
  "<dimension value words>: prefer <to route name>". It is fed to `build_proposal` so it arrives checked and simulated,
  as the prototype's device suggestion does (line 2439).

**Tests:** exactly one suggestion for a synthetic override set; none below the thresholds.

#### MVP-12.4 End to end MVP smoke
**Files:** Create `frontend/scripts/smoke-mvp.mjs`.

**Journey (all through the UI):**
1. Admin creates the org `company-x` under `workspace`.
2. Developer creates a source bound to `company-x` from the catalogue and publishes an ingest workflow on `rl` with
   Open case (`template industrial`, `org company-x`).
3. A sync opens cases.
4. planner.a requests access to `company-x` (`access.requestTenant {tenant: "company-x", reason}`), and approver grants
   it (`access.decideRequest {id, decision: "approve"}`), the existing tenant access flow. The planner then uses the
   assistant ("Never recycle grade A"), simulates and submits.
5. approver approves and publishes.
6. planner.a re-evaluates a `company-x` case. The rule shows.
7. The agent autopilot is started from the Agents page and stops at a held submit; planner.a accepts.
8. approver approves the decision.
9. finance confirms the outcome.
10. Admin runs `model.fit` and sees a candidate.

Exit non-zero on any missing text.

**Done when:** `reset.sh`, the smoke and `reset.sh` again all pass.

#### MVP-12.5 Final gate and status
1. Run every phase gate command, plus `smoke-modeler.mjs` and `smoke-mvp.mjs`.
2. Update:
   - `docs/backend-steps.md`: a "Plan 8 status" section listing what each task delivered and the known gaps (copy the
     "Good-to-haves" list);
   - `AGENTS.md`: the "Current state" paragraph and the map rows for `di/services/modeler/`, `di/services/agents/`,
     `frontend/src/pages/modeler/` and `agents/`;
   - `docs/agents/history.md`: one entry.
3. Commit. Do not push (the human pushes).

---

## Phase gates (what "green" means)

- **Backend:**
  - `suite-shard.sh` 1-4 of 4 all pass and `suite-shard.sh sim` passes. The counts are at least the previous gate's
    plus the tests added since; record them.
  - `lint.sh` passes.
- **Frontend:** `web-check.sh` passes.
- **Browser:**
  - `smoke-pages.mjs` (11 accounts);
  - `smoke-rt1048.mjs` (reset before and after);
  - the phase's own smoke, from Phase 4 on.
- Any red result → R13. A phase gate commits only `PROGRESS.md`.

## Good-to-haves (not in this MVP; listed so nothing is silently dropped)

| Item | Why it matters | Source |
|---|---|---|
| Plans 03 (REST CRUD + gzip), 04 (async), 05 (OpenTelemetry incl. GenAI spans) | Production scale and observability; the GenAI semantic conventions are still "Development" status, so instrument after the code settles | `docs/agents/plans/03-05`; [OTel GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) |
| PLM writes (change requests for remanufactured part numbers) | Closes the loop into engineering; deliberately out for a read-only testbed | Dover stories §3 K, §6 |
| Re-evaluate the open queue on publish (a button) | The prototype applies a flow from the next decision only; some owners want an immediate sweep | prototype line 2575 toast |
| Guardrail editing by their named owners, with their own maker-checker | The prototype keeps guardrails locked; real clients will need to add theirs | prototype line 2447 message |
| DMN 1.5/1.6 decision-table import and export | An industry standard for business rules; lets clients bring rules from other tools | [OMG DMN](https://www.omg.org/spec/DMN/1.5), [Apache KIE DMN](https://kie.apache.org/docs/10.1.x/drools/drools/DMN/index.html) |
| An A2A agent card for the platform | Lets other enterprises' agents discover and delegate to ours; v1.0 is stable, with signed agent cards | [Linux Foundation A2A](https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year) |
| MCP protocol revision upgrade (2025-11-25 Tasks, URL elicitation; later revisions) | Long-running agent calls and safer auth flows for external agents | [MCP 2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog) |
| A LangGraph (or similar) adapter behind `runtime.py` | Language-model-planned playbooks with durable checkpoints | decision MVP-0.1 #6 |
| Email or Teams notifications for proposals and approvals | People act outside the app | Dover stories §5 |
| A production language-model provider behind `AskModel` | The Groq free tier limits (about 30 requests a minute and 1,000 a day) cannot run agents at scale | decision log 2026-11-19 |
| Exchange-programme and remanufacture routes for the industrial template | Dover's public sustainability pages describe repair, refurbishment and module exchange programmes | [Dover circularity](https://www.dovercorporation.com/sustainability/environmental/waste) |
| Digital product passport fields | A circularity data need; regulatory, so out of scope here | see the Legal note below |
| Edge cases no task covers: 2 (inter-company part transfer and value split), 15 (recall overrides every route), 16 (warranty claim vs commercial return), 19 (price moves between approval and execution), 23 (partial teardown) | Real at group scale; each needs its own data model or routes | `business-reviews/dover-user-stories.md` §4 |

## Out of scope: security, compliance, privacy

Production authentication (SSO), secrets vault, rate limits, database-level tenant isolation, penetration testing and
any regulatory reporting (e.g. ESRS E5, digital product passports) are not in this plan. They need their own plan and
must be reviewed by Kinective's Legal team before anyone relies on them.

## Sources

- PO prototype: `docs/reference/po-modeler/recover-app-prototype.html` (lines cited in the Domain spec).
- `business-reviews/dover-user-stories.md`.
- Ralphy: [README](https://github.com/michaelshimeles/ralphy) and `ralphy.sh` (`build_prompt`,
  `get_next_task_markdown`, `mark_task_complete_markdown`).
- Tool-fleet market reference: [Hilti circularity, second life of tools](https://reports.hilti.group/2022/our-stories/circularity-second-life-of-tools),
  [TechTarget on Hilti circularity centres](https://www.techtarget.com/it-strategy/feature/Hilti-Group-uses-tools-tech-to-tackle-circular-manufacturing),
  [Hilti fleet exchange flyer](https://www.hilti.ca/content/dam/urgent-folder/w1/pdf/fleet/tool_fleet_management_exchange_flyer.pdf).
- Device trade-in market reference: [Assurant asset disposition](https://assurant.com/partner-with-us/mobile-device-lifecycle-management/asset-disposition),
  [Assurant Q2 2026 trade-in trends](https://www.assurant.com/news-insights/news_releases/mobile-trade-in-programs-trends-Q2-2026).
- Multi-company industrial reference: [Dover segments](https://www.dovercorporation.com/docs/libraries/corporate/Dover-Segments-Overview-Jan-26.pdf),
  [Dover circularity and waste](https://www.dovercorporation.com/sustainability/environmental/waste).
- PLM: [Windchill REST Services ProdMgmt actions](https://support.ptc.com/help/windchill/r13.1.1.0/en/Windchill_Help_Center/WCRESTFramework/wccg_restapisaccess_PTCProdMgmtDomainActions.html),
  [GetPartStructure example](https://support.ptc.com/help/wnc/r12.0.2.0/en/Windchill_Help_Center/WCCG_RESTAccessExamplesReadBOMGetPartStructure.html).
- Agent protocols: [MCP changelog 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/changelog),
  [A2A at the Linux Foundation](https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year).
- Rules standards: [OMG DMN 1.5](https://www.omg.org/spec/DMN/1.5), [GoRules ZEN engine](https://github.com/gorules/zen).
- Observability: [OpenTelemetry GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/).
- Buyer caution with agent autonomy: [G2 enterprise AI agents report](https://learn.g2.com/enterprise-ai-agents-report).
