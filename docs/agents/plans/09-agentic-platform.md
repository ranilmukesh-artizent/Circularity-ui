# Plan 9 (DRAFT): Agentic platform for the two pilots

> **Status: draft, 24 Nov 2026.** Not ready for the loop (`loop.md`). It holds the phases, tasks and acceptance at
> task-list level. After the team agrees the decisions in
> [research/2026-11-platform/README.md](../research/2026-11-platform/README.md) §3 and the open questions in §6, each
> task gets a spec section in the plan-8 format (operating rules, standard task cycle, gates).

**Goal:** a customer can pilot the tool-fleet AMS and device trade-in templates end to end.

- **Agents plan, people approve.** An LLM agent loop gathers evidence, values every route with carbon and proposes
  the best one. People step in only on thresholds, low confidence, conflicts and exceptions.
- **Building the setup.** The Studio drafts the template, workflows and adapters from a sentence, and a person
  publishes them.
- **Back-test.** A back-test of the customer's own history shows the uplift.

**Constraints** (unchanged from plan 8 and AGENTS.md):
- Parity with the demo stays: the 128 cases and RT-1048 don't change while the default flows have no rules.
- Every write goes through `pipeline.invoke`. Agents never approve, publish, override, decline or change access.
- Postgres is the only datastore, and the trial package gains no container.
- Every new dependency is permissively licensed and listed for review by Kinective's Legal team before it ships in
  the trial package.

**Decisions this plan builds on** (research README §3):
- **D1, agent stack:** Pydantic AI behind `AgentLoop`, an in-house model router, Postgres traces, pydantic-evals.
- **D2, Business Studio:** our own flow graph; GoRules ZEN decision tables; DMN/BPMN export; our own case process
  layer; LightGBM with MAPIE.
- **D3, Connection Studio:**
  - Our own engine, with a published workflow JSON Schema.
  - `@xyflow/react` with dagre for the canvas.
  - `ConfiguredAdapter` v2 with an OpenAPI importer.
- **D4, domain:**
  - Template packs as data, with a gate catalogue and evidence types.
  - Standing-policy approvals below the thresholds.
  - Carbon on every card, with sources.
  - Back-tests replayed as of each decision date.

## Phases and tasks

Sizes: S ≤2 days, M ≤1 week, L >1 week (first-pass, one engineer). Story ids refer to the research (A §1.10,
§2.11; README §4).

### Phase 0: decisions and quick wins (week 1)

- [ ] **P9-0.1** Decision-log entries:
  - D1–D4.
  - Standing-policy approval below thresholds, reconciled with GR-05 and GR-D6.
  - Studio "Decision" workflows hidden, because rules live only in the Modeler.
  - `credentials.rotate` is forbidden to agents.

  Size: S.
- [ ] **P9-0.2** Model chain:
  - A configured list of models and providers in `get_model`, with a 429 cooldown and the next model on rate limits.
  - One shared `complete_json()` for `model_slots` and `modeler_read`.
  - Test: a 429 on model A moves the call to model B, and A is not called again during its cooldown.

  Size: S.
- [ ] **P9-0.3** Carbon for the tool-fleet and device packs:
  - A factor set with source, year and licence for each factor.
  - A `co2` value line in both valuers, and the cards show it.
  - Test: no route shows 0 unless its factor is 0 by definition.

  Size: S.
