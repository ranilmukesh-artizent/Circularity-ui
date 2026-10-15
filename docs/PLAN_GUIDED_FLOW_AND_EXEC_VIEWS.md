# Plan: guided decision flow, senior and operational views, enterprise handoffs

**Purpose of this file:** a self-contained brief for a fresh session. It does not assume any earlier conversation. Read it top to bottom, then start at **Phase 0**.

**Status:** draft, not started (2026-10-15). Checked against published guidance on 2026-10-15 (section 13); the confirmed findings are folded into section 4 and marked "research note 13.x". Section 14 checks each requirement against the plan. The source is the Product Owner review of the role-based demo (meeting notes and the written requirements, summarised in section 1). Open decisions are in **section 3**. Each has a recommended default. Until the Product Owner answers, build the default and label it **(assumed)**.

**Builds on:** `docs/PLAN_RBAC_ADAPTIVE_UI.md` (role-adaptive UI, branch `feature/rbac-adaptive-ui`, not merged into `main` at the time of writing). This plan reuses its access policy, sign-in, requests and Command Center layouts. **Branch from `feature/rbac-adaptive-ui`** (or from `main` once that PR is merged).

> **Compliance note.** This work touches access control (new roles, site scoping, identity provider settings) and product positioning ("decision intelligence, not an execution system"). Per Kinective policy, the role matrix, any wording about access, identity, security or regulation, and the positioning statements should be reviewed by Kinective's Legal team before they are relied on or used with clients.

---

## 1. The feedback to solve

The Product Owner liked the role-based demo ("it's come out very well… we are there almost"). The ask is to **structure the flow** so a viewer can see where a user starts, how they navigate, and what outcome they get. The written requirements, in short:

| # | Requirement | Today | Wanted |
|---|---|---|---|
| R1 | **Senior management and operational views of the Command Center** | Admin mixes executive KPIs with operational queues; the value KPIs (net recovery $2.43M, uplift +$652k, yield 97%, avoided spend $1.74M, CO₂e 263 t) exist only in the Finance view | A **senior view** (CEO, COO, Production Head, VP): value KPIs on top, portfolio health, exceptions with drill-down and "notify the owner", no operational queues by default. An **operational view** (Planner, Engineer, Warehouse Manager): approvals inbox, **Actions on me**, items handed to enterprise systems that are awaiting outcomes, all scoped to the user's warehouse or site |
| R2 | **Expected returns come from the Contract / Lease Management application** | Product → Expected returns reads like inventory or inspection signals | Contract ID, Customer, Lease period, Contract expiry, Source application = Contract Management. The page must say returns are derived from contract and lease expiry |
| R3 | **Make the what-if result prominent** | Panel 4 shows the result in a small "Scenario impact (preview)" text callout | A large, high-contrast card showing **Base net**, **Simulated net**, **Δ $** and **Δ %**, live while dragging, with clear up and down indicators. Sliders: avoided purchase price, preparation/parts/fees, service exposure, resale price |
| R4 | **Tie-breaker logic and multi-option what-if** | What-if focuses on the top pathway. The ranking is by net value only, so near-ties are not explained (RT-1048: Redeploy $9,600 against Sell + buy $4,800 is not close) | When nets are close, rank by secondary factors: **cycle time, remaining useful life (RUL), risk/confidence, demand certainty, carbon**, and explain why. Compare and simulate the top pathways **side by side** (base and simulated net, with the secondary factors), and mark the recommendation with its rationale |
| R5 | **RUL and post-intervention lease value together** | RUL is buried in gate notes (`engLife`) or a small table column | One summary card: **A. Diagnostic condition** (from EAM/diagnostics, e.g. battery health 60%, winding Grade B). **B. RUL after intervention**, keeping *estimated RUL* separate from the *certified operating period*. **C. Commercial value** for that life (route, net, lease horizon, matched demand such as an order at Site 3). Flag any commercial horizon longer than the certified period |
| R6 | **Treatment page as a guided top-to-bottom flow** | Five side-by-side panels plus "Detailed analysis"; the reader jumps around | Five steps in order: **1** asset and current status (with reason and what is outstanding), **2** recommended outcome summary, **3** why this outcome, **4** what-if and edge cases, **5** next best action: approval and enterprise handoff |
| R7 | **Process Orchestration ("Behind the screen") view** | Demos show results, not how agents and services produce them | A new menu item showing ten stages: Start → Pull data → Data preparation → Evaluate gates → ML predictions → Optimise pool → Recommendation → Present for approval → Hand off to enterprise system → Retrieve actual outcome. For each stage: the agent or component, the source systems, the status (done, active, pending, failed), timestamps, and a link to the live agent call log |
| R8 | **No internal-execution wording; clear enterprise handoffs** | "Executing", "Execution timeline", "Execution readiness", "Executed" suggest Circularity does the work | Position Circularity as **decision intelligence: it calculates, recommends and sends approved instructions**. Handoff model: Redeploy → **ERP Order Management**; Refurbish or repair → **EAM / Diagnostic and Repair**; Return to stock → **WMS putaway** |

**Also from the meeting:**

| # | Point | What it means for the build |
|---|---|---|
| M1 | **Identity from the customer's SSO.** Users, email, roles, hierarchy and approvals come from the customer's identity management (for example Microsoft Entra ID). "Sign in as is OK, but how do I add?" | Keep the simulated sign-in for the demo. Add a **User settings** area (Admin) that shows how users and roles arrive from the identity provider: group-to-role mapping, site assignment, approval hierarchy and "Sync from directory". Simulated, no real directory |
| M2 | **Structure the flow along the user journey diagram** the Product Owner shared | R6 and R7 deliver this. The diagram itself is not in the repo: **ask for it** and save it to `docs/` so the build can be checked against it |
| M3 | **Edge cases** | Covered by R4 (near-ties) and the "What-if: edge cases" step in R6. Seed at least one genuine near-tie case (section 6) |
| M4 | "Increase the count of the rows… with the same button" | **Unclear.** Possibly the "Show 40 more" button on Audit, or row counts on a table. Ask (section 3, D12). Do not build until clarified |
| M5 | Developer sees only integration, workflows and MCP | Already delivered by the RBAC work; no change |

---

## 2. Orientation: where the code is

The app is still **one file, `index.html`**, with no build step. Read `docs/PLAN_RBAC_ADAPTIVE_UI.md` section 2 for the general structure (state `S`, hash routes, `ACT` handlers, `NAV`, marker blocks). Pointers for this plan (line numbers drift, so search by name):

