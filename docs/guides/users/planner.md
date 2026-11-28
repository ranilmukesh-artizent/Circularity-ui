# Planner guide

**Sign in as** `ops` (or `planner.a`) for Customer A, `planner.b` for Customer B, `planner.c` for Customer C. Any
password.

The Planner prepares cases for **their own customer (tenant)**: closes evidence gaps, reviews the recommendation,
tries what-if scenarios and submits decisions for approval. The Planner also shapes the business rules their
organisation's decisions follow, in the Modeler, which another person approves.

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures; *Proposals for you* when an agent holds one you may act on |
| Command Center | Key figures, Actions on me, Handed off, Portfolio charts, Actions to prioritise, Signals and capacity |
| Decision Workbench | Returned assets, Expected returns, Asset intelligence, the case pages |
| Analytics | Recovery waterfall, Pipeline, Route mix, Predicted vs actual, Model versions, Overrides |
| Modeler | Your organisation's decision flow and business rules; the **Models** panel |
| Process Orchestration | Live run, Stages, Case run, Agents and services |
| Also | My Tasks, Alerts, Audit & Provenance, Reports, Data Checks, Settings |

You see only your own customer's cases. Every page, list and figure is filtered to it, and the server refuses any
action on another customer's case ("… belongs to Customer B, a tenant you cannot see. Request tenant access first.").
Your account menu lists the customers you can see.

Your Command Center is described as: "Prepare cases, close evidence gaps and submit decisions for review."

## What you can do

| Action | Where |
|---|---|
| Request missing evidence or an inspection | Case, stages 4–5 |
| Save and delete what-if scenarios | Case, stage 6 *What-if and edge cases*, or Full analysis |
| Re-evaluate a case after a decline | Case, stage 6 |
| Submit a decision for review | Case, stages 6–7 |
| Check for the next acknowledgement during execution | Case, stage 8 |
| Edit your organisation's business rules, submit them for approval, discard a draft | Modeler |
| Give your organisation its own decision flow | Modeler |
| Apply a rule suggested by repeated overrides to your draft | Modeler → Suggestions from overrides |
| Fit a candidate model and propose it for promotion | Modeler → Models |
| Accept or reject an agent's proposal (reject only, when the agent acted for you) | Home → Proposals for you |
| Request access to another customer | Account menu → Request tenant access |
| Acknowledge notifications | Home, My Tasks, Alerts |

## Your day

### 1. See what needs you

Open **Home → Needs you** or **My Tasks**. Cases appear there when their next step is yours: evidence to request,
decisions to submit, cases to re-evaluate. **Command Center → Actions on me** shows the same work ranked.

If an agent prepared something for you (for example the case autopilot held a *Submit for review*), Home shows
**Proposals for you**: what the agent proposes, the case, why, the agent and the time. **Accept** runs it as you, with
the same checks as if you pressed the button yourself; **Reject** asks for a reason for the agent's owner. The card is
not shown when nothing is waiting.

When the agent acted for you (it worked under your sign-in), the proposal is yours: it shows "Your agent's proposal:
another person accepts it." instead of **Accept**. You can still **Reject** it; another person who may run the action
accepts it (maker-checker).

### 2. Close an evidence gap

1. Open a case marked *Needs evidence* (for example from **Decision Workbench → Returned assets**).
2. On stage 4 or 5 the **What you do now** box names what is missing, for example **Request inspection**, and who owns
   it ("Sends the request to Inspection").
3. Press it. A request with a work order reference goes to the owner. The case shows *Requested* and waits.
4. When the Engineer records the result, the case is valued at once and, if a route is eligible, moves to *Awaiting
   approval*. You see it in *Needs you* again.

### 3. Review and submit a decision

1. Open a case *Awaiting approval*. Stage 6 (**Decide**) shows the recommendation.
2. Read the tabs: *Decision packet* (what would be approved), *Compare outcomes* (every route with its net value,
   range and gate results), *Why this outcome*, *Evidence*, *How it was predicted*, *Demand*.
3. Ask the assistant (Ctrl+J, Ask mode) anything you want explained, in plain words. **Run the agent on this case** (on
   the case Overview) starts a propose-only autopilot run: whatever it prepares is held for a person.
4. Press **Submit RT-… for review**. "The Approver gets it in their inbox and approves, edits or declines it in stage
   7." Nothing is sent to any system yet.

You cannot approve your own decision: Planners start with an approval limit of $0. If Admin raises it, you may approve
other people's submissions within your limit; your own only if Admin also allows self-approval.

### 4. Re-evaluate after a decline

When an approver declines, the case shows *Re-evaluate* with the approver's reason ("Review triggered: …"). Press
**Re-evaluate RT-…** on stage 6. Circularity rebuilds every route on fresh evidence, applies the business rules as
published now and ranks again; the toast says the new recommendation and what it was. Then submit again.

### 5. Follow execution

