# Plan: agent-first Circularity Decision Workbench (product-wide)

**Purpose of this file:** a self-contained brief for building the PR *Agent-First Circularity Decision Workbench (Product-Wide)* in `index.html`. It does not assume any earlier conversation. Read it top to bottom, then start at **Phase 0**.

**Status:** phases 0 to 5 **built** on branch `feature/agent-first` (21 Oct 2026), one commit per phase, cut from `feature/demo-refactor` at `21e48de`; see section 15 and `CHANGES.md` Update 12. Phase 6 (language-model provider) is **not built**: it needs a server endpoint, and the PR default is "none". Every open decision is built on the PR default and marked **(assumed)** (section 10). Nothing is pushed or merged until the user asks.

**Source:** the PR text, kept as [`docs/PR_AGENT_FIRST_WORKBENCH.md`](PR_AGENT_FIRST_WORKBENCH.md) (copied unchanged from the repo root). This plan does not restate the PR. It maps each PR requirement to the code, settles how to build it in a single static file, and fixes the order of the work.

**Builds on:** `docs/PLAN_RBAC_ADAPTIVE_UI.md` (roles, policy, harness), `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` (Executive, Warehouse Manager, orchestration), `docs/PLAN_DEMO_SIGNIN_SINGLE_ASSET.md` and iterations two and three (sign-in, journey strip, retrieved vs predicted, `FEAT` flags). None of these branches is merged into `main` yet.

**Do not disturb the 22 Oct presentation.** The presentation runs from `feature/demo-refactor`. This work lives only on `feature/agent-first`. In addition, **`FEAT.agent`** (default `true` on this branch) can be switched off with `?agent=0` (remembered on the device; `?agent=1` turns it back on). With it off, the app behaves exactly as `21e48de`: the PO's journey labels, today's landing pages, no agent home, panel or command bar. The existing test suites must still pass with it off.

> **Legal review.** This PR adds autonomy settings, approval limits, self-approval, delegated agent actions, audit attribution, evidence-pack export, personal-data flags in field mapping and data-retention behaviour (local persistence). Wording and defaults on authorisation, audit, data protection and record retention must be reviewed by Kinective's Legal team before they are relied on or shown to clients. All data stays synthetic; no personal data is used, stored or sent anywhere.

---

## 1. What the PR asks for, in one table

