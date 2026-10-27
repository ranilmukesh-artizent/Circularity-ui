# Plan: Decision Workbench stage pages (one page per stage, a case overview, "what happened" first, no long scroll)

**Purpose of this file.** It records why the Decision Workbench is hard to follow today (measured), what UX research and comparable products recommend, the decisions taken, and the design, phases and tests to build it. A fresh session can build the work from it.

| | |
|---|---|
| **Status** | Built on 27 Oct 2026 (section 16). D1–D5, D7, D11, D13, D19 and D20 decided by the product owner; the rest assumed (section 11) |
| **Source** | Feedback from everyone who used the workbench (27 Oct 2026): *"stages 1 2 3 4 5 all come up to the same page, too much scrolling, no proper highlighting boxes or cards; each time I click Next everything should be distinguishable and easy to follow; better to have separate pages for each step; outcomes and what happened must be shown well; components should be superb"*. Measurements in section 3 |
| **Builds on** | `PLAN_SIDEBAR_AND_CONNECTION_FABRIC_REVAMP.md` (component kit, charcoal theme, menu), `PLAN_AGENT_FIRST_WORKBENCH.md` (journey strip, agent suggests, decision packet, approval card), `PLAN_LIVE_RUN_AND_LIVE_UI.md` (run stages), `PLAN_EXECUTION_DETAIL_AND_COST_TRACE.md` (handoff plan, route and timing, cost trace) |
| **Branch** | `feature/workbench-ux`, cut from `feature/fabric-revamp` (D4); rebased onto `main` once PR #16 merges |

---

## 1. The asks

| ID | The ask |
|---|---|
| U1 | **Separate pages per stage.** Clicking a stage, or *Next*, opens a page about that stage, not the same page scrolled |
| U2 | **No long scrolling.** What a stage established and what to do next are visible without scrolling |
| U3 | **Distinguishable stages.** Each stage looks and reads differently: its own title, status, result and boxes; the current stage is obvious |
| U4 | **Easy to follow.** Always clear where you are (stage n of 10), what is done, what waits on whom, and what comes next |
| U5 | **Outcomes and what happened, shown well.** Each stage leads with its result: what happened, when, who or which system, which documents, and what it means for the decision. The end of the journey shows predicted against actual |
| U6 | **Superb components.** Cards, status tags, timelines, comparison and recap built from the revamp's component kit, consistent across all ten stages |
| U7 | **Keep everything that works**: every agent feature, every value, deep links, the Full analysis for reviewers |

## 2. Orientation (code by name; line numbers drift)

| Area | Where it lives today |
|---|---|
| The ten stages | `AF_STAGES` (title, trigger, what the agent does, what a person does, systems), `JSTEPS_AF` (labels and one-line descriptions), `afRun(c)` (state of each stage for a case), `RUN_ST` (state names) |
| Stage navigation | `AF_JG` (stage → URL), `jgAt` (which stage a URL means), `jgStrip` (the journey bar `#jgNav`), `jgGuide` (the bottom bar `#jgGuide` with *Agent suggests* and `#jgContinue`), `JG_TGT` (which element each stage highlights with `.jghl`), `afterRender` (scrolls to the highlight) |
| Stages 1–5 page | `assetPage` → `assetHead`, `skuStrip`, `assetTabBody`: zone `#aszKnown` (*Retrieved from enterprise systems*) with `#afLease` (lease end, return and transit), diagnostic condition, certified period, inspection findings, `#asCostCard`, lifecycle timeline, return history, fleet context, product specs; zone `#aszPred` |
| Stages 6–10 page | `caseView` (Treatment Intelligence): `#afPacket` (decision packet), `TI_STEPS` sections `#step-1`…`#step-5` (asset and status; possible outcomes `#tiAllPaths`, `#tiRecPath`; why `#tiA`; what-if `#tiImpact`, `#tiCmp`; approval and handoff `#tiDecision`, `#tiInstr`, `#tiHandoff` with `#tiHo1`…`#tiHo6`), `#tiReconcile` |
| Data per stage | `afLease(c)` (stages 1–3), `c.received`, `c.location`, inspection fields (`c.grade`, `c.condition`, `c.assessment`, `c.blocked`), `c.routes`, `c.recommendation`, `c.packet`, `c.approval`, `c.exec` (steps, acknowledgements, `exClock`), `c.outcome`, reconcile lines (`exTrace`) |
| Agent features | `afAssist` (✦ Ask about), `afNextStep` (*Agent suggests*), `AF_CARDS.packet`, the approval card (`afOpenApproval`), the run board link, evidence pack (`afEvidencePack`) |

## 3. Today, measured (27 Oct 2026, Planner · Customer A, RT-1048, 1440 × 900)

