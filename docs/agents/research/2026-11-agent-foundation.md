# Agent foundation: framework choice and interoperability (research, 24 Nov 2026)

Decision-grade research for the long-term agent foundation of the Circularity Decision Workbench. Every version,
release and capability claim carries a source number; the sources (URL plus date) are listed at the end. Claims we
could not confirm from a primary source are marked **unconfirmed**. Licence, security, authorization, compliance and
privacy statements in this report **must be reviewed by Kinective's Legal team before anyone relies on or acts on
them**.

## 1. Bottom line

- **Keep our own runtime as the control plane, and add Pydantic AI as the agent-loop library.** We already own the
  hard parts: the single write path (`pipeline.invoke`), proposals that hold a write for a person, the Postgres job
  queue, the journal, the forbidden-action list and per-agent tool allow-lists. Pydantic AI's "deferred tools" end a
  run when a tool needs approval and hand the pending call back to the caller [S32], which maps 1:1 onto our
  `agent_proposal` + `runtime.wake`. It is MIT, Pydantic-native, provider-neutral (Groq included), emits OpenTelemetry
  GenAI spans to any backend and ships an eval library [S30, S31, S33].
- **Do not adopt Orkes Conductor or Agno AgentOS as the platform.** Both bring a second runtime that owns run state,
  approvals and (for Orkes) a second workflow engine and queue on a Java server [S10, S12]; that breaks "one pipeline,
  everything journaled". Agno is a strong library but its value is AgentOS, a parallel product server, and it ships
  breaking changes within minor versions [S1].
- **LangGraph is the best of the three named options and our fallback.** MIT library, 1.2.x stable line, Postgres
  checkpointer, the largest adoption [S19, S20, S22]. It loses to Pydantic AI for us because its pause/resume needs its
  own checkpoint store and re-runs node code on resume [S21], and its A2A/MCP endpoints live in the Elastic-2.0
  Agent Server, not the MIT library [S24, S26].
- **Expose the platform in this order:** (1) MCP server generated from the action catalogue with OAuth, (2) OpenAPI plus
  a thin CLI over the same actions, (3) an A2A v1.0 agent card with two or three high-level skills, (4) AG-UI only for
  our own web panel, later. Neither "ACP" needs work: IBM's ACP merged into A2A, and Zed's ACP is editor-to-coding-agent.
- **Hide the framework behind one port** (`AgentLoop`) so the tools, state and approvals stay ours and the library can
  be swapped (to LangGraph) in days, not months.

## 2. What the code already gives us (read-only review of the main repo)

| Piece | File | What it means for the choice |
|---|---|---|
| One write path | `backend/di/services/actions/pipeline.py` | 12 steps incl. agent gate (step 6), agent limits (step 8), idempotency (9), hold for a person (9b), journal with `preparer` and `run_id` (11). Any framework must call this, never the DB. |
| Tool catalogue | `backend/di/services/agents/catalog.py` | Every registry action as a JSON Schema 2020-12 tool with `agent_allowed`. Ready to feed any framework or MCP. |
| Forbidden actions | `backend/di/mcp/policy.py` (`FORBIDDEN_ACTIONS`; in the fix worktree `services/agents/forbidden.py`, checked also in the pipeline) | `workflow.publish`, `flow.approve/publish`, `org.create/update/move`, `source.*`, `proposal.*`, `access.*` ... stay human. Note: `source.*` is forbidden as a whole, so today an agent cannot even *draft* a connector. |
| Proposals | `backend/di/services/agents/proposals.py`, `services/actions/proposals.py` | A held write runs, on `proposal.accept`, as the deciding person, prepared by the agent. This is our human-in-the-loop; no framework HITL is needed. |
| Runtime | `backend/di/services/agents/runtime.py`, `playbooks/case_autopilot.py` | Deterministic playbook, one step per `agent.step` job, states `running/waiting/stopped/failed/done`, woken by a person's action. No LLM loop yet. |
| Durability | `backend/di/core/jobs.py` | Priorities, dedupe, retries, dead letters, reaper, LISTEN/NOTIFY. Enough for agent runs that persist after each model turn. |
| MCP server | `backend/di/mcp/server.py`, `tools.py` | `mcp==2.3.0`, Streamable HTTP, stateless JSON, bearer JWT + `X-Agent`; 12 hand-written demo tools (parity), not the 125-action catalogue. |
| MCP client | `backend/di/connectors/mcp_client.py` | Reads a source through an MCP tool. Already the "consume other agents' tools" half. |
| Modeler | `backend/di/services/actions/modeler.py` | `flow.saveDraft/propose/simulate/submit` are agent-allowed; approve/publish enforce maker != checker (`MAKER_CHECKER`). |
| Workflow Studio | `backend/di/services/actions/*` | `workflow.create/draft/save/validate/testRun/plan` exist; `publish/setStatus/delete` forbidden. |

