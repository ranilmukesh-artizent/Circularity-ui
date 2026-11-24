# Platform direction: research synthesis and decisions (revision 2, 25 Nov 2026)

Research reports, a source note and two verification passes. This page is the synthesis:
- what we decided (assumed best decisions, open to the team's challenge);
- what to build next, and in what order.

The plan that follows from it is the draft [plan 9](../../plans/09-agentic-platform.md).

**Revision 2** aligns everything with the product owner's **Recover** concept: five industry segments, one Decision
Intelligence core, and three products: Recover, Resolve and Reconcile ([01](01-recover-segments.md)). The prototype
was shared **for the concept, not the UI design**. These docs take capabilities, rules and data from it, never layout.
The changes and the reasons for each are in §7.

| Report | Question |
|---|---|
| [00-brief.md](00-brief.md) | Shared context: the product, the target, the user's answers, rules for every report |
| [01-recover-segments.md](01-recover-segments.md) | **New.** The Recover concept: Compose, agents, models, the five segments' packs |
| [A-pilot-templates.md](A-pilot-templates.md) | Tool fleet AMS (returns, service desk, contract refresh) and device recommerce: process, stories, back-test, demo |
| [B-industries-and-stories.md](B-industries-and-stories.md) | Used cars, telecom network equipment, medical rental; gate catalogue; pack format; roles; cross-segment stories; next segments |
| [C-competitive-landscape.md](C-competitive-landscape.md) | Orchestrators, suites, decision intelligence platforms, flow generators, per-segment competitors |
| [D-tier1-2-connection-oss.md](D-tier1-2-connection-oss.md) | Open source for connections: adapter registry, field mapping, workflow, identity provider |
| [E-tier3a-decision-oss.md](E-tier3a-decision-oss.md) | Open source for flows and rules: customer layer, decision tables, model catalogue, queue plan, canary |
| [F-tier3b-agent-stack.md](F-tier3b-agent-stack.md) | The agent stack: stage-agent chain, configuration agent, loop, models, tracing, evals, safety |
| [G-capability-gaps.md](G-capability-gaps.md) | What the code does today against the asks and the Recover concept (file:line evidence) |
| [H-resolve.md](H-resolve.md) | **New.** Resolve: service network disruptions |
| [I-reconcile.md](I-reconcile.md) | **New.** Reconcile: service and logistics settlement |
| [V-verification.md](V-verification.md) | Fact-checks of licence, version, regulatory, competitor and code claims (rounds 1 and 2) |

Licence, regulatory, accounting and contract findings in these reports need review by Kinective's Legal team before
anyone relies on or acts on them. Effort estimates are first-pass, not commitments.

## 1. Where we stand (G)

- **Strong middle, weak ends.**
  - Decide → approve → execute is the strongest part: gates, valuers, ranking, maker-checker, one action pipeline,
    instructions and outcomes.
  - Stage 1 fraud triage is thin.
  - Settlement stops at a cost posting: actuals are synthetic, and a detention check the demo describes is not
    computed (I §8). That is Reconcile's job.
- **Already close to the concept.**
  - The six tool-fleet routes match Recover's six paths.
  - A queue planner fills each order once (`plan_queue`).
  - Group-to-role mapping, flow versions and maker-checker exist.
- **The gaps are mostly about packs and agents.**
  1. A pack is a code builder, with no stages, typed guardrails, systems, KPIs or version.
  2. There is no replay of history.
  3. There are no stage agents with their own autonomy.
  4. There is no configuration agent: every "AI" feature is a keyword parser.
  5. There is no customer layer, and no publishing to a share of volume.
  6. Live tool-fleet cases are each planned in a queue of one. Named demand can arrive in the intake facts, but no
     source fills it, so the queue plan never weighs live cases against each other (G §7.5, V round 2).
- **Coverage per segment.** Of the 32 P0 stories for tool fleet and device, 2 exist, 15 are partial and 15 are
  missing. Service desk is the least covered. Used cars, telecom network equipment and medical rental have no code.

## 2. The market (C, H, I)

- **Horizontal orchestrators** (Camunda, UiPath, Pega, Appian, ServiceNow, Microsoft, Workato, n8n) mix flow,
  governed agents and human tasks. None has disposition content.
- **Decision intelligence platforms** became a Gartner category in January 2026. Aera has announced decisions built
  from a prompt; the date it ships is not stated. This is the nearest threat to Compose.
- **Of the flow and app generators checked, none has all of these:**
  - compliance guardrails locked by a pack;
  - maker-checker on the generated flow;
  - a replay before publishing;
  - a percentage or regional rollout.
- **Per segment:**
  - **Used cars:** dealer tools already recommend retail, wholesale or reprice per car. Our space is lessor and fleet
    returns, across channels.
  - **Telecom network equipment:** no software rival was found; service firms and maker take-back programmes do the
    work.
  - **Medical rental:** asset-management tools serve fleets that hospitals own, not rental routing.
- **Resolve:** service-parts and field-service suites (PTC, IFS) plan parts and visits. None prices a returned unit
  as a loaner or a parts donor at its Recover value.
- **Reconcile:** freight-audit, warranty and AP-automation vendors each audit one invoice type. None ties an invoice
  to the decision that caused the cost.
- **Our edge:**
  - every route is valued with value, risk and carbon, against named demand;
  - one core runs three decisions (Recover, Resolve, Reconcile) on the same chain and evidence;
  - agents can't approve;
  - packs with locked compliance and a customer layer;
  - replay before publishing;
  - self-hosted.

## 3. Decisions (assumed, revision 2)

The rule still holds: **our control plane stays ours.** We embed permissive libraries that don't bring a second state
store, approval store, workflow engine or API server. Nothing below adds a container to the trial package.

### D1. Agentic processing stack (F)

| Layer | Choice |
|---|---|
| Control plane | Ours: `pipeline.invoke`, proposals, `agent_run`, Postgres job queue, journal |
| **Orchestration (new)** | A **deterministic chain of stage agents** owned by our runtime: Intake → Condition and life → Demand → Fit-for-use → Valuation → Disposition (queue plan) → Follow-through, with Analytics learning after close. Each stage has its own tools, autonomy (Recommend only / Act within limits / Act alone), limits and a calibrated confidence. Below the flow's threshold the item goes to a person. Application code picks the next stage. Resolve and Reconcile run on the same chain. `case_planner` is no longer the main path; it becomes an exception assistant |
| Agent loop | **Pydantic AI** *inside* a stage, behind our `AgentLoop` port. Approvals map to external-call deferred tools: the resumed run receives the person's result and never re-runs the tool. Fallbacks: LangGraph, then the OpenAI Agents SDK |
| **Configuration agent (new)** | Same stack. It reads a description, matches a pack and asks one clarifying question. It outputs a pack change set (configuration, never code), which is validated and held for maker-checker. It has its own eval set |
| Durability | Own queue, conversation persisted after each model turn, idempotency key `run_id:tool_call_id`. DBOS (MIT) is the first upgrade |
| Models | Small in-house router: per-model budgets and 429 cooldowns, sticky per run. Not LiteLLM (compromised PyPI releases in 2026) |
| Tracing, evals | OTel GenAI spans to Postgres `trace_span`; pydantic-evals; a prompt-injection corpus |
| Safety | Forbidden list (adds `credentials.rotate`) + hold policy (risk, value, confidence, taint, destructive, stage autonomy) + typed outputs |
| Interop | MCP tools generated from the action catalogue with OAuth metadata; no A2A between our own products |

### D2. Flows, rules and models (E)

- **Own flow graph** stays the model of record. Add DMN/BPMN export and a viewer. Don't embed a BPMN engine; build
  the case process layer (stages, SLAs, timers, escalations, "needs info") ourselves.
- **GoRules ZEN** (MIT) for decision tables, including **per-market** labour rates, price lists, credit rules and
  cover terms (service desk). Rate cards are data; rules are tables.
- **Customer layer (new):** a base pack plus a customer overlay of typed operations, with a 3-way rebase when the
  pack updates.
  - The stricter value wins.
  - Locked compliance guardrails can be tightened or given an extra approver, never weakened.
  - Diversions add a step or a shortcut. A diversion that skips a compliance guardrail is refused.
  - Helpers: jsonpatch (BSD-3) and deepdiff (MIT).
- **Model catalogue (new):** each entry records its quality, drift, last-trained date and cadence. Drift metrics are
  our own, with no drift library.

  | Model | Choice |
  |---|---|
  | Remaining life | lifelines (MIT); not scikit-survival (GPL-3.0) |
  | Demand | statsforecast (Apache-2.0) |
  | Resale price | LightGBM + MAPIE intervals |
  | Refurbishment cost | regression |
  | Condition estimate | classifier fallback, always labelled an estimate |
- **Queue plan:** `plan_queue` (a heuristic pinned by the golden files) stays the default. SciPy `milp` (HiGHS) sits
  behind a `QueuePlanner` port for bigger queues and for Resolve's allocation.
- **Publishing in steps (new):** replay, then shadow, then **canary by region and share of volume**, then full.
- Authorization stays in `policy.py`.

### D3. Connections (D)

- **Keep our workflow engine** and its JSON, with a published JSON Schema and an LLM repair loop. Canvas on
  `@xyflow/react` with dagre.
- **Adapter registry (new):**
  - Three connector kinds: catalogue, generic REST, and built once from an API spec (dlt `rest_api` vocabulary plus
    an OpenAPI importer).
  - Test, then production. Read-only, or read plus write-back. The read-only setting is enforced.
  - A write-only credential vault.
  - A **system owner approves** a connection before it goes live or gains write-back.
  - Discovery samples 500 records.
- **Field mapping (new):** RapidFuzz (MIT) name scores, value profiles from the sample, and a memory of accepted
  mappings. An LLM reranks and may abstain. The confidence is calibrated, and every proposal gives a reason. A person
  makes one of five choices on each mapping:
  1. accept;
  2. choose another field;
  3. accept with a conversion;
  4. mark it not needed;
  5. ask the owner.
- **Identity provider (new, D3b):**
  - OIDC sign-in with Authlib (BSD-3).
  - SCIM 2.0 provisioning on scim2-models (Apache-2.0).
  - Directory groups map to roles as data in `policy`.
  - "Test a user" shows what a user gets.
  - No identity-provider server in the trial package. Zitadel is AGPL-3.0, so we don't use it.
- Agents draft *declarative* adapter specs. A person publishes them and enters the credentials.

### D4. Product and domain (01, A, B, H, I)

- **One core, three products.**
  - **Recover** decides where a returned item is worth most.
  - **Resolve** protects the turnaround promise in a service network disruption (H). Its case is one disruption with
    every promise at risk listed inside it, and it shares scarce fixes across them. A returned unit used as a loaner
    or parts donor costs its Recover value.
  - **Reconcile** decides what to pay, charge, recover or settle (I). It checks each invoice against the cost Recover
    predicted. It absorbs stage 4: credit settlement, asset retirement and the variance queue. The ERP pays; every
    money move needs a person or a standing policy.
- **Five segments first, in this order:**
  1. Tool fleet AMS: returns, service desk and contract refresh, all P0.
  2. Device recommerce.
  3. Used cars (lease and trade-in returns).
  4. Telecom network equipment.
  5. Medical rental.

  Then the **next segments** already researched (ITAD/IT lease end, rental and construction fleets, telecom CPE,
  batteries, automotive cores, medical capital equipment, B2C retail) are completed in the same plan (B §7).
- **Packs as data** follow 01's pack contract and B §4.2:
  - seven stages with an agent each;
  - typed guardrails placed at a stage;
  - routes or channels;
  - systems, entities and mappings;
  - sample prompts and the clarifying question;
  - replay data;
  - exception types with owners;
  - KPIs and analytics questions;
  - the customer layer.
  A **gate catalogue of 41 gates** makes evidence rules configuration. The run-time views are **driven by pack data,
  with no screen code per pack**, in our own UI.
- **Agents plan, people approve.** Below the thresholds, a standing policy that a person owns approves, and the policy
  itself went through maker-checker. Above them, or on low confidence, conflicts, exceptions or destructive writes, a
  person decides. This needs a decision-log entry and the team's sign-off.
- **Price floors and limits are per customer.** For example, the device floor is 55% of reference value in the demo
  (parity) and 60% of forecast in the concept: the same guardrail type with a different value.
- **Carbon on every card,** with cited factors.
- **Replay before publishing** and **back-test as the sales motion.** Each case is replayed as of its decision date.
  The report gives the route mix (actual against flow), straight-through %, approvals and exceptions per day, and the
  uplift with a bootstrap band.

## 4. Stories

IDs: TF tool-fleet returns, SD service desk, CR contract refresh, DV device recommerce (A); UC used cars, TN telecom
network equipment, MR medical rental, X cross-segment (B); RS Resolve (H); RC Reconcile (I). Each story has
Given/When/Then acceptance in its report.

| Set | P0 | P1 | P2 | Today (P0) |
|---|---|---|---|---|
| Tool fleet returns TF | 10 | 3 | 3 | TF-07, TF-08 exist; rest partial or missing |
| Service desk SD | 8 | 2 | 1 | 6 of 8 missing |
| Contract refresh CR | 5 | 2 | 1 | missing or partial |
| Device recommerce DV | 9 | 4 | 2 | partial or missing |
| Used cars UC | 14 | 8 | 3 | no code |
| Telecom network TN | 13 | 8 | 3 | no code |
| Medical rental MR | 12 | 8 | 3 | no code |
| Cross-segment X | 8 | 7 | 1 | pack contract, configuration agent, gates as data, customer layer, agents plan / people approve, replay and canary, evidence gates, match to the system of record |
| Resolve RS | 9 | 8 | 5 | about 60% of the core reusable (H §8) |
| Reconcile RC | 8 | 9 | 5 | outcome and instructions exist; actuals synthetic |
| Next segments | 21 later-phase stories (B §7) | | | |

**Pilot P0, tool fleet:**
- **Returns:**
  - TF-01: one case per returned tool.
  - TF-02: the contract-right gate.
  - TF-03: grade read from the workbench.
  - TF-04: recall with quarantine.
  - TF-05: stale telematics.
  - TF-06: wear index (WTI) and remaining life (RUL) with a confidence class.
  - TF-07: six paths valued against named demand.
  - TF-08: queue plan.
  - TF-09: threshold-only approvals.
  - TF-10: follow-through and outcome.
- **Service desk:**
  - SD-01: one case per ticket or batch.
  - SD-02: estimate from past repairs.
  - SD-03: per-market tables.
  - SD-04: fix, covered swap or upgrade priced.
  - SD-05: execute on market terms.
  - SD-06: re-run when the fault is posted.
  - SD-07: batch split.
  - SD-08: estimate accuracy.
- **Contract refresh:**
  - CR-01: one case per contract entering the window.
  - CR-02: keep, swap or upgrade by rule.
  - CR-03: like-life units reserved once.
  - CR-04: priced proposal.
  - CR-05: approve, send and draft.

**Pilot P0, device recommerce:**
- DV-01: one case per device.
- DV-02: verify against the quote.
- DV-03: blacklist and lock.
- DV-04: wipe certificate.
- DV-05: payout adjustment.
- DV-06: price per channel with an interval and floor.
- DV-07: wholesale lots and bids.
- DV-08: ageing suggestions.
- DV-09: settlement and learning.

## 5. Order of work

Detail and acceptance are in [plan 9](../../plans/09-agentic-platform.md).

1. **Quick wins (week 1):**
   - model chain with 429 fallback;
   - carbon;
   - catalogue hygiene, with `credentials.rotate` forbidden;
   - workflow JSON Schema and server export;
   - guardrail type and stage on the existing guardrails;
   - read-only sources enforced;
   - discovery sample of 500;
   - change requests pinned to a step;
   - role matrix and "test a user";
   - seeded agents' tool lists fixed;
   - What-if over the tool-fleet queue.
2. **Packs as data and the pack contract**, the gate catalogue and the customer layer; the queue plan on live cases.
3. **Agent chain:** the stage-chain runtime with per-stage autonomy and confidence, the router, the hold policy,
   tracing, evals, the configuration agent, generated MCP tools.
4. **Tool fleet pilot**, returns, service desk and contract refresh on real inputs, then the **device recommerce
   pilot**, with real actuals into the outcome (RC-08).
5. **Replay and back-test**, then publishing to a share of volume.
6. **Compose end to end:**
   - adapter registry with owner approval;
   - field mapping with five choices;
   - identity provider;
   - flow and pack drafting from a sentence;
   - React Flow canvas;
   - decision tables;
   - case process layer.
7. **Three more packs:** used cars, telecom network equipment, medical rental.
8. **Reconcile v1** (replaces P9-5.2), then the **Resolve** spike, then Resolve R1 and R2.
9. **Next segments:** complete the remaining industries' stories.

## 6. Open questions for the team

1. **Standing-policy approval below thresholds:** is it acceptable to the pilot customers' auditors? Should the
   thresholds be set per pack?
2. **Back-test data:** will the pilots share a quarter with actual routes, realised values and, for the service desk,
   past repairs with final costs?
3. **Device pricing:** is a licensed price feed available, or do we train on the customer's history only?
4. **Adapter code:** stay declarative-only (recommended), or approve a sandbox?
5. **Service desk** (A): who is "sales" for credits, and is the $300 limit per tool or per proposal? Does contract
   refresh trigger at 90 days before the end or before the notice deadline?
6. **Resolve** (H): one case per disruption (recommended) or one per promise at risk? Do pilot contracts state breach
   penalties? Which wins when Resolve and Recover both want a returned unit?
7. **Reconcile** (I): which money moves can a standing policy approve (short-pay under tolerance?), and which always
   need a person?
8. **Used cars** (B): no US federal rule stops a dealer retailing a car with an open recall (unconfirmed). Is "no
   retail with an open recall" pack policy?
9. **Legal sign-off** for the gate catalogue, carbon factors, regulatory gates and every bundled licence before the
   trial package changes.

## 7. What changed in revision 2 and why

| Change | What | Why |
|---|---|---|
| Added | [01-recover-segments.md](01-recover-segments.md) | The product owner's Recover concept is the target; one note all reports cite. It is a concept share, not a UI design |
| Added | [H-resolve.md](H-resolve.md), [I-reconcile.md](I-reconcile.md) | The user asked for full research on both products now |
| Updated | A | Tool fleet now has three flows, all P0 (service desk and contract refresh added). Device trade-in became device recommerce per the concept, with protection kept as a P1 replacement-stock channel. Stories renumbered; demos start in Compose |
| Updated | B | The five segments lead, with full chapters for used cars, telecom network equipment and medical rental. Gate catalogue grows from 24 to 41. The pack format matches the concept's pack contract plus a customer layer. Four stages became seven |
| Moved, not deleted | B: ITAD, rental fleets, telecom CPE, batteries, automotive cores, medical capital equipment, B2C | The user wants them completed later in the same plan |
| Updated | C | Per-segment competitors, decision intelligence platforms, flow and app generators against Compose |
| Updated | D, E, F | Adapter registry, field mapping, identity provider; customer layer, per-market tables, model catalogue, queue plan, canary; stage-agent chain and configuration agent |
| Changed decision | D1 | `case_planner` replaced by the stage-agent chain, because the concept's agents are stages with their own autonomy; a chain gives per-stage audit, replay and bounded cost |
| Changed decision | D4 industry order | ITAD-first became the five segments, because the product owner's concept names them |
| Moved | Stage-4 finance reconciliation | It becomes Reconcile v1, because the concept makes settlement a product on the same core |
| Updated | G | 27 ranked gaps (was 16) and quick wins 9–16 against the concept |
| Deleted | README's P0 table of revision 1 (TF-01..07, DV-01..07, X-01..02) | Replaced by the renumbered stories in §4; the old-to-new ID map is in A |
