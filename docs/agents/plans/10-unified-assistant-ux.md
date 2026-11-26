# Plan 10: one assistant, and a Modeler with a hierarchy (UX/UI spec and tasks)

Status: spec, not built. Written 26 Nov 2026 by the design lead. Frontend only: every capability below calls an action
or endpoint that exists today; no backend change is needed (two optional server tweaks are listed in section 7).

Inputs read: `AGENTS.md`, `CLAUDE.md`, the user's playbook ("Agentic App UX and UI That Does Not Look AI-Generated",
Nov 2026), `docs/agents/research/2026-11-ui-skills.md` section 4 (the five panel rules, cited as R1–R5 below), the code
named in each section, and the running app (read-only, as `admin`, 1440 x 900, screenshots in the session scratchpad).
The parallel audit `docs/agents/audits/2026-11-26-ui-packs/` did not exist when this was written; fold its gaps in
when it lands (section 8, open items).

Rules adopted from the research note (section 4), cited where they apply:

- R1 Never work silently: an immediate state for every run (waiting, working, done, failed). Linear AIG.
- R2 Preview before any consequential action: steps, approve, edit, take over. Smashing, Feb 2026.
- R3 Propose first; a person approves: the panel drafts, shows the diff, applies only on approval. Claude Code plan mode.
- R4 Every agent write has an undo, or says it does not. Claude Code checkpointing.
- R5 The proposer is not the grader: a separate check before a change counts. Here, the server's checks and simulation
  (`flow.propose` runs `validate` and `simulate`; `compose.*` runs the pack's guardrails) are the grader, never the
  model that drafted the change.

---

## 1. Diagnosis

The user counts three AIs. The code has more voices than that. Each section: the UI problem, then the UX problem.

### 1.1 Ask Circularity: `frontend/src/layout/AskPanel.tsx` (+ `TopBar.tsx`, `utils/askBus.ts`, `api/ask.ts`)

**UI.** A fixed overlay (`.afp`, z-index 45) that covers the right 420px of whatever page is open; on the Modeler it
sits over the canvas while the Modeler's own "Assistant" box shows in the column beside it, so two chat boxes with two
sparkle icons are on screen at once. Turns are bordered cards with shadows (`.afc`, `box-shadow: var(--shadow)`) inside
a panel that has its own shadow: the card-in-card kit look. "You:" in bold as a chat label. The context is shown as
chips ("Page: modeler") but never says what it will read.

**UX.** The best of the three: streaming, a list of lookups, sources, "Stop", suggested next steps that run only after
"Confirm". But it is blind to the work surface: on the Modeler it sends `page: modeler` and nothing about the flow, the
template or the draft, so "why is IR-01 blocking?" cannot be answered from context. It never says whether a model or the
rules answered unless a model did (`final.by_model` is sent by the server, `services/ask/service.py`, but is not in the
`AskFinal` type). The top bar's search box says "or ask anything" but has no handler, and a second Ctrl K search sits in
the sidebar.

### 1.2 The Modeler's Assistant: `frontend/src/pages/modeler/AssistantPanel.tsx`

**UI.** A 320px panel squeezed between the Inspector and Checks in `.mdl-side`; its input is a single-line box whose
placeholder is cut off ("e.g. Never send grade D motors t"). Messages are bubbles (`.mdl-msg ai|user`). The proposal is
an ALL-CAPS "PROPOSED CHANGE" label with ✓/! glyphs. The primary button says "Approve · AI applies it".

**UX.** The pattern is right (R3): `flow.propose` reads the sentence, checks it, simulates it, and the proposal is drawn
dashed on the canvas until applied. Three things are wrong. (1) The button misattributes the write: `applyProposal` is
the person's own `flow.saveDraft` with `source: "assistant"`, so "AI applies it" tells the person the agent acted. (2)
No undo after apply (R4) other than discarding the whole draft. (3) It is a second chatbot with its own memory, opening
line and voice, separate from Ask; a question typed here ("what does GR-I2 do?") is read as a change and refused.
Whether the rules or a model read the sentence (`read_by: 'rules' | 'rules+model'`) is returned and never shown.

### 1.3 Describe your business: `frontend/src/pages/modeler/DescribeDialog.tsx`

**UI.** A modal over the Modeler with a textarea, a "Read it" button, then raw output: `op: {"field":…}` JSON strings in
a list, "assumed" chips, red "Blocked (GR-…)" lines. No hierarchy between what the person said, what was assumed and
what was blocked.

**UX.** A third conversational surface with a third backend path (`config.read`, then `config.draft`, which holds the
overlay draft as a proposal on Home). It duplicates Compose's Describe step (1.4), which drafts the same change set
through `compose.start` into a composition that goes through maker-checker. Two buttons side by side in the Modeler bar
("Describe your business", "Compose") start the same conversation and end in two different approval paths.

### 1.4 Compose, Describe step: `frontend/src/pages/modeler/compose/DescribeStep.tsx` (+ `ComposePanel.tsx`, `api/compose.ts`)

**UI.** Opens as a full-width panel above the canvas, pushing the flow down. The drafted ops are again JSON strings.
The five steps (Describe, Adapter mapping, Agents, Approve, Publish) are a segmented control, which is right: this is a
work surface, not a chat.

**UX.** The copy is word for word the dialog's ("Say how your returns work in a few sentences…"). The conversation part
(describe, read, one question, draft) belongs to the assistant; the review part (mapping, agents, approve, publish) is a
work surface and should stay one.

### 1.5 Other voices the user did not count

- Workflow Studio "Build with AI" (`pages/workflows/WorkflowBuilder.tsx`: `workflow.plan`, `workflow.author`) and Ask's
  `wfdiff` card that drafts a workflow too (`AskPanel.tsx` Card): two ways to draft a workflow.
- "Agent suggests" on the case overview and stage pages (`CaseOverview.tsx`, `StagePage.tsx`), "Drafted by the
  exception assistant" in My Work (`api/mywork.ts` `draftedBy`), "Suggest mappings" in the Fabric (`ConnectFlow.tsx`,
  `SourceMap.tsx`). These are inline drafts on a work surface; they are fine as such but each names its author
  differently.
- The sparkle icon (`<Icon name="spark" />`) appears on about 20 buttons across Home, Alerts, Checks, Reports, Tasks,
  case pages, Workflows and the Fabric. A sparkle on every AI button is one of the playbook's tells, and it makes every
  page look like it has its own bot. "Do it for me" (Tasks) opens a read-only Ask: it promises an act it cannot do
  (agentic sludge).