| Area | Where |
|---|---|
| Access policy, roles, accounts | Between `/*RBAC-START*/` and `/*RBAC-END*/`: `ROLE_POLICY`, `PERM_ACTS`, `ACCOUNTS`, `can`, `canPage`, `homeFor`, `allowedTenants`, `myCases` |
| Command Center per role | `CC_LAYOUT` (KPI ids, `inbox`, `outcomes`, `charts`, `row`, `ops`, `health`), `ccOutcomesHTML`, capacity `CC_CAP` and `ccUtil()` |
| Stage labels | `stageChip` (line ~1745: `Approved · sending`, `Executing`), the Command Center lifecycle legend (`['exec','Executing',…]`), `CC_CAP['In execution']` |
| Expected returns | `const EXPECTED=[…]` (ids `ER-31xx`, `signal` text such as "Lease LS-5412 ends 11 Oct") and `expectedTable()` |
| Treatment Intelligence | Between `/*TI-START*/` and `/*TI-END*/`: `caseView`, `tiCtx` (photo, facts, objective sliders), `tiA` (panels 1–3), `tiP3` (recommendation), `tiP4` (what-if), `tiImpact` (the small callout), `tiP5` (execution readiness), `tiM` (cycle days, success %, life, CO₂e per pathway), `tiRows` (fit score) |
| Execution and handoff | `STEP_TPL` (per-route steps and target systems), `stepsFor`, `mkExec` (seeded approvals, refs), `execBlock` ("Execution timeline", "Advance simulation", "Replay instruction") |
| Scenario engine | `S.scen={purchase,cost,service,market,demandOff}`, `scenRoutes`, `scenNet`, `scenActive`, `scenTopText` |
| Asset data | Case seeds around `mkRoute(...)`: `engLife` (e.g. `'36 months'`), `demand:{internal,confirmed,site,lease,parts}`, `grade`, `condition`, `location` (`Warehouse 1`, `Warehouse 2`, `Repair centre`) |
| Agents and tools | `AGENTS` (Evidence Assembler, Opportunity Finder, Gap Requester, Execution Coordinator, Reconciler), the tool catalog, the call log (`mcp/calls`) |
| Analytics wording | Pipeline (`'Executed'`, "Not cancelled or expired"), "Route mix over time: executed decisions per month", outcome cards ("Route executed", "executed …") |

**Seeded approver names.** `mkExec` picks approvers from `['A. Menon','R. Das','S. Iyer','K. Raman']`. These look like personal names, which goes against the project rule of synthetic labels only. Replace them with account labels (for example `Approver`) in Phase 1.

---

## 3. Decisions needed from the Product Owner

Ask these in one message before Phase 1. If there is no answer, build the **recommended default** and mark it **(assumed)** in the UI notes and in section 9 of this file.

| # | Question | Recommended default |
|---|---|---|
| D1 | Is the senior view a **new role** (Executive) or a **view switch** on the Command Center? | **New role `Executive`** (demo account "Executive"), read-only plus Notify. Admin also gets a **Senior / Operational** switch on its Command Center, because Admin is the master role |
| D2 | What may the Executive open beyond the Command Center? | Command Center (senior view), Analytics (all sections, read-only), Product read-only (drill-down cases and Asset intelligence, no actions), Audit read-only, Process Orchestration. No Integration, MCP or Access |
| D3 | Is **Warehouse Manager** a new role? What can it do? | **Yes, new role**, locked to one warehouse (accounts: "Warehouse Manager · Warehouse 1" and "· Warehouse 2"). Sees cases at that location, capacity, inbound expected returns and items awaiting handoff outcomes. Can **request evidence** and **acknowledge** a notification. It does not approve and does not move stock; WMS stays the system of record |
| D4 | Site scoping for Planner and Engineer: a hard lock or a default filter? | A **default filter** set to the account's home site, which the user can widen within their tenant. A **hard lock** only for Warehouse Manager. Planner tenant lock (RBAC) is unchanged |
| D5 | Does "warehouse or site" mean the asset's **current location** (Warehouse 1, Warehouse 2, Repair centre) or the **demand site** (Site 1–8)? | Current location for the operational queues; the demand site is shown as context |
| D6 | In the operational view, what does the **Approvals inbox** mean for a Planner or Engineer? | "My items waiting for approval": status only, with who it waits on. Only Approver and Admin can act (unchanged) |
| D7 | Who is the **responsible person** for Notify? | Fixed by exception type: value at risk (approval delay) → Approver; missing evidence or failed gate → Engineer; warehouse bottleneck → Warehouse Manager of that warehouse; stale feed or integration failure → Developer. The sender can change the recipient. Notifications are simulated: they create an **Actions on me** item, an audit entry and a toast; nothing is sent outside the app |
| D8 | Tie-breaker: what counts as "near-identical", and what is the order of the secondary factors? | Near-tie when the top two nets are within **5% or $250**, whichever is larger. Order: **1 Risk/confidence, 2 Demand certainty, 3 Cycle time, 4 RUL, 5 Carbon**, and each factor decides only if the gap is meaningful (thresholds in 4.4). The business-objective weights still produce the **Fit** score, shown as a second opinion |
| D9 | Multi-option what-if: one set of sliders for all options, or sliders per option? | One shared set of sliders that apply to every option, plus an **"Apply to"** selector (All, or one pathway) so one option can be stressed on its own |
| D10 | RUL: may the commercial horizon ever exceed the certified period? | **No.** The lease or demand horizon is capped at the certified period. If demand needs longer, show "Needs re-certification" and treat the route as **Conditional** (not Restricted) |
| D11 | Who sees **Process Orchestration**? | Every role, read-only (it is a demo and transparency view). Developer and Admin also get "Open live call log" |
| D12 | What did "increase the count of the rows… with the same button" refer to? | Ask. Do not build until clarified |
| D13 | User settings and SSO: which identity provider should the demo show, and may Admin edit the group-to-role mapping? | Show a **generic "Identity provider (for example Microsoft Entra ID)"** card, labelled simulated. Admin can edit the group-to-role mapping, site assignment and approval hierarchy in the demo. Users cannot be created by hand; they come from the directory |
| D14 | Should "Execution Coordinator" (agent) be renamed? | Yes: **"Handoff Coordinator"**, same scopes |
| D15 | Can we have the user journey diagram the Product Owner sent? | Needed to check R6 and R7 against it. Save it as `docs/user-journey.png` (or `.webp`) |
| D16 | Is there a **middle (tactical) audience**, such as regional or portfolio managers or analysts, between the senior and site views? | No new role. **Analytics is the tactical layer**, and the senior view drills into it (4.7) |
| D17 | Should the Approver see the **full instruction** (what goes to ERP, EAM or WMS) **before** approving? | **Yes**: a readable preview plus "View raw payload" in step 5 (4.6) |
| D18 | Should the near-tie threshold and the order of the secondary factors be **configurable** (by Admin, per tenant), or fixed? | Fixed in the demo and shown on screen; a "configurable by Admin" note for production |
| D19 | Does the customer's contract data include past **buyouts, extensions and early terminations**, or only end dates? | Assume history exists and show **Likely outcome** with probabilities (4.2), with a fallback to expiry = return |
| D20 | Production identity: which identity providers at launch (Entra ID, Okta, others)? Is **SCIM provisioning** required (for timely removal of leavers), or is SSO-only acceptable? | Entra ID first, Okta second, SCIM required. The demo shows both and is labelled simulated |

---

## 4. Design

### 4.1 Wording and the handoff model (R8, do first)

**Principle.** Circularity evaluates, calculates, recommends and **sends approved instructions**. Enterprise systems **carry out** the work and **report the outcome**. Never say Circularity "executes", "manages orders", "moves stock" or "repairs".

**Keep internal ids** (`stage:'executing'`, `CC_CAP` keys, test hooks). Change only the **labels** so invariants and tests keep working.