Implication: we need an **LLM reasoning loop, provider neutrality, tracing and evals**. We do **not** need a second
durable engine, a second approval store or a second API server.

## 3. Head to head: Orkes Conductor vs Agno, then LangGraph

| Criterion | Orkes Conductor (OSS + Orkes) | Agno (library + AgentOS) | LangGraph |
|---|---|---|---|
| Latest version | Conductor OSS v3.34.0, 18 Nov 2026 (Java 25, Spring Boot 4.1, ES8 default) [S9]; `conductor-python` 2.0.0, 3 Aug 2026 [S11] | `agno` 3.2.1, 17 Nov 2026; 3.2.0 on 12 Nov 2026 [S1, S2] | `langgraph` 1.2.24, 20 Nov 2026 [S19]; 1.0 Oct 2025 (secondary, **unconfirmed** date) |
| Licence | Apache-2.0 server and Python SDK [S10, S11]; Orkes enterprise features (human-task forms, RBAC, SSO, secrets, AI prompt studio) are commercial [S16] | Apache-2.0 (changed in Feb 2026 per vendor roundup [S3]) [S2, S8] | Library MIT [S19]; Agent Server (`langgraph-api`) Elastic-2.0 [S26], production self-host needs a LangSmith licence (CLI docs, via [S25], **unconfirmed** detail) |
| Self-host | Java server + Redis/ES or Postgres backends (6 listed) [S10, S18]; Orkes Enterprise self-host on custom pricing [S17] | Self-host AgentOS (a FastAPI app) on your DB; paid hosted control plane (price **unconfirmed**) [S2, S5] | Library runs in-process; Postgres checkpointer `langgraph-checkpoint-postgres` 3.2.1, 14 Nov 2026, MIT [S22] |
| Python fit (FastAPI/Postgres) | Python is a worker SDK polling a separate Java server; a second runtime and DB to operate [S10] | Native Python; AgentOS is its own FastAPI app with its own tables [S2, S5] | Native Python, psycopg 3 [S22]; embeds in our worker |
| Durable execution | Strongest: every model turn and tool call is a server task; resumes after worker crash [S12] | Opt-in durable queue (`QueueConfig(durable=True)`), lease 60 s; external-framework agents do not get durable resume [S5] | Checkpointer per super-step; resume via `thread_id` [S21]; open durable-execution bugs (Nov 2026) [S27] |
| Human in the loop | HUMAN task pauses until approve/reject via API, survives restarts [S15]; approvals per step [S12] | `needs_confirmation` requirements, `continue_run`; AgentOS approval UI, Slack approvals [S1, S4] | `interrupt()` + `Command(resume=…)`; node code before `interrupt()` re-runs on resume [S21] |
| Multi-agent | Agents call workflows and other agents (AGENT task, A2A or Conductor mode) [S13] | Teams (modes), Workflows (parallel, loop, router), external Claude/Codex agents as steps [S1, S3] | Subgraphs, supervisor patterns; `deepagents` 0.7.41 (planning, sub-agents), 20 Nov 2026, MIT [S29] |
| MCP client | `LIST_MCP_TOOLS` / `CALL_MCP_TOOL` tasks [S15] | `MCPTools` [S1, S7] | `langchain-mcp-adapters` 0.3.2, 6 Aug 2026, client only [S23] |
| MCP server | Conductor MCP server (create/run/review workflows) [S14]; workflows as MCP tools via gateway [S15] | AgentOS `/mcp` (`mcp=True`) [S7] | Agent Server `/mcp`, revisions up to 2026-07-28 from langgraph-api 0.18.0rc1 (30 Oct 2026) [S25]; not in the MIT library |
| A2A | AGENT task calls any A2A agent; agents exposed over A2A [S12, S13]; version not stated (**unconfirmed**) | A2A v1.0 since 3.2.0 (breaking: v0.3 routes removed) [S1] | Agent Server `/a2a/{assistant_id}`, A2A v1.0 JSON-RPC only, agent card at `/.well-known/agent-card.json` [S24]; not in the MIT library |
| Observability (OTel GenAI) | Per-task prompt/response/IO recorded in Conductor [S12]; OTel GenAI **unconfirmed** | OTel via OpenInference instrumentation, stored in Agno DB or any OTel backend [S6]; OpenInference is not the OTel GenAI convention [S28b] | Through LangSmith instrumentation; OTel-only export possible with `LANGSMITH_OTEL_ONLY` [S28] |
| Evals | None found (**unconfirmed**) | In the paid control plane (**unconfirmed** scope) [S2] | LangSmith (commercial); OSS options **unconfirmed** |
| Model neutrality | Many providers via integrations (**unconfirmed** list); SDK bridges ADK, LangGraph, OpenAI Agents, Claude Agent SDK [S11] | Multi-provider (**unconfirmed** list) | Any LangChain chat model (Groq, Anthropic, OpenAI, Google) (**unconfirmed** list) |
| Adoption signals | 32.5k GitHub stars [S10] | 43.3k stars [S8]; very fast release cadence | 45.3k stars, cited users [S20] |
| Lock-in and cost | High: workflows, agent state and approvals live in Conductor; enterprise features paid [S16, S17] | Medium: AgentOS tables, auth and control plane; breaking minors [S1, S5] | Low for the library; high if we use Agent Server/LangSmith [S26] |
| Next to our pipeline | Agents would be Conductor workflows whose tasks are workers calling `pipeline.invoke`. Two orchestrators (ours + Conductor), two approval stores (HUMAN task + `agent_proposal`), two journals. | AgentOS would sit beside di-api with its own sessions/approvals; usable as a library only, losing most of its value. | Tools wrap `pipeline.invoke`; approvals via `interrupt()` duplicate `agent_proposal` unless we skip `interrupt()` and use our hold. |

