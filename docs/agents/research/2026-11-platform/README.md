# Platform direction: research synthesis and decisions (24 Nov 2026)

Seven research reports and one verification pass, run after the 24 Nov reviews. This page is the synthesis: what we
decided (assumed best decisions, open to the team's challenge), what to build next and in what order. The plan that
follows from it is the draft [plan 9](../../plans/09-agentic-platform.md).

| Report | Question |
|---|---|
| [00-brief.md](00-brief.md) | Shared context: the product, the three tiers, the 13 asks from the reviews |
| [A-pilot-templates.md](A-pilot-templates.md) | Tool-fleet AMS and device trade-in: how they work, stories, back-testing, demo scripts |
| [B-industries-and-stories.md](B-industries-and-stories.md) | Other industries, regulatory gates, roles, the template-pack structure, epics, roadmap |
| [C-competitive-landscape.md](C-competitive-landscape.md) | Agentic orchestration platforms, suites with agents, returns and ITAD software |
| [D-tier1-2-connection-oss.md](D-tier1-2-connection-oss.md) | Open source for the Connection Fabric and Workflow Studio |
| [E-tier3a-decision-oss.md](E-tier3a-decision-oss.md) | Open source for the Business Studio: BPMN/DMN, rules, policy, ML confidence |
| [F-tier3b-agent-stack.md](F-tier3b-agent-stack.md) | The agent stack end to end: loop, durability, models, tracing, evals, safety, interop |
| [G-capability-gaps.md](G-capability-gaps.md) | What the code does today against the 13 asks (file:line evidence) |
| [V-verification.md](V-verification.md) | Fact-check of the key licence, version and code claims |

Licence, regulatory and contract findings in these reports need review by Kinective's Legal team before anyone relies
on or acts on them. Effort estimates are first-pass, not commitments.

## 1. Where we stand

- **Strong middle, weak ends.** Decide → approve → execute is the strongest part (gates, valuers, ranking,
  maker-checker, one action pipeline, instructions, outcomes). Fraud triage (stage 1) does not exist; financial
  reconciliation (stage 4) stops at a cost posting and predicted-vs-actual (G §4).
- **Nothing generative yet.** Every "AI" feature (Build with AI, the Modeler assistant, Ask) is a keyword/regex parser
  that asks one LLM model only to settle what it could not read. No agent creates or edits a workflow, source,
  mapping or flow today. 131 actions, 79 agent-allowed, 17 reachable by an agent (12 hand-written MCP tools) (G §2).
- **Both pilot templates exist as prototype ports** (`valuers/tool_fleet.py`, `valuers/device.py`): RUL is a typed
  number, device prices come from a fixed table, no contract, telemetry, erasure or fraud evidence, carbon shows 0
  (A §5, G §2.5).
- **Back-testing, the sales motion, is missing**: simulation compares draft rules with published rules, never with
  what people actually did, and never "as of" the decision date (A §3, G §5).

## 2. The market (C)

- Horizontal orchestrators (Camunda, UiPath Maestro, Pega, Appian, ServiceNow, Microsoft, Workato, n8n) all mix
  deterministic flow + governed agents + human tasks, and none has returns content (valuers, routes, asset model).
- Suites (Manhattan Agent Foundry, Blue Yonder, SAP, Oracle) ship agents on their own data. Blue Yonder is the only one
  with agentic returns features, retail only.
- Returns SaaS (Loop, ReverseLogix, Narvar, Happy Returns, ReturnPro) is B2C/retail; ITAD/device tools own grading and
  erasure: we read their outputs, we don't compete.
- **The empty quadrant**: general agentic orchestration *and* deep disposition content, vendor-neutral, self-hosted.
  The window is real for B2B asset circularity, closed for retail. The bigger threat is a horizontal platform plus a
  systems integrator's returns template, so ship templates and back-test evidence fast.
- **Our edge to say out loud**: every route valued with value, risk and carbon; canonical fabric with a conflict queue;
  maker-checker + shadow mode on rules; agents structurally unable to approve; self-hosted; back-test first.

## 3. Decisions (assumed, 24 Nov 2026)

"Mix of custom and OSS" made concrete. The rule from the agent-foundation note still holds: **our control plane stays
ours; we embed permissive libraries that don't bring a second state store, approval store, workflow engine or API
server.** Nothing below adds a container to the trial package.

### D1. Agentic processing stack (Tier 3b, F §9)

| Layer | Choice |
|---|---|
| Control plane | Ours: `pipeline.invoke`, proposals, `agent_run`, Postgres job queue, journal |
| Agent loop | **Pydantic AI** behind our `AgentLoop` port. Approvals map to *external-call* deferred tools (`proposal.accept` runs the held action as the person; the resumed run receives that result and never re-runs the tool). Fallback: LangGraph, then OpenAI Agents SDK |
| Durability | Own queue + conversation persisted after each model turn + idempotency key `run_id:tool_call_id`. A run waiting days for a person holds no process. **DBOS** (MIT, in-process, Postgres as its system database in production; SQLite is its default) is the first upgrade if we need parallel sub-agents with compensation |
| Models | Small in-house **router**: per-model budgets and 429 cooldowns in Postgres, feeding Pydantic AI's fallback chain, sticky per run. Not LiteLLM (see V for the supply-chain finding), not a gateway container |
| Tracing | OTel GenAI spans to a Postgres `trace_span` table shown on the Agents page; OTLP optional; Langfuse only as an opt-in profile (it needs ClickHouse, Redis, S3) |
| Evals | pydantic-evals in CI on test models; nightly live evals decide which models may take the agent role; a prompt-injection corpus |
| Safety | Forbidden list + **hold policy** (risk, value, confidence, taint) + dual-LLM extraction for untrusted source data + typed outputs + domain validators |
| Interop | MCP tools **generated from the action catalogue** with OAuth protected-resource metadata; then A2A agent card; AG-UI for our own panel later |

### D2. Business Studio (Tier 3a, E §8–10)

- **Keep our own flow graph** as the model (BPMN/DMN can't hold locked stages, guardrail owners, scope, maker-checker,
  shadow). Add **DMN 1.x and BPMN 2.0 export** plus a narrow DMN-table import, and a bpmn-js *viewer*, for interop and
  credibility next to BPMN vendors.
- **Adopt GoRules ZEN** (MIT, Python bindings) behind a `DecisionTableEvaluator` port for a new decision-table node,
  with its MIT JDM editor as the table panel; function (JavaScript) nodes off. Tables compile to our rule objects, so
  guardrails, simulation and shadow keep working. CEL is the fallback.
- **Don't embed a BPMN engine.** Camunda 8 self-managed production needs a paid licence (8.6+); Camunda 7 CE is end
  of life; the healthy open ones are JVM. **Build a small case process layer ourselves** (stages, SLAs, timers,
  escalations, human tasks, "request for information") on the job queue, approvals and proposals; export it as BPMN.
  SpiffWorkflow (Python, LGPL) is plan B.
- Pricing confidence: **LightGBM** behind the existing `Predictor` port with **MAPIE** conformal intervals; a wide
  interval is a hold reason ("low confidence goes to a person"). Keep our own model registry (propose/promote).
- Authorization stays in `policy.py`; learn from Cedar. Avoid OpenFGA (second store), Oso OSS (deprecated), Unleash
  (AGPL from v8).

### D3. Connection Studio (Tiers 1 + 2, D §9–10)

- **Keep our workflow engine** (a sync is its ingest workflow; replacing it means re-proving parity, and every
  candidate brings its own server/store and often Node or JVM; n8n's Sustainable Use, Windmill's AGPL and
  Activepieces EE block shipping).
- **Workflow JSON stays ours**, with a **published, versioned JSON Schema generated from `blocks.py`**. Agent output is
  validated against it with up to 3 repair rounds, then auto-laid-out and test-run. Open Workflow Spec / Arazzo only
  for import/export later.
- **Canvas on `@xyflow/react`** (MIT) with dagre auto-layout: infinite pan/zoom, no scrollbars, n8n-style input/output
  samples per node from the test run.
- **Adapters in hours**: extend `ConfiguredAdapter` with dlt's `rest_api` config vocabulary (Apache-2.0) and an OpenAPI
  importer. An agent drafts a *declarative* adapter spec (no code, no credentials) → probe read-only against a mock
  generated from the same spec → discovery → mapping draft → dry run → **a person publishes and enters credentials**.
  Generated Python adapter code stays out of scope until we decide on a sandbox.
- Formats: `pydifact` for EDIFACT, own X12 tokenizer for 180/856, sniffed CSV. pandera only for back-test imports.
  Avoid PyAirbyte and Soda Core (ELv2) and Singer taps (often AGPL). CDC not needed now.

### D4. Product and domain

- **Template packs become data**: a versioned bundle of 13 parts (B §4.2): manifest, asset classes, grade scale,
  routes, **declarative gate rules**, authoring guardrails, **evidence types**, valuer (parameterised or plug-in),
  **carbon factor set with sources**, required adapters and canonical fields, scope and wording, KPIs, stories + demo
  data + back-test dataset. A shared **gate catalogue** (~20 gates of 6–7 types) makes "erasure only for IT, RUL and
  grade certificate for tools and motors" configuration, not code.
- **"Create a template for my AMS process"** = an agent drafts a pack as one **change set** from the nearest pack and
  the sentence; the person reviews the whole set, simulates it, and applies it through maker-checker.
- **Humans approve, agents plan**, reconciled with today's rule that every decision has a named approver (B §open
  questions; guardrails GR-05, GR-D6): below the thresholds a decision is approved by a **standing policy** that a
  person owns and that itself went through maker-checker; the journal records "approved by policy P vN, owner X".
  Above threshold, low confidence, conflicts, exceptions and every agent write that is destructive → a person.
  Needs a decision-log entry and the team's sign-off.
