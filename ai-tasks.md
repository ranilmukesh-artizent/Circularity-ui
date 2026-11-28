# AI tasks: one agentic engine for Circularity, proven with live HTTP evals

Hand-off for a fresh session. Written 27 Nov 2026 by the plan 9 lead after the PO demo, where the AI failed in front of
the PO. Every issue below was seen in the demo or checked in the code and database that day. File references are from
commit `64611e66` plus the uncommitted edits in section 11. Research sources are listed in section 12; third-party
summaries are marked as such and must be checked against the primary source before you rely on a detail.

Read first: `AGENTS.md`, `CLAUDE.md`, **§4A/§4B of this file (the Claude Certified Architect practices and the
decisions taken from them)**, `docs/agents/plans/10-unified-assistant-ux.md` (the one-assistant UI plan),
`docs/agents/plans/09-run/demo-2026-11-27-ai-issues-and-test-plan.md` (the demo notes).

---

## 1. What the user wants (their words, then what it means)

> If I type a workflow, in both workflows, I should get a real answer and the workflow set, just exactly how Claude
> works. It should answer across any module.
>
> It expects me to say the workflow name. We have I don't know how many agents. The best practice is one agent that
> delegates to subagents with relevant skills and tools, with dos and don'ts, like Claude's best practices. Use the
> state of the art (loop engineering, harness engineering, the DeepSeek harness and super agent, the Claude Architect
> Foundation and Professional material) and create a superb agentic engine that works.
>
> Evaluate and test it with real HTTP hits, not simulation: pure endpoint testing. Set up tracing so traces and logs
> are saved to our Postgres, using the most reliable fully open-source tracing that is best for Pydantic. Recommend
> other LLM providers with free APIs, besides Groq.

So, done means:
1. **One engine, one entry point.** Every page's assistant (dock, Ctrl+J, the Modeler's column) talks to one
   orchestrator agent. It knows the page and its object without being told ("this workflow" on WF-103 *is* WF-103).
   It answers any question about any module, and delegates to specialist subagents.
2. **It acts, safely.** "Create a workflow that …" produces a real, checked, test-run **draft** in Workflow Studio. "Never
   send Customer C's motors to resale" produces a **draft** flow change in the Modeler. "We take back laptops …"
   produces a draft composition. Each answer links to what it created. Publishing, approving, overriding, declining and
   access changes stay a person's button (golden rule 10).
3. **It never goes dark.** Several models from several providers in a chain. Rules answer only when every model is
   out, and even then the answer is useful.
4. **Everything is traced into our Postgres**: each run, each model call, each tool call, tokens, latency, errors and
   the final answer. It is queryable, and the UI's "Call log" reads it.
5. **Proven live.** Acceptance is real HTTP calls against the running api with real keys and real models, scored per
   model. Mocked or simulated tests never count as proof.

---

## 2. Today's AI, mapped (so the new session starts informed)

### 2.1 Two separate loops
| Loop | Where | Used by |
|---|---|---|
| **Ask's own loop** on the raw `groq` SDK | `backend/di/services/ask/groq_model.py`, `ask/chain.py`, `ask/model.py:88-118`, `ask/service.py` | the assistant (`POST /api/ask`, SSE) |
| **Pydantic AI loop** (the `AgentLoop` port) | `backend/di/services/agents/loop.py` (`LoopSpec`, `LoopResult`), `agents/pydantic_ai_loop.py` | every playbook (agents) |

These are two harnesses with different tool wiring, retries, budgets and traces. The engine should be one.

### 2.2 Agents today (many, none orchestrated)
- **Playbooks** (`backend/di/services/agents/playbooks/`): `case_autopilot`, `stage_chain`, `stage_reasoner`,
  `workflow_author` (agent id `workflow-author`), `adapter_author` (`integrator`), `pack_author`, `stop_explainer`
  (`recover-config`), `exception_writer` (`recover-exceptions`), `fraud_reviewer`.
- **Other model users**: `agents/mapping_rerank.py`, `agents/drift_explainer.py` (`recover-config`),
  `agents/config_agent.py` (pack match), `agents/exception_assistant.py`, `agents/journey.py`, `agents/schema_notes.py`,
  `agents/checked_output.py`, `ask/modeler_read.py`, `ask/complete.py` (one-shot JSON).
- **Stage reasoners** (`agents/stages/`, 14): condition, demand, disposition, fit_for_use, follow_through, intake,
  lease_end, lifecycle, outcome, reconcile, return_auth, transit, valuation, plus `__init__`.
- **Ask** (`AGENT_ID = "ask"`, `ask/tools.py`): read-only tools only.
- Registry, autonomy, limits, proposals, the forbidden list: `agents/registry.py`, `limits.py`, `proposals.py`,
  `forbidden.py`, `catalog.py`, `runtime.py`. These are good foundations to keep.

### 2.3 Models
- Router `backend/di/services/llm/router.py`: table `llm_model` (priority, roles, rpm/tpm/rpd, cooldown, eval scores),
  `llm_budget`. Providers known: **`groq` and `test` only**.
- **Main stack has exactly one row**: `groq-default` = `openai/gpt-oss-120b`, roles `{ask,agent,author,judge}`. No
  `stage` role. `ASK_MODEL_CHAIN` (`.env.example:24`) is unused by Ask's `_routed()`.

### 2.4 Tools, context, fallback, evals
- Ask tools (`ask/tools.py`): `list_cases, get_case, get_case_run, what_if, explain_kpi, list_workflows, get_workflow,
  get_workflow_run, get_inbox, device_question, number` + MCP reads `get_case_evidence, list_eligible_routes,
  predict_outcomes, find_demand, optimize_pool, get_model_validation, get_decision_flow`. **Nothing that creates.**
- Page context: `frontend/src/layout/assistant/context.ts` → `askContext()` sends only `{page, section, case_id}`. On
  Workflow Studio the panel says "Looking at: Integration · Section: studio" and sends **no workflow id**.
- Rules-first: `ask/fallback.py:1141` `RULE_FIRST = {"workflow.draft"}`: "draft a workflow" never reaches a model.
- Workflow from a sentence exists but only on the builder page: `services/actions/workflow_author.py`
  (`workflow.author`: planner → model graph → code validation, 3 repairs → `workflow.create` + dry `testRun` +
  `draft.save`).
