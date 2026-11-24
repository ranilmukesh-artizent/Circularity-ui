# F. Tier 3b: the agent stack, end to end (research, 24 Nov 2026)

Part F of the platform research (brief: [00-brief.md](00-brief.md)). The question, in the user's words: "agentic
processing end to end, idk which stack to use". This report re-checks the prior decision
([../2026-11-agent-foundation.md](../2026-11-agent-foundation.md)) against the state of each project on 24 Nov 2026 and
turns it into one stack and one reference architecture. Every version, date and licence carries a source number
(list at the end). Anything not confirmed from a primary source is marked **unconfirmed**. Licence, security and
authorization statements are research inputs only: **they need review by Kinective's Legal team before anyone relies
on or acts on them.**

## Summary

- **The prior decision holds.** Our runtime stays the control plane (pipeline, proposals, journal, queue); Pydantic AI
  2.73.0 (MIT, 24 Nov 2026) runs the LLM loop behind our own `AgentLoop` port; LangGraph 1.2.24 stays the fallback.
- **One change to how approvals map:** use Pydantic AI's *external* deferred calls (`CallDeferred`), not
  `requires_approval`. `proposal.accept` already runs the held action as the person; the resumed run must receive
  that result, never run the tool a second time.
- **No durable-execution engine now.** A run waiting days for a person holds no process: state is in Postgres and the
  `after` hook wakes it. Add DBOS (MIT, an in-process library whose system database is Postgres or SQLite; Postgres
  recommended for production) only on the triggers in section 3 (corrected in verification, see V-verification.md).
  Reject Restate (BSL)
  and Inngest (SSPL) for anything we redistribute.
- **LLM routing: a small in-house router** (per-model budgets and cooldowns in Postgres) that feeds Pydantic AI's
  `FallbackModel`. No LiteLLM proxy: its PyPI releases were compromised twice in 2026 (Mar, Oct) and it adds a service.
- **Tracing: OTel GenAI spans from Pydantic AI into a Postgres span table** shown on the Agents page; OTLP export for
  customers who have a backend; Langfuse only as an opt-in Compose profile (it needs ClickHouse, Redis and S3).
- **Evals: pydantic-evals in CI** on a test model (no key), a nightly live run, and an injection corpus. Safety stays
  architectural: the agent only drafts or proposes, so a hijacked agent can do nothing that a person doesn't approve.

## 1. What is fixed by the code (read-only review, 24 Nov 2026)

| Piece | Where | What it fixes for the stack |
|---|---|---|
| One write path | `backend/di/services/actions/pipeline.py` | 12 steps; step 6 agent gate (forbidden list, `commit` needs `confirmed`), step 8 `limits.check`, step 9 idempotency on `action_journal.idem_key`, step 9b hold for a person, step 11 journal with `preparer` and `run_id`. Every agent tool call must be `invoke(action, input, ctx)` with `ctx.preparer` and `ctx.run_id`. |
| Forbidden list | `backend/di/services/agents/forbidden.py` | Approve, override, decline, `access.`, `agent.`, `proposal.`, `source.`, `workflow.publish/setStatus/delete`, `flow.approve/publish/reject/rollback`, `model.promote/propose`, `org.*`. Checked in the pipeline whatever the transport. |
| Tool catalogue | `backend/di/services/agents/catalog.py` | Every action as a JSON Schema 2020-12 tool with `agent_allowed`. Schemas are thin today (type, required, minLength, one example); no enums or descriptions per field. |
| Proposals | `backend/di/services/agents/proposals.py` | `hold()` stores the call; `proposal.accept` runs it as the deciding person; the agent's own requester only rejects (F3a). Holding is per agent (`autonomy == "propose"`), not per action or per value. |
| Runtime | `backend/di/services/agents/runtime.py` | `agent_run` (`running/waiting/stopped/failed/done`, JSON `state`), `agent_run_step`, one `agent.step` job deduped per run, `wake()` on a decided proposal, `resume_waiting()` from `@after("decision.approve")`. Deterministic playbook only. |
| Job queue | `backend/di/core/jobs.py` | Priorities, dedupe keys, backoff retries, dead letters, heartbeat reaper, `run_after`, LISTEN/NOTIFY. |
| Workflow engine | `backend/di/workflow/` | Triggers (schedule, event, approval, file, case) and Wait steps that park records for days via a `run_after` job (`waits.py`). The pattern "park in Postgres, come back on a job" already exists. |
| MCP server | `backend/di/mcp/server.py` | `mcp==2.3.0` low-level `Server`, Streamable HTTP, stateless JSON, bearer account JWT plus `X-Agent`; 12 hand-written parity tools. |
| Ask | `backend/di/services/ask/` | `AskModel` port, `GroqModel` (SDK retries off so a 429 falls back at once; free tier ~30 req/min, 8,000 tokens/min), rule-based fallback, seven safety tests (`safety.py`). |
| Stack | `backend/requirements.lock`, `docker-compose.yml` | FastAPI 0.115.6, pydantic 2.14.4, SQLAlchemy 2.0.36, psycopg 3.2.3, `opentelemetry-api` only (no SDK), Postgres 16. |

What is missing: an LLM reasoning loop, a model router with per-model limits, tracing with storage, evals, per-agent
credentials, per-action/per-value hold policy, draft-only actions for sources and adapters, and richer tool schemas.

## 2. Agent frameworks (re-check)