- Backend capabilities with no conversational home: proposals that hold for a person (only Home's card), agent runs and
  their pause switch (only the Agents page), the worked analytics questions (`device.question`, only Analytics ›
  Packs), rule suggestions from overrides (`flow.suggestions`, a panel at the bottom of the Modeler).

### 1.6 The Modeler page: `frontend/src/pages/modeler/ModelerPage.tsx`

**UI.** Measured at 1440 x 900 as Admin: the page is 3,845px tall with 12 stacked panels (Rollout, Inspector,
Assistant, Checks, Impact, History, Suggestions from overrides, Customer layer, Packs, Standing policies, Models,
Repair estimate accuracy). The canvas, the one thing the page is for, gets about 560px of height, 15% of the page,
and starts below the Rollout panel. Models and Repair estimate accuracy are the Agents page's `ModelsPanel`, rendered
again here. The Customer layer is a wide form of checkboxes. Every panel has the same weight: the same border, radius,
header size and padding.

**UX.** No order of work. A planner who came to change one rule must scroll past packs and model fitting; an approver
must find the lifecycle buttons in a chip row. The bar mixes lifecycle (Submit, Discard), set-up (Describe, Compose)
and editing (Add rule) with equal weight.

---

## 2. The target: one assistant

### 2.1 The decision

There is one assistant, **Ask Circularity**. One entry point (the top-bar button and Ctrl+J), one panel, one
conversation per session, one voice. It keeps the name the demo already uses, so no new product name is introduced and
the demo's texts stay. Registered agents (case autopilot, stage agents, the configuration agent) are not chatbots:
they are workers that appear in the panel and on work surfaces as named actors with their runs and their held
proposals, never as a second chat.

The panel does three jobs, chosen by a visible **mode** in the composer, never guessed silently:

| Mode | Label in the composer | Available when | Backend (all existing) |
|---|---|---|---|
| Ask | "Ask" | always | `POST /api/ask` (SSE: start, tool, delta, reset, final); its read-only tools in `di/services/ask/tools.py` incl. `get_decision_flow` (`flow.get`), `device_question` (`device.question`), `get_inbox`, `what_if`, `explain_kpi` |
| Change this flow | "Change flow" | the Modeler is open and `s.can.edit` | `flow.propose` (read), `flow.simulate` (read), `flow.suggestions` (read), `flow.saveDraft` (the person's write, `source: "assistant"`, `note`) |
| Set up a business | "Set up" | `can('managePacks')` | `compose.prompts`, `config.read` (reading and match score), `compose.start`, `compose.answer`, `compose.get`; then the Compose work surface for `compose.systems`, `compose.markStep`, `compose.setStageAgents`, `compose.testRun`, `compose.submit`, `compose.history` |

Plus, in every mode, the panel's **Waiting for you** strip (held proposals, `GET /api/screens/home/proposals`,
`proposal.accept`, `proposal.reject`) and **Agents on this** (runs for the case in context, `agent.runTrace
{case_id}`; pause with `agent.setEnabled`).

The default mode comes from context: on the Modeler with edit rights it opens in "Change flow"; launched from
Compose's Describe tab it opens in "Set up"; everywhere else "Ask". The person can always switch (one click, or
Alt+1/2/3). When the mode is "Change flow" and the text reads like a question (ends in "?", or starts with what, why,
how, which, who, when, does, is, can), the composer shows one line under the box: "This reads like a question. Ask it
instead" (button switches mode and sends). The reverse hint shows in Ask mode on the Modeler when the text starts with
never, always, only, require, prefer, exclude, send, route, block. No model decides the mode.

### 2.2 Layout of the panel

```
+---------------------------------------------- 400px dock --+
| Ask Circularity                              [Esc] [x]     |   header: name once, close
| Looking at: Industrial returns · workspace · draft v2      |   context line (what it may read)
|------------------------------------------------------------|
| Waiting for you (2)                                [v]     |   held proposals, collapsed if 0
|   Case autopilot · Approve RT-1048 route · Value $9,200 > ..|
|------------------------------------------------------------|
|                                                            |
|  Never send grade D motors to resale                       |   the person's words, as a line
|  Checking the sentence against 5 guardrails · nothing saved|   status line (live), then done
|  +------------------------------------------------------+  |
|  | Proposed: IR-02 exclude Resale when grade = D       |  |   intent preview card (2.3)
|  | ...                                                 |  |
|  +------------------------------------------------------+  |
|                                                            |
|------------------------------------------------------------|
| [Ask] [Change flow] [Set up]           read-only · role: Admin |  mode + limits line
| +--------------------------------------------------------+ |
| | Describe a change to this flow                          | |   2-row textarea, grows to 6
| +--------------------------------------------------------+ |
|                                      [New conversation] [Propose] |
+------------------------------------------------------------+
```

- Docked, not floating: at a viewport of 1280px or wider the dock pushes the page (the app grid gains a 400px
  column; `--afpw` stays the width token). Below 1280px it overlays with a shadow; below 700px it is full screen (as
  today).
- On the Modeler, the dock and the right rail (section 3) share one column below 1600px: opening the dock swaps the
  rail out; the rail's tab strip stays as a 44px vertical column, so one click swaps back. At 1600px and wider both
  show.
- Focus moves to the composer on open and back to the invoking control on close.

### 2.3 The intent preview card (R2, R3)

Shown before any write the panel can start: applying a flow proposal, accepting a held proposal, running a suggested
next step from an Ask answer, creating a workflow from Ask's workflow draft. Not shown for reads, nor for
`compose.start` (a draft with no effect; its limits line under the composer is the preview, scaled to risk).

```
+--------------------------------------------------------------+
| Proposed: exclude Resale for grade D motors        rule IR-02 |  title: the change, in the template's words
| Read by the rules                      Δ shown dashed on canvas |  basis (2.5) and where to see it
|--------------------------------------------------------------|
| What changes                                                 |
|   + IR-02 at stage "Choose best route": exclude Resale       |
|     when grade = D                                           |  diff lines: + added, ~ changed, - removed
| Checks                                                       |
|   Passes the 5 locked guardrails                             |
|   Every outcome still reaches owner approval                 |
| Impact on the 41 open cases                                  |
|   3 cases change route · net value -$1,240                   |  from p.sim (formatImpact, tradeOff)
| Limits                                                       |
|   Saved to draft v2 only. Not published. A different person  |
|   approves it after you submit.                              |
|--------------------------------------------------------------|
| [Apply to draft]  [Apply and adjust]  [Rephrase]  [Dismiss]  |
+--------------------------------------------------------------+
```