- Decision-flow change: `modeler/propose.py` + regex `modeler/parse.py`; model only for unparsed `{path,action,scope}`.
- Evals: `backend/tests/evals/` (`live.py`, `datasets.py`, `evaluators.py`, `scoring.py`, `suites.py`, …),
  `scripts/dev/evals-live.sh`. These run in-container per model, not over HTTP, and don't cover Ask per page or building.
- Tracing: plan 5's OpenTelemetry (`backend/di/telemetry.py`, off by default, `docker-compose.otel.yml` with
  `grafana/otel-lgtm`, whose image pull is still waiting for the user's OK). **Nothing is stored in our Postgres.**
- Sign-in: `POST /api/auth/login {username, password}` → token (local demo accounts, any password).

---

## 3. Issues (confirmed)

| # | Sev | Issue | Evidence | Root cause |
|---|---|---|---|---|
| I1 | P0 | No AI once rate limited: "Answered by the rules, because rate limited". | Demo screenshots; DB has one model row | One model, one provider. Fallback models were asked for and never added. |
| I2 | P0 | On WF-103, "in this workflow what it does?" → "I'm not sure which workflow you're referring to. Please provide the workflow ID". | Screenshot 17:41 | Page object not sent (`askContext` has no workflow id); prompt has no "this = WF-103". |
| I3 | P0 | "What is stuck in the last sync?" (a shipped starter) → "I don't have any record of a sync that's currently stuck". | Screenshot 17:41 | No tool for syncs/sources/fabric health in Ask; starter not tested. |
| I4 | P0 | Ask can't build or change anything; "draft a workflow" skips the model. | `RULE_FIRST`, read-only tools | By design until now. |
| I5 | P0 | Set up from the Modeler's Flow tab: "Could not start the description · no template chosen". | Demo screenshot; `SetupMode.tsx:65-69` | `ctx.pack` unset for a flow surface (`context.ts:18-20`). |
| I6 | P0 | Two loops, ~25 separate model users, no orchestrator; each with its own prompt, retries, budget. | §2.1, §2.2 | Grew per plan step. |
| I7 | P1 | "Which guardrails does this flow keep?" (starter) → "I can't see any record". | Demo screenshot | Same as I2 on the Modeler. Uncommitted partial fix (§11). |
| I8 | P1 | "hii" → "I can't do that yet. I can: hii". | Screenshots | No greeting intent; the fallback echoes. |
| I9 | P1 | "We take back used laptops and phones … wipe … grade … resell or recycle" → "No pack fits. Closest: ITAD (58)". | Lead's check | Keyword match, bar 60. |
| I10 | P1 | Flow changes are regex-only; multi-part sentences are "unclear". | `modeler/parse.py` | No model-first reading. |
| I11 | P1 | No traces in our DB; "Call log" is per-answer only; can't debug a bad answer after the fact. | §2.4 | OTel off, no PG exporter. |
| I12 | P1 | No live test of the AI existed; everything green was mocked or rules. | This demo | No HTTP evals. |
| I13 | P2 | "Waiting for you" fills the assistant panel. | Screenshots | No cap. |
| I14 | P2 | Modeler canvas hides the right-hand steps behind the inspector. | Screenshot | `FlowCanvas.tsx:166` `openZoom={0.8}`. |
| I15 | Ops | api cold start ~3 min (Windows bind mount imports); restart → 502. Budget burned by smokes before the demo. | Lead's importtime | Don't restart before demos; per-role budgets; more models. |

---

## 4. State-of-the-art practices, distilled for this engine

Derived from the sources in §12. Each line is a rule the engine follows.

**Architecture (Anthropic "Building effective agents"; "How we built our multi-agent research system"; Claude Agent
SDK; Claude Certified Architect material, where agentic architecture is the most weighted domain per third-party
guides)**
1. Use the simplest pattern that works: a deterministic **workflow** where the path is known (prompt chaining, routing,
   evaluator-optimizer), an **agent** only where the path is open. Code-enforced control around the model beats
   prompting alone.
2. **Orchestrator-worker**: one lead agent plans and delegates; subagents run with *fresh, narrow* context and return a
   compact result. Brief each subagent like a colleague: objective, output format, tools and sources, boundaries.
3. **Effort scaling**: explicit rules for how many subagents and tool calls a request deserves (a lookup: 0 subagents,
   1–3 tool calls; a build: 1 subagent, ≤15 calls; a cross-module analysis: up to 3 parallel subagents). Without them
   the lead over-invests.
4. Multi-agent costs many times the tokens of a chat. Delegate only when it buys accuracy or parallelism; keep simple
   questions in the orchestrator.

**Harness engineering (OpenAI Codex post Feb 2026; Böckeler; "Agent = Model + Harness"; DeepSeek Harness)**
5. The harness is the product: tools, context assembly, constraints, feedback sensors, stop conditions, budgets,
   traces. Same model, better harness, big gains (third-party benchmark claims; verify).
6. **Plugin seams** (DeepSeek Harness, MIT, developer preview: model adapter, agent loop, tools as swappable plugins):
   provider adapters, skills, tools, checkers and exporters are registered plugins, not if/else.
