# Plan 9 (DRAFT, revision 2): Recover on the agentic core, five segments

> **Status: draft, 25 Nov 2026.** Not ready for the loop (`loop.md`). It holds phases, tasks and acceptance at
> task-list level. After the team agrees the decisions in
> [research/2026-11-platform/README.md](../research/2026-11-platform/README.md) §3 and the open questions in §6, each
> task gets a spec section in the plan-8 format (operating rules, standard task cycle, gates).
>
> **Revision 2** aligns the plan with the product owner's Recover concept ([01](../research/2026-11-platform/01-recover-segments.md)).
> The concept was shared for its ideas, not its UI: tasks name capabilities, and our pages follow our own design and
> the demo's parity. Task IDs changed; the old → new map is at the end.

**Goal:** customers can pilot **Recover** on the **tool fleet AMS** pack (returns, service desk, contract refresh)
and the **device recommerce** pack, end to end. The same core then carries used cars, telecom network equipment and
medical rental, then **Reconcile** and **Resolve**, then the next segments.

- **Agents plan, people approve.** A chain of stage agents gathers evidence, values every route with carbon against
  named demand, and plans the queue. People step in only on thresholds, low confidence, conflicts and exceptions.
- **Compose.** A person describes the business. The configuration agent drafts the pack change set, adapters and
  mappings, and a person approves and publishes them.
- **Replay before publishing, back-test to sell.** The customer's own history shows the uplift.

**Constraints** (unchanged from plan 8 and AGENTS.md):
- Parity with the demo stays: the 128 cases and RT-1048 don't change while the default flows have no rules. Changing
  a default (for example `rulMin`) needs a decision-log entry first.
- Every write goes through `pipeline.invoke`. Agents never approve, publish, override, decline or change access.
- Postgres is the only datastore, and the trial package gains no container.
- Every new dependency is permissively licensed and listed for review by Kinective's Legal team before it ships.

**Decisions this plan builds on** (research README §3):
- **D1, agents:**
  - a deterministic stage-agent chain with per-stage autonomy and confidence;
  - Pydantic AI inside a stage behind `AgentLoop`;
  - the configuration agent;
  - an in-house model router;
  - Postgres traces and pydantic-evals.
- **D2, flows, rules and models:**
  - our own flow graph;
  - ZEN decision tables, including per-market ones;
  - a customer layer with 3-way rebase;
  - the model catalogue (lifelines, statsforecast, LightGBM with MAPIE);
  - `plan_queue` by default, with `milp` behind a port;
  - replay → shadow → canary.
- **D3, connections:**
  - our own engine and JSON Schema;
  - an adapter registry with system-owner approval;
  - field mapping with five choices;
  - OIDC sign-in and SCIM provisioning;
  - `@xyflow/react` for the canvas.
- **D4, domain:**
  - one core and three products;
  - the five segments first;
  - packs as data, with a gate catalogue of 41 gates;
  - standing-policy approval below thresholds;
  - carbon with sources.

Sizes: S ≤2 days, M ≤1 week, L >1 week (first pass, one engineer). Story IDs: A (TF, SD, CR, DV), B (UC, TN, MR,
X), H (RS), I (RC).

## Phase 0: decisions and quick wins (week 1)

- [ ] **P9-0.1** Decision-log entries: D1–D4 revision 2 and standing-policy approval reconciled with GR-05 and GR-D6.
  - Studio "Decision" workflows are hidden, because rules live only in the Modeler.
  - `credentials.rotate` is forbidden to agents.
  - The price floor is per customer (55% stays for parity).
  - The concept is not a UI spec.

  Size: S.
- [ ] **P9-0.2** Model chain in `get_model`: a 429 moves the call to the next model, plus one shared
  `complete_json()`. Size: S.
- [ ] **P9-0.3** Carbon factor set, with source, year and licence for each factor. A `co2` value line goes in the
  tool-fleet and device valuers. Size: S.