After approval, stage 8 lists the instructions to the enterprise systems and their acknowledgements. You handle
exceptions only. **Check for the next acknowledgement** refreshes the case. A step that passes its time limit shows
that it escalated.

## Your tools

### The Decision Workbench

- **Returned assets**: the cases of your customer with stage, recommendation and value. RT-1048 is marked *Start here*
  for `ops`.
- **Expected returns**: planning signals for assets not yet received.
- **Asset intelligence**: one asset's lifecycle, condition, product, economics, eligibility, data and related records.
- **The case**: the ten stages (see [the case journey](../case-journey.md)), the overview and **Full analysis**.

### What-if scenarios

On stage 6, **What-if and edge cases** lets you change the assumptions and see how the ranking moves:

- adjust the purchase price, prep and fees, service and market;
- presets: *Demand cancelled*, *Parts cost +30%*, *Resale price −20%*, *Certification shorter than demand*,
  *Critical part unavailable*, *Customer requires a new unit*;
- weight the business objectives behind the fit score: *Maximize net recovery*, *Minimize turnaround time*,
  *Minimize environmental impact*, *Preserve serviceability (redeploy)*.

**Save scenario** stores the assumptions on the case, named after what you changed. A scenario **never changes the
decision**; it is for understanding and for discussing with the approver.

### The Modeler (business rules)

The **Modeler** (left menu) shows the decision process of a template and an organisation: the flow of steps from
trigger to approval, the locked guardrails (the six gates and the core prediction, which never change) and the
business rules. Rules change which path a decision may take:

- **exclude** a route for cases in the rule's scope (it fails at *Policy & certification* with "Excluded by business
  rule …");
- **require** a route (every other route is set aside);
- **prefer** a route (it is ranked first when eligible).

If the rules would leave a case with no eligible route, they are waived for that case.