| Framework | Latest (date) | Licence | HITL / pause | Durability | Fit for us |
|---|---|---|---|---|---|
| **Pydantic AI** | 2.73.0 (24 Nov 2026); 2.71.0 on 19 Nov [S1] | MIT [S1] | Deferred tools: `requires_approval`/`ApprovalRequired` or `CallDeferred`; run ends with `DeferredToolRequests`; resume with `DeferredToolResults` + stored `conversation`; caller owns the state [S3] | Optional integrations: Temporal, DBOS, Prefect, Restate, Lambda, Airflow, Absurd, pgtask, Azure Durable Task [S2, S4] | **Best.** Pydantic-native, stateless pause, `FallbackModel`, OTel, evals, AG-UI streams [S2]. |
| **LangGraph** | 1.2.24 (20 Nov 2026) [S6] | MIT [S6]; Agent Server Elastic-2.0 (prior note S26) | `interrupt()` + `Command(resume=…)`; node code before `interrupt()` re-runs (prior S21) | Own checkpointer (Postgres 3.2.1, prior S22) | **Fallback.** Second state store beside `agent_run`. |
| OpenAI Agents SDK | 0.26.0 (24 Nov 2026) [S7] | MIT [S7] | `needs_approval`; `result.interruptions`; `RunState.to_json()`/`from_json()`; approve/reject; docs warn the state is not authenticated [S8] | Extras `temporal`, `dapr` [S7] | Viable second fallback; pre-1.0; any-llm/LiteLLM extras for other providers [S7]. |
| Google ADK | 2.15.0 (20 Nov 2026) [S9] | Apache-2.0 [S9] | Tool confirmation (**unconfirmed**) | Session services (**unconfirmed**) | Good A2A story; Google-cloud leaning. Not better for us. |
| Microsoft Agent Framework | 1.26.0 (12 Nov 2026) [S10] | MIT [S10] | Workflows with checkpoints and HITL (**unconfirmed**, PyPI page silent) | Checkpoints (**unconfirmed**) | Azure-leaning; graph workflows would compete with ours. |
| Claude Agent SDK | 0.2.188 (date **unconfirmed**) [S11] | MIT, plus Anthropic's Commercial Terms per README [S11] | Permission callbacks (**unconfirmed**) | Session files (**unconfirmed**) | "Python SDK for Claude Code" [S11]: one vendor's harness. Fails provider neutrality. Fine as an outside MCP client. |
| CrewAI | 1.15.45 (24 Nov 2026) [S12] | MIT [S12] | Human input on tasks (**unconfirmed**) | Flows state (**unconfirmed**) | Role-play crews; weak fit for typed, gated actions. |
| smolagents | 1.26.0 (29 May 2026, per PyPI) [S13] | Apache-2.0 (**unconfirmed**, page links the file) | None found | None | Code agents run Python; the docs say the local executor is not a security sandbox [S13]. Wrong model for a write-gated platform. |
| Agno | 3.2.1 (17 Nov 2026) [S14] | Apache-2.0 [S14] | `needs_confirmation`, AgentOS approvals (prior S4) | AgentOS queue (prior S5) | Value is AgentOS, a second control plane (prior verdict stands). |
| Mastra | `@mastra/core` 1.85.0 (date **unconfirmed**) [S15] | Apache-2.0 [S15] | Workflow suspend/resume (**unconfirmed**) | Own storage (**unconfirmed**) | TypeScript. Would add a Node service next to a Python backend. No. |

**Verdict.** Nothing released since the prior note changes the ranking. Pydantic AI moved from 2.71.0 to 2.73.0 in five
days [S1]: it ships fast, so pin it and keep it behind the port. Two new facts help us: (1) its durable options now
include two Postgres-only engines, Absurd and pgtask, via `pydantic-ai-harness` (0.x, "API may change") [S4, S5]; (2)
its fallback is now also a `ModelFallback` capability with per-model timeouts and sticky mode [S16].

**Correction to the prior mapping (important).** The prior note mapped our proposals to "deferred tools". The right
kind is the *external call* (`CallDeferred`), not `requires_approval`:

- With `requires_approval`, the resumed run executes the tool itself after `ToolApproved` [S3]. Our `proposal.accept`
  already executes the held action, as the deciding person, with its own journal row. Running it again from the agent
  would double the write (idempotency would refuse it, but the journal would then show a refusal, and the actor would
  be wrong).