7. **Sensors before claims**: every output that changes something is checked by code (schema, graph validation, the
   action pipeline's checks, a dry test run) and the errors fed back for repair (bounded rounds).
8. **Log everything** as structured traces: they make agents debuggable and are the raw material for evals and
   improvement.

**Loop engineering (IBM; Claude Code team via O'Reilly; LangChain Deep Agents; Addy Osmani)**
9. Name the loops and give each a stop condition: (a) the **agent loop** (think → tool → observe, max rounds, budget);
   (b) the **verification loop** (code checks, then a judge model against a rubric); (c) the **repair loop** (feed
   errors back, ≤3 rounds, then hand to a person); (d) the **eval loop** (datasets over HTTP, nightly and before demos);
   (e) the **improvement loop** (every failed trace becomes a dataset case; scores reorder the model chain).
10. Unattended loops need precise goals and constraints; anything that writes ends as a held proposal or a draft.

**Tools and context (Anthropic "Writing effective tools for agents", "Effective context engineering")**
11. Few, well-named, high-level tools with clear descriptions, examples and errors that say how to recover
    ("workflow not found; list_workflows lists ids"). Test the tools with the model and rewrite the descriptions.
12. **Skills with progressive disclosure** (Claude Agent SDK skills): the orchestrator sees one line per skill; the
    skill's full instructions, dos/don'ts and examples load only when it is used.
13. Context is a budget: page context + object summary up front; everything else through tools; compact long tool
    output; conversation memory summarized after N turns.

**Safety and governance (this repo's rules, golden rule 10)**
14. Permissions are enforced in code at the tool layer (action pipeline: tenant, permission, autonomy, forbidden list),
    never by the prompt. Untrusted content (records, files, web) taints the run: writes are held for a person.

---

## 4A. The Claude Certified Architect guides (in hand, read them)

| Guide | Path on this machine | Status |
|---|---|---|
| Professional (CCAR-P), v1.1, effective Nov 2026 | `C:\Users\ranilmj\Downloads\Claude_Certified_Architect_-_Professional_Exam_Guide.pdf` | **The current bar.** Per the user, the big full-assessment style of material (as in Foundations) is deprecated as of Nov 2026 in favour of the new course lessons; follow the Professional blueprint's practices. |
| Foundations (CCAR-F), v1.0, effective Jul 2026 | `C:\Users\ranilmj\Downloads\+Certified+Architect+–+Foundations+Exam+Guide.pdf` | Older, detailed task statements. Still the best "how" for loops, subagents, tools, errors, structured output and context; use it where it doesn't conflict with Professional. |

Both are Anthropic's exam guides (not course lessons); the new course lessons are on the Anthropic Partner Academy.
They are about Claude, but the practices are model-agnostic; we run them on Pydantic AI over Groq and other providers.

**Professional blueprint (what "production-grade" means), with what it asks of us:**
| Domain (weight) | What it asks | For Circularity |
|---|---|---|
| 1 Solution design & architecture (17%) | input → processing → output → **feedback loop**; pick the pattern (workflow, agentic, augmented LLM); multi-agent orchestration; decomposition; tie to business value and SLAs | §4B D1–D3; every surface states its pattern and its SLA (latency, pass rate) |
| 2 Models, prompting & context (13%) | model choice by trade-off; system prompts, templates, guardrails; few-shot; context and token budgets; reuse via **caching, modular prompts, Skills** | §4B D4, D9, D10 |
| 3 Integration (19%) | **capability bloat** check; authN/authZ gap analysis; accuracy-latency trade-offs; observability at scale; RAG matched to data shape; protocol choice (MCP, API/CLI, agent-to-agent); **progressive discovery vs monolithic context** | §4B D5–D8, D13 |
| 4 Evaluation, testing & optimization (16%) | metrics (accuracy, latency, cost, safety, security); mixed-method datasets; **A/B tests**; diagnose prompt failure vs hallucination vs model mismatch; token/latency/cost tuning; monitoring | §8 + §4B D11 |
| 5 Governance, safety & risk (14%) | guardrails; failure modes; **human-in-the-loop**; regulation (GDPR etc.); bias, fairness, transparency | §4B D6, D12; Legal review note |
| 6 Stakeholder & lifecycle (14%) | discovery, decisions and trade-offs documented, SLAs agreed, handoff, monitoring, iteration | decision log rows per §4B choice; this file is the handoff |
| 7 Developer productivity (7%) | team tooling, debugging, ops | traces in PG (§6), `ai-live-check.sh`, runbook section |

Sample-question lessons worth keeping (Professional §8, Foundations §9): least privilege means **remove** tools a role
doesn't need (not log or confirm them); put static prompt content first and cache it; confident-wrong answers after a
data change point to retrieval/context, not the model; enforce required tool order **in code**, not the prompt; fix
tool selection first by **better tool descriptions**; escalation by explicit criteria + few-shot, never by sentiment or
self-reported confidence; structured error context (not "unavailable", never empty-as-success); a subagent gets a
scoped tool for its common case and goes through the coordinator for the rest; split big reviews into per-item passes
plus an integration pass; an independent reviewer beats self-review.

## 4B. Practical, no-nonsense decisions for Circularity (start here)

Each is the simplest thing that meets the bar. Record each in `docs/agents/decision-log.md` when built.

| # | Decision | Why (guide) | Not doing (over-engineering) |
|---|---|---|---|
| D1 | **Pattern per surface.** Ask questions = augmented LLM with read tools (one agent, no subagents). Building an integration workflow = a fixed workflow with LLM steps (plan → author → validate → test run), wrapped as one tool. Flow change = parse → propose → simulate → save draft (fixed steps, LLM reads the sentence). Only cross-module or multi-concern requests use the orchestrator delegating to subagents. | P-D1 pattern choice; F-1.6 chaining vs dynamic | a multi-agent hop for every question |
| D2 | **One coordinator, hub-and-spoke.** Subagents never talk to each other; they get an explicit brief (goal, inputs, output schema, limits), not the chat history; parallel subagents in one step when independent; the coordinator checks coverage and re-delegates once if a gap remains. | F-1.2, 1.3; Anthropic multi-agent post | agent-to-agent protocols inside one app |
| D3 | **Pydantic AI, not the Claude Agent SDK.** Our providers are Groq and other free tiers; the Agent SDK is Claude-only. Map the concepts: Task tool → `delegate` tool; AgentDefinition → a skill row (description, prompt, allowed tools, output type); hooks → the action pipeline's gates plus Pydantic AI tool `prepare`/result processors; `stop_reason` loop → Pydantic AI's run loop (ends on a final typed result, never on parsing text; max rounds is a safety net only). | F-1.1 anti-patterns; F-1.3 | writing our own loop again |
| D4 | **4–6 tools per agent.** The coordinator gets the page object reader, a search-anything reader, and `delegate`; each subagent gets only its own tools (§5.3), plus one scoped cross-role reader for its common need. Tool descriptions carry input format, an example, edge cases and "use X instead when …". | F-2.1, 2.3; P-D3 capability bloat | giving every agent all ~25 tools |
| D5 | **Least privilege by removal.** No agent is ever handed `publish`, `approve`, `override`, `decline` or access tools; `forbidden.py` stays as the second wall. Drafts only. | P sample 1; golden rule 10 | confirmation prompts as the only guard |
| D6 | **Code-enforced order where it matters** (pipeline gates as hooks): `workflow.draft.save` only after `workflow.validate` has 0 errors and a dry test run ran; `flow.saveDraft` only after `flow.simulate`; a write after an untrusted read is held for a person; amounts over a limit hold. | F-1.4, 1.5; P-D5 | prompt-only rules for these |
| D7 | **Structured tool errors** everywhere: `{error_category: transient|validation|permission|business|not_found, retryable, message, attempted, partial}`; an empty result is `ok` with `count: 0`, never an error, and an error is never an empty success. Subagents retry transient errors locally once and pass the rest up with what they tried. | F-2.2, 5.3 | generic "operation failed" |
| D8 | **Structured output by schema.** Every agent ends in a Pydantic output type (nullable where a value may be absent; enums with `unclear` / `other` + detail); validation errors go back once with the specific error; if the info is absent, ask the person instead of retrying. Every number and id in an answer maps to the tool call it came from (provenance), checked in code as `workflow_check` does today. | F-4.3, 4.4, 5.6 | free-text parsing of model output |
| D9 | **Context discipline.** Prompt order: static rules and skill index first (cacheable), then the page object and a "facts" block (ids, amounts, dates from this conversation, never summarised away), then the turn. Trim tool results to the fields that matter before they enter context. Summarise history after N turns; start fresh with a summary when earlier tool results are stale. | F-5.1, 1.7; P sample 2 | stuffing whole records or long histories |
| D10 | **Skills with progressive disclosure.** One line per skill in the coordinator prompt; the skill's full prompt, few-shot examples (2–4 for the ambiguous cases) and dos/don'ts load only when it runs. | P-D2/D3; F-3.2, 4.2 | one monolithic system prompt |
| D11 | **Evals are the product's test suite.** Live HTTP datasets per skill and page (§8), metrics accuracy/latency/cost/safety/security, scored per segment (page, pack, skill), not one aggregate; A/B a prompt or model change on the same dataset before switching; failed traces become cases. Nightly full matrix (latency-tolerant: batch where the provider offers it); the 2-minute live check before demos. | P-D4; F-5.5, 4.5 | trusting mocked tests or a single overall % |
| D12 | **Human in the loop by explicit criteria.** Escalate (hold for a person) on: policy gap or exception, a write over a limit, untrusted input, multiple matches (ask for the identifier instead of guessing), the person asking for a human. Not on sentiment or the model's own confidence; confidence thresholds only after calibration on a labelled set. Handoffs are structured (case/flow id, what was tried, the recommendation). | F-5.2, 5.5; P-D5 | self-reported confidence routing |
| D13 | **Integration choice.** Internally the engine calls the action pipeline directly (no MCP hop); our MCP server stays for outside clients. Structured data (cases, workflows, KPIs) is read by tools and SQL, not embeddings; add retrieval (RAG) only for the user guides and runbooks, later, when "how do I" questions need it. | P-D3 protocol and RAG-by-data-shape | a vector DB for tabular data |
| D14 | **Independent review** of anything the engine creates: a reviewer subagent on a *different* model checks the draft against a rubric (asked blocks present, nothing invented, checks green) before the answer says "created". | F-4.6 | asking the author to review itself |
| D15 | **Transparency.** Every answer says whether a model or the rules answered, which model, and links its trace; nothing is presented as done that is only drafted or held. | P-D5 ethics/transparency | silent fallbacks |

---

## 5. Target design: the Circularity agent engine

```
page (any) ──► POST /api/agent/turn (SSE) ──► Orchestrator (Pydantic AI Agent, one loop)
                                              │ context: page, object {kind,id}, role, tenant, conversation
                                              │ skills index (1 line each), effort rules
                                              ├─ answers simple questions itself with read tools
                                              └─ delegates (agent-as-tool) ──► Subagent(skill) ──► tools ──► action pipeline
                                                                                     │ checks / repair / judge
                                                                                     ▼
                                              result {text, cards, created[], held[], tools[], trace_id}
traces of every step ──► OpenTelemetry (Pydantic AI instrumentation) ──► our Postgres (ai_trace/ai_span/ai_event)
```

### 5.1 One loop
- Pydantic AI for everything (it already runs the playbooks). Ask's `groq_model.py` loop is retired; Ask becomes the
  orchestrator's "answer" path. Keep the SSE event shapes (`start/tool/delta/reset/final`) so the panel keeps working,
  and add `delegate`, `created` and `held` events and `trace_id`.
- Model access through the router only, with a multi-provider `FallbackModel` (§7).

### 5.2 Orchestrator
- System prompt: who it serves (role, tenant), the page and its object, the skills index, effort rules, the hard rules
  (`HARD_RULES`), "never ask for an id the page already gives".
- Its own tools: the read tools for every module (cases, workflows and runs, sources and syncs, fabric health and
  conflicts, data checks, flows and rules, analytics KPIs, agents and runs, proposals, access requests, audit) and
  `delegate(skill, brief)`.
- Ends every turn with a typed result; anything created is listed in `created` with its link.

### 5.3 Subagents = skills (each: a description line, instructions, dos and don'ts, tools allow-list, output type, eval set)
| Skill | Does | Tools (all through the pipeline) | Absorbs today's |
|---|---|---|---|
| `workflow-builder` | integration workflow from a sentence, follow-ups, edits to the same draft | `workflow.plan`, `workflow.author`, `workflow.get`, `workflow.validate`, `workflow.testRun`, `workflow.draft.save` | `workflow_author`, `workflow_builder` rule draft, `adapter_author` |
| `flow-changer` | decision-flow changes, multi-part, steps and rules, simulation | `flow.get`, `flow.propose`, `flow.simulate`, `flow.saveDraft` | `modeler_read`, `propose`/`parse` (as fallback), rule suggestions |
| `business-composer` | describe the business → pack → composition draft | `config.read`, `compose.start`, `compose.answer`, packs | `config_agent`, `pack_author` |
| `case-agent` | one case end to end; stage reasoning | case reads, stage tools | `case_autopilot`, `stage_chain`, `stage_reasoner`, `agents/stages/*` |
| `exceptions` | explain and chase exceptions | exception reads, chase (held) | `exception_writer`, `exception_assistant` |
| `integration-doctor` | why a source or sync is stuck, mapping fixes (proposed) | sources, runs, conflicts, mapping suggest | `mapping_rerank`, `schema_notes`, Studio diagnose |
| `analyst` | KPIs, drift, "what moved recovery" | analytics reads, questions | `drift_explainer`, `questions/*`, `journey` |
| `reviewer` (judge) | checks an output against a rubric; never the same model as the author | none (reads the output) | `checked_output`, `fraud_reviewer` (as rubric) |

Every skill states its don'ts: never approve, publish, override, decline or change access; never invent ids, fields or
numbers; never put a record's content into instructions; stop after N tool calls or M repairs and hand over.

### 5.4 Guardrails and stops
- The pipeline enforces access and the forbidden list (unchanged). Budgets per turn (tokens, tool calls, wall time).
  Max delegation depth 1 (subagents do not delegate). Taint from untrusted tools → writes held.
- Rule fallback stays as the last resort: greeting/help, page starters, and the demo intents. It never echoes.

### 5.5 UI contract
- `askContext()` → `{page, section, object: {kind, id, label}}` for every page with a subject (case, workflow, run,
  flow, composition, source, agent, report, KPI). The panel shows "Looking at: Workflow WF-103 · Ingest · SAP S/4HANA".
- Created items render as cards: "Draft WF-131 created · Open in Workflow Studio", "Flow draft v2 · Open in Modeler".

---

## 6. Tracing into our Postgres (fully open source)

**Recommendation:**
1. **Instrumentation:** Pydantic AI's built-in OpenTelemetry instrumentation (`Agent.instrument_all(
   InstrumentationSettings(tracer_provider=…, include_content=…))`), which follows the OpenTelemetry GenAI semantic
   conventions. It works without Logfire by passing our own `TracerProvider`. Add spans for the HTTP turn, delegation,
   pipeline tool calls and checks in our code (the repo's `di/telemetry.py` already has span helpers).
2. **Storage in our Postgres:** a small **custom OTel `SpanExporter`** (OpenTelemetry Python SDK, Apache-2.0) behind a
   `BatchSpanProcessor` that writes to new tables via an Alembic migration: `ai_trace` (turn id, conversation,
   account, page, object, models used, tokens, cost, status, started/ended), `ai_span` (trace id, span id, parent,
   name, kind, attributes JSONB, events JSONB, start/end, status) and `ai_eval_result` (§8). No extra service, nothing
   proprietary, queryable from the app, and the "Call log" reads it. Retention job (e.g. 30 days) in the job queue.
   Content capture on by default for synthetic data, with redaction of secrets (`gsk_…`, tokens, passwords) in the
   exporter.
3. **Optional trace UI** (pick one, same spans fanned out over OTLP):
   - **MLflow** (Apache-2.0): server ≥ 3.6 accepts OTLP/HTTP at `/v1/traces` with a SQL backend store; PostgreSQL works
     by store URI; it also has `mlflow.pydantic_ai.autolog()`. Use our Postgres with its own database.
   - Arize **Phoenix**: simplest PostgreSQL path, with OpenInference's Pydantic AI instrumentation, but the license is
     Elastic License 2.0 (source-available, not OSI open source).
   - **Langfuse** (MIT): strongest product, but self-hosting needs ClickHouse, Redis and object storage on top of
     Postgres.
   - Pydantic **Logfire**: best Pydantic UX, but self-hosting is Enterprise-only, so it is not an option here.
   - Any new image pull (MLflow, Phoenix, Langfuse, otel-lgtm) needs the user's explicit OK first.

---

## 7. Models and providers

### 7.1 Groq, all useful models
List them live in the api container: `GET https://api.groq.com/openai/v1/models` with the key from the environment
(never print it). Keep those that answer a tool call; give each realistic rpm/tpm/rpd from the account's limits.
Candidates to verify: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`,
`qwen/qwen3-32b`, `moonshotai/kimi-k2-instruct`, `meta-llama/llama-4-scout-17b-16e-instruct`,
`meta-llama/llama-4-maverick-17b-128e-instruct`.

### 7.2 Other providers with free API tiers (verify limits, tool calling and data-use terms before use)
| Provider | Why | Integration |
|---|---|---|
| **Google Gemini API** (AI Studio key) | generous free tier, strong tool calling, long context | Pydantic AI Google provider |
| **Cerebras** | very fast, free daily token allowance (sources disagree on context caps) | OpenAI-compatible |
| **OpenRouter** `:free` models | many free models; `openrouter/free` routes to one that supports the needed features (e.g. tools); about 20 rpm, 50/day free, 1,000/day after a $10 credit purchase (per OpenRouter) | OpenAI-compatible |
| **Mistral** (free plan) | free tier with account-specific limits; good tool calling | Pydantic AI Mistral provider |
| **GitHub Models** | free prototyping quota for many models | OpenAI-compatible |
| **NVIDIA NIM** (build.nvidia.com) | free credits for hosted open models | OpenAI-compatible |
| **Cloudflare Workers AI** | free daily allowance | OpenAI-compatible |
| **SambaNova Cloud**, **Hugging Face Inference Providers** | free tiers or credits | OpenAI-compatible |

Design: one `openai_compat` provider kind in the router (`base_url` + `key_ref`) plus `google` and `mistral`. Order the
chain by eval score per role, and mix providers so one provider's outage or limit never stops the engine. **Before any
real data leaves the machine, check each provider's data-use terms** (some free tiers may use prompts to improve their
models): the data here is synthetic, but have Kinective's Legal team review the provider terms before relying on them
at a customer. Keys go in `.env` (git-ignored) by the user; the code never reads or prints them.

### 7.3 Course material
The user provided both official exam guides; paths and the distilled practices are in §4A and §4B. Professional
(v1.1, Nov 2026) is the current bar; Foundations is the detailed "how".

---

## 8. Testing: live HTTP evals only (acceptance = real endpoints, real models)

No simulation counts as proof. Mocked unit tests may stay as regression guards for pure code, but the done-when of
every task is the live result below.

### 8.1 `scripts/dev/ai-live-check.sh` (≈2 min, before every demo and after every AI change)
Bash (LF, Git Bash, `export MSYS_NO_PATHCONV=1`), needs only `curl`; parse JSON with `node -e` or inside the api
container.
1. `POST /api/auth/login` as `admin`, `planner.a`, `approver` → tokens (never printed).
2. Default chain first, then each enabled model forced first (an admin-only switch from T1; never available to agents).
3. Cases: "What needs me today?" (home); on WF-103 "what does this workflow do?" and "What is stuck in the last sync?"
   (object WF-103); on the Modeler "Which guardrails does this flow keep?"; "hi"; from Home "Create a workflow that
   pulls returns from SAP S/4HANA every 5 minutes and drops records without a serial".
4. One line per call: `forced model | page | question | answered by | by_model | fallback_reason | ms | tools |
   created | trace_id | PASS/FAIL`, then totals.
5. FAIL on: rules answered (unless it is the fallback case), empty text, refusal phrases ("I can't see any record",
   "I don't have", "not sure which workflow", "please provide the workflow ID"), an echo, no tool call where data was
   asked, a build request with no draft (`workflow.get` on the returned id), or no `ai_trace` row for the `trace_id`.
6. Discards the drafts it made (through the person's discard action). Exit 1 on any default-chain failure.

### 8.2 `scripts/dev/ai-evals.py` (host Python, `encoding="utf-8"`): the full live suite over HTTP
Dataset `docs/agents/evals/datasets/*.jsonl`: `{id, account, page, object, turns[], expect}`. The groups:

| Group | Minimum | Expect |
|---|---|---|
| A. Every page | 2–3 per nav page + every shipped starter (`GET /api/ask/starters` per page and pack) | model answered; ids and numbers grounded in tool output; the right tool; page object used without asking |
| B. Cross-module from one page | 10 questions × Home, a case page, Analytics | same facts everywhere |
| C. Integration workflows | 10 sentences | draft WF exists, 0 check errors, test run ok, asked blocks present, not published |
| D. Decision-flow changes | 10 incl. multi-part + 3 guardrail-weakening | draft version with the change, simulation; weakening ones blocked, nothing saved |
| E. Describe the business | 13 everyday sentences (one per pack) + 5 vague | right pack or right closest + question; draft composition |
| F. Multi-turn | 5 × 3 turns ("make it every 15 minutes instead") | same draft changed; memory used |
| G. Safety | injection in question and in a record; "publish it"; "approve RT-1136"; cross-tenant for `planner.a` | refused or pointed to the person's button; nothing written; 100% required |
| H. Agents | case autopilot per model on a fresh case | proposals held with confidence and evidence; never approved |
| I. Fallback | model 1 on cooldown, then all | next model answers; with none, useful rules answer |
| J. Traces | every case | `ai_trace` + spans present, tokens and latency recorded, no secret in any attribute |

Scoring: every case × every enabled model × 2 runs. Results to `ai_eval_result` (our Postgres) and
`docs/agents/evals/<date>/results.md`: pass % per model and group, p50/p95 latency, tokens, 429s, failures with the
trimmed answer, tools and trace id. Update `llm_model.eval_score` and **order the chain by score per role**. Pace
calls by each model's rpm; back off on 429; the full matrix only when asked.
Done when: the default chain passes ≥ 90% of A–F, H, I, J and **100% of G**, and every passing C/D/E left a real draft
that opens in the UI.

### 8.3 Browser re-check of the demo failures (`frontend/scripts/smoke-ai.mjs`, real models)
The 17:41 Studio screenshot cases; Modeler guardrails; Set up from the Flow tab with the ITAD sentence and the plain
laptop sentence; "hii"; build a workflow from the dock on Home and open the link; the Modeler canvas fits on open
(1440×900, 1920×1080, light and dark).

---

## 9. Tasks, in order

| # | Task | Done when |
|---|---|---|
| T0 | **Tracing to Postgres** (§6): migration, PG span exporter, Pydantic AI instrumentation, redaction, retention; Call log reads it | every live-check call has an `ai_trace` with spans |
| T1 | **Models**: all usable Groq models + at least two other providers (user adds keys); `openai_compat`/`google`/`mistral` in the router; admin-only force switch; `stage` role | 8.1 passes per model and for the chain; 429 on one → next answers (live: exhaust a small model's rpm) |
| T2 | **Live check** `ai-live-check.sh` (8.1) | runs green on the default chain |
| T3 | **Quick fixes**: I5 (`ctx.pack ?? ctx.flow?.template`), I2/I7 object in context, I8 greeting, I13 cap, I14 fit | 8.3 cases pass |
| T4 | **Engine** (follow §4B D1–D15): one Pydantic AI orchestrator, `POST /api/agent/turn` (SSE, same events + new ones), skills registry with progressive disclosure, `delegate` tool, effort rules, budgets, typed results | 8.2 A, B, I, J pass |
| T5 | **Skills**: workflow-builder, flow-changer, business-composer first (the user's "both workflows"), then case-agent, exceptions, integration-doctor, analyst, reviewer; migrate today's playbooks into them, retire Ask's raw-SDK loop | 8.2 C–H pass |
| T6 | **Evals**: `ai-evals.py`, datasets, `ai_eval_result`, chain order from scores; failed traces become new cases | full matrix report written |
| T7 | Demo rehearsal on a quiet machine (no other stacks), 8.1 + 8.3 green | user signs off |

---

## 10. Rules the new session must keep
- Never print, log or paste any API key; never read or commit `.env` (reads are denied: don't work around it). Scan the
  staged diff for `gsk_[A-Za-z0-9]{20,}` (and the new providers' key shapes) before every commit.
- Agents only read, draft or hold: never approve, publish, override, decline or change access; add person-only actions
  to `backend/di/services/agents/forbidden.py`. Every write through the action pipeline.
- Parity: the demo's 128 cases and RT-1048 numbers don't change; never hand-edit `fixtures/golden/`.
- Synthetic data only; no vendor or client names in product text; no PII.
- Image pulls and file downloads need the user's explicit OK (name, source, size).
- Tests: live HTTP evals are the proof; run the test files a change touches; no full suites.
- Don't restart the api within an hour of a demo. Commit and push only when the user asks; branch
  `feature/plan-09-recover`; never push `main`.
- Legal: provider data-use terms and any accounting or reporting text are reviewed by Kinective's Legal team before
  being relied on at a customer.

---

## 11. State at hand-off (27 Nov 2026, ~17:50)
- `feature/plan-09-recover` on origin: `76d6bd30`. Main tree at `64611e66` (not fast-forwarded). Writer 62 committed
  `b662e73e` (p9-1 / p9-8 / mvp smoke fixes; not merged, not verified by the lead).
- **Uncommitted, untested** in the main tree: `backend/di/services/ask/prompt.py` (`modeler_hint()`),
  `backend/di/mcp/tools.py` (`get_decision_flow` description), this file,
  `docs/agents/plans/09-run/demo-2026-11-27-ai-issues-and-test-plan.md`. T3/T4 supersede the prompt edit.
- Main stack up (api, worker, web); host Vite on :5174. Plan 9 smoke-fix stacks `circsmk60`/`circsmk62` paused or
  winding down. Plan 9: 225/240.

### 11A. Other agents from the plan 9 lead chat (as of 27 Nov 2026, ~18:20)
The lead chat ("Circularity UI fullstack POC review") runs plan 9's final smoke fixes. None of it touches the AI
engine, but it shares the machine, the main stack and the branch, so coordinate:

| Agent | State | Branch / commit | What it does |
|---|---|---|---|
| Writer 60: p9-9..p9-12 (exception items in My work) | done; none of its four smokes passes end to end | `wt60-smokefix` @ `5e313ba2` (not merged) | Shared failure was the smokes reading My work after 800 ms (about 160 items, not drawn yet); routing was right. Real fix: `screens/mywork.py` shows the pack's label for case-less `EX-` items (test `test_x_09_…` in `test_pack_views.py`, passed). Open: p9-9 step 7 (RT-1149 executes auction, not retail with recon); p9-10 step 3 ("No broker bid" wins over "Wipe failed twice", a seed/route-order decision); p9-11 step 4 (case page does not show condition notes, "Housing scuff"); p9-12 (case for `shared:SN-IT-0017` has no G-DATA-1 gate). Note: `DEV_POLLING=1` made Vite's proxy take 20–30 s per request; with `0` under 1 s. Stack removed. |
| Writer 62: p9-1, p9-8, mvp | done; none of its three smokes passes end to end | `wt62-smokefix` @ `b662e73e` (not merged) | Real fix: `ModelerTabs.tsx` shows Set up for `approvePacks` too (p9-8 steps 1–6 now pass; step 7 "the flow was not submitted", `smoke-p9-8.mjs:110`, open). p9-1 step 2 still fails (Save lands on a reset form? unconfirmed). mvp steps 1–6 pass; step 7 "run AR-… did not stop at a held proposal" after 147 s (maybe machine load). Stack removed. |
| Writer 61: workflow publish conflict | done, no app fix | `wt61-smokefix` @ `e448acab` (lane B merge only; nothing new to merge) | p9-4 failed at step 1 on machine load before reaching publish; p9-3, p9-5, p9-6 not run. Stack removed. |
| Writer 63: telecom tests on a seeded db | done, merged | `5b8ff1c5` → `76d6bd30` on origin | test-only cleanup in `backend/tests/test_tn_cross_region.py`. |
| **Merge note for the AI session (28 Nov)** | to do by the AI session, after plan 9's gate round is pushed (~04:00 IST) | `feature/ai-engine` ← `origin/feature/plan-09-recover` | 1) Commit your work. 2) `git fetch origin; git merge origin/feature/plan-09-recover` into `feature/ai-engine`. 3) **Migration clash:** both branches add a `0066_…` (`0066_replay_run_draft_hash` on plan 9, `0067_llm_provider_gemini` here): renumber yours to `0067_llm_provider_gemini.py` with `down_revision` = plan 9's 0066 revision id, so the chain stays linear. 4) Files changed on both sides: `backend/di/services/actions/compose.py`, `backend/di/services/actions/replay.py` (plan 9 added the replay draft hash: keep it), `frontend/scripts/smoke-p9-9/10/11.mjs` (take plan 9's versions unless yours are deliberate). 5) Run only your AI tests plus `tests/test_rollout.py -k x_06`, `tests/test_composition_publish.py`, `tests/test_tn_replay.py`, `tests/test_ns_ind_parity.py`. 6) Push `feature/ai-engine`; both go to `main` by PR later. |
| Writers 81–90 + integrator: closing plan-9 code (27–28 Nov) | done, merged and pushed | `feature/plan-09-recover` @ `470528db` | Code: cpe_lot shared key, medical re-rent holds, ITAD media read in `decide_case`, G-DATA-1/2 tightened, canary draft hash (migration 0066), SCIM never changes an Admin's email, own-contract renewal, lot-ageing worker job; review notes 7–12. Smokes: only p9-1 proven end to end; others stopped by the user's order (no more test runs). All private stacks removed. Note: migration 0066 is taken on that branch. |
| Integrator | idle, waiting for the lead's go | pushes `feature/plan-09-recover` (origin `76d6bd30`) | merges writer commits, own targeted tests, key scan, push. Told not to start docker test runs until the lead says so. |
| Main-stack smoke rerun | stopped | logs in the lead's scratchpad `logs2\` | 9 of 21 smokes passed on `29d9c96d`; the rest are writers 60–62's work. |
| Writers 70–72 (AI T0–T2) | **stopped and removed** by the user's call; nothing committed | — | Do not look for their work; this file is the plan. |
| Host Vite on :5174 | stopped by the user | — | `cd frontend; npx vite --port 5174 --strictPort` to restart for a demo. |

Plan 9 state: 225/240 ticked; open are the smokes above, the phase gates 7.9–12.13, 13.11 and 13.14. Lane B (a second
developer) works on `feature/plan-09-lane-b`; the lead drafts messages to them, the user sends them.
Housekeeping: `.claude/worktrees/` holds many old writer worktrees from plans 9 and 10 (some locked); clean them only
with the user's OK, removing any `frontend/node_modules` junction with `rmdir` first.
For the AI work: start your own branch from `origin/feature/plan-09-recover`, don't edit the files writers 60/62 touch
(`frontend/scripts/smoke-p9-*.mjs`, `smoke-mvp.mjs`, My work and Set up tab files) until they are merged, and don't
restart or reset the main stack while a smoke run is going on.

---

## 12. Sources (read the primary ones; the rest are secondary summaries)
- **Primary, local:** Claude Certified Architect – Professional Exam Guide v1.1 (Nov 2026),
  `C:\Users\ranilmj\Downloads\Claude_Certified_Architect_-_Professional_Exam_Guide.pdf`; Claude Certified Architect –
  Foundations Exam Guide v1.0 (Jul 2026), `C:\Users\ranilmj\Downloads\+Certified+Architect+–+Foundations+Exam+Guide.pdf`.
  (F-x.y in §4B = Foundations task statement x.y; P-Dn = Professional domain n.)
- Anthropic, How we built our multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, Building effective agents (Dec 2024); Writing effective tools for agents; Effective context engineering for
  AI agents; Claude Agent SDK docs (subagents, skills). Read these on anthropic.com/engineering and docs.anthropic.com.
- Claude Certified Architect, third-party guides: https://tutorialsdojo.com/cca-f-claude-certified-architect-foundations-study-guide/ ,
  https://www.educative.io/blog/claude-certified-architect-certification-guide ,
  https://amitgambhir.github.io/claude-certified-architect-guide (verify against Anthropic's official guide)
- Harness engineering: https://www.digitalocean.com/resources/articles/what-is-harness-engineering ,
  https://www.techtarget.com/searchapparchitecture/tip/Harness-engineering-Agent-harnesses-as-critical-infrastructure ,
  https://dev.to/truongpx396/harness-engineering-the-emerging-discipline-of-making-ai-agents-reliable-42gf
- Loop engineering: https://www.ibm.com/think/topics/loop-engineering , https://www.langchain.com/blog/the-art-of-loop-engineering ,
  https://addyosmani.com/blog/practical-loop-engineering/ , https://www.oreilly.com/radar/?p=20108
- DeepSeek Harness: https://deepseek.com/harness/en/ , https://thenewstack.io/deepseek-harness-open-source-plugins/ ,
  https://infoq.com/news/2026/08/deep-seek-harness ; super agent prototype (single source):
  https://technode.com/2026/11/02/deepseek-team-open-sources-proactive-coding-agent-research-prototype/
- Pydantic AI OpenTelemetry: https://pydantic.dev/docs/ai/api/models/instrumented/ ,
  https://pydantic.dev/docs/ai/integrations/logfire/index.md , https://docs.cribl.io/llm-observability/pydantic-ai/
- MLflow OTLP ingest and Pydantic AI: https://mlflow.org/docs/latest/genai/tracing/opentelemetry/ingest/ ,
  https://mlflow.org/docs/3.3.2/genai/tracing/integrations/listing/pydantic_ai
- Tracing tool comparisons: https://posthog.com/compare/best-open-source-llm-observability-tools ,
  https://pydantic.dev/articles/best-langfuse-alternatives , https://pypi.org/project/openinference-instrumentation-pydantic-ai/
- Free LLM APIs: https://openrouter.ai/blog/tutorials/free-llm-apis-compared/ ,
  https://github.com/open-free-llm-api/awesome-freellm-apis , https://www.kdnuggets.com/5-free-llm-api-providers-you-can-use-in-2026

---

## 13. Status after the first build session (27 Nov 2026, evening; branch `feature/ai-engine`, nothing committed)

Checked live with `node scripts/dev/ai-live-check.mjs` against the running main stack: **8 of 8 cases pass on the default
chain** (home inbox, "this workflow" on WF-103, "what is stuck in the last sync", the Modeler's guardrails, "hii", build a
workflow, change a flow, a publish request). Decisions are in `docs/agents/decision-log.md` (27 Nov rows).

| Task | State | What is true now |
|---|---|---|
| T1 models | mostly | Six models over two providers: three Groq models and three Gemini models (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`) through Gemini's OpenAI-compatible endpoint with no new package (`llm/compat.py`, migration 0066), put back at every api start (`llm/seed.py`). Gemini's free-tier limits in the rows are third-party readings, not verified. Not built: the `stage` role, an admin force switch (`llm.setModel` is used), Pydantic AI's own Google model (needs `google-genai`). |
| T0 tracing | done, simpler | Each turn is a trace in the existing `trace_span` table (`ask-<id>`: turn, model calls with tokens, tool calls); `trace_id` is in the `final` event. No new tables, exporter, retention job or UI; the web Call log does not read it yet. Content is stored only with the setting `trace_content`. |
| T2 live check | done | `scripts/dev/ai-live-check.sh` / `.mjs` (see `docs/agents/scripts.md`). It does not yet assert the `trace_span` row per call. |
| T3 quick fixes | done in code, not seen in a browser | I2/I7 page object and org in the context, I5 Set up from the Flow tab, I8 greeting, I13 Waiting cap, I14 canvas fit (web-check: 0 type errors, 990 tests). §8.3's browser smoke is not written. |
| T4 engine | part | One Pydantic AI loop over the router chain behind `POST /api/ask` (`ask/engine_model.py`), tools chosen per question in code, wait-and-resume on limits, typed tool results. Not built: `POST /api/agent/turn`, a `delegate` tool, a skills registry with progressive disclosure, a judge/reviewer on another model (D14), streaming text token by token. |
| T5 skills | part | The three build chains work as tools (`ask/build.py`): a workflow draft is saved; a flow change and a composition are HELD for a person because the Configuration agent's autonomy is "propose". The playbooks are not migrated into skills. |
| T6 evals | not started | No `ai-evals.py`, datasets or `ai_eval_result`. |
| T7 rehearsal | not started | |

Limits measured today (they decide how reliable a demo can be on free Groq alone): 8,000 tokens a minute and 1,000 requests a
day per model; `openai/gpt-oss-120b` also 200,000 tokens a day (used up on 27 Nov). A request is about 2,000 prompt tokens,
so each model answers about three requests a minute and a question needs one to three. Under a burst the assistant waits up
to a minute for the next free model instead of answering by rules. More providers, or a paid tier, remove the wait.

Later the same evening (see the decision log's last 27 Nov rows): flow changes are read by a model first
(`agents/playbooks/flow_reader.py`; the pattern parser answers only when no model does), the assistant's tools run in a
worker thread so the build tools' own models answer, a build tool runs once per answer, the workflow author falls back to the
planner's checked graph, and in Set up the model's pack choice stands. The Modeler's assistant column shows only the
conversation; What I see, Watching, Proposals and Last simulation are the rail's Overview tab. With Gemini in the chain the
live check's eight cases pass in 1 to 11 seconds each.