- Buttons, in this order: **Apply to draft** (primary, the only yellow element in the card), **Apply and adjust**
  (applies, then selects the new rule in the Inspector: the takeover path), **Rephrase** (puts the sentence back in the
  composer), **Dismiss**. A person without edit rights sees the card with no Apply buttons and the line "Only a person
  with Modeler edit rights applies this."
- A blocked proposal (`kind: 'blocked'`) shows the same card with a red left rule, the title "Blocked by GR-I2", the
  guardrail's text, and only Rephrase and Dismiss. An unclear one (`kind: 'unclear'`) is not a card: it is a question
  back with the options the parser offers (escalation, 2.5).
- A suggested next step from Ask (`final.next[].action`) uses the same card: title = the step's label, "What changes"
  = the action's verb from the catalogue, Limits = "Runs as you, with your role's checks and approvals." Buttons:
  **Run it** / **Not now**. This replaces today's "Confirm" alertdialog in `AskPanel.tsx`.

### 2.4 The status line (R1)

Formula: **action word + specific item + limit**, present tense while running, past tense when done. One line, 12.5px,
muted, tabular figures, under the person's words. No spinner, no "Thinking…", no animated dots. While working the line
ends in an ellipsis glyph; when done it changes to the past tense and stays as the turn's audit summary.

| Event | While running | Done |
|---|---|---|
| Ask `tool get_case {case_id}` | Reading RT-1048 and its evidence · read-only | Read RT-1048 and 6 evidence records |
| Ask `tool list_cases` | Searching open cases you may see · read-only | Searched 41 open cases |
| Ask `tool device_question` | Answering "Which grades sell fastest?" from device records · read-only | Answered from 312 device records |
| Ask refused tool | — | Could not read Customer B's cases: outside your tenants |
| Ask fallback | — | Answered by the rules, because the model was unavailable |
| `flow.propose` | Checking the sentence against 5 guardrails · nothing saved | Checked against 5 guardrails · 1 rule proposed |
| `flow.simulate` | Simulating draft v2 on 41 open cases · nothing saved | Simulated on 41 open cases |
| `flow.saveDraft` (apply) | Saving IR-02 to draft v2 · not published | Saved to draft v2 · Undo |
| `compose.start` | Reading 62 words for workspace · drafts only | Read 62 words · matched Industrial returns |
| `compose.answer` | Drafting changes from your answer · drafts only | Drafted 4 changes, 1 assumed |
| `proposal.accept` | Running "Approve route" for RT-1048 as you | Ran as you · see History |

The mapping is a pure function `statusLine(event, ctx): { verb, item, limit, state }` with a table per tool name and a
generic fallback ("Reading <tool name> · read-only"); numbers come only from the event or its result, never invented.

### 2.5 Basis, confidence and escalation

No percentage is shown unless the server computed one. What the server already returns is enough:

| Source | Shown as (one line under the answer or card title) |
|---|---|
| Ask `final.by_model` true | "Answered by a language model (<model>) from the lookups above" (existing text) |
| Ask fallback | "Answered by the rules, because <reason>" (`final.notice`, existing) |
| `flow.propose` `read_by: 'rules'` | "Read by the rules" |
| `read_by: 'rules+model'` | "Read by a language model, checked by the rules" |
| Compose `reading.by_model` / `change_set.by_model` | "Drafted by a language model, checked by the pack's rules" (existing wording) |
| `match.nearest_only` | "Nearest pack: no pack matched well. Check every change." (amber) |
| `change_set.assumed`, `rule.assumed` | An "assumed" tag on each line, and a count in the title: "4 changes, 1 assumed" |
| Held proposal `reasons` | `reasonText(reasons)`, e.g. "Confidence 0.62 is below 0.75" (server-computed) |

Escalation: an `unclear` proposal, an Ask `clarify` card, or the Compose question shows as a question from the
assistant with option buttons and "Skip" where the backend accepts skip. The panel never proceeds past a question on
its own.

### 2.6 Held-for-a-person card ("Waiting for you")

One component, used by the dock's strip and by Home's "Proposals for you" card (today `ProposalsCard.tsx`):

```
| Case autopilot  ·  held 14:02                         RT-1048 |  actor (agentName), time, case link
| Approve route: Whole-asset resale                            |  title
| Why: buyer demand covers the unit at $9,200                  |  why (agent's words)
| Held because: Value $9,200 is above the $6,000 limit         |  reasonText(reasons), amber
| [Accept, runs as you]  [Reject…]                  View the run |  proposal.accept / proposal.reject / run trace
```

- Accept runs the held action as the signed-in person (`proposal.accept`), so it goes through the same pipeline and
  approvals. When `own` is true, Accept is replaced by `OWN_PROPOSAL_NOTE`. Reject asks for a reason.
- The strip lists the proposals for the case or flow in context first, then the rest; collapsed when empty.
- "View the run" opens the run trace (`agent.runTrace {run_id}`, `RunView`).

### 2.7 Undo and checkpoints (R4)

- After **Apply to draft**, the done status line carries **Undo** while the draft still equals what was applied (the
  dock compares the work surface's current graph JSON to the applied one; any later edit, submit or lifecycle step
  removes Undo). Undo is the person's own `flow.saveDraft {flow_id, graph: <graph before apply>, note: "Undid the
  assistant's change: <text>"}`. Both writes are journaled and show in History.
- Checkpoints that already exist are named in the card's Limits, not rebuilt: the draft (`flow.discard` returns to the
  published flow), published versions (`s.versions`, `flow.rollback` by an approver), the composition's versions
  (`compose.history`).