Measured with the harness suite `dwbase.js` (section 10), which visits every stage link the bottom bar uses.

| Stage | Link the bar opens | Page | Page length | Where that stage's content starts |
|---|---|---|---|---|
| 1 Lease ends | `product/asset/RT-1048?zone=known&jstep=1` | Asset intelligence | 3,501 px (3.9 screens) | 914 px: below the first screen |
| 2 Return authorised | `…jstep=2` | the same page | 3,501 px | 914 px: the same box as stage 1 |
| 3 Pickup and transit | `…jstep=3` | the same page | 3,501 px | 914 px: the same box again |
| 4 Received | `…jstep=4` | the same page | 3,501 px | 800 px |
| 5 Inspect and grade | `…jstep=5` | the same page | 3,482 px | 800 px: the same box as stage 4 |
| 6 Decide | `product/RT-1048?step=2&jstep=6` | Treatment Intelligence | 9,700 px (10.8 screens, 30 panels) | 291 px |
| 7 Approve | `…?step=5&jstep=7` | the same page | 9,700 px | 6,161 px: about 7 screens down |
| 8 Execute | `…&at=handoff&jstep=8` | the same page | 9,700 px | 8,657 px |
| 9 Outcome | `…&at=handoff&jstep=9` | the same page | 9,700 px | 8,920 px |
| 10 Reconcile and learn | `…&at=reconcile&jstep=10` | the same page | 9,700 px | 9,393 px |

**What this means**
- Five clicks (stages 1–5) show an identical page; three of them highlight the same box, and it starts below the first screen.
- The other five clicks scroll one 10.8-screen page. Stages 7–10 sit 7–10 screens down, between nine other sections.
- The only cue that the stage changed is a yellow outline (`.jghl`) and the bar's label. There is no stage title, no stage status on the page, and no "what happened" for the stage.
- The Treatment Intelligence page has its own five numbered steps (`TI_STEPS`), so "step 5" means two different things on the same screen.

## 4. What research and comparable products say

Full brief with sources was gathered on 27 Oct 2026; the points that shape this plan:

| Finding | Source | What we do with it |
|---|---|---|
| Wizards suit infrequent, ordered tasks; they frustrate repeat users and steps done in any order. Let people leave and come back with state kept | NN/g, *Wizards* (nngroup.com/articles/wizards) | Not a strict wizard: every stage is reachable at any time; Next and Back are a convenience |
| Long pages of distantly related sections are better split across pages | NN/g, *In-page links* (nngroup.com/articles/in-page-links-content-navigation) | One stage, one page (D1) |
| For long, multi-sitting services, a task list hub with a status per task, each linking to its own page and returning to the hub | GOV.UK *Task list* (design-system.service.gov.uk/components/task-list) | The case Overview (D1) |
| One thing per page, a heading specific to the page with the section as a caption, a working Back | GOV.UK *Question pages* | Stage page header: caption *Decide · Stage 6 of 10*, h1 the stage |
| Summarise earlier answers with a link to change each | GOV.UK *Check answers*; Baymard: collapse finished steps into summaries | *Established so far* recap on every stage page |
| Name the next step on the button; generic Next/Previous gives weak scent | NN/g, *Wizards* | Footer buttons read *Approve →* and *← Inspect and grade* |
| Steppers: label states in words, not colour alone; past steps clickable; more than six steps should be grouped | Carbon *Progress indicator*; Atlassian *Progress tracker*; Baymard | Ten stages grouped into four phases (D5); status tags with words |
| Stage bar on the record with key fields and guidance for the selected stage | Salesforce *Path*; ServiceNow *process flow formatter* | The stage bar plus each stage's key facts |
| Status trackers: latest update first, plain words, dated history, say what happens next during waits, deep-link to the details | NN/g, *Status trackers* (nngroup.com/articles/status-tracker-progress-update) | *What happened* card, *What happens next* when waiting, dated timeline per stage |
| Explain why the system did what it did: local explanation, inputs to output, what-if; show confidence only where it changes decisions | Microsoft HAX Guideline 11; Google PAIR *Explainability + Trust* | Stage 6 *Why* tab and the packet's drivers; P10–P90 shown with what it means |
| On desktop, tabs handle complex related content better than accordions; accordions hide content | NN/g, *Tabs*, *Accordions on desktop* | Stage details in tabs on desktop, accordions on phones |
| Exactly one `aria-current="step"`; on a step change move focus to the new h1 and update the title | MDN `aria-current`; WCAG 3 draft *current step indicated*; Gatsby/Fable Tech Labs routing study | Accessibility rules (6.10) |
| Each meaningful view has its own URL; Back returns to the previous step | web.dev; Smashing Magazine, *Back button UX* | One URL per stage; old links redirect (6.8) |

## 5. Target, at a glance

