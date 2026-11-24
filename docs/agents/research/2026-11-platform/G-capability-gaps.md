# G. Capability gaps: what the repo does against what the team wants next

Report G of the platform research (brief: [00-brief.md](00-brief.md)). Read from the code at `0c71585`
(`feature/fullstack-poc`, 24 Nov 2026). Nothing was run: no tests, no Docker, no git. Every claim cites the file and
line it comes from; links are relative to this folder (`../../../../` is the repo root). Anything I could not confirm
from the code is marked **unconfirmed**.

Sizes: **S** ≤ 2 days, **M** ≤ 1 week, **L** > 1 week (one engineer who knows the repo, tests included).

Compliance note: the data-erasure and certification items below touch regulatory obligations (data sanitisation,
certified recycling). Kinective's Legal team should review those items before anyone relies on them.

---

## 1. Summary

The POC is strong on the **decide → approve → execute** middle of the return (gates, valuers, ranking, maker-checker,
one action pipeline, instructions to mocks, outcomes). It is weak at both ends of the reverse-logistics chain (no
fraud triage, finance stops at a cost posting) and on everything **generative**: every "AI" feature today is a
deterministic parser that uses a language model only to settle what its keywords could not read. No agent creates or
edits a workflow, source, mapping or flow today; the action catalogue would allow most of it, but only 17 actions
are reachable from an agent path.

| # | Ask | State | Size of the gap |
|---|---|---|---|
| 1 | Pitch flow, Studio first | Partial: one workflow or one rule from a sentence; no process template | L |
| 2 | Humans approve, agents plan | Partial: autopilot playbook, approval limits; no confidence or value routing | M |
| 3 | Guardrails per asset type | Partial: hard-coded gates, text-only guardrails | M |
| 4 | Back-testing | Missing (calibration and simulation are near it) | L |
| 5a | Tool-fleet AMS template | Partial: valuer reads grade and RUL as inputs; no contract check, no wear index | M–L |
| 5b | Device trade-in template | Partial: lookup-table pricing, wipe is a text guardrail only | M (ML pricing L) |
| 6 | Carbon on every disposition card | Partial: industrial template only, factor table in code | S |
| 7 | Agentic CRUD, platform as MCP | Partial: 131 actions, 79 agent-allowed, 12 MCP tools hand-written | M |
| 8 | Adapter generation in hours | Partial: configured read adapter; no OpenAPI import, no generated writes | M (writes L) |
| 9 | LLM resilience | Partial: one provider, one model, rule fallback | S |
| 10 | Declarative workflow JSON | Partial: export/import exist; no JSON Schema, no auto-layout | S–M |
| 11 | One role-based home | Duplicate: Home and Command Center share data, two pages | M |
| 12 | Connection workflows apart from decision rules | Mostly there; Studio still has "Decision" workflows | S |
| 13 | Positioning, deploy in under a week | Trial package exists; security and per-agent credentials open | M |

| Stage | State | Size |
|---|---|---|
| RMA intake and fraud triage | Intake exists; fraud triage: nothing | M (rules) / L (ML) |
| Receiving and grading | Mostly exists (expected returns, inspection app, repair-centre grade authority) | S–M |
| Smart disposition and recommerce | Strongest part | M for live pricing |
| ERP/WMS financial reconciliation | Partial: cost posting and predicted-vs-actual only | L |

---

## 2. The specific checks

### 2.1 "Build with AI" (Workflow Studio): a keyword planner with an optional model hint