| Where | Today | New |
|---|---|---|
| Stage chip (`stageChip`) | Approved · sending | **Approved · handing off** |
| Stage chip | Executing | **With {system} · awaiting outcome** (short form in tables: **Handed off**) |
| Command Center lifecycle legend | Executing | **Handed off · awaiting outcome** |
| Capacity (`CC_CAP`) label | In execution | **Awaiting outcome from enterprise systems** |
| Treatment page panel 5 | Execution readiness | **Handoff readiness** |
| `execBlock` title | Execution timeline | **Enterprise handoff** |
| `execBlock` note | "Execution systems stay authoritative…" | "Circularity sends the approved instruction. {ERP / EAM / WMS} carries out the work and reports back; those systems stay the record for orders, stock and repairs." |
| Buttons | Advance simulation · Replay instruction | **Simulate system acknowledgement** · **Resend instruction** |
| Returned assets intro | "…execution continues in your systems" | "…once approved, the instruction goes to your enterprise systems, which carry out the work" |
| Outcomes to confirm | "Execution finished; Finance confirms…" | "Enterprise systems reported the outcome; Finance confirms the economic result." |
| Analytics pipeline | Executed · "Not cancelled or expired" | **Carried out by enterprise systems** · "Reported done by ERP, EAM or WMS" |
| Analytics route mix | executed decisions per month | **decisions carried out per month** |
| Outcome cards | Route executed / executed {route} | **Route carried out** / carried out {route} |
| Agent registry | Execution Coordinator | **Handoff Coordinator** (D14) |
| MCP playground step | "write executed within scope" | "write sent within scope" |

**Handoff templates (`STEP_TPL`).** Rewrite each route's steps as instructions to named systems. Each step has a **target application**, an **instruction**, a **status** (Not sent, Sent, Acknowledged, Done, Error) and an **external reference** when acknowledged.

| Route | Handoffs, in order |
|---|---|
| Redeploy | 1 **ERP · Order Management**: redeployment against pending order {order} at {site} · 2 **EAM · Diagnostic and Repair**: refurbishment work order (only if prep is needed) · 3 **WMS**: transfer to {site} · 4 Outcome reported (ERP order fulfilled) |
| Refurbish or repair (re-lease, internal parts) | 1 **EAM · Diagnostic and Repair**: work order · 2 **WMS**: putaway after refurbishment · 3 **CRM / Lease**: contract (re-lease only) · 4 Outcome reported |
| Return to stock | 1 **WMS**: inventory putaway · 2 Outcome reported |
| Resale, external parts | 1 **WMS**: reserve · 2 **CRM**: sale task · 3 **WMS**: ship · 4 Outcome reported (ERP receipts) |
| Material, exit | 1 **WMS**: release to partner · 2 **Recycler / Exit partner**: collection · 3 Certificate returned |

Show the three-row handoff table from R8 as a small legend under "Enterprise handoff", and on the Process Orchestration page.

### 4.2 Expected returns from Contract Management (R2)

- **Source:** the existing **Lease management** source (Oracle Lease and Finance Management) in the Source map, presented as the **Contract / Lease Management application**. Add a tooltip saying that is its role. Do not add a new source; that keeps the integration counts (19 sources, 31 workflows) unchanged.
- **Data:** extend `EXPECTED` with `contract` (reuse `LS-5412`, `LS-5440`…; add synthetic ids where the signal is not a lease, such as `CT-7031` for a project contract), `lease:{start,end,months}`, `expiry`, `customer`, `source:'Contract Management'`. The "signal" text becomes a derived "Return reason" (Lease ends, Contract ends, Refresh programme).
- **Columns:** Contract ID · Customer · Asset (product, class) · Lease period (start–end, months) · Contract expiry · Expected return · Site · Planning range · Source application · Status (Conditional).
- **Header note:** "Expected returns are derived from contract and lease expiry in the Contract Management application ({vendor}). They are planning signals; nothing is committed until the asset is received and inspected."
- **Likely outcome, not just the expiry date (research note 13.6).** A lease end does not always mean a return: the lessee may buy the asset, extend, or end early. Add a **Likely outcome** column (Return, Buyout, Extension, Early termination), with its probability and a **return window** (for example "10–24 Oct") rather than one date. The **planning range** is weighted by the probability of return. Label these "modelled from contract terms and past outcomes". If the customer's contract history does not include buyouts and extensions, fall back to expiry = return and say so (question D19).
- **Drawer** (`expDetail`): contract summary, lease timeline bar (start → expiry → expected return), source and freshness, and "Open source" (only for roles that can see the Source map).
- **Tenant and site scoping** as for Returned assets.

### 4.3 What-if result card (R3)

Replace the `#tiImpact` callout with a **result card** at the top of the what-if step:

- Four large figures in one row (two by two on phone): **Base net** · **Simulated net** · **Δ $** · **Δ %**. Next to them, a list of the assumptions changed from base ("Resale price −20%, Parts +30%"), so the reader sees why the value moved (research note 13.2). Δ uses `--ok` with ▲ for up, `--bad` with ▼ for down, and `--muted` with "No change". Never colour alone: always include the arrow and sign.
- Under them, one plain sentence: "Under these assumptions {pathway} still ranks first" or "{other} would now rank first by $X".
- It updates **on every `input` event** (already wired through `ACT.scen` → `tiRefresh`); keep it under 16 ms by updating only the card, not the whole panel.
- Slider labels as in R3: **Avoided purchase price**, **Preparation, parts and fees**, **Service exposure**, **Resale price** (tooltip: "also scales lease income"). Keep the "Confirmed internal demand is cancelled" switch; it becomes an edge case in 4.6.
- `aria-live="polite"` on the sentence (not on the figures, to avoid chatter while dragging).
- Reuse `.panel`, `.num` and the KPI tile styling. No new colours.

### 4.4 Tie-breaker and multi-option comparison (R4)

**Tie-breaker.** In `scenRoutes` / ranking, after sorting by net:
1. If the top two are a **near-tie** (D8), compare secondary factors in order. A factor decides only when the gap is meaningful: risk/confidence ≥ 5 points; demand certainty is confirmed against forecast; cycle time ≥ 3 days; RUL ≥ 6 months; carbon ≥ 10%. Otherwise move to the next factor.
2. Record `tie:{withPlan, decidedBy, values}` on the ranking result.
3. Show a **"Close call"** callout in the recommendation: "Redeploy and Re-lease are within $180 (2%). Redeploy is preferred because demand is confirmed (order SO-… at Site 3) while re-lease demand is a forecast." List the factors checked, with a tick or dash for each.
4. Factor sources already exist in `tiM`: `days` (cycle time), `prob` (risk/confidence), `life` (RUL), `co2`. Demand certainty comes from `demand.confirmed` / `demandStatus`.

**Do not change the approved recommendation** of existing seeded cases. Tie-breaking applies only when a near-tie exists, and seeded near-ties are added on purpose (section 6). Check that the cross-page invariants still hold.

**Multi-option comparison.** In the what-if step, a table (cards on phone) of the **top three** pathways (or the ones ticked in panel 2):

| Column | Content |
|---|---|
| Pathway | name, Recommended badge on the winner |
| Base net · Simulated net · Δ | as in 4.3, per option |
| Cycle time · RUL · Success % · Demand · CO₂e | secondary factors, with the deciding one highlighted (bold plus a "decides" tag) |
| Rank | under the current assumptions |