**Verdict, Orkes vs Agno for us.** Agno wins the pair: Python-native, Apache-2.0, current MCP and A2A v1.0, and it
can run in-process. Orkes is the better *durable orchestrator*, but we already have a workflow engine
(`backend/di/workflow/`) and a job queue, and Conductor would add a Java service, a second queue and a second source
of truth for agent state. Neither is the right foundation: both want to own state and approvals that our pipeline
already owns and journals.

**LangGraph** fits better than both because it is just a library over our Postgres. Its weaknesses for us: a second
state store (checkpoints) beside `agent_run`, resume semantics that re-execute node code [S21], open durable-execution
bugs [S27], and its interop endpoints sit in the Elastic-licensed server [S24, S26].

## 4. Does another option beat all three?

| Option | Latest (date) | Licence | For us |
|---|---|---|---|
| **Pydantic AI** | 2.71.0, 19 Nov 2026 [S30] | MIT | **Best fit.** Pydantic/FastAPI-native; deferred tools return pending approvals to the caller, who stores the conversation [S32]; OTel GenAI spans to any backend (semconv 1.37.0) [S33]; Groq, OpenAI, Anthropic, Google, Bedrock, Mistral and more; evals; typed graphs; optional durable engines (Temporal, DBOS, Prefect, pgtask …); AG-UI event streams [S31]. A2A moved out of core to `fasta2a` [S34]. 21.4k stars [S31]. |
| Claude Agent SDK | 0.2.187, 20 Nov 2026 [S35] | MIT | Excellent agent loop but bundles the Claude Code CLI [S35] and targets Claude models (**unconfirmed** for others). Fails provider neutrality as a foundation; fine as an outside client. |
| OpenAI Agents SDK | 0.25.0, 17 Nov 2026 [S36] | MIT (**unconfirmed**) | Pre-1.0, breaking minors [S36]; Temporal integration GA for Python 23 Mar 2026 [S40]. Viable, less Pydantic-native than Pydantic AI. |
| Google ADK | 2.15.0, 19 Nov 2026; 2.0 GA 19 May 2026 [S37] | Apache-2.0 (**unconfirmed**) | Strong A2A story; Google-cloud-leaning deployment. |
| Microsoft Agent Framework | 1.26.0, 12 Nov 2026 [S38]; 1.0 GA 3 Apr 2026 [S38b] | MIT [S38] | Credible (workflows, checkpoints, AG-UI per secondary sources, **unconfirmed**); Azure-leaning. |
| Temporal + agent library | Temporal AI integrations GA [S40] | MIT (Temporal server, **unconfirmed**) | The upgrade path if per-tool-call durability is ever needed; Pydantic AI already integrates [S31]. Not needed now. |
| CrewAI | 1.15.44, 19 Nov 2026 [S39] | MIT [S39] | Role-play crews; weaker fit for a typed, approval-gated action pipeline. |

