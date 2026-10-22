# Plan: a live run board for Process orchestration, and a product that reads as live

**Purpose of this file:** a self-contained brief for a fresh session. It does not assume any earlier conversation. Read it top to bottom, then start at **Phase 0**.

**Status:** draft, not started (22 Oct 2026). Decisions L5–L8 answered by the user on 22 Oct (section 10); L9–L11 are built on their defaults and marked **(assumed)**.

**Source:** the user's review of the agent-first build on 22 Oct 2026 (three asks, plus a screenshot of the case run view: `image copy.png` in the repo root, not committed).

**Builds on:** `docs/PLAN_AGENT_FIRST_WORKBENCH.md` (Update 12: actions layer, journal, run store, case run view, presenter tools) and every earlier plan. **Branch:** `feature/live-run` (proposed), cut from `main` at `a6bf3e5` (= `feature/agent-first` at `9cfba2d`, already merged as PR #12 and served by GitHub Pages).

**Timing:** the presentation is today (22 Oct) from the hosted link, which now serves the agent-first build. This work must not reach `main` before the presentation unless the user says so (section 3, L6).

> **Legal review.** This plan removes the words that tell a viewer the data, systems and acknowledgements are simulated. The product will look like a live, connected application although nothing is connected and all data is synthetic. Before it is shown to clients or prospects, Kinective's Legal team should review how it is presented (for example in sales meetings and recorded videos), and nobody should state or imply that a named vendor product (SAP, IBM Maximo, Salesforce, MasterControl …) is connected when it is not. The repository documentation (README, CHANGES, plans) keeps saying plainly what is synthetic.

---

## 1. The feedback to solve

| # | Ask (user, 22 Oct) | Today (checked in the code) | Wanted |
|---|---|---|---|
| L1 | **Animations should not need scrolling; they should play by themselves, slowly and realistically** | Process orchestration has two stage displays. The **case run view** (`#afRunView`, top) shows ten boxes; *Replay* only moves the selection one box at a time and redraws the page (`ACT.afRunReplay` → `afRender` → `route(true)`). The **classic stage list** (`#orFlow`, further down) is what *Replay* in the page header animates (`ACT.orReplay`, 280–400 ms per stage), so the viewer has to scroll down to see it, and it is fast | Opening a case on Process orchestration **plays its run by itself**, in place, at the top of the page: each stage lights up, shows its work happening and settles. Slow and believable (about 5 s per stage, with fluid animations and counters for tools called and audit entries, section 4.2). The page never scrolls on its own and never needs scrolling to follow the animation |
| L2 | **Remove “demo”, “simulated”, “mock” and similar words across the UI; make it look like a live application** | About 160 user-visible occurrences: 52 × “(simulated)”, 31 × “Simulated …”, 13 × “synthetic”, “Demo data” pill, “Synthetic data, seed 20261007” in the sidebar, “Stand-in adapter”, “Simulated feed / live / stream”, “connected (simulated)”, “Simulate system acknowledgement”, “Simulate failure at stage…”, “Simulated net” (what-if), “Agent: rule-based. No language model connected.”, “POC”, “not a legal record”, the sign-in note “All data is synthetic and there is no real authentication”, the `Simulated` badge on cards and the lease panel. Counted on 22 Oct with a grep of `index.html` | None of these words in anything a viewer can see (text, tooltips, `aria-label`, toasts, downloaded files), for any role, light or dark, desktop or phone. Live-application wording instead: *Live*, *Connected*, *Streaming*, *Acknowledged*, *Last updated 2 min ago*, *Circularity Agent* (section 4.5). Presenter-only controls stay hidden from the audience |
| L3 | **The step box itself expands while replaying; no separate panel below** | Selecting a box opens a separate “Stage N · …” panel below the boxes with nine numbered fields (`afStagePanel`), plus three side panels (Approval and execution, Action calls, Events for this run). It is dense and reads like a form | The **box drills down in place**: it grows and shows, line by line, what the stage did, **where it fetched from and what it fetched** (“Fetched certification records from MasterControl QMS · CERT-2027-03, valid to Mar 2027”), with a spinner while a line runs and a tick when it lands. Short: three to five lines per stage, no nine-field form. The same box opens on click for any finished stage. The separate panel goes |
| L4 | **Update every file: README, CHANGES, screenshots; mention the earlier test scripts** | — | README and CHANGES (Update 13) describe the new board and wording; README-referenced screenshots that show the old wording are retaken; this plan lists the test harness and suites built in earlier sessions and how each is affected (section 6) |

**Not in scope:** new actions, data or agent intents; changes to the decision logic, the journal or the run store. The run board reads the same run store (`afRun`, `afStageStates`) as the journey indicator, Home and the agent, so they keep agreeing.

---

## 2. Orientation: where the code is

Still **one file, `index.html`**, no build step. The agent-first code sits between `/*AF-START*/ … /*AF-END*/` and `/*AF-CSS-START*/ … /*AF-CSS-END*/`. Line numbers drift; search by name.

| Area | Where |
|---|---|
| Process orchestration page | `/*ORCH-START*/ … /*ORCH-END*/`: `OR_STAGES` (now the ten stages), `orRun` (overridden from the run store), `orFlowHTML`, `orTraceHTML` (overridden: spans from the journal), `renderOrch` (wrapped), `ACT.orReplay`, `ACT.orFail` (“Simulate failure at stage…”), `ACT.orCase` |
| Case run view | AF block, run-view section: `afRunViewHTML`, `afStagePanel` (the nine fields), `ACT.afRunSel/afRunBack/afRunNext/afRunReplay/afRunReset`, `AF_STAGE_AGENT`, `AF_STAGE_ACTIONS`; CSS `.afrtl`, `.afrs`, `.afrv`, `.afnine` |
| Run store | `AF_STAGES`, `RUN_ST`, `afLease`, `afStageStates`, `afRun`, `afNextStep`, `runNext` |
| Provenance for “where it fetched from” | `provFor(c,e)` (source name, vendor, table, record, fetch time), `SOURCES` (vendor per system), `PMAP`, `afLease`, `caseRul`, `caseDemand`, `instrPayload`, the case `exec.steps[*].ack` |
| Simulation wording | Spread across the classic code and the AF block. Hot spots: `stChip`, the sidebar footer in `shell`, the top-bar `Demo data` pill (`ACT.dataChecks`), sign-in (`signInFormHTML`, `renderSignIn`), `execBlock` chips and the *Simulate system acknowledgement* button, `ACT.notifyOpen` hint, `idpHTML`, source map live dots (`Simulated live`, `Simulated stream`), MCP `playground` and `CLIENT_SERVERS` chips, what-if (`Simulated net`), event `ack` strings written by actions (`acknowledged (simulated)`, `sent (simulated)`), AF cards (`afSimTag`, `AF_BADGE_TIP`), `PROVIDERS.rule.label`, `afEvidencePack`, the lease panel, `afPresenterHTML` (presenter-only, may keep its words) |
| Presenter-only | `presenterOn()` (`?presenter=1`, remembered), `afPresenterHTML`, `jgHint`, `siSwitchTo` chips |

---

## 3. Decisions needed (answer before or during the build)

| # | Question | Recommended default |
|---|---|---|
| L5 | **How far does the wording go?** | Remove every simulation word from what the **audience** can see. Keep one discreet place for the presenter only: with `?presenter=1` the Presenter menu shows “Synthetic data · nothing is connected”. README, CHANGES and plans keep saying what is synthetic |
| L6 | **Branch and release** | New branch `feature/live-run` from `main`; commit locally; **do not merge to `main` before today's presentation** unless you ask (Pages serves `main`) |
| L7 | **Replay speed** | **Answered:** about **5 s per stage**, slow, with fluid animations: the box opens smoothly, lines slide and fade in one after another, a counter shows the number of tools called and the audit entry numbers written. A full ten-stage run takes about 50 s; *Pause*, *1× / 2×* and *Skip to now* on the board; instant with reduced motion |
| L8 | **Dates** | Keep the seeded data anchored where it is, but replace the “As of 07 Oct 2026” pill with a live indicator (“Live · updated 1 min ago”, ticking). Re-anchoring every date to today is possible but shifts many fixed dates and tests; not recommended for today |
| L9 | **The agent's label** | “**Circularity Agent**” with a small status dot, replacing “Agent: rule-based. No language model connected.” (the PR asked for that honesty label; this decision overrides it on this branch) |
| L10 | **What-if wording** | “Scenario net” instead of “Simulated net” (a what-if is not a demo simulation, but the word reads like one) |
| L11 | **Presenter controls that say “simulate”** | *Simulate system acknowledgement* → **Check for acknowledgement** (visible only to roles that can drive execution); *Simulate failure at stage…* → presenter-only, renamed **Failure drill** |

---

## 4. Design

### 4.1 One live run board (L1, L3)

Process orchestration gets **one** stage display at the top: the **live run board**. It replaces both the ten boxes of the case run view and the classic stage list (`#orFlow`). The run trace and the *Agents and services* table stay below it unchanged.

- **Layout:** two rows of five boxes at 1280 px and wider (one column on a phone). Each box shows its number, stage name and state chip as today.
- **Drill-down in place:** the expanded box spans its full row (`grid-column: 1 / -1`) and grows to at most about 260 px, with its own scroll if a stage ever has more lines. The other boxes stay visible. Only one box is open at a time; opening another closes the first. `aria-expanded` on the box button; Enter or Space toggles; Esc closes.
- **What an expanded box shows** (no nine-field form): a header line (stage, state, elapsed time, who acted), then three to five **activity lines**, then one **result line** and, for the current stage, the **next step** with its button (the existing `runNext`). Each activity line:
  `[icon] [system] verb + what · record or count · latency`
  for example `✓ MasterControl QMS · Fetched certification records · CERT-2027-03, valid to Mar 2027 · 214 ms`.
- **Activity lines per stage** are built from the case record and its provenance, deterministically (no `rnd()`), so they match every other screen:

| Stage | Lines (example for RT-1048) | Built from |
|---|---|---|
| 1 Lease ends | Oracle Lease and Finance Management · Read lease contract LC-4739, ended 11 Aug 2026 · Salesforce · Read customer intent: return at term · IBM Maximo · Read usage: 32,805 operating hours · Circularity · Opened case RT-1048 | `afLease`, `SOURCES` |
| 2 Return authorised | Optoro · Read return authorisation RMA-56509 · SAP S/4HANA · Read book value and acquisition date · SAP S/4HANA · Linked replacement order SO-48102 | `afLease`, `demandOrder` |
| 3 Pickup and transit | Optoro · Tracked pickup 21 Aug, Velo Freight · Optoro · Arrival confirmed · SAP S/4HANA · Freight cost posted | `afLease` |
| 4 Received | Manhattan Active WM · Goods receipt at Warehouse 1, 03 Oct · Circularity · Evidence check: 10 of 10 present (or which are missing) · Holding-cost clock started | case, `evidence` |
| 5 Inspect and grade | SafetyCulture · Fetched inspection report INS-… · grade B, 12 photos · MasterControl QMS · Fetched certification records · certified 24 months · IBM Maximo · Fetched service history · Bentley AssetWise · Fetched life assessment · 36 months | `provFor` per evidence item, `caseRul` |
| 6 Decide | Salesforce / SAP · Matched demand SO-48102 (confirmed) · Ritchie Bros. Market Data · 48 comparable sales (last fresh data) · Gate engine · 6 gates on 7 routes, 1 excluded · Models v1.3 · Predicted 6 routes · Ranking · Recommended Redeploy, $9,600 | `case.routes`, `caseDemand`, `GATES` |
| 7 Approve | Circularity Agent · Pre-approval check, 2 items · Drafted the rationale · Approver · Approved APR-… (or a pulsing “Waiting for the Approver”) | `afRisks`, `c.approval`, `c.submitted` |
| 8 Execute | SAP S/4HANA · Redeployment order SO-48102 acknowledged · IBM Maximo · Work order WO-… acknowledged · Manhattan Active WM · Transfer TR-… acknowledged | `c.exec.steps[*].ack` |
| 9 Outcome | SAP S/4HANA finance · Actual result reported, $9,230 · Finance · Confirmed | `c.outcome`, step 4 ack |
| 10 Reconcile and learn | Circularity · Compared 4 cost lines, predicted against actual · Proposed 3 learning records · Carried forward open demand | `c.outcome.lines`, `LEARN` |

  Stages not reached show their lines greyed as **Queued** (“Will fetch certification records from MasterControl QMS”). A stage that is waiting shows its last line pulsing (“Waiting for the Approver”). A failed or blocked stage shows the blocking line in red with the owner and the escalation button (existing `afEscalation`), not a separate panel.
- **Latencies and record counts** shown on lines are derived from `hashId(case + line)`, so they are stable across reloads and identical for everyone.

### 4.2 Auto-play: slow, believable, no scrolling (L1, L7)

- **Starts by itself** when Process orchestration opens, when the case selector changes, and on *Replay*. It plays from stage 1 up to the stage the case has reached, then stops on the current stage, expanded.
- **Pace (L7):** about **5 s per stage**. The box opens with a smooth height transition (≈400 ms); each activity line slides up and fades in, shows a spinner for 0.9–1.4 s (deterministic per line), then a tick, its result and its latency; the next line follows after ≈150 ms; the box settles to its compact done state (≈300 ms) and the next box opens. A board header shows a progress bar, an elapsed timer (“00:24”), a pulsing **Live** dot, and two running counters: **tools called** (one per activity line that reads or writes a system; for example “7 tools called”) and **audit entries** written (the IDs of the audit and event records for that stage, for example `AU-PRV-3F2A1C`, `EV-9142`, taken from `provFor(...).id` and the case's events). Each finished box shows its own small counter (“3 tools · 3 audit entries”). Fluid motion uses CSS transitions and `requestAnimationFrame`, never page-level redraws.
- **No scrolling:** the board sits at the top of the page under a compacted header (title and case selector on one line). Auto-play never calls `scrollIntoView` and never redraws the whole page: it updates only the board's DOM (no `route(true)` while playing), so the reader's scroll position and the open panel stay put. At 1440 × 900 the whole board, including the expanded box, fits on screen.
- **Controls** on the board: *Pause / Resume*, *1× / 2×*, *Skip to now* (shows the end state at once), *Replay*. Clicking any box while playing pauses playback and opens that box.
- **Reduced motion** (`prefers-reduced-motion` or `AF.fast`): no animation; the board shows the end state with the current stage open.
- **Accessibility:** the board's status line is an `aria-live="polite"` region that announces each stage as it completes (“Stage 5, Inspect and grade, completed”), not each line. Colour is never the only signal (icons plus text).
- **Ends cleanly:** navigating away stops the timers (no stray `setTimeout` writes into a page that is gone).

### 4.3 What goes, what moves (L3)

| Today | After |
|---|---|
| Nine-field stage panel (`afStagePanel`, `#afStage`) | **Removed.** Its content becomes the activity lines, result line and next step inside the box |
| Classic stage list `#orFlow` and the header *Replay* that animated it | **Merged** into the live board; the header *Replay* drives the board |
| *Approval and execution*, *Action calls*, *Events for this run* side panels | Moved under one collapsed **Run details** disclosure below the board (still there for technical users and tests) |
| *Simulate failure at stage…* select in the header | Presenter-only **Failure drill** in the Presenter menu |
| *Next*, *Back*, *Reset case* buttons | *Next* moves into the open box as the next-step button; *Back* goes (the boxes are the navigation); *Reset case* stays in the Presenter menu |

### 4.4 Interaction with the rest of the product

- The journey indicator, Home, the agent's *Explain the run* card and the run trace keep reading the same run store, so states stay identical (existing check in `af5`).
- `#/orchestration/run?case=RT-1049` still opens the run view on that case and auto-plays it.
- *Show trace* and *Open the run view* buttons elsewhere keep working.

### 4.5 Live wording (L2, L5, L8–L11)

**Rule:** no user-visible text, tooltip (`data-tip`, `title`), `aria-label`, toast, card badge or downloaded file may contain *simulat\**, *synthetic*, *demo* (as a word), *mock*, *stand-in*, *POC*, *seed*, *rule-based*, *no language model* or *not a legal record*. Internal identifiers (`execSim`, `AF.evalMode`, `sim:true`, `FEAT`) and code comments do not change.

| Where | Today | After |
|---|---|---|
| Top bar | `Demo data` pill (opens the integrity checks) | `Data checks` pill with a green dot (same modal) |
| Top bar | `As of 07 Oct 2026` | `Live · updated 1 min ago` (ticking; data anchored as today, L8) |
| Sidebar footer | `Synthetic data, seed 20261007` | `Production · all systems operational` |
| Sign-in | Notes about simulated sign-in and synthetic data | Removed; SSO wording stays as a normal enterprise sign-in |
| Source map, health, events | `Simulated feed`, `Simulated live`, `Simulated stream`, `Sync activity (simulated)`, tooltip “Stand-in adapter…” | `Live`, `Live`, `Streaming`, `Sync activity`, no tooltip |
| MCP | `connected (simulated)`, Playground “Responses come from the synthetic data” | `connected`, “Responses come from your connected data” |
| Handoff | `Sent (simulated) · awaiting acknowledgement`, `Acknowledged (simulated)`, `Done (simulated)`, `Approve and hand off (simulated)`, *Simulate system acknowledgement* | `Sent · awaiting acknowledgement`, `Acknowledged`, `Done`, `Approve and send instruction`, *Check for acknowledgement* |
| Events and audit | `ack` strings `acknowledged (simulated)`, `sent (simulated) · awaiting ack` | `acknowledged`, `sent · awaiting ack` |
| Toasts | “… (simulated)” | Same sentence without the suffix |
| Identity and users | “Simulated. In production these come from your identity provider” | “Synced from your identity provider” |
| Notify / escalation hints | “Simulated: it creates an Actions on me item…” | “Creates an Actions on me item and an audit entry” |
| Cards | `Simulated` badge; badge tip “Produced by a stand-in adapter…” | Badge removed; Retrieved, Model and Rules badges stay |
| Agent | “Agent: rule-based. No language model connected.” | “Circularity Agent” with a status dot (L9) |
| What-if | “Simulated net”, “Simulated” column | “Scenario net”, “Scenario” (L10) |
| Lease, return and transit panel | `Simulated` badge | Removed; systems named as sources |
| Evidence pack file | `simulated:true`, “generated by the Circularity POC from synthetic data. Simulated; not a legal record.” | `generated_by: "Circularity"`, generation time; no disclaimer in the file (L5: the disclaimer lives in the repo docs) |
| Data checks modal | “Seed 20261007 · mulberry32” | “All checks run on every load” |
| Run trace note | “Timings for replay and failure simulation are simulated” | Removed |
| Presenter menu (presenter only) | — | Adds “Synthetic data · nothing is connected” (L5) |

### 4.6 What stays the same

Every number, rule, gate, approval, journal entry, role permission and test-relevant ID. The decision logic and the agent are unchanged. With `?agent=0` the 22 Oct demo build still loads, but it gets the same live wording (the wording lives in shared code).

---

## 5. Phases (each ends with tests and one commit)

**Phase 0: Baseline.** Branch `feature/live-run` from `main`. Copy the harness (section 6.1) into the session scratchpad. Run every suite and record the counts. Run the wording scan (section 6.3) on the current build to get the starting list of offending strings per page and role.

**Phase 1: Live wording.** Apply section 4.5 everywhere, including strings written into events by actions (`acknowledged (simulated)` …) and the evidence-pack file. Update the assertions in the existing suites that test the old wording (section 6.2). Exit: the wording scan finds nothing for any role, page, theme or modal; every suite passes.

**Phase 2: Live run board.** Replace the run view's boxes, the nine-field panel and `#orFlow` with the board (4.1), the activity-line builder (`afStageLines(c, n)`), drill-down, *Run details* disclosure, and the presenter-only Failure drill. Exit: one board, boxes expand in place, every stage has three to five lines from the case's own data, no separate stage panel.

**Phase 3: Auto-play.** Timers, pace, spinner and tick, progress and elapsed time, Pause, 1× / 2×, Skip to now, Replay, reduced motion, no page scroll, clean stop on navigation, live-region announcements. Exit: section 6.4 checks pass.

**Phase 4: Docs and screenshots.** README, CHANGES Update 13, this plan's status and decisions, screenshots (section 7). Exit: no old wording in README-referenced screenshots; the new board has its own screenshots (light, dark, phone).

**If time is short:** Phase 1 (wording) first, since it shows on every screen; then 2 and 3 together; then 4.

---

## 6. Tests

### 6.1 The harness and suites built in earlier sessions

All of these live in session scratchpads, not in the repo. The latest copy is in the agent-first session's scratchpad (`…/d8962f53-…/scratchpad/`); the originals came from the iteration-three session (`…/3f4cb7b1-…/scratchpad/h/`). Known traps are in the *headless harness quirks* memory note (`MSYS_NO_PATHCONV=1`, `--disable-ipc-flooding-protection`, CRLF, `PYTHONIOENCODING=utf-8`, top-level `const`s are not `window` properties, so frame tests use `contentWindow.eval`).

| Tool | What it does |
|---|---|
| `h/run.py` | Headless Chrome. `test <suite.js>` injects error capture and the suite into a copy of `index.html` and prints `PASS` / `FAIL` lines; `--keep` keeps `localStorage` between runs (two-part reload tests); `--pre` runs code before the app (for example `localStorage.setItem('circ-agent','0')`); `--hash` opens a route. `shot <png> <hash>` takes a screenshot (`--session`, `--theme dark`, `--w/--h`, phone width through an iframe, `--post` runs code after load). `frame <page.html>` runs an iframe-driven test (390 px overflow) |
| `h/pt.py` | CRLF-safe find-and-replace patcher for `index.html` |
| `tools/inject.py` | Built the AF blocks from `af/*.js` and `af/af.css` into `index.html` and applied `af/patches.py`. A fresh session should edit `index.html` directly instead |
| `tools/aft.py` | Merges `h/af_common.js` (helpers: `as`, `nav`, `tick`, `bad`, `afHash`) into `h/src/<suite>.js` and runs it |
| `tools/regress.sh` | Runs the five legacy suites; pass `--pre "localStorage.setItem('circ-agent','0');"` for the demo build |

| Suite | Checks (last run 21 Oct) | Covers |
|---|---|---|
| `rbac.js` | 208 | Sign-in, role × page matrix, forbidden controls, tenant lock, reconciliation |
| `gf_run.js` | 110 | Guided flow, Executive and Warehouse Manager, orchestration, identity |
| `demo.js` | 91 | Sign-in form, demo path, retrieved vs predicted, SKU and units |
| `iter2.js` | 51 | Journey strip, step guidance, line-item actuals |
| `iter3.js` | 61 | Command Center by section, Asset Intelligence layout, edge cases |
| `ovd.js` (+`ovd.html`) | 25 | No horizontal overflow at 390 px on the legacy screens |
| `af1a.js` + `af1b.js` | 42 + 10 | Actions layer, refusals, repeats, journal replay after reload, tab sync |
| `af2.js` | 92 | Home for every role, panel, command bar, journey, packet, RT-1049 flow end to end |
| `af3a.js` + `af3b.js` | 39 + 7 | Plan previews, autonomy, limits, self-approval, kill switches, undo and rebuild |
| `af4.js` | 61 | Every module assist through its real buttons |
| `af5.js` | 50 | Case run view, Next/Back/Replay/Reset, traces, presenter, keyboard, timing |
| `afovd.js` (+`afovd.html`) | 15 | No horizontal overflow at 390 px on the agent-first screens |
| In-app evals (Demo data checks) | 53 + 7 | Intent tests and safety tests, run inside `runInvariants()` |

### 6.2 Expected changes to existing suites

These assert on wording this plan removes; update the expectations (and say so in CHANGES), do not weaken the checks:
- `rbac.js`, `gf_run.js`, `demo.js`: sign-in notes, *Simulated* chips, the *Demo data* pill and the *Simulate system acknowledgement* button label.
- `af1a.js`, `af2.js`, `af4.js`: the provider label (“rule-based”), `Simulated` badges and tags (for example “stages 1–3 facts … tagged simulated”).
- `af5.js`: the nine-field panel (`#afStage .afnine`), *Back*, `afRunSel` and the separate escalation panel move into the board; rewrite those checks against the expanded box. Classic `#orFlow` checks become board checks.
- In-app safety and intent tests are unaffected (they check behaviour, not wording), except the eval runner's references to the `Simulated` badge, if any.

### 6.3 New suite: `live.js` (wording scan)

For each of the eight roles plus signed-out, visit every reachable route (sidebar sections, a case page, an asset page, the run view, Home), open the Ask panel with two answers, the command bar, the approval form, the notify form, the Data checks modal and the source drawer; in light and dark. Collect `innerText`, every `data-tip`, `title` and `aria-label`, open toasts and the evidence-pack JSON. **Fail** on any match of
`/simulat|synthetic|\bdemo\b|\bmock|stand-in|\bPOC\b|seed \d|rule-based|no language model|not a legal record/i`.
With `?presenter=1` the scan skips the Presenter menu only.

### 6.4 New suite: `run.js` (live run board)

- Opening `orchestration/run?case=RT-1048` starts playback without any click; after about 5 s stage 1 is complete and stage 2 is running; the window's `scrollY` never changes during playback.
- The tools-called and audit-entry counters rise as lines land and match the number of lines and the audit IDs shown; each audit ID exists in the audit log (`auditEntries()`) or the event stream.
- Each stage has three to five activity lines; every line names a system that exists in `SOURCES` (or Circularity, Gate engine, Models, a role); record IDs match the case (`LC-…`, `RMA-…`, `SO-48102`, `WO-…`).
- Exactly one box is expanded; clicking a finished box pauses playback and expands it; Esc closes.
- Pause stops progress; Resume continues; 2× halves the per-line time; *Skip to now* shows the end state at once.
- Reduced motion: no timers, end state immediately.
- No `#afStage` and no `#orFlow`; *Run details* is collapsed by default and holds the three side panels.
- Playback stops when navigating away (no errors, no writes).
- States on the board equal the journey indicator's states for six cases at different stages (reuse the `af5` comparison).
- 390 px: no horizontal overflow; the board stacks in one column.

### 6.5 Regression

All suites in 6.1 (with the expectation updates of 6.2) plus `live.js` and `run.js`, in both `?agent=1` and `?agent=0` where they apply.

---

## 7. Docs and screenshots

- **README:** the intro table (*Data* row keeps “synthetic” for readers of the repo), section 6.11 *Process orchestration* (the live run board), section 13 *What is real and what is simulated* (stays, for the team; add a line that the UI no longer shows these labels and where the presenter sees them), section 15 (agent label, live wording).
- **CHANGES.md:** **Update 13** (what changed, where, what you see; the test expectation updates; the Legal note).
- **This plan:** status line, section 3 answers, build report.
- **Screenshots** (`docs/screenshots/*.webp`, taken with `h/run.py shot`, converted with Pillow): retake every README-referenced screenshot that shows the old wording (39 are referenced; most show the *Demo data* pill), and add `live-run-board.webp`, `live-run-expanded.webp`, `live-run-dark.webp`, `live-run-phone.webp`, `live-home.webp`. Screenshots referenced only by older CHANGES updates stay as the record of those releases.

---

## 8. Project rules

Earlier rules apply unchanged: palette tokens only, prefixed class names (new prefix **`lr`** for the live run board), reuse existing components, no new libraries, `data-act` + `ACT` + `esc()`, numbers from the case record (never typed into templates), deterministic values (`hashId`, not `rnd()`), 390/768/1280/1600 px, both themes, reduced motion respected, plain English, `CHANGES.md` for every visible change, commit per phase, no push or merge until asked.

---

## 9. Definition of done

- Opening a case on Process orchestration plays its run by itself, slowly, at the top of the page, with no scrolling; each stage's box expands in place and shows where it fetched from and what it fetched, with a spinner then a tick; the nine-field panel is gone.
- No user-visible text, tooltip, label, toast or file says simulated, synthetic, demo, mock, stand-in, POC, seed or rule-based, for any role, page or theme.
- All suites pass (with the documented expectation updates) plus `live.js` and `run.js`; no console errors; 390 px clean.
- README, CHANGES Update 13, this plan and the screenshots are updated; committed on `feature/live-run`; not merged to `main` until the user says so.

---

## 10. Decisions (to be filled in)

| # | Answer | Where it lands |
|---|---|---|
| L5 | **Answered 22 Oct:** audience UI only; the Presenter menu (`?presenter=1`) alone says “Synthetic data · nothing is connected”; repo docs keep saying what is synthetic | `afPresenterHTML`, every string in 4.5 |
| L6 | **Answered 22 Oct:** new branch `feature/live-run` from `main`, commit locally, do not merge before the presentation | Git |
| L7 | **Answered 22 Oct:** about 5 s per stage, fluid animations, counters for tools called and audit entries | `LR_PACE`, board header |
| L8 | **Answered 22 Oct:** live indicator, keep the data dates | Top-bar pill (`rgAsOf`) |
| L9 | (assumed) “Circularity Agent” with a status dot | `PROVIDERS.rule.label` |
| L10 | (assumed) “Scenario net” | What-if card and step 4 |
| L11 | (assumed) *Check for acknowledgement*; *Failure drill* presenter-only | `execBlock`, `afNextStep`, Presenter menu |

---

## 11. Prompt to paste into a fresh session

> Read `docs/PLAN_LIVE_RUN_AND_LIVE_UI.md` fully, then `docs/PLAN_AGENT_FIRST_WORKBENCH.md` sections 2, 3 and 15. Skim `index.html` around `/*ORCH-START*/`, `afRunViewHTML`, `afStagePanel`, `afStageStates`, `provFor`, `stChip`, `shell` and `execBlock`. Work on branch `feature/live-run`. Rebuild the harness from section 6.1, run Phase 0, then one phase at a time in section 5's order, running the tests in section 6 after each and committing with a detailed message. Do not push or merge until asked.