The **"Apply to"** selector (D9) stresses one option only; the others stay at base. A one-line rationale under the table explains the ranking. A **"Show differences only"** switch hides the factors where the options are equal (research note 13.2).

**Confidence as labelled levels.** Show the recommendation's confidence as **High**, **Medium** or **Low**, each with what to do: High → approve as normal; Medium → check the deciding factor; Low or a close call → compare the alternatives before approving. Keep the success % in the drill-down for engineers and analysts. When confidence is Low or a near-tie applies, **open the comparison table by default** instead of leaving it collapsed (research note 13.2). The tie-breaker rules and their order are always visible on screen, not only in a tooltip.

### 4.5 Condition → life → value summary (R5)

A three-column card, used in **Step 2** of the treatment page (4.6) and on the **Asset intelligence Overview**:

| A. Diagnostic condition | B. Life after intervention | C. Commercial value for that life |
|---|---|---|
| Main metric per class: motor **winding insulation (grade)**, pump **seal and bearing wear (%)**, control unit **controller self-test (pass/fail, error count)**, power tool, batch and IT **battery health (%)**. Source: EAM or Inspection, with freshness | **Estimated RUL** after intervention (from `engLife`, e.g. 36 months) **and**, separately, the **Certified operating period** (e.g. 12 or 24 months) with its basis ("certified by Engineering, QMS ref …"). When the certified period is shorter, say so plainly: "Can't be certified for 36 months; limited to 24" | Recommended route · Net recovery (e.g. **$9,600**) · Lease or demand horizon **capped at the certified period** (D10) · Matched demand (e.g. "Pending order **SO-48102** at **Site 3**") · Target warehouse or site |

Rules:
- If demand needs a longer horizon than certified: show the "Needs re-certification" chip and mark the pathway **Conditional** in panel 1, with that reason.
- Show the **estimated RUL as a range** (for example "30–40 months, most likely 36"), not a single number. The certified period is a single, firm figure with its reference. The difference between "estimated range" and "certified" is the point of this card (research note 13.3).
- Text labels for every status; no colour-only meaning.
- Mark modelled values ("modelled from grade, age and class"), as the asset page already does.

### 4.6 Treatment page as five guided steps (R6)

Restructure `caseView` into numbered **steps** with a sticky step bar (1–5) that scrolls to each. Every existing piece is kept and moved; **nothing is deleted**.

| Step | Contents (new or moved) |
|---|---|
| **1. Returned asset and current status** | `tiCtx` facts and photo (objective sliders move to step 4) · current status chip · **why** it is in that status (for example "Awaiting approval since 06 Oct · submitted by Planner · Customer A") · **outstanding** items: missing evidence, pending test report, pending approval and who it waits on · re-evaluation callout (moved) |
| **2. Recommended outcome** | Large summary: route, **net recovery**, **costs**, **RUL** and the 4.5 card, matched order or demand, target site or warehouse, success %, cycle time. "Close call" badge if the tie-breaker applied |
| **3. Why this outcome** | Panel 3's rationale (drivers, why not the runner-up, binding constraints) · panel 1 (eligibility and gates) · panel 2 (outcomes comparison table and chart) · diagnostic findings · demand matching · "Detailed analysis" (evidence, prediction, options and gates, pool, explanation) collapsed by default under **Show full analysis** |
| **4. What-if and edge cases** | Business-objective sliders (moved from step 1) · 4.3 result card · 4.4 multi-option table and tie-breaker · edge-case presets as buttons: **Demand cancelled**, **Parts cost +30%**, **Resale price −20%**, **Certification shorter than demand**. Save, load and delete scenarios (role-gated, unchanged) |
| **5. Next best action: approval and handoff** | The role's buttons (unchanged by RBAC: Submit for review, Approve, Override, Decline, Record assessment result, Confirm outcome) · **required approval and responsible approver** · **target enterprise application(s)** from 4.1 · **instruction preview before approval**: the full handoff content per target system (route, asset, site, order, amounts) in readable form, with "View raw payload", so the Approver sees exactly what will be sent (today the payload is only visible after approval) · instruction status · external reference once acknowledged · expected outcome against actual result status · handoff readiness (old panel 5). There is never an auto-approve path; every handoff carries the approval reference (research note 13.4) |

Layout: single column on all widths for steps 1, 2 and 5. Steps 3 and 4 may use two columns above 1180 px. Every step has an anchor (`#/product/RT-1048` plus `#step-3`), so the sidebar flyout and the step bar deep-link. Keep `#explain` working (it points to the collapsed analysis and opens it).

### 4.7 Command Center: senior and operational views (R1)

**Executive (senior view)**: add to `CC_LAYOUT`:
- **KPIs (top, large):** `net`, `uplift`, `yield`, `avoided`, `co2m`: the same ids and functions as Finance, so the numbers match Finance and Analytics.
- **Portfolio health:** lifecycle portfolio, treatment opportunity, value realisation (12 months).
- **Exceptions panel** (new, `ccExceptions`), each row with severity, value, count, trend and two buttons, **View cases** and **Notify owner**:
  - Value at risk by reason (existing data)
  - **Warehouse bottlenecks:** from `ccUtil()` against `CC_CAP`; show any location at 85% or more, with the cases there
  - **Declining metrics:** any KPI whose month-on-month change is below −5% (the sparkline data already exists)
  - **Deteriorating condition:** assets whose grade or health dropped between inspections (needs a small seeded `prevGrade`; see section 6)
- **Hidden by default:** approvals inbox, actions to prioritise table, outcomes to confirm. A **"Show operational queues"** toggle reveals them read-only (remembered in `circ-nav`-style local state).
- **View cases** opens the existing drill drawer (`setDrill`) filtered to the affected cases. **Notify owner** opens a modal (recipient prefilled by D7, message, severity) → creates a **notification request** in `S.reqs` (type `notify`), an audit entry, an event and a toast "Notification sent to {account} (simulated)".

**Operational view** (Planner, Engineer, Warehouse Manager):
- **Actions on me** (new panel, top): everything whose next step belongs to this account: notifications addressed to me, evidence requests I must answer (Engineer), my declined cases to re-evaluate (Planner), items at my warehouse waiting for putaway acknowledgement (Warehouse Manager). Each row has one primary button that deep-links to the step on the treatment page.
- **Approvals** (D6): my submissions waiting for approval, status only.
- **Handed off · awaiting outcome**: cases in `approved` or `executing` stage (38 in the seed: 31 + 7), with target system, external reference and age; overdue ones are flagged.
- **Scope:** the account's site or warehouse (D4, D5). A scope chip in the header: "Warehouse 1 · change".
- KPIs per role stay as in the RBAC plan, plus "Actions on me" as the first KPI.

**Admin:** a **Senior / Operational** segmented switch on the Command Center (D1). The default is Operational, as today.

**Linked layers, not silos (research note 13.1).** Dashboard guidance describes three linked layers: strategic (senior view), tactical (analysis by managers and analysts) and operational (queues). They share the same metric definitions and drill into each other. Here:
- Senior view → **Analytics** is the tactical layer → **Returned assets / case pages** are the operational layer.
- Every senior KPI and exception drills down along that path, using the **same KPI ids** as Finance and Analytics.
- An exception that is notified links to the recipient's **Actions on me** item. When the recipient acts, the exception shows "In hand by {account}", closing the loop.
- Exceptions are **ranked** (value × urgency), not just listed when they cross a threshold.