- With `CallDeferred`, the tool function calls `invoke()`; when the pipeline answers `{"held": pid}`, the function
  raises `CallDeferred` with `pid` in its metadata; the run ends with `DeferredToolRequests.calls`; we store the
  `conversation` [S3] in the run; on `proposal.accept` we resume with `DeferredToolResults` whose value is the
  accepted action's real result (what the person's call returned). On reject we pass a `ToolDenied`-style message, or
  stop the run (today's behaviour).

So the model never decides whether a tool needs approval; the pipeline does, per call. That keeps the safety decision
on the server, where rule 9 of AGENTS.md wants it.

## 3. Durable execution on Postgres

### The question

"Agent proposes, waits days for a person, resumes." Which parts need durability?

1. **The wait itself** (hours to weeks): nothing runs. It needs only a row (`agent_run.status = waiting`, the
   conversation, the proposal id) and a wake-up when the proposal is decided. We have both: `wake()` and the
   `@after` hooks, plus a `run_after` job for time-outs and reminders.
2. **Inside one active burst** (seconds to minutes: model turn, tool call, model turn …): a worker can crash between a
   tool call and the next model turn. What matters is that a re-run does not double a write and does not re-spend too
   much model budget.
3. **Fan-out/fan-in** (sub-agents in parallel, then a join) and **compensation** (undo step 2 when step 4 fails).

Our stack covers 1 fully and 2 with two rules: persist the conversation after every model response (Pydantic AI's
`agent.iter()` exposes each node; **unconfirmed** that its node API suits per-turn persistence in 2.73 without
private APIs), and give every write the idempotency key `run_id:tool_call_id` (pipeline step 9 already honours
`ctx.idem_key`). A crash then repeats at most one model call. Case 3 does not exist yet.

### Options

| Option | Latest (date) | Licence | Infra | Long waits | Verdict |
|---|---|---|---|---|---|
| **Own queue** (`core/jobs.py`) | in repo | ours | Postgres | `run_after`, wake on event | **Now.** Enough for 1 and 2. |
| **DBOS Transact** | 3.6.0 (17 Nov 2026); 3.7.0a5 (20 Nov) [S17] | MIT [S17] | Postgres or SQLite system database (SQLite is the default when no URL is set; Postgres recommended for production), library in our process [S17] (corrected in verification, see V-verification.md) | `DBOS.recv()` with timeout, durable `sleep()` for days or weeks [S17] | **First upgrade** if we hit a trigger below. Pydantic AI integration exists [S2]. Adds its own system tables. |
| Absurd | Apache-2.0 repo, single SQL file, Python SDK [S18, S19] | Apache-2.0 [S19] | Postgres only (stored procedures) [S18] | Sleep and wait for events for "days or weeks" [S18] | Interesting, in production at its author's company ~5 months by Apr 2026 [S18]; young; via `pydantic-ai-harness` 0.x [S4]. Watch. |
| pgtask | no release shown; 122 stars [S20] | MIT [S20] | Postgres 16+ (we run 16) [S20] | Durable `sleep_for` [S5] | Too young (one maintainer, no maturity statement). Watch. |
| Hatchet | `hatchet-sdk` 1.46.0 (13 Nov 2026); 2.0.0a7 (24 Nov) [S21] | MIT [S22] | Go engine + API + dashboard on Postgres; RabbitMQ optional; "Lite" single image [S23] | Durable sleep, event waits [S22] | Good, but a second service and a second queue beside ours. |
| Temporal | Python SDK 1.36.1 (14 Nov, year **unconfirmed**) [S24] | MIT server [S25] | Temporal cluster + its own persistence and visibility store (**unconfirmed** this session) | Signals, timers | Gold standard; heaviest to ship in a customer trial. Only for case 3 at scale. |
| Restate | server release **unconfirmed** | **BSL 1.1**: no "Public Restate Platform Service"; each version turns Apache-2.0 after 4 years [S26] | Own server and log (**unconfirmed**) | Awakeables (**unconfirmed**) | **Reject for redistribution** (source-available). |
| Inngest | release **unconfirmed** | **Server and CLI SSPL** with delayed open-source publication under Apache-2.0; SDKs Apache-2.0 [S27] | Own server, state store (**unconfirmed**) | `waitForEvent` (**unconfirmed**) | **Reject for redistribution** (SSPL). |
| Procrastinate | 3.12.0 (19 Nov 2026) [S28] | MIT [S28] | Postgres | Scheduled jobs | A task queue like ours, not durable execution. No gain. |
| pgmq | v1.10.0 seen in docs (date **unconfirmed**) [S29] | PostgreSQL licence [S29] | Extension or plain SQL [S29] | Visibility timeout | A queue primitive. No gain over `jobs.py`. |

### When a durable engine is worth it (the switch triggers)

Adopt DBOS (first) or Temporal (at scale) when **any** of these becomes true:

1. A playbook needs **parallel sub-agents with a join** or **compensation** across steps (e.g. the "AMS template from a
   sentence" flow drafting flow, mappings and three adapters at once, then a joint test run).
2. A step has a **side effect outside the pipeline** that cannot be made idempotent (e.g. an outside A2A agent that
   charges per call).
3. **Volume**: more than ~10,000 active runs or bursts longer than the job heartbeat window cause reaper requeues
   (measure first; **unconfirmed** where our queue's limit lies).
4. We find ourselves writing a **step-memo table** by hand for a second playbook. That is the moment a library is
   cheaper than our own code.

Until then, a second engine only gives us a second place where run state lives, which is what the prior decision
rejected.

## 4. LLM gateway and per-model fallback

### What we need

Per-model limits (requests/min, tokens/min, requests/day) differ per model and provider; a 429 on one model must move
the call to the next model **without** spending more of the limited one; streaming for Ask; one configuration for Ask,
agents, the Modeler assistant and "Build with AI"; works with an open-weight model on a hosted inference API, a second
provider and a local server (vLLM/Ollama) in a customer's network; no new service in the trial package.

| Option | Latest (date) | Licence | Shape | For us |
|---|---|---|---|---|
| Pydantic AI `FallbackModel` / `ModelFallback` | 2.73.0 [S1] | MIT | In-process. `fallback_on` defaults to `(ModelAPIError, ContentFilterError, OutputTokenLimitExceeded)`; 4xx/5xx raise `ModelAPIError`, `ModelRateLimitError` a subclass; a stream falls back only before its first output; `request_timeout`, `first_event_timeout`, `sticky=True`; failures in `failed_attempts` [S16] | **Use** for the chain. It has no per-model budget or cooldown that we could find [S16] (**unconfirmed** that none exists). SDK retries must be 0 or they delay the fallback [S16, S30]. |
| LiteLLM (SDK + proxy) | 1.110.3 (24 Nov 2026) [S31] | MIT except `litellm/enterprise/` (separate licence) [S32] | Python SDK or a proxy service with budgets, rate limits, fallbacks | **No.** Two compromised PyPI releases in 2026: 1.82.7 and 1.82.8 on 24 Mar 2026 (credential stealer, CI token stolen via a poisoned scanner action) [S33]; 1.107.0 wheels and Docker images including `latest` on 21 Oct 2026 [S34]. The proxy also adds a service and its own database. |
| Portkey gateway | release **unconfirmed**; 13.4k stars [S35] | MIT [S35] | Node/TypeScript service; fallbacks, weighted load balancing, guardrails; 2.0 pre-release moves enterprise features into OSS [S35] | Good gateway, but a Node service in a Python trial package. Use only if a customer already runs it. |
| any-llm (`any-llm-sdk`) | 1.54.0 (24 Nov 2026) [S36] | Apache-2.0 [S36] | One Python interface over providers; separate gateway "Otari" (licence **unconfirmed**) [S36] | Overlaps with Pydantic AI's providers. Not needed. |
| **In-house router** | — | ours | ~200 lines: model list, budgets and cooldowns in Postgres, builds the `FallbackModel` chain per call | **Recommend**, on top of Pydantic AI's model classes. |

### Recommendation: `di/services/llm/router.py`

- **Config** (settings + one table `llm_model`): `{id, provider, model, base_url, key_ref, rpm, tpm, rpd, ctx_tokens,
  tools: bool, structured: bool, roles: [ask, agent, author, judge], priority}`. Keys stay in the encrypted credential
  store we already use for sources (`connectors/`), never in the table.
- **Budget** (table `llm_budget`, one row per model and minute/day window): before a call, `UPDATE … SET used = used +
  :est WHERE used + :est <= limit RETURNING` (atomic, no Redis). Estimated tokens = prompt tokens + `max_tokens`
  (the hosted API counts both, see `groq_model.py`).
- **Cooldown**: on a 429, store `cooldown_until` from `retry-after` (or 60 s) for that model; skip it until then.
- **Chain**: filter by role, capability (tools, structured output, context size), budget and cooldown; order by
  priority; hand Pydantic AI a `FallbackModel` of what is left with provider SDK retries 0 and a per-model
  `request_timeout` [S16]. Nothing left: Ask uses the rule-based fallback (as today); an agent run goes `waiting` with
  `reason = "no model available"` and a `run_after` retry job, never a silent partial run.
- **Sticky per run** (`sticky=True` [S16]): an agent run keeps one model for all turns unless it fails, so a
  conversation does not switch models mid-plan; the model used is recorded on the span and on `agent_run_step`.
- **Providers**: an OpenAI-compatible provider class covers most hosted open-weight APIs and local vLLM/Ollama; add
  Anthropic/Google/Bedrock providers when a customer asks. Ask's `GroqModel` moves behind the same router later.
- **Context budget**: on small tokens-per-minute tiers (8,000 TPM on the free tier, per `groq_model.py`) a 125-tool
  catalogue does not fit. Toolsets must be per playbook (5–20 tools) with a `find_tools` read tool for the rest.

Switch trigger: if a customer mandates a central gateway (theirs), point the router's base URL at it and keep the
budgets as a second guard.

## 5. Observability and evals

### Tracing

| Option | Latest (date) | Licence | Storage | For us |
|---|---|---|---|---|
| OTel GenAI semantic conventions | no tagged release in the new repo [S37] | Apache-2.0 (OTel) | — | Every `gen_ai.*` item still "Development"; moved to `open-telemetry/semantic-conventions-genai` on 12 Jun 2026 with core v1.42.0 (secondary) [S38]. Pin the version Pydantic AI emits; add our own `di.*` attributes. |
| Pydantic AI instrumentation | 2.73.0 [S1] | MIT | any OTel backend [S2] | **Use**: spans per run, model request and tool call. |
| Langfuse | v4.85.0 (24 Nov; year inferred) [S39] | MIT except `ee/` and other `ee` folders [S40] | Web + worker + Postgres + Redis/Valkey + ClickHouse + S3/blob [S41] | Best OSS UI, but four extra services. **Opt-in Compose profile only.** |
| Arize Phoenix | release **unconfirmed**; 12.4k stars [S42] | **Elastic License 2.0** [S42] | **unconfirmed** (SQLite/Postgres per memory) | ELv2 limits offering it as a managed service; shipping it inside our trial needs Legal review. **Don't bundle.** |
| OpenLIT | release **unconfirmed**; 3.1k stars [S43] | Apache-2.0 [S43] | ClickHouse [S43] | Follows `gen_ai.*` [S43]; ClickHouse again. Not bundled. |
| Logfire | SaaS; self-host **unconfirmed** (enterprise) | SDK MIT (**unconfirmed**) | hosted | Not for a self-hosted trial. |
| **Own span table** | — | ours | Postgres | **Recommend** as the default: a small OTel `SpanExporter` that writes finished spans of agent runs into `trace_span` (partitioned by day, 14-day retention), read by the Agents page run view. |

**Recommendation.** Add `opentelemetry-sdk` (only the API is in the lock today). Default exporter: the Postgres span
table, so the trial shows "what did the agent do, with which model, how many tokens, which tool calls, which
proposals" with no new service. `OTEL_EXPORTER_OTLP_ENDPOINT` set: also export OTLP to the customer's backend.
`docker compose --profile observability` adds Langfuse for our own forward-deployed engineers. Content capture (prompts,
tool inputs and outputs) off by default in the trial, on in dev; the pipeline's `SECRET_WORDS` filter also runs on
span attributes. Attributes we add: `di.run_id`, `di.agent`, `di.preparer`, `di.action`, `di.proposal_id`,
`di.tenant`, `di.model_route` (which fallback position answered).

### Evals

| Tool | Latest (date) | Licence | Role for us |
|---|---|---|---|
| **pydantic-evals** | 2.73.0 (24 Nov 2026) [S44] | MIT [S44] | **CI.** Datasets of `Case`s, custom evaluators, an OTel trace per case [S44], trajectory evaluators [S2]. Same library family as the loop. |
| Inspect AI | 0.3.292 (23 Nov 2026), UK AI Security Institute [S45] | MIT [S45] | Optional: agentic safety evals in sandboxes, later. |
| DeepEval | 4.3.5 (24 Nov 2026) [S46] | Apache-2.0 [S46] | Metric library; pushes towards a hosted account ("highly recommended") [S46]; telemetry **unconfirmed**. Not needed. |
| Ragas | 0.4.4 (14 Nov 2026) [S47] | Apache-2.0 [S47] | Retrieval metrics. Only if we add document retrieval (adapter specs). |
| promptfoo | 0.126.0 [S48] | MIT [S48] | Red-team runs (injection, jailbreak) from the CLI. Note: OpenAI announced its acquisition on 9 Mar 2026 and promised to keep the open-source project [S49]. Use as a dev tool, not a dependency. |

**Three eval layers.**

1. **CI (every push, no key):** pydantic-evals datasets in `backend/tests/evals/`, run by `scripts/dev/api-test.sh` with
   Pydantic AI's test models (`TestModel`/`FunctionModel`, **unconfirmed** names unchanged in 2.73) scripted to call
   tools. They check *our* side: toolsets never contain a forbidden action, held writes produce proposals, resume
   passes the accepted result, idempotency holds, spans carry `di.*`.
2. **Nightly live (with keys, outside the gate):** the same datasets against each configured model: tool trajectory,
   `workflow.validate` passing, `flow.simulate` uplift within tolerance of the golden PO scenarios
   (`fixtures/golden/po/`), cost and latency. Scores stored in a table; a drop of more than 10 points blocks a model
   from the `agent` role in the router.
3. **Safety corpus:** extend `services/ask/safety.py`'s seven tests into an agent corpus: planted instructions in
   evidence notes, CSV cells, MCP source results, PDF text, adapter docs and webhook payloads. Pass = the action journal
   holds no write beyond the drafts the scenario allows, and no proposal for a forbidden action exists.

## 6. Safety: prompt injection and output validation

**Threat.** Source data, documents and outside agents' answers flow into the model's context. Research is clear that
model-level defences alone fail; designs that limit what a hijacked model can *do* work. CaMeL separates control flow
from untrusted data and attaches capabilities to values; it solved 77% of AgentDojo tasks with provable security vs
84% undefended [S50]. The six patterns paper names action-selector, plan-then-execute, LLM map-reduce, dual LLM,
code-then-execute and context minimisation [S51].

**Our layers (in order of strength).**

1. **Blast radius (already ours).** Agents never approve, publish or change access (forbidden list in the pipeline);
   writes by `propose` agents are held; every write is journaled with the agent and run. A hijacked agent can at worst
   create drafts and proposals that a person sees with the agent's "why".
2. **Hold by risk and value, not only by agent.** Extend `proposals.holds()` from "agent has autonomy propose" to a
   policy per (agent, action type, input): hold if `value > threshold`, `confidence < x`, the case has a conflict or
   exception, the input touches more than N records, or the call's data came from an untrusted source this run (see 4).
   This is also the brief's "people step in only on high value, low confidence, exceptions and conflicts".
3. **Least privilege per playbook.** Toolset = playbook's list ∩ agent allow-list ∩ `agent_allowed` ∩ the person's
   permissions (the pipeline enforces the last two anyway).
4. **Taint tracking (light CaMeL).** Each tool result carries `provenance: trusted|untrusted` (records from sources,
   documents, MCP-client sources and outside agents are untrusted). Once a run has read untrusted text, its writes are
   held regardless of autonomy (rule in 2). Cheap and explainable; not a proof.
5. **Dual-LLM extraction for documents.** Contracts, adapter docs and PDFs go through a *quarantined* call with no
   tools whose output is a Pydantic model (fields like `may_refurbish: bool`, `clauses: [..]`), validated, then handed to
   the planning agent as data. The planner never sees the raw document. (Pattern 4 of [S51].)
6. **Plan-then-execute for authoring.** "Build with AI" and the AMS-template flow first produce a typed plan (list of
   intended actions) before reading untrusted samples; the runtime refuses tools outside the plan (pattern 2 of
   [S51]).
7. **Output validation.** Structured outputs as Pydantic models; then the action's own `validate()` (step 1); then the
   domain validators (`workflow.validate`, `flow` checks and guardrails, mapping dry run); a failed validation goes back
   to the model as a retry, max 2.
8. **Classifiers (optional, last).** NeMo Guardrails 0.25.0 (19 Nov 2026, Apache-2.0) [S52] is a full dialogue rail
   framework, heavy for us. Guardrails AI 0.11.0 (14 Aug 2026, Apache-2.0) [S53] validators come from a hub (account
   need **unconfirmed**). LlamaFirewall's last PyPI release is 1.0.3 of 29 May 2025 [S54] (licence **unconfirmed** on
   the page): its PromptGuard 2 classifier could flag injected text in tool results, but it adds a model download.
   None of these replaces 1–7; consider PromptGuard-style scoring only as one more input to the hold policy.

## 7. Interop

| Piece | State | Recommendation |
|---|---|---|
| MCP Python SDK | `mcp` 2.3.0 (2 Oct 2026), MIT; ships `MCPServer` [S55] | Keep the low-level server we have. Add a second toolset generated from `catalog.py`. |
| FastMCP (separate project) | 4.2.5 (23 Nov 2026), Apache-2.0 [S56] | Not needed: we generate schemas from the catalogue, not from Python signatures. Its auth helpers are **unconfirmed** from the page. |
| MCP authorization (rev. 2026-07-28) | Server is an OAuth 2.1 resource server; **MUST** serve Protected Resource Metadata (RFC 9728) and point to it in `WWW-Authenticate`; tokens must be audience-bound (RFC 8707 `resource`) and validated as issued for this server; **no token passthrough**; CIMD preferred, DCR deprecated; RFC 9207 `iss` check; `insufficient_scope` 403 with step-up [S57] | Serve `/.well-known/oauth-protected-resource`; keep the account JWT for our own UI; for outside clients, an authorization server issues audience-bound tokens with scopes per action family (`cases:read`, `workflows:draft`, …). Which authorization server (ours, or the customer's IdP) is a decision for plan "per-agent credentials". |
| Tools from the action catalogue | `catalog.py` | Generate: name, title, description, input schema, `readOnlyHint` (risk read), `destructiveHint` (delete/undo actions), `_meta.requiresHumanApproval` (would hold for this agent). Filter by `agent_allowed`, the agent's allow-list and the token's scopes. Enrich `ActionDef.input` with field descriptions and enums first: the schemas are too thin for a model today. |
| A2A | `a2a-sdk` 1.3.1 (17 Nov 2026), Apache-2.0; spec 1.0 with 0.3 compatibility; JSON-RPC, REST, gRPC; `postgresql` extra [S58] | Later (prior order stands): an agent card with 2–3 coarse skills; A2A `input-required` = our run `waiting`. Use the SDK's server, but keep task state in `agent_run` (whether its Postgres extra is a task store is **unconfirmed**). |
| AG-UI | `ag-ui-protocol` 1.0.0 (17 Sep 2026), MIT [S59]; Pydantic AI emits AG-UI streams [S2] | For the Agents page and Ask panel when we add live runs: stream run events (text, tool call, proposal held) as AG-UI over our existing SSE. |
| CopilotKit | MIT, 38.9k stars; AG-UI client with Pydantic AI and LangGraph integrations; "Intelligence" layer is a separate product with cloud and self-host plans [S60] | Optional. Our panel is hand-built and small; read its React components for ideas, adopt only the OSS part if the panel grows. |
| Per-agent identity | today: agent named by `X-Agent` on a person's JWT | Two token shapes: (a) **delegated**: `sub = person`, `act = {sub: "agent:<id>"}` (RFC 8693 actor claim; **unconfirmed** we will use token exchange itself) for runs a person starts; (b) **autonomous**: `sub = "agent:<id>"` from client credentials, for event-triggered runs, acting as a service principal whose permissions are the agent's allow-list ∩ its org scope. In both, `ctx.preparer` comes from the token, never from a header. `proposal.accept` stays person-only. |

## 8. Reference architecture: "agents plan, humans approve"

### Components (new pieces in bold)

```
trigger (case opened, IoT alarm, conflict, schedule, a person in Ask, MCP/A2A call)
   -> domain_event / workflow trigger -> **agent subscription** (agent, playbook, event filter, autonomy policy)
   -> runtime.start(agent, playbook, subject, principal) -> agent_run (running) + job agent.step
di-worker: agent.step
   -> deterministic playbook  (case_autopilot, as today)
   -> **LLM playbook**: AgentLoop port -> Pydantic AI Agent
         model   = **llm.router** (budgets, cooldowns) -> FallbackModel chain (sticky per run)
         tools   = **catalog.toolset(agent, playbook)** -> each tool = invoke(action, input, ctx)
                   ctx: preparer=agent, run_id, idem_key=run_id:tool_call_id, principal from token
         output  = typed (Pydantic) plan / draft / answer
         persist = conversation + usage after each model response -> agent_run.state, agent_run_step
pipeline.invoke: validate, permission, scope, agent gate (forbidden), guard, limits,
                 **hold policy (risk, value, confidence, taint)**, idempotency, handler, journal, events
   held -> agent_proposal + domain_event proposal.held -> tool raises CallDeferred(pid) -> run waiting
person: Home / My work -> proposal.accept (runs the held action as the person, journaled) | proposal.reject
   -> @after hook -> runtime.wake(run) -> DeferredToolResults(accepted result | denied) -> job agent.step
execution: instructions to enterprise systems (existing), confirmations -> journal -> case timeline
tracing: Pydantic AI OTel spans + di.* -> **trace_span** (Postgres) [+ OTLP] ; evals: pydantic-evals in CI + nightly
```

### Sequence (case autopilot with an LLM step, one held write, resume days later)

```mermaid
sequenceDiagram
    autonumber
    participant SRC as Source / trigger
    participant API as di-api (events, triggers)
    participant Q as Postgres job queue
    participant W as di-worker (runtime)
    participant L as AgentLoop (Pydantic AI)
    participant R as LLM router
    participant M as Model A / Model B
    participant P as pipeline.invoke
    participant DB as Postgres (journal, proposals, agent_run, trace_span)
    actor H as Person (approver)

    SRC->>API: return received / IoT alarm (webhook, sync)
    API->>DB: case opened, domain_event case.opened
    API->>Q: enqueue agent.start (subscription matches)
    Q->>W: claim job
    W->>DB: agent_run(running), principal = agent or person+agent
    W->>L: run(playbook, conversation=[], toolset)
    L->>R: request model for role "agent"
    R->>DB: reserve budget (model A), check cooldown
    R-->>L: FallbackModel[A, B], sticky
    L->>M: model request (tools: case_evidence, route_value, decision_submit ...)
    M-->>L: 429 from model A
    R->>DB: cooldown A until retry-after
    L->>M: same request on model B
    M-->>L: tool calls: case_evidence, route_value
    L->>P: invoke(read actions, preparer=agent, run_id)
    P-->>L: data (tagged untrusted where from sources)
    L->>DB: persist conversation + spans
    M-->>L: tool call decision_submit(route=resell, why=...)
    L->>P: invoke(decision.submit, idem_key=run:call)
    P->>DB: hold policy: value above threshold -> agent_proposal(pending), event proposal.held
    P-->>L: {held: pid}
    L-->>W: CallDeferred(pid) -> DeferredToolRequests
    W->>DB: agent_run(waiting, proposal=pid, conversation)
    Note over W,DB: no process waits; hours or days pass
    H->>API: proposal.accept(pid) from My work
    API->>P: invoke(decision.submit as the person, prepared by agent)
    P->>DB: handler + action_journal(actor=person, preparer=agent, run_id)
    P->>W: @after hook -> runtime.wake(run)
    W->>Q: enqueue agent.step
    Q->>W: claim job
    W->>L: resume(conversation, DeferredToolResults{pid: accepted result})
    L->>M: model request (sticky model B, or A if B is down)
    M-->>L: final summary for the case timeline
    L->>DB: persist, spans
    W->>DB: agent_run(done)
    Note over API,DB: execution: instructions to ERP/WMS, confirmations journaled (existing)
```

### Run state (`agent_run.state` for LLM playbooks)

`{account | principal, playbook_version, model_route, conversation (Pydantic AI serialised conversation, incl.
deferred requests), plan (typed), taint: bool, usage: {requests, input_tokens, output_tokens}, waiting: proposal |
approval | model | time, proposal, reason}`. Large conversations move to a child table `agent_run_message` once they
pass ~200 kB (**unconfirmed** threshold). `playbook_version` pins the prompt and toolset, so a run that resumes after a
deploy uses what it started with, or stops with "playbook changed" if that version is gone.

### Agentic CRUD across the platform (generated from the catalogue)

- **One source of truth:** `ActionDef` (registry). From it we generate: the agent toolsets, the MCP catalogue toolset,
  OpenAPI operations per action, and the eval checklist "every agent-allowed action has a case".
- **Create / update** go through the existing actions (`workflow.create/save`, `flow.saveDraft`, `mapping.*` …).
  **Delete** by an agent is always held, whatever its autonomy (add a `destructive` flag to `ActionDef`; risk levels
  today are `read`, `act`, `commit`, `system`).
- **Read** tools return compact, typed views (the screens services already shape them); never raw table rows.
- **Find, don't list:** a `find_tools(query)` read tool searches the catalogue by title and description, so the model
  sees ~10 tools, not 125.
- "Within a week" is realistic for *exposure* (generated MCP toolset + OpenAPI) because the pipeline already exists;
  the real work is enriching input schemas (descriptions, enums) for model use.

### Agents drafting workflow JSON, rules and adapters (draft only)

| Artefact | Agent may | Validation before a person sees it | Person does |
|---|---|---|---|
| Workflow JSON (Connection Studio) | `workflow.create/save` a draft from a typed `WorkflowGraph` Pydantic model generated from the block schemas (`workflow/blocks.py`) | `workflow.validate`; `workflow.testRun` (dry, parks nothing); diff vs current version | publishes (`workflow.publish` is forbidden for agents) |
| Decision rules (Modeler) | `flow.fork/saveDraft/propose/simulate/submit` | guardrail checks, `flow.simulate` over historical cases with uplift and changed decisions | approves and publishes (maker != checker; the requester only rejects) |
| Mapping | draft mapping from source samples (samples are untrusted: dual-LLM extraction) | mapping dry run on held samples; canonical checks | publishes the source's ingest workflow |
| New adapter | **new** `source.draft`: a declarative adapter spec (endpoints, auth type, pagination, fields) like the generic spec-built mocks (`source-sim/sim/generic`), no credentials, no code | schema validation; probe against a mock generated from the same spec; contract test | enters credentials and connects (all live `source.*` stay forbidden; narrow the prefix to the live actions) |
| Template pack ("AMS from a sentence") | a **change set**: list of the calls above held as one proposal | each call validated; whole-set simulation | applies the set with their own permissions |

Generated **code** (Python adapters) stays out of scope: it would need a sandbox and code review; the declarative spec
covers the ~21 system types we know. Revisit only with a sandbox decision.

### Multi-model fallback, tracing and evals in the loop

- Router per call; sticky per run; budgets in Postgres; fallback recorded in spans and `agent_run_step`.
- A run with no model available waits (`waiting: model`) and retries via `run_after`; Ask keeps the rule-based answer.
- Every run visible on the Agents page from `trace_span` + `agent_run_step` + journal rows with its `run_id`.
- CI evals gate merges; nightly live evals gate which models may take the `agent` role.

## 9. ADR-F1: the agent stack

**Status:** proposed (24 Nov 2026). **Supersedes:** nothing; refines the agent-foundation note.

**Context.** We need an LLM reasoning loop for "agents plan, humans approve", across ~125 actions, with per-model rate
limits, a self-hosted trial package, Postgres as the only datastore, and a write path that already enforces approvals.

**Decision.**

| Layer | Choice | Version pin (24 Nov 2026) |
|---|---|---|
| Control plane | Ours: `pipeline.invoke`, `agent_proposal`, `agent_run`, `jobs.py`, journal | — |
| Agent loop | Pydantic AI behind `AgentLoop`; approvals as `CallDeferred` external calls | `pydantic-ai-slim` 2.73.0 (MIT) [S1] |
| Durability | Own queue + per-turn persistence + `run_id:tool_call_id` idempotency | — |
| Models | In-house router (Postgres budgets, cooldowns) → Pydantic AI `FallbackModel`, sticky per run | — |
| Tracing | Pydantic AI OTel GenAI spans → Postgres `trace_span`; optional OTLP; optional Langfuse profile | `opentelemetry-sdk` (to add) |
| Evals | pydantic-evals (CI on test models; nightly live); safety corpus | `pydantic-evals` 2.73.0 (MIT) [S44] |
| Safety | Forbidden list + hold policy by risk/value/confidence/taint + dual-LLM extraction + typed outputs + domain validators | — |
| Interop | MCP (official SDK) with catalogue toolset and OAuth resource-server metadata; then A2A; AG-UI for our panel | `mcp` 2.3.0 [S55], `a2a-sdk` 1.3.1 later [S58] |

**Alternatives considered.**

- LangGraph 1.2.24 as the loop: second state store (checkpoints), resume re-runs node code; keep as fallback behind the
  port.
- OpenAI Agents SDK 0.26.0: viable (`RunState` serialisation maps to our runs [S8]); pre-1.0; second fallback.
- Agno AgentOS, Orkes Conductor, Microsoft Agent Framework workflows, Mastra: second control plane or second language.
- DBOS / Temporal / Hatchet for durability: not needed for waits; DBOS is the first upgrade.
- Restate (BSL 1.1) and Inngest (SSPL): source-available, not for a redistributed package.
- LiteLLM proxy / Portkey gateway: an extra service; LiteLLM's 2026 supply-chain incidents.
- Langfuse / Phoenix / OpenLIT bundled: ClickHouse or ELv2; Postgres span table first.

**Consequences.** We write ~4 small modules (`agents/loop.py`, `llm/router.py`, `observability/pg_exporter.py`,
`agents/toolsets.py`) and one migration (`llm_model`, `llm_budget`, `trace_span`, `agent_run_message`). We own the
integration tests per Pydantic AI upgrade. We can swap the loop library in days because tools, state and approvals are
ours.

**Switch triggers.**

| If … | Then … |
|---|---|
| Pydantic AI breaks the deferred-call or conversation-serialisation contract twice in a quarter, or drops a provider we need | Move the adapter behind `AgentLoop` to LangGraph (or OpenAI Agents SDK `RunState`). |
| Parallel sub-agents with join/compensation, non-idempotent outside side effects, or a hand-written step-memo table appears | Add DBOS (in-process, on our Postgres; it also supports SQLite, so not Postgres-only) (corrected in verification, see V-verification.md); Temporal only at large scale. |
| A customer mandates a central LLM gateway | Point the router at it; keep our budgets. |
| Forward-deployed teams need trace search beyond the Agents page | Ship the Langfuse profile (MIT core) to them, not in the trial. |
| OTel GenAI conventions get a stable release | Re-pin and drop our duplicate attributes. |
| An outside client needs MCP Tasks or enterprise-managed authorization | Revisit when the Python SDK ships them (prior note: not confirmed yet). |

## 10. First steps (fits the prior spike plan)

1. `AgentLoop` port and Pydantic AI adapter with `CallDeferred` approvals; `llm.router` with one model and a test
   model; per-turn persistence; idempotency key per tool call.
2. Hold policy per action type and value (with the brief's thresholds); `destructive` flag; taint flag.
3. `trace_span` exporter and a run view on the Agents page.
4. Two LLM playbooks: `workflow_author` (draft + validate + test run) and `case_planner` (evidence → route proposal).
5. Evals: 10 authoring and 10 case scenarios in pydantic-evals; the injection corpus; nightly live job.
6. Generated MCP catalogue toolset + Protected Resource Metadata; enriched input schemas.

Acceptance: the nine spike tests of the prior note, plus: (a) an accepted proposal resumes the run with the person's
result and the journal shows exactly one row for that write, actor = person, preparer = agent; (b) a 429 on model A
moves the call to model B without a second request to A, and the span shows it; (c) a run that read an injected
instruction from a source record produces only held proposals; (d) the trial package gains no new container.

## Unconfirmed

- Pydantic AI: exact `CallDeferred` metadata API and whether `agent.iter()` supports per-turn persistence without
  private APIs in 2.73; test-model class names in 2.73; whether any per-model cooldown exists in `FallbackModel`
  [S3, S16].
- Claude Agent SDK 0.2.188 release date; Mastra 1.85.0 release date; smolagents licence (page links the file only).
- Google ADK, Microsoft Agent Framework, CrewAI and Mastra HITL/durability details (from the prior note or memory,
  not re-read).
- Temporal server persistence and visibility requirements; Temporal SDK 1.36.1 year; Restate and Inngest storage and
  latest versions; pgmq latest version date.
- Absurd's and pgtask's maturity beyond their authors' statements; whether `a2a-sdk`'s `postgresql` extra is a task
  store.
- OTel GenAI: secondary sources only for the repo move date (12 Jun 2026) and status; no tagged release seen.
- Langfuse release year (page shows "24 Nov"); Phoenix storage backends; OpenLIT and Portkey latest releases; Logfire
  self-host terms; any-llm's gateway (Otari) licence; DeepEval telemetry defaults; Guardrails Hub account need;
  LlamaFirewall licence.
- Whether the promptfoo acquisition closed and whether its licence changed afterwards [S49].
- Our own queue's practical limit on active runs (needs a load test).
- Use of RFC 8693 token exchange for delegated agent tokens (design proposal, not verified against a chosen IdP).

## Legal note

Licence findings in this report (MIT, Apache-2.0, PostgreSQL, Elastic License 2.0, BSL 1.1, SSPL with delayed open
publication, split licences with enterprise directories in LiteLLM and Langfuse, Anthropic's commercial terms on the
Claude Agent SDK), the supply-chain incident summaries and the authorization design (OAuth 2.1, RFC 9728, RFC 8707,
CIMD, RFC 8693) are research inputs only. **They need review by Kinective's Legal team before anyone relies on or acts
on them**, in particular before any of these components is bundled into the trial package redistributed to customers.

## Sources (accessed 24 Nov 2026 unless stated)

- S1 `pydantic-ai` on PyPI: 2.73.0 (24 Nov 2026), 2.71.0 (19 Nov), 2.70.0 and 2.69.0 (17 Nov), 2.68.0 (12 Nov); MIT: https://pypi.org/project/pydantic-ai/
- S2 Pydantic AI repository README (durable engines incl. Absurd and pgtask, providers, AG-UI and Vercel AI streams, evals, fallback, OTel; 21.4k stars): https://github.com/pydantic/pydantic-ai
- S3 Pydantic AI deferred tools (`requires_approval`, `ApprovalRequired`, `CallDeferred`, `DeferredToolRequests/Results`, store the `conversation`): https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/
- S4 Pydantic AI durable execution overview (nine engines): https://pydantic.dev/docs/ai/integrations/durable_execution/overview/ ; Absurd harness: https://pydantic.dev/docs/ai/harness/absurd/
- S5 Pydantic AI harness, pgtask (`PGTaskDurability`, harness 0.x): https://pydantic.dev/docs/ai/harness/pgtask/
- S6 `langgraph` on PyPI, 1.2.24 (20 Nov 2026), MIT: https://pypi.org/project/langgraph/
- S7 `openai-agents` on PyPI, 0.26.0 (24 Nov 2026), MIT, extras incl. `temporal`, `dapr`, `any-llm`, `litellm`: https://pypi.org/project/openai-agents/
- S8 OpenAI Agents SDK, human in the loop (`needs_approval`, `RunState` serialisation, unauthenticated state warning): https://openai.github.io/openai-agents-python/human_in_the_loop/
- S9 `google-adk` on PyPI, 2.15.0 (20 Nov 2026), Apache-2.0: https://pypi.org/project/google-adk/
- S10 `agent-framework` on PyPI, 1.26.0 (12 Nov 2026), MIT: https://pypi.org/project/agent-framework/
- S11 `claude-agent-sdk` PyPI JSON, 0.2.188, MIT, "Python SDK for Claude Code", README refers to Anthropic's Commercial Terms: https://pypi.org/pypi/claude-agent-sdk/json
- S12 `crewai` on PyPI, 1.15.45 (24 Nov 2026), MIT: https://pypi.org/project/crewai/
- S13 `smolagents` on PyPI, 1.26.0 (29 May 2026), sandbox warning: https://pypi.org/project/smolagents/
- S14 `agno` on PyPI, 3.2.1 (17 Nov 2026), Apache-2.0: https://pypi.org/project/agno/
- S15 `@mastra/core` npm registry, 1.85.0, Apache-2.0: https://registry.npmjs.org/@mastra/core/latest
- S16 Pydantic AI model fallback capability (`fallback_on` defaults, streaming, retries, timeouts, sticky): https://pydantic.dev/docs/ai/capabilities/model-fallback/
- S17 `dbos` on PyPI, 3.6.0 (17 Nov 2026), 3.7.0a5 (20 Nov), MIT, Postgres or SQLite system database (https://docs.dbos.dev/python/reference/configuration) (corrected in verification, see V-verification.md), `recv`, durable `sleep`: https://pypi.org/project/dbos/
- S18 "Absurd in production" (4 Apr 2026): https://lucumr.pocoo.org/2026/4/4/absurd-in-production/
- S19 Absurd repository README (Apache-2.0): https://raw.githubusercontent.com/earendil-works/absurd/refs/heads/main/README.md (via search summary)
- S20 pgtask repository (MIT, Postgres 16+, 122 stars): https://github.com/Kludex/pgtask
- S21 `hatchet-sdk` on PyPI, 1.46.0 (13 Nov 2026), 2.0.0a7 (24 Nov), MIT: https://pypi.org/project/hatchet-sdk/
- S22 Hatchet repository (MIT, Postgres durability layer, durable tasks, event waits; 8.3k stars): https://github.com/hatchet-dev/hatchet
- S23 Hatchet self-hosting (API, engine, Postgres; RabbitMQ optional; Lite image): https://docs.hatchet.run/self-hosting
- S24 Temporal Python SDK releases (1.36.1, 14 Nov): https://github.com/temporalio/sdk-python/releases
- S25 Temporal server repository (MIT): https://github.com/temporalio/temporal
- S26 Restate LICENSE (BSL 1.1, Additional Use Grant, Change License Apache-2.0 after four years): https://raw.githubusercontent.com/restatedev/restate/main/LICENSE
- S27 Inngest repository (server and CLI SSPL with delayed open source publication under Apache-2.0; SDKs Apache-2.0): https://github.com/inngest/inngest
- S28 `procrastinate` on PyPI, 3.12.0 (19 Nov 2026), MIT: https://pypi.org/project/procrastinate/
- S29 pgmq repository (PostgreSQL licence, extension or SQL-only; 5.4k stars): https://github.com/pgmq/pgmq
- S30 Pydantic AI issue on provider retries delaying fallback: https://github.com/pydantic/pydantic-ai/issues/2837 (via search summary)
- S31 `litellm` on PyPI, 1.110.3 (24 Nov 2026), MIT expression: https://pypi.org/project/litellm/
- S32 LiteLLM LICENSE (`litellm/enterprise/` under a separate licence, rest MIT): https://raw.githubusercontent.com/BerriAI/litellm/main/LICENSE
- S33 Snyk, LiteLLM 1.82.7/1.82.8 backdoored via a poisoned scanner action (24 Mar 2026): https://snyk.io/articles/poisoned-security-scanner-backdooring-litellm
- S34 Mend, LiteLLM 1.107.0 and Docker images compromised (21 Oct 2026): https://mend.io/blog/litellm-1-107-0-compromised
- S35 Portkey gateway repository (MIT, Node/TypeScript, 13.4k stars, 2.0 pre-release): https://github.com/Portkey-AI/gateway
- S36 `any-llm-sdk` on PyPI, 1.54.0 (24 Nov 2026), Apache-2.0, gateway Otari: https://pypi.org/project/any-llm-sdk/
- S37 OTel GenAI semantic conventions repository (no tagged release): https://github.com/open-telemetry/semantic-conventions-genai ; redirect notice: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- S38 Status of OTel GenAI conventions (Development; repo move 12 Jun 2026; secondary, Jul–Sep 2026): https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke ; https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained
- S39 Langfuse releases (v4.85.0, "24 Nov"): https://github.com/langfuse/langfuse/releases
- S40 Langfuse LICENSE (MIT except `ee/`, `web/src/ee/`, `worker/src/ee/`, `packages/shared/src/server/ee/`): https://raw.githubusercontent.com/langfuse/langfuse/main/LICENSE
- S41 Langfuse self-hosting (web, worker, Postgres, Redis/Valkey, ClickHouse, S3): https://langfuse.com/self-hosting
- S42 Arize Phoenix repository (Elastic License 2.0; 12.4k stars): https://github.com/Arize-ai/phoenix
- S43 OpenLIT repository (Apache-2.0, ClickHouse, `gen_ai.*`; 3.1k stars): https://github.com/openlit/openlit
- S44 `pydantic-evals` on PyPI, 2.73.0 (24 Nov 2026), MIT: https://pypi.org/project/pydantic-evals/
- S45 `inspect-ai` on PyPI, 0.3.292 (23 Nov 2026), MIT, UK AI Security Institute: https://pypi.org/project/inspect-ai/
- S46 `deepeval` on PyPI, 4.3.5 (24 Nov 2026), Apache-2.0: https://pypi.org/project/deepeval/
- S47 `ragas` on PyPI, 0.4.4 (14 Nov 2026), Apache-2.0: https://pypi.org/project/ragas/
- S48 `promptfoo` npm registry, 0.126.0, MIT: https://registry.npmjs.org/promptfoo/latest
- S49 OpenAI, "OpenAI to acquire Promptfoo" (9 Mar 2026): https://openai.com/index/openai-to-acquire-promptfoo/
- S50 "Defeating Prompt Injections by Design" (CaMeL), arXiv 2503.18813, v1 24 Mar 2025, v2 24 Jun 2025: https://arxiv.org/abs/2503.18813
- S51 "Design Patterns for Securing LLM Agents against Prompt Injections", arXiv 2506.08837, v1 10 Jun 2025, v3 27 Jun 2025: https://arxiv.org/html/2506.08837v3
- S52 `nemoguardrails` on PyPI, 0.25.0 (19 Nov 2026), Apache-2.0: https://pypi.org/project/nemoguardrails/
- S53 `guardrails-ai` on PyPI, 0.11.0 (14 Aug 2026), Apache-2.0: https://pypi.org/project/guardrails-ai/
- S54 `llamafirewall` on PyPI, 1.0.3 (29 May 2025): https://pypi.org/project/llamafirewall/
- S55 `mcp` on PyPI, 2.3.0 (2 Oct 2026), MIT, `MCPServer`: https://pypi.org/project/mcp/
- S56 `fastmcp` on PyPI, 4.2.5 (23 Nov 2026), Apache-2.0: https://pypi.org/project/fastmcp/
- S57 MCP specification 2026-07-28, Authorization: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- S58 `a2a-sdk` on PyPI, 1.3.1 (17 Nov 2026), Apache-2.0, spec 1.0 with 0.3 compatibility: https://pypi.org/project/a2a-sdk/
- S59 `ag-ui-protocol` on PyPI, 1.0.0 (17 Sep 2026), MIT: https://pypi.org/project/ag-ui-protocol/
- S60 CopilotKit repository (MIT; 38.9k stars; AG-UI integrations; Intelligence layer): https://github.com/CopilotKit/CopilotKit
- Prior note references (S4, S5, S21, S22, S26 of the prior list) are cited as "prior Sn": [../2026-11-agent-foundation.md](../2026-11-agent-foundation.md)