- Where there is no undo, the card says so in Limits: accepting a held proposal ("This runs the action; undo it from
  the case if the action allows"), running a next step.

### 2.8 Stop and steer

- **Stop** (Esc while the composer has focus and a turn runs, or the Stop button that replaces Send): aborts the Ask
  stream (existing `AbortController`); for `flow.propose`/`compose.*` it drops the result when it arrives and marks the
  turn "Stopped. Nothing was saved." (these calls only read or make drafts).
- **Steer**: while a turn runs, Enter queues the next message ("Queued: sends when this answer finishes", with a ×
  to drop it). One queue slot.
- **Agents**: the "Agents on this" row shows the latest run for the case in context (status from `JourneyStatus`); a
  person with `manageAgents` sees **Pause agent** (`agent.setEnabled {id, on: false}`), the existing kill switch.

### 2.9 Audit trail link

Every finished turn ends with one quiet line: "Lookups (3) · Call log" for Ask (the existing lookups list, collapsed;
Call log opens MCP & Tools › Calls, where Ask's calls are logged as the agent "Ask Circularity"), "See in History" after
an apply (opens the Modeler rail's History tab at the new log row), "Composition 12 · versions" for Set up, "View the
run" for agent proposals.

### 2.10 Empty and error states

- **Empty, Ask mode**: the role's starters (`AF_STARTERS`, existing, max 4) plus up to 2 from context: on a case page
  "Why this route for RT-1048?", on Analytics › Packs the pack's worked questions. One sentence above them: "Answers
  from your data, within what your role may see. Ask never changes anything." (existing text).
- **Empty, Change flow**: "Describe a change to <flow name>. It is checked and simulated before anything is saved."
  plus `flow.suggestions` as starters ("3 changes suggested by approver overrides"; each opens straight as a preview
  card, R3).
- **Empty, Set up**: the pack's sample descriptions (`compose.prompts`) as starters and the limits line "Drafts a
  composition for <org>. Nothing is published; a different person approves."
- **Errors** say what happened and what to do, keep the person's text, and never apologise:
  - network: "Could not reach Circularity. Your text is kept. [Retry]"
  - refused by policy (`refused[]`, or an action's `forbidden`/`not_permitted`): "Your role cannot <verb> <item>."
  - model unavailable: the fallback notice (Ask), or "Read by the rules" (propose); never an error.
  - blocked by a guardrail: the blocked card (2.3).
  - stale draft (the flow changed under the proposal): "The draft changed since this was proposed. [Propose again]".

### 2.11 Keyboard and accessibility

Ctrl+J (Cmd+J) toggles the dock (existing). Esc stops a running turn, else closes (through the overlay stack, as
today). Enter sends, Shift+Enter is a new line. Alt+1/2/3 picks the mode; the mode control is a radio group (arrow
keys). Tab order: header, Waiting strip, transcript, mode, composer, buttons. The transcript is `aria-live="polite"`;
status lines are announced once when done, not on every delta. The preview card is a `role="group"` with its title as
the label; Apply has a visible focus ring (existing `:focus-visible` tokens).

### 2.12 Role limits

- Ask never writes. A suggested step runs only on the person's own click through `invoke()` (rule 8).
- Agents never approve, override, decline or change access (rule 10, `services/agents/forbidden.py`). The panel never
  shows Approve, Publish, Reject-on-behalf or access buttons as the assistant's; the Limits line names the next human
  step instead ("A different person approves it after you submit").
- "Change flow" appears only with `s.can.edit`; "Set up" only with `managePacks`; Accept on a held proposal only when
  the server lists it for the person and `own` is false. These are display checks; the server enforces (rule 9).

### 2.13 What happens to the old surfaces

| Surface | Fate |
|---|---|
| `layout/AskPanel.tsx` | Replaced by `layout/assistant/AssistantDock.tsx` (Ask mode keeps its streaming, lookups, cards and next steps). `openAsk()` stays as an alias of `openAssistant({mode:'ask'})`. |
| `pages/modeler/AssistantPanel.tsx` | Removed. Its logic moves to the dock's Change flow mode; the canvas still draws the proposal dashed. |
| `pages/modeler/DescribeDialog.tsx` | Removed, with the "Describe your business" button. `config.read`/`config.draft` stay in the backend (agents and MCP use them; `config.read` still gives the match score). |
| `compose/DescribeStep.tsx` | Before a composition exists: a launcher ("Describe the business in Ask Circularity") that opens the dock in Set up. After: the review of what was drafted, kept, with the change set drawn by a shared `ChangeSetList` (no JSON strings). |
| Modeler bar "Compose" | Becomes the page tab "Set up" (section 3). |
| Workflow Studio "Build with AI" | Kept for now as a work-surface wizard, renamed "Build a workflow"; Ask's `wfdiff` card links to it ("Refine in Workflow Studio", existing). Folding it into a fourth mode is phase 2. |
| Inline launchers (Explain, Summarise, Ask about RT-1048, Diagnose…) | Kept as text links/buttons that open the dock with a question and context; the sparkle icon is removed from all of them. "Do it for me" becomes "Ask how to do this". |
| Inline drafts (Agent suggests, exception assistant, Suggest mappings) | Stay on their work surfaces; their attribution uses the basis lines of 2.5. |
| Top-bar search | Stays search. "or ask anything" is dropped from the placeholder unless Enter wires to `openAssistant({question})` when no search result matches (T6 decides by what search does today). |

---

## 3. The Modeler page layout

Principle (playbook, "the work, not the chat, is the primary surface"): the canvas is the page. Everything that edits
the selected thing sits in one rail; everything that configures the org or the pack sits in page tabs; lifecycle sits
in one bar.

```
+-- sidebar --+------------------------------------------------------------------------------------------+
|             | Modeler                                        [Industrial returns v] [workspace v]        |
|             | Flow · Customer layer · Policies · Tables* · Packs · Set up        (page tabs)              |
|             |------------------------------------------------------------------------------------------|
|             | Industrial returns · workspace   Draft v2 · 1 blocking   [Submit for approval] [Discard]      |
|             | Rollout: Replay > Shadow > Canary > Full  (only when a candidate exists, inline stepper)     |
|             |------------------------------------------------------------------------------------------|
|             |                                                            | Inspector Checks Impact History|
|             |                                                            |--------------------------------|
|             |        FLOW CANVAS (fills the viewport height)             | IR-01 · set a path             |
|             |                                                            | Stage  Choose best route       |
|             |   dashed revision marks = proposed, not applied            | When   grade = D               |
|             |                                                            | Then   exclude Resale          |
|             |                                     [+ Add rule]           | ...                            |
|             |  [+][-][fit]                         minimap               |              360px rail        |
+-------------+------------------------------------------------------------+--------------------------------+
                                                            (Ask Circularity dock opens to the right, 2.2)
```

- **Header**: title, the template and org pickers (as today), then the page tabs. The description sentence moves into
  the empty state of the rail's Inspector tab.
- **Lifecycle bar** (`LifecycleBar.tsx`): flow chip, status with the blocking count from Checks, the lifecycle buttons
  for the person's role, "Give <org> its own flow" when `s.can.fork`. Rollout (`RolloutPanel.tsx`) collapses into an
  inline stepper on this bar when `showRollout(s)`; clicking a step opens it in a drawer (Replay opens `ReplayPanel`
  in the same drawer).
- **Canvas**: `height: calc(100vh - <header + bar>)`, min 520px. "Add rule" moves onto the canvas (bottom right),
  because it acts on the canvas.
- **Rail** (new `ModelerRail.tsx`, 360px), four tabs: **Inspector** (`FlowInspector`), **Checks** (`ChecksPanel`, tab
  shows the blocking count; clicking a check selects the node and switches to Inspector), **Impact** (`ImpactPanel` and
  `WhatIf`), **History** (`HistoryPanel`: versions, rollback, exports, log). The selected tab is kept per session.
  Selecting a node switches to Inspector unless the person pinned another tab.
- **Page tabs** (secondary work, one at a time, below the header; the Flow tab is the default):
  - Customer layer: `OverlayPanel`.
  - Policies: `StandingPolicyPanel`.
  - Tables (tool_fleet only, as today): `TablesPanel`.
  - Packs: `PacksPanel` (shown to `managePacks`).
  - Set up (shown to `managePacks`): `ComposePanel`, opened by `?compose=<id>` (existing) or from the dock.
  - Tab in the URL: `?tab=layer|policies|tables|packs|setup`, so the dock and links can open one.
- **Moved off the page**: `ModelsPanel` and Repair estimate accuracy (already on the Agents page; the Modeler shows a
  one-line link "Models used by this flow: Agents › Models"). `SuggestionsPanel` moves into the dock's Change flow
  empty state (and its count shows on the rail's Impact tab: "3 suggestions from overrides").
- Below 1100px the rail drops under the canvas as tabs (as `.mdl-main` does today).

---

## 4. Visual direction

Subject: industrial asset decisions, read by planners, approvers and engineers. The one memorable element, borrowed
from that world: **proposed changes are drawn like revision marks on an engineering drawing** (a dashed outline and a
small triangle tag with the revision number, "Δ2"), on the canvas and in the preview card's diff. This is where the
boldness goes; everything else is quiet.

Brand stays: ink and signal yellow on warm paper. The stylesheet `frontend/src/styles/legacy.gen.css` is generated from
the demo and is never hand-edited; new tokens go in a new `frontend/src/styles/assistant.css`, imported after it in
`main.tsx`, under `:root` and `:root[data-theme="dark"]` (the app's theme switch; it does not use
`prefers-color-scheme`).

### 4.1 Colours (six, with roles)

| Name | Token | Light | Dark | Role |
|---|---|---|---|---|
| Graphite | `--ink` (exists) | #141414 | #F3F2EE | Text, the assistant's voice. The assistant has no colour of its own. |
| Signal yellow | `--yellow` (exists) | #FFDD00 | #FFDD00 | The one primary action per card (Apply to draft, Accept). Never decoration, never an icon fill. |
| Drafting line | `--as-rev` (new) | #4B4541 (= `--ink2`) | #CBC8C1 | Revision marks: dashed outline 1.5px, dash 5 3, and the Δ tag. |
| Drafting wash | `--as-rev-bg` (new) | rgba(20,20,20,.035) | rgba(243,242,238,.05) | Fill behind proposed nodes and `+` diff lines. |
| Held amber | `--as-hold` (new, = `--warn`) | #8A6400 | #E5A543 | Waiting for a person, nearest-pack, assumed. Left rule 3px on held cards. |
| Guardrail red | `--as-block` (new, = `--bad`) | #B3382C | #EC7A6E | Blocked by a guardrail. Left rule 3px; the guardrail id in mono. |

Surfaces reuse `--panel` (dock), `--panel2` (preview card), `--line`/`--line2` (hairlines). No gradients, no purple, no
glass, no glow on the AI.

### 4.2 Type roles

- Display, `--f-display` (Plus Jakarta Sans, exists): dock title 15px/600; preview card title 14px/650.
- Body, `--f-body` (exists): turns 14px/1.5; lines under 72 characters in the dock (400px minus 32px padding).
- Status and basis lines: 12.5px, `--muted`, `font-feature-settings: 'tnum'` (exists on body).
- Mono, `--f-mono` (JetBrains Mono, exists): rule ids, guardrail ids, tool names, case ids in lookups, 12px.
- Sentence case everywhere. No uppercase eyebrows in the dock (today's "PROPOSED CHANGE" `.label` goes).
- Open question, not in this plan: the body face is Inter, the most common AI default. Changing it is a brand decision
  for the demo too; raise it with the PO.

### 4.3 Spacing and shape

4px base. Dock padding 16px; 20px between turns; a hairline (`--line2`) between turns instead of boxes. The person's
words are a plain line in 14px/600, not a bubble; no avatars, no "You:". Only the preview card and the held card are
boxed (radius 8px, 1px `--line`, no shadow); nothing is nested in another box. The docked panel has no shadow and no
radius (it is part of the layout); the overlay form below 1280px keeps `--shadow`.

New tokens: `--as-w: 400px` (alias of `--afpw`), `--as-pad: 16px`, `--as-gap: 20px`, `--as-radius: 8px`,
`--as-dur: 240ms`, `--as-ease: cubic-bezier(.2, 0, 0, 1)`.

### 4.4 Motion

- One meaningful motion: when Apply to draft succeeds, the proposed node's dashed revision outline closes into a
  solid line (`stroke-dashoffset` to 0, then the dash removed, `--as-dur`, `--as-ease`), and the Δ tag fades out. It
  marks the moment a proposal becomes part of the draft.
- None on frequent actions: opening and closing the dock (Ctrl+J), sending, streaming text, switching modes and rail
  tabs are instant. No typewriter effect, no pulsing dots, no hover lift on cards.
- Animate only `transform`, `opacity`, `stroke-dashoffset`; never `transition: all`.
- Reduced motion: the global rule in `legacy.gen.css` already removes animation and transition; the outline simply
  becomes solid.

### 4.5 Tells removed (playbook Part 3)

Sparkle on every AI button (keep one, on the dock's entry); bubbles and "You:"; card-in-card with shadows; ALL-CAPS
labels in the panel; "Approve · AI applies it"; "Do it for me"; ✓/! glyphs as icons (use the existing `Icon` set);
"Thinking…" dots.

---

## 5. Contracts written before the fan-out (task T0, the lead)

So T1–T7 can start at once, the lead commits two small files verbatim before starting writers.

`frontend/src/layout/assistant/types.ts`

```ts
import type { ComponentType } from 'react';
export type AssistantMode = 'ask' | 'change' | 'setup';
export interface AssistantContext {
  page: string; section?: string; caseId?: string; role: string;
  flow?: { id: number; name: string; template: string; org: string; canEdit: boolean; draftVer: number | null };
  pack?: string; org?: string;
}
export interface OpenRequest { mode?: AssistantMode; question?: string; composeId?: number }
export type TurnState = 'waiting' | 'working' | 'done' | 'held' | 'blocked' | 'failed' | 'stopped';
export interface Status { verb: string; item: string; limit?: string; state: TurnState }
export interface Turn { id: number; mode: AssistantMode; text: string; status: Status[]; data: unknown; error?: string }
export interface ModeDef {
  id: AssistantMode; label: string; placeholder: string; limits(ctx: AssistantContext): string;
  /** null when available, else why not (shown on the disabled radio) */
  unavailable(ctx: AssistantContext): string | null;
  send(text: string, ctx: AssistantContext, io: { signal: AbortSignal; patch(f: (t: Turn) => Turn): void }): Promise<void>;
  Turn: ComponentType<{ turn: Turn; ctx: AssistantContext; ask(text: string, mode?: AssistantMode): void }>;
  Empty: ComponentType<{ ctx: AssistantContext; ask(text: string, mode?: AssistantMode): void }>;
}
```

`frontend/src/utils/workSurface.ts` (how a page tells the dock what it is working on; pages register, the dock reads)

```ts
export interface FlowSurface {
  kind: 'flow'; flowId: number; name: string; template: string; org: string; canEdit: boolean; draftVer: number | null;
  graph(): FlowGraph;                 // the current working graph
  flush(): Promise<void>;             // save a pending autosave first
  showProposal(p: Proposal | null): void;           // draw dashed on the canvas, or clear
  applyGraph(g: FlowGraph, nodeId: string | null, call: () => Promise<ActionResult<{ checks: Check[] }>>): Promise<boolean>;
  select(nodeId: string | null, tab?: 'inspector' | 'history'): void;
}
export type Surface = FlowSurface | { kind: 'compose'; id: number | null; org: string; pack: string };
export function registerSurface(s: Surface | null): void;
export function useSurface(): Surface | null;     // useSyncExternalStore over one module-level value
```

Plus `openAssistant(req: OpenRequest)` and `onOpenAssistant` in `utils/askBus.ts` (T1 implements; `openAsk(q)` stays
as `openAssistant({ mode: 'ask', question: q })`).

---

## 6. Task breakdown for parallel writers

Rules for every task: pages call only `src/api/*.ts` (rule 6); every write through `invoke()` (rule 8); no change to a
number or text of the industrial demo or RT-1048 except those listed in the decision-log draft (section 9); writers
check with `scripts/dev/wt-check.sh <k>` and `bash scripts/dev/web-check.sh`; each task adds its Playwright check as
its own file `frontend/scripts/smoke-a10-<task>.mjs` (Node Playwright, `channel: 'chrome'`, pattern of
`smoke-pages.mjs`); a check that writes resets before and after. A task that removes a surface updates the existing
smokes that use it (named below; one owner each).

Skills (in `.claude/skills/` on the `lead-merge` branch, commit `162b359d`; writers based on it have them): every UI
writer (T1–T7) reads `.claude/skills/frontend-design/SKILL.md` and
`.claude/skills/web-interface-guidelines/SKILL.md` before coding; T7, and T2 for the apply moment, also read
`.claude/skills/emil-design-eng/SKILL.md` (motion restraint). This spec's tokens and rules win where they differ. Part
of every task's **done**: a review of the task's changed files against web-interface-guidelines, reported in the
task's report as `file:line` findings with what was fixed and what was left (and why).

T0 (lead, XS, before fan-out): commit `layout/assistant/types.ts` and `utils/workSurface.ts` from section 5.

After T0, **T1, T4, T5, T6, T7 start at once** (five in parallel); T2 and T3 start at once too, against the contracts,
and integrate when T1 lands (seven in parallel at most).

### T1. The dock and Ask mode (M)

- Files (owned): `frontend/src/layout/assistant/AssistantDock.tsx` (new), `layout/assistant/modes/ask.tsx` (new; the
  answer turn and cards moved from `AskPanel.tsx`), `layout/assistant/status.ts` + `status.test.ts` (new),
  `layout/assistant/turns.ts` + `turns.test.ts` (new: turn reducer, queue slot, stop), `layout/assistant/modes/index.ts`
  (registry of modes; T2 and T3 each add one line, see shared files), `layout/AskPanel.tsx` (deleted),
  `layout/App.tsx` (mount the dock; docked grid column at >= 1280px), `utils/askBus.ts` (`openAssistant`),
  `api/ask.ts` (add `by_model` to `AskFinal`; send `context.section` = template on the Modeler), `layout/TopBar.tsx`
  (entry button only: label "Ask Circularity (Ctrl+J)", unchanged icon), `frontend/scripts/smoke-ask.mjs` (update).
- Done: one dock on every page; header, context line, mode radio (modes from the registry; unavailable ones disabled
  with the reason), composer, Stop, queue, New conversation; Ask mode at parity with today (stream, lookups, cards,
  sources, next steps) plus status lines (2.4), the basis line (2.5), next steps through the preview card (2.3), the
  audit line (2.9), the empty and error states (2.10), keyboard (2.11). Context from `useSurface()` and the route.
- Tests: vitest for `statusLine` (every row of the 2.4 table, the generic fallback, a refused tool), the turn reducer
  (queue, stop, reset event clears text). Playwright `smoke-a10-t1.mjs`: as `planner.a`, Ctrl+J on Home, click a
  starter, see a done status line and an answer, Esc closes and focus returns. Read-only.
- Depends on: T0.

### T2. Change flow mode (M)

- Files (owned): `layout/assistant/modes/change.tsx` (new), `layout/assistant/PreviewCard.tsx` (new; also used by
  T1 for next steps and T5 for held proposals: T2 owns it, T1 and T5 import it), `pages/modeler/proposal.ts` +
  `proposal.test.ts` (add `previewOf(p, s)`: title, diff lines, checks, impact, limits; `undoNote(text)`),
  `api/modeler.ts` (`saveDraft` takes an optional `note`), `frontend/scripts/smoke-modeler.mjs` and
  `frontend/scripts/smoke-mvp.mjs` (replace `#mdl-ask` and "Approve · AI applies it" with the dock).
- Done: in the Modeler with edit rights the dock opens in Change flow; a sentence runs `flow.propose`, the proposal is
  drawn through `surface.showProposal`, the preview card shows diff, checks, impact (from `p.sim`), basis (`read_by`)
  and limits; Apply to draft / Apply and adjust / Rephrase / Dismiss; blocked and unclear handled (2.3, 2.5); Undo
  (2.7) while the draft is unchanged; the empty state lists `flow.suggestions` and opens each as a preview card; the
  question hint (2.1).
- Tests: vitest for `previewOf` (rule, step, blocked; limits text by role), the Undo availability rule, the question
  heuristic. Playwright `smoke-a10-t2.mjs` (writes: reset before and after): as `admin`, Modeler › Industrial returns,
  propose "Never send grade D motors to resale", see the card, Apply to draft, see "Saved to draft", Undo, History shows
  both notes.
- Depends on: T0; integrates with T1 (dock) and T4 (surface registration).

### T3. Set up mode and the Compose launcher (M)

- Files (owned): `layout/assistant/modes/setup.tsx` (new), `pages/modeler/compose/ChangeSetList.tsx` (new; replaces
  the JSON-string lists), `pages/modeler/compose/changeSetView.ts` + `.test.ts` (new: op to plain sentence, assumed
  count, blocked lines), `pages/modeler/compose/DescribeStep.tsx` (launcher before a composition; `ChangeSetList`
  after), `pages/modeler/DescribeDialog.tsx` (deleted), `frontend/scripts/smoke-p9-2.mjs` step 7,
  `smoke-p9-8.mjs`, `smoke-p9-10.mjs`, `smoke-p9-11.mjs` (the Describe steps).
- Done: Set up mode runs describe → `compose.start` → reading line, match (with `config.read` score, nearest-pack
  amber) → the one question (options and Skip, `compose.answer`) → drafted changes as plain sentences with assumed and
  blocked lines → "Open in Set up" (navigates to `?tab=setup&compose=<id>`). The DescribeDialog and its button are gone.
- Tests: vitest for `changeSetView` (each op kind to a sentence, assumed count, blocked guardrail line). Playwright
  `smoke-a10-t3.mjs` (writes a draft composition: reset before and after): as `admin`, open the dock in Set up from the
  Modeler's Set up tab, pick the first sample prompt, answer the question, see "Drafted N changes", Open in Set up shows
  composition N on the Describe step.
- Depends on: T0; integrates with T1 and T4 (the Set up tab).

### T4. Modeler layout (L)

- Files (owned): `pages/modeler/ModelerPage.tsx`, `pages/modeler/modeler.css`, `pages/modeler/ModelerRail.tsx`
  (new), `pages/modeler/ModelerTabs.tsx` (new), `pages/modeler/LifecycleBar.tsx` (rollout stepper),
  `pages/modeler/RolloutPanel.tsx` (drawer form), `pages/modeler/ReplayPanel.tsx` (in the rollout drawer),
  `pages/modeler/AssistantPanel.tsx` and `pages/modeler/SuggestionsPanel.tsx` (deleted; the suggestions logic is in
  `api/modeler.ts`, used by T2), `pages/modeler/railTab.ts` + `.test.ts` (new: which tab shows after a selection, a
  check click, a pin).
- Done: the layout of section 3 (header with page tabs and `?tab=`, lifecycle bar with inline rollout, full-height
  canvas with Add rule on it, 360px rail with four tabs, secondary panels in tabs, Models moved to a link);
  `registerSurface` with the `FlowSurface` handle (graph, flush, showProposal, applyGraph, select) and `{kind:'compose'}`
  on the Set up tab; the rail and the dock share one column below 1600px (2.2).
- Tests: vitest for `railTab`. Playwright `smoke-a10-t4.mjs` (read-only): as `planner.a` and `admin` at 1440 x 900, the
  Modeler page is no taller than 1.2 viewports on the Flow tab, the canvas is at least 520px tall, the four rail tabs
  and the page tabs exist, clicking a failing check selects its node in the Inspector.
- Depends on: T0. Also updates `smoke-modeler.mjs` selectors for moved panels only if T2 has not (coordinate with T2:
  T2 owns that file; T4 sends its selector changes to T2's writer through the lead).

### T5. Held-for-a-person and agents in the dock (S)

- Files (owned): `components/ProposalRow.tsx` (new, the card of 2.6), `components/proposalRow.test.ts` (new: the
  order by context, the own-proposal rule), `pages/home/ProposalsCard.tsx` (uses `ProposalRow`),
  `layout/assistant/WaitingStrip.tsx` (new), `layout/assistant/AgentsOnThis.tsx` (new: latest run for the case via
  `runTrace({caseId})`, Pause with `setAgentEnabled`), `pages/agents/AgentsPage.tsx` (open a run from `?run=<id>`).
- Done: the strip of 2.6 at the top of the dock, Accept through the preview card (Limits: "Runs as you"), Reject with
  a reason, View the run; Home's card renders the same row; the agents row on case pages.
- Tests: vitest as named. Playwright `smoke-a10-t5.mjs` (read-only unless a proposal is pending; it only opens and
  reads): as `approver`, Ctrl+J on Home shows "Waiting for you (n)" equal to Home's card count, and View the run opens
  the run drawer.
- Depends on: T0; integrates with T1 (mount point is one line in `AssistantDock.tsx`, done by T1 as a placeholder
  `<WaitingStrip/>` import).

### T6. Launchers, copy and the sparkle (S)

- Files (owned): `pages/home/HomePage.tsx`, `AlertsPage.tsx`, `ChecksPage.tsx`, `ReportsPage.tsx`, `TasksPage.tsx`,
  `pages/case/CaseOverview.tsx`, `pages/case/StagePage.tsx`, `pages/case/caseActions.ts`,
  `pages/workflows/WorkflowPage.tsx`, `pages/workflows/WorkflowList.tsx` (button label "Build a workflow"),
  `pages/integration/ConnectFlow.tsx`, `pages/integration/SourceMap.tsx`, `pages/integration/FabricOverview.tsx`,
  `layout/Sidebar.tsx` (search), the top-bar search input in `layout/TopBar.tsx` (T1 owns the entry button lines of
  the same file; T6 edits only the `.frsearch` block, merge in order T1 then T6).
- Done: no `<Icon name="spark" />` outside the dock's entry and header; every inline launcher calls `openAssistant`
  with its question and context (case id, KPI); "Do it for me" becomes "Ask how to do this"; demo texts otherwise
  unchanged ("Explain this number", "Agent suggests", "Ask about RT-1048"); the search placeholder matches what search
  does; one Ctrl K search, not two.
- Tests: vitest `caseActions.test.ts` (existing, extended: the question and context each launcher sends). Playwright
  `smoke-a10-t6.mjs` (read-only): count spark icons per page over the 11 accounts' pages (0 outside the top bar), and
  "Ask about RT-1048" opens the dock with "Case: RT-1048" in the context line.
- Depends on: T0 (`openAssistant` signature; until T1 lands it can call the existing `openAsk`).

### T7. Tokens, the revision mark and the one motion (S)

- Files (owned): `frontend/src/styles/assistant.css` (new: tokens of 4.1 and 4.3 in light and dark, dock, turn, card,
  status line, revision mark), `frontend/src/main.tsx` (one import line), `pages/modeler/FlowCanvas.tsx` and
  `FlowCanvas.test.tsx` (the dashed outline, the Δ tag with the draft version, the resolve-to-solid on apply via a
  `resolved` prop), `components/Icon.tsx` (only if a Δ glyph is needed).
- Done: the dock and cards use only these tokens; the proposed node shows the revision mark in both themes; the one
  motion of 4.4 plays on apply and not under reduced motion.
- Tests: vitest in `FlowCanvas.test.tsx` (proposed node has the revision class and tag; `resolved` removes it).
  Playwright `smoke-a10-t7.mjs` (read-only): screenshots of the dock and a proposed node in light and dark into the
  session scratchpad, and a contrast check of status-line text against `--panel` (>= 4.5:1) in both themes.
- Depends on: T0. Visual integration with T1/T2 is by class names fixed in this spec: `.as-dock`, `.as-turn`,
  `.as-status`, `.as-card`, `.as-card.held`, `.as-card.blocked`, `.rev`, `.rev-tag`.

### T8. Integration and gate (M, lead or one writer, last)

- Files (owned): `frontend/scripts/smoke-a10.mjs` (runs the seven checks in order, resets around the writing ones),
  `docs/agents/decision-log.md` (the entry of section 9), `docs/guides/users/` (the pages that mention Ask, the
  Modeler assistant, Describe your business or Compose), `AGENTS.md` map rows (`layout/assistant/`, plan 10 status).
- Done: all checks green on a reset database; `smoke-pages.mjs` (11 accounts) and `smoke-rt1048.mjs` unchanged and
  green (RT-1048 numbers and texts at parity); `web-check.sh` green; the plan-9 smokes updated by T2/T3 green.
- Depends on: T1–T7.

### Shared files and owners

| File | Owner | Others |
|---|---|---|
| `layout/assistant/types.ts`, `utils/workSurface.ts` | T0 (lead) | read by all; changes go through the lead |
| `layout/assistant/modes/index.ts` | T1 | T2, T3 each add one import line after T1 merges |
| `layout/assistant/AssistantDock.tsx` | T1 | T5 mount line placed by T1 |
| `layout/assistant/PreviewCard.tsx` | T2 | imported by T1, T5 |
| `layout/TopBar.tsx` | T1 (entry button) | T6 (search block), merged after T1 |
| `api/modeler.ts` | T2 | — |
| `pages/modeler/ModelerPage.tsx` | T4 | — |
| `smoke-modeler.mjs`, `smoke-mvp.mjs` | T2 | T4 sends selector changes through the lead |
| `smoke-p9-2/8/10/11.mjs` | T3 | — |
| `main.tsx` | T7 | — |

| Task | Size | Depends on | Parallel group |
|---|---|---|---|
| T0 contracts | XS | — | first |
| T1 dock + Ask | M | T0 | A |
| T2 Change flow | M | T0 (integrates T1, T4) | A |
| T3 Set up | M | T0 (integrates T1, T4) | A |
| T4 Modeler layout | L | T0 | A |
| T5 Held + agents | S | T0 (integrates T1) | A |
| T6 Launchers + copy | S | T0 | A |
| T7 Tokens + motion | S | T0 | A |
| T8 Integration + gate | M | T1–T7 | last |

---

## 7. Optional server tweaks (not needed for the plan)

- `AskObject.kind` documents case, kpi, source, workflow, exception, event. Adding `flow` (id = flow id) would let Ask
  read the exact draft in context; until then the dock sends `page: modeler`, `section: <template key>` and Ask's
  `get_decision_flow` tool reads the flow of that template.
- `flow.saveDraft` could record `source: "undo"` for the Undo of 2.7; today the note carries it.

## 8. Open items

- Fold in `docs/agents/audits/2026-11-26-ui-packs/README.md` when it exists (it did not when this was written).
- Inter as the body face (4.2): a brand question for the PO.
- Phase 2: Workflow Studio's builder as a fourth mode ("Build a workflow") using the same preview card.
- Compliance-sensitive behaviour in the panel (agents' held actions on customer data, the audit trail, takeover and
  undo limits) should be reviewed by Kinective's Legal team before it is relied on or acted on.

## 9. Decision-log entry (draft, for T8 to add)

| Date | Decision | Why | Alternatives | Where |
|---|---|---|---|---|
| 2026-11-26 | **One assistant: Ask Circularity is the only conversational surface** (plan 10). The global panel becomes a docked panel with three modes: Ask (read-only, `POST /api/ask`), Change flow (`flow.propose`, `flow.simulate`, `flow.suggestions`; the person applies with `flow.saveDraft`, with an Undo that is the person's own `flow.saveDraft` of the earlier graph) and Set up (`compose.start`, `compose.answer`; the Compose work surface keeps mapping, agents, approve and publish). The Modeler's Assistant panel and the "Describe your business" dialog are removed; `config.read`/`config.draft` stay for agents and MCP. Held proposals and agent runs show in the panel through `proposal.accept`/`proposal.reject` and `agent.runTrace`. Text changes against the demo and plan 8/9 screens: "Approve · AI applies it" becomes "Apply to draft" (the write is the person's), "Do it for me" becomes "Ask how to do this" (Ask cannot act), the sparkle icon stays only on the panel's entry, and the Modeler's secondary panels move to tabs (Models to the Agents page only). No number, rule, guardrail or decision text changes; RT-1048 and the 128 cases are unchanged. | Users saw three chatbots with three voices and two approval paths for the same description; the playbook's agent patterns (preview, visible state, undo, takeover) were partly built in each and whole in none. | Keep three panels with a shared style (still three voices); a model-chosen mode (silent routing the person cannot see); a new product name for the assistant (churn on demo texts). | `frontend/src/layout/assistant/`, `pages/modeler/ModelerPage.tsx`, `ModelerRail.tsx`, `compose/DescribeStep.tsx`, `styles/assistant.css`; smokes `frontend/scripts/smoke-a10*.mjs` |