Whether a separate tactical audience exists (regional or portfolio managers) is question D16.

### 4.8 Process Orchestration page (R7)

New page `#/orchestration` ("Behind the screen", menu item **Process orchestration** with the sub-line "How a recommendation is made"). Sections: `flow`, `run`, `agents`.

- **Flow:** the ten stages as a horizontal pipeline (vertical on phone). Reuse the Workflow studio canvas styles (`--fx-*` tokens, node states success, failed, upstream failed, running), not a new chart library.
- **Each stage card:** name, what happens (one line), **agent or component** (Evidence Assembler, Data preparation service, Gate engine, Prediction models v1.3, Opportunity Finder / `optimize_pool`, Recommendation service, Approval (human), Handoff Coordinator, Reconciler), **source systems** (EAM, ERP, CRM, WMS, telemetry…), status, start and end time, duration.
- **Run:** pick a case (default RT-1048) to show its run. Completed stages come from real case data (evidence fetch times from the audit log, gate results, model version, approval ref, handoff refs). **Replay** animates the stages with simulated timing (`Math.random` is allowed for live motion only). A **"Simulate failure at stage"** dropdown shows how failures propagate (reuse the workflow failure logic).
- **Links:** stage → its evidence (Audit), its tool calls (MCP call log, for Developer and Admin), its handoff (Event stream).
- **Data source:** build the run view **from the audit trail and call log**, not from a separate script, so the demo shows what is actually recorded. Each tool call shows its parameters, the account or agent, and timestamps, with **sensitive values redacted** (shown as `•••` with the field name). Shape the records like the OpenTelemetry GenAI conventions (a trace per case, a span per stage or tool call), so a real build could export them to the customer's monitoring tools (research note 13.4).
- **Mapping note** on the page: how these stages relate to the ten-step journey strip (1 Supply evidence = Pull data + Data preparation; 2–3 = Gates + Predictions; 4 = Optimise; 5 = Approval; 6–8 = Handoff; 9–10 = Outcome and reconcile).
- **Wording:** a callout saying "Circularity decides and instructs. The physical work, orders and stock movements happen in your enterprise systems." (R8)

### 4.9 Identity and user settings (M1)

New **Access → Identity and users** section (Admin), next to Accounts and roles:
- **Identity provider card:** "Microsoft Entra ID (example) · simulated", tenant id placeholder, last directory sync, **Sync from directory** (simulated, writes an audit entry).
- **Setup order shown as three steps:** 1 **SSO** (SAML or OIDC) → 2 **Provisioning** (SCIM: creates, updates and removes users) → 3 **Role mapping**. Each has a status. The note says SSO must work before provisioning (research note 13.5).
- **Role source:** "Entra ID App Roles (recommended)" or "Directory groups". Explain in one line why App Roles are preferred: they keep working when a group is renamed and avoid group-overage limits.
- **Group-to-role mapping:** a table of directory groups or App Roles (synthetic, e.g. `circ-planners-customer-a`) → role, tenant, site. Admin can edit the **mapping**, which re-maps the demo accounts. **Group membership is read-only** here ("Managed in your identity provider"). Mapped roles only **add** permissions; a user's effective access is the union of their roles. Admin cannot be granted through a group; it is assigned directly.
- **Deprovisioning:** show that a user removed in the directory loses access at the next provisioning sync. Without provisioning, access is only refreshed when the user next signs in. Show "Last sync" and a simulated "User removed" event in the audit log.
- **Approval hierarchy and delegation:** Approver delegation per scope (exists) plus an **escalation path** (Approver → Admin) and limits (for example approvals above $25k need Admin; show only, enforcing it is optional and assumed). Add **out-of-office delegation**: an Approver names a delegate with **start and end dates**. The delegate must already hold the Approver role for that scope (ineligible people cannot be picked), and whoever acts first completes the item.
- **Users:** a synthetic list with role-based labels and `example.com` addresses only (no real names), marked "From directory". There is no "Add user" form; a note explains that users are added in the identity provider and appear after the next sync. This answers "how do I add?".
- The sign-in screen gets a note: "In production you sign in with your company account (SSO). This demo lets you pick a role."

### 4.10 Roles after this plan

| Role | New in this plan | Lands on |
|---|---|---|
| Executive (new) | Senior Command Center, exceptions, Notify, read-only Analytics, Product, Audit and Orchestration | Command Center (senior) |
| Warehouse Manager (new, per warehouse) | Operational Command Center for one warehouse, Actions on me, acknowledge, request evidence | Command Center (operational) |
| Planner | Operational view, Actions on me, site default filter | Command Center |
| Engineer | Operational view, Actions on me, site default filter | Asset intelligence (unchanged) |
| Approver | Receives notifications; otherwise unchanged | Command Center |
| Finance | Unchanged (the value KPIs are now shared with Executive) | Analytics |
| Developer | Receives integration notifications; Orchestration with call-log links | Source map |
| Admin | Senior/Operational switch, Identity and users | Command Center |

Add both new roles to `ROLE_POLICY`, `ACCOUNTS`, `CC_LAYOUT`, `HOME_LABEL` and the README role tables. Every new control must be listed in `PERM_ACTS` (new permissions: `notify`, `ack`, `manageIdentity`) so the forbidden-control scan covers it.

### 4.11 Do not break

- RBAC behaviour: hide-don't-disable, the tenant lock, delegations, requests, comments and the forbidden-control scan.
- Seeded numbers and invariants: 128 live cases, 1,400 closed, the Command Center, Product and Analytics figures. Section 6 additions must not change existing totals. If one does (for example a new near-tie case), update the invariants, the README "demo in numbers" table and `CHANGES.md` together.
- Deep links: `#/product/RT-xxxx`, `#/product/asset/RT-xxxx` and `#explain` must keep working.
- Phone width (390 px): no horizontal overflow, as today.

---

## 5. Visibility changes (adds to the RBAC matrix)

`V` visible and usable, `R` read-only, `—` hidden. Admin is `V` everywhere.

| Area | Executive | Warehouse Mgr | Planner | Engineer | Approver | Finance | Developer |
|---|---|---|---|---|---|---|---|
| Command Center · senior view | V | — | — | — | — | — | — |
| Command Center · Actions on me | — | V | V | V | V | V | V |
| Command Center · Exceptions + Notify | V | R (own warehouse) | — | — | — | — | — |
| Product · Expected returns | R | V (own warehouse) | V | V | V | R | — |
| Product · Returned assets, case pages | R (drill-down) | R (own warehouse) | V | V | V | R | — |
| Analytics | R | — | R | R (eng, sustain) | V | V | — |
| Process orchestration | R | R | R | R | R | R | R + call log |
| Audit | R | R (own warehouse) | R (own tenant) | R | R | R + C | R + C |
| Access · Identity and users | — | — | — | — | — | — | — |

---

## 6. Data additions (synthetic, deterministic)

Add these with the seeded generator (`rnd`, `rint`, `pick` at load time only):

