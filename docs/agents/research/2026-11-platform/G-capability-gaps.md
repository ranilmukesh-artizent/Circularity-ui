# G. Capability gaps: what the repo does against what the team wants next

> Plan task IDs (P9-x.y) in this report follow [plan 9 revision 2](../../plans/09-agentic-platform.md) (remapped 25 Nov 2026; its last table maps old to new).

Report G of the platform research (brief: [00-brief.md](00-brief.md)). Read from the code at `0c71585`
(`feature/fullstack-poc`, 24 Nov 2026). Nothing was run: no tests, no Docker, no git. Every claim cites the file and
line it comes from; links are relative to this folder (`../../../../` is the repo root). Anything I could not confirm
from the code is marked **unconfirmed**.

Sizes: **S** ≤ 2 days, **M** ≤ 1 week, **L** > 1 week (one engineer who knows the repo, tests included).

Compliance note: the data-erasure and certification items below touch regulatory obligations (data sanitisation,
certified recycling). §7 adds more (safety recalls, export control, vehicle title and liens, medical
decontamination and service certification, compliance guardrails that customers cannot weaken). Kinective's Legal
team should review those items before anyone relies on them.

## What changed in this revision and why (24 Nov 2026, second pass)

The team's Recover prototype (summarised in [01-recover-segments.md](01-recover-segments.md), cited "01 §n") is now
the target. The first pass measured the code against the 13 asks of the brief; this pass also measures it against 01.
The code read is the same as the first pass (the only later commit, `5b1fcfd`, is documentation; git was not run, so
this is **unconfirmed** but every new citation below was read from the working tree).

- **Added §7, "Against the Recover prototype (01)":** one table per area (Compose, customer layer, access from the
  identity provider, adapter registry, agents, models catalogue, tool-fleet flows and packs), each row with what 01 requires, what the code has (exists / partial / missing) with file:line, the gap,
  a size and a plan-9 placement (task ids from [plans/09-agentic-platform.md](../../plans/09-agentic-platform.md)).
  Reason: 01 turns the pack into the unit of everything (flow, guardrails, agents, systems, screens, KPIs), which the
  13 asks did not spell out.
- **Updated §1 (summary)** with one paragraph on 01. Reason: the headline changes: the biggest gap is no longer one
  feature but the missing *pack contract* that every Compose step and every run-time screen hangs off.
- **Updated §5 (prioritised gap list):** re-ranked, with 11 new rows from §7 and a "Source" column (ask number or
  01 section). The pack format moved to the top because Compose, the customer layer, pack-driven run-time views and the three
  new packs all depend on it. Back-testing stays near the top: 01's publish step needs the same replay.
- **Updated §6 (quick wins):** eight new items (9–16) found in §7.
- **Deleted:** nothing. The first-pass findings were verified ([V-verification.md](V-verification.md)) and still hold.
- Resolve and Reconcile removed (parked as out of scope, user decision 25 Nov 2026).

---

## 1. Summary

The POC is strong on the **decide → approve → execute** middle of the return (gates, valuers, ranking, maker-checker,
one action pipeline, instructions to mocks, outcomes). It is weak at both ends of the reverse-logistics chain (no
fraud triage, finance stops at a cost posting) and on everything **generative**: every "AI" feature today is a
deterministic parser that uses a language model only to settle what its keywords could not read. No agent creates or
edits a workflow, source, mapping or flow today; the action catalogue would allow most of it, but only 17 actions
are reachable from an agent path.

Against the Recover prototype (01, §7 below) the gap is mostly **structural**. 01 makes the *pack* the unit of
everything: seven stages with an agent each, typed guardrails placed at stages, the systems and canonical entities a
pack needs, its KPIs and exception types, its replay data, and the run-time screens generated from it. Today a
template is three fixed Python builders with paths, untyped guardrail texts and scope dimensions; the flow has one
guardrail gate and no stages; pages are fixed React screens shaped by the industrial demo. Much of the machinery 01
needs is already there in some form (maker-checker, version history, shadow decisions, pilot mode, per-agent
autonomy, a queue planner, a simulated directory with group-to-role mapping, encrypted credentials, discovery), so
the work is mostly re-shaping and wiring, plus three things that are genuinely new: the configuration agent, generated
screens, and the Service desk and Contract refresh flows. Two of 01's five packs exist (tool fleet, device); used
cars, telecom network equipment and medical rental have nothing, and about half of the systems they need have no mock.

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

Re-ranked in the second pass to include 01 (§7). "Source" is the brief's ask number or the 01 section; the §7 row ids
(C1, L2 …) point at the evidence.

