# Approvals: who approves what

Circularity is built so that a person decides. This guide lists every approval in the product: who asks, who
approves, where in the app, and what happens after. It also explains approval limits, delegations, the
maker-checker rule and what agents may never do.

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## Contents

- [Summary table](#summary-table)
- [The ground rules](#the-ground-rules)
- [1. Decisions (case approval)](#1-decisions-case-approval)
- [2. Decision flow and business rule changes](#2-decision-flow-and-business-rule-changes)
- [3. Tenant (customer) access requests](#3-tenant-customer-access-requests)
- [4. MCP server proposals](#4-mcp-server-proposals)
- [5. Agent proposals](#5-agent-proposals)
- [6. Model promotion](#6-model-promotion)
- [7. Pilot mode](#7-pilot-mode)
- [8. Admin's settings: limits, self-approval, delegations](#8-admins-settings-limits-self-approval-delegations)

## Summary table

| What | Who requests or makes it | Who approves | Where in the app | What happens after |
|---|---|---|---|---|
| A decision on a case | Planner (or Admin) submits | Approver (if Admin delegates decisions), Admin; the Approver's out-of-office delegate while that delegation is in force; a Planner only if Admin gives Planners a limit above $0 | The case, stage 7 *Approve*; **Command Center → Approvals** (approval cards) | Approve or override: an approval reference is created and the instructions go to the enterprise systems. Decline: back to *Re-evaluate*, nothing sent |
| A decision above the approver's limit | The approver who tries it | Admin | The approval card escalates it | An escalation goes to Admin |
| A decision flow (business rules) change | Planner or Admin edits a draft and submits it | Approver or Admin, **never a maker** (anyone who saved or submitted the draft) | **Modeler** | Approve: shadow run beside the published flow. Publish: cases use it from their next valuation. Return to draft, or roll back later |
| Access to another customer (tenant) | Planner, in the account menu's **Request tenant access** | Approver (if Admin delegates tenant access), Admin; **never the requester** | **Command Center → Approvals** (Approvals inbox); **Access & Governance → All requests** | Approved: the Planner sees that customer's cases at once, until the chosen end or a revoke. Declined: the note tells them why |
| A new MCP server | Developer or Admin proposes | Approver (if Admin delegates MCP proposals), Admin; **never the proposer** | **MCP & Tools → Server proposals**; Approvals inbox; All requests | Approved: the server joins the MCP client list as *approved · not yet connected*. Connecting it is a separate step |
| An agent's held action | An agent with autonomy *Propose for a person* | A person who holds that action's own permission (and may see the case), **never the person the agent acted for** (they may reject it) | **Home → Proposals for you**; **Agents → Proposals waiting for you** | Accept: the action runs as that person. Reject: closed with the reason |
| A calibration model | Admin or Planner fits a candidate and proposes it | Approver or Admin, **never the person who fitted it or proposed it** | **Models** panel on the Modeler and on the Agents page | The candidate becomes active and values new cases; the old model is retired |
| Pilot mode for an organisation | Admin switches it | (Admin's own decision) | **Access & Governance → Organisation** (*Pilot mode* switch, **Pilot report**); **Analytics** (**Pilot report** for the chosen *Org unit*) | Decisions run as usual, but no instruction is sent to any enterprise system |
| Delegations, limits, self-approval, agent autonomy, kill switches, organisation tree | Admin | (Admin's own decision) | **Access & Governance** | Takes effect on the next request; recorded in the audit log |

## The ground rules

**A person presses the final button.** Approving, overriding or declining a decision, approving, returning,
publishing or rolling back a rule change, proposing or promoting a model, accepting an agent's proposal (never the
person the agent acted for), deciding an access request
and every change to access are done only by a signed-in person.

**What agents may never do.** The agents (Ask Circularity, the MCP tools, the case autopilot, the workflow builder
and any registered external agent) act as the person they work for and never with more rights. They can read, draft
and prepare. The server refuses, whatever the agent's settings, any attempt by an agent to:

- approve, override or decline a decision, or confirm an outcome ("Decisions are approved, overridden or declined
  only in the approval card, by a person.");
- approve, return, publish or roll back a decision flow ("Decision flows are approved, returned, published or rolled
  back only by a person.");
- propose or promote a model ("Models are proposed for promotion only by a person.", "Models are promoted only by a
  person.");
- accept or reject an agent's proposal;
- register an agent, or change access, the organisation tree, pilot mode, the agents themselves, MCP servers, source
  connections, or publish, pause or delete a workflow.

The server refuses these however the agent's call arrives (Ask, the MCP tools, an agent run or a direct call), even
when it claims a person confirmed it. Reading stays open to agents, for example "Who can approve above $5,000?".

The Access page lists the hard rules that are never configurable, among them: the agent cannot waive a failed gate;
the agent cannot approve, publish, change access or change live source connections; nothing is sent to an enterprise
system without an approval reference.

**Maker-checker.** Nobody approves their own change:

- a decision flow change is approved and published by a different person from everyone who saved or submitted the
  draft ("Maker-checker: you made these changes, so you cannot approve them.");
- an agent's proposal is accepted by a different person from the one the agent acted for; that person sees it marked
  "Your agent's proposal: another person accepts it." and can only reject it;
- a model is promoted by a different person from the one who fitted it and from the one who proposed it ("Maker-checker:
  you created this model, so you cannot promote it.", "Maker-checker: you proposed this model, so you cannot promote
  it.");
- a tenant access request or an MCP server proposal is decided by someone other than the person who made it, whatever
  the self-approval setting ("You made this request, so another person must decide it.");
- a decision you submitted is approved by someone else ("You submitted RT-…, so another person must approve it. Admin
  can allow self-approval within a limit."), unless Admin turns self-approval on.

**Everything is recorded** in the audit log: who asked, who decided, when, and the reason or note.

## 1. Decisions (case approval)

**Who can approve.** The permission is *approve decisions*:

- **Admin**, always.
- **Approver**, while Admin has the *Decisions and overrides* delegation switched on (it is on at the start).
- **Planner**, only if Admin raises the Planner approval limit above $0 (it starts at $0, which means Planners cannot
  approve). Self-approval rules still apply.
- **The Approver's out-of-office delegate**, while that delegation is in force (see
  [section 8](#8-admins-settings-limits-self-approval-delegations)).

**Approval limits.** Each approver has a dollar limit; the value checked is the larger of the route's net value and
the spend authority entered on the card. At the start: Approver unlimited, Admin unlimited, Planner $0. Admin changes
them in **Access & Governance → Approval limits**. Above your limit the card says "this decision is above it and
escalates" and, when you confirm, sends an escalation to Admin instead of approving.

**Worked example (RT-1048).**

1. `ops` (Planner · Customer A) opens RT-1048 and presses **Submit RT-1048 for review**.
2. `approver` sees it in **Command Center → Approvals** as an approval card (*RT-1048 · Redeploy RT-1048*, $9,600,
   "submitted by Planner · Customer A") and in *Needs you*. **Approve…** opens the case.
3. On stage 7, **Approve Redeploy RT-1048** opens the approval card: the recommendation and its range, the agent's
   drafted rationale (edit it or keep it), your limit, the raw instruction, spend authority and terms.
4. Tick "I reviewed evidence snapshot EVS-E7402581 and the excluded routes" and press **Approve and send instruction**.
   The toast says "APR-2026-10-3161 created. Instruction handed to OMS."
5. Execution starts (see [the case journey](case-journey.md#stage-8-execute)).

**Override.** On the card, pick another eligible route under *Route to approve*. The rationale is pre-filled with
"Override: … instead of … (… less predicted net). Reason:"; finish the reason. Overrides are counted in
**Analytics → Overrides**. An excluded route can never be approved.

**Decline.** **Decline** asks for a reason of at least 10 characters ("What has to change before you would approve?").
Nothing is sent to any system; the case moves to *Re-evaluate* and the Planner sees your reason.

**Many at once.** **Review all … in turn** lists every submitted decision with the instructions it would send. Each is
still approved on its own, within your limit; there is no "approve all".

**Notes.**

- The approval card works on any case that is *Awaiting approval*; normally the Planner submits first so the case
  carries "Submitted for review by …".
- A case can be approved only once per decision cycle; after a decline and re-evaluation it is a new cycle.

## 2. Decision flow and business rule changes

Each organisation unit uses a **decision flow**: the template's steps, its locked guardrails, and the business rules
that exclude, require or prefer a route. Flows are edited in the **Modeler** (see the
[Planner guide](users/planner.md#the-modeler-business-rules)).

**Who.**

| Step | Who | Permission |
|---|---|---|
| Edit a draft, submit it, discard it, give an organisation its own flow | Planner (own organisation only), Admin | manage flows |
| Approve, publish | Approver, Admin, never a maker | approve flows |
| Return to draft, roll back | Approver, Admin | approve flows |
| View the Modeler | Planner, Approver, Executive (read only), Admin | Modeler page |

The Approver's right to approve flows does not depend on the delegation switches.

**Lifecycle.** The status pill shows *Draft*, *In review*, *Shadow* or *Published*, with the version.

1. **Draft.** The first edit to a published flow makes a draft of the next version. Everyone who saves a change to
   the draft or submits it is a **maker** of that version, until it is published, discarded or rolled back. Changes
   save automatically; **Checks** shows what blocks a submit. **Simulate on open queue** shows which open
   decisions the draft would change and the value impact.
2. **Submit for approval** (the maker). Refused while a blocking check remains: "Fix the blocking checks before
   submitting."
3. **Approve** (a person who is not a maker). The flow enters **Shadow**: every case valued while it is in shadow is also
   decided with the draft's rules on a copy, and the bar shows "Shadow: N decisions, X agree, Y differ" with the value
   difference. Live decisions are unchanged.
4. **Publish** (a person who is not a maker). The draft becomes the published version; the version it replaces is kept in
   *History*. Cases use the new rules from their next valuation (a new case, a recorded inspection, a
   re-evaluation). Publishing never changes a case by itself, and approved decisions keep their routes.
5. **Return to draft** (in review or shadow) needs a reason of at least 15 characters.
6. **Roll back to v…** (an approver, in *History*) restores the version published before the current one.

**Worked example.** `ops` opens **Modeler**, picks *Industrial returns* and *Customer A*, presses **Give Customer A its
own flow** (Customer A then stops inheriting the workspace flow), and asks the assistant "Never send grade D motors to
resale". The proposal is drawn dashed on the canvas with its checks and impact; **Approve · AI applies it** puts it
into ops's draft (this is ops's own edit, not an approval). ops presses **Submit for approval**. `approver` opens the
same flow, reviews checks and impact, presses **Approve** (shadow starts), later **Publish**. If `ops` tried to approve
it, the server would refuse with the maker-checker message. So would it if `admin` had also saved a change to the
draft before it was submitted: Admin would then be a maker too, and only `approver` could approve it.

**Suggestions from overrides.** In the Modeler, **Find suggestions** (in *Suggestions from overrides*) reads the
approvals and overrides of the decisions the flow made and suggests a rule where approvers keep overriding one group of
assets to the same path, checked and simulated like an assistant proposal. Planners, Approvers and Admin can read
them. **Apply as draft** (Planner or Admin) saves the rule into the draft as that person's own edit; it never submits
or approves anything, so the change then goes through the steps above.

## 3. Tenant (customer) access requests

A Planner sees only their own customer. To plan across customers (for example a shared motor pool), a Planner asks
for access to another customer (tenant).

- **Who asks:** Planner (Admin has the permission too, but already sees everything). Open the account menu (top
  right) and press **Request tenant access**. The dialog shows *Extra tenants you can see* (your live grants and when
  each ends), *Your requests* with their status, and a form: pick a **Tenant** you cannot see yet, give a **Reason**
  of at least 10 characters and press **Send request**. A second pending request for the same customer is refused;
  that customer shows "request waiting" in the list.
- **Who decides:** Approver while Admin delegates *Tenant access*, and Admin. Nobody decides their own request: the
  **Approve access** button is disabled with "You made this request, so another person must decide it."
- **Where:** **Command Center → Approvals** (the *Approvals inbox*: "Tenant access requests and MCP server proposals
  appear here"), and **Access & Governance → All requests** for Admin.
- **Deciding:** **Approve access** or **Decline**. A note is optional for approval and required (at least 5
  characters) for a decline: "Say what would change your decision." When you approve, pick **Access ends**: *After 8
  hours*, *After 1 day*, *After 7 days*, *After 30 days* or *No end* (the default: access lasts until it is revoked).
- **After:** approved, the Planner sees that customer's cases (and every unit below it in the organisation tree) at
  once, in the session already open, without signing in again. Access ends on its own when its time is up. Declined,
  the requester sees the note.
- **Revoke:** Admin, or the Approver while Admin delegates *Tenant access*, presses **Revoke** on a grant under
  *Tenant access granted* (below **All requests** on the Access page, and below the Approvals inbox), with an optional
  note. The Planner loses access at once; open pages lock.

**Worked example.** The demo starts with REQ-304: Planner · Customer B asks for Customer A, because "Customer A and
Customer B share the Site 3 motor pool". Sign in as `approver`, open **Command Center → Approvals**, press **Approve
access** on REQ-304, add a note, choose **Access ends** (for example *After 7 days*) and press **Approve**. Planner ·
Customer B can now open Customer A's cases, and sees the end under *Extra tenants you can see*.

## 4. MCP server proposals

An MCP server is a set of tools an outside system offers to agents. A new one is reviewed before any agent can use it.

- **Who proposes:** Developer and Admin, with **MCP & Tools → Server proposals → Propose MCP server**: server name,
  vendor or owner, purpose (at least 10 characters), the tools it exposes, access (*Read only* or *Read and write*),
  and the data it touches (categories only, never real records). A second pending proposal with the same name is
  refused.
- **Who decides:** Approver while Admin delegates *MCP server proposals*, and Admin. Nobody decides their own
  proposal, whatever the self-approval setting: **Approve proposal** is disabled with "You made this request, so
  another person must decide it." When Admin proposes a server, the Approver decides it.
- **Where:** **MCP & Tools → Server proposals**, the Approvals inbox, **Access & Governance → All requests**.
- **After:** approved, "The server joins the MCP client list as approved. Connecting it is a separate step."
  Declined, the note says what to change.

**Worked example.** REQ-301 (from the Developer) proposes a *Fleet telematics MCP server* with read-only tools
`telemetry.hours` and `telemetry.duty_cycle`, so condition predictions can use measured duty. The approver opens
**MCP & Tools → Server proposals** and presses **Approve proposal**. For contrast, REQ-303 shows a declined one: "It
books shipments without a human approval step. Resubmit with the approval gate."

## 5. Agent proposals

Admin registers each agent with an autonomy: *Read only*, *Propose for a person* or *Act within its tools*. When an
agent set to **Propose for a person** tries to change something, it does not run: the call is held as a proposal for
a person.

- **Who decides:** a person who holds the held action's own permission and, for a case, may see that case. For
  example, a held *Submit for review* needs someone with the submit permission for that customer. The person the
  agent acted for (the agent worked under their sign-in, or they started its run) never accepts it: maker-checker.
- **Where:** **Home → Proposals for you** ("An agent prepared these. Nothing runs until you accept."), for every
  account that may act on a pending proposal. Each shows what the agent proposes, the case, why, the agent and the
  time. The card is not drawn when nothing is pending. Admin and Developer also see the proposals on **Agents →
  Proposals waiting for you**.
- **Accept** runs the held action as you, through the same checks as if you had pressed the button yourself. A held
  approval, override or decline can never be accepted this way: decisions are approved only in the approval card.
- **Your own agent's proposal** is still listed to you, with "Your agent's proposal: another person accepts it." in
  place of **Accept**. You can reject it; if you try to accept it another way, the server refuses with the
  maker-checker message.
- **Reject** asks for a short reason for the agent's owner ("Why not? The agent's owner sees this."; at least 5
  characters).
- **After:** if the proposal came from an agent run, the run continues (or stops, if rejected).

**Worked example (case autopilot).** `admin` opens **Agents**, picks an agent under *Runs*, types `RT-1048` and
presses **Start case autopilot**. The autopilot reads the evidence, requests missing evidence if any, re-evaluates if
needed, and submits the decision. If the agent's autonomy is *Propose for a person*, the submit is held: the run shows
*waiting* with a link to the proposal. `ops` (or any account that may submit for Customer A) sees it on Home under
*Proposals for you* and accepts it; the run then waits for the approval, which a person gives in the approval card as
in [section 1](#1-decisions-case-approval). `admin`, who started the run, sees the same proposal marked as their own
agent's and can only reject it.

## 6. Model promotion

Circularity learns from confirmed outcomes. A **calibration model** adjusts the predictions of new cases using the
difference between predicted and actual on past outcomes.

Promotion takes two steps after the fit: a proposal, then an approval by a different person.

- **Where:** the **Models** panel, at the foot of the **Modeler** and on the **Agents** page. It shows the base model
  and the active calibration per template, and the fitted models: outcome count, the error of the current model and
  of this model, the factors, who fitted it and when, and the promotion status (*Not proposed*, *Proposed by …*,
  *Approved by …*).
- **Fit a candidate:** Admin or Planner (manage flows). Pick the **Template** and press **Fit a candidate**. The
  candidate records its error against the active model on the same outcomes. It is not used until promoted.
- **Propose promotion:** Admin or Planner (manage flows) presses **Propose promotion** on a candidate.
- **Approve promotion:** Approver or Admin (approve flows), never the person who fitted it and never the person who
  proposed it. A candidate that is not proposed yet cannot be approved ("Propose … for promotion first.").
- A disabled button shows the server's reason beside it.
- An agent never proposes or promotes a model.
- **After:** the candidate becomes active, the model it replaces is retired, and only **new** cases are valued with
  it; cases already open keep their routes. A confirmed case's *Learning record* (stage 10) says whether a candidate
  is awaiting promotion.

## 7. Pilot mode

Pilot mode lets an organisation try Circularity without touching its enterprise systems.

- **Who:** Admin only (manage organisations). It applies to the unit and everything below it.
- **Where:** **Access & Governance → Organisation**, the *Pilot mode* column: a switch per unit (*On* / *Off*). A
  unit below a pilot unit shows "On, through <parent>"; switch it at that parent.
- **What happens:** cases are decided, submitted and approved as usual, but no instruction is sent: each one is held
  with "Pilot mode: not sent to …" and acknowledged by the simulation, so the case still runs to the end. Pilot mode
  never sends.
- **Pilot report:** **Pilot report** on the unit's row. It gives cases, decisions submitted and approved, the total
  recommended net value, cases with business rules applied, instructions held and the recommended routes, then *What
  would have been sent*: each held instruction with its case, step, instruction, target system and time. The figures
  cover the unit and every unit below it. Admin and Approver may read it for any unit, the workspace at the top too;
  an account limited to some customers reads only units within them. The Organisation section is shown to Admin only;
  both also find **Pilot report** in **Analytics** after picking an *Org unit*.
- Agents can never switch pilot mode.

## 8. Admin's settings: limits, self-approval, delegations

All in **Access & Governance**, Admin only; every change is recorded.

- **Approver delegations** (*What the Approver may decide; Admin can always decide*): three switches, all on at the
  start: *Decisions and overrides*, *MCP server proposals*, *Tenant access*. Switching one off takes that approval away
  from the Approver; Admin can still decide.
- **Approval limits** (*A decision above the approver's limit escalates to Admin*): a dollar limit per role; empty
  means unlimited. "$0 means Planners cannot approve. Raise it to let them approve within the limit."
- **Self-approval:** off at the start. When on, the person who submitted a decision may approve it within their limit.
- **Out-of-office delegation** (in *Identity and users*): a delegate who already holds the Approver role, with *From*
  and *Until* dates. It counts while Admin delegates decisions to the Approver, the workspace day is within the dates,
  and the delegate signs in to an account that holds the Approver role. Then:
  - waiting texts and the Approvals inbox name the delegate ("Waiting for <delegate> (covering for the Approver)");
    the delegate's inbox says "You cover for … until …";
  - the delegate may approve or decline decisions in the Approver's place, under the delegate's own limit and the
    no-self-approval rule. The approval reads "Approved by <delegate> on behalf of <Approver> under APR-…", and the
    audit log records on whose behalf;
  - whoever acts first completes the item.

  A delegate without a sign-in account (the demo's seeded deputy) is recorded only.
- **Agent autonomy:** how far the agent may go per role and type of action (*Off*, *Suggest*, *Prepare*, *Act and
  notify*), capped by the action's risk: approving, overriding or declining decisions, confirming outcomes, publishing
  workflows, changing source connections and changing access are capped at *Prepare*, so a person always presses the
  final button.
- **Agents and kill switches:** stop or start any agent; a stopped agent does nothing, not even read. Run limits cap
  how many actions one agent run may take and how many items one bulk plan may hold.

See the [Admin guide](users/admin.md) for the step-by-step.