| # | Ask (PR section) | Today, checked in the code on 21 Oct | Wanted |
|---|---|---|---|
| A1 | One actions layer for UI and agent (*Architecture*, *Actions layer*) | 252 `ACT` handlers, mixing view state (filters, tabs) and domain changes. Domain handlers read the DOM (`ACT.confirmApprove` reads `#ap-why`, `#ap-route`, `#ap-spend`), call `route(true)` themselves (93 calls) and are protected only by `rbRefuse`/`rbPrune` | `ACTIONS` registry + `invoke(id,input,ctx)`; pure handlers; permission, scope, risk, idempotency checked in `invoke`; screens re-render from the event bus |
| A2 | Agent runtime + Ask Circularity (*Agent runtime*) | MCP `TOOLS`, `AGENTS`, `runTool` exist, but only the Playground calls them; no natural-language entry | Rule-based provider with intent catalog, parameter extraction, plans, streamed action lines, typed cards; provider label always shown |
| A3 | App shell (*App shell*) | Sidebar, global search (`ACT.gsearch`), journey strip + guide bar | Agent home `#/home` for every role, Ask panel (Ctrl+J), command bar (Ctrl+K), ✦ assist buttons, run inbox |
| A4 | Card catalog (*Card catalog*) | Rich render functions (`bestCard`, `tiOutcome`, `execBlock`, `tiReconcile`) but tied to pages | 19 card types drawn from typed data, identical in panel, home and module |
| A5 | Trust and governance | Approval modal (15-char rationale + snapshot tick), `S.deleg`, `HARD_RULES` text | Plan previews, autonomy matrix, approval limits, self-approval rule, undo, attribution, escalation cards, agent kill switches |
| A6 | Roles and modes | 8 roles in `ROLE_POLICY`; Senior/Operational switch on the Command Center | Per-role briefing, starters, Needs you; Business and Technical modes |
| A7 | Module assists (*Module requirements*) | Source map, tables, workflow studio, conflicts, import, events, MCP, audit, access all exist as manual screens | ✦ assists that return reviewable diffs; nothing saves until accepted; versioned "AI-suggested, accepted by …" |
| A8 | Case run orchestration | `OR_STAGES` (10 technical stages), `orRun` derived from timings, `JSTEPS` (PO's 10 journey steps), `jgDone` from case fields | One run store; the PR's ten stages from **Lease ends** to **Reconcile and learn** everywhere; Next/Back/Replay/Reset on any case |
| A9 | Data, persistence, presenter mode, honest simulation | State is in memory only; a refresh loses every change. References from counters (`S.seq.apr`, `S.seq.wo`); event keys use `Date.now()`; `smTick` runs every second | Versioned persistence + tab sync; deterministic references; Quiet mode; Simulated tags; reset all or one case |
| A10 | Security, privacy, observability, a11y | Client-side demo sign-in; traces derived from seeded `CALLS` | Agent acts as the user; data never treated as instructions; one trace per run; eval and safety sets; keyboard and screen-reader support |

**Out of scope (PR):** live integrations, real writes, production auth, server-side runs, model training, trace export, and a required language model.

---

## 2. Orientation: where the code is

Still **one file, `index.html`** (4,615 lines; most of the 795 KB is CSS, the base64 logo and the `I18N` table), no build step. Line numbers drift; search by name. All 28 functions the PR names exist with the meaning it describes (checked 21 Oct); `confirmApprove` and `confirmOutcome` are `ACT` properties, not top-level functions.

| Area | Where |
|---|---|
| Seed | `mulberry32`, `RNG`, `rnd`, `rint`, `pick`, `wpick`, `gauss`, `AS_OF` (2026-10-07 09:00 UTC); heroes RT-1048, RT-1062, RT-1049, RT-1050, RT-1051, RT-1044, RT-1052, RT-1033, RT-1027, RT-1104; `genCase`, `fill`, `finalise`; `ROWS` (1,400 closed); `EXPECTED` |
| Rules and pricing | `buildRoutes`, `mkRoute`, `fail`, `rankRoutes`, `tieBreak`, `flips`, `scenRoutes`, `solvePool`, `POOLS`, `lineActuals`, `defaultSpend` |
| Execution | `STEP_TPL`, `stepsFor`, `mkExec`, `ackRef`, `hoKind`, `approvalRef`, `ackStep`, `ACT.advance`, `ACT.replay`, `instrPayload`, `ACT.viewInstr` |
| Decision handlers | `ACT.approve` (modal), `ACT.apRoute`, `ACT.confirmApprove`, `ACT.declineDecision(Ok)`, `ACT.tiSubmit`, `ACT.tiSave`, `ACT.reqEvidence`, `ACT.simResult`, `ACT.reeval`, `ACT.confirmOutcome` |
| Events and audit | `EVENTS`, `pushEvent`, `genEvents`, `CALLS`, `provFor`, `auditEntries`, `renderAudit` |
| MCP | `TOOLS`, `AGENTS`, `HARD_RULES`, `CLIENT_SERVERS`, `runTool`, `autoAgent`, `playground`, `renderMcp` |
| Integration | `SOURCES`, `SRC_TYPES`, `CANON`, `MAPPINGS`, `CONFLICTS`, `SAMPLE_CSV`, `smTick` (1 s interval at the end of the script), workflow studio (`wfValidate`, `wfTick`, `wfSave`, `wfPublish`) |
| Policy | `/*RBAC-START*/ … /*RBAC-END*/`: `FEAT`, `RB_SECS`, `PERM_ACTS`, `ROLE_POLICY`, `ACCOUNTS`, `can`, `canPage`, `canRoute`, `tenantOK`, `locOK`, `rbDenied`, `rbPrune`, `homeOf` |
| Journey | `JSTEPS`, `stp`, `stpn`, `JG`, `JG_TGT`, `jgCase`, `jgAt`, `jgDone`, `jgProg`, `jgStrip`, `jgGuide`, `jgEst`, `jgWait` |
| Orchestration | `/*ORCH-START*/ … /*ORCH-END*/`: `OR_STAGES`, `orRun`, `orFlowHTML`, `orTraceHTML`, `renderOrch` |
| Shell and router | `S` (state), `shell`, `parse`, `go`, `route`, `PAGES`, `NAV`, `ANCH`, `afterRender`, click/input/change delegation onto `ACT` |
| Invariants | `runInvariants`, `ACT.dataChecks` |

**Test harness:** headless Chrome, `run.py` + `pt.py` in the session scratchpad (`h/`), copied from the iteration-three session. Suites: `rbac.js` (208), `gf_run.js` (110), `demo.js` (91), `iter2.js` (50), `iter3.js` (55), `ovd.js` (390 px overflow). Known traps are in the *headless harness quirks* memory note (`MSYS_NO_PATHCONV=1`, `--disable-ipc-flooding-protection`, CRLF, `PYTHONIOENCODING=utf-8`).

---

## 3. Key design decisions (taken now, so the build does not stall)

### 3.1 Actions are a registry over the existing rules, not a rewrite

- `ACTIONS` is a plain object keyed by id (`decision.approve`). Each entry follows the PR's contract: `title`, `desc`, `input` (same `{t,req,ex}` mini-schema `runTool` already validates), `output`, `perm` (a `PERM_ACTS` key or `null` for reads), `risk` (`read|draft|act|commit|system`), `scope` (`case|tenant|none`), `idem(input)`, `reversible`, `emits`, `handler(input,ctx)`.
- **View-state handlers stay as they are.** Filters, tabs, sorting, zoom, drawers and navigation (`qtext`, `asTab`, `wfZoom`, `go`, …) are not domain changes, so they are not actions and keep their `route(true)`. "Every button goes through `invoke()`" applies to every **state-changing** button. The registry lists which `data-act` names are UI adapters for which action (`ACT_TO_ACTION`), and a data check fails if a domain handler is reachable without `invoke`.
- **UI adapters read the DOM; handlers never do.** For example, `ACT.confirmApprove` becomes: read `#ap-why`, `#ap-route`, `#ap-spend`, `#ap-terms`, `#ap-ack`, then `invoke('decision.approve',{case_id,route,rationale,spend,terms,reviewed})`.
- Existing rules are called, never copied: `rankRoutes`, `scenRoutes`, `tieBreak`, `flips`, `solvePool`, `wfValidate`, `lineActuals`, `mkExec`.

### 3.2 `invoke(id, input, ctx)`

In order: find the action → validate input → **permission** (`can(perm)` for `S.acct`; the agent passes the same actor, so it never has more rights) → **scope** (`tenantOK`, `locOK` on the case; `tenant_boundary` / `out_of_scope`) → **agent rules** (`ctx.preparer==='agent'`: `commit` → `approval_required` unless the call comes from the human approval card; `act` → needs `ctx.confirmed` from a plan preview unless autonomy is *Act and notify*; a stopped agent → `out_of_scope`) → **limits** (approval limit, self-approval) → **idempotency** (key already in the journal → `duplicate`, no second write) → run handler → append to the **journal** → emit events → return `{ok, output, error:{code,message}, key, seq}`.

### 3.3 State: deterministic seed + an action journal (event sourcing)

The seed is deterministic, so the cheapest correct persistence is to store **what was done**, not the whole world:

- Every successful non-read `invoke` appends `{seq, id, input, actor, preparer, runId, at, key}` to `S.af.journal`, saved under one versioned key **`circ-af-v1`** together with chat threads, autonomy settings, limits, kill switches and watch rules.
- On load, after the seed is built, the journal is **replayed** through the same handlers with `ctx.replay=true` (no toasts, timers or animations; time and references come from the entry). A refresh therefore restores every case change, run, approval and event.
- **Tab sync:** a `storage` listener replays new entries when the other tab only appended; if the journals diverged (reset or undo elsewhere), it reloads.
- **Reset all** clears the key and reloads; **Reset case** removes that case's entries and reloads; **Undo** appends an `undo` marker for a journal entry (or a whole run) and rebuilds. Rebuild = save the UI state (route, panel, thread) to `sessionStorage`, reload, restore. It takes well under a second because the seed is fast.
- **Determinism rules this needs:** (a) handlers that use randomness (`simResult`, `reeval` → `buildRoutes`) run inside `seeded(key, fn)`, which swaps the generator behind `rnd()` for one seeded from the action key; so the seed's random-call count never changes and replays are identical. (b) Time comes from `ctx.now`, stored in the entry. (c) References are derived from case and stage (`approvalRef`, `ackRef` with a per-case step number) instead of `S.seq`.

### 3.4 Ten journey stages, one run store

- `JSTEPS` becomes the PR's ten stages when `FEAT.agent` is on: **1 Lease ends · 2 Return authorised · 3 Pickup and transit · 4 Received · 5 Inspect and grade · 6 Decide · 7 Approve · 8 Execute · 9 Outcome · 10 Reconcile and learn** (labels **(assumed)** until the PO signs off; open decision O4). With the flag off, the PO's labels stay.
- Existing step chips (`stp(4)` on the best card, `[6,7,8,9].map(stpn)` on the handoff, `PAGES[*].j`) go through one mapping `jmap(old)` so every screen shows the new numbers: old 1 → 5, old 2–4 → 6, old 5 → 7, old 6–8 → 8, old 9 → 9, old 10 → 10.
- Stages 1–3 need data the seed does not have (lease end, return authorisation, pickup). It is derived from `hashId(case id)`, **not** from `rnd()`, so no seeded case shifts: lease end date, RMA reference (the asset page already shows `RMA-…`), fees, replacement order, book value, pickup date, ETA, freight cost. Every value carries the *Simulated* tag.
- **Run store** `RUNS[caseId]` = `{id:'RUN-<n>', stages:[{state, result, actor, at, keys}], keys:Set}`, seeded from the case data (the PR's rule: stages 1–5 from evidence and inspection, 6 when routes exist, 7 when a recommendation exists, 8 when approved, 9 from acknowledgements, 10 when the outcome is confirmed), then updated by events. `jgDone`, `jgProg`, `orRun`, the journey strip, the case run view, agent answers and the home page all read it.
- **Expected returns** (`EXPECTED`) get runs at stages 1–3 (`RUN-EXP-…`) but stay out of `CASES`, so the 128-case invariants hold.

### 3.5 Agent runtime: rule-based provider, typed cards

- `INTENTS`: one entry per row of the PR's intent catalog (24 rows) plus fallback and clarification. Each has `examples`, `keywords`, `extract(text, ctx)` → params (case IDs `RT-\d{4}`, asset IDs, "this/it" from context chips, source names, warehouse and site names, route names, percentages and amounts, dates like "this week" relative to `AS_OF`), `plan(params, ctx)` → `[{action, input}]`, `compose(outputs)` → `{text, cards}`. Text is built only from action outputs.
- Matching: normalise → keyword score + example-similarity (token overlap) → best intent above a threshold; a tie between areas → **clarification card**; nothing above threshold → **"I can't do that yet. I can:"** with three suggestions for the page. "Approve it" maps to the approval card intent, never to `decision.approve`.
- Each run: `RUN-AG-<seq>` with intent, provider, calls (`{action, input summary, ok, ms, badge}`), result and the user's response (accepted, edited, undone, thumbs). Lines stream at 300–600 ms (instant with reduced motion or `S.af.fast`, which tests use).
- Provider label: **"Agent: rule-based. No language model connected."** in the panel header, the home prompt bar and every agent card footer. The `PROVIDERS` table has the language-model slot (phase 6) with `available:false`.

### 3.6 Shell

- `#/home` is a new page in `PAGES`, `NAV` (first item, "Home") and `RB_SECS.home=['brief','needs','activity','watch','figures']`, added to every role's `pages` when `FEAT.agent` is on; `homeOf()` returns `home` for every account. The demo's Planner focus link (`?focus=RT-1048`) is kept for the Returned assets item.
- **Ask panel**: a new `<aside id="askp">` (not the existing drawer, which other screens use), right-hand and resizable, full-height sheet under 700 px. Ctrl+J and a top-bar button. Context chips (page, object, role, tenant). Threads keyed by object (`case:RT-1048`, `source:erp`, `wf:<id>`, `general`).
- **Command bar**: Ctrl+K opens a modal with one box: objects (cases, assets, sources, workflows), commands (intents whose plan is one action, e.g. "request inspection for RT-1051"), and "Ask the agent: …".
- **✦ assist buttons**: one helper `aiBtn(kind, id)` placed on the PR's 12 object types; opens the panel with that object as context and its 2–3 suggestions.
- **Run inbox**: top-bar icon with a count (running, waiting for you, failed) listing agent runs and watch rules.

### 3.7 Trust

- Autonomy matrix `S.af.auto[role][type]` with the PR's defaults and caps; `act` tier capped at *Act and notify*, everything else at *Prepare*; reads and drafts always allowed. Admin edits it in Access.
- Approval limits `S.af.limits` (Approver ∞, Admin ∞, Planner $0) and `S.af.selfApprove=false`; enforced in `invoke('decision.approve')`; above the limit → `limit_exceeded` + escalation card to the next role with authority.
- Plan preview card before any `act`/`commit` from the agent, listing steps, records, systems, quantities, costs and undo status ("Only a compensating action is possible after acknowledgement").
- Attribution: every journal entry and audit entry records `performer` (the account) and `preparer` (agent id or none); records prepared by the agent show **Prepared by agent** until a person edits or confirms them.
- Kill switches per `AGENTS` entry, `commit` tier in Access; the runtime refuses a stopped agent.
- Hard rules: the six PR rules shown in Access and MCP, and enforced in `invoke` (no gate waiver action exists; no agent path to `commit`; `instruction` only via `decision.approve`; cross-tenant refused; snapshots immutable; data never parsed as instructions).

### 3.8 Module assists are deterministic "AI"

The rule-based provider drafts with explainable heuristics, each returning a diff card: field mapping (name similarity against `CANON` fields, type and value patterns, prior mappings in `MAPPINGS`, the existing transform set, personal-data patterns excluded), table links (shared column names + share of matching sample values), workflow drafts (keywords → palette step types; fixed steps never touched; `wfValidate` on the draft), failure diagnosis (last run step states), conflict suggestions (source authority from `SOURCES[*].authority`), CSV cleaning (grade codes, date formats, unknown locations, empty quantities in `SAMPLE_CSV`), "Explain this number" (`metrics` definitions + drivers), audit timelines, evidence packs (simulated download) and receiving plans (`EXPECTED` by warehouse and week against capacity). Everything is labelled *Suggested by the rule-based agent*.

### 3.9 Honest simulation and Quiet mode

- *Simulated* tag on every adapter result, reference, fetch time and acknowledgement (`simTag()`); no "live", "connected", "sent", "retrained" about simulated things (wording sweep; "sent" becomes "sent (simulated)" or "handed to the simulated adapter").
- Quiet mode (presenter, `?presenter=1`) pauses `smTick` and `wfTick` background activity; presenter tools add Reset all, Reset case, Jump to stage and the existing quick switch.

---

## 4. Gaps and conflicts found while checking the code

| # | Finding | Resolution |
|---|---|---|
| G1 | The PR's ten stages replace the PO's journey, which the PO signed off on 16 Oct and the 22 Oct presentation uses | Only on this branch, behind `FEAT.agent`; labels marked (assumed), O4 |
| G2 | `reeval` (re-run the evaluation) is a state change missing from the PR's catalog | Add `case.reevaluate`, `act` tier |
| G3 | Many integration editors (`srcAdd`, `tgAdd`, `tgDel`, `wfNew`, `wfDel*`, `idpSync`, `oooSave`, `cmAdd`, `escConf`) change state but are not in the PR catalog | Register them as actions under the nearest PR verb (`source.update`, `tables.update`, `workflow.save`, `access.*`, `comment.add`, `conflict.escalate`) with the matching tier |
| G4 | `seq` counters (`S.seq.apr`, `S.seq.wo`) and `Date.now()` in event keys break idempotency and replay | Derived references and stage keys (3.3), hazard table rows 1–2 |
| G5 | `simResult` and `reeval` call `rnd()` after the seed, so their output depends on how many random calls ran before | `seeded(key, fn)` (3.3) |
| G6 | `SOURCES[*].lastSync` and `updatedAt` use `_now0=Date.now()` | Keep relative ages (they read as "4 min ago"), but fix the stored timestamps relative to a fixed clock captured once per session and mark them Simulated; seeded history (events, calls) already uses `AS_OF` |
| G7 | The PR wants actual lines not rounded to $10 (`lineActuals`) | Add optional exact actuals per line on hero cases; keep the ±25% invariant |
| G8 | Approval modal, delegation toggles and workflow publish are already human-only; the agent never reaches them | Keep; `invoke` rejects them for `preparer:'agent'` as a second line of defence |
| G9 | `runTool` (MCP Playground) has its own permission path | The MCP catalog becomes generated from `ACTIONS`; `runTool` calls `invoke` for registry tools and keeps the old ten as aliases |
| G10 | The PR's Planner limit is $0 but Planners cannot approve at all today (`approve.decisions` not in their perms) | Limit applies only once Admin both grants `approve.decisions` and raises the limit (Access); default unchanged |
| G11 | Expected returns are not cases; the PR wants a case from lease end | Expected rows get runs at stages 1–3 (3.4); not added to `CASES` |

---

## 5. Design, by area

### 5.1 Actions catalog (phase 1)

| Action | Risk | Wraps | Notes |
|---|---|---|---|
| `cases.list`, `case.get`, `case.evidence`, `case.routes`, `case.trace` | read | `visCases`/`queueRows`, `CASE_BY_ID`, `provFor`, run store | Filters as typed input (`location`, `missing`, `stage`, `received_within_days`, `owner`, `product`) |
| `case.whatIf` | read | `scenRoutes` | Never stored |
| `demand.find`, `pool.optimize` | read | `find_demand` logic, `solvePool` | |
| `analytics.query`, `audit.search`, `sources.health` | read | `metrics`, `auditEntries`, `SOURCES` | |
| `workflow.validate` | read | `wfValidate` | |
| `mapping.suggest`, `tables.suggestLinks`, `workflow.draft`, `import.clean` | draft | new (5.6) | |
| `decision.prepare`, `decision.submit`, `scenario.save` | draft | ranking + snapshot, `tiSubmit`, `tiSave` | |
| `access.requestTenant`, `mcp.propose` | draft | `tenantReqOk`, `mcpProposeOk` | |
| `evidence.request`, `evidence.recordResult`, `case.reevaluate` | act | `reqEvidence`, `simResult`, `reeval` | |
| `notify.send`, `notify.acknowledge`, `source.sync`, `workflow.save`, `mapping.apply`, `tables.update`, `conflict.resolve`, `import.commit`, `instruction.resend`, `comment.add` | act | `notifyOk`, `notifyAck`, `srcSync`, `wfSave`, `sdSave` (mapping), `tg*Ok`, `resolveConf`, `csvCommit`, `replay`, `cmAdd` | |
| `decision.approve`, `decision.override`, `decision.decline`, `outcome.confirm`, `workflow.publish`, `source.update`, `source.delete`, `credentials.rotate`, `access.decideRequest`, `access.setDelegation`, `access.setAutonomy`, `access.setLimit`, `agent.setEnabled` | commit | `confirmApprove`, `declineDecisionOk`, `confirmOutcome`, `wfPublish`, `sdSave` (connection), `srcDelOk`, `sdRotateOk`, `reqDecideOk`, `delegToggle`, new | |
| `adapter.acknowledge` | system | `ackStep` | Simulated systems only; never the agent |

### 5.2 Agent home (phase 2)

Briefing (3–5 data lines per role; table in PR *Roles*), prompt bar with starters, **Needs you** cards (approvals, evidence gaps, outcomes to confirm, failing workflows, notifications, decisions ready to submit; primary action on each), **Agent activity** (journal entries with a preparer, "Show trace", Undo where allowed), **Watching** (watch rules), **Key figures** (the role's existing `ccKpis` tiles with "Explain this number"), links to the classic modules. Business vs Technical toggle in the header for roles that can open Process orchestration (Developer and Admin default to Technical).

### 5.3 Card catalog (phase 2, finished in phase 3)

`CARDS[type](data)` → HTML, one function per card type in the PR table, sharing a frame (`afCard`) with title, badges (Retrieved / Model / Rules), provider footer for agent cards, pin and full-screen buttons. Card buttons are `data-act="afDo"` with an encoded `{action, input}` that goes through `invoke`. Pinned cards are stored in `S.af.pins` and drawn on the home page.

### 5.4 Treatment Intelligence and approvals (phases 2–3)

Decision packet card at the top of the case page; the five existing steps collapse under **Full analysis** (open by default when arriving from the journey strip so the presentation flow is unchanged with `?jstep=`). What-if questions move the scenario sliders (`S.scen`) and show a what-if card. The approval modal becomes the **approval card**: raw instruction payload (`instrPayload`), approval limit, drafted rationale that must be edited or acknowledged, evidence snapshot. The approvals inbox becomes approval cards sorted by value and deadline with a pre-approval check; batch review lists every item, each approved separately; nothing approves "all".

### 5.5 Case run view (phase 5, the earliest pieces in phase 2)

Process orchestration → Case run: ten-stage timeline (Queued, Running, Completed, Waiting for approval, Warning, Failed, Skipped), stage panel with the PR's nine fields, event feed for that run only, evidence panel, action-call panel, approval and execution status. Controls: **Next** (`runNext(caseId)`, the same function the business Continue, the journey strip and the agent call), **Back** (view only), **Replay** (stored results, no writes), **Reset case** (presenter or Admin). Blocked stages explain why and offer the escalation card.

### 5.6 Integration and platform assists (phase 4)

Exactly the PR's module list. Every assist returns a diff card; *Accept* saves a new config version with `AI-suggested, accepted by <role>`; nothing saves automatically; the agent never publishes, never touches fixed workflow steps and never bypasses the approval step.

### 5.7 What stays the same

Every existing screen, filter, search, sidebar section and deep link. Sign-in, presenter chips, the Retrieved/Predicted split, the SKU selector, the Executive exceptions, `FEAT.uplift` and `FEAT.pools`. Numbers do not change: the seed and all `runInvariants` checks stay green.

---

## 6. Data additions (synthetic, deterministic, no `rnd()` calls)

- Lease and logistics facts for stages 1–3, from `hashId(case id)`: lease end (14–60 days before receipt), lease ref `LC-…`, return authorisation `RMA-…` (same as the asset page), early-return fee, replacement order `SO-…` where demand exists, book value (from `CLASSES[cls].pnew`, age and `tau`), acquisition date, pickup date, carrier ETA, freight cost.
- Exact per-line actuals for RT-1048 (actual $9,230 stays) so lines need not round to $10.
- Seeded agent history for the home page's Agent activity (5–8 entries from `AS_OF`, labelled seeded).
- Expected-return runs at stages 1–3.

---

## 7. Phases (each ends with tests, a short report in `CHANGES.md` and one commit)

**Phase 0: Baseline.** Branch (done). Copy the PR text to `docs/`. Run every existing suite (record counts). Inventory every `ACT` handler: *view* or *domain*, its target action and tier (`ACT_INVENTORY` in the code, plus section 12 here). Record the success-measure baseline: interactions to approve RT-1048 from landing (section 11).

**Phase 1: Foundation.** `ACTIONS`, `invoke`, journal, replay, persistence (`circ-af-v1`), tab sync, reset, event bus (`afEmit`/`afOn`) with one debounced re-render, `seeded()`, derived references, stage keys, pure handlers for every domain action, UI adapters, `invoke`-side permission and scope checks, *Simulated* tags, `FEAT.agent`. Exit: every state-changing button goes through `invoke`; refresh keeps state; repeated clicks create no duplicates; every existing suite passes with `?agent=0`; data checks pass.

**Phase 2: Agent core.** Run store and the ten stages; intent and card catalogs; rule-based provider; Ask panel; command bar; ✦ buttons on cases; agent home for all eight roles; decision packet; decision flow (stages 6–10) from the home page for any seeded case. Exit: every intent returns its card on seeded cases; fallback and clarification work; prepare → approve → execute → outcome works from Home.

**Phase 3: Trust.** Plan previews, autonomy matrix, approval limits and self-approval, undo (entry and run), attribution badges, escalation cards, agent registry kill switches, approval card, batch review, safety tests. Exit: every `act`/`commit` previewed; safety tests pass; undo follows its rules.

**Phase 4: Module assists.** Source map (suggest, diagnose, set up from a sample), tables (links, descriptions), workflow studio (draft, fix, next step, explain, diagnose, clone), conflicts, import cleaning, events, MCP (catalog from registry, agent test bench, proposal review), audit (performer/preparer/run filter, timeline, evidence pack), access (autonomy, limits, agents), analytics questions and Explain this number, Command Center (KPI explain, exception cards, prepare top items, plain-language filters), Returned assets (chips, triage, bulk plan), Expected returns (receiving plan, watch rules), Asset intelligence (summary, compare). Exit: each assist produces a reviewable diff and saves only on accept.

**Phase 5: Orchestration and quality.** Case run view with stage panels and controls; `OR_STAGES` → ten stages; traces from real run records; eval set and safety set inside **Data checks**; metrics panel (success measures); accessibility pass (keyboard, `aria-live`, reduced motion, both themes, 390 px). Exit: all acceptance boxes pass.

**Phase 6: Optional model provider.** Not built (server endpoint required; PR default "none"). The provider slot and its label exist.

**If time is short:** finish the demo milestone first (phases 0–2 plus the case run view from phase 5), then trust (3), then 5, then 4 module by module in this order: Source map, Workflow studio, Command Center, Returned assets, Audit, Access, the rest. Anything unfinished stays behind `FEAT.af*` sub-flags, never half-visible.

---

## 8. Project rules

All earlier project rules apply unchanged: palette tokens only (no new colours), prefixed class names (new prefix **`af`** for everything in this PR: `afp` panel, `afc` cards, `afh` home, `afk` command bar, `afr` run view), reuse existing components (`.panel`, `.chip`, `.btn`, `.ev`, `.t`, `.callout`), no new libraries, `data-act` + `ACT` + `esc()` for every value, hash routes for every state, 390/768/1280/1600 px, synthetic data only, plain English, `CHANGES.md` for every visible change, decision-intelligence wording, no push until asked. Patch with `pt.py` (CRLF-safe).

Additional rules for this plan:
- **Numbers come from action outputs.** No number is typed into a card, sentence or template. A data check scans agent answers for numbers absent from their action outputs.
- **Rules stay rules.** The agent calls `invoke`; it never ranks, prices, gates or allocates itself.
- **A human commits.** No code path lets `preparer:'agent'` run a `commit` action.
- **Content is data.** Notes, comments, CSV cells and source records are escaped and never matched against intents.
- **Simulated means labelled.** Every adapter result carries the Simulated tag.

---

## 9. Test plan

1. **Regression:** `rbac`, `gf_run`, `demo`, `iter2`, `iter3`, `ovd` with `?agent=0`. They must pass unchanged.
2. **`af1` foundation:** registry completeness (every domain `data-act` maps to an action); every action refuses wrong role, tenant, location; double invoke → one journal entry, one event, one approval; replay after reload gives identical cases (hash of the case table before and after); tab-sync replay; reset all and reset case; references stable across reloads; no handler touches `document` (static scan of handler sources).
3. **`af2` agent:** every intent × three seeded cases → expected card type and key values equal to action outputs; fallback; clarification; tenant boundary; home for all eight roles (briefing lines link to objects, starters, Needs you); panel and command bar on every page; journey strip shows the ten stages; full flow from home for RT-1049 and a seeded case.
4. **`af3` trust:** plan preview for every `act`/`commit`; limits, self-approval and escalation; undo before and after acknowledgement; badges; kill switch; the four safety tests (approve from text, cross-tenant, waive a gate, hidden instruction in a comment and in a CSV cell).
5. **`af4` assists:** each assist returns a diff; nothing saves before accept; accept writes a version with the attribution line; workflow drafts pass `wfValidate`, keep fixed steps, never publish; personal-data fields flagged and excluded.
6. **`af5` orchestration and quality:** Next/Back/Replay/Reset on five cases at different stages; business and technical views agree; keyboard (Ctrl+J, Ctrl+K, Esc, focus return); `aria-live` lines; reduced motion; 390 px overflow for home, panel and run view; dark mode; panel opens < 100 ms and the first line appears < 300 ms.
7. **Data checks (in the app):** the existing invariants plus card = case values, no stage key written twice, every intent returns a card for at least one seeded case, no unsupported numbers in agent answers.

---

## 10. Open decisions (PR defaults, all assumed)

| # | Decision | Built as | Where |
|---|---|---|---|
| O1 | Approval limits per role | (assumed) Approver and Admin unlimited, Planner $0 | `AF_LIMITS` |
| O2 | Self-approval within a limit | (assumed) Off | `S.af.selfApprove` |
| O3 | Default autonomy | (assumed) PR table | `AF_AUTO_DEFAULT` |
| O4 | Labels of the ten stages | (assumed) PR wording; the PO signed off different labels on 16 Oct, which return with `?agent=0` | `JSTEPS_AF` |
| O5 | Language-model provider and hosting | (assumed) None; phase 6 not built | `PROVIDERS` |
| O6 | Max actions per run / items per bulk plan | (assumed) 50 and 100 | `AF_MAX` |
| O7 | Default experience flag on this branch | **Decided 21 Oct**: on, `?agent=0` restores today's app | `FEAT.agent` |
| O8 | Branch, scope and git | **Decided 21 Oct**: `feature/agent-first`; phases 0–5 in order; commit locally, no push | — |

---

## 11. Success-measure baseline (phase 0)

Counted on `21e48de` with the Approver, from sign-in landing to an approved RT-1049 decision (RT-1048 is already awaiting approval with a full packet; RT-1049 has the near-tie):

| Measure | Baseline | Counted after the build |
|---|---|---|
| Interactions to approve a recommended decision | 7 (Command Center → Approvals inbox → open case → Approve → type rationale → tick snapshot → Approve and send) | Recorded by `afMetric` (clicks + prompts) |
| Share of tasks started through the agent | 0% (no agent entry point) | Per role, from the journal (`preparer`) |
| Proposal acceptance, edit rate, undo rate, fallback rate, time to decision | Not measurable today | From agent runs and the journal; shown in Access → Agent metrics |

---

## 12. `ACT` inventory (phase 0 output)

Generated by the inventory script and kept in the code as `ACT_INVENTORY` so a data check can compare it with the registry. Summary: 252 handlers, of which roughly 70 change domain state and become UI adapters for an action; the rest are view handlers (navigation, filters, tabs, zoom, drawers, exports and downloads) and keep their `route(true)`.

---

## 13. Definition of done

- Every role signs in and lands on its agent home: a data-driven briefing, starter prompts, Needs you, agent activity, watching, key figures.
- From any page, Ctrl+J or the ✦ button opens Ask Circularity with the page's context; Ctrl+K finds objects, runs commands and asks the agent.
- "What should we do with RT-1049, and why?" returns a decision packet whose every number equals the case record; "Approve it" opens the approval card; a person approves; the run moves through Execute, Outcome and Reconcile on Next.
- Configuration assists return diffs that save only when accepted, with attribution.
- A refresh keeps everything; two tabs agree; reset restores the seed.
- Everything simulated says so; the provider label is always visible.
- All suites and data checks pass; with `?agent=0` the app is today's demo build.
- `CHANGES.md` Update 12 and `README.md` updated; committed per phase on `feature/agent-first`, not pushed.

---

## 14. Prompt to paste into a fresh session

> Read `docs/PLAN_AGENT_FIRST_WORKBENCH.md` fully, then `docs/PR_AGENT_FIRST_WORKBENCH.md`. Skim `index.html` around `/*RBAC-START*/`, `JSTEPS`, `ACT.confirmApprove`, `ackStep`, `/*ORCH-START*/`, `runTool` and the `/*AF-…*/` blocks this plan adds. Work on branch `feature/agent-first`. Follow section 8 exactly. Continue from the first phase whose exit criteria are not met (see `CHANGES.md` Update 12), run the tests in section 9 after each phase, and commit with a detailed message. Do not push or merge until asked.

---

## 15. Build report (21 Oct 2026)

| Phase | Commit | Exit criteria |
|---|---|---|
| 0–1 Foundation | `6515af4` | Every state-changing button calls `invoke()` (41 adapters; data check); handlers pure (data check); refresh keeps state (replay is exact: hash before and after reload equal); repeats create no duplicates; tab sync; legacy suites pass |
| 2 Agent core | `e408fbf` | Home for all eight roles; Ask panel, command bar, ✦; ten stages; every catalog intent returns its card; fallback and clarification; the full RT-1049 flow from Home to reconciliation |
| 3 Trust | `e30b77c` | Plan previews for every act and commit; autonomy with caps; limits, self-approval and escalation; undo within its rules (rebuild verified after reload); kill switches; attribution; safety tests |
| 4 Module assists | `c7bfa4d` | Each assist returns a reviewable diff and saves a versioned change only when accepted |
| 5 Orchestration and quality | this commit | Run view with nine-field stage panels and Next, Back, Replay, Reset; one run store for the business and technical views; traces from records; presenter tools; keyboard, live regions, reduced motion, 390 px, timing |

**Tests (headless Chrome, session scratchpad `h/`):** legacy suites with `?agent=0`: rbac 208, guided-flow 110, demo 91, iter2 51, iter3 61, 390 px 25 — all pass unchanged. New suites with the agent on: foundation 52, agent core 92, trust 46, assists 61, orchestration and quality 50, 390 px 15 — all pass. In-app Demo data checks: 53 intent tests and 7 safety tests, plus the agent-first data checks.

**Where the code is:** everything new sits between `/*AF-START*/` and `/*AF-END*/` (sections: core, inventory, actions, reads, adapters, runs, agent, cards, shell, trust, assists, run view, checks, evals) and `/*AF-CSS-START*/ … /*AF-CSS-END*/`. Small patches outside those blocks: `let RNG`, `AF_ON` and `JSTEPS_AF` before `JSTEPS`, `jmap` in `stp`/`stpn`/`journey`, `FEAT.agent`, `pushEvent`/`rbLog`/`srcEvent` attribution and stage keys, `LINE_EXACT` in `lineActuals`, `home:renderHome` in the router, no journey strip on Home, `afBoot()` and `afAfterBoot()` at boot, and honest-simulation wording.

**Assumed (unchanged):** O1–O6 in section 10. **Open for the Product Owner:** the ten stage labels (O4), autonomy defaults (O3) and approval limits (O1).