| Rank | Gap | Why it is pilot-critical | Source | Size |
|---|---|---|---|---|
| 1 | **Pack format v1 carrying 01's pack contract**: stages (the seven), typed guardrails placed at stages, routes, systems with adapter status, canonical entities, KPIs, exception types with owners, sample prompts, replay dataset, a version (§7.8 P0, §7.2 L1) | Compose, the customer layer, pack-driven run-time views and the three new packs all hang off it; today a template is a code builder with no stages, types or version | 01 §9; ask 1 | L |
| 2 | **Back-testing and replay**: historical import with actual route and value, as-of valuation, counterfactual uplift; the same engine reports 01's route mix, straight-through %, approvals and exceptions per day (§2.7, §7.1 C10) | The sales motion and Compose's publish step | ask 4; 01 §2 step 5 | L |
| 3 | **Stage agents**: one named agent per stage bound in the flow, autonomy Recommend only / Act within limits / Act alone, a confidence threshold that sends the item to a person, and a live queue planner (§7.5, §7.1 C7) | "Humans approve, agents plan"; today one playbook, no stage binding, no threshold, the queue plan sees each live case alone (a queue of one) | ask 2; 01 §3 | L (M for threshold + queue planner) |
| 4 | **Tool-fleet template on real inputs**: contract entitlement gate, explainable RUL/wear, customer tool classes as data, named demand from live sources, 01's guardrails (recall, telematics freshness, repair limit, early write-off) (§3 ask 5a, §7.8 P1) | Pilot template (a) | ask 5a; 01 §4.1 | M–L |
| 5 | **Customer layer**: pack updates never overwrite customer changes (overlay on a pinned pack version), compliance guardrails tighten-only, diversions that run at a stage for a condition and are blocked when they skip a compliance guardrail (§7.2) | 01's governance story; today steps added by the assistant are drawn but never executed | 01 §2 extensions; ask 3 | M–L |
| 6 | **Evidence gates per asset type** (erasure certificate for IT, RUL + grade certificate for tools/motors, blacklist/lock for devices) as typed pack guardrails | Compliance exposure (Legal review); merges with rank 5's typed guardrails | ask 3; 01 §4–5 | M |
| 7 | **Compose configuration agent**: description → matching pack → one clarifying question → draft flow, adapter list and KPIs, with its reading log (§7.1 C1–C3) | The pitch, Studio first | ask 1; 01 §2 step 1 | L |
| 8 | **Adapter-mapping step**: per-field confidence with a reason, the five person choices (accept, other field, conversion, not needed, ask the owner), system-owner approval, test-then-production, discovery on 500 records (§7.1 C4–C5, §7.4) | Compose step 2; today confidence is a constant and "ask the owner" / "not needed" do not exist | ask 8; 01 §2 step 2 | M |
| 9 | **Canary publish**: one region at a share of volume, compared with the rest (§7.1 C9) | Compose step 5; today shadow (all cases, no effect) and pilot (all instructions held) only | 01 §2 step 5 | M |
| 10 | **Sign-in from the identity provider**: OIDC, group claims to roles, sync, a role × permission matrix and "test a user" (§7.3) | Any customer pilot; today any password signs in and the directory is seeded state | 01 §2 access; ask 13 | M |
| 11 | **Decide and Understand driven by pack data** (cases, exceptions with types and owners, KPIs, suggestion rules, analytics questions, agents) with no screen code per pack (§7.1 C11). A capability, not the prototype's layout (01 is a concept share) | 01's "one engine for every industry pack"; today pages are fixed and industrial-shaped | 01 §2, §9 | L |
| 12 | **Carbon for every pack** with factor provenance | Tool-fleet and device cards show 0 | ask 6 | S |
| 13 | **LLM model/provider chain** | One 429 drops every AI feature to rules | ask 9 | S |
| 14 | **Model catalogue with quality, drift, last-trained and cadence** for six models; the models themselves (§7.6) | 01's Models page; today seven reference cards with fixed figures, plus calibration candidates | 01 §3 | S–M registry; L models |
| 15 | **Device template pricing**: wipe gate, a trained price model behind `Predictor`, ageing suggestion rules (§7.7 T4) | Pilot template (b) | ask 5b; 01 §5 | M (L with ML) |
| 16 | **Exceptions routed by role per pack** with cause, recommended action and owner; inside one "My work" home (§2.11, §7.7 T5) | Asks 2 and 11; 01's Decide · Exceptions | ask 11; 01 §2 | M |
| 17 | **MCP tools generated from the catalogue** + read actions for workflows, sources, mappings, agents + `mapping.save` | 17 of 79 allowed actions are reachable | ask 7 | M |
| 18 | **Workflow JSON Schema, validated import, auto-layout** | Prerequisite for agent-generated workflows | ask 10 | S–M |
| 19 | **Service desk** flow: ticket → estimate from similar past repairs, cover check, per-market labour and credit rules, fix / covered swap / upgrade, batches, credit lever (§7.7 T1) | Tool-fleet extra in 01; nothing exists | 01 §4.2 | L (M rules-only) |
| 20 | **Contract refresh** flow: proposal 90 days ahead, keep / like-life swap / upgrade, fee and renewal likelihood, sales approval, email + contract lines + reservation (§7.7 T2) | Tool-fleet extra in 01; nothing exists | 01 §4.3 | L |
| 21 | **Analytics by prompt**, saved shared views, alerts on a measure (§7.7 T6) | 01's Understand · Analytics; `analytics.query` answers 501 | 01 §2 | M–L |
| 22 | **Adapter from OpenAPI** (connection row + source-sim spec + suggested mapping), held for a person | Adapters in hours | ask 8; 01 §2 extensions | M |
| 23 | **LLM playbook** in the agent runtime behind the port | Agentic CRUD beyond Ask | ask 7 | M |
| 24 | **Three new packs**: used cars, telecom network equipment, medical rental, with their missing mocks (§7.8) | 01's segments 3–5; after rank 1 | 01 §6–8 | L each |
| 25 | **Fraud triage** (rules) | Stage A; only if the pilot covers intake | stage A | M |
| 26 | **Financial reconciliation** (credit memo, resale invoice, variance queue) | Stage D; only if the pilot covers finance | stage D | L |
| 27 | Per-agent credentials, OAuth for outside MCP clients, B18 security review | Before anyone outside the team connects an agent | ask 13 | M |

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

Added in the second pass (from §7):