- [ ] **P9-0.4** Catalogue hygiene:
  - `credentials.rotate` joins `FORBIDDEN_ACTIONS`; it takes a `secret` and is outside the `source.` prefix.
  - `mapping.revert` and `tables.update` hold for a person.
  - The 12 unimplemented actions are no longer agent-allowed.
  - Seeded agents lose the tools that answer 501.
  - A test checks that the catalogue matches the pipeline.

  Size: S.
- [ ] **P9-0.5** Workflow JSON Schema generated from `blocks.py`. A validated `workflow.import` returns every problem.
  A server-side `workflow.export` read action. Size: S–M.
- [ ] **P9-0.6** `mapping.save` split out of `source.update`, held for a person. Autopilot on `case.opened` behind a
  setting. Size: S.
- [ ] **P9-0.7** A guardrail **type** (Compliance / Data quality / Threshold / Approval) and a **stage** on the
  existing guardrails. Data only, with no decision change. Size: S.
- [ ] **P9-0.8** Read-only sources enforced: an outbound instruction to a read-only source is refused. Discovery
  samples 500 records. Size: S.
- [ ] **P9-0.9** A sent-back flow change pinned to a step (`node_id` on `flow.reject`). A role × permission matrix and
  "test a user" as one read action. Size: S.
- [ ] **P9-0.10** What-if over the tool-fleet queue: market, labour, lease and slot overrides through `flow.simulate`.
  Size: S–M.

## Phase 1: packs as data, gates, customer layer (B §4, E §11)

- [ ] **P9-1.1** **Pack format v1**: 01's pack contract and B §4.2, with a JSON Schema.
  - Contents:
    - identity and version;
    - sample prompts and the clarifying question;
    - seven stages, each with its agent and default autonomy;
    - routes or channels;
    - typed guardrails placed at a stage;
    - systems, with adapter status;
    - canonical entities and mappings;
    - exception types with owners;
    - KPIs and analytics questions;
    - a replay dataset.
  - `tool_fleet` and `device` move from code into data, with parity tests against the PO goldens.

  Size: L.
- [ ] **P9-1.2** **Gate catalogue** (41 gates, B §3): declarative gates (trigger, evidence, effect, owner, citation)
  evaluated in the engine, with a batch hold and automatic release when evidence arrives (X-07). Size: M.
- [ ] **P9-1.3** **Customer layer** (X-04, E §11.1):
  - A base pack plus an overlay of typed operations, with a 3-way rebase when the pack updates.
  - Locked compliance guardrails can only be tightened.
  - Diversions insert a step or a shortcut, and run.
  - A diversion that skips a compliance guardrail is refused.
  - Pack updates never overwrite customer changes.

  Size: M–L.
- [ ] **P9-1.4** **Queue plan on live cases**: live tool-fleet cases carry named demand (renewals, pool shortages,
  open repair orders, bids) and are planned together by `plan_queue`, behind a `QueuePlanner` port (TF-07, TF-08).
  Size: M.
- [ ] **P9-1.5** **Pack-driven run-time views**: cases, exceptions with types and owners, KPIs, suggestion rules,
  analytics questions and the flow's agents come from pack data, in our existing pages, with no page code per pack
  (X-09). Size: L.

## Phase 2: the agent chain (F §8a–c)

- [ ] **P9-2.1** The **stage-chain runtime**:
  - Application code picks the next stage.
  - Each stage has its own tools, autonomy (Recommend only / Act within limits / Act alone), limits and a
    calibrated confidence.
  - Below the flow's threshold the item goes to a person, with the stage's recommendation.
  - `case_planner` becomes an exception assistant.

  Size: L.
- [ ] **P9-2.2** The `AgentLoop` port and its Pydantic AI adapter, used inside LLM stages:
  - external-call deferred tools;
  - the conversation persisted after each model turn;
  - the idempotency key `run_id:tool_call_id`;
  - a pinned playbook version.

  Size: M.