**Getting your own flow.** Pick the template (*Industrial returns*, *Tool fleet returns* or *Device recommerce*) and
your organisation at the top. At first your organisation uses the flow of the workspace above it ("Customer A uses
this flow from workspace"), which you cannot edit. Press **Give Customer A its own flow** to start your own copy.

**Editing.** Press **Add rule**, or select a step or rule on the canvas and change it in the **Inspector** (action,
path, scope, owner; **Delete rule**). Changes save automatically as a draft of the next version. The **Checks** panel
says what blocks a submit (for example a rule that breaks a guardrail) and what is only a warning (for example two
rules that conflict).

**The assistant.** The assistant is pinned in the column beside the canvas (it is the same assistant as Ctrl+J, with
the Modeler's flow and draft as its context). In **Change flow** mode, describe a change in plain words, for example
"Never send grade D motors to resale", and press **Propose**. It turns the sentence into a checked, simulated preview
card, drawn dashed on the canvas with its checks and its impact against your current draft. Applying the card puts it
into your draft (it is your own edit, recorded as "Proposed by the assistant: …") and offers **Undo** while the draft is
unchanged; dismissing drops it. A change that would touch a guardrail is refused in red. Nothing changes until you
apply it. **Set up** mode drafts a whole flow or composition from a description (this replaced the *Describe your
business* dialog), and **Ask** answers questions about the flow, for example why a rule is blocking.

**Impact.** **Simulate on open queue** runs your draft against the open decisions and shows which would change and
the value impact against the published flow.

**Suggestions from overrides.** **Find suggestions** reads the approvals and overrides of the decisions this flow
made. When approvers keep overriding one group of assets to the same path, it suggests a rule, for example "3 of 4
motor decisions overridden to …", checked and simulated like an assistant proposal. **Apply as draft** puts it into
your draft only; you still submit it yourself, and another person approves it. Nothing changes until you apply one.

**Submit.** **Submit for approval** sends the draft to an Approver (or Admin). You cannot approve or publish your own
change (maker-checker). Everyone who saved or submitted the draft counts as its maker, so none of them approves or
publishes it. **Discard draft** goes back to the published flow. *History* shows earlier versions and the
log of every change.

After an approver approves, the flow runs in **Shadow** beside the published one; after they publish, cases use it
from their **next valuation**. To apply it to a case already *Awaiting approval*, the case must be valued again
(for example after a decline and **Re-evaluate**). See [Approvals](../approvals.md#2-decision-flow-and-business-rule-changes).

**Models.** The **Models** panel at the foot of the Modeler shows the base model, the active calibration per template
and the fitted models (outcomes, error figures, factors, who fitted them, promotion status). Pick the **Template** and
press **Fit a candidate** to fit one on the confirmed outcomes; then **Propose promotion**. A different person (an
Approver or Admin) approves the promotion; you cannot approve a model you fitted or proposed. See
[Approvals](../approvals.md#6-model-promotion).

### Compose: set up a pack for an organisation (five steps)

**Compose** (in the Modeler; the assistant's Set up mode opens it) takes one pack to a live flow for one organisation
as a single object that a different person approves. The steps show their state (to do, done, sent back):

1. **Describe:** say in plain words what the business does. The agent shows what it read (drafted by a model when one
   is available, always checked by the rules) and drafts the changes to the pack as a list of typed operations. The
   rules refuse a change that loosens a locked guardrail or skips a compliance check, and say why.
2. **Mapping:** each system the pack needs is listed with its status. A system with no adapter yet is added **from the
   adapter registry**; the field mapping uses the suggestions and the five choices ([developer.md](developer.md)). A
   field still waiting for its system owner blocks the submit.
3. **Agents:** per stage, how far the agent may go and its confidence threshold (0.65 to 0.85), with value and bulk
   limits. Outside that range the submit is refused.
4. **Approve:** you press **Submit**; the page lists what blocks it, if anything. A different person approves, or sends
   a step back with a reason ([approver.md](approver.md)). A sent-back step shows the reason pinned to it, and the node
   it is about.
5. **Publish:** after approval, a person with the right starts a canary in one region at a share of cases; the **replay
   report** (route mix, straight-through rate, approvals and exceptions a day, uplift with its band) and the rollout
   state show on the same step. See [executive.md](executive.md) for reading them.

A **test run** card runs sample cases through the draft without saving anything.

**Decision tables.** For packs with per-market rules (the tool fleet's service desk), **Tables** in the Modeler holds a
rate card and a decision table per market. Pick the market and a version, change the values or the rows (first match
wins), **Test**, save a draft and submit it. A different person approves it (maker-checker); each version has the dates
it is in force. Tables are data checked by code, not free text. A table can also go out in steps (an Approver starts it):
its canary sends a
share of one market's cases to the new version, and compares them with the rest at a standard quote, which is the
first other market of the pack in the same currency (for example Germany when the canary is in France). A table canary
needs a finished replay of the flow first, has no automatic pause (pause it yourself) and cannot be taken straight to
everyone; roll it back, or replace it with the next version.

### Cases of the other industries

The same Decision Workbench and **My Tasks** show cases of the other packs ([README](README.md#more-industries-plan-9)):
one case per VIN, serial, tag or device. Each pack has its own gates, and a gate that lacks evidence holds the case, or
the whole batch it came in, until the evidence arrives. A few examples you may meet: title or lien on a vehicle,
an open recall, a configuration wipe or export control on network equipment, a decontamination record or service date on
a medical device.

**Downstream vendor.** Where a route sends the asset to a vendor (a recycler, a parts supplier), the case shows the
vendor chosen and why. A vendor qualifies while its certificate is approved and its valid-to date is on or after the
decision date; otherwise the case says, for example, that the certificate expired on a date, or that none is on file,
and picks the best vendor that does qualify. A replay as of an earlier date judges on that date.

**Close.** Some packs add a last step: retire or transfer the asset in the ERP, record the lease residual, credit a
customer, or wait for the treatment facility's reporting evidence. The case stays *executing* until they are done; see
[finance.md](finance.md) and [engineer.md](engineer.md) for who answers.

### Requesting access to another customer

If you need to plan across customers (for example a shared pool), open the account menu (top right) and press
**Request tenant access**. The dialog shows the extra customers you can already see and when each grant ends, your
requests with their status, and a form: pick the **Tenant**, give a **Reason** of at least 10 characters ("Why you
need to see this tenant's cases.") and press **Send request**. An Approver or Admin decides it and chooses when the
access ends. Once approved, the other customer's cases appear in your lists at once, without signing in again. The
access ends on its own at its end date, or when Admin or the Approver revokes it.

## What you cannot do, and why

- **Approve, override or decline** decisions: a different person checks every decision. (Unless Admin raises the
  Planner approval limit.)
- **Confirm outcomes**: Finance owns the actual numbers.
- **Record inspection results**: the Engineer owns technical eligibility.
- **Approve or publish your own rule change, or promote a model**: maker-checker, and promoting needs an Approver or
  Admin.
- **Accept a proposal from an agent that acted for you**: another person accepts it; you can reject it.
- **Edit the workspace flow or another customer's flow**: you edit only your own organisation's flow.
- **See the Connection Fabric, MCP & Tools, Agents or Access**: those belong to integration and administration.
- **Waive a failed gate**: nobody can; engineering and policy owners resolve the cause.

## Tips

- Start with RT-1048: follow it through every stage before working on other cases.
- The agent's drafted rationale and the pre-approval check help the approver; make sure the packet is complete
  before you submit, because a decline starts a new cycle.
- Simulate a rule change on the open queue before you submit it; the approver sees the same impact.
- Every action you take is in the audit log with your name.

## For the technical team

Planner permissions: submit, request, reeval, execSim, scenario, requestTenant, ack; plan 8 adds manageFlows (Modeler
edit, model.fit, model.propose) and openCases (no screen path for a Planner yet). Tenant-scoped; a tenant grant may
have an end (`expires_at`) and reaches the open session through the live stream. Pages: home, command, tasks, alerts,
product, analytics (no pool), modeler, orchestration, audit, reports, checks, settings.