| Field | On | Notes |
|---|---|---|
| `diag:{metric,value,unit,source,at}` | every case with an inspection | Per-class metric (4.5). Derived from grade and age so it agrees with the existing condition |
| `rul:{estMonths,estLow,estHigh,certMonths,basis,certRef}` | cases with `engLife` | `estMonths` from `engLife`, with a low–high band (wider for older or lower-grade units); `certMonths` ≤ estimate (for example 12 or 24 for older units). RT-1048: estimate 36 (30–40), certified 24 |
| `confidence:'High'\|'Medium'\|'Low'` | ranked recommendations | Derived from the existing P10–P90 spread and success %, so it agrees with the numbers already shown |
| `outcome:{likely,prob,window}` | `EXPECTED` rows | Return, Buyout, Extension or Early termination; probability; return window |
| `demand.order`, `demand.horizonMonths` | cases with internal demand | Synthetic order refs (`SO-48102` for RT-1048 at Site 3); horizon for the lease or demand |
| `prevGrade` | about 10 cases | Gives the "deteriorating condition" exception something real to show |
| `contract`, `lease`, `expiry`, `customer` | `EXPECTED` rows | 4.2 |
| Near-tie cases | 2 existing cases, adjusted | Choose cases whose top-two nets are already close (measure in Phase 0). Only if none exist, adjust one non-hero case's terms, and update totals as 4.11 says |
| Account `site` / `warehouse` | `ACCOUNTS` | Planner and Engineer home site; Warehouse Manager warehouse |
| Approver labels | `mkExec` | Replace the personal-looking names with account labels |
| Directory groups and users | Access | `example.com` addresses and role-based labels only |

Every new figure that appears in two places gets an invariant in `runInvariants` (for example the Executive KPIs equal the Finance KPIs; the "handed off · awaiting outcome" count equals the lifecycle legend).

---

## 7. Phases (each ends with tests, a screenshot and a short report)

**Phase 0: Baseline and decisions.**
- Branch `feature/guided-flow` from `feature/rbac-adaptive-ui` (or from `main` if it is merged).
- Rebuild the test harness (section 9) and run the existing 178 checks.
- Take baseline screenshots of the treatment page (RT-1048), the Command Center (Admin, Finance) and Expected returns.
- Measure near-ties: list cases whose top-two nets are within 5% or $250.
- Send the section 3 questions. Record the answers in section 10 of this file.

**Phase 1: Wording and handoff model (R8).** Labels per 4.1, `STEP_TPL` rewrite, the handoff legend, the agent rename, and approver labels instead of names. No change to ids, stages or numbers. Test: label scan (no "Executing", "Execution timeline", "Execution readiness" or "executed" in rendered text for any role) and the invariants unchanged.

**Phase 2: Expected returns from Contract Management (R2).** 4.2 data, columns, header note, drawer and scoping. Test: columns present; every row names Contract Management; tenant lock holds; no overflow at 390 px.

**Phase 3: Guided treatment page (R6, R5).** Restructure `caseView` into five steps (4.6), the condition → life → value card (4.5) on the treatment page and the Asset Overview, the outstanding-items list, the step bar and anchors. Test: all 128 cases render for every role with no `undefined` or `NaN`; RBAC buttons are only in step 5; `#explain` and the deep links work; the certified-period cap and Conditional flag work.

**Phase 4: What-if, tie-breaker, multi-option (R3, R4).** Result card (4.3), tie-breaker in ranking, "Close call" callout, comparison table, Apply-to selector and edge-case presets. Test: the card updates on `input`; Δ sign and colour are correct; the seeded near-tie is explained by the expected factor; non-tie cases keep their recommendation; invariants hold.

**Phase 5: Command Center views and new roles (R1).** Executive and Warehouse Manager in the policy and accounts; senior layout with exceptions, drill-down and Notify; operational layout with Actions on me, approvals status and handed-off items; site scoping; Admin switch. Test: role-by-page matrix extended; forbidden-control scan for new acts; Executive KPIs equal Finance KPIs; Notify creates an Actions on me item for the recipient and an audit entry; Warehouse Manager sees only its warehouse.

**Phase 6: Process Orchestration (R7).** Page, stages, per-case run, replay, failure simulation, links and the mapping note. Test: renders for every role; stage states come from case data for RT-1048; links are hidden for roles without access; no overflow at 390 px; reduced motion respected.

**Phase 7: Identity and user settings (M1).** Access → Identity and users, the sign-in note, editable mapping and the audit of changes. Test: Admin only; editing a mapping changes the demo account's role or scope; no personal data patterns (no real-looking names; only `example.com` addresses).

**Phase 8: Hardening and docs.**
- Full test run, palette audit, dark mode and 390 px screenshots for the new screens.
- `CHANGES.md` **Update 8** with what changed, where, buttons to press, a three-minute walk-through and screenshots `docs/screenshots/flow-*.webp`.
- Update `README.md`: roles, screens, matrix, "demo in numbers", pitch script (Executive first) and "what is real and what is simulated".
- Commit with a detailed message. **Do not push until asked.**

Suggested order if time is short: Phase 1 → 3 → 4 → 5 → 6 → 2 → 7. Wording and the guided page carry most of the Product Owner's "structure the flow" ask.

---

## 8. Project rules

All rules in `docs/PLAN_RBAC_ADAPTIVE_UI.md` **section 7** apply unchanged: palette tokens only (no new colour literals), prefixed class names (search before adding; new prefixes here: `or` for orchestration, `ex` for exceptions, `ao` for actions on me, `idp` for identity), reuse existing components, no new libraries, `data-act` + `ACT` + `esc()`, hash routes for every section, container queries, test at 390, 768, 1280 and 1600 px, synthetic data only, plain English, `CHANGES.md` for every visible change, and no push until asked.

Additional rules for this plan:
- **Positioning wording (R8) is a rule, not a phase.** Any new text must describe Circularity as deciding, recommending and instructing. Enterprise systems carry out the work.
- **Estimated vs certified** must never be merged into one number (R5).
- **Simulated** must be stated wherever the demo pretends: notifications, directory sync, SSO, system acknowledgements, orchestration timings.
- **No personal data.** No real or real-looking personal names, emails or account numbers. Use role labels, Customer A/B/C, Site 1–8, Warehouse 1/2 and `example.com`.

---

## 9. Test plan (extends the RBAC harness)

The harness (headless Chrome, `t.js` writing PASS/FAIL into `<pre id=T>`) is described in the RBAC plan section 8. Known traps are in the session memory note "headless harness quirks": `MSYS_NO_PATHCONV=1` for `#/` arguments; override `parse()` in bulk route loops (Chrome throttles hash changes); use a 390 px iframe for phone width; CRLF line endings.

Add these checks:

1. **Wording scan:** for every role and reachable page, the rendered text contains no "Executing", "Execution timeline", "Execution readiness", "executed" or "In execution". Each handoff step names a target application.
2. **Expected returns:** the required columns exist; every row shows a Contract ID and "Contract Management"; the tenant and warehouse scope holds.
3. **Guided page:** for all 128 cases and every role, steps 1–5 render in order; the action buttons appear only in step 5; there is no `undefined` or `NaN`; `#step-N` and `#explain` scroll to the right place.
4. **RUL card:** estimated and certified values are shown separately; the horizon is ≤ the certified period; "Needs re-certification" appears when demand is longer, and the pathway is Conditional.
5. **What-if card:** setting a slider value and dispatching `input` updates Base, Simulated, Δ $ and Δ % correctly (compare with `scenNet`); the sign and arrow match.
6. **Tie-breaker:** seeded near-ties report the expected `decidedBy`; non-ties keep their current recommendation (compare with the Phase 0 snapshot of all 128 recommendations).
7. **Command Center views:** Executive KPI values equal Finance's; operational queues are hidden by default for Executive; exceptions drill to the right cases; Notify → the recipient's Actions on me shows the item, with an audit row.
8. **New roles:** the role-by-page matrix and forbidden-control scan include Executive and Warehouse Manager; Warehouse Manager sees only its warehouse everywhere (Command Center, Product, Audit, search).
9. **Orchestration:** ten stages render for every role; RT-1048 stage states match its data; replay finishes; failure simulation marks downstream stages; links obey the policy.
10. **Identity:** Admin only; a mapping edit changes the demo account's role or scope and is audited; no personal-data patterns.
11. **Existing suite:** all 178 RBAC checks still pass (update expectations only where this plan deliberately changes a label).
12. **Overflow at 390 px** for every page each role can reach; dark-mode screenshots of the new screens; palette audit.
13. **Research-driven checks:** the instruction preview is visible before Approve and matches the payload sent after approval; confidence labels agree with the P10–P90 spread; the comparison opens by default on Low confidence or a near-tie; the RUL range always contains the point estimate and the certified period is never shown as a range; group membership is read-only in Identity and users; an out-of-office delegate must be eligible; Expected returns probabilities sum to 100% per row; redacted fields never show raw values in the orchestration view.

---

## 10. Product Owner decisions

*To be filled in after Phase 0.* One row per section 3 question: the answer, and where it lands. Points not answered stay **(assumed)** and are listed here.

| # | Answer | Where it lands |
|---|---|---|
| D1 | **Team decision (2026-10-15):** new **Executive** role, read-only plus Notify; Admin also gets the Senior / Operational switch. Still to confirm with the Product Owner | 4.7, 4.10 |
| D3 | **Team decision:** keep **Warehouse Manager** as its own role, locked to one warehouse | 4.7, 4.10, 5 |
| D4 | **Team decision:** a default site filter for Planner and Engineer (they can widen it within their tenant); a hard lock only for Warehouse Manager | 4.7 |
| — | **Team decision:** keep the additions beyond the brief: instruction preview before approval, confidence levels and the RUL range, and Likely lease outcome on Expected returns | 4.2, 4.4, 4.5, 4.6 |
| D2, D5–D20 | pending (Product Owner) | |

**Still open from the RBAC plan:** Approver and Engineer access to Integration and Audit; non-Planner roles see all tenants; Developer and Admin reply to Finance comments; the Access page cannot create accounts. D13 may settle the last one.

---

## 11. Definition of done

- A senior user signs in and, without scrolling, sees value realised, portfolio health and the exceptions that need attention. They can drill into the cases and notify the owner, and the owner sees it in **Actions on me**.
- An operational user sees their own queue for their site or warehouse: what is on them, what waits for approval, and what is with enterprise systems awaiting an outcome.
- Expected returns clearly come from contract and lease expiry in the Contract Management application.
- The treatment page reads top to bottom: status → recommendation → why → what-if → approve and hand off. The recommendation summary connects condition, certified life and commercial value.
- What-if results are impossible to miss. Near-ties are explained by named secondary factors, and the top options can be compared side by side.
- Process orchestration explains, stage by stage, how agents and services produce a recommendation, with sources, status and time.
- No screen implies Circularity carries out physical work. Every handoff names the target enterprise application.
- User settings explain how users and roles come from the identity provider.
- All checks pass with no console errors; no new colours; light and dark both correct; no overflow at 390 px; numbers reconcile.
- `CHANGES.md` Update 8 and `README.md` are updated with screenshots; work is committed (not pushed).

---

## 12. Prompt to paste into the fresh session

> Read `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` fully (including the research notes in section 13 and the requirement check in section 14), then `docs/PLAN_RBAC_ADAPTIVE_UI.md` sections 2, 7 and 8, `README.md` and `CHANGES.md` Update 7. Skim `index.html` around `/*RBAC-START*/`, `CC_LAYOUT`, `EXPECTED`, `/*TI-START*/` (`caseView`, `tiP3`, `tiP4`, `tiImpact`, `tiP5`), `STEP_TPL`, `execBlock` and `stageChip`. Follow the project rules in section 8 exactly (palette tokens only, no new libraries, prefixed class names, reconcile numbers, synthetic data, no personal data, decision-intelligence wording). Start with Phase 0: branch, rebuild the harness, run the existing checks, take baseline screenshots, measure near-ties, and list the section 3 questions for me to send to the Product Owner. Then do one phase at a time, running tests and sharing a screenshot after each. Commit with detailed messages but do not push until I say so.

---

## 13. Research notes (2026-10-15)

A web research pass checked the plan against published guidance: 20 sources fetched, 78 claims extracted, 25 checked by three independent reviewers. 24 were confirmed and 1 refuted. Confidence is given for each note. **The sources are thin in places, so treat these as informed defaults, not standards.**