- [ ] **P9-2.3** `llm.router`: per-model budgets and cooldowns in Postgres, sticky per run. A run waits for a model
  instead of failing. Size: M.
- [ ] **P9-2.4** **Hold policy** in the pipeline. A held write states its reason: risk, value, confidence, taint,
  destructive, or stage autonomy. Thresholds come from the pack. Standing-policy approval below the thresholds is
  journaled as "approved by policy P vN, owner X". Size: M.
- [ ] **P9-2.5** Tracing and the run view: a `trace_span` exporter, and an agent-run view per case and per agent
  showing stages, tools, calls with their input and output, and usage. A journaled pause-agent switch. Size: M.
- [ ] **P9-2.6** The **configuration agent** (X-02):
  - reads a description and matches a pack;
  - asks one clarifying question;
  - outputs a pack change set (configuration, never code);
  - the change set is validated and held for maker-checker;
  - it has its own eval set.

  Size: L.
- [ ] **P9-2.7** Evals: pydantic-evals for case stages, the configuration agent and `workflow_author`, plus an
  injection corpus. CI runs them on test models, plus a nightly live run. Size: M.
- [ ] **P9-2.8** MCP tools generated from the action catalogue, plus `find_tools`, with OAuth protected-resource
  metadata. Size: M.
- [ ] **P9-2.9** **Phase gate**:
  - one journal row per accepted write;
  - fallback without a repeat call;
  - injected text gives held-only proposals;
  - each stage's autonomy is respected;
  - no new container.

## Phase 3: the two pilot packs on real inputs (A)

- [ ] **P9-3.1** **Tool fleet returns** (TF-01..10):
  - a case per returned tool from the contract or fleet feed;
  - the contract-right gate (GR-07);
  - grade read from the workbench;
  - a safety recall check with quarantine;
  - stale telematics caught;
  - WTI and RUL per tool and per part with a confidence class (lifelines);
  - threshold-only approvals;
  - follow-through and the outcome.

  Size: L.
- [ ] **P9-3.2** **Service desk** (SD-01..08):
  - a case per ticket or batch;
  - an estimate from similar past repairs (≥50 matches gives an instant price, otherwise a draft plus a technician
    check);
  - per-market tables in ZEN (labour, price lists, credit rules, cover terms);
  - fix, covered swap and upgrade priced for the customer and the margin;
  - options re-run when the fault is posted;
  - batches split per tool;
  - estimate accuracy shown on held-out repairs.

  Size: L.
- [ ] **P9-3.3** **Contract refresh** (CR-01..05):
  - a case per contract entering the window;
  - keep, like-life swap or upgrade by rule;
  - like-life units matched and reserved once;
  - the proposal priced (fee, saving against new, likelihood to renew, credits);
  - on approval, the proposal is sent, contract lines drafted and the units reserved.

  Size: M–L.
- [ ] **P9-3.4** **Device recommerce** (DV-01..09):
  - verify against the quote;
  - blacklist and lock;
  - no listing without a wipe certificate;
  - payout adjusted within 10%, with customer care beyond that;
  - price per channel with a MAPIE interval and the per-customer floor;
  - wholesale lots with approved-buyer bids;
  - ageing suggestions;
  - settlement.

  Size: L.
- [ ] **P9-3.5** Real actuals into the outcome where invoices exist (RC-08), so realised against predicted is real.
  Size: M.
- [ ] **P9-3.6** Mocks in source-sim, all synthetic: contract/fleet, telematics, service desk with repair history,
  spare-parts catalogue, device registry (blacklist/lock), wipe tool, price feed, marketplace. Size: M–L.

## Phase 4: replay, back-test, publishing in steps (A §3, E §11.6)

- [ ] **P9-4.1** Historical import of returns with their actual route, realised value, costs and dates. pandera checks
  the batch. Size: M.
- [ ] **P9-4.2** **As-of replay**: each case is valued as of its decision date, and both sides use the same valuer.
  The report shows:
  - the route mix, actual against flow;
  - straight-through %;
  - approvals and exceptions per day;
  - uplift with a bootstrap band.

  Size: L.