9. **Guardrail type** (`Compliance | Data quality | Threshold | Approval`) and a `stage` on the 17 existing guardrails
   (`Guardrail`, [templates.py:52](../../../../backend/di/services/modeler/templates.py#L52);
   [industrial.json:14–20](../../../../backend/di/services/modeler/packs/industrial.json)). Data only, no decision
   changes; the first step of pack format v1.
10. **Pin a sent-back change to a step:** an optional `node_id` on `flow.reject` (today `{flow_id, reason}`,
    [modeler.py:13](../../../../backend/di/services/actions/modeler.py#L13)), shown on that node in the canvas.
11. **Access: role × permission matrix and "Test a user"** as one read action over the policy and the directory
    (`policy.idp_role_of`, [policy.py:280](../../../../backend/di/core/policy.py#L280)); the Access page has only the
    per-account "What the role does" column ([AccessPage.tsx:58](../../../../frontend/src/pages/access/AccessPage.tsx#L58)).
12. **Enforce read-only sources:** refuse an outbound instruction to a source whose access is "Read" (today `rw` is a
    label, [fabric_sources.py:381](../../../../backend/di/services/actions/fabric_sources.py#L381)).
13. **Discovery sample 200 → 500 records** ([discover.py:31](../../../../backend/di/connectors/discover.py#L31)), as 01
    states; check the discovery tests for counts first.
14. **Fit-for-use threshold as a Quality-owned setting** changed through maker-checker (today `rulMin` 50 in
    `BASEP`, [tool_fleet.py:167](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L167), protected only by
    guardrail GR-03's text pattern). Changing the default changes tool-fleet numbers: decision-log entry first.
15. **Seeded agents' tool lists:** four of the ten seeded agents list tools that answer 501 (§7.5); drop those tools or
    implement the reads, together with quick win 3.
16. **What-if over the tool-fleet queue:** pass `BASEP` overrides (market, labour, lease, slots) through
    `flow.simulate` so a person can "move the market, see decisions change" (§7.7 T3). **S–M**.

---

## 7. Against the Recover prototype (01)

What 01 requires, what the code has, the gap, the size and where it fits in the draft
[plan 9](../../plans/09-agentic-platform.md) (task ids `P9-x.y`; "new" means plan 9 has no task for it yet). State:
**exists**, **partial** or **missing**. Every citation was read for this pass.

### 7.1 Compose (01 §2, the five steps)

| Id | 01 requires | Today | Gap | Size | Plan 9 |
|---|---|---|---|---|---|
| C1 | A *configuration agent* reads a description (with a reading log), matches an industry pack and lists asset fields, stages, routes, guardrails (stated + pack), systems (with adapter or needing one) and KPIs. "Writes configuration, never code." | **Missing.** Two keyword parsers: `workflow.plan` drafts **one ingest/outbound workflow** for systems already connected ([workflow_builder.py:7](../../../../backend/di/services/actions/workflow_builder.py#L7), §2.1); `flow.propose` turns a sentence into **one rule or one step** ([propose.py:1–10](../../../../backend/di/services/modeler/propose.py#L1), §2.2). Nothing picks a pack from words; the packs are three fixed keys ([templates.py:20](../../../../backend/di/services/modeler/templates.py#L20)). | A pack-matching agent that emits a draft *composition* (pack id + overrides: stages, routes, guardrails, systems, KPIs) as data, checked deterministically, with its reading log. Needs the pack format (§7.8 P0) first. | L | P9-2.6 (pack drafting), after P9-1.1 |
| C2 | Exactly **one** clarifying question. | **Partial.** `workflow.plan` asks slot questions (type, system, delivery, trigger …), as many as it needs ([workflow_builder.py:28](../../../../backend/di/services/actions/workflow_builder.py#L28)). | Pick the one most ambiguous slot for the pack; the rest take the pack's defaults. | S (inside C1) | P9-2.6 |
| C3 | Drafts the flow in the modeler. | **Partial.** A flow is a fork of the template's default graph (`flow.fork`, [modeler.py:238](../../../../backend/di/services/actions/modeler.py#L238)); the assistant edits it one rule at a time. The graph has no stages: one locked `guard` node and fixed node types ([flow.py:16–17](../../../../backend/di/services/modeler/flow.py#L16)). | Generate the seven-stage graph with stage agents and guardrails placed at stages. | M | P9-2.6 + P9-5.8 |
| C4 | Adapter mapping: each field proposed from the connected systems **with a confidence score**; a low-confidence field carries a **reason**. | **Partial.** `mapping.catalogSuggest` offers a catalogue template's rows with one sample value and a **constant** confidence (96 % for a copy rule, else 91 %; [fabric_sources.py:596, 642](../../../../backend/di/services/actions/fabric_sources.py#L642)); no reason text; `mapping.suggest` (the demo's free suggestion) answers 501 (§2.8). | Confidence from evidence (name, type, sample values, documentation), a reason for anything below a bar, mapped to the pack's canonical entities. LLM-assisted, checked by `mapping.preview` ([fabric_sources.py:919](../../../../backend/di/services/actions/fabric_sources.py#L919)). | M | P9-5.1 |
| C5 | Five person choices per field: accept, choose another field, accept with a conversion, mark not needed, **ask the system owner**. | **Partial.** Accept (the "Accepted from the agent's suggestion" note, [fabric_sources.py:72](../../../../backend/di/services/actions/fabric_sources.py#L72)), choose another field and conversions (mapping rules) exist through the Data Mapping tab via `source.update`. "Not needed" and "ask the owner" do not. | A per-field decision record; "ask the owner" opens a task for the source's owner and holds the composition. | S–M | P9-0.6 (`mapping.save`) + P9-5.1 |
| C6 | A **test run** puts past items through the draft flow and shows **where cases stopped**. | **Partial.** `workflow.testRun` runs one ingest workflow on sample records ([workflow_drafts.py:167](../../../../backend/di/services/actions/workflow_drafts.py#L167)); `flow.simulate` compares the draft's route choice with the published one on the open or sample queue ([modeler.py:431](../../../../backend/di/services/actions/modeler.py#L431)). Neither reports the stage each case reached or what stopped it (missing field, guardrail, threshold). | A stage-by-stage trace per past item over the draft composition, grouped by stop reason. Reuses the back-test import. | M | P9-4.1/3.2 + new |
| C7 | Agent mapping: an agent per stage, autonomy per agent **Recommend only / Act within limits / Act alone**; a **confidence threshold** (65–85 %, default 75 %) below which any agent sends the item to a person; guardrails enforced whatever the autonomy. | **Partial.** Per agent: autonomy `read | propose | act` ([0023_agent_identity.py:34–35](../../../../backend/migrations/versions/0023_agent_identity.py#L34)); per role and action type: `off | suggest | prepare | act`, plus run limits of 50 actions and 100 items ([limits.py:34–35](../../../../backend/di/services/agents/limits.py#L34)). Guardrails and the forbidden list hold whatever the autonomy (§2.8). No stage binding; no confidence threshold (a route's `prob` drives nothing, §3 ask 2). | Map Recommend only → `propose`, Act within limits → `act` + value/count limits + approval limits ([policy.py:152](../../../../backend/di/core/policy.py#L152)), Act alone → `act`; a `stage → agent` binding in the flow; a per-flow threshold checked in the pipeline's hold step. | M | P9-2.4 (hold policy) + new |
| C8 | Approve or modify: the approver sees steps 1–3 together and can send it back **with a change pinned to the step**; maker-checker. | **Mostly exists for the flow.** Maker-checker: whoever saved or submitted cannot approve or publish ([modeler.py:156, 175](../../../../backend/di/services/actions/modeler.py#L156)); reject with a reason ([modeler.py:299](../../../../backend/di/services/actions/modeler.py#L299)). Sources, mappings and agents are approved separately or not at all. | Pin the reason to a node (quick win 10, **S**); one *composition* object approved as a whole (**M**). | S / M | new (phase 4) |
| C9 | Publish v1.0 to **one region at 20 % of volume**. | **Partial.** A flow is per template **and org unit** ([models/modeler.py:22–38](../../../../backend/di/models/modeler.py#L22), unique on both), so "one region" can be a `segment` or `site` unit (kinds: group, segment, company, site, customer; [orgs.py:27](../../../../backend/di/services/actions/orgs.py#L27); no "region" kind). **Shadow** records, for **every** case of the unit, what the approved flow would have chosen beside the live decision, with no effect ([decisions.py:207–217](../../../../backend/di/services/actions/decisions.py#L207)). **Pilot mode** keeps deciding but holds **every** instruction of the unit's subtree ([org_pilot.py:1–15](../../../../backend/di/services/actions/org_pilot.py#L1)). Neither splits volume. | A canary state: a deterministic share of the unit's cases (hash of case id) decided by the new version for real, the rest by the old, with the comparison kept per case (the `shadow_decision` shape fits). | M | new (phase 4, beside P9-2.4) |
| C10 | A **replay** compares the route mix (actual against flow) and reports straight-through %, approvals and exceptions per day, modelled uplift. | **Partial.** Shadow stats give count, agree/disagree and the summed net difference ([flows.py:80–91](../../../../backend/di/repositories/flows.py#L80)); simulation gives route changes. No route-mix table, no straight-through %, no per-day approval or exception load, and no "actual" (§2.7). | Same engine as back-testing, plus the four 01 measures. | M on top of P9-3 | P9-4.2/3.3 |
| C11 | **Publishing makes the run-time views pack-driven**: Decide (cases, exceptions, suggestions) and Understand (analytics, agents) take their KPIs, exception types and questions from the pack. A capability, not the prototype's layout. | **Missing.** Pages are fixed React areas loaded by id ([registry.tsx:12](../../../../frontend/src/pages/registry.tsx#L12)); Home, Command Center and Analytics compute the industrial demo's KPIs and exceptions (§2.11). Tool-fleet and device cases use the generic case page. | Pack-driven screen configuration (KPIs + trend, exception types with owners, two analytics questions, the agents of the flow) rendered by one set of generic pages. | L | new (phase 4), with P9-5.8 |
| C12 | Version history: each version with its audit log. | **Exists for the flow.** `decision_flow_version` ([models/modeler.py:41–50](../../../../backend/di/models/modeler.py#L41)); the History panel lists versions, the flow's log and rollback ([HistoryPanel.tsx:13–27](../../../../frontend/src/pages/modeler/HistoryPanel.tsx#L13)). | Version the whole composition (flow + mappings + agent settings + screens), not the flow alone. | S–M | with C8 |

### 7.2 Customer layer (01 §2 extensions; every pack §4–8 "diversions")

| Id | 01 requires | Today | Gap | Size | Plan 9 |
|---|---|---|---|---|---|
| L1 | **Pack updates never overwrite the customer's changes.** | **Partial, by accident.** An org's flow is its own copy (fork), so a later default graph does not replace it. But paths, guardrails, dimensions and valuers are code (`BUILDERS`, [templates.py:215](../../../../backend/di/services/modeler/templates.py#L215)); a `Template` has no version ([templates.py:98–106](../../../../backend/di/services/modeler/templates.py#L98)); a change ships to every org at once, and an imported org pack lands as drafts ([org_pack.py:22–25](../../../../backend/di/services/actions/org_pack.py#L22)), not as a layer. | Pack versions; the customer layer stored as an overlay (diff) on a pinned pack version; an upgrade rebases the overlay and shows conflicts to a person. | M–L | P9-1.1 (add to its scope) |
| L2 | Guardrails typed *Compliance / Data quality / Threshold / Approval*; a guardrail can be **tightened** or given an **extra approver**; pack-locked compliance guardrails **cannot be weakened, suspended or removed**. | **Partial.** Guardrails are locked texts with an owner ([templates.py:52–58](../../../../backend/di/services/modeler/templates.py#L52)): a rule that breaks one is blocked and dropped at compile ([guard.py:20](../../../../backend/di/services/modeler/guard.py#L20), [compile.py:36–41](../../../../backend/di/services/modeler/compile.py#L36)); a plain-language text that would weaken one is blocked by regex ([guard.py:34](../../../../backend/di/services/modeler/guard.py#L34)). No type, no parameter (the fit-for-use 50 % is a valuer constant, [tool_fleet.py:166](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L166)), no "tighten" or "add approver" operation. | Typed guardrails with a structured parameter and a direction (raise-only / lower-only), an extra-approver list, and refusals for weaken/suspend/remove of a compliance one. | M | P9-1.2 |
| L3 | **Diversions**: add a step or a shortcut at a stage **for a condition**; a diversion that skips a compliance guardrail is **blocked** (e.g. "new tool under 3 months: skip the recall check"). | **Partial, and not executed.** The assistant adds a `step` node after a path ("add … step before/for/after …", [propose.py:28, 74–90](../../../../backend/di/services/modeler/propose.py#L74)), with no condition; **nothing runs it**: compile reads only `rule` nodes ([compile.py:36–41](../../../../backend/di/services/modeler/compile.py#L36)) and no other code reads `step` nodes. No shortcuts. Blocking works only by text pattern: the device wipe guardrail blocks "skip … wipe" ([templates.py:125](../../../../backend/di/services/modeler/templates.py#L125)), but there is no recall, blacklist, title, configuration-wipe or decontamination guardrail to protect. | A diversion node (condition from scope dimensions + an inserted step or a jump to a later stage); a graph check that refuses a diversion whose path bypasses a compliance gate (the `reach` check compile already uses); execution in the case process. | M–L | P9-5.8 (case process layer) |
| L4 | **Guardrails in plain words**: the assistant places a typed control on the right stage; screens, inbox, audit trail and KPIs update with it. | **Missing.** Plain words become a business rule only (`exclude / require / prefer`, §2.2); guardrails cannot be authored; there are no stages to place them on. | A guardrail reading into the typed form of L2, placed at a stage, with "% held by guardrails" (a KPI in every 01 pack) counted per guardrail. | M | P9-1.2 + P9-2.6 |

### 7.3 Access from the identity provider (01 §2 "Access")

| Id | 01 requires | Today | Gap | Size | Plan 9 |
|---|---|---|---|---|---|
| A1 | Directory groups map to roles. | **Exists as a simulation.** Group-to-account table `IDP_GROUPS` ([policy.py:252–263](../../../../backend/di/core/policy.py#L252)), `access.mapIdentity` ([policy.py:288](../../../../backend/di/core/policy.py#L288)), role source "Directory groups" or "App Roles" ([AccessPage.tsx:145–153](../../../../frontend/src/pages/access/AccessPage.tsx#L145)). The directory is seeded state, not read from a provider. | Read groups from a real provider. | in A2 | — |
| A2 | Members get access on the next sync. | **Simulated.** `access.syncDirectory` only stamps `lastSync` and journals ([access.py:320–325](../../../../backend/di/services/actions/access.py#L320)). Sign-in accepts any non-empty password for a known ID ([services/auth.py:11–21](../../../../backend/di/services/auth.py#L11)); OIDC is named as the later replacement ([core/auth.py:3–5](../../../../backend/di/core/auth.py#L3)). | OIDC sign-in (Keycloak as the local stand-in), group or app-role claims → roles at sign-in, optional SCIM provisioning. | M | P9-8.2 (extend), but pilot-critical |
| A3 | A "what each role can do" matrix. | **Partial.** One row per account with "What the role does" ([AccessPage.tsx:58](../../../../frontend/src/pages/access/AccessPage.tsx#L58)); permissions live in `policy.json`. | A role × permission (and page) matrix. | S | quick win 11 |
| A4 | "Test a user". | **Missing.** | A read action: pick a directory user, show their roles, tenants, pages and permissions. | S | quick win 11 |

### 7.4 Adapter registry (01 §2 extensions)

| Id | 01 requires | Today | Gap | Size | Plan 9 |
|---|---|---|---|---|---|
| R1 | Catalogue connectors maintained by us. | **Exists.** 21 hand-written adapters, catalogue templates for 15 systems (§2.10), 15 catalogue mocks in source-sim ([generic/specs/](../../../../source-sim/sim/generic/specs)). | — | — | — |
| R2 | A generic REST adapter. | **Exists, read only.** `ConfiguredAdapter`, GET only (§2.10). | Generic writes. | L | P9-5.1 (later) |
| R3 | A connector built once from an API specification. | **Missing** (§2.10). | OpenAPI → connection row + source-sim spec + mapping draft. | M | P9-5.1 |
| R4 | Sign-in by OAuth 2.0, service account or API key. | **Exists.** none / api_key / bearer / basic / oauth_cc (§2.10). | — | — | — |
| R5 | Test environment first, then production. | **Partial.** `env` is a free label, default "Production" ([fabric_sources.py:68, 135](../../../../backend/di/services/actions/fabric_sources.py#L135)); catalogue systems have a sandbox key ([fabric_sources.py:647](../../../../backend/di/services/actions/fabric_sources.py#L647)); `source.test` probes one connection ([fabric_sources.py:870](../../../../backend/di/services/actions/fabric_sources.py#L870)). | Two connections per source (test, production) with separate credentials and a promote step. | S–M | new (with P9-5.1) |
| R6 | Read-only, or read plus writing decisions back. | **Partial.** `rw` is a label ("Read", "Read / write", [fabric_sources.py:381, 554](../../../../backend/di/services/actions/fabric_sources.py#L381)); writes are hand-written per system (§2.10). | Enforce it (quick win 12). | S | Phase 0 |
| R7 | Credentials go to the vault and are never shown again. | **Exists in-house.** Fernet at rest, the plain value only to the connector, never journaled or sent to the browser ([secrets.py:1–13](../../../../backend/di/connectors/secrets.py#L1)). Whether customers need an external vault (cloud key vault) is **unconfirmed**. | Optional external-vault port. | M if needed | — |
| R8 | The **system owner approves** the connection. | **Missing.** `owner` is a text field ([fabric_sources.py:380](../../../../backend/di/services/actions/fabric_sources.py#L380)); a person with the permission connects directly. | A held connection that the named owner (a directory user) approves; reuse the proposal/maker-checker pattern. | S–M | new (with P9-5.1) |
| R9 | Discovery reads objects and fields, **samples 500 records** and proposes mappings. | **Partial.** Discovery samples the newest **200** landed records per resource and proposes tables, columns, types and foreign keys ([discover.py:6–9, 31](../../../../backend/di/connectors/discover.py#L31)); mapping proposals only from catalogue templates (C4). | 500 (quick win 13); mapping proposals from the samples (C4). | S / M | P9-5.1 |

### 7.5 Agents (01 §3)

01 names a **seven-agent decision chain** for the tool fleet and **six stage agents** for Compose. Today ten agents are
seeded ([0023_agent_identity.py:41–54](../../../../backend/migrations/versions/0023_agent_identity.py#L41)): Evidence
Assembler, Opportunity Finder, Gap Requester, Handoff Coordinator, Reconciler, Briefing Agent, Analytics Explainer,
Integration Assistant, Audit Assistant, Ask. They are tool allow-lists, not stage owners; the runtime has **one**
playbook ([runtime.py:38](../../../../backend/di/services/agents/runtime.py#L38),
[case_autopilot.py:20–22](../../../../backend/di/services/agents/playbooks/case_autopilot.py#L20)).

| 01 agent (Compose name, default autonomy) | Today | State | Gap | Size | Plan 9 |
|---|---|---|---|---|---|
| 1 Intake (Intake, act alone) | `case.open` with dedupe and the *Open case* workflow block (§4 A); a workflow step, no agent. | Partial | Name an Intake agent that runs on return events; per-pack event types. | S | P9-2.1 |
| 2 Condition and life (Condition, act within limits) | Grade **read** from the inspection app and the repair centre (§2.6); tool-fleet RUL is an input number; the grade falls back to `estGrade` ([templates.py:136](../../../../backend/di/services/modeler/templates.py#L136)) but is not shown as an estimate. | Partial | Agent + explainable RUL/wear; "estimate" label when the workbench grade is late. | M | P9-3.1 |
| 3 Demand discovery (part of Valuation/Routing) | Opportunity Finder (`find_demand`). In the tool fleet, named demand (renewals, orders, pool requests, open repair orders) exists only in the generated sample world ([tool_fleet.py:970](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L970)) or in intake facts a caller passes as `dem` ([intake.py:172–174](../../../../backend/di/services/cases/intake.py#L172); no source fills it); a live case is decided "in a queue of its own (no sample orders)" ([intake.py:233–239](../../../../backend/di/services/cases/intake.py#L233)). | Partial | Demand as canonical records from the lease, ERP, pool and repair-order sources (the `demand` model exists, [schema.py:41–43](../../../../backend/di/services/canonical/schema.py#L41)), read per org. | M–L | new (phase 2) |
| 4 Fit-for-use | The rule is in the valuer: a harvested part counts only at or above `rulMin` ([tool_fleet.py:526–529](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L526)); guardrail GR-03 says Quality owns the threshold. No agent; the threshold is a constant. | Partial | Agent + Quality-owned threshold (quick win 14). | S | P9-1.2 |
| 5 Valuation (Valuation, act alone) | Three valuers (industrial predictor, tool fleet, device). | Exists | Carbon in two of three (§2.5). | S | P9-0.3 |
| 6 Disposition, whole-queue plan (Routing, act within limits) | `plan_queue` fills each named order once and keeps refurbishment within repair slots ([tool_fleet.py:684, 1089–1090](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L1089)), used by the sample world and simulation only; live cases are planned alone (row 3). Industrial: `pool.optimize` per pool ([engine.py:25–40](../../../../backend/di/services/actions/engine.py#L25)). | Partial | A `queue_planner` playbook over the live open queue per org, re-planned on each arrival, explained against the standard route. | M | new (next to P9-2.1) |
| 7 Follow-through (Follow-through, act within limits) | Handoff Coordinator; the autopilot resends a failed instruction; execution plans and instructions (§4 C). | Exists | "Reminds the owner": a timed task when an instruction or approval waits. | S | P9-2.1 |
| — Analytics (act alone) | Analytics Explainer and Briefing Agent, whose `analytics.query` answers 501. | Partial | See T6. | M | — |

Runtime gaps: stage binding and the confidence threshold (C7); an LLM loop (§2.13, P9-2.2); the autopilot never starts
on its own (§3 ask 2). **Surprise:** four seeded agents list tools that answer 501: Integration Assistant
(`sources.health`, `mapping.suggest`, `tables.suggestLinks`, `import.clean`), Briefing Agent and Analytics Explainer
(`analytics.query`), Audit Assistant (`audit.search`) ([0023_agent_identity.py:49–53](../../../../backend/migrations/versions/0023_agent_identity.py#L49)
against §2.8's list). The Agents page therefore shows capabilities that do not work (quick win 15).

### 7.6 Models catalogue (01 §3)

A catalogue already exists **as reference cards**: seven models with fixed versions and fixed validation lines (resale-price's line is measured on reconciled decisions)
(condition-vision, rul-survival, demand-match, resale-price, prep-cost-time, service-exposure, repair-success;
[orchestration.py:93–101, 693–701](../../../../backend/di/services/screens/orchestration.py#L93)). Only resale-price,
prep-cost-time and service-exposure take their version from reconciled decisions
([orchestration.py:686](../../../../backend/di/services/screens/orchestration.py#L686)). Real learning is the
calibration candidates: `model.fit` on Finance-confirmed outcomes, MAE as the metric, propose and promote under
maker-checker, agents forbidden ([models.py:1–14, 122](../../../../backend/di/services/actions/models.py#L1)). Every
prediction is a formula behind the `Predictor` seam ([predictor.py:1–8](../../../../backend/di/services/engine/predictor.py#L1)).

| 01 model | Today | State | Gap | Size |
|---|---|---|---|---|
| Condition estimate (classifier; fallback only when the workbench grade is late; always labelled) | Card only; `estGrade` field in the tool fleet, unlabelled. | Missing | Rule-based estimate from telemetry and repair history, labelled; a trained classifier later. | M / L |
| Remaining-life estimator (survival; per tool and per part) | Card only; RUL is an input; per-part RUL is input data. | Missing | Explainable wear index first (P9-3.1), survival model later. | M / L |
| Demand forecaster (time series per path) | "demand-match" card is a matcher, not a forecaster. | Missing | Per-path demand series from canonical `demand`. | L |
| Resale price estimator (gradient boosting) | Formulas + calibration factors; device uses a fixed table (§3 ask 5b). | Partial | P9-3.4 (LightGBM + intervals). | L |
| Refurbishment cost estimator (regression) | Formulas; prep-cost-time card versioned from reconciled cost lines. | Partial | Regression on depot-repair actuals. | M–L |
| Disposition optimiser (constrained, over the queue; learns from every closed outcome) | `plan_queue` and `pool.optimize`, no learning. | Partial | Live queue planner (§7.5 row 6); learning from outcomes later. | M / L |
| Quality, drift, last-trained date, retraining cadence per model | MAE on calibration candidates; no drift, no trained date on cards, no cadence. | Partial | One model registry for all six (metrics, trained_at, cadence, input and residual drift), the cards read from it. Thresholds and factor tables change only with a person's approval: true for calibration, not for valuer constants (code). | S–M |

### 7.7 Tool-fleet flows and run-time features (01 §2, §4.2, §4.3, §5)

| Id | 01 requires | Today | State | Gap | Size | Plan 9 |
|---|---|---|---|---|---|---|
| T1 | **Service desk**: every ticket → intake, estimate from **similar past repairs** (family, age band, fault, 3 years; ≥ 50 matches priced without a technician; accuracy on held-out repairs), cover check, per-market labour rates, price lists and **credit rules**, options fix / covered swap / upgrade with credit (upgrade only past 50 % life or when cover allows), **batches** (e.g. 22 tools split 9/11/2), a **credit lever** using 24 months of offer take-up. | Nothing. The ServiceNow mock exists as a source ([vendors/servicenow/](../../../../source-sim/sim/vendors/servicenow)) and the Depot Repair mock holds repair orders, tasks, hours and parts ([depot_repair/__init__.py:1–3](../../../../source-sim/sim/vendors/depot_repair/__init__.py#L1)); whether its seed has enough history for ≥ 50 similar repairs is **unconfirmed**. No markets, no cover terms, no credit. | Missing | A ticket case type, a nearest-neighbour estimate over repair history, market and cover tables as pack data, three priced options, a batch action, a credit what-if. | L (M rules-only) | new (phase 5 or a tool-fleet phase) |
| T2 | **Contract refresh**: one proposal per contract 90 days before its end: keep good-life tools, **swap** worn ones (below 25 % life) for refurbished units of similar life, **upgrade** where parts end before the next term; fee, saving against new, likelihood to renew; credits over $300 need sales approval; on approval: email, draft contract lines, reserve the refurbished tools. | Nothing. The lease mock has contract end dates and renewal options ([oracle_lease/__init__.py:1–3](../../../../source-sim/sim/vendors/oracle_lease/__init__.py#L1)); renewals appear only as sample-world demand. | Missing | A scheduled trigger, a proposal object per contract, like-life matching against refurbished stock, approval by credit size, three instruction steps. | L | new |
| T3 | **What-if**: "move the market, see decisions change". | Per case, industrial: `case.whatIf` with market, cost and service levers ([engine.py:20](../../../../backend/di/services/actions/engine.py#L20); [case.ts:259–262](../../../../frontend/src/api/case.ts#L259)). The tool-fleet valuer already takes market, labour, lease, slots parameters (`BASEP`, [tool_fleet.py:166](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L166)); nothing exposes them over the queue. | Partial | Quick win 16. | S–M | Phase 0 |
| T4 | **Pulse suggestion rules** that target the oldest value bands first (device: Offers → Auction after 14 days with no offer; Buy Now → Offers after 21 days). | Nothing. The device valuer scores a lot once ([device.py:1–10](../../../../backend/di/services/modeler/valuers/device.py#L1)); the Machinio mock already exposes `listing_age_days` ([machinio/__init__.py:3–5](../../../../source-sim/sim/vendors/machinio/__init__.py#L3)). | Missing | A suggestion-rule type (condition on listing age → move channel), evaluated daily, raised as a proposal. | M | new (with P9-3.4) |
| T5 | **Exceptions inbox** routed by role: each item with cause, recommended action and owner; per-pack exception types (e.g. "telematics and inspection disagree", "no active contract for the serial"). | Command Center groups value at risk by risk type over industrial cases ([command.py:1082](../../../../backend/di/services/screens/command.py#L1082)); inbox ([command.py:1346](../../../../backend/di/services/screens/command.py#L1346)); Home alerts; the conflict queue. | Partial | Exception types as pack data with an owner role and a recommended action, listed in "My work". | M | P9-5.8 |
| T6 | **Analytics**: rates by item with drill-down; analysis **from a prompt** as a chart plus example records; **saved shared views**; **alerts on a measure**. | Drill-down exists over the demo's closed decisions (§2.11); Ask answers questions (§2.4); `analytics.query` answers 501 (§2.8). No saved views, no measure alerts. | Partial | `analytics.query` over a semantic layer of the pack's KPIs; views and alerts stored per org. | M–L | new |

### 7.8 Packs (01 §4–9)

**P0, the pack contract (01 §9).** 01's pack carries: identity and version, author role, three sample prompts, the
configuration agent's reading log and question, seven stages each with an agent, routes, typed guardrails at stages,
the systems (with adapter or not), about seven canonical entities, field mappings with confidence and reasons, a replay
dataset, an example asset, exception types with owners, six KPIs and a trend, two analytics questions, and the customer
layer. Today's `Template` has key, name, prefix, paths, guardrails (id, text, owner, block patterns), scope dimensions,
actors and wording ([templates.py:98–106](../../../../backend/di/services/modeler/templates.py#L98)); the valuer is code.
Of 01's parts, only routes, untyped guardrails and the industrial pack's JSON file exist. The canonical store has 11
models (asset, condition, demand, intervention, market, route, sustainability, vendor, outcome, part, bom;
[schema.py:41–43](../../../../backend/di/services/canonical/schema.py#L41)); 01's "return event", "cost rate",
"compliance record", "channel" and a contract entitlement have no model. **L**, P9-1.1 (whose scope must grow to the
full contract).

System coverage (✔ a mock exists; ~ a mock of a related system could stand in; ✖ none). Mocks:
[source-sim/sim/vendors/](../../../../source-sim/sim/vendors) and [generic/specs/](../../../../source-sim/sim/generic/specs).

| Pack (01) | Exists in code | Systems 01 lists → mocks | Missing |
|---|---|---|---|
| **P1 Tool fleet AMS** (§4) | Pack, valuer, flow. The six paths match 01 §4.1 one to one ([tool_fleet.py:40–58](../../../../backend/di/services/modeler/valuers/tool_fleet.py#L40)). Guardrails GR-01–06: grade C/D not re-issued, refurbishment ends in a named destination, fit-for-use threshold, holding cost set by Finance, owner approval, certified recycler. | ERP ✔ S/4HANA; CRM ✔ Salesforce; fleet contract system ~ Oracle Lease; telematics ✔ AWS IoT; service desk ✔ ServiceNow; spare-parts catalogue ~ PLM BOM (Windchill, Teamcenter) or S/4 materials (**unconfirmed** which fits); legacy depot repair log ✔ Depot Repair. **6–7 of 7.** | 01's pack guardrails: safety recall check (compliance; no recall source anywhere), telematics under 7 days old (data quality); stated: repair over $600 → fleet manager (approval limits exist per role, [policy.py:152](../../../../backend/di/core/policy.py#L152), not per action value); write-off under 24 months. Diversions (recall → quarantine; key account → account manager). Live demand (§7.5 row 3). Service desk, Contract refresh (T1, T2). KPIs: days to next use, upgrade offers accepted, % held by guardrails. **M–L** |
| **P2 Device recommerce** (§5) | Pack, valuer, flow. Channels Buy Now, Offers, Auction, Marketplace ([device.py:27–35](../../../../backend/di/services/modeler/valuers/device.py#L27)); 01 has wholesale lot instead of Marketplace. Guardrails: wipe (text only), recovery floor 55 % (01 states 60 %, a customer value), grade D, lot size, no undercut, owner approval. | Trade-in platform ~ Optoro (returns); diagnostics ✖; photo grading ✖ (Google Drive photos ~); data-wipe tool ✖; device registry (blacklist/lock) ✖; marketplaces ~ Machinio (listings, offers), Ritchie (auction comparables); price feeds ✖ (Ritchie ~); ERP ✔. **1 ✔, 4 ~, 3 ✖ of 8.** | Blacklist/lock gate (pack compliance), wipe gate as data, payout adjustment within 10 % of the quote, wholesale lots from approved-buyer bids, ageing rules (T4), lot over $25,000 → commercial manager. P9-3.4–2.7 cover the gates and mocks. **M (L with ML)** |
| **P3 Used cars** (§6) | Nothing. | Lease system ~ Oracle Lease; dealer management ✖; title and lien ✖; inspection app ✔ SafetyCulture; recall database ✖; auction platform ~ Ritchie; pricing guide ✖; legacy body shop ✖. **1 ✔, 2 ~, 5 ✖ of 8.** | Pack, valuer (retail by lot vs auction net of fees and transport, recon cost), title/lien and open-recall gates, five mocks. **L** |
| **P4 Telecom network equipment** (§7) | Nothing. | Network inventory ~ Maximo (EAM); decommission tracker ✖; ERP ✔; field service ✔ ServiceNow / Maximo; test bench ~ Depot Repair bench tests; spares planning ~ S/4; broker marketplace ~ Machinio; recycler portal ✔ Sims. **3 ✔, 4 ~, 1 ✖ of 8.** | Pack, valuer (spares-before-new across regions, 6-month need), inventory-match and configuration-wipe gates, export-control check, firmware-gap diversion. **L** |
| **P5 Medical rental** (§8) | Nothing. | Rental system ~ Oracle Lease; asset management ✔ Maximo; decontamination log ✖; biomedical service ~ ServiceNow / MasterControl (QMS); CRM ✔; ERP ✔; parts supplier portal ~ Ariba; disposal partner ✔ Sims. **4 ✔, 3 ~, 1 ✖ of 8.** | Pack, valuer (next hospital with least travel while certification stays in date), decontamination and certification gates, utilisation KPIs. Compliance-heavy: Legal review. **L** |

Mock counts are by system *type*; a "~" mock serves other objects than the pack needs and would need new resources.
None of the five packs' sample replays (3,420 tools, 18,600 devices …, all *sample*) exists as data.

---

## Sources read

`docs/agents/research/2026-11-platform/00-brief.md`, `AGENTS.md`, `docs/backend-steps.md` (B13–B17 and the plan-8
status), and the code cited inline. Action counts come from `fixtures/golden/actions_catalog.json` plus a scan of
`ACTIONS.setdefault`/`_declare` calls and `@implement` decorators under `backend/di` (24 Nov 2026); a runtime count
through `GET /api/agents/tools` was not taken (**unconfirmed** at runtime, expected 131).

Second pass: [01-recover-segments.md](01-recover-segments.md), [V-verification.md](V-verification.md), the draft
[plan 9](../../plans/09-agentic-platform.md) (for task ids), `fixtures/golden/po/templates.json` (the tool-fleet and
device guardrails), the source-sim vendor and generic-spec docstrings (for the system coverage table), and the code
cited in §7. Nothing was run. **Unconfirmed** in §7: whether the Depot Repair seed holds enough repair history for
the Service desk estimate (T1); which mock best stands in for a spare-parts catalogue (P1); whether customers need an
external vault (R7); and that no code changed between `0c71585` and `5b1fcfd`.
