# Admin guide

**Sign in as** `admin`. Any password.

Admin has "every permission on every page and tenant, plus accounts, Approver delegations and access requests". Admin
also owns the organisation tree, approval limits, agent autonomy and the agents themselves. Admin's Pulse is
described as: "Identify, prioritise and act on lifecycle opportunities to maximise economic, operational and
sustainability outcomes."

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected. The identity provider shown in Access is an example with placeholder values.

## What you can see

Every page and every section, for every customer: Home, Pulse (all sections, including Approvals, Outcomes
to confirm and Integration health), My Tasks, Alerts, Cases, Analytics, the Modeler, Reports, Data
Checks, the Connection Fabric (all tabs), MCP & Tools (all sections), Data pipelines and runs, **Agents**, Audit &
Provenance, **Access & Governance** and Settings.

## What you can do

Everything the other roles can do (see their guides), and in addition:

| Action | Where |
|---|---|
| Accounts and roles; identity provider sync, role source, group-to-role mapping, directory removals | Access & Governance → Accounts and roles, Identity and users |
| The organisation tree: add units, move them, rename them | Access & Governance → Organisation |
| Export and import an organisation's configuration pack | Access & Governance → Organisation |
| Pilot mode for an organisation; the pilot report | Access & Governance → Organisation (the report also on Analytics, for the chosen *Org unit*) |
| Approver delegations | Access & Governance → Approver delegations |
| Decide tenant access requests and MCP proposals (not your own); revoke tenant access | Access & Governance → All requests; Pulse → Approvals |
| Agent autonomy per role and action type | Access & Governance → Agent autonomy |
| Approval limits, self-approval, agent run limits | Access & Governance → Approval limits |
| Stop or start any agent (kill switch) | Access & Governance → Agents and kill switches; Agents |
| Register an agent; change an agent's autonomy, tools and organisation scope; start the case autopilot on a case | Agents |
| Accept or reject an agent's proposal (reject only, when the agent acted for you) | Home → Proposals for you; Agents |
| Fit a candidate model, propose it, approve another person's proposal | Models panel (Agents, Modeler) |
| Out-of-office delegation for the Approver | Access & Governance → Identity and users |

The same rules bind you as everyone else: you cannot approve or publish a rule change you made (or saved or submitted
along the way), or promote a model you fitted or proposed (maker-checker); you cannot accept a proposal from an agent
that acted for you; you cannot decide your own tenant access request or MCP proposal; you cannot approve a decision
you submitted unless self-approval is on; you cannot approve an excluded route.

## Your tasks

### Accounts and identity

**Accounts and roles** lists every account with its role, the tenants it sees, the page it lands on and what the role
does.

**Identity and users** shows how people arrive from the identity provider:

- **Sync from directory** reads the users and groups again.
- **Role source**: *App Roles* (recommended: "App Roles keep working when a group is renamed and avoid group-overage
  limits") or *Directory groups*.
- **Role mapping**: for each group (or App Role), pick the **Role** and the **Site or warehouse**. The account changes
  from the next request on (for example, mapping a group to Warehouse Manager locks it to a warehouse). The Admin role
  is "assigned directly, never through a group" and cannot be changed here.
- **Users**: there is no Add user form; users are added in the identity provider and appear after the next sync. A
  user removed in the directory loses access at the next provisioning sync (**Apply directory removal** shows it for
  the demo's deputy planner).
- **Out-of-office delegate**: pick a user who already holds the Approver role, with *From* and *Until* dates, and
  **Save delegation**. While *Decisions and overrides* is delegated, the workspace day is within the dates and the
  delegate signs in to an account that holds the Approver role, the delegate approves or declines decisions in the
  Approver's place, under the delegate's own limit and the no-self-approval rule. Waiting texts name the delegate
  ("Waiting for … (covering for the Approver)"), the approval reads "Approved by … on behalf of … under APR-…", and
  whoever acts first completes the item. A delegate without a sign-in account (the demo's deputy) is recorded only.
  See [Approvals](../approvals.md#8-admins-settings-limits-self-approval-delegations).

**Organisation sign-in, group mapping, SCIM and test a user (plan 9).** The demo signs in with any ID and password. A
company that signs people in from its own directory (OpenID Connect) sets the `DI_OIDC_*` settings on the API service
([trial START-HERE](../../../trial/START-HERE.md#organisation-sign-in) says which). Then:

- **Group map:** each directory group is mapped to a role and a site. You save a row and a different person (an
  Approver or another Admin) approves it, so a map never takes effect on one person's word. The Admin role is never
  given through a group. When a new row for a group is approved, the group's previous approved row retires.
- **SCIM:** the directory can provision users at `/scim/v2` with a bearer secret kept as the directory source's webhook
  secret. A delete or `active=false` deactivates the user and never deletes anything; SCIM cannot create or change a
  group or give a role (the approved group map does).
- **Role matrix and Test a user** (Access page): the matrix shows every permission by role. **Test a user** shows what
  a given account, with its groups, would see and be allowed to do, without signing in as them.

**Adapter registry and system owners.** A connection made from the registry starts in the test environment and read
only. As Admin you hold the right to answer for any system owner: in **My Tasks**, a request for production access or for
write-back shows the system, the access asked for and the requester's note; **Approve** or **Decline** with a reason.
Nobody approves their own request. A person other than the drafter releases a new connector entry
([developer.md](developer.md)).

### The organisation tree

**Organisation** shows the tree: *Workspace* at the top, with Customer A, B and C below it at the start. A case
belongs to a customer or company unit, and **a tenant grant on a unit covers every unit below it**.

- **Add unit**: pick the *Parent*, the *Kind* (group, segment, company, site or customer) and a *Name*.
- **Move** a unit by changing its parent in the table. Moving a unit "changes who sees its cases": grants on the new
  parent now cover it.
- **Rename** a unit: type the new name and **Save**. Its id stays, so grants and cases keep pointing at it.
- New units can have their own decision flow (Modeler) and sources bound to them (Connection Fabric: the *Org unit*
  field in the Connect dialog, and on a connected source's drawer under *Configuration*).

**Configuration packs.** A pack holds a unit's source settings, field mappings, workflows and decision flows. It never
holds passwords, keys or tokens.

- **Export pack** downloads `org-pack-<unit>.json`.
- **Import pack** on the unit that receives it: choose the JSON file. A preview shows what will be created (the
  sources with their new ids, the field mappings, the workflows as drafts, the decision flows, and the credentials
  still needed) before anything changes. Press **Import**. Sources arrive disconnected without credentials; enter
  them and reconnect in Connection Fabric. Workflows and decision flows arrive as drafts; nothing is published.

**Pilot mode.** The *Pilot mode* column has a switch per unit. In pilot mode, decisions run as usual, but no
instruction is sent to an enterprise system; each one is held with "Pilot mode: not sent to …". It covers the unit and
every unit below it; a unit below shows "On, through <parent>". **Pilot report** gives cases, decisions submitted and
approved, the recommended net value, cases with business rules applied, instructions held and the routes, and *What
would have been sent* (case, step, instruction, target system, time). See [Approvals](../approvals.md#7-pilot-mode).

### Approver delegations

Three switches, all on at the start: *Decisions and overrides*, *MCP server proposals*, *Tenant access*. Each says what
the Approver may decide; "Admin can always decide". Switching one off removes that approval from the Approver's
inbox at once. It does not affect the Approver's right to approve rule changes and promote models.

### Requests

**All requests** lists tenant access requests and MCP server proposals with their status. Approve with an optional
note; decline with a note of at least 5 characters. When you approve tenant access, pick **Access ends** (*After 8
hours*, *After 1 day*, *After 7 days*, *After 30 days* or *No end*, the default). The Planner sees the customer at
once, without signing in again. You cannot decide a request you made yourself: the button is disabled with "You made
this request, so another person must decide it."

**Tenant access granted** lists the live grants with who granted them and when each ends. **Revoke** ends one now,
with an optional note; the Planner's open pages lock at once. See
[Approvals](../approvals.md#3-tenant-customer-access-requests).

### Approval limits and self-approval

**Approval limits** ("A decision above the approver's limit escalates to Admin") holds a dollar limit per role; empty
means unlimited. At the start: Approver and Admin unlimited, Planner $0 ("$0 means Planners cannot approve. Raise it
to let them approve within the limit.").

**Self-approval** is off at the start: the person who submitted a decision cannot approve it. Turning it on allows it
within the person's limit.

Here also: **Max actions per agent run** (1–500) and **Max items per bulk plan** (1–1,000).

### Agent autonomy

**Agent autonomy** sets, per role and action type, how far the agent may go: *Off* (never offers it), *Suggest*
(offers a button; you start it), *Prepare* (fills it in and shows a plan; you confirm), *Act and notify* (runs it,
tells you, offers Undo). Each type has a cap from its risk: requesting evidence, notifications, syncing a source and
saving a workflow draft can go up to *Act and notify*; field mappings, tables, conflicts and imports, all decision
actions, and publishing workflows, changing source connections and changing access are capped at *Prepare*. Reads,
drafts and what-ifs are always allowed.

### Agents and kill switches

**Agents and kill switches** ("Each agent acts as the signed-in person and never has more rights") lists every agent
with its scopes, limits, how many actions it prepared, and its status, plus the **hard rules (never configurable)**.
Stop an agent and it does nothing at all, reads included, until you start it again.

The **Agents** page is the fuller view:

- **Registry**: each agent's kind, status (**Stop** / **Start**), autonomy (*Read only*, *Propose for a person*, *Act
  within its tools*), tools and organisation scope. **Edit** changes the tools it may use (only those an agent is
  allowed) and the organisations it may see (none ticked: every organisation).
- **Register agent** opens a dialog: **Name**, **Id** (made from the name; you may change it), **Kind** (*External*
  or *Internal*), **Autonomy** (*Propose for a person* by default), **Org scope** (none ticked: every org) and **Tools
  it may use**. Only tools an agent may use are offered; actions that only a person may run, such as approving or
  changing access, are not, and the server refuses them. **Register** adds the agent.
- **Proposals waiting for you**: actions an agent held for a person. **Accept** runs it as you; **Reject** asks for a
  reason. A proposal from an agent that acted for you (for example a case autopilot you started) shows "Your agent's
  proposal: another person accepts it." instead of **Accept**; you can only reject it. The same proposals show on Home
  under *Proposals for you*. See
  [Approvals](../approvals.md#5-agent-proposals).
- **Runs**: each agent run step by step, and what it waits for. **Start case autopilot**: pick an agent, type a case
  (for example `RT-1048`) and start it. The autopilot gathers evidence, requests what is missing, re-evaluates if
  needed and submits the decision, acting as you; a submit by an agent set to *Propose for a person* waits as a
  proposal that another person (for example the customer's Planner) accepts, and the run always waits for a person to
  approve the decision.
- **Tool catalogue**: every action as a tool, and whether an agent may call it.
- **Models**: the base model, the active calibration per template and the fitted models. See
  [Models](#models) below.

**Agent metrics** counts success measures from the journal: interactions to approve, share of changes started through
the agent, acceptance, edit, undo and fallback rates, time to decision, response time.

### Who may start an agent run

Starting any agent run is Admin's. **Run the agent on this case** (case Overview) is the one narrower path: the
`runAgent` right (Admin, Planner, Approver) starts a propose-only run of the case autopilot of an enabled agent, and the
action pipeline holds every write of that run for a person. **Agent activity** (read only) lists what each agent did.

### Agent credentials

An agent can sign in on its own instead of borrowing a person's token. On the **Agents** page, **Credentials**: pick the
agent and press **Issue credential**. The page shows the **client id** and the **client secret once**; copy the secret
then, because only a hash is kept and nobody can read it again. The list shows each credential's client id, created and
last used time and status, with **Revoke**. The agent's token lasts 15 minutes and acts with its owner's permissions,
narrowed by the agent's tools and organisation scope. It prepares work and never approves: the forbidden list and the
autonomy limits still apply. A revoked credential, a stopped agent or a deactivated owner is refused at the next
request. Issuing and revoking are a person's
action; an agent cannot do either.

### Outside clients

**Outside clients** (Agents page, Admin only) lets a program outside Circularity, such as an AI assistant that speaks MCP,
ask a person for consent and then use Circularity's MCP tools as one of your agents. You register the client: **Client
name**, **Redirect URIs** (one per line, matched exactly), **Acts as** (the agent) and the scopes it may ask for: *Read
cases*, *Prepare case actions*, *Draft decision flows*, *Draft configuration* (these three are held for a person) and
*Find tools*. The client holds no secret. Each use starts with a signed-in person who sees a consent page and allows or
denies; the token is good for 15 minutes with no refresh, and is refused at the app's own API. **Revoke** stops a client.
The client is pre-registered by you: dynamic registration is not offered.

> **Legal review first.** Kinective's Legal team reviews outside-client access before it is offered to a customer. Do not
> register an outside client for a customer organisation until that review is done.

### Models

The **Models** panel (on the Agents page and at the foot of the Modeler) shows the base model, the active calibration
per template, and every fitted model with its outcome count, error figures, factors, who fitted it and its promotion
status.

- **Fit a candidate**: pick the **Template** and fit a candidate calibration model on the confirmed outcomes.
- **Propose promotion** on a candidate.
- **Approve promotion**: only on a candidate that someone else fitted and someone else proposed. A disabled button
  shows the server's reason.

See [Approvals](../approvals.md#6-model-promotion).

## What you cannot do, and why

- **Approve your own rule change, or promote a model you fitted or proposed**: maker-checker holds for Admin too.
- **Decide your own tenant access request or MCP proposal**: another person decides it, whatever the self-approval
  setting.
- **Approve your own submitted decision** while self-approval is off.
- **Approve an excluded route** or waive a failed gate: nobody can.
- **Change the Admin mapping** through the identity provider: Admin is assigned directly.
- **Let an agent do any of the above**: agents never approve, publish, propose or promote a model, register agents
  or change access, whatever their autonomy.

## Tips

- Change one delegation, limit or autonomy level at a time, and watch *Agent metrics* and the audit log.
- Before moving an organisation unit, check who holds grants on its old and new parents: it changes who sees its
  cases.
- Sign in as each role (see the [index](README.md)) to check what people see after you change a mapping or a
  delegation.

## For the technical team

Admin has every golden permission ("all") and the plan-8 ones: manageOrgs, manageFlows, approve.flows, manageAgents,
openCases. Screens for the plan-8 actions: Access → Organisation (`org.update` rename, `org.exportPack`,
`org.previewPack`, `org.importPack`, `org.setPilot`, the pilot report), Analytics (the pilot report for the org-unit
filter), the source drawer and the Connect dialog (`org_unit_id`), Manual Import (open tool-fleet and device cases),
the Modeler (`flow.suggestions`; Apply as draft is the person's own `flow.saveDraft`), Agents (`agent.register`), the
Models panel (`model.fit`, `model.propose`, `model.promote`; `model.list` is a read for agents and API clients), and
tenant grants (`access.decideRequest` with `expires_hours`, `access.revokeGrant`). `proposal.accept` refuses the
person the agent acted for (`own`); the pack export drops credential- and key-named settings; an agent-prepared call
to a forbidden action is refused whatever its headers say (reads excepted).