- [ ] **P9-4.3** Publish in steps (X-06): replay, then shadow, then **canary by region and share of volume**, then
  full, with rollback. Size: M.
- [ ] **P9-4.4** Back-test report export (PDF) for the sales motion. Size: S–M.

## Phase 5: Compose end to end (D, E)

- [ ] **P9-5.1** **Adapter registry**:
  - catalogue, generic REST, and from an API spec (OpenAPI importer, dlt `rest_api` vocabulary);
  - test, then production;
  - read-only or write-back;
  - a write-only vault;
  - **system-owner approval**.

  Size: L.
- [ ] **P9-5.2** **Field mapping**: proposals with calibrated confidence and a reason (RapidFuzz, value profiles, a
  memory of accepted mappings, an LLM rerank that may abstain), the five person choices, and a test run of past
  items. Size: M–L.
- [ ] **P9-5.3** **Identity provider**: OIDC sign-in (Authlib), SCIM 2.0 provisioning (scim2-models), and groups →
  roles as data in `policy`. Size: M.
- [ ] **P9-5.4** **Compose flow**:
  1. describe;
  2. adapter mapping;
  3. agent mapping, with per-stage autonomy and the confidence threshold;
  4. approve or modify, with a change pinned to a step and maker-checker;
  5. publish (P9-4.3).

  One version history and audit log. Size: L.
- [ ] **P9-5.5** `workflow_author`: a sentence becomes a typed `WorkflowGraph`, then schema validation, up to 3
  repair rounds, `workflow.validate`, a dry run, and a draft. Adapter generation drafts a declarative spec, held for a
  person. Size: M–L.
- [ ] **P9-5.6** Canvas on `@xyflow/react` with dagre, for the Studio and the Modeler, with per-node input/output
  samples. Parity is checked by the smoke scripts. Size: L.
- [ ] **P9-5.7** Decision-table node: a `DecisionTableEvaluator` port with a ZEN adapter (function nodes off) and the
  JDM editor. Tables compile to rule objects. Size: L.
- [ ] **P9-5.8** Case process layer (stages, SLA timers on `run_after`, escalations, "needs info") feeding one
  role-based "My work". DMN/BPMN export. Size: L.

## Phase 6: three more segment packs (B)

- [ ] **P9-6.1** **Used cars** (UC P0, 14 stories):
  - title and finance gate;
  - open-recall gate (pack policy; see the open question);
  - inspection and recon estimate;
  - channels: retail lot, auction, dealer trade, salvage;
  - recon and auction-mileage approvals;
  - lot choice by speed and price.

  Mocks: lease system, dealer management system, title service, recall database, auction, pricing guide.

  Size: L.
- [ ] **P9-6.2** **Telecom network equipment** (TN P0, 13 stories):
  - inventory-match and configuration-wipe gates;
  - export-control hold before resale;
  - routes: redeploy, spare, broker, harvest boards, recycle;
  - spares before new;
  - firmware upgrade step.

  Mocks: network inventory, decommission tracker, test bench, spares planning, broker marketplace, recycler.

  Size: L.
- [ ] **P9-6.3** **Medical rental** (MR P0, 12 stories):
  - a decontamination record is required;
  - service and certification must be in date for the rental;
  - routes: re-rent, service then re-rent, refurbish, retire;
  - nearest next hospital;
  - repair and early-retirement approvals.

  Mocks: rental system, asset management, decontamination log, biomedical service system.

  Size: L.
- [ ] **P9-6.4** Cross-segment P1 stories (X-09..15) and each segment's P1 stories. Size: L.

## Phase 7: Reconcile and Resolve (I, H)

- [ ] **P9-7.1** **Reconcile v1** (RC-01..07, RC-13; replaces old P9-5.2):
  - freight and third-party repair audit against the predicted cost lines;
  - outcomes: pay, short-pay, dispute, charge the customer, recover from the supplier, or accrue;
  - settlement and the AP handoff as instructions; the ERP pays.

  Money moves need a person or a standing policy, and new forbidden actions are added. Size: L.