- [ ] **P9-0.4** Catalogue hygiene:
  - `credentials.rotate` joins `FORBIDDEN_ACTIONS`. It takes a `secret` input and is outside the forbidden `source.`
    prefix (`services/agents/forbidden.py:12`), so today an agent may set a connection's credentials.
  - `mapping.revert` and `tables.update` (agent-allowed, change a source's setup) hold for a person (V, claim 17).
  - The 12 unimplemented actions become not agent-allowed.
  - `source.test` and `access.lookup` show as allowed, matching the pipeline.
  - A test checks that the catalogue and the pipeline agree.

  Size: S.
- [ ] **P9-0.5** Workflow JSON Schema:
  - The schema is generated from `blocks.py` and served beside `/blocks`.
  - `workflow.import` validates against the schema, runs `workflow.validate` and returns every problem.
  - A server-side `workflow.export` read action.

  Size: S–M.
- [ ] **P9-0.6** `mapping.save` split out of `source.update`, agent-allowed with hold-for-a-person. Autopilot starts on
  `case.opened` for agents with autonomy `act`, behind a setting.

  Size: S.

### Phase 1: the agent loop (F §8–10)

- [ ] **P9-1.1** The `AgentLoop` port and its Pydantic AI adapter:
  - Holds map to external-call deferred tools.
  - The conversation is persisted after each model turn.
  - Each tool call carries the idempotency key `run_id:tool_call_id`.
  - `playbook_version` is pinned for the run.

  Size: M.
- [ ] **P9-1.2** `llm.router`: Postgres tables `llm_model` and `llm_budget`; per-model budgets and cooldowns; sticky
  per run; a run waits for a model instead of failing.

  Size: M.
- [ ] **P9-1.3** Hold policy in the pipeline:
  - A held write states its reason: risk, value threshold, confidence, taint (untrusted data was read) or destructive.
  - `destructive` flag on `ActionDef`.
  - Thresholds per template.

  Size: M.
- [ ] **P9-1.4** Tracing and the run view:
  - A `trace_span` exporter.
  - An agent run drawer on the case and on the Agents page, copying Camunda's agent instance view: state, model,
    tools, each call with its input and output, and usage against limits.
  - A pause-agent kill switch, journaled.

  Size: M.
- [ ] **P9-1.5** Playbook `case_planner`: evidence → value routes → `decision.submit`, held by policy. It resumes after
  `proposal.accept` with the person's result.

  Size: M.
- [ ] **P9-1.6** Evals:
  - pydantic-evals with 10 case scenarios and 10 authoring scenarios, plus an injection corpus.
  - Runs in CI on test models; a nightly live job.

  Size: M.
- [ ] **P9-1.7** MCP tools generated from the action catalogue, plus a `find_tools` read tool. Input schemas enriched
  with descriptions and enums. OAuth protected-resource metadata.

  Size: M.
- [ ] **P9-1.8** Phase gate:
  - The nine spike tests from the agent-foundation note.
  - F §10 acceptance (a)–(d): one journal row per accepted write; fallback without a repeat call; injected text
    gives held-only proposals; no new container.

### Phase 2: template packs as data and the pilot packs (A, B §4)

- [ ] **P9-2.1** Pack format v1:
  - The 13 parts from B §4.2, with a JSON Schema.
  - `tool_fleet` and `device` move from code into data files, with parity tests against the PO goldens.

  Size: L.
- [ ] **P9-2.2** Gate catalogue and evidence types:
  - Declarative gates (trigger, evidence, effect, owner, citation), evaluated in the engine.
  - Erasure gates apply to IT and devices; RUL and grade-certificate gates apply to tools and motors.

  Size: M.
- [ ] **P9-2.3** TF-02, the contract disposition-rights gate. Contract terms are a decision table (P9-4.1), or a
  gate until that table exists.

  Size: M.
- [ ] **P9-2.4** TF-04, the wear index and RUL per component:
  - Inputs: IoT run hours × load, PLM rated life, and resets from the repair history.
  - Every number is a value line that shows its source.
  - A confidence class per tool.

  Size: M.
- [ ] **P9-2.5** DV-02 and DV-03: fraud-check evidence (blocklist/finance status, activation lock, genuine parts) and
  a certified-erasure gate before any listing.

  Size: M.
- [ ] **P9-2.6** DV-05 and DV-06: a LightGBM price model behind `Predictor`, with MAPIE P10–P90 intervals. Hold reasons:
  wide interval, unseen model, below the 55% floor, stale feed.

  Size: L.
- [ ] **P9-2.7** Mocks for contract/fleet, blocklist, price feed and erasure-certificate systems in source-sim, all
  synthetic.

  Size: M.

### Phase 3: back-testing (A §3)

- [ ] **P9-3.1** Historical import of returns with their actual route, realised value, costs and dates. pandera checks
  the batch.

  Size: M.
- [ ] **P9-3.2** As-of replay: each case is valued as of its decision date (price index, open demand, grades known
  then), and both sides go through the same valuer.

  Size: L.
- [ ] **P9-3.3** Uplift report: net uplift with a bootstrap band, broken down by route, class and site. Export as PDF.

  Size: M.

### Phase 4: Studio and Business Studio (D, E)

- [ ] **P9-4.1** Decision-table node:
  - A `DecisionTableEvaluator` port with a ZEN adapter, function nodes off.
  - The JDM editor as the table panel.
  - Tables compile to rule objects, so guardrails, simulation and shadow are unchanged.

  Size: L.
- [ ] **P9-4.2** Canvas on `@xyflow/react`, for both the Studio and the Modeler:
  - dagre auto-layout; pan and zoom with no scrollbars.
  - Each node shows its input/output samples from the test run.
  - Parity-checked by the smoke scripts.

  Size: L.
- [ ] **P9-4.3** Playbook `workflow_author`: from a sentence it builds a typed `WorkflowGraph`, then schema
  validation, up to 3 repair rounds, `workflow.validate`, a dry test run, and a draft for a person to publish.

  Size: M.
- [ ] **P9-4.4** Adapter generation:
  - A new `source.draft` action holds a declarative spec; an OpenAPI importer feeds it.
  - The flow: probe against a mock generated from the spec → discovery → mapping draft → dry run → a person publishes
    and enters the credentials.

  Size: L.
- [ ] **P9-4.5** X-02, pack drafting from a sentence:
  - The nearest pack plus the sentence give a change set, held as one proposal.
  - The whole set is simulated, then applied through maker-checker.
  - The Studio entry screen offers three ways in: describe it, start from a template, build from scratch.

  Size: L.
- [ ] **P9-4.6** DMN 1.x and BPMN 2.0 exporters, DMN table import (a subset), and a bpmn-js viewer with the watermark.

  Size: M.
- [ ] **P9-4.7** Case process layer:
  - Stages, SLA timers (`run_after`) and escalations.
  - A "needs info" proposal type.
  - All of it feeds "My work".

  Size: L.
- [ ] **P9-4.8** One role-based "My work" home replaces the Home/Command Center duplicate, with exceptions, alerts,
  approvals and proposals inside it. Decision-log entry.

  Size: M.

### Phase 5: after the pilots start

- [ ] **P9-5.1** Fraud triage rules (stage 1) with explainable signals and a hold for a person. Size: M.
- [ ] **P9-5.2** Credit settlement, fixed-asset retirement and a variance queue (stage 4). Size: L.
- [ ] **P9-5.3** Per-agent credentials, OAuth for outside MCP clients, and the B18 security review. Size: M.
- [ ] **P9-5.4** Next industry pack: ITAD / IT lease end, which reuses the device valuer and the erasure gates.
  Size: M–L.

## Demo path (Studio first)

The demo walks one tool-fleet case end to end:

1. **Draft the template.** The user types "Create a template for my AMS process". The agent drafts a pack change set
   and lists the adapters and fields it needs; the person reviews and applies it.
2. **Connect and map the sources.** An adapter is generated from OpenAPI and held for a person, and a mapping draft is
   proposed. The person publishes both.
3. **Open and plan the case.** A returned tool opens a case, and `case_planner` reads:
   - telemetry hours;
   - PLM rated life;
   - the repair-centre grade;
   - the contract terms.
4. **Propose a route.** The planner values every route with carbon and proposes the best.
5. **Approve or auto-approve.** Above the threshold a person approves in "My work"; below it the standing policy
   approves. The run view shows every tool call.
6. **Execute.** Instructions go to the ERP and WMS mocks, and their confirmations are journaled.
7. **Back-test.** A quarter of synthetic history shows the uplift with a band.

Script detail: research A §4.
