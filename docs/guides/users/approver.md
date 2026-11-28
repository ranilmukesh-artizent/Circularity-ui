# Approver guide

**Sign in as** `approver`. Any password.

The Approver "approves or declines what Admin delegates: decisions and overrides, MCP server proposals and tenant
access". The Approver also approves and publishes changes to the business rules and promotes models, always as the
second person (maker-checker). You see **all customers**.

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures; *Proposals for you* when an agent holds one you may act on |
| Pulse | Key figures, Actions on me, **Approvals** (approval cards, the Approvals inbox and the tenant access granted), Portfolio charts, Actions to prioritise, Signals and capacity, Value realisation |
| Cases | Returned assets, Expected returns, Asset intelligence, the case pages |
| Analytics | All sections (Recovery waterfall, Pipeline, Route mix, Predicted vs actual, Model versions, Overrides, Engineering economics, Sustainability) |
| Modeler | Every organisation's decision flow, with Approve, Publish, Return to draft and Roll back; the **Models** panel |
| Connection Fabric | Event Streams and Conflict Queue (read only) |
| MCP & Tools | Tool catalog, Agent registry, Permission matrix, Call log and gate, As MCP client, Server proposals |
| Also | My Tasks, Alerts, Data pipelines and runs, Audit & Provenance, Reports, Data Checks, Settings |

Your Pulse is described as: "Decide what is waiting for you: treatment decisions, spend and sale terms, and
the requests Admin delegated to you."

## What you can do

| Action | Where | Depends on |
|---|---|---|
| Approve, override or decline a decision | Case, stage 7 (approval card) | Admin's *Decisions and overrides* delegation; your approval limit |
| Approve or decline a tenant access request, and choose when the access ends | Pulse → Approvals inbox | Admin's *Tenant access* delegation; never your own request |
| Revoke a tenant access grant | Pulse → Approvals (*Tenant access granted*) | Admin's *Tenant access* delegation |
| Approve or decline an MCP server proposal | MCP & Tools → Server proposals; Approvals inbox | Admin's *MCP server proposals* delegation; never your own proposal |
| Approve, publish, return or roll back a decision flow | Modeler | Never on a flow you made yourself |
| Approve a model promotion | Modeler → Models (**Approve promotion**) | Never a model you fitted or proposed yourself |
| Accept or reject an agent's proposal | Home → Proposals for you | The held action must be one you may run; reject only when the agent acted for you |
| Read the pilot report of an organisation | Analytics (pick the *Org unit*, then **Pilot report**) | |
| Request evidence, re-evaluate a case, save what-if scenarios | Case | |
| Check for the next acknowledgement during execution | Case, stage 8 | |
| Acknowledge notifications | Home, My Tasks, Alerts | |