- [ ] **P9-7.2** Reconcile: warranty attribution and supplier recovery (RC-05 in full, RC-10/11). Size: M–L.
- [ ] **P9-7.3** Reconcile: finance close (accruals, asset retirement, variance queue; RC-12/14/15), then device
  payouts and marketplace settlement. Size: M + M.
- [ ] **P9-7.4** **Resolve R0 spike** (1 week): promise and part-supply facts in the depot and WMS mocks, slack and a
  greedy plan for one backorder, and the harvest and swap remedies priced with the tool-fleet valuer. Size: S–M.
- [ ] **P9-7.5** **Resolve R1** (RS P0): the disruption case kind, with promise lines, the ripple trace, options and
  costing, and an allocation plan (`milp` behind the port). Approvals under standing policy, instructions. Size: L.
- [ ] **P9-7.6** **Resolve R2** (RS P1): P(breach) with lifelines and calibration, pool forecasts (statsforecast),
  capacity scheduling, hand-off to Reconcile. Size: L.

## Phase 8: next segments and hardening

- [ ] **P9-8.1** Complete the next segments' stories (B §7): ITAD / IT lease end first (it reuses the device valuer
  and the wipe gates), then rental and construction fleets, telecom CPE, batteries (EU battery passport), automotive
  cores, medical capital equipment, B2C serialised electronics. Size: L per segment.
- [ ] **P9-8.2** Per-agent credentials, OAuth for outside MCP clients, and the B18 security review. Size: M.
- [ ] **P9-8.3** Fraud triage rules (stage 1) with explainable signals and a hold for a person. Size: M.

## Demo path (Compose first)

One tool-fleet story, end to end:

1. **Describe.** The person types how they handle returns. The configuration agent matches the tool-fleet pack, asks
   one question and drafts the change set.
2. **Connect.** The adapter registry proposes the systems. The owner approves the connections, and the field
   mappings are confirmed with the five choices.
3. **Agents.** Each stage gets its autonomy, and the confidence threshold is set.
4. **Approve and publish.** A second person approves. A replay shows the uplift, and the flow publishes to one
   region at a share of volume.
5. **Run.** Returns, a service ticket and a contract nearing refresh each go through the chain. The queue plan fills
   each order once. Threshold cases wait in "My work"; the rest pass under the standing policy. The run view shows
   every call.
6. **Execute and learn.** Instructions go to the mocks and the confirmations are journaled. Real actuals come back,
   and the back-test report shows the uplift with a band.

Script detail: research A §4.

## Old → new task IDs (revision 1 → 2)

| Revision 1 | Revision 2 |
|---|---|
| P9-0.1..0.6 | P9-0.1..0.6 (0.7–0.10 new) |
| P9-1.1 AgentLoop, 1.2 router, 1.3 hold, 1.4 tracing, 1.6 evals, 1.7 MCP, 1.8 gate | P9-2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.9 |
| P9-1.5 `case_planner` | P9-2.1 stage chain (planner becomes the exception assistant) |
| P9-2.1 pack format, 2.2 gates | P9-1.1, 1.2 |
| P9-2.3..2.6 TF/DV stories, 2.7 mocks | P9-3.1..3.4, 3.6 |
| P9-3.1..3.3 back-test | P9-4.1, 4.2, 4.4 |
| P9-4.1 tables, 4.2 canvas, 4.3 workflow_author, 4.4 adapters, 4.5 pack from a sentence, 4.6 DMN/BPMN, 4.7 process layer, 4.8 My work | P9-5.7, 5.6, 5.5, 5.1/5.5, 2.6, 5.8, 5.8, 5.8 |
| P9-5.1 fraud, 5.2 finance stage 4, 5.3 per-agent credentials, 5.4 ITAD | P9-8.3, 7.1–7.3 (Reconcile), 8.2, 8.1 |