- **Frontend.** The button opens a modal on the list page
  ([WorkflowList.tsx:129](../../../../frontend/src/pages/workflows/WorkflowList.tsx#L129)); the questions and plan UI is
  [WorkflowBuilder.tsx](../../../../frontend/src/pages/workflows/WorkflowBuilder.tsx); it posts to `workflow.plan`
  ([workflowBuilder.ts:97](../../../../frontend/src/api/workflowBuilder.ts#L97)). *Create workflow* is the person's own
  `workflow.create` + `workflow.save`.
- **Backend.** [workflow_builder.py](../../../../backend/di/services/actions/workflow_builder.py) holds two actions:
  - `workflow.draft` (the demo's `afWfDraft`, [L99](../../../../backend/di/services/actions/workflow_builder.py#L99)):
    the standard ingest graph for one source plus palette steps picked by seven regexes (`AF_WF_KW`, L88). Pure
    template + keyword match.
  - `workflow.plan` (L77, L708): a slot-filling planner (type, system, delivery, decision flow, channels, trigger,
    steps, handling, retries, alert, name). Reading is deterministic: keywords and `difflib` fuzzy matching over source
    names, vendors, trigger words (L252–L515). The graph is built from a fixed minimal topology per type
    (`MINIMAL`, docstring L14–L21; `_ingest` L1007, `_outbound` L1081).
  - **LLM use:** `model_slots` ([L516](../../../../backend/di/services/actions/workflow_builder.py#L516)) sends one JSON-mode
    request to Groq (temperature 0, 300 tokens) when `GROQ_API_KEY` is set. `_merge_model` (L555) lets the answer
    settle **only** ambiguities the keywords already found (which of two types, which of several systems, a trigger said
    in other words); every value is checked against the allowed choices. Any failure is ignored.
- **Verdict:** a topology match with an LLM tie-breaker. It produces one workflow of one of four shapes for systems
  already connected. It cannot draft a multi-workflow process, invent a block, or map fields.

### 2.2 The Modeler's plain-language assistant: a regex parser with an optional model hint

- [parse.py](../../../../backend/di/services/modeler/parse.py) reads `{path, action, scope}` with regexes (`EXCLUDE`,
  `REQUIRE`, grades, classes, sites); [propose.py](../../../../backend/di/services/modeler/propose.py) turns it into a
  checked, simulated proposal (rule, step, blocked, unclear).
- `flow.propose` ([modeler.py:453](../../../../backend/di/services/actions/modeler.py#L453)) calls the model only when
  the parser found no path (`_model_fill`, L465): one JSON request through
  [modeler_read.py](../../../../backend/di/services/ask/modeler_read.py) (temperature 0, 200 tokens), values checked
  against the template's paths, actions and scope dimensions. The answer says `read_by: "rules"` or `"rules+model"`.
- Frontend: [AssistantPanel.tsx:42](../../../../frontend/src/pages/modeler/AssistantPanel.tsx#L42) →
  `proposeChange` ([api/modeler.ts:49](../../../../frontend/src/api/modeler.ts#L49)); applying is the person's
  `flow.saveDraft`.
- **Verdict:** one rule per sentence, three actions (exclude/require/prefer), the template's fixed dimensions. No
  multi-rule edits, no new dimensions, no guardrail authoring.

### 2.3 Workflow JSON export and import

- **Export** is built in the browser, not on the server:
  [api/workflows.ts:444](../../../../frontend/src/api/workflows.ts#L444) `exportJson` writes
  `{id, name, version, type, status, owner, trigger, source, source_id, description, steps:[{id, kind, ref, label, x, y, cfg?}], links:[{from, to, fixed}], exported_by, exported_at}`.
  `cfg` holds only settings that differ from the defaults.
- **Import** is `workflow.import` ([workflows.py:1276](../../../../backend/di/services/actions/workflows.py#L1276),
  parser `_parse_import` L1293, handler L1376). It checks: steps is a non-empty list, each step has an id, a known
  kind (`_KINDS`, L1280), a known block ref (`_known_block`), a live source for connector and map steps, no duplicate
  ids, numeric `x`/`y` (missing ones default to 0), `cfg` is an object, links name existing steps, the trigger.
  It creates a **draft**; refusals name the first problem.
- **Not checked at import:** the graph's own checks (`workflow.validate`; run on save and publish), the block settings
  against the block catalogue (only "is an object"), graph shape (cycles, orphans).
- **No JSON Schema** exists for the export, the internal graph `{nodes:[{id,k,ref,x,y,cfg}], edges:[{id,a,b,locked}]}`,
  or the Modeler's flow graph `{nodes:[{id,t,x,y,label,…}], edges:[{id,a,b,l}]}`
  ([flow.py:1–5](../../../../backend/di/services/modeler/flow.py#L1)). That is three shapes for two canvases.
  `jsonschema` 4.26 is already in `requirements.lock` (pulled in by `mcp`), unused. The block catalogue with its
  settings is served at `GET /api/screens/workflows/blocks`
  ([routes/screens/workflows.py:34](../../../../backend/di/routes/screens/workflows.py#L34), from `di/workflow/blocks.py`),
  which is the natural source for a generated schema.
- **No auto-layout**: positions come from the JSON. No dagre/ELK in `frontend/package.json`. An agent that emits a
  graph must place every node itself, or all land at (0, 0).
- The org pack embeds the same export for workflows
  ([org_pack.py:1–25](../../../../backend/di/services/actions/org_pack.py#L1)).

### 2.4 LLM provider and fallback

- **Callers:** three, all Groq, all through the one private client
  ([groq_model.py:35](../../../../backend/di/services/ask/groq_model.py#L35) `_client`):
  Ask (`GroqModel.answer`, streaming tool loop, up to `ask_max_rounds` = 4), `workflow_builder.model_slots`, and
  `modeler_read._ask`. Nothing else calls a model (checked: no `openai`, `anthropic`, `litellm`, `pydantic_ai` in
  `backend/requirements.in`).
- **Models:** one. `DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"`
  ([config.py:9](../../../../backend/di/core/config.py#L9)); `GROQ_MODEL` overrides it (L57). `ASK_PROVIDER` accepts
  only `groq | none | off | fallback` (L55).
- **Port:** `AskModel` protocol and `get_model()` ([model.py:86](../../../../backend/di/services/ask/model.py#L86)); a
  second provider is "one more class". The two JSON helpers bypass the port and import `_client` directly.
- **Rate limits:** the SDK runs with `max_retries=0`; a 429 becomes `ModelUnavailable("rate_limited")`
  ([groq_model.py:40](../../../../backend/di/services/ask/groq_model.py#L40)). Ask then answers with the rule-based
  fallback ([fallback.py](../../../../backend/di/services/ask/fallback.py): 52 intents, 25 runners); the two helpers fall
  back to the keyword reading. No token budget, no limiter, no circuit breaker.
- **Gap:** no fallback **across models or providers**. A 429 on the one model drops straight to rules. Size **S**: a
  configured chain `[(provider, model), …]` in `get_model`, try the next on `rate_limited | unavailable | timeout`,
  one shared `complete_json()` for the helpers; an OpenAI-compatible provider class covers most hosted endpoints.

### 2.5 Carbon per route

- **Computed** for the industrial template only, in `ti_m`
  ([common.py:332–343](../../../../backend/di/repositories/common.py#L332)):
  `co2 = EMB[class] × qty × CO2S[route]`, with the factor tables in code (`EMB`, `CO2S`,
  [common.py:166–167](../../../../backend/di/repositories/common.py#L166)). Deterministic.
- **Shown** per route on the case: the ranking row carries `co2`
  ([screens/case.py:770](../../../../backend/di/services/screens/case.py#L770)); the Decide tab shows "CO₂e avoided"
  per route and uses it as a tie-break
  ([DecideTabs.tsx:335, 720, 836](../../../../frontend/src/pages/case/tabs/DecideTabs.tsx#L720);
  [cases.py:204](../../../../backend/di/repositories/cases.py#L204)). Portfolio totals on Command Center and Analytics
  ([command.py:709](../../../../backend/di/services/screens/command.py#L709),
  [workspace.py:659](../../../../backend/di/repositories/workspace.py#L659)).
- **Not computed** for tool-fleet and device cases: their valuers have no carbon term
  ([tool_fleet.py](../../../../backend/di/services/modeler/valuers/tool_fleet.py),
  [device.py](../../../../backend/di/services/modeler/valuers/device.py)), their classes are not in `EMB` (so 0), and the
  frontend fills `co2: 0` when a route has no ranking row
  ([DecideTabs.tsx:38](../../../../frontend/src/pages/case/tabs/DecideTabs.tsx#L38)).
- No method/source provenance per factor; the Persefoni mock (carbon accounting) is read but not used for factors.
- **Gap S:** factors per pack (class × route), a `co2` line in both valuers, the factor's source shown on the card.

### 2.6 RUL / wear index, data-erasure gate, grade certification gate

| Item | industrial | tool_fleet | device |
|---|---|---|---|
| RUL | `engLife` text ("N months") from the engineering source, shown as life, not a gate ([common.py:337–341](../../../../backend/di/repositories/common.py#L337)) | `rul` % is an **input field** on the case; gates refurb (≥ 40) and pool (≥ 45) ([tool_fleet.py:331, 428, 451](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L331)); part RUL per part | none |
| Wear-and-tear index | none | none | none |
| IoT telemetry | only the rule-scope fact `alarm: yes|no` from vibration/bearing temperature ([facts.py](../../../../backend/di/services/modeler/facts.py)); `run_hours` lands in canonical ([aws_iot.py:237](../../../../backend/di/connectors/adapters/aws_iot.py#L237)) but no engine or valuer reads it | same | — |
| PLM | BOM parts valuation at intake (`BomPartsPredictor`); Windchill is read-only part/BOM, no RUL | none | — |
| Data erasure | hard gate, IT class only, **resale only** ([gates.py:45–48](../../../../backend/di/services/engine/gates.py#L45)); redeploy and re-lease are not gated; guardrail GR-I1 is text ([industrial.json:15](../../../../backend/di/services/modeler/packs/industrial.json)) | — | guardrail GR-D1 "Certified data wipe before any listing" is a **text pattern only** that blocks rules saying "skip wipe" ([templates.py:125](../../../../backend/di/services/modeler/templates.py#L125)); no lot field or gate checks a wipe |
| Grade certification | SIL recertification gate for safety-rated controls ([gates.py:49](../../../../backend/di/services/engine/gates.py#L49)); grade D gate | grade read from the case (`grade`, else `estGrade`); release needs A, refurb B/C ([tool_fleet.py:331](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L331)); "certified" appears only in value-line wording | grade D never on Buy Now/Marketplace (GR-D3) |

Grading is **read**, not computed, as the pitch wants: inspection app (SafetyCulture,
[safetyculture.py](../../../../backend/di/connectors/adapters/safetyculture.py)) and Depot Repair as the authority over
the grade, disagreements to the conflict queue.

Changing the industrial erasure gate (e.g. also on redeploy) changes demo numbers: it needs a decision-log entry
(golden rule 1).

### 2.7 Back-testing

- **Simulation** (`flow.simulate`, [modeler_sim.py:1–15](../../../../backend/di/services/actions/modeler_sim.py#L1);
  [simulate.py](../../../../backend/di/services/modeler/simulate.py)) compares a **candidate rule set with the published
  one** on the open queue (industrial) or the prototype's random sample queues (tool fleet `rng(26110)`, device
  `rng(4242)`). It never compares with what people actually did.
- **Calibration** ([calibration.py](../../../../backend/di/services/engine/calibration.py),
  [outcomes.py](../../../../backend/di/repositories/outcomes.py), `model.fit`) compares predicted net with
  Finance-confirmed actual net, per (template, route, class). That is the right data shape, but only for cases that
  ran through the platform.
- **Pilot mode** per org holds instructions and reports what would have been sent (`org.pilotReport`): a forward shadow,
  not a replay.
- **Manual import** (`import.commit`, [fabric_records.py](../../../../backend/di/services/actions/fabric_records.py))
  opens cases from CSV rows, but has no column for the **actual disposition and realised value**, and opened cases are
  valued **now**, with industrial routes drawn from a random source seeded from the case id
  ([intake.py:12, 67](../../../../backend/di/services/cases/intake.py#L67)).
- **Missing:** a back-test dataset (historical returns with as-of date, actual route, actual recovery), valuing each at
  its as-of date with the market and demand of that date, the counterfactual "our route vs theirs" per row, uplift with
  confidence bands, and a report. The industrial valuer's random draws make a replay's uplift hard to defend; the
  back-test needs market inputs from the customer's data. Size **L**.

### 2.8 Agentic CRUD: the action catalogue

- **Count:** 131 declared actions: 76 from the demo's catalogue
  ([registry.py:63](../../../../backend/di/services/actions/registry.py#L63), `fixtures/golden/actions_catalog.json`)
  plus 55 declared in code (flow 12, workflow 9, org 9, source 5, model 4, task 4, access 3, agent 3, mapping 3,
  proposal 2, case.open 1). **12 have no handler** and answer `not_implemented` (501,
  [pipeline.py:222](../../../../backend/di/services/actions/pipeline.py#L222)): `analytics.query`, `audit.search`,
  `sources.health`, `sources.diagnose`, `mapping.suggest`, `mapping.apply`, `tables.suggestLinks`, `tables.describe`,
  `conflict.suggest`, `import.clean`, `event.explain`, `asset.summary`.
- **agent_allowed** ([catalog.py:40](../../../../backend/di/services/agents/catalog.py#L40)): not `system` and not a
  `FORBIDDEN_ACTIONS` prefix ([forbidden.py:10](../../../../backend/di/services/agents/forbidden.py#L10)). That gives
  **79 allowed, 52 forbidden**; 67 of the 79 have handlers.
- **Reachable by an agent today: 17 actions.** MCP's 12 tools reach 10 actions
  ([mcp/tools.py:56–69](../../../../backend/di/mcp/tools.py#L56)); the autopilot adds `case.reevaluate`
  ([case_autopilot.py:21](../../../../backend/di/services/agents/playbooks/case_autopilot.py#L21)); Ask adds six reads
  ([ask/tools.py:1–17](../../../../backend/di/services/ask/tools.py#L1)). Of these, four write: `evidence.request`,
  `decision.submit`, `instruction.resend`, `case.reevaluate`.

Per resource (C/R/U/D; ✔ handler exists and agent-allowed, ✖F forbidden for agents, — no action):

| Resource | Create | Read | Update | Delete | Notes |
|---|---|---|---|---|---|
| Workflows | `workflow.create`, `import`, `duplicate`, `plan`, `draft` ✔ | `workflow.validate`, `testRun` ✔; **list/get only as screen endpoints** (`/api/screens/workflows`), no read action | `workflow.save`, `draft.save`, `restore`, `applyFix`, `saveTemplate` ✔; `publish`, `setStatus` ✖F | `workflow.delete` ✖F; `draft.discard` ✔ | `run`, `reprocess` ✔. None exposed through MCP. |
| Decision flows (rules) | `flow.fork` ✔ | `flow.get`, `simulate`, `propose`, `suggestions` ✔ | `flow.saveDraft`, `submit` ✔; `approve`, `publish`, `reject`, `rollback` ✖F | `flow.discard` (draft) ✔; no flow delete | `get_decision_flow`, `propose_rule_change` are MCP tools (read). |
| Sources / connections | `source.update` (modes new/catalog/mcp) ✖F | `source.test`, `sandboxKey` ✖F (prefix `source.` even though they are reads); `sources.health`/`diagnose` not implemented; list only as screens | `source.update`, `pause`, `resume`, `reconnect` ✖F; **`credentials.rotate` ✔ (allowed: not under the `source.` prefix)** | `source.delete`, `disconnect` ✖F | `source.sync` ✖F. |
| Mappings | via `source.update` ✖F | `mapping.preview`, `catalogSuggest` ✔ | edit only via `source.update` ✖F; `mapping.revert` ✔; `mapping.apply`, `suggest` not implemented | — | An agent can revert a mapping but not edit one. |
| Source tables | — | `tables.describe` not implemented | `tables.update` ✔ | — | |
| Agents | `agent.register` ✖F | screens only (`/api/screens/agents`, `GET /api/agents/tools`) | `agent.update`, `setEnabled` ✖F | — | By design: only a person changes agents. |
| Cases | `case.open` ✔ | `cases.list`, `case.get`, `case.evidence`, `case.routes`, `case.trace`, `case.whatIf` ✔ | `case.reevaluate`, `decision.prepare`, `decision.submit`, `evidence.*`, `comment.add`, `scenario.save` ✔; `decision.approve/override/decline` ✖F | `scenario.delete` ✔; no case close or cancel action | Best covered resource. |
| Templates | — (packs are code + golden JSON) | `org.exportPack`, `previewPack` ✔ | — | — | `workflow.saveTemplate` covers workflow templates only. |
| Org units | `org.create` ✖F | `org.tree`, `pilotReport` ✔ | `org.update`, `move`, `setPilot`, `importPack` ✖F | — | |
| Users / access | — | `access.lookup`, `grants`, `myAccess` ✖F in the catalogue (prefix), though the pipeline lets reads through ([pipeline.py:134](../../../../backend/di/services/actions/pipeline.py#L134)) | `access.*` ✖F | `access.removeUser` ✖F | By design. |
| Tasks (job queue) | `task.enqueue` ✔ | REST `GET /api/v1/tasks` only | `task.retry`, `reprioritise` ✔ | `task.cancel` ✔ | |

**Gaps for ask 7:**
- Exposure, not permission, is the main gap: MCP tools generated from the catalogue (filtered by `agent_allowed` and the
  agent's `tools` allow-list, [mcp/policy.py:138](../../../../backend/di/mcp/policy.py#L138)). The JSON Schemas already
  exist ([catalog.py:27](../../../../backend/di/services/agents/catalog.py#L27)). **M** with tests.
- Read actions for workflows, sources, mappings and agents (today screen endpoints only, so invisible to tools). **S–M**.
- A `mapping.save` action separate from `source.update`, so an agent can propose a mapping edit (held for a person)
  without touching the connection. **S**.
- "Agents create sources" conflicts with the forbidden list (`source.`). Decision needed: keep it forbidden but let an
  agent **propose** (the hold-for-a-person path) a source draft. **S** once decided.
- Inconsistencies to fix: `credentials.rotate` is agent-allowed while every other change to a connection's settings
  (`source.update`, `pause`, `resume`, `reconnect`, `disconnect`, `delete`) is forbidden; `mapping.revert` and
  `tables.update`, which change a source's field mapping and table model, are agent-allowed too (corrected in
  verification, see V-verification.md);
  `source.test` and `access.lookup` are reads but marked not allowed in the catalogue; 12 catalogue entries advertise
  actions that answer 501. **S**.
- Per-agent credentials and OAuth for outside MCP clients (today `X-Agent` header on a person's token). **M**.

### 2.9 MCP tools

- **12 tools, hand-written**: the demo's ten (`TOOLS_BY_ID` from `fixtures/golden/tools.json`) plus two Modeler reads
  ([mcp/tools.py:36–51](../../../../backend/di/mcp/tools.py#L36)); each has a hand-written answer shaper and an
  `ACTIONS_OF` row. Server: official `mcp==2.3.0` low-level `Server`, stateless Streamable HTTP, bearer token
  ([mcp/server.py](../../../../backend/di/mcp/server.py)). The server refuses to start if a tool maps to a forbidden
  action.
- The tool catalogue (`GET /api/agents/tools`, [routes/agents.py:17](../../../../backend/di/routes/agents.py#L17)) lists
  all 131 actions as tools with schemas, but nothing serves them over MCP.

### 2.10 Adapter generation

What exists:
- **21 hand-written Python adapters** (`backend/di/connectors/adapters/`, 91–395 lines each), read and map.
- **ConfiguredAdapter** ([configured.py](../../../../backend/di/connectors/configured.py)): any HTTP JSON API described by
  a `source_connection` row: resources `{name, path, id_field, delta_param?, changed_field?}`, paging
  offset/page/cursor, auth none/api_key/bearer/basic/oauth_cc, delta cursors, retries on 429/5xx. **GET only.**
- **Catalogue templates** ([catalog.py](../../../../backend/di/connectors/catalog.py)) for 15 synthetic systems, with
  default mapping rows; `mapping.catalogSuggest` offers them with a sample read.
- **Discovery** ([discover.py](../../../../backend/di/connectors/discover.py)): table columns, types and FK suggestions
  from landed payloads. **Probe** (DNS, TLS, auth, permissions, sample read).
- **MCP-client sources** ([mcp_client.py](../../../../backend/di/connectors/mcp_client.py)): read one tool of an outside
  MCP server as a source.
- **source-sim generic mocks** from a `Spec` (auth, paging, resources, seed;
  [spec.py](../../../../source-sim/sim/generic/spec.py)), 17 specs, 1,010 lines in total.
- **Writes** are hand-written per system ([writers.py](../../../../backend/di/services/instructions/writers.py): order,
  pod, repair, transport, move, finance). A configured source can be an outbound target only in name: steps without a
  writer are acknowledged by the simulated adapter.

What an agent would need to add a system in hours:
1. OpenAPI (or sample payload) → a draft `source_connection` row (resources, paging, auth guess, id fields). **M**.
2. The same input → a source-sim `Spec` with a synthetic seed, so the new system is testable end to end. **S–M**.
3. Mapping suggestion onto `MODEL_FIELDS` (the demo's `mapping.suggest` is still unported) checked by
   `mapping.preview`. **M** (LLM-assisted, checked deterministically).
4. A path for the agent: today every `source.*` action is forbidden, so it must be a proposal held for a person.
5. Generic writes (configured POST/PUT with an idempotency header, a payload template from the instruction envelope).
   **L**.

### 2.11 Role-based Home vs Command Center

Two pages over largely the same data:
- Home: briefing, tasks, alerts, KPIs, activity, figures, reports, proposals
  ([routes/screens/home.py](../../../../backend/di/routes/screens/home.py),
  [screens/home.py:152 alerts, 297 kpis, 877 tasks](../../../../backend/di/services/screens/home.py#L877)).
- Command Center: layout per role (`CC_LAYOUT`, [command.py:115](../../../../backend/di/services/screens/command.py#L115)),
  KPI tiles (L302), exceptions (L1082), actions on me (L1451), handed off, outcomes, inbox (L1346), health.
- **Home's tasks and Command Center's "Actions on me" are the same function** (`aome_items`,
  [workspace.py:733](../../../../backend/di/repositories/workspace.py#L733)), as is the menu badge
  ([nav.py:186](../../../../backend/di/services/screens/nav.py#L186)). KPIs are computed twice, by different code.
  Alerts (Home) and exceptions (Command) overlap. Plus separate Tasks, Alerts and Reports pages.
- Frontend: [HomePage.tsx](../../../../frontend/src/pages/home/HomePage.tsx) and
  [CommandCenterPage.tsx](../../../../frontend/src/pages/command/CommandCenterPage.tsx), 2,417 lines across both folders.
- **Gap M:** one "My work" page per role (tasks + approvals + proposals + exceptions + conflicts in one list) with the
  role's KPI strip; Command Center sections become tabs or go. The demo has both pages, so this needs a decision-log
  entry for parity.

### 2.12 Fraud triage and financial reconciliation

- **Fraud: nothing.** No match for "fraud" anywhere in backend, source-sim or frontend. Pieces to build on: intake
  dedupe (same asset + reason opens one case, [intake.py:54–63](../../../../backend/di/services/cases/intake.py#L54)),
  the Optoro RMA facts (RMA id, reason code, receipt status, [optoro.py:1–20](../../../../backend/di/connectors/adapters/optoro.py#L1)),
  expected returns ([expected.py](../../../../backend/di/repositories/expected.py)), the conflict queue (sources that
  disagree, e.g. grade).
- **Financial reconciliation: partial.** S/4 journal entry post of the actual cost lines
  ([writers.py:320](../../../../backend/di/services/instructions/writers.py#L320)), read back into the canonical
  `outcome`; `outcome.confirm` by Finance ([execution.py:53](../../../../backend/di/services/actions/execution.py#L53));
  predicted vs actual and calibration. Missing: customer credit memo or refund, resale invoice and cash (these steps are
  acknowledged by the **simulated** adapter, backend-steps B13b), WMS stock value vs ERP, a variance queue, period close.

### 2.13 The agent runtime without an LLM, and where a loop plugs in

- **Today** ([runtime.py](../../../../backend/di/services/agents/runtime.py)): `start` creates an `agent_run` and an
  `agent.step` job (L50); `step` (L107) asks the playbook for the next step (`pb.next_step`, L123): `Call | Skip | Wait | Done`.
  A `Call` goes through `pipeline.invoke` as the person with the agent as preparer (kill switch, autonomy, org scope,
  run limits, forbidden list). A held write becomes a proposal and the run waits; `wake` (L154) and `resume_waiting`
  restart it when a person decides.
- **One playbook**, `case_autopilot`: evidence → request missing evidence → re-evaluate → submit → wait for approval
  → resend a failed instruction → done
  ([case_autopilot.py:49–69](../../../../backend/di/services/agents/playbooks/case_autopilot.py#L49)). Fully deterministic.
- **Where an LLM loop plugs in:** a second entry in `PLAYBOOKS` (L38) whose `next_step` asks a model which tool to call,
  with the tools = catalogue entries filtered by `agent_allowed` and the agent's allow-list; each tool call becomes a
  `Call`, a held answer a `Wait`. `GroqModel.answer` already runs a tool loop behind the `AskModel` port and could be
  reused, or replaced by Pydantic AI as decided in `../2026-11-agent-foundation.md` (deferred tools ↔ proposals). The
  forbidden-list import check (L40–L42) applies only to static `ACTIONS` tuples, so an LLM playbook must rely on the
  pipeline's step 6 at run time. Size **M** for one LLM playbook with tests and a fake model.

---

## 3. The 13 asks, one by one

### 1. Pitch flow, Studio first — Partial, **L**
- **Exists:** `workflow.plan` (one workflow from a sentence, §2.1); `flow.propose` (one rule, §2.2); `case.open` with
  the *Open case* block; the autopilot; `rank_routes` evaluates every route
  ([routes.py:63](../../../../backend/di/services/engine/routes.py#L63)); org packs bundle sources, mappings, workflows
  and flows as one JSON ([org_pack.py](../../../../backend/di/services/actions/org_pack.py)).
- **Partial:** IoT operating hours land in canonical but reach no decision; PLM gives BOM values, not RUL.
- **Missing:** "create a template for my AMS process" end to end: a planner that drafts an **org-pack-shaped** proposal
  (which adapters, which ingest workflows, which mappings, which flow and rules) for a person to confirm; AI field
  mapping; new template packs without code (paths, dimensions, guardrails, valuer config). Templates today are
  `BUILDERS` in code ([templates.py:215](../../../../backend/di/services/modeler/templates.py#L215)) and tool classes
  are the prototype's fixed `tool_fleet.CLS`.
- **Size:** M for "draft an org pack from a prompt, using existing templates"; L for data-defined new templates.

### 2. Humans approve, agents plan — Partial, **M**
- **Exists:** autopilot plans and submits; approval limits per role and self-approval (`access.setLimit`,
  `setSelfApprove`, [policy.py:152](../../../../backend/di/core/policy.py#L152)); out-of-office delegation; conflicts
  queue; proposals held for a person; agents never approve.
- **Missing:** routing to a person **because** of low model confidence (a route's `prob` exists in `ti_m` but drives
  nothing), an exceptions-only work queue, and a straight-through policy for low-value cases. The last one conflicts
  with "agents never approve": it needs a decision (a published policy rule that approves, journaled as the rule, not
  as an agent).
- No auto-run: a person starts each autopilot run (`agent.startRun`). A trigger "run autopilot on every new case" is
  missing. **S**.

### 3. Guardrails per asset type — Partial, **M**
- **Exists:** gates in code (§2.6), locked guardrails per pack with owners, business rules scoped by class/grade/site.
- **Missing:** a per-pack, per-class **required evidence** gate ("IT: erasure certificate before redeploy or scrap";
  "tools/motors: RUL and grade certificate before refurbish/redeploy") as data, checked against canonical
  `condition.certificates`; guardrail editing by owners (listed as a good-to-have). Device wipe is text-only.

### 4. Back-testing — Missing, **L** (§2.7)

### 5. Two pilot templates
- **(a) Tool-fleet AMS — Partial, M–L.** Grading is read (good). RUL is an input number, not derived; no
  wear-and-tear index; no contract-terms check ("may we refurbish and resell?") beyond the presence of a fleet contract
  or sales order; demand pools (lease contracts, sales orders) come from the prototype's sample world; explanations
  are value lines, not an RUL derivation. Needs: a contract entitlement fact and gate (S), an explainable RUL/wear
  calculation from `run_hours` + duty + PLM design life with its inputs shown (M), the customer's tool classes as data
  (M).
- **(b) Device trade-in — Partial, M (ML pricing L).** Price comes from a static channel-learning table `DST`
  ([device.py:36](../../../../backend/di/services/modeler/valuers/device.py#L36)); "ML" is not present
  (`FormulaPredictor` has the seam for a trained model, [predictor.py:1–8](../../../../backend/di/services/engine/predictor.py#L1)).
  Channel routing is per-lot scoring, not dynamic re-routing on live sell-through. No wipe gate.

### 6. Carbon on every disposition card — Partial, **S** (§2.5)

### 7. Agentic CRUD, the whole platform as MCP — Partial, **M** (§2.8, §2.9)

### 8. Adapter generation — Partial, **M** (writes **L**) (§2.10)

### 9. LLM resilience — Partial, **S** (§2.4)

### 10. Declarative workflow JSON — Partial, **S–M** (§2.3)
- Missing: a published JSON Schema (generated from the block catalogue), server-side `workflow.export`, import that runs
  `workflow.validate` and the block-settings checks and returns all problems (not the first), auto-layout when
  positions are missing, one shape for export and storage.

### 11. One role-based home — Duplicate, **M** (§2.11)

### 12. Connection workflows apart from decision rules — Mostly there, **S**
- Workflow Studio (`di/workflow/`) runs ETL; the Modeler (`di/services/modeler/`) holds policy. Overlap: Studio still
  offers **Decision** workflows (`TYPES["dec"]`, three decision graphs,
  [workflow_builder.py:152–161](../../../../backend/di/services/actions/workflow_builder.py#L152)) whose `tool` and `act`
  nodes the engine passes through without doing anything ([engine.py:30–32](../../../../backend/di/workflow/engine.py#L30)).
  They are demo parity, not behaviour. Hide or relabel them (decision-log entry) so business users meet rules in one
  place.

### 13. Positioning, deploy in under a week — Partial, **M**
- **Exists:** `trial/` package with start/stop/reset and a clean-install check; vendor-neutral fabric (21 adapters,
  configured adapter, MCP client, file drops); Postgres only.
- **Open:** B18 security review (auth, CORS, rate limits), per-agent credentials, a production LLM provider, the
  connection to a customer's real systems (every vendor here is a mock). "Under a week" for a real customer is
  **unconfirmed**: no deployment to a non-synthetic system has been done.

---

## 4. The four reverse-logistics stages

### A. RMA intake and fraud triage — intake Partial, fraud Missing
- **Exists:** `case.open` from `rma | lease_end | trade_in | contract_end | iot_alarm | manual` with dedupe
  ([intake.py:54](../../../../backend/di/services/cases/intake.py#L54)); the *Open case* workflow block
  ([blocks.py:184](../../../../backend/di/workflow/blocks.py#L184)); Optoro RMAs, receipts, ASNs; webhooks with
  per-source secret and dedupe; manual CSV import opens cases.
- **Missing:** RMA authorisation decision (approve/deny the return itself), warranty/serial/entitlement checks, fraud
  signals (serial mismatch, return frequency per customer, expected vs received item, refund before receipt), a triage
  score and hold. **M** for rule-based triage as gates + a held queue; **L** for a trained risk model.

### B. Warehouse receiving and grading — Mostly exists, **S–M**
- **Exists:** expected returns and `receiving.plan` ([workspace.py:533](../../../../backend/di/repositories/workspace.py#L533));
  warehouse roles with a warehouse lock; inspection reports (SafetyCulture) and repair-centre grading (Depot Repair as
  authority), conflicts on disagreement; `evidence.recordResult` and the `inspection.result` event
  ([decisions.py:524](../../../../backend/di/services/actions/decisions.py#L524)).
- **Missing:** a receiving discrepancy check (expected vs received: item, quantity, condition), a grade certificate
  as evidence (ties to ask 3), photo evidence beyond a count.

### C. Smart disposition and recommerce — Exists, gaps **M**
- **Exists:** six gates, seven industrial routes, ranking with tie-breaks, P10/P50/P90, pool optimisation, demand
  matching, what-if, business rules, maker-checker flows, shadow, simulation, three valuers, execution plans and cost
  traces, six real instruction writes to mocks.
- **Missing:** live market prices (industrial draws seeded noise; device uses a fixed table), an ML price model,
  re-routing when a listing does not sell (only modelled inside `dScore`), carbon for two of three packs.

### D. ERP/WMS financial reconciliation — Partial, **L** (§2.12)

---

## 5. Prioritised gap list (pilot-critical first)

| Rank | Gap | Why it is pilot-critical | Size |
|---|---|---|---|
| 1 | **Back-testing harness**: historical import with actual route and value, as-of valuation, counterfactual uplift report | The sales motion (ask 4); nothing like it exists | L |
| 2 | **Tool-fleet template on real inputs**: contract entitlement gate, explainable RUL/wear from `run_hours` + duty + PLM life, customer tool classes as data | Pilot template (a); today RUL is a typed number and classes are the prototype's | M–L |
| 3 | **Evidence gates per asset type** (erasure certificate for IT, RUL + grade certificate for tools/motors) as pack data | Ask 3; compliance exposure (Legal review) | M |
| 4 | **Carbon for every pack** with factor provenance | Ask 6; tool-fleet and device cards show 0 | S |
| 5 | **LLM model/provider chain** | Ask 9; one 429 drops every AI feature to rules | S |
| 6 | **MCP tools generated from the catalogue** + read actions for workflows, sources, mappings, agents + `mapping.save` | Ask 7; 17 of 79 allowed actions are reachable | M |
| 7 | **Workflow JSON Schema, validated import, auto-layout** | Ask 10; prerequisite for agent-generated workflows | S–M |
| 8 | **Device template pricing**: wipe gate, a trained price model behind `Predictor` | Pilot template (b) | M (L with ML) |
| 9 | **Confidence and value routing**, exceptions-only queue, autopilot on every new case | Ask 2 | M |
| 10 | **One "My work" home** | Ask 11; demo walk-through clarity | M |
| 11 | **Process-template drafting** ("create a template for my AMS process") as an org-pack proposal | Ask 1, the pitch | L |
| 12 | **Adapter from OpenAPI** (connection row + source-sim spec + suggested mapping), held for a person | Ask 8 | M |
| 13 | **LLM playbook** in the agent runtime behind the port | Ask 7's "by natural language" beyond Ask | M |
| 14 | **Fraud triage** (rules) | Stage A; only if the pilot covers intake | M |
| 15 | **Financial reconciliation** (credit memo, resale invoice, variance queue) | Stage D; only if the pilot covers finance | L |
| 16 | Per-agent credentials, OAuth for outside MCP clients, B18 security review | Before anyone outside the team connects an agent | M |

## 6. Quick wins (S, each a day or less unless noted)

1. **Model chain** in `get_model` and one shared `complete_json()` for `model_slots` and `modeler_read` (§2.4).
2. **Carbon factors** in the tool-fleet and device packs and a `co2` value line in both valuers (§2.5).
3. **Catalogue hygiene:** mark the 12 unimplemented actions `agent_allowed: false` (or implement the reads);
   decide whether `credentials.rotate` joins `FORBIDDEN_ACTIONS`; let read-only `source.test` and `access.lookup` show
   as allowed, matching the pipeline.
4. **JSON Schema** for the workflow export generated from `blocks.py`, served beside `/blocks`; validate
   `workflow.import` with `jsonschema` (already locked) and run `workflow.validate` on the imported graph; return all
   problems.
5. **Server-side `workflow.export`** read action (today the export exists only in the browser), so agents and MCP can
   read a workflow as JSON.
6. **Hide or relabel Studio's Decision workflows** (decision-log entry) so rules live only in the Modeler.
7. **Autopilot trigger**: start `case_autopilot` on `case.opened` for agents with autonomy `act` (behind a setting).
8. **`mapping.save`** split out of `source.update`, agent-allowed with hold-for-a-person.

---

## Sources read

`docs/agents/research/2026-11-platform/00-brief.md`, `AGENTS.md`, `docs/backend-steps.md` (B13–B17 and the plan-8
status), and the code cited inline. Action counts come from `fixtures/golden/actions_catalog.json` plus a scan of
`ACTIONS.setdefault`/`_declare` calls and `@implement` decorators under `backend/di` (24 Nov 2026); a runtime count
through `GET /api/agents/tools` was not taken (**unconfirmed** at runtime, expected 131).