All three delegations are on at the start. The Approvals inbox header says what is delegated to you now ("Delegated to
you by Admin: …"). Approving flows and promoting models does not depend on the delegations.

You cannot submit decisions, confirm outcomes, record inspections, edit rules, change access or manage sources.

## Your day

### 1. Open your queue

**Pulse → Approvals** shows:

- **Approval cards**: every submitted decision, ordered by value then deadline, each with the route, the value, who
  submitted it and the pre-approval check ("nothing to flag" or the risks). A card above your limit says "Above your
  approval limit: it escalates to Admin." **Approve…** and **Decline…** open the case; **Open** shows it.
- **Review all … in turn** lists every item with the instructions it would send. Each is still approved separately;
  "there is no unlisted 'approve all'".
- **Approvals inbox**: tenant access requests and MCP server proposals you may decide, and a button with the number
  of decisions awaiting approval. Below it, *Tenant access granted* lists the live grants.

**Out of office.** When Admin records an out-of-office delegate for you (Access → Identity and users), the delegate
covers your decisions between the dates, while *Decisions and overrides* is delegated. Your inbox then says "Out of
office until …: … approves or declines decisions on behalf of …. Whoever acts first completes the item.", and waiting
texts name the delegate ("Waiting for … (covering for the Approver)"). If you are the delegate, your inbox says "You
cover for … until …". You decide under your own limit, never your own submission, and the approval reads "Approved by
you on behalf of … under APR-…".

**Home → Needs you** and **My Tasks** list the same work.

### 2. Approve a decision

1. Open the case on stage 7 (**Approve**). Read the *Rationale*, *Checks* and *History* tabs, and stage 6 for the
   routes, evidence and what-ifs.
2. Press **Approve [route]**. The approval card opens with:
   - the recommendation, its expected net and the P10–P90 range;
   - **Route to approve** (the recommendation, or another eligible route as an override);
   - **Rationale** (required): the agent's draft. Edit it, or keep it. At least 15 characters;
   - your approval limit, and whether this decision is above it;
   - **Raw instruction that will be sent**;
   - **Spend authority (USD)**: "Instruction cannot commit beyond this amount", and the spend and sale terms;
   - the box "I reviewed evidence snapshot … and the excluded routes", which you must tick.
3. Press **Approve and send instruction**. The toast gives the approval reference (APR-…) and the system the first
   instruction went to. Execution starts (stage 8).

If the value (the larger of the route's net and the spend authority) is above your limit, the card escalates it to
Admin instead of approving. If you submitted the decision yourself, the server refuses unless Admin allows
self-approval.

### 3. Override

On the card, pick another route under **Route to approve**. The hint says "Override. A human-selected route replaces
the recommendation. Your rationale is recorded and counted in override analytics." The rationale is pre-filled with
the difference in predicted net; complete the reason. An excluded route cannot be approved: failed gates are
resolved by engineering and policy owners, never waived. **Edit route** on stage 7 opens the card with the route list
focused.

### 4. Decline

Press **Decline**, give a reason of at least 10 characters ("What has to change before you would approve?") and
confirm. Nothing is sent to any system; the case goes to *Re-evaluate* and the Planner sees your reason.

### 5. Decide access requests and MCP proposals

In the **Approvals inbox**, each request shows its kind, status, who asked, when, and the details.

- **Approve access** / **Approve proposal**, with an optional note. For tenant access, pick **Access ends**: *After
  8 hours*, *After 1 day*, *After 7 days*, *After 30 days* or *No end* (the default).
- **Decline**, with a required note (at least 5 characters): "Say what would change your decision."
- An approved tenant request lets the Planner see that customer's cases at once, without signing in again, until the
  access ends. An approved MCP server joins the MCP client list as approved; connecting it is a separate step for the
  Developer.
- A request or proposal you made yourself shows a disabled button: "You made this request, so another person must
  decide it."
- **Revoke** on a grant under *Tenant access granted* ends it now, with an optional note.

### 6. Approve a rule change (Modeler)

1. Open **Modeler**, pick the template and the organisation. A flow waiting for you shows *In review*.
2. Look at the canvas, **Checks** and **Impact** (**Simulate on open queue** shows which open decisions the draft would
   change and by how much).
3. **Approve** starts a shadow run: decisions keep using the published rules, and the draft decides beside them. The
   bar shows "Shadow: N decisions, X agree, Y differ" and the value difference.
4. When you are satisfied, **Publish**. Cases use the new rules from their next valuation.
5. Or **Return to draft** with a reason of at least 15 characters.
6. Later, **Roll back to v…** in *History* restores the version published before.

You cannot approve or publish a flow you edited yourself: "Maker-checker: you made these changes, so you cannot
approve them." This holds for everyone who saved or submitted the draft, not only the person who started it.

The Modeler's **Suggestions from overrides** shows rules that repeated overrides point to, checked and simulated.
You can read them; a Planner or Admin applies one to a draft, and it then comes to you for approval like any change.

### 6b. Approve a composition or a group map

**A composition** (Set up) arrives as one object: the pack changes, the accepted field mappings and the
agent settings. **Approve** applies them all together or none; you cannot approve one you made, and the checks run again
for you. If a step is wrong, choose the **Step**, optionally a **Node** (for example `stage:condition`), write the
reason (15 characters or more) and press **Send back**: the reason stays pinned to that step for its maker. You start the
canary on **Publish** after approving.

**A directory group map** (Access, Admin's Identity page) maps a directory group to a role and a site. One person saves
it and a different person approves it; the Admin role is never given through a group. See
[admin.md](admin.md#accounts-and-identity).

**A fraud hold on an automotive core** is released here with a reason (it needs the permission to approve decisions).
Planners and agents cannot release it.

### 7. Approve a model promotion

The **Models** panel at the foot of the Modeler lists the fitted models with their outcome count, error figures,
factors, who fitted them and their promotion status. A Planner or Admin fits a candidate and presses **Propose
promotion**. You press **Approve promotion** on a proposed candidate; it then values new cases, and the model it
replaces is retired. The button is disabled, with the reason beside it, on a model you fitted or proposed, or one not
proposed yet. See [Approvals](../approvals.md#6-model-promotion).

### 8. Act on an agent's proposal

When an agent holds an action that you may run, Home shows **Proposals for you**: what the agent proposes, the case,
why, the agent and the time. **Accept** runs it as you; **Reject** asks for a reason for the agent's owner. A
proposal from an agent that acted for you shows "Your agent's proposal: another person accepts it." instead of
**Accept**; you can only reject it. See [Approvals](../approvals.md#5-agent-proposals).

### 9. Approvals that the new packs hold for you

Some packs hold a decision for a person with a typed reason: a lot below the floor, an export-control check, a repair
approval, a customer credit that the ERP posted differently (Finance), or a standing policy limit. They show in your queue
like any decision. Everything else in this guide applies. An outside MCP client or an agent with credentials cannot
approve: its writes wait as proposals for a person.

### 10. Read a pilot report

In **Analytics**, pick an organisation under *Org unit* and press **Pilot report**. It shows what that organisation's
cases did (cases, decisions submitted and approved, the recommended net value, cases with business rules applied,
instructions held, the routes) and *What would have been sent* while it was in pilot mode. Admin switches pilot mode.
See [Approvals](../approvals.md#7-pilot-mode).

## What you cannot do, and why

- **Submit a decision**: the Planner prepares and submits; you check.
- **Approve above your limit**: it escalates to Admin.
- **Approve what Admin has not delegated**: if Admin switches off a delegation, those items leave your inbox.
- **Approve your own submission, your own rule change, or a model you fitted or proposed**: maker-checker.
- **Decide your own access request or MCP proposal**: another person decides it.
- **Approve an excluded route**: a failed gate is never waived.
- **Let an agent approve for you**: decisions are approved only in the approval card, by a person.
- **Accept a proposal from an agent that acted for you**: another person accepts it; you can reject it.

## Tips

- The pre-approval check on each card is a fast filter; open the case for the evidence behind it.
- An override is not a failure: it teaches the models. Write the reason the model could not see.
- When you decline, say exactly what would change your mind; the Planner re-evaluates with it.

See [Approvals](../approvals.md) for every approval type and [the case journey](../case-journey.md) for the stages.

## For the technical team

Approver permissions: approve.decisions, approve.mcp, approve.tenantAccess (each gated by Admin's delegation switch),
request, reeval, execSim, scenario, ack; plan 8 adds approve.flows (flows, model.promote, pilot report; not gated by
delegations). `access.revokeGrant` is allowed to Admin and to the Approver with the tenantAccess delegation. Not tenant-scoped. The Agents page and Access →
Organisation are not open to the Approver, so the Models panel is reached on the Modeler and the pilot report on
Analytics (org unit filter; `org.pilotReport` reads any unit for an account that is not tenant-scoped, the group too).
`proposal.accept` refuses the person an agent acted for (`own`, conflict); `flow.suggestions` is a read.