| | Today | After |
|---|---|---|
| Pages for a case | 2 long pages shared by 10 stages | A case Overview + 10 stage pages + Full analysis |
| Length of a stage | 3.9 or 10.8 screens | The result and the next action fit on the first screen (1440 × 900); details in tabs |
| Cue that the stage changed | A yellow outline | A different page: its own title, status tag, result card, boxes and URL |
| Where you are | A bar label | Stage bar with four phases and ten stages, *Stage 6 of 10*, a status per stage in words |
| What happened | Spread across panels | A *What happened* card first on every stage: result, when, who or which system, documents, and what it means |
| Next | *Stage 7 screen →* (scrolls) | *Approve →* (opens the stage page; focus on its title) |
| Old links | — | Every old link opens the matching stage page |

## 6. Design

### 6.1 Information architecture and URLs (D1, D2)

| URL | Page |
|---|---|
| `#/product/RT-1048` | **Case overview** (the hub): stage bar, a card per stage with status and one-line result, the decision and outcome at a glance |
| `#/product/RT-1048/stage/1` … `/stage/10` | **Stage pages** |
| `#/product/RT-1048/stage/6?tab=why` | A stage page with a details tab open (tabs: see each stage) |
| `#/product/RT-1048/full` | **Full analysis**: today's Treatment Intelligence page, unchanged, for reviewers and print (D2) |
| `#/product/asset/RT-1048` | **Asset intelligence** stays the asset record (lifecycle, condition, economics, data), no longer used as a stage page |

**Opening a case** (from Returned assets, search, Needs you, the command bar) goes to the stage that is current for the signed-in role (D11), with the Overview one click away in the breadcrumb.

### 6.2 The stage bar (`#jgNav`, D5)

- **Four phases, ten stages:** *Arrive* (1 Lease ends, 2 Return authorised, 3 Pickup and transit, 4 Received, 5 Inspect and grade) · *Decide* (6) · *Approve* (7) · *Execute and learn* (8 Execute, 9 Outcome, 10 Reconcile and learn). Phase labels above, numbered stage chips below.
- **States in words and shape, not colour alone:** ✓ *Done*, ● *Current*, ⏳ *Waiting on Approver* / *Waiting on WMS*, ! *Blocked* (a gate or missing evidence), ○ *Not reached*. Tooltip and `aria-label` carry the full sentence (*Stage 7, Approve: waiting on Approver since 6 Oct 14:20*).
- **The stage you are viewing** is marked with `aria-current="step"`, a yellow underline and a raised chip; the stage the case is actually at carries the *Current* state, so viewing stage 3 while the case is at stage 6 is never confusing.
- **Sticky** under the top bar on case pages; it replaces the journey strip there, so there is one bar, not two (D16).
- **Every chip is a link** to its stage page (past and future, D7).
- **Phone:** the phases collapse to *Stage 6 of 10 · Decide* with a chevron that opens the full list as a sheet.

### 6.3 The stage page template

Every stage page uses the same frame so it is easy to learn, and different content so each stage is easy to tell apart.

| Part | What it shows | Notes |
|---|---|---|
| **A. Header** | Breadcrumb *Returned assets › RT-1048 · Voltara V4 motor › Stage 6*. Caption *Decide · Stage 6 of 10*. h1 the stage name. Status tag. One line: *Done 6 Oct 09:14 · by IBM Maximo* or *Waiting on you since 6 Oct*. System logos for the stage. ✦ *Ask about this stage* | Phase hue on the caption only; yellow stays the action colour |
| **B. What happened** | A large result card: the stage's outcome in one sentence, then 2–5 key facts as labelled values (Salesforce Path key fields), document references (WO-47349, TR-47362) with copy buttons, and a provenance chip per fact (*Retrieved · IBM Maximo · 4 min ago*) | Newest first (NN/g status trackers). For a stage not reached: *What will happen* with trigger, who, systems and typical time (from `AF_STAGES`) |
| **C. What it means** | One or two lines connecting the stage to the decision: *Grade B and a 24-month certified life make Redeploy eligible; Sell as-is is not needed* | Built from existing gate results and packet drivers, never invented |
| **D. What you do now** or **What happens next** | If the stage is the role's to act on: the one primary action as a large button with its consequence (*Submit RT-1048 for review: the Approver gets it in their inbox*). Otherwise who it waits on, since when, the time limit and *Notify the owner* | One primary action per page (GOV.UK *one thing per page*) |
| **E. Details** | Tabs with the supporting panels moved from today's pages (per stage below). Remembered per case in the URL `?tab=` | Accordions on phones |
| **F. Established so far** | A collapsed summary list of earlier stages: one line each with result and a *View* link (check-answers pattern) | Hidden on stages 1 and the Overview |
| **G. Footer (`#jgGuide`)** | Sticky: *← 5 Inspect and grade* · *Stage 6 of 10* · *Overview* · *Agent suggests: Submit RT-1048 for review* · *7 Approve →* (`#jgContinue`) | Buttons name the stage (NN/g). Keyboard: Alt+← and Alt+→ |

