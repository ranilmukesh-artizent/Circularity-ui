# PR: Agent-First Circularity Decision Workbench (Product-Wide)

Oct 21, 2026 · @Ranil Mukesh M J

## Summary and scope

This PR turns the whole Circularity Decision Workbench from a click-driven app into an agent-first, human-governed product. It applies to every module, every role and every case, not to one demo flow.

In the new product, a user states a goal in plain language or presses an AI action on any object. An agent investigates using the product's own actions, deterministic rules validate the result, an authorised person approves anything consequential, and every step is traceable. Agent output always lands in the normal screens as editable work, not only as chat text.

**In scope**

- All eight navigation areas: Command Center, Product, Analytics, Integration, MCP & Tools, Process orchestration, Audit & provenance, Access.
- All eight roles: Planner, Approver, Engineer, Finance, Developer, Executive, Warehouse Manager, Admin.
- A shared actions layer, an agent runtime, an agent home, a global Ask Circularity panel, AI assist buttons, structured cards, trust controls, a case run view for any case, and AI assistance for field mapping and workflow building.

**Out of scope here** (detail in the last sections): live integrations with any third-party product, real writes to external systems, production authentication, and model retraining. Integrations stay simulated adapters, clearly labelled.

Implement in the existing application (`index.html`). Extend and refactor; do not rebuild.

## Goals, principles and success measures

The product should let users delegate work to an agent, check it, and approve it, instead of clicking through every step themselves.

**Goals**

1. Any common task can be started by stating a goal, from any page.
2. One actions layer is used by both the UI and the agent, so they always behave the same.
3. The agent's main output is a structured, editable card (a decision packet, a mapping diff, a workflow draft), not paragraphs.
4. Every role lands on its own agent home showing what needs them.
5. Configuration work (field mapping, table links, workflows, imports) gets AI drafting with human review.
6. Every consequential action is previewed, approved by an authorised person, attributed, auditable and, where possible, reversible.
7. Everything simulated is labelled as simulated.

**Non-goals**

- Replacing screens with a chat window. Tables, filters, search and direct navigation all stay.
- Letting a language model decide eligibility, prices, allocations or approvals.
- Connecting real enterprise systems or any vendor product in this PR.

**Design principles**

- **State the goal, review the result.** The user directs, the agent does the legwork, the user checks.
- **One action, two ways in.** Every button and every agent step call the same action.
- **Rules stay rules.** Gates, pricing, ranking, tie-breaks, pool allocation, permissions and validation are deterministic code the agent calls and explains.
- **A human commits.** Spend, stock, price, publishing and access changes always end at a person.
- **Output lands in the product.** Agent results open in the normal screens, editable.
- **Show, don't hide.** Plans before actions, sources behind numbers, confidence where it exists.
- **Honest by default.** Simulated data, adapters and agent reasoning are labelled.
- **Parity both ways.** Anything the agent can do, a person can do in the UI, and the reverse.

**Success measures** (record a baseline before building)

| Measure | How it is counted |
| --- | --- |
| Interactions to approve a recommended decision | Clicks plus prompts, from landing to approval |
| Share of tasks started through the agent | Agent-started actions over all actions, per role |
| Proposal acceptance | Agent proposals accepted without edit |
| Edit rate | Agent proposals accepted after editing |
| Undo rate | Agent-prepared actions later undone |
| Fallback rate | Agent requests answered with "I can't do that yet" |
| Time to decision | Case received to approval |

## Target experience

Every interaction follows one loop, and every case follows one ten-stage journey from lease end to learning.

**The interaction loop (any page, any role)**

1. **State the goal**: in the home prompt bar, the Ask Circularity panel, the command bar, or an AI assist button on an object.
2. **See the plan**: reads just run; anything that changes data shows a plan preview first.
3. **Watch it work**: each action the agent calls appears as a line with its result.
4. **Get a card**: the result arrives as a structured card and opens in the normal screen.
5. **Review**: accept, edit, ask why, try a what-if, or escalate.
6. **Commit**: consequential steps need an authorised person's explicit approval.
7. **Track**: the agent follows execution, reports progress and flags blockers.
8. **Learn**: the outcome is reconciled against the prediction and recorded.

**The returned-asset journey (applies to every case)**

This replaces the current ten journey steps (Supply evidence ... Reconcile & learn) everywhere in the product. A case now exists from lease end, not only from receipt.

| # | Stage | Triggered by | Agent does | Person does | Typical systems (simulated) |
| --- | --- | --- | --- | --- | --- |
| 1 | Lease ends | Contract expiry | Opens the case; gathers serial, model, site, usage, customer intent and lease terms | Nothing required | Customer portal / asset tracking, CRM, lease management |
| 2 | Return authorised | Return authorisation | Records fees, replacement order, book value, acquisition date | Nothing required | Lease management, ERP finance |
| 3 | Pickup and transit | Pickup booked | Tracks pickup date, ETA and freight cost | Nothing required | TMS / 3PL |
| 4 | Received | Goods receipt | Starts the holding-cost clock; checks which evidence is still missing | Confirms receipt if needed | WMS |
| 5 | Inspect and grade | Inspection result | Requests missing tests; reads grade, faults, repair estimate and test criteria | Engineer records results | Repair orders, inspection, PLM |
| 6 | Decide | Evidence complete | Gathers demand, pool shortages, purchase requests, parts forecasts, model status and market prices; builds every candidate outcome; runs the gates; predicts and ranks; builds the decision packet | Planner reviews, asks why, tries what-ifs, submits | CRM, EAM, ERP procurement, parts planning, PLM, remarketing |
| 7 | Approve | Packet submitted | Runs a pre-approval check; drafts the rationale | Approver (or Planner within a limit) approves, edits or declines | Circularity |
| 8 | Execute | Approval | Sends the route's instructions in sequence; tracks acknowledgements; flags delays | Handles exceptions only | ERP, EAM, WMS, repair, finance, sustainability reporting |
| 9 | Outcome | Final acknowledgement | Collects actual costs and realised value | Finance confirms where required | ERP finance, repair |
| 10 | Reconcile and learn | Outcome confirmed | Compares predicted and actual line by line; creates learning records; carries forward open demand | Reviews variances | Circularity |

