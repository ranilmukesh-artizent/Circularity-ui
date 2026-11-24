# The case journey: from lease end to learning

A **case** is one returned asset and the decision about what to do with it. Every case runs through the same ten
stages. This guide names each stage as the app does, says what starts it, who acts, and what Circularity does on its
own. The worked example is **RT-1048**, a Voltara industrial motor returned by Customer A: sign in as `ops` (Planner ·
Customer A) to follow it.

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems the case talks to are simulations;
> no real vendor system is connected.

## Contents

1. [Where you see the journey](#1-where-you-see-the-journey)
2. [The ten stages at a glance](#2-the-ten-stages-at-a-glance)
3. [How a case opens](#3-how-a-case-opens)
4. [Stage by stage](#4-stage-by-stage)
5. [Declines and re-evaluation](#5-declines-and-re-evaluation)
6. [Worked example: RT-1048](#6-worked-example-rt-1048)
7. [Good to know](#7-good-to-know)

## 1. Where you see the journey

- **Decision Workbench → Returned assets** lists the cases you may see. Click a case to open it. RT-1048 is marked
  *Start here* for the Planner of Customer A.
- A case opens on the stage where it is now. The stage bar across the top shows all ten stages; each has a state
  (done, running, waiting for approval, waiting for a person, warning, failed, queued) and you can open any of them.
- Each stage page has a **What you do now** box (one primary button when the next step is yours) or a **What happens
  next** box (who it is waiting for, and since when), and detail tabs below it.
- **Process Orchestration** shows the same ten stages for every case: *Stages* explains them, *Case run* follows one
  case, *Live run* plays them in place, *Agents and services* lists who does what with which systems.
- The case's status chip uses short labels: *Needs evidence* (or *Needs review*), *Awaiting approval*, *Approved ·
  handing off*, *Handed off*, *Re-evaluate*, *Closed*.

The stages are grouped into four phases: **Arrive** (1–5), **Decide** (6), **Approve** (7) and **Execute and learn**
(8–10).

## 2. The ten stages at a glance

| # | Stage | Starts on | The agent and systems | A person |
|---|---|---|---|---|
| 1 | **Lease ends** | Contract expiry | Opens the case; gathers serial, model, site, usage, customer intent and lease terms | Nothing required |
| 2 | **Return authorised** | Return authorisation | Records fees, replacement order, book value and acquisition date | Nothing required |
| 3 | **Pickup and transit** | Pickup booked | Tracks pickup date, ETA and freight cost | Nothing required |
| 4 | **Received** | Goods receipt | Starts the holding-cost clock; checks which evidence is still missing | Confirms receipt if needed; may request missing evidence |
| 5 | **Inspect and grade** | Inspection result | Requests missing tests; reads grade, faults, repair estimate and test criteria | Engineer records results |
| 6 | **Decide** | Evidence complete | Gathers demand and prices, builds every candidate route, runs the gates and the business rules, predicts and ranks; builds the decision packet | Planner reviews, asks why, tries what-ifs, submits |
| 7 | **Approve** | Packet submitted | Runs a pre-approval check; drafts the rationale | Approver approves, edits (overrides) or declines |
| 8 | **Execute** | Approval | Sends the route's instructions in sequence; tracks acknowledgements; flags delays | Handles exceptions only |
| 9 | **Outcome** | Final acknowledgement | Collects actual costs and realised value | Finance confirms |
| 10 | **Reconcile and learn** | Outcome confirmed | Compares predicted and actual line by line; creates learning records; carries forward open demand | Reviews variances |

## 3. How a case opens

Cases reach Circularity in two ways.

**From the book (the demo's starting cases).** The demo starts with 128 returned assets across the three customers,
already at different stages. Their stages 1 to 3 are drawn from the lease and return records ("Opened by the agent
from Lease management").

**From data (new cases).** A new case opens when a return, lease end, trade-in, contract end or device alarm arrives
as data. The reasons the app knows are: return (RMA), lease end, trade-in, contract end, IoT alarm and manual. There
are three ways in, each needing the *open cases* permission (Admin, Developer and Planner; in the screens, Admin and
Developer):

- **A workflow with the Open case block.** In Workflow Studio, the *Open case* block (under branches, "A case for each
  record") opens a case for every record that passes it. You set the *Asset field* that holds the asset key, the
  *Template* (`industrial`, `tool_fleet` or `device`: industrial returns, tool fleet returns or device recommerce),
  the *Reason*, and the organisation unit (or it takes the one the source is bound to). A test run opens nothing; it says "Would open N cases". See the
  [Workflow Studio guide](workflow-studio.md).
- **Manual Import.** In Connection Fabric → *Manual Import*, after validating a CSV, tick **Open a case for each row**
  and pick the template and the reason before **Load … rows for evaluation**. Each row's owner column names the
  organisation unit. Tool-fleet and device rows carry their template's extra columns (see the
  [Connection Fabric guide](connection-fabric.md#13-manual-import)).
- **Directly through the API** (the technical team, as a signed-in person with the permission).

What happens when a case opens: it gets the next free number (RT-…), belongs to the organisation unit (which decides
who may see it), takes its facts from the record and from what the source systems say about the asset, and is valued
at once: every route is built, the published business rules of its organisation are applied, and the routes are
ranked. With a recommendation it waits for approval; without one it waits for evidence. A tool-fleet or device case
is valued and ranked by its own template (its paths, such as *Re-issue to fleet* or *Refurbish → place* for a tool,
or the sale channels *Buy Now*, *Offers*, *Auction* and *Marketplace* for a device lot), the same way the Modeler's simulation ranks it; a re-evaluation values it again the same way, and
after approval each of its paths has its own execution steps.

**One case per asset and reason.** If the same asset arrives again for the same reason (a re-sync, a replayed event,
a file loaded twice), no second case opens: the workflow and the import skip it, and a direct request is refused with
"A case for this asset and reason is already open".

## 4. Stage by stage

### Stages 1–3: Lease ends, Return authorised, Pickup and transit

Nothing for a person to do. The agent reads the lease, the return authorisation, the finance record and the
carrier's tracking. Tabs: *Lease record*, *Customer*, *Systems* (stage 1); *Authorisation*, *Finance* (stage 2);
*Route*, *Cost trace* (stage 3).

### Stage 4: Received

The goods receipt in the warehouse system starts the holding-cost clock. Circularity checks the evidence list
(return record, identity and configuration, inspection report, service history, engineering assessment, photos,
demand evidence, market comparables, cost and stock data, policy and certification) and shows what is missing.

- If evidence is missing and no route can be valued, the case shows *Needs evidence* and the box offers the request,
  for example **Request inspection**. A Planner, Engineer, Warehouse Manager, Approver or Admin can press it. It sends
  a request (a work order reference) to the owner of the missing evidence; the case continues when the result arrives.
- Tabs: *Evidence checklist*, *Location*, *Holding cost*.

### Stage 5: Inspect and grade

- If evidence is missing and nobody has asked yet, the box offers the request (as in stage 4).
- Once the request is out, an **Engineer** (or Admin) sees **Record the result**. It records the result from the
  inspection system: the grade (A to D), the engineering life in months and the next inspection date. You do not
  type the grade.
- Recording the result rebuilds and ranks every route at once and takes a new evidence snapshot. With a
  recommendation the case moves on to approval; if no route is eligible it waits for review.
- Tabs: *Findings*, *Diagnostic condition*, *Certified period*, *Photos*.

### Stage 6: Decide

This is where Circularity does most of its work, automatically, each time a case is valued (when it opens, when an
inspection result is recorded, and when it is re-evaluated):

1. **Routes.** It builds the candidate routes: *Redeploy*, *Whole-asset resale*, *Internal recovered-part use*,
   *Re-lease*, *Material recovery*, *External parts sale* and *Responsible exit* (each with demand, prices, costs,
   timing and a range from pessimistic to optimistic, P10–P90).
2. **Gates.** Every route must pass six gates: *Condition & life*, *Post-intervention*, *Policy & certification*,
   *Demand fit*, *Economics* and *Sustainability*. A route that fails a gate is excluded and shows why. Failed gates
   are resolved by engineering and policy owners, never waived, and the agent cannot waive them. For a battery or IT
   lot, the gates include the need for an approved hazardous-waste route.
3. **Business rules.** Then, after every gate, the rules of the published decision flow of the case's organisation apply (see the
   [Planner guide](users/planner.md#the-modeler-business-rules)): a rule can exclude a route, require one, or prefer
   one. If the rules would leave no eligible route, they are waived for that case. The case records which rules
   applied and which flow version it was valued with.
4. **Recommendation.** The eligible routes are ranked; the top one is the recommendation, with its predicted net
   value, range and confidence. The decision packet holds the evidence snapshot behind it.

What a person does here:

- The **Planner** reviews the packet. Tabs: *Decision packet*, *Compare outcomes*, *Why this outcome*, *Evidence*,
  *What-if and edge cases*, *How it was predicted*, *Demand*.
- What-if scenarios (Planner, Approver, Admin) change assumptions (purchase price, prep and fees, service, market,
  and presets such as *Demand cancelled*, *Parts cost +30%*, *Resale price −20%*, *Critical part unavailable*) and the
  business objectives behind the fit score. **Save scenario** keeps them on the case. A scenario never changes the
  decision.
- The Planner (or Admin) presses **Submit RT-… for review**. The case goes to the approver's queue. Nothing is sent
  anywhere yet.
- If every route failed a gate, the stage shows *failed*: "Every route failed a gate. Engineering and policy owners
  resolve failed gates; the agent cannot waive them."

### Stage 7: Approve

- The **Approver** (or Admin, or a role Admin has given an approval limit) opens the case and presses **Approve
  [route]**, **Edit route** or **Decline**. The approval card shows the recommendation, its expected net and range,
  the agent's drafted rationale, your approval limit, the raw instruction that will be sent, the spend authority and
  the spend and sale terms. You must tick "I reviewed evidence snapshot … and the excluded routes" and keep a
  rationale of at least 15 characters.
- **Approve and send instruction** creates the approval reference (APR-…) and sends the first instruction.
- Choosing another eligible route is an **override**; your rationale is recorded and counted in override analytics.
  An excluded route cannot be approved.
- **Decline** needs a reason (at least 10 characters). Nothing is sent; the case goes to *Re-evaluate*.
- When the Approver is out of office and Admin has recorded a delegate, the stage names the delegate ("waiting for …
  (covering for the Approver)"). The delegate approves or declines in the Approver's place, and the stage then reads
  "Approved by … on behalf of … under APR-…". Whoever acts first completes it.
- Limits and who may approve: see [Approvals](approvals.md#1-decisions-case-approval).
- Tabs: *Rationale*, *Checks*, *History*.

### Stage 8: Execute

The approved route becomes a sequence of instructions, one per enterprise system, sent one at a time. Each system
acknowledges its step and returns its own document (a sales order, a work order, a load, a transfer …), which starts
the next step. For a redeploy the steps are:

| Step | Goes to | Owner | Document back |
|---|---|---|---|
| Allocate to the order line | Order management (order allocation) | Customer operations · order desk | Sales order |
| Refurbishment work order | Repair (depot repair) | Repair centre lead (Engineer) | Work order |
| Book transport | Transport management (load booking) | Transport planner | Load |
| Warehouse moves and outbound delivery | Warehouse management (transfer) | Warehouse Manager | Transfer |
| Delivery confirmed | Order management (order fulfilled) | Customer operations | Fulfilment |
| Actual costs posted | ERP finance | Finance | Finance document |

Other routes have their own steps (a resale reserves the unit, creates a sale order, books the shipment and records
the receipt; a re-lease refurbishes, moves, puts away and signs a lease contract; and so on).

- The first acknowledgement moves the case to *Handed off*; the last one closes it.
- The systems do the work; people handle exceptions only. Each step has a time limit and escalates when it passes it.
- **Check for the next acknowledgement** refreshes the case; acknowledgements arrive as the systems send them.
- The systems are simulations that run on a **simulated clock**, which starts at the demo's date (7 October 2026,
  09:00 UTC) and runs at normal speed. A repair that takes days takes days unless your technical team moves the
  simulated clock forward for a demonstration. A step whose simulated system has nothing to write is acknowledged by
  the simulation itself, two simulated hours later.
- **Pilot mode.** If the case's organisation (or one above it) is in pilot mode, nothing is sent to any system: each
  instruction is held with "Pilot mode: not sent to …" and acknowledged by the simulation, so the case still runs to
  the end. Admin switches it in **Access & Governance → Organisation**, and the unit's **Pilot report** lists what
  would have been sent. See [Approvals](approvals.md#7-pilot-mode).
- Tabs: *Plan*, *Route and timing*, *Messages and acknowledgements*, *Instruction*.

### Stage 9: Outcome

When every step is acknowledged, the systems have reported the actual costs and value and the case is *Closed*.
**Finance** (or Admin) presses **Confirm the outcome**. This records the actual per cost line of the chosen route
against the prediction and links the lines to the models that predicted them. Before the case is closed the button
is refused: "The outcome has not been reported yet".

Tabs: *Delivery*, *Actual costs*, *Documents*.

### Stage 10: Reconcile and learn

After Finance confirms, Circularity compares predicted and actual line by line. Tabs: *Lines* (the variance per
line), *Learning record* (which models learn from the difference; it says either "queued for the next retraining,
for review" or that a candidate model is awaiting promotion) and *Carried forward* (open demand carried to other
cases). A person reviews the variances; with the right page, **Open in Analytics** shows the case in *Predicted vs
actual*.

Learning never changes a decision already made: a newly promoted model values only new cases, and retraining never
overwrites the evidence snapshot behind an earlier decision. Candidates are fitted, proposed and promoted in the
**Models** panel (Modeler, Agents); see [Approvals](approvals.md#6-model-promotion).

## 5. Declines and re-evaluation

- A decline sends the case to **Re-evaluate** with the approver's reason, and starts a new decision cycle. The
  earlier recommendation is on hold. Moving a case to *Re-evaluate* also starts any published decision workflows that
  are triggered by cases.
- The Planner (or Approver, or Admin) presses **Re-evaluate RT-…** (stage 6, "Rebuilds every route on fresh
  evidence"). Circularity values the case again: routes, gates, the business rules **as published now**, ranking and a
  new evidence snapshot. The toast says the new recommendation and what it was before.
- After re-evaluation the case is again *Awaiting approval* (or waits for review if no route passes every gate), and
  the Planner submits it again.
- Re-evaluation is the moment a newly published rule change reaches an existing case. Publishing a flow never changes
  a case by itself, and an approved decision keeps the routes it was approved with.

## 6. Worked example: RT-1048

Sign in as `ops`. Open **Decision Workbench → Returned assets** and click RT-1048 (*Start here*).

**What it is.** An industrial motor, Voltara, 55 kW, asset MTR-2041, returned by Customer A and now in Warehouse 1.

**Stages 1–5 are done.** The ten evidence items are ready (snapshot EVS-E7402581). Inspection graded it **B** with
36 months of engineering life.

**Stage 6, Decide.** Customer A's Site 3 needs a motor of this rating in 10 days, under contract replacement order
SO-48102, which accepts a certified refurbished motor; a new one would cost $12,000. The recommendation is
**Redeploy RT-1048** to Customer A · Site 3, predicted net **$9,600** (P10–P90 $8,371–$10,608):

| Line | Amount |
|---|---|
| Avoided equivalent purchase | $12,000 |
| Preparation and transfer | −$1,800 |
| Service exposure (30 months) | −$900 |
| Residual value adjustment | $300 |
| **Predicted net** | **$9,600** |

The other routes rank lower: *Sell + buy for Site 3* $4,800, *Re-lease + buy for Site 3* $3,600, *Recover parts + buy
for Site 3* $3,200, *Recover material* $310, *Responsible exit* −$60. *Sell parts externally* is excluded at the
*Demand fit* gate. Open *What-if and edge cases* and try *Demand cancelled* to see the ranking change; save it as a
scenario if you like. The decision does not change.

**Submit.** Press **Submit RT-1048 for review**. The toast confirms it; the case waits for the Approver.

**Stage 7, Approve.** Sign in as `approver`. RT-1048 appears in **Command Center → Approvals** (approval cards) and in
*Needs you*. Open it, press **Approve Redeploy RT-1048**, read the drafted rationale, tick "I reviewed evidence
snapshot EVS-E7402581 and the excluded routes", and press **Approve and send instruction**. The approval reference is
**APR-2026-10-3161** and the first instruction goes to order management.

**Stage 8, Execute.** The six redeploy steps run one after another as the simulated systems acknowledge them: the
order line SO-48102 is allocated (and the planned purchase is cancelled), the refurbishment work order, the transport
booking, the warehouse transfer, the proof of delivery, and the actual cost posting. Follow them in *Messages and
acknowledgements*.

**Stage 9, Outcome.** When the last step is acknowledged the case is *Closed*. Sign in as `finance` and press
**Confirm the outcome** on RT-1048 (also listed under **Command Center → Outcomes to confirm**). In the demo's
reference run the actual net is **$9,230** against $9,600 predicted: a variance of −$370.

**Stage 10, Reconcile and learn.** The *Lines* tab shows the variance per cost line; the *Learning record* says what
the models learn from it.

If the approver had declined instead, RT-1048 would show *Re-evaluate* with the reason, and `ops` would press
**Re-evaluate RT-1048** and submit again.

## 7. Good to know

- **You see only what your role allows.** A Planner sees their own customer's cases; a Warehouse Manager the cases in
  their warehouse. Acting on any other case is refused: "RT-… belongs to Customer B, a tenant you cannot see. Request
  tenant access first." or "RT-… is at Warehouse 2, outside your warehouse."
- **Each action happens once.** Submitting, approving or requesting twice is refused as a duplicate ("already
  submitted", "already sent"); resending an instruction never creates a second order or work order.
- **Agents help, people decide.** The agent drafts the rationale, prepares the packet and can run the case autopilot
  up to the approval; only a person approves. See [Approvals](approvals.md).
- **Every step is recorded.** The case's *History* tab and **Audit & Provenance** show who did what and when, and
  where each piece of evidence came from.