**Page budget (U2):** at 1440 × 900, parts A–D fit on the first screen for every stage; E opens on demand. The test in section 10 measures it.

### 6.4 The ten stage pages

Content moves; nothing is invented. *Source* names the function or field each value comes from.

| # | Stage | What happened (B) | What it means (C) | What you do now / next (D) | Details tabs (E) | Kept ids |
|---|---|---|---|---|---|---|
| 1 | **Lease ends** | Contract and end date, lessee, customer intent (return or renew), lease terms, how the case opened (`afLease`, `AF_STAGES[0]`) | Return expected; demand window opens | Nothing for the Planner: *Opened by the agent from Lease management* | Contract · Customer · Systems | `#afLease` |
| 2 | **Return authorised** | RMA number, fees, replacement order, book value, acquisition date (`afLease`) | Book value sets the baseline the decision must beat | Nothing required | Authorisation · Finance | — |
| 3 | **Pickup and transit** | Pickup date, carrier, ETA against arrival, freight cost from the lane rate card, route legs (`afLease`, rate card) | Freight already spent; arrival starts holding cost | Nothing required | Route · Cost trace | — |
| 4 | **Received** | Receipt time, warehouse and bin, holding cost per day so far, evidence checklist: which evidence arrived and which is missing (`c.received`, `c.location`, evidence readiness) | Missing evidence blocks some routes, named | If evidence is missing: *Request evidence* (Planner) or *Confirm receipt* (Warehouse Manager) | Evidence checklist · Location · Holding cost | `#aszKnown` (container) |
| 5 | **Inspect and grade** | Grade, faults found, repair estimate, tests required and done, certified period, photos (inspection, diagnostic condition, certified period panels) | Which gates the grade passes; which routes it opens or closes | Engineer: *Record the result*; Planner: wait or *Request a re-test* | Findings · Diagnostic condition · Certified period · Photos | — |
| 6 | **Decide** | The decision packet as the hero: recommended route and net, P10–P90 with confidence in words, gates passed, three alternatives with their nets, what was not eligible and why (`AF_CARDS.packet`) | One sentence: why this route beats the next one (*Redeploy beats Sell + buy by $4,800 because it replaces PO-49048*) | Planner: *Submit for review*; others: *Waiting on Planner* | Compare outcomes · Why this outcome · Evidence · What-if and edge cases · How it was predicted · Demand | `#afPacket`, `#step-2`, `#step-3`, `#step-4`, `#tiAllPaths`, `#tiRecPath`, `#tiA`, `#tiImpact`, `#tiCmp` |
| 7 | **Approve** | Submitted by, when, recommended route and net, the drafted rationale, the limit check, the pre-approval check result (`afOpenApproval` content) | What approval commits (stock, spend, the order line) | Approver: *Approve*, *Edit route*, *Decline* (the existing approval card); Planner: *Waiting on Approver since …*, *Notify* | Rationale · Checks · History | `#step-5`, `#tiDecision` |
| 8 | **Execute** | The instruction plan as a vertical timeline: each step's system (logo), document, owner, time limit and acknowledgement; route and timing (legs, ETD, ETA, slack); escalations (`c.exec`, `exClock`, handoff panels) | Which step is running and when the unit arrives | *Handles exceptions only*: escalations and *Notify the owner* | Plan · Route and timing · Messages and acknowledgements · Raw instruction | `#tiHandoff`, `#tiHo1`…`#tiHo6`, `#tiInstr` |
| 9 | **Outcome** | *Delivered to Chennai Foundry (Site 3) for Customer A against SO-48102 line 10*, when, by which carrier; actual value and costs next to predicted (`c.outcome`, delivery event) | Whether the decision delivered what it promised | Finance: *Confirm the outcome*; others: *Waiting on Finance* | Delivery · Actual costs · Documents | `#tiHo4` |
| 10 | **Reconcile and learn** | Predicted against actual, line by line, with the variance and its reason; the learning record and model version; open demand carried forward (`exTrace`, reconcile panel) | What the next decision of this kind will do differently | *Review variances*; *Open in Analytics* | Lines · Learning record · Carried forward | `#tiReconcile` |

### 6.5 The case Overview (the hub)