**Route-specific execution sequences (stage 8)**

Extend `STEP_TPL` so each route has its full sequence. For example, redeploy: raise refurbish order, retest and confirm grade, reduce the open purchase request, put away to the pool location, assign in EAM, reclassify the asset and close the lease in ERP finance, record the outcome in sustainability reporting. Resale, re-lease, parts harvesting, material recovery and exit each get their own sequence in the same format.

## Architecture

UI controls and the agent both call `invoke(actionId, input, actor)`. `invoke` checks permissions and approval rules, runs the deterministic handler, writes state, emits an event, and the UI, audit log and trace all update from that event.

| Component | Responsibility | Existing code to reuse |
| --- | --- | --- |
| Action registry (`ACTIONS`) | Named, schema-described operations with permission, risk tier, idempotency and events | `ACT` handlers, `PERM_ACTS`, `can()` |
| `invoke()` | Single entry point: validate input, check role, tenant and location scope, check approval, deduplicate, run, emit | New; wraps existing handlers |
| Rules and pricing services | Gates, route building and ranking, tie-breaks, pool allocation, workflow validation | `buildRoutes`, `rankRoutes`, `tieBreak`, `solvePool`, `scenRoutes`, `wfValidate` |
| Agent runtime | Turns a goal into action calls and cards | `runTool`, `TOOLS`, `AGENTS` |
| Reasoning providers | Choose which actions to call and how to phrase the answer | New: a rule-based provider (default) and an optional language-model provider |
| Card renderer | Draws cards from typed data using one fixed catalog | Existing render functions (`bestCard`, `tiOutcome`, `execBlock`, `tiReconcile` and others) |
| Approval and autonomy engine | Risk tiers, autonomy settings, approval limits, delegations, hard rules | Approval modal, `S.deleg`, `HARD_RULES` |
| State and run store | Cases, runs, stage states, chat threads; persistence and cross-tab sync | `CASES`, `S`, new persistence |
| Event bus | Publishes every change to subscribers (UI, audit, trace, run inbox) | `EVENTS`, `pushEvent` |
| Provenance and audit | Source, record and fetch time for every fact; the audit trail | `provFor`, Data Trace, `auditEntries` |
| Trace | One trace per agent run, one span per action call | `orTraceHTML` |
| Simulated adapters | Stand-ins for ERP, EAM, WMS and the rest | `STEP_TPL`, `ackStep`, `SOURCES` |

**Rules for the architecture**