- **Carbon on every card** with a deterministic per-route formula and cited, licence-safe public factors, labelled
  "avoided, not inventory" (B §2.4).
- **Back-test** replays each case **as of its decision date** (same price index, open demand, no later grades), prices
  both sides with the same valuer, includes all costs, and reports uplift with a bootstrap band (A §3).
- **One role-based "My work" home** replacing the Home/Command Center duplicate; exceptions, alerts, approvals and
  proposals inside it.
- **Industry order after the two pilots**: ITAD / IT lease end → rental and construction fleets → telecom CPE →
  EV and industrial batteries (aim at the battery passport date, 18 Feb 2027) → automotive cores → medical devices.
  B2C retail only for serialised electronics (B §6).

## 4. Pilot stories (P0)

From A §1.10 and §2.11 (Given/When/Then there). Agent = the agent does it; Person = a person approves or acts.

| ID | Story | Who | Today |
|---|---|---|---|
| TF-01 | A case opens per returned serial from the contract/fleet system | Agent | partial |
| TF-02 | Contract disposition-rights gate (may refurbish, resell, export; theft-recovered; open charges) | Agent; Person on breach | missing |
| TF-03 | Grade read from the repair centre, never computed | Agent | partial |
| TF-04 | Wear index and RUL per component from IoT hours × load, PLM rated life, repair resets, with value lines | Agent | missing |
| TF-05 | Every route valued with the why (best, second, uplift, rules, carbon) | Agent | exists (no carbon) |
| TF-06 | Exceptions-only approvals (value threshold, confidence, conflicts) | Person | partial |
| TF-07 | Instructions to systems and reconciliation of confirmations | Agent | partial |
| DV-01 | A case per IMEI or per lot | Agent | partial |
| DV-02 | Fraud checks: blocklist/finance status, activation lock, genuine parts | Agent; Person on hit | missing |
| DV-03 | Certified-erasure gate before any listing | Agent | partial (text guard) |
| DV-04 | Grade, battery health and parts read from the inspection app | Agent | partial |
| DV-05 | Price per channel with a P10–P90 interval | Agent | partial (table) |
| DV-06 | Low-confidence hand-off (wide interval, unseen model, below floor, stale feed) | Person | missing |
| DV-07 | Reconciliation and price-model feedback | Agent | partial |
| X-01 | Back-test a month/quarter of history as of each decision date, uplift with a band | Agent; Person reviews | missing |
| X-02 | "Create a template for my AMS process" drafts a pack change set | Agent; Person applies | missing |