- **Header:** asset photo and model, RT-1048, customer, location, and the decision at a glance (*Redeploy · $9,600 · Approved 6 Oct*), or the outcome when there is one (*$9,230 actual · −$370 against prediction*).
- **Stage bar** (6.2).
- **A card per stage**, grouped by phase: number, title, status tag, one-line result (*Grade B · 24-month certified life*), when, who or which system, and *Open*. Waiting cards show who and since when; blocked cards show why and the action.
- **Right column:** *Needs you* for this case, *Agent suggests*, ✦ Ask about RT-1048, links to Asset intelligence, Full analysis and the evidence pack.
- Follows the GOV.UK task-list pattern: every row is one link and returns here.

### 6.6 Full analysis (D2)

Today's Treatment Intelligence page moves to `#/product/RT-1048/full` unchanged, titled *Full analysis*, with a banner *Everything on one page, for review and print · Back to stage 6*. Its own numbered sections lose their numbers (*Asset and status*, *Possible outcomes* …) so "step" means only the ten stages (D12).

### 6.7 Roles (D8)

The same pages for every role; only part D changes, from what each role may do today (`ROLE_POLICY`, `can()`):

| Role | Lands on | Acts on |
|---|---|---|
| Planner | The current stage | 4 *Request evidence*, 6 *Submit for review* |
| Approver | Stage 7 when waiting on them, else the current stage | 7 *Approve · Edit · Decline* |
| Engineer | Stage 5 | 5 *Record the result* |
| Finance | Stage 9 or 10 | 9 *Confirm the outcome* |
| Warehouse Manager | Stage 4 or 8 | 4 *Confirm receipt*; 8 WMS steps |
| Executive | The Overview | Read-only, *Notify the owner* |
| Admin | The current stage | Everything |

### 6.8 Old links keep working (U7)

| Old link | Opens |
|---|---|
| `product/asset/ID?zone=known&jstep=n` (n 1–5) | `product/ID/stage/n` |
| `product/ID?step=1` | the Overview |
| `product/ID?step=2` / `step=3` / `step=4` | stage 6, tab *Compare outcomes* / *Why* / *What-if* |
| `product/ID?step=5` | stage 7 |
| `product/ID?…at=handoff` (`jstep=8` / `9`) | stage 8 / stage 9 |
| `product/ID?…at=reconcile` | stage 10 |
| `product/ID?explain` | stage 6, tab *Why* |
| `product/received?focus=ID` | unchanged (the queue, row focused) |

The redirect replaces the history entry, so Back works.

### 6.9 Components (U6), built on the revamp kit

| Component | Built from | Used on |
|---|---|---|
| **Stage bar** | new; phase groups, state tags, `aria-current` | Overview, every stage |
| **Stage header** | `frHead` + status tag (`frSt`) + system logos (`vlogo`) | Every stage |
| **What happened card** | new: result sentence, key facts grid, document chips with copy, provenance chips | Every stage |
| **Meaning line** | new: one sentence with an icon tile (`frIt`) | Every stage |
| **Action panel** | new: one primary button with its consequence, or *waiting on* with time limit and *Notify* | Every stage |
| **Details tabs** | `frSeg` style tabs, keyboard arrows, `?tab=` | Stages 1–10 |
| **Recap list** | new: summary list with *View* links | Stages 2–10 |
| **Stage footer** | replaces `jgGuide`; sticky; named Back and Next | Every stage |
| **Stage card** | `frKpi` style card with state | Overview |
| **Timeline** | `frTl` | Stages 8 and 9, Overview |
| **Compare table** | today's comparison, restyled with the kit | Stage 6 |
| **Predicted vs actual** | new: two columns with the variance bar | Stages 9 and 10, Overview |

### 6.10 Accessibility and behaviour

- Exactly one `aria-current="step"` in the stage bar; each chip's label states the stage, its state and since when.
- On a stage change: focus moves to the stage h1, the document title becomes *Stage 6 · Decide · RT-1048*, and a polite live region announces it.
- Scroll resets to the top on a new stage; Back restores the previous stage and its scroll.
- Status is never colour alone: every state has a word and a shape.
- Contrast stays WCAG AA in light and charcoal dark.
- `prefers-reduced-motion` turns off the stage transition.

### 6.11 Phone (390 px)

The stage bar collapses to *Stage 6 of 10 · Decide* with a sheet; parts A–D stack; details become accordions; the footer keeps *← Back* and *Next →* with the stage names truncated.

### 6.12 Agent features kept

| Feature | Where after |
|---|---|
| ✦ Ask about RT-1048 | Header of every stage (asks about the stage) and the Overview |
| *Agent suggests* (`afNextStep`) | Stage footer and Overview right column |
| Decision packet | Stage 6 hero |
| Approval card with the drafted rationale | Stage 7 |
| Prepared-by-agent badges, Show trace, Undo | On the facts and actions they belong to |
| Run board | *See it run* link on the Overview (Process orchestration) |
| Evidence pack | Overview and stage 6 |
| Journey strip | Replaced by the stage bar on case pages; unchanged elsewhere |