None beats our "own control plane + a thin library" approach; among libraries Pydantic AI is the clearest fit, with
LangGraph (plus `deepagents` for deep-research-style planning [S29]) as the fallback behind the same port.

## 5. Interoperability foundation (state in Nov 2026)

| Standard | State | Source |
|---|---|---|
| **MCP** | Latest revision **2026-07-28** (28 Jul 2026): stateless core (no `initialize`, no `Mcp-Session-Id`), optional `server/discover`, `Mcp-Method`/`Mcp-Name` routing headers, multi-round-trip requests replace server-initiated elicitation/sampling (elicitation now via `input_required`), cacheable lists. Auth: RFC 9207 `iss` check, DCR deprecated in favour of Client ID Metadata Documents. Tasks moved to the `io.modelcontextprotocol/tasks` extension; MCP Apps and Enterprise-Managed Authorization are extensions. Roots, Sampling, Logging and HTTP+SSE deprecated (12-month window). | [S41] |
| MCP Python SDK | `mcp` 2.3.0, 2 Oct 2026 (what we pin) [S42]; v2 serves 2026-07-28 and earlier revisions [S43]; Tasks extension in the Python SDK **unconfirmed** [S43]. | [S42, S43] |
| MCP server cards | `.well-known` server card (SEP-2127) still in review; path not final. **unconfirmed** | [S44] |
| Enterprise auth | Cross App Access / Enterprise-Managed Authorization: enterprise IdP issues a scoped assertion; Python SDK support "in progress" in Jun 2026. | [S45] |
| **A2A** | v1.0.0, 12 Mar 2026 (breaking: transport mappings separated, `tasks/list`, multi-tenancy scope, OAuth device code + PKCE); v1.0.1, 28 May 2026. Agent card at `agent-card.json` (since v0.3.0), `signatures` on cards since v0.3.0. Joined the Agentic AI Foundation (with MCP) on 17 Aug 2026. SDKs: Python, Go, Java, JS, .NET, Rust. | [S46, S47, S48] |
| **ACP (IBM/BeeAI)** | Agent Communication Protocol merged into A2A in Aug 2025; repository archived (secondary sources). | [S49] |
| **ACP (Zed)** | Agent Client Protocol: editor/IDE to coding agent, JSON-RPC over stdio, remote support "work in progress"; JetBrains co-develops; ACP registry live. Not relevant to a business platform. | [S50] |
| **AG-UI** | Agent-to-user event protocol; 1.0 reported 30 Sep 2026 (secondary). | [S51] |
| **OTel GenAI** | All GenAI spans/attributes still "Development"; conventions moved to a dedicated repo in Jun 2026 (secondary). Pin a version. | [S52] |

**How other products expose themselves.** The pattern across agent platforms is the same: REST/OpenAPI for code,
an MCP server for tool-using agents, an A2A agent card for agent-to-agent delegation. LangGraph's Agent Server serves
`/mcp`, `/a2a/{id}` and an OpenAPI spec from one process [S24, S25]; Agno AgentOS serves REST, `/mcp`, A2A and AG-UI
[S2, S7]; Copilot Studio exposes agents as a remote MCP server or an A2A agent (preview, Oct 2026) and consumes
A2A agents [S53].

**What we should expose, in order.**