Cross-industry epics (E1.1–E4.6, EX.1–2) and the top-15 stories with acceptance criteria: B §5.

## 5. Order of work

Pilot-critical first, quick wins folded in; detail and acceptance in [plan 9](../../plans/09-agentic-platform.md).

1. **Quick wins (week 1)**: model chain with 429 fallback; carbon for tool-fleet and device; catalogue hygiene (12
   unimplemented actions not agent-allowed, decide `credentials.rotate`); workflow JSON Schema + validated import +
   server-side export; autopilot on `case.opened` behind a setting; `mapping.save` split out.
2. **Agent loop**: `AgentLoop` port + Pydantic AI, router, per-turn persistence, hold policy, `trace_span`, agent run
   drawer, evals; playbooks `case_planner` and `workflow_author`. Generated MCP toolset (agentic CRUD) with OAuth
   metadata.
3. **Packs as data + gate catalogue + evidence types**, then the two pilot packs on real inputs (TF-02/04, DV-02/03/05/06).
4. **Back-test harness** (as-of import, replay, uplift report): the sales motion.
5. **Studio**: React Flow canvas with auto-layout and per-node samples; LLM workflow generation with repair loop;
   adapter generation from OpenAPI held for a person; pack drafting from a sentence.
6. **Decision tables** (ZEN) for contract terms; DMN/BPMN export; case process layer (SLAs, timers, RFI); "My work".
7. Then: fraud triage rules, credit settlement and asset retirement (stage 4), per-agent credentials, next industry
   pack (ITAD).

## 6. Open questions for the team

1. Standing-policy approval below thresholds (D4): acceptable to the pilot customers' auditors? Thresholds per
   template?
2. Which stages does each pilot cover? Fraud triage and finance reconciliation are L-sized; scope them in or out.
3. Back-test data: will the pilot customers share one quarter with actual routes and realised values?
4. Device pricing: is a licensed price feed available, or do we train only on the customer's history?
5. Agent-generated adapter *code*: stay declarative-only (recommended) or approve a sandbox?
6. Sign-off on Legal review for the gate catalogue, carbon factors and every bundled licence before the trial package
   changes.