### What stays the same
Every route, value, gate, approval rule, role rule, agent intent and guard rail. RT-1048's $9,600 and $9,230. The execution detail and cost trace. Asset intelligence as the asset record. The demo build (`?agent=0`) and the previous look (`?fabric=0`).

## 7. Data rules

- No new data and no new `rnd()` calls: every value on a stage page comes from the fields in section 2.
- A stage's state comes from `afRun(c)` only, so the stage bar, the Overview, the run board and Needs you agree.
- *What it means* lines are built from gate results and packet drivers; where there is nothing to say, the line is left out.

## 8. Phases (each ends with tests, screenshots and a short report)

| # | Phase |
|---|---|
| 0 | Baseline: all suites green; `dwbase.js` records today's lengths (section 3) |
| 1 | Routes and redirects (6.1, 6.8); the stage frame: stage bar, header, What happened, action panel, recap, footer, focus and titles; behind `FEAT.stages` (on with the revamp, `?stages=0` restores today's flow) |
| 2 | Stages 1–5 pages (content from Asset intelligence and `afLease`) |
| 3 | Stage 6 Decide (packet hero, tabs from Treatment Intelligence) |
| 4 | Stage 7 Approve (approval card in place) |
| 5 | Stages 8–10 (plan timeline, outcome, predicted vs actual, reconcile) |
| 6 | Case Overview; Full analysis route; opening a case lands on the role's stage |
| 7 | Roles (6.7), agent features (6.12), phone (6.11), accessibility (6.10) |
| 8 | Docs (README, CHANGES Update 18), screenshots of every stage in light, dark and phone, demo video selectors check |

## 9. Rules

- Plain English; *stage* means one of the ten, nowhere else.
- One primary action per page; yellow only for actions, current markers and focus.
- Roles, not names. `$9,600` and `−$370` money format.
- No *simulated* or *demo* wording in the interface.
- Circularity recommends and sends approved instructions; the enterprise systems do the work.

## 10. Tests

### Baseline (run 27 Oct 2026)

| Suite | Result |
|---|---|
| 16 existing suites | 945 pass |
| `fabric.js`, `smoke.js`, `video.js`, `menus.js` | 172, 85, 17, 11 pass |
| `dwbase.js` (new, measurement) | the table in section 3 |

### New suite `stages.js`

- **One page per stage:** stages 1–10 each render a different page: unique h1, unique *What happened* text, unique URL; no two stages share their primary content.
- **No long scroll:** at 1440 × 900, parts A–D of every stage end within the first screen; the full page of every stage is at most 2.5 screens with details closed.
- **Next and Back:** Next opens exactly the next stage, Back the previous; the buttons name the stages; Alt+→ and Alt+← work.
- **Stage bar:** ten chips in four phases; exactly one `aria-current="step"`; each state has a word; states match `afRun(c)` for cases the seed holds at stages 5, 6, 7 and 8 (41, 8, 41 and 38 cases on 27 Oct), and for RT-1048 taken through stages 8–10 with the existing journey actions (`afJump`, `runNext`, as `live.js` does).
- **Focus and title:** after a stage change focus is on the h1 and the title reads *Stage n · name · RT-…*.
- **What happened:** every reached stage shows a result sentence, at least two facts, a when and a who or system; every fact has provenance; not-reached stages show *What will happen*.
- **Actions by role:** each role sees its action only on its stages (table 6.7) and *Waiting on …* elsewhere; read-only roles never see action buttons.
- **Old links:** every link in 6.8 opens the right stage and tab, and Back returns to the previous page.
- **Content inventory:** every panel listed in section 2 appears on exactly one stage page or the Overview (none lost), and on Full analysis.
- **Values agree:** RT-1048 shows $9,600 on stage 6, the Overview and Full analysis; once taken through stages 8–10 it shows the $9,230 actual on stages 9 and 10 and the Overview. (RT-1048 is seeded at stage 7, with no outcome yet.)
- **Agent features:** ✦ on every stage, *Agent suggests* in the footer, packet on stage 6, approval card on stage 7, evidence pack, run board link.
- **Overview:** ten cards with states and results matching the stage pages.
- **Phone (screenshots):** stage bar sheet, stacked parts, footer.
- **No *undefined* or *NaN*** on any stage for any role, in both themes; no console errors.

### Existing suites

All green. Expectations that move with the new pages are updated, listed in CHANGES and never weakened. Known ones: `af2`, `af5`, `exec`, `run`, `afovd` and `frx` use `#jgNav`, `#jgGuide`, `#jgContinue`, `#aszKnown`, `#afLease`, `#step-5`, `#tiReconcile` and `jstep` links; the ids are kept on the stage pages (table 6.4) and the links redirect (6.8).

## 11. Decisions

| # | Decision | State |
|---|---|---|
| D1 | **One page per stage plus a case Overview** (hub), not phase pages or one page with an accordion | Decided (product owner, 27 Oct) |
| D2 | **Keep today's long page as *Full analysis*** at `/full`; its content also moves into the stage pages; old links redirect | Decided |
| D3 | **Stages 1–5 get their own short *what happened* pages**, not one Arrival page | Decided |
| D4 | **Build on `feature/workbench-ux` cut from `feature/fabric-revamp`**, rebased onto `main` after PR #16 merges | Decided |
| D5 | Ten stages in **four phases** (Arrive, Decide, Approve, Execute and learn) on the stage bar | Decided (product owner, 27 Oct) |
| D6 | Footer buttons **name the stage** (*7 Approve →*), not *Next* | Assumed |
| D7 | **Every stage is reachable**, including ones not reached yet (they show *What will happen*); nothing is blocked by navigation. A stage not reached yet shows only what will happen, who does it and what it waits on, with no invented results | Decided (product owner, 27 Oct) |
| D8 | **Same pages for every role**; only *What you do now* changes (6.7) | Assumed |
| D9 | **Details in tabs on desktop**, accordions on phones | Assumed |
| D10 | ***Established so far* recap** on every stage from 2 | Assumed |
| D11 | **Opening a case lands on the role's current stage**, not the Overview; the Overview is one click away on the stage bar | Decided (product owner, 27 Oct) |
| D12 | Treatment Intelligence's own numbered steps lose their numbers; *step* means only the ten stages | Assumed |
| D13 | **Page budget:** parts A–D on the first screen at 1440 × 900; any stage at most 2.5 screens with details closed. The rule holds for stage 6 too: extra detail goes in tabs below and may scroll; `stages.js` enforces it | Decided (product owner, 27 Oct) |
| D14 | URL scheme `#/product/ID/stage/n?tab=` | Assumed |
| D15 | Focus to h1, title update and live announcement on every stage change | Assumed |
| D16 | The stage bar **replaces** the journey strip on case pages | Assumed |
| D17 | ✦ *Ask about this stage* in every stage header | Assumed |
| D18 | `FEAT.stages` on with the revamp; `?stages=0` restores today's flow | Assumed |
| D19 | **The Approver sees all ten stages** and lands on stage 7; stages 1–5 are read-only background for them | Decided (product owner, 27 Oct) |
| D20 | The main card on every stage is titled ***What happened***, followed by *What it means* and *What you do now* | Decided (product owner, 27 Oct) |

## 12. Product owner questions

All six questions were answered on 27 Oct and are recorded as D5, D7, D11, D13, D19 and D20 in section 11. The rest (D6, D8–D10, D12, D14–D18) are build details, assumed as written.

## 13. Definition of done

- [x] U1–U7 visible and working (section 14)
- [x] `stages.js` green; all existing suites green; `dwbase.js` re-run shows every stage under the page budget
- [x] Every agent feature in 6.12 present
- [x] Screenshots of the Overview and all ten stages in light, dark and phone
- [x] README and CHANGES updated
- [ ] Product owner confirms D5–D18

## 14. Prompt for a fresh session

> Read `docs/PLAN_DECISION_WORKBENCH_STAGE_PAGES.md`. Work on branch `feature/workbench-ux`. Build the phases in order behind `FEAT.stages`. Keep every agent feature, element id and value; move content, do not invent it; add no `rnd()` calls; run all suites and `dwbase.js` before and after each phase.

## 15. Does the plan match the asks?

| Ask | Section | Match |
|---|---|---|
| U1 Separate pages per stage | 6.1, 6.4, D1, D3 | Yes |
| U2 No long scrolling | 6.3 page budget, D13, tests | Yes; measured before and after |
| U3 Distinguishable stages | 6.2, 6.3, 6.4 | Yes: own title, status, result, URL |
| U4 Easy to follow | 6.2, 6.3 (F, G), 6.5 | Yes: stage bar, recap, named Next, Overview |
| U5 Outcomes and what happened | 6.3 (B, C), 6.4 stages 9–10, 6.5 | Yes |
| U6 Superb components | 6.9 | Yes, on the revamp kit |
| U7 Keep what works | 6.6, 6.8, 6.12 | Yes: Full analysis, redirects, agent features |

## 16. Build report (27 Oct 2026)

Built on `feature/workbench-ux` in one pass, behind `FEAT.stages` (on with the revamp; `?stages=0` restores the previous flow, remembered on this device as `circ-stages`). All code is between `/*ST-START*/` and `/*ST-END*/` (after FR-END) and `/*ST-CSS-START*/` and `/*ST-CSS-END*/` (after FR-CSS-END), scoped to `html.st`. It wraps `parse`, `route`, `renderProduct`, `jgStrip`, `jgGuide`, `jgAt` and `jgCase`; no existing function body changed. No new data and no `rnd()` calls: every value comes from `afLease`, `afStageStates`/`afRun`, the case record, `exPlan`, `exMove`, `instrPayload` and the outcome.

| Phase | Result |
|---|---|
| 0 Baseline | 21 suites green (rbac 208, gf 110, demo 91, iter2 51, iter3 61, af1a 42, af1b 10, af2 92, af3a 39, af3b 7, af4 61, af5 50, live 8, run 75, exec 46, smoke 85, fabric 172, video 17, menus 11, ovd 25, afovd 15); `dwbase.js` matched section 3 |
| 1 Routes and frame | `#/product/ID/stage/n?tab=`, `/overview`, `/full`; every link in 6.8 redirects with `history.replaceState`; stage bar, header, What happened, What it means, What you do now, tabs, recap, footer; focus, title and live region |
| 2 Stages 1–5 | From `afLease`, the evidence list, the inspection, diagnostic and certified-period panels; `#afLease` on stage 1, `#aszKnown` and `#asCostCard` on stage 4 |
| 3 Stage 6 | Packet, *Compare outcomes*, *Why this outcome*, *Evidence*, *What-if and edge cases*, *How it was predicted*, *Demand*; `#afPacket`, `#step-2`–`#step-4`, `#tiAllPaths`, `#tiRecPath`, `#tiA`, `#tiImpact`, `#tiCmp` |
| 4 Stage 7 | The existing approval card (Approve, Edit route, Decline) with the agent's drafted rationale; *Rationale*, *Checks* (`#step-5`, `#tiDecision`), *History* |
| 5 Stages 8–10 | Plan as a vertical timeline, route and timing, acknowledgements (`#tiHandoff`, `#tiHo1`–`#tiHo6`), instruction (`#tiInstr`); delivery summary, actual costs and documents; predicted against actual, lines (`#tiReconcile`), learning record, carried forward |
| 6 Overview and Full analysis | Ten stage cards by phase; Needs you, Agent suggests, predicted against actual, links; Full analysis open, banner, section numbers hidden; landing per role |
| 7 Roles, agent, phone, accessibility | Table 6.7; ✦ on every stage, Agent suggests in every footer, packet, approval card, evidence pack, run board link; sheet and accordions at 390 px; Alt+← and Alt+→, Back restores scroll |
| 8 Docs | README row and 6.5 note, CHANGES Update 18, 47 screenshots `docs/screenshots/stage-*.webp` |

**Tests.** New suite `stages.js`, 48 checks, all pass at a 1440 × 900 viewport: one page per stage (unique title, result and URL), A–D above the footer and at most 2.5 screens, Next and Back, Alt+← and Alt+→, focus and title, the stage bar (states match `afRun` for 4 cases at each of stages 5, 6, 7 and 8 of the seed's 41, 8, 41 and 38), What happened on every stage, every old link and tab, Back after a redirect, the content inventory (each panel on exactly one stage page, all on Full analysis), $9,600 on stage 6, the Overview and Full analysis, $9,230 and −$370 on stages 9 and 10 and the Overview after RT-1048 is taken through stages 8–10 with the journey actions, agent features, Overview, actions by role, and no *undefined* or *NaN* for seven roles in both themes. `stoff.js` (4 checks) proves `?stages=0` restores the previous flow. All 21 existing suites stay green; the expectations that moved are listed in CHANGES Update 18 (af1b, af2, exec).

**Measured after** (`dwafter.js`, the same links the bar used to open): every stage is its own page, 915–1,084 px with details closed (1.0–1.2 screens, before 3.9 or 10.8), and the result and action end at 625–821 px against a footer at 845 px.

**Where the build differs from the plan.**
- `#/product/ID` opens the role's stage (D11) and the Overview is `#/product/ID/overview` (6.1 had the Overview at `#/product/ID`), so every existing link that opens a case lands on a stage without changing it.
- `?step=5` opens stage 7, or stage 8 once the case is executing (the escalation alerts use this link).
- `#tiHo4` stays on stage 8 inside the handoff panel; stage 9 has its own delivery summary and document list, so no panel is on two stage pages.
- Stage 4 has no *Confirm receipt* action for the Warehouse Manager: none exists, and nothing is invented. It offers *Request evidence* when evidence is missing.
- *Notify the owner* opens Ask with an escalation drafted to whoever the stage waits on (the existing `escalation.send` action).

**Still open:** the product owner confirms the assumed decisions (D6, D8–D10, D12, D14–D18 and the differences above). The demo video was not re-recorded; `video.js` (its selectors) passes.