1. **MCP (now, extend what exists).** Keep the 12 parity tools; add catalogue-generated tools (`agent_allowed` only,
   filtered by the agent's allow-list) as a second toolset, with `readOnlyHint`/`destructiveHint` from `risk`. Add
   OAuth 2.1 resource-server metadata and CIMD for outside clients (Claude, ChatGPT, Gemini, Copilot), keeping the
   account JWT for our own UI. Add MCP resources for read models (case, flow, workflow, mapping). Defer Tasks until the
   Python SDK ships it.
2. **OpenAPI + CLI (next).** FastAPI already emits OpenAPI; publish one operation per catalogue action and a thin `circ`
   CLI (`circ actions list`, `circ run workflow.validate --input …`) so coding agents and CI use the same pipeline.
3. **A2A v1.0 (then).** One agent card at `/.well-known/agent-card.json` with 2–3 coarse skills ("assess a returned
   asset", "draft an integration for a source", "draft a decision-flow change") that start a run of our runtime. A2A
   task state `input-required` = our run `waiting` on a proposal. Use the official Python SDK [S47]; JSON-RPC binding
   first (what LangGraph also chose [S24]).
4. **AG-UI (later, optional)** for our own agent panel if the SSE stream of Ask is outgrown. **ACP: none.**

## 6. Recommendation

**Primary: keep our runtime + Pydantic AI behind an `AgentLoop` port. Fallback library: LangGraph (+ `deepagents`).**

Why: our safety model (one pipeline, hold for a person, maker != checker, journal) is the product's moat and must stay
the only write path; Pydantic AI is the thinnest library that adds what we lack (LLM loop, provider neutrality, OTel
GenAI, evals) without bringing a competing state store. Its deferred-tool pause is stateless for the framework [S32],
so `agent_run.state` and `agent_proposal` stay the single truth.

**Risks and mitigations**

| Risk | Mitigation |
|---|---|
| Pydantic AI moves fast (2.71 minors by Nov 2026) [S30] | Pin exact version in `requirements.lock`; all use behind `AgentLoop`; contract tests per upgrade. |
| No per-tool-call durability inside one model run | Persist after every model turn; each tool call carries `idem_key = run_id:tool_call_id` (pipeline step 9 already supports `ctx.idem_key`); a crashed job re-runs the turn safely. Temporal/DBOS later only if needed [S31, S40]. |
| Prompt injection from source data (docs, MCP sources, records) | Agents only read or prepare; forbidden list in the pipeline; per-agent allow-lists; tool outputs treated as data; run limits. |
| Standards churn (MCP 2026-07-28 breaking, A2A 1.0 breaking) [S41, S46] | Stay on the official SDKs; serve old MCP revisions [S43]; integration tests with an outside client per revision. |
| OTel GenAI not stable [S52] | Pin semconv version; add our own `di.run_id`, `di.preparer`, `di.action` attributes. |
| Outside-agent auth and data exposure | OAuth + tenant consent per call as today; **security/privacy design to be reviewed by Kinective's Legal team**. |

**Architecture (text)**

```
Outside agents: Claude, ChatGPT/Codex, Gemini, Copilot, CLIs, enterprise agents
   | MCP 2026-07-28 (Streamable HTTP)   | A2A v1.0 (JSON-RPC)        | OpenAPI / `circ` CLI
   v                                    v                            v
+--------------------------------- di-api (FastAPI) -----------------------------------+
| /mcp (di/mcp)        /a2a + /.well-known/agent-card.json        /api/actions/{id}     |
|   identity: account JWT or OAuth token  +  agent id (preparer)  +  tenant             |
|                                   |                                                   |
|  Agent runtime (ours) di/services/agents/runtime.py: agent_run, agent_run_step        |
|    - deterministic playbooks (case_autopilot)                                         |
|    - LLM playbooks -> AgentLoop port -> Pydantic AI Agent                             |
|         tools = catalog.py (agent_allowed ∩ agent allow-list) -> pipeline.invoke      |
|         approval-needing tools -> deferred -> agent_proposal -> run "waiting"         |
|                                   v                                                   |
|  pipeline.invoke: validate, permission, scope, agent gate, forbidden, guard, limits,  |
|                   idempotency, HOLD, handler, journal, events                         |
+---------------------------------------------------------------------------------------+
   Postgres: domain tables, action_journal, agent_run*, agent_proposal, job (NOTIFY)
   di-worker: job `agent.step` = one model turn or one playbook call, then persist
   Models: Groq | Anthropic | OpenAI | Google | Bedrock (Pydantic AI providers)
   OTel: gen_ai.* spans + di.run_id -> collector
```

**Phased adoption mapped to our files**

| Phase | Scope | Files |
|---|---|---|
| 0. Spike (2 weeks) | `AgentLoop` port + Pydantic AI adapter; one LLM playbook `workflow_author` | new `services/agents/loop.py`, `services/agents/playbooks/workflow_author.py`; `runtime.py` dispatches deterministic vs LLM playbooks; `catalog.py` gains `toolset(agent)` |
| 1. Config authoring (weeks 3–8) | Agents draft workflows, mappings, connectors, flows and rules; a person publishes | Workflow: `workflow.create/draft/save/validate/testRun` (allowed). Modeler: `flow.fork/saveDraft/simulate/submit` (allowed; maker != checker unchanged). Connection Fabric: add draft-only actions (e.g. `source.draft`, `mapping.propose`) that write a draft without credentials, and narrow `FORBIDDEN_ACTIONS` from `source.` to the live ones (`source.update`, `source.reconnect`, `source.delete` ...). Org setup: agent emits a **change set** (list of calls) held as one proposal; a person applies it from the UI with their own permission. |
| 2. Outside agents (weeks 6–10) | Catalogue toolset in MCP, OAuth/CIMD, OpenAPI per action, `circ` CLI, A2A card + 2–3 skills | `di/mcp/server.py`, `di/mcp/tools.py`, new `di/routes/a2a.py`, `scripts/` or a small CLI package |
| 3. End-to-end process agent (quarter 2) | Planner + sub-agents (research source docs, draft mapping, simulate, critic) on the same port; autonomy levels per org; A2A client to customers' agents | `services/agents/playbooks/*`, `connectors/mcp_client.py` reused; evals on `fixtures/golden/po/` scenarios |
| 4. Only if needed | Temporal/DBOS durability; AG-UI panel | behind `AgentLoop` |

**First 2-week spike: acceptance tests** (run through `scripts/dev/api-test.sh`; a test model, no live key in CI)

1. A `workflow_author` run drafts and validates a workflow; every write is an `action_journal` row with
   `preparer = <agent>` and `run_id`; an import-linter contract forbids `services/agents/loop*` from importing
   `di.models` or repositories (no direct DB writes).
2. The toolset never contains a forbidden action; a crafted call to `workflow.publish` is refused by the pipeline and
   nothing is journaled.
3. Agent with autonomy `propose`: `workflow.save` is held; the run is `waiting` with the proposal id; restart the worker;
   `proposal.accept` by a person resumes the run from `agent_run.state` and finishes; exactly one journal row
   (idempotency key `run_id:tool_call_id`).
4. `proposal.reject` stops the run with the reason; the kill switch and the run limit stop a running run on the next step.
5. Provider neutrality: the same playbook passes with the test model and, outside CI, with Groq and one other provider;
   with no key the run fails cleanly (no fallback writes).
6. OTel: spans carry `gen_ai.*` attributes and `di.run_id`; no input key containing `secret`, `password` or `token`
   appears in any span.
7. MCP: an outside client on the MCP Python SDK (revision 2026-07-28) and one on an older revision list the
   catalogue toolset filtered by `X-Agent` and call `workflow_validate`.
8. Eval: 10 scripted authoring scenarios scored on tool trajectory and on `workflow.validate` passing; threshold 8/10.
9. Parity: full suite green; the 128 demo cases and RT-1048 unchanged.

## 7. Legal note

Statements on licences (Apache-2.0, MIT, Elastic-2.0, commercial tiers), authorization (OAuth, CIMD, enterprise-managed
authorization), data exposure to outside agents, security and privacy are research inputs only and **must be reviewed by
Kinective's Legal team before they are relied on or acted on**.

## Sources (accessed 24 Nov 2026 unless stated)

- S1 Agno releases, v3.1.10–v3.2.1 (17 Nov 2026): https://github.com/agno-agi/agno/releases
- S2 `agno` on PyPI, 3.2.1 (17 Nov 2026), Apache-2.0, AgentOS, extras `a2a`, `agui`: https://pypi.org/project/agno/
- S3 Agno community roundup, Feb 2026 (v2.5 Team Modes, licence to Apache 2.0; via search summary): https://www.agno.com/blog/community-roundup-february-2026
- S4 Agno HITL docs: https://docs.agno.com/hitl/overview
- S5 Agno v3 changelog and background execution (durable queue opt-in): https://docs.agno.com/other/v3-changelog ; https://docs.agno.com/agent-os/background-execution/overview
- S6 Agno tracing (OpenTelemetry via OpenInference): https://docs.agno.com/tracing/overview
- S7 Agno AgentOS A2A interface and MCP server: https://docs.agno.com/agent-os/interfaces/a2a/introduction ; https://docs.agno.com/features/mcp-server
- S8 Agno repository (43.3k stars, Apache-2.0): https://github.com/agno-agi/agno
- S9 Conductor OSS releases, v3.34.0 (18 Nov 2026), v3.33.1 (12 Nov 2026): https://github.com/conductor-oss/conductor/releases
- S10 Conductor OSS repository (32.5k stars, Apache-2.0, Java 25, backends): https://github.com/conductor-oss/conductor
- S11 `conductor-python` on PyPI, 2.0.0 (3 Aug 2026), agent extras: https://pypi.org/project/conductor-python/
- S12 Orkes, "Conductor now runs agents alongside your workflows" (updated 18 Nov 2026): https://orkes.io/blog/conductor-now-runs-agents-alongside-your-workflows
- S13 Orkes, AGENT task (updated 7 Sep 2026): https://orkes.io/blog/introducing-agent-task
- S14 Orkes, Conductor MCP server (9 Jun 2025): https://orkes.io/blog/conductor-mcp-server-announcement
- S15 Conductor OSS FAQ (HUMAN task, LLM and MCP tasks): https://docs.conductor-oss.org/devguide/faq
- S16 Orkes, Conductor OSS vs Orkes: https://orkes.io/platform/conductor-oss-vs-orkes
- S17 Orkes pricing (custom enterprise; via search summary): https://www.orkes.io/pricing
- S18 Conductor OSS PostgreSQL backend: https://docs.conductor-oss.org/documentation/advanced/postgresql.html
- S19 `langgraph` on PyPI, 1.2.24 (20 Nov 2026), MIT: https://pypi.org/project/langgraph/
- S20 LangGraph repository (45.3k stars, MIT): https://github.com/langchain-ai/langgraph
- S21 LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- S22 `langgraph-checkpoint-postgres` 3.2.1 (14 Nov 2026), MIT: https://pypi.org/project/langgraph-checkpoint-postgres/
- S23 `langchain-mcp-adapters` 0.3.2 (6 Aug 2026), MIT: https://pypi.org/project/langchain-mcp-adapters/
- S24 LangSmith Agent Server A2A endpoint (A2A v1.0, JSON-RPC): https://docs.langchain.com/langsmith/server-a2a
- S25 Agent Server changelog (0.18.x, Nov 2026; MCP 2026-07-28 from 0.18.0rc1, 30 Oct 2026): https://docs.langchain.com/langsmith/agent-server-changelog
- S26 `langgraph-api` on PyPI, 0.18.4 (21 Nov 2026), Elastic-2.0: https://pypi.org/project/langgraph-api/
- S27 LangGraph issue #9655, open durable-execution bugs (Nov 2026): https://github.com/langchain-ai/langgraph/issues/9655
- S28 Logfire, LangGraph OTel-only export: https://pydantic.dev/docs/logfire/integrations/llms/langgraph/ ; S28b OpenInference vs GenAI conventions: https://agent-observability-docs.splunk.com/how-to-guides/third-party-integrations/otel
- S29 `deepagents` 0.7.41 (20 Nov 2026), MIT: https://pypi.org/project/deepagents/
- S30 `pydantic-ai` on PyPI, 2.71.0 (19 Nov 2026), MIT: https://pypi.org/project/pydantic-ai/
- S31 Pydantic AI repository README (21.4k stars; providers, durable engines, HITL, evals, OTel, AG-UI): https://github.com/pydantic/pydantic-ai
- S32 Pydantic AI deferred tools: https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/
- S33 Pydantic AI OpenTelemetry (GenAI semconv 1.37.0, any OTel backend): https://pydantic.dev/docs/ai/integrations/logfire/
- S34 Pydantic AI A2A (`to_a2a` deprecated, use `fasta2a`): https://pydantic.dev/docs/ai/integrations/a2a/index.md
- S35 `claude-agent-sdk` 0.2.187 (20 Nov 2026), MIT, bundles CLI: https://pypi.org/project/claude-agent-sdk/
- S36 OpenAI Agents SDK v0.25.0 (17 Nov 2026): https://github.com/openai/openai-agents-python/releases/tag/v0.25.0
- S37 Google ADK releases v2.15.0 (19 Nov 2026); ADK 2.0 GA (19 May 2026): https://github.com/google/adk-python/releases ; https://adk.dev/2.0/
- S38 `agent-framework` 1.26.0 (12 Nov 2026), MIT: https://pypi.org/project/agent-framework/ ; S38b 1.0 GA (3 Apr 2026): https://techcommunity.microsoft.com/blog/azuredevcommunityblog/the-future-of-agentic-ai-inside-microsoft-agent-framework-1-0/4510698
- S39 `crewai` 1.15.44 (19 Nov 2026), MIT: https://pypi.org/project/crewai/
- S40 Temporal OpenAI Agents SDK integration GA for Python (23 Mar 2026); AI integrations GA: https://temporal.io/blog/announcing-openai-agents-sdk-integration ; https://temporal.io/blog/ai-framework-integrations
- S41 MCP 2026-07-28 specification post (28 Jul 2026): https://blog.modelcontextprotocol.io/posts/2026-07-28/
- S42 `mcp` on PyPI, 2.3.0 (2 Oct 2026): https://pypi.org/project/mcp/
- S43 MCP Python SDK v2 "What's new" (serves 2026-07-28 and earlier; Tasks gap per secondary report): https://py.sdk.modelcontextprotocol.io/whats-new/
- S44 MCP server cards, SEP-2127 status (Jul–Sep 2026, secondary): https://bex.co/blog/2026/07/08/mcp-server-cards-well-known-discovery ; https://contextiq.trango-compute.com/blog/mcp-server-discovery-well-known-server-card-sep-2127
- S45 Okta, Cross App Access / Enterprise-Managed Authorization (Jun 2026): https://www.okta.com/newsroom/press-releases/okta-announces-cross-app-access-partners/
- S46 A2A releases v1.0.0 (12 Mar 2026), v1.0.1 (28 May 2026), v0.3.0 (30 Jul 2025): https://github.com/a2aproject/A2A/releases
- S47 A2A site (v1.0, SDK languages, AAIF): https://a2a-protocol.org/latest/
- S48 AAIF, "A2A joins AAIF" (17 Aug 2026): https://aaif.io/blog/a2a-joins-aaif ; Axios (17 Aug 2026): https://axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards
- S49 IBM ACP merged into A2A (Aug 2025; secondary): https://www.ml4devs.com/what-is/acp-agent-communication-protocol/
- S50 Agent Client Protocol: https://agentclientprotocol.com/ ; JetBrains + Zed (Oct 2025): https://blog.jetbrains.com/ai/2025/10/jetbrains-zed-open-interoperability-for-ai-coding-agents-in-your-ide/ ; ACP registry: https://zed.dev/blog/acp-registry
- S51 AG-UI 1.0 (30 Sep 2026; secondary): https://byteiota.com/ag-ui-1-stable-spec/ ; https://www.copilotkit.ai/blog/introducing-ag-ui-the-protocol-where-agents-meet-users
- S52 OTel GenAI conventions status (Jul–Aug 2026; secondary): https://john-hodge.com/blog/opentelemetry-genai-semantic-conventions/ ; https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke
- S53 Copilot Studio what's new (MCP/A2A channels, Oct 2026 preview) and A2A connected agents: https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new ; https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-agent-to-agent