| # | Area | What the evidence says | Change made to this plan | Confidence | Sources |
|---|---|---|---|---|---|
| 13.1 | Senior vs operational dashboards (R1) | Separate views are justified, but the standard framework has **three linked layers** (strategic, tactical, operational) with shared metrics and drill-down. Operational dashboards monitor and **alert on exceptions**. Recent practitioner writing favours **ranked exception queues** over simple threshold alerts | 4.7: linked layers, the same KPI ids, a drill path through Analytics, ranked exceptions, Notify closing the loop to Actions on me. D16 asks about a tactical audience | Medium (an old but stable framework; secondary source) | [IBM Cognos white paper reproducing Eckerson's framework](https://public.dhe.ibm.com/software/data/sw-library/cognos/pdfs/whitepapers/wp_picturing_performance_dashboards_and_scorecards.pdf); [From monitoring to exception workflows (blog)](https://www.antoinebuteau.com/the-end-of-the-dashboard-series-6-from-monitoring-to-exception-workflows/) |
| 13.2 | Explainable recommendations and what-if (R3, R4, R6) | Aim for **calibrated** trust, not maximum trust. Explain each recommendation **in the moment**. Show confidence as **labelled levels that each say what to do**; raw percentages are risky for non-experts. Show the **N best alternatives** when confidence is low. Decision-optimisation tools compare scenarios **side by side and mark the differences**. Showing confidence helps people calibrate trust but does not by itself improve joint decisions | 4.3: list of changed assumptions. 4.4: High/Medium/Low with actions, comparison open by default on Low confidence or a near-tie, rules shown on screen, "Show differences only" | High (PAIR), Medium (IBM product docs) | [Google PAIR, Explainability + Trust](https://pair.withgoogle.com/chapter/People%20+%20AI%20Guidebook%20-%20Explainability%20+%20Trust.pdf); [IBM Decision Optimization, compare scenarios](https://www.ibm.com/docs/en/DSXDOC/DO/do_expts/comparescenarios.html) |
| 13.3 | RUL (R5) | Probabilistic RUL models can give calibrated intervals. Much published work reports single numbers, which hides uncertainty | 4.5: estimated RUL shown as a range; the certified period stays a single, firm figure | Low (one preprint on simulated data). Nothing found on showing RUL next to the certified period and lease value; that part of the plan is untested against outside evidence | [arXiv 2511.19124 (preprint)](https://arxiv.org/pdf/2511.19124) |
| 13.4 | Approval gate and agent transparency (R6, R7) | Require explicit human confirmation for financial or data-sharing actions, **never auto-approve**, and show the **full parameters** of the action, not a summary name. **Log every tool call** with parameters, user context and timestamps, **redact secrets and PII**, and alert on unusual patterns. OpenTelemetry has GenAI conventions for agent and tool traces | 4.6: instruction preview before approval, no auto-approve. 4.8: orchestration built from the audit trail and call log, with redaction and trace-and-span shape | High (OWASP), Medium (blog on OpenTelemetry). This applies directly only where handoffs go through MCP or agent tool calls | [OWASP MCP Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html); [OpenTelemetry GenAI conventions explained](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained) |
| 13.5 | Identity, SSO, SCIM, roles (M1) | **SSO first, then SCIM** on top. The identity provider owns group membership, so it is **read-only in the app**. Groups map to custom roles; **effective access is the union** and groups only add permissions; built-in system roles usually cannot be group-mapped. On Entra ID, prefer **App Roles** over group claims (rename-safe, no overage). **SSO-only does not remove leavers**; provisioning does. Out-of-office **delegation does not grant permissions**: the delegate must already be eligible. *Refuted:* "with SCIM on, sign-in is rejected for users not yet provisioned" (0 of 3) | 4.9: three-step setup, App Roles option, read-only membership, union rule, Admin assigned directly, deprovisioning, dated delegation with an eligibility check. D20 asks about identity providers and SCIM | High / Medium (vendor docs that agree with each other; patterns, not standards) | [Braze, SCIM group-role mapping](https://www.braze.com/docs/user_guide/administer/global/user_management/scim_group_role_mapping/); [ClickHouse, SCIM with Entra](https://clickhouse.com/docs/cloud/security/scim-setup-entra); [Docker, group mapping](https://docs.docker.com/enterprise/security/provisioning/scim/group-mapping.md); [Agility Credit, SSO role mapping](https://apidocs.agilitycredit.com/sso/role-mapping); [Oracle EDM, request delegation](https://docs.oracle.com/en/cloud/saas/enterprise-data-management-cloud/dmcaa/understand_request_delegation.html) |
| 13.6 | Expected returns from leases (R2) | Lease ends can be modelled as **probabilistic outcomes** (returned, bought, ended early), each with uncertain timing and an end-of-lease value, rather than expiry = return | 4.2: Likely outcome column, probability, return window, probability-weighted planning range. D19 asks whether the data exists | Low (one abandoned 2003–04 patent application about vehicle leases) | [US20040148241 (abandoned application)](https://www.google.com.tw/patents/US20040148241) |

**Gaps in the evidence.** No source survived verification on (a) guided top-to-bottom case page layouts, or (b) how other products build "behind the screen" agent views. Those parts of R6 and R7 rest on the Product Owner's brief and our own design.

**Tension to resolve.** OWASP's "log full parameters" pulls against redacting PII. Kinective policy also forbids processing end-customer PII. The demo uses synthetic data only. A production design needs field-level redaction or tokenisation, decided with security and Legal.

> **Legal review.** Sections 13.4 to 13.6 touch security, identity and a patent document. Kinective's Legal team should review them before anyone relies on them; the patent reference is background only and must not be used as a design source without that review.

---

## 14. Does the plan match the intent?

Each written requirement and meeting point, checked against the plan.

| Ask | Covered in | Match | Notes |
|---|---|---|---|
| R1 Senior view: value KPIs on top for non-Finance users | 4.7, 4.10 | Yes | New Executive role; Admin switch (D1) |
| R1 Senior view: hide operational queues by default | 4.7 | Yes | "Show operational queues" toggle, read-only |
| R1 Exceptions: value at risk, warehouse bottlenecks, declining metrics, deteriorating condition | 4.7, 6 (`prevGrade`) | Yes | Ranked (13.1) |
| R1 Drill down and notify the responsible person | 4.7, D7 | Yes | Simulated notification → Actions on me |
| R1 Operational: approvals inbox, Actions on me, items with enterprise apps awaiting outcomes | 4.7 | Yes | Approvals as status for non-approvers (D6) |
| R1 Scope to the user's warehouse or site | 4.7, D4, D5 | Yes, with a choice | A default filter or a hard lock is the Product Owner's call |
| R2 Contract ID, Customer, Lease period, Expiry, Source application | 4.2 | Yes | Plus Likely outcome (13.6), going beyond the brief; confirm (D19) |
| R2 Say clearly it comes from contract and lease expiry | 4.2 | Yes | Header note and source label |
| R3 Large Base / Simulated / Δ $ / Δ % card, live, up and down cues | 4.3 | Yes | Plus a list of the changed assumptions |
| R3 Sliders: purchase price, prep/parts/fees, service exposure, resale price | 4.3 | **Partly** | The resale slider also scales lease income (as today). Ask whether to split it into "Resale price" and "Lease income" |
| R4 Tie-breaker on cycle time, RUL, risk/confidence, demand certainty, carbon, with an explanation | 4.4, D8 | Yes | The factor order is a proposal (D8, D18) |
| R4 Side-by-side multi-option what-if with base and simulated per option | 4.4, D9 | Yes | "Apply to" selector for one option |
| R5 Diagnostic condition from EAM or diagnostics | 4.5, 6 (`diag`) | Yes | Modelled metric per class, labelled |
| R5 Estimated RUL vs certified period, clearly separate | 4.5 | Yes | RUL as a range (13.3) |
| R5 Commercial value for that life, demand match, consistent with certification | 4.5, D10 | Yes | Horizon capped at the certified period |
| R6 Five-step guided page in the given order | 4.6 | Yes | Nothing removed; "Detailed analysis" collapsed in step 3 |
| R7 Process Orchestration menu item with ten stages, agents, sources, status, timestamps, live link | 4.8 | Yes | Built from the audit trail (13.4) |
| R7 Must not imply Circularity executes physical work | 4.8, 4.1 | Yes | Callout on the page |
| R8 Decision-intelligence positioning; handoff table (ERP order mgmt, EAM, WMS putaway) | 4.1 | Yes | Labels only; internal ids kept |
| M1 Users and roles from SSO / identity provider; "how do I add?" | 4.9 | Yes | Simulated; users are added in the identity provider, not in the app |
| M2 Follow the user journey diagram | D15 | **Blocked** | The diagram is not in the repo |
| M3 Edge cases | 4.4, 4.6 step 4 | Yes | Near-tie seeds and edge-case presets |
| M4 "Increase the count of the rows… with the same button" | D12 | **Unclear** | Not planned until clarified |

**Added beyond the brief** (flag to the Product Owner, easy to drop): Warehouse Manager as its own role, the instruction preview before approval, confidence levels, Likely outcome on expected returns, out-of-office delegation, and the replacement of personal-looking approver names.