- No handler reads the DOM. UI adapters collect input (for example the approval modal's fields) and pass it to `invoke`.
- The agent never calls a handler directly, only `invoke`, with the signed-in user as the actor and the agent recorded as the preparer.
- Screens re-render from events, not from scattered `route(true)` calls inside handlers.

## Actions layer

Every operation in the product becomes a named action with one contract. The agent's tool list and every button are generated from, or call into, this one registry.

**Action contract**

| Field | Meaning |
| --- | --- |
| `id` | Namespaced verb, e.g. `decision.approve` |
| `title`, `description` | Human label and an agent-readable description of when to use it |
| `input`, `output` | JSON schemas |
| `permission` | Verb on resource, e.g. `decision:approve`, mapped from `PERM_ACTS` |
| `risk` | `read`, `draft`, `act` or `commit` (below) |
| `scope` | Tenant and location checks applied (`tenantOK`, `locOK`) |
| `idempotencyKey(input)` | Key that makes a repeat call a no-op |
| `reversible`, `undo` | Whether it can be undone, and the undo action's id |
| `emits` | Event type(s) written on success |
| `errors` | Typed codes: `validation_error`, `out_of_scope`, `tenant_boundary`, `approval_required`, `limit_exceeded`, `not_found`, `conflict`, `duplicate` |
| `handler(input, ctx)` | Pure function; no DOM access |

**Risk tiers**

| Tier | Meaning | Agent may |
| --- | --- | --- |
| `read` | No change | Run freely within the user's permissions |
| `draft` | Creates or edits a proposal inside Circularity only | Run, show the draft, user can discard |
| `act` | Low-impact, reversible change or message (request evidence, notify, sync, save a draft workflow) | Prepare with a plan preview; run after user confirms, or automatically if the autonomy setting allows |
| `commit` | Spend, stock, price, approvals, publishing, configuration of live sources, access | Prepare only. A person presses the final button |

**Action catalog**

| Action | Risk | Replaces or wraps |
| --- | --- | --- |
| `cases.list`, `case.get`, `case.evidence`, `case.routes`, `case.trace` | read | `queueRows`, `CASE_BY_ID`, `provFor`, `orRun` |
| `case.whatIf` | read | `scenRoutes` with scenario inputs, never stored |
| `demand.find`, `pool.optimize` | read | `find_demand`, `solvePool` |
| `analytics.query`, `audit.search`, `sources.health` | read | `metrics`, `auditEntries`, `SOURCES` |
| `workflow.validate` | read | `wfValidate` |
| `mapping.suggest`, `tables.suggestLinks`, `workflow.draft`, `import.clean` | draft | New AI assists (module sections) |
| `decision.prepare` | draft | Route building, ranking, snapshot |
| `decision.submit` | draft | `tiSubmit` |
| `scenario.save` | draft | `tiSave` |
| `access.requestTenant`, `mcp.propose` | draft | `tenantReqOk`, `mcpProposeOk` |
| `evidence.request` | act | `reqEvidence` |
| `evidence.recordResult` | act | `simResult` |
| `notify.send`, `notify.acknowledge` | act | `notifyOk`, `notifyAck` |
| `source.sync` | act | `srcSync` |
| `workflow.save` | act | `wfSave` |
| `mapping.apply`, `tables.update` | act | `sdSave` mapping part, `tgEditOk`, `tgFkOk` |
| `conflict.resolve` | act | `resolveConf` |
| `import.commit` | act | `csvCommit` |
| `instruction.resend` | act | `replay` (idempotent) |
| `decision.approve`, `decision.override`, `decision.decline` | commit | `confirmApprove`, `declineDecisionOk` |
| `outcome.confirm` | commit | `confirmOutcome` |
| `workflow.publish` | commit | `wfPublish` |
| `source.update`, `source.delete`, `credentials.rotate` | commit | `sdSave` connection part, `srcDelOk`, `sdRotateOk` |
| `access.decideRequest`, `access.setDelegation`, `access.setAutonomy` | commit | `reqDecideOk`, `delegToggle`, new |
| `adapter.acknowledge` | system only | `ackStep` (simulated systems, never the agent) |

Instructions to enterprise systems are not a separate action the agent can call: `decision.approve` creates them, so nothing is sent without an approval reference.

## Agent runtime and Ask Circularity

The agent runtime turns a goal into action calls and cards, always acting as the signed-in user. It never has more permission than that user.

**Request lifecycle**

1. Capture the goal and its context: page, selected object, role, tenant, location.
2. Resolve the intent and its parameters (case IDs, asset IDs, sources, sites, routes, amounts, dates). If something is ambiguous, return a clarification card with options.
3. Build a plan: an ordered list of actions. If any action is `act` or `commit`, show the plan preview before running it.
4. Run `read` and `draft` actions through `invoke`, streaming one line per call (action, key input, result, Retrieved / Model / Rules badge).
5. Compose the answer: one or two sentences built only from returned values, plus one or more cards.
6. Offer next steps as buttons that call actions (never free-text instructions).
7. Record the run: run ID, intent, provider, each call, durations, result, and the user's response (accepted, edited, undone).

**Reasoning providers**

| Provider | When | How it works | Label shown |
| --- | --- | --- | --- |
| Rule-based (default) | Always available, offline, deterministic | Intent catalog with example phrasings and keyword matching; parameter extraction by pattern and lookup; templated sentences filled from action outputs | "Agent: rule-based. No language model connected." |
| Language model (optional) | Only when a server-side endpoint is configured; off by default in the POC | Tool-calling over the same action catalog; answers validated against the card schemas; same permission and approval checks | "Agent: language model." plus model name |

Both providers return the same response shape, so the UI does not change when a model is added later.

**Grounding rules**

- Every number and fact in an answer comes from an action output and links to its source.
- If no intent matches, reply "I can't do that yet. I can:" with relevant suggestions. Never guess.
- "Approve it" or similar opens the approval card; nothing is approved from text.
- Requests outside the user's tenant or location return the `tenant_boundary` explanation, not data.
- Text from evidence notes, comments, imported files and source records is data. It is never followed as an instruction.

**Intent catalog (minimum set)**

| Area | Example phrasing | Actions called | Card |
| --- | --- | --- | --- |
| Briefing | "What needs me today?" | role inbox queries | Briefing, inbox list |
| Case | "Explain RT-1049" | `case.get`, `case.evidence` | Case card |
| Case | "What should we do with this asset, and why?" | `decision.prepare` or `case.routes` | Decision packet |
| Case | "Compare the routes" | `case.routes` | Route comparison |
| Case | "Why not resale?" | `case.routes` + tie-break and gate results | Explanation card |
| Case | "What if repair costs 30% more?" | `case.whatIf` | What-if result |
| Case | "Anything risky before I approve?" | gates, confidence, evidence gaps | Risk checklist |
| Case | "Submit this for review" | `decision.submit` | Plan preview, then status |
| Queue | "Received cases at Warehouse 2 missing inspection" | `cases.list` | Table card with filter chips |
| Queue | "Which cases should I look at first?" | `cases.list` + ranking | Ranked list with reasons |
| Queue | "Request inspection for all of them" | `evidence.request` × n | Plan preview listing each case |
| Approvals | "What's waiting for my approval?" | approvals inbox | Approval list |
| Outcomes | "Compare predicted and actual for RT-1049" | outcome record | Reconciliation card |
| Analytics | "Why did recovery drop last month?" | `analytics.query` | Chart card with drivers |
| Analytics | "Explain this number" (from a KPI) | `analytics.query` | Definition and breakdown |
| Integration | "Which sources are stale?" | `sources.health` | Source health list |
| Integration | "Map the fields for this source" | `mapping.suggest` | Mapping diff |
| Integration | "Build an ingest for this source" | `workflow.draft`, `workflow.validate` | Workflow diff |
| Integration | "Why is this workflow failing?" | last run states, `workflow.validate` | Diagnosis card with fix |
| Integration | "Suggest links between these tables" | `tables.suggestLinks` | Link suggestions |
| Audit | "What happened to RT-1049 this week?" | `audit.search` | Timeline card |
| Access | "Who can approve above $5,000?" | role and limit lookup | Table card |
| Orchestration | "Explain this run" | `case.trace` | Stage timeline |

**Conversation and controls**

- One thread per object (case, source, workflow) plus a general thread; stored with the app state, cleared on reset. No long-term memory about the user.
- Each streamed line takes 300 to 600 ms, instant when the user prefers reduced motion. Stop is always available; Retry and Edit plan follow any result.
- Thumbs up and down are recorded with the run; a thumbs-down adds the request to the eval set.

## App shell

Every role lands on an agent home, the Ask Circularity panel is available on every page, and every important object carries an AI assist button. The existing navigation stays as the secondary way around.

**Agent home (`#/home`, the new landing page for all roles)**

1. **Briefing**: three to five lines generated from data for that role (see Roles).
2. **Prompt bar** with three to six role starter chips.
3. **Needs you**: actionable cards for that role (approvals, evidence gaps, outcomes to confirm, failing workflows, notifications), each with its primary action.
4. **Agent activity**: what the agent did recently, each item with "Show trace" and, where allowed, Undo.
5. **Watching**: active watch rules (for example "tell me when inspection arrives for RT-1051").
6. **Key figures**: the role's existing Command Center figures, each with "Explain this number".
7. Links to the classic modules.

**Ask Circularity panel**

- A right-hand panel, resizable, opened from a top-bar button or Ctrl+J; a full-height sheet on narrow screens.
- Context chips at the top (page, object, role, tenant), removable to widen the question.
- Shows the provider label from the agent runtime section.
- Keeps its thread when the user navigates; switches thread when the selected object changes.

**Command bar (Ctrl+K)**

One box for three things: find an object (cases, assets, sources, workflows), run a command ("request inspection for RT-1051"), or "Ask the agent: ..." which opens the panel with the text.

**AI assist buttons**

A small "✦" button on each object below opens the panel with that object as context and two or three object-specific suggestions.

| Object | Suggestions |
| --- | --- |
| Case row, case page | Explain, what should we do, risks before approving |
| Asset page | Summarise this asset, compare similar assets |
| KPI or chart | Explain this number, what changed and why |
| Exception card | Draft a notification to the owner, chase evidence |
| Source tile | Diagnose this feed, suggest mappings |
| Field mapping table | Suggest mappings, check gaps |
| Table graph | Suggest links, describe tables |
| Workflow canvas | Draft from a description, fix errors, explain |
| Failed run | Explain this failure |
| Conflict | Suggest a resolution |
| Import preview | Clean this file |
| Audit entry or event | Explain this entry |

**Run inbox**

A top-bar icon with a count. It lists agent runs (running, waiting for you, done, failed) and watch rules, each linking to its result or trace.

**Changes to existing navigation**

- The sidebar stays; its sections keep working.
- The journey strip on case pages becomes a compact progress indicator for the ten stages. The bottom "Continue to step" bar is replaced by the agent's suggested next action.
- Notifications become agent messages: "I did X. Y needs you. I could not do Z because ...".

## Card catalog

The agent returns only cards from this fixed catalog, rendered with the product's own components. A card looks the same in the panel, on the home page and inside a module page.

| Card | Used for | Must show | Actions on the card |
| --- | --- | --- | --- |
| Briefing | Home, "what needs me" | 3 to 5 lines, each linked to its object | Open item |
| Case | "Explain this case" | Asset, owner, location, stage, grade, evidence status | Open case, ask follow-up |
| Decision packet | The main decision output | Recommended route and one-line reason; predicted net with confidence or range; alternatives with values; ineligible routes with the failed gate; gate checklist; key evidence with badges; risks and open items; who must decide; the instructions that follow approval | Approve, Edit, Escalate (by role); Full analysis; Show trace |
| Route comparison | Comparing options | Each route's net, range, demand, cycle time, gates passed | Pick for override (approver only) |
| Explanation | "Why" and "why not" | The deciding terms, gates or tie-break rule, each cited | Show trace |
| What-if result | Scenario questions | Base and simulated values, change in $ and %, what changed, whether the ranking changes; note that the approved decision is unchanged | Save scenario, Reset |
| Risk checklist | Before approval | Gate warnings, stale data, forecast-only demand, low confidence, open blockers | Escalate |
| Plan preview | Before any `act` or `commit` | Steps, actions, affected records, systems, quantities, costs, what can be undone | Confirm, Edit, Cancel |
| Approval | Commit decisions | The raw instructions, approval limit, drafted rationale that must be edited or acknowledged, evidence snapshot | Approve, Override, Decline |
| Progress | Execution | Each step's system, instruction, reference, status, Simulated tag | View payload, Resend (idempotent) |
| Reconciliation | Outcomes | Predicted and actual per line, variance, learning records, carried-forward demand | Show trace |
| Table | Lists and queries | Rows plus the filters applied, as editable chips | Open in module |
| Chart | Analytics answers | Chart, method and baseline, period | Open in Analytics |
| Mapping diff | AI field mapping | Source field, sample value, proposed canonical field, transform, confidence, reason | Accept row, Accept all high, Reject, Edit |
| Workflow diff | AI workflow drafts and fixes | Added or changed steps shown as ghosts, check results | Accept all, Accept step, Discard |
| Diagnosis | Failures and stale feeds | What failed, evidence, likely cause, proposed fix | Apply fix (with preview), Open |
| Clarification | Ambiguous requests | One question with 2 to 4 options | Pick option |
| Can't do that yet | Unsupported requests | What it cannot do, and relevant suggestions | Pick suggestion |
| Escalation | Blocked work | The blocker, its owner, a drafted message | Send (act), Edit |

**Card rules**

- Cards are built from typed data, never from free text.
- Every figure carries its Retrieved / Model / Rules badge and opens its trace.
- Card buttons call `invoke`, so permissions and approvals apply exactly as in the module screens.
- Any card can be pinned to the home page and opened full screen.

## Trust and governance

The agent's freedom is set per action type and per role, capped by the action's risk tier, and every agent-prepared change is previewed, attributed and, where possible, undoable.

**Autonomy levels**

| Level | Meaning |
| --- | --- |
| Off | The agent never offers this action |
| Suggest | The agent offers it as a button; the user starts it |
| Prepare | The agent fills it in and shows a plan preview; the user confirms |
| Act and notify | The agent runs it, tells the user, and offers Undo (only for `act` tier) |

**Default autonomy (Admin can change these in Access)**

| Action type | Default | Highest allowed |
| --- | --- | --- |
| Reads, drafts, what-ifs | Always allowed | Always allowed |
| Request evidence | Prepare | Act and notify |
| Send notifications | Prepare | Act and notify |
| Sync a source | Prepare | Act and notify |
| Save a workflow draft | Prepare | Act and notify |
| Apply field mappings, update tables, resolve conflicts, commit imports | Prepare | Prepare |
| Approve, override or decline decisions; confirm outcomes | Prepare | Prepare |
| Publish workflows, change source connections, change access | Prepare | Prepare |

**Approvals**

- Each role has an approval limit in dollars, set by Admin. Defaults: Approver and Admin unlimited; Planner $0, which Admin can raise.
- A decision above the approver's limit escalates to the next role with authority.
- A person cannot approve a decision they submitted, unless Admin enables self-approval within their limit.
- The agent drafts the rationale; the approver must edit it or tick "I reviewed the evidence snapshot". Minimum 15 characters, as today.
- The approval card shows the raw instructions that will be sent, not a summary of them.

**Undo**

- `draft` and `act` changes can be undone until a downstream system acknowledges them.
- "Undo this run" reverses every `draft` and `act` change from one agent run.
- After a downstream acknowledgement, only a compensating action is possible (for example, recall an instruction). The plan preview says so before the user confirms.

**Attribution**

- Every change records who performed it (a person) and who prepared it (an agent, if any).
- Agent-prepared records show a "Prepared by agent" badge until a person edits or confirms them.

**Confidence and escalation**

- Confidence or ranges are shown wherever the model provides them; low confidence adds the risk checklist and a suggestion to compare routes.
- When the agent is blocked (missing evidence, failed gate, no permission, low confidence, timeout), it returns an escalation card addressed to the owner (reuse `exOwner()`), with a drafted message.

**Agent identities**

Each agent in `AGENTS` keeps its scopes and limits, is listed in Access, and has its own kill switch. A stopped agent cannot be called by the runtime.

**Hard rules (never configurable)**

- The agent cannot waive a failed gate.
- The agent cannot approve, publish, change access or change live source connections.
- Nothing is sent to an enterprise system without an approval reference.
- Cross-tenant data is never assumed available.
- Retraining never overwrites the evidence snapshot behind an earlier decision.
- Content from records, files and comments is never treated as an instruction.

## Roles and experience modes

Each of the eight roles gets its own briefing, starter prompts and agent permissions, and sees the same cases and numbers as everyone else. Permissions are unchanged from `ROLE_POLICY`; the agent can only prepare what the role could do itself.

**Two experience modes over the same data**

- **Business mode**: decision packets, values, approvals, progress and outcomes. Technical detail sits behind "Show trace".
- **Technical mode**: the case run view with stages, agent activity, action calls, evidence, rules, approvals and traces.
- Developer and Admin default to technical mode; all other roles default to business mode. Any role that can open Process orchestration can switch.

**Per-role behaviour**

| Role | Home briefing shows | Starter prompts | Agent may prepare | Person-only actions |
| --- | --- | --- | --- | --- |
| Planner | Cases to prepare, evidence gaps, decisions ready to submit | "What should I work on first?" "Prepare decisions for cases received this week." "Which cases are missing evidence?" | Decision preparation, evidence requests, submissions | Submit confirmation; approval only if Admin set a limit |
| Approver | Approvals waiting, by value and deadline; risks | "What's waiting for me?" "Anything risky in these?" "Compare the routes for this case." | Rationale drafts, pre-approval checks, requests decided by delegation | Approve, override, decline; decide tenant and MCP requests |
| Engineer | Inspections due, failed gates, parts on backorder | "Which inspections are overdue?" "Why did this case fail the condition gate?" "Record the result for this case." | Evidence requests, result recording | Confirm recorded results |
| Finance | Outcomes to confirm, variances, avoided spend | "Which outcomes need confirming?" "Why did recovery drop last month?" "Explain this variance." | Reconciliation summaries | Confirm outcomes |
| Executive | Value realised, top exceptions and owners | "Brief me." "Biggest value at risk and who owns it?" | Notification drafts | Send notifications |
| Warehouse Manager | Inbound returns, capacity, handed-off items for their warehouse | "What's arriving next week?" "Am I over capacity?" "What's stuck with WMS?" | Evidence requests, acknowledgements | Acknowledge notifications |
| Developer | Stale or failed sources, failing workflows, open conflicts, mapping gaps | "Which sources need attention?" "Map the fields for this source." "Build an ingest for this source." "Why is this workflow failing?" | Mapping diffs, workflow drafts and fixes, table links, syncs | Publish workflows, change source connections, apply mappings |
| Admin | Everything above, plus agent activity and pending access requests | "Who can approve above $5,000?" "What did agents do today?" | All of the above | Access, delegations, autonomy settings, approval limits |

Scope rules stay as today: Planners see their tenants, Warehouse Managers their warehouse. The agent applies the same scope to every query.

## Module requirements: decision flow

Each module keeps its current screens and gains agent entry points that produce cards and land results back in those screens.

### Command Center

- Its key figures and "Needs you" items feed each role's agent home; the page stays as the drill-down view.
- Every KPI gets "Explain this number": definition, calculation, main drivers and links to the underlying cases.
- Exceptions become action cards: "Draft notification to owner" and "Chase evidence for these items" (plan preview listing each item).
- Filters accept plain language and show the result as editable filter chips.
- "Actions to prioritise" gets "Prepare the top items" (draft only, one decision packet per case).
- Senior and operational modes stay.

### Returned assets

- Plain-language queries become filter chips over the existing table; grouping by product stays.
- "Triage for me" returns a ranked list with a reason per case (value at risk, deadline, missing evidence).
- Bulk actions on selected rows (request inspection, prepare decisions) go through one plan preview that lists every case, then one action per case.
- Rows show a "Prepared by agent" badge where relevant and an AI assist button.

### Expected returns

- A case is created at contract expiry with status Expected; the agent fills stages 1 to 3 before the asset arrives.
- "Draft a receiving plan" returns a draft by warehouse and week, against capacity.
- Users can set watch rules ("tell me if this return slips").

### Asset intelligence

- "Summarise this asset" keeps the Retrieved and Predicted pages separate and labels each statement accordingly.
- Questions about the asset are answered with links to Data Trace.
- "Compare similar assets" returns a table card.

### Treatment Intelligence (the decision page)

- The decision packet sits at the top; the existing five steps collapse under "Full analysis". Nothing is removed.
- What-if questions in plain language move the visible scenario sliders and show the what-if result card. The approved decision never changes this way.
- "Why not this route?" answers from route terms, gates and tie-break rules.
- The agent drafts the rationale and any override reason; the person must edit or acknowledge them.
- Submit and approve go through the approval card.

### Approvals

- The approvals inbox becomes a list of approval cards, sorted by value and deadline, each with its pre-approval check.
- Batch review lists every item with its instructions; each approval is recorded separately and only within the approver's limit. There is no unlisted "approve all".
- Decline needs a reason and returns the case to the Planner. Items above the approver's limit escalate.

### Pool optimizer (behind its existing feature flag)

- The agent explains the allocation and the uplift over deciding each asset alone; the solver is unchanged.

### Analytics

- Plain-language questions return chart cards with method, baseline and period, and drill through to cases.
- "Explain this variance" breaks predicted against actual into its drivers.
- Existing charts and filters stay.

## Module requirements: integration and platform

Configuration work gets AI drafting: the agent proposes a diff, a person accepts it item by item, and every accepted change is versioned with "AI-suggested, accepted by \<role>".

### Source map (AI-assisted field mapping)

- **Suggest mappings** on the Field mapping tab. Inputs: source fields and masked sample values, the canonical model fields (`CANON`), and existing mappings for the same system type.
- Output: a mapping diff, grouped High, Medium and Low confidence. Each row has the proposed canonical field, a transform from the existing set (unit conversion, currency at a dated rate, local time to UTC, code table, pass-through) and a reason (name match, type, value pattern, prior mapping).
- Preview on up to 20 sample rows, before and after, with the count of rows that would fail validation.
- Gap check: required canonical fields still unmapped, source fields not used.
- Fields that look like personal data are flagged and excluded by default.
- Refine in chat ("this price is in lakh INR"); the diff and preview update.
- Accepting saves a new config version; nothing is saved automatically.
- **Diagnose this feed** on stale, failed or unmapped sources: cause (from sync runs, status, credential age) and a fix (refresh token, rotate credentials, add mapping) through a plan preview.
- **Set up from a sample**: paste a payload or a CSV header to get a draft connection and draft mapping, which stay drafts until a Developer saves them.

### Source tables

- **Suggest links**: foreign keys with evidence (name match, share of matching values in samples) and confidence.
- **Describe tables**: drafts the hover descriptions for tables and columns, and suggests clusters.
- Each suggestion is accepted or rejected individually.

### Workflow studio (AI-assisted workflow building)

- **Draft from a description**: builds a graph only from the existing palette step types. New steps appear as dashed ghost nodes; the user accepts all or one at a time. `wfValidate` runs automatically on the draft.
- **Fix errors**: from the Checks panel, proposes the smallest change that clears each error, as a diff.
- **Suggest next step**: when a step is dropped, suggests what usually follows (for example the matching ingestion channel).
- **Explain**: writes the workflow's plain-language description.
- **Diagnose a failed run**: from the last run's step states, names the failing step, the steps it blocked, the likely cause and a fix.
- **Clone and adapt**: "same as this workflow, for that source".
- The agent never moves or removes fixed steps, never bypasses the approval step, and never publishes. Its edits mark the workflow as unsaved.

### Conflict queue

- Suggests a resolution based on source authority and the routes it is holding; the person accepts or escalates.

### Manual import

- **Clean this file**: proposed normalisations as a diff (grade codes, date formats, units) and rejected rows with reasons. Commit still loads only valid rows, never partial rows.

### Event stream

- Explain any event; filter in plain language; duplicates, late arrivals and retries are explained in one line each.

### MCP & Tools

- The tool catalog is generated from the action registry. Read, draft and act actions are exposed; commit actions are exposed only as "prepare" variants.
- The Playground becomes an agent test bench: run any catalog intent against seeded data, see the trace, compare with the expected card.
- MCP server proposals get a review assist: write access, missing approval step, data touched.

### Audit & provenance

- Every entry records who performed it, who prepared it, and the run ID. Add a filter for agent-prepared entries.
- "What happened to this case?" returns a timeline card.
- "Export evidence pack" (simulated) bundles the snapshot, approvals, instructions and outcome for one case.

### Access

- Autonomy matrix (role by action type, capped by tier), approval limits per role, and the self-approval setting.
- Agent registry with scopes, limits and a kill switch per agent.
- Existing delegations, accounts and requests stay. Every change here is `commit` tier and audited.

## Case run orchestration

Every case has one run that moves through the ten journey stages, and one run store drives the technical run view, the business progress indicator, the journey strip and the agent's answers.

**Run store**

- One run per case: run ID (`RUN-<case number>`), the state of each stage, its stored result, the actor, timestamps, and the stage keys already written.
- Stage keys have the form `<case>:<stage>` or `<case>:<stage>:<step>`. A write checks its key first, so a repeat is a no-op.
- Seeded cases start at the stage their data implies: stages 1 to 5 from evidence and inspection state, 6 when routes exist, 7 when a recommendation exists, 8 when approved, 9 from execution acknowledgements, 10 when the outcome is confirmed.

**Case run view (Process orchestration, any case in scope)**

- A stage timeline for the ten stages, each with a status: Queued, Running, Completed, Waiting for approval, Warning, Failed, Skipped.
- A stage panel with nine fields: stage and purpose; agent or workflow; activity; evidence with provenance; actions or systems called; result; validation (gates, missing evidence, warnings); state change; next step.
- An event feed filtered to the run, an evidence panel, an action-call panel (input and output per call), and the approval and execution status.
- Inputs, outputs and decisions are shown. Hidden model reasoning is not.

**Controls**

- **Next** moves one stage. On a completed stage it shows the stored result. On a pending stage it performs that stage's work once. At Approve, it opens the approval card for someone with authority, or shows "Waiting for \<role>" to everyone else. At Execute, each Next is one acknowledgement in the route's sequence.
- **Back** changes the view only.
- **Replay** steps through stored results without writing.
- A blocked stage explains why and offers the escalation card. It never skips silently.
- **Reset case** (presenter or Admin) restores the case and its run to the seeded state.
- The business "Continue" action, the technical Next, the journey strip and agent requests all call the same run function.

**Code changes**

- Replace `JSTEPS` and `OR_STAGES` with the ten journey stages, and derive `jgDone()` and `orRun()` from the run store.
- Keep `orTraceHTML()` as the trace view, fed by real run records instead of derived timings.

## Data, state, demo mode and honest simulation

Every value on screen comes from one record per case, state survives a refresh, and anything simulated says so.

**Single source of truth**

- Cards, agent sentences, traces and events read values from the case record through functions. No number is typed into UI strings or templates.
- The seed stays deterministic (`mulberry32`). Every seeded case with a recommendation must reconcile: net equals the sum of its terms, and actual lines sum to the actual net.
- Extend `runInvariants()` so the Demo data checks also confirm: card values equal case values; no stage key is written twice; every catalog intent returns a card for at least one seeded case; agent answers contain no numbers absent from action outputs.

**Persistence**

- Persist the run store, case changes, chat threads and autonomy settings to `localStorage` under one versioned key; restore on load.
- Listen for the `storage` event so two open tabs stay in step.
- Reset (all, or one case) restores the seeded state.

**Presenter mode (`?presenter=1`)**

- Quiet mode pauses the random background activity (scheduled syncs in `smTick`, workflow runs in `wfTick`).
- Reset all, reset one case, jump a case to a given stage.
- Quick switch between accounts without losing state.

**Honest simulation**

- Results, references, fetch times and acknowledgements from simulated adapters carry a "Simulated" tag.
- The agent shows its provider label at all times.
- The product never says "live", "connected", "sent", "retrained" or similar about something simulated. Learning appears as proposed learning records.
- Historical timestamps in seeded data are fixed per seed, not generated from the current clock.

**Known code hazards to fix**

| Hazard | Where | Fix |
| --- | --- | --- |
| Approval and work-order references come from counters, so they differ each run | `S.seq.apr`, `S.seq.wo` | Derive references from case and stage |
| Event keys include `Date.now()`, so repeats create duplicates | `ackStep()` and other `pushEvent` callers | Use stage keys, checked before writing |
| Actual line values round to $10 | `lineActuals()` | Allow exact actuals per line in the seed |
| Handlers read form fields directly | e.g. `ACT.confirmApprove` | Move field reading into UI adapters |
| Handlers re-render the page themselves | `route(true)` inside handlers | Re-render from events |
| Permissions enforced only by removing buttons | `rbPrune()` | Enforce in `invoke()`; keep pruning as cosmetic |
| Random background activity changes the event feed | `smTick()`, `wfTick()` | Quiet mode; filter run views to their run |
| Unavailable or stale sources can break a stage | `SOURCES` | Surface them as Warnings with an explanation; never crash a flow |
| Editing hand-written seed cases changes the number of random calls and shifts every generated case | Hero seed functions | Keep random-call counts stable; rerun the data checks |
| Seed cases reference each other (pool partners) | `pool`, `POOLS` | Update linked cases together |

## Security, privacy, observability and accessibility

The agent can never do more than the signed-in user, never treats data as instructions, and every run is traced and testable.

**Security**

- The POC sign-in is client-side and demo-only, and is labelled so. Production needs server-side authentication and server-side enforcement in `invoke()`.
- The agent acts as the user. Agent identities in `AGENTS` limit which actions each agent may call; a kill switch stops one agent.
- Evidence notes, comments, imported files, source records and MCP proposals are untrusted data. If a language model provider is used, they are passed as clearly delimited data and never followed as instructions.
- No secrets in client code. Credentials stay masked; rotation stays simulated.
- Limits per run: a maximum number of actions per run and of items per bulk plan, configurable by Admin.
- Use the OWASP Top 10 for Agentic Applications (2026) as the security review checklist.

**Privacy**

- Seed data stays synthetic.
- No personal data in agent prompts, traces, logs or exported evidence packs. Fields flagged as personal are excluded from mapping suggestions and redacted in traces.
- Any compliance or regulatory implication of these choices (data protection, audit-log retention) must be reviewed by Kinective's Legal team before it is relied on.

**Observability**

- One trace per agent run, one span per action call: run ID, intent, provider, role, action, input and output summaries, duration, result, error code. Shape it like the OpenTelemetry GenAI conventions (`invoke_agent`, `execute_tool`) so it can be exported later.
- Record the success measures from the goals section, plus fallback rate and response time.

**Evals**

- An intent test set: each catalog intent against several seeded cases, with the expected card type and key values. It runs with the Demo data checks.
- Safety tests: approving from text, cross-tenant requests, attempts to waive a gate, and an instruction hidden in a comment or CSV must all be refused.
- Every thumbs-down adds a test case.

**Accessibility and performance**

- Keyboard: Ctrl+J for the panel, Ctrl+K for the command bar, Esc closes, focus returns to where it was.
- Streamed lines are announced with `aria-live="polite"`; status is never shown by colour alone; contrast works in both themes; reduced motion is respected.
- The panel opens in under 100 ms and shows the first streamed line in under 300 ms. Events update only the affected parts of the page.
- On narrow screens the panel becomes a full-height sheet.

## Delivery phases

Build in six phases, each finished and tested before the next starts. The first demo-ready milestone is phases 0 to 2 plus the case run view from phase 5; everything else can sit behind feature flags until it is ready.

| Phase | Scope | Exit criteria |
| --- | --- | --- |
| 0. Baseline | Inventory every `ACT` handler with its risk tier and target action; record the success-measure baseline; keep a copy of the current `index.html` | Inventory complete; baseline recorded; Demo data checks pass |
| 1. Foundation | Action registry and `invoke()`; handlers without DOM reads; event-driven re-render; run store; persistence and tab sync; honest-simulation labels; the code hazards fixed | Every button goes through `invoke()`; data checks pass; a refresh keeps state; repeated clicks create no duplicates |
| 2. Agent core | Agent runtime with the rule-based provider; intent and card catalogs; Ask panel; command bar; agent home for all eight roles; the decision flow (stages 6 to 10) working for any seeded case | Every catalog intent returns the right card on seeded cases; unsupported requests get the fallback; a decision can be prepared, approved and followed to its outcome starting from the home page |
| 3. Trust | Plan previews; autonomy matrix; approval limits and self-approval setting; undo per action and per run; attribution badges; escalation cards; agent registry and kill switches | Safety tests pass; every `act` and `commit` is previewed; undo works within its rules |
| 4. Module AI assists | Field mapping, feed diagnosis and setup from a sample; table links and descriptions; workflow drafting, fixing, diagnosis and explanation; conflict suggestions; import cleaning; analytics questions and "Explain this number"; audit timeline and evidence pack; receiving plans | Each assist produces a reviewable diff and saves a versioned change only when accepted |
| 5. Orchestration and quality | Ten-stage journey replacing the old steps; case run view with stage panels and controls; traces; eval set; metrics; accessibility pass | All acceptance criteria pass |
| 6. Optional model provider | A language-model provider behind a server endpoint and a feature flag, using the same actions and cards | Passes the same eval set and safety tests as the rule-based provider |

## Acceptance criteria

The PR is complete when every box passes from a clean reset, in a fresh browser profile, for every role.

**Foundation**

- [ ] Every state-changing button calls `invoke()`; no handler reads the DOM.
- [ ] Direct URLs, card buttons and agent requests are refused for actions outside the user's role, tenant or location.
- [ ] Repeating any action (double click, Back then Next, replay) creates no second event, approval or instruction.
- [ ] A refresh restores runs, case changes and chat threads; two tabs stay in step.
- [ ] Demo data checks pass, including the new checks.

**Agent**

- [ ] Every role lands on its agent home with a data-driven briefing, starter prompts and a Needs you list.
- [ ] The Ask panel and command bar work on every page and carry the page's context.
- [ ] Every intent in the catalog returns the correct card for the seeded cases, with streamed action lines.
- [ ] Every number in an agent answer matches an action output and links to its source.
- [ ] Unsupported requests get the fallback; ambiguous ones get a clarification card.
- [ ] The provider label is always visible.

**Trust**

- [ ] Every `act` and `commit` shows a plan preview before it runs.
- [ ] Nothing is approved, published or changed in Access by the agent or from text.
- [ ] Approval limits, self-approval rules and escalation above the limit work.
- [ ] Undo works for `draft` and `act` until a downstream acknowledgement; afterwards the preview says only a compensating action is possible.
- [ ] Agent-prepared records show the badge and the audit log shows performer and preparer.
- [ ] The safety tests pass (approve from text, cross-tenant, waive a gate, hidden instruction in data).

**Modules**

- [ ] Field mapping suggestions arrive as a tiered diff with sample preview, gap check and personal-data flags; nothing saves until accepted.
- [ ] Workflow drafts and fixes appear as ghost steps, pass `wfValidate`, never touch fixed steps and never publish.
- [ ] Every module listed in the module sections has its AI assist entry points working.
- [ ] Existing screens, filters, search and navigation still work for their roles.

**Orchestration**

- [ ] The ten journey stages appear consistently in the journey strip, the case run view and agent answers.
- [ ] Next, Back, Replay and Reset follow the rules in the case run section for any seeded case.
- [ ] Business and technical views of the same case always show the same status, references and values.

**Honesty and quality**

- [ ] Every simulated result, reference and acknowledgement carries the Simulated tag.
- [ ] Keyboard, screen-reader announcements, reduced motion and both themes pass the accessibility checks.
- [ ] Panel and streaming meet the performance targets.

## Out of scope and open decisions

**Out of scope for this PR**

- Live integrations with any third-party product or vendor platform; all integrations stay simulated adapters.
- Real writes to ERP, EAM, WMS or any external system.
- Production authentication, SSO, user provisioning and a server-side permission service.
- Durable server-side runs and background execution.
- Model training or automatic retraining; learning stays as proposed records.
- Exporting traces to an external tracing service.
- A required language model. The optional provider is phase 6 and needs a server endpoint.

**Open decisions (build with the default, change later)**

- [ ] Approval limits per role. Default: Approver and Admin unlimited, Planner $0.
- [ ] Self-approval within a limit. Default: off.
- [ ] Default autonomy levels. Default: the table in Trust and governance.
- [ ] Final labels for the ten journey stages. Default: as in Target experience, to be signed off by the PO.
- [ ] Which language model provider and hosting, if any, for phase 6. Default: none.
- [ ] Maximum actions per agent run and items per bulk plan. Default: 50 and 100.

## Instructions to the coding agent

Hand this whole document to the coding agent with `index.html`. It should implement the PR phase by phase, not produce a plan or mockup.

1. Read all of `index.html` first. Confirm the functions this PR names (`ACT`, `PERM_ACTS`, `can`, `runTool`, `TOOLS`, `AGENTS`, `HARD_RULES`, `buildRoutes`, `rankRoutes`, `tieBreak`, `solvePool`, `scenRoutes`, `wfValidate`, `provFor`, `runInvariants`, `lineActuals`, `ackStep`, `instrPayload`, `pushEvent`, `JSTEPS`, `OR_STAGES`, `orRun`, `jgDone`, `orTraceHTML`, `smTick`, `wfTick`, `rbPrune`) and list any that differ from this description before changing code.
2. Work through the delivery phases in order. Finish each phase's exit criteria before starting the next.
3. Reuse existing rules, pricing, gates, approvals, provenance and rendering. Never reimplement them inside the agent.
4. Keep every existing screen working. Put unfinished features behind feature flags rather than leaving them half-visible.
5. Never make anything simulated look live, and never let the agent approve, publish or change access.
6. After each phase, run the Demo data checks, the intent test set and the relevant acceptance boxes, and fix what fails.

**Completion report (after each phase)**

- Files and functions changed.
- Features delivered, against that phase's exit criteria.
- Sign-in IDs and how to use presenter mode, reset and Quiet mode.
- Tests run and their results.
- What is real POC logic and what is simulated.
- Known limitations and anything left unfinished.
