# Plan 5: OpenTelemetry (traces, metrics, logs, GenAI) Implementation Plan

> **For agentic workers:** run through `scripts/dev/loop.ps1` (see `loop.md`), one task per iteration.

Gate: tests/test_otel.py tests/test_otel_genai.py tests/test_mcp_server.py

**Goal:** every request, job, database call and outbound HTTP call is traced; logs carry the trace id; Ask's model calls
and tool calls, and MCP tool calls, emit OpenTelemetry GenAI/MCP spans; a local Grafana LGTM stack shows it all.

**Architecture:** `backend/di/telemetry.py` sets up the SDK once (api, worker) from env (`OTEL_*`); auto-instrumentation
for FastAPI, SQLAlchemy, psycopg, httpx and logging; hand-written GenAI spans in `di/services/ask/` and MCP spans in `di/mcp/`
(the GenAI conventions are Development status and their env names are changing, so we do not depend on a
third-party LLM instrumentation). Off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set; tests use the in-memory exporter.

**Tech Stack:** `opentelemetry-api==1.45.2`, `opentelemetry-sdk==1.45.2`, `opentelemetry-exporter-otlp-proto-http==1.45.2`,
`opentelemetry-instrumentation-fastapi==0.66b2`, `-sqlalchemy==0.66b2`, `-psycopg==0.66b2`, `-httpx==0.66b2`,
`-logging==0.66b2` (pin all together); dev backend `grafana/otel-lgtm:0.39.0` (OTLP 4317/4318, Grafana 3000).

**Spec:** OpenTelemetry GenAI semantic conventions (github.com/open-telemetry/semantic-conventions-genai, Development):
inference span `chat {gen_ai.request.model}` (CLIENT) with `gen_ai.operation.name=chat`, `gen_ai.provider.name=groq`,
`gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens`,
`gen_ai.usage.output_tokens`, `gen_ai.conversation.id`, `error.type`; tool span `execute_tool {gen_ai.tool.name}`
(INTERNAL) with `gen_ai.operation.name=execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id`; metric
`gen_ai.client.inference.duration`. MCP: span `tools/call {tool}` (SERVER) with `mcp.method.name`, `gen_ai.tool.name`,
`jsonrpc.request.id`, `error.type=tool_error` when the result is an error; metric `mcp.server.operation.duration`.

## Global Constraints

- Content capture is off: no prompts, answers, tool arguments or results in spans or logs unless
  `DI_OTEL_CAPTURE_CONTENT=true` (then only on spans, truncated to 4 KB). The data is synthetic, but the rule holds.
- No secret in any attribute: never the Groq key, bearer tokens or webhook signatures (test asserts it).
- The OTel Logs SDK is Development in Python: use the logging instrumentation to inject `trace_id`/`span_id` into
  stdlib log records and export logs through OTLP only behind `DI_OTEL_LOGS=true`.
- Service names: `di-api`, `di-worker`, `source-sim`.

## Review Focus

1. Telemetry backend down → the app works and does not slow down (exporter batches, drops on failure).
2. An SSE stream left open for minutes → one span that ends when the client disconnects, not a leaked span.
3. Trace context from the web app's `fetch` → api span is the child (W3C `traceparent` accepted; CORS allows it).
4. A worker job started by a request → linked to the request's trace (store `traceparent` in the job payload).
5. A Groq 429 fallback → the inference span has `error.type` and the fallback answer is a sibling span, not lost.

---

### Task 1: setup, off by default
**Files:** Create `backend/di/telemetry.py`; Modify `di/main.py`, `di/worker.py`, `requirements.in` (+ recompiled lock), `.env.example`
(`OTEL_EXPORTER_OTLP_ENDPOINT=` empty). Test: `tests/test_otel.py`.
**Interfaces:** Produces `setup_telemetry(service_name: str, app: FastAPI | None = None) -> None` and
`tracer = trace.get_tracer("di")`; tests use `InMemorySpanExporter` via `setup_telemetry(..., exporter=...)`.
- [ ] Tests: with no endpoint set, nothing is exported and no error; with the in-memory exporter, `GET /api/screens/nav`
  yields a server span with child SQL spans; log records carry `otelTraceID`. Fail → implement → pass. Commit.

### Task 2: worker and job traces
- [ ] `enqueue` stores the current `traceparent` in `job.payload["_trace"]`; the worker starts the job's span as a link
  to it. Test: request → job → span link present. Commit.

### Task 3: GenAI spans for Ask
**Files:** Modify `backend/di/services/ask/groq_model.py`, `di/services/ask/service.py`, `di/services/ask/tools.py`. Test: `tests/test_otel_genai.py`
(uses the fake model from the Ask tests).
- [ ] Tests: one `chat openai/gpt-oss-120b` span with the attributes listed in Spec (token counts from Groq's `usage`);
  one `execute_tool get_case` span per tool call as a child; no `gen_ai.input.messages` by default; a 429 sets
  `error.type` and the fallback runs under its own span; the histogram `gen_ai.client.inference.duration` records one value.
- [ ] Fail → implement → pass. Commit.

### Task 4: MCP spans
**Files:** Modify `backend/di/mcp/server.py`. Test: extend `tests/test_mcp_server.py`.
- [ ] Tests: a `tools/call get_case_evidence` SERVER span with `mcp.method.name`, `gen_ai.tool.name`, `jsonrpc.request.id`;
  a held or refused call sets `error.type=tool_error`; `traceparent` in `params._meta` becomes the parent. Commit.

### Task 5: local backend and docs
**Files:** Modify `docker-compose.yml` (service `otel` with image `grafana/otel-lgtm:0.39.0` under profile `otel`, ports
3000/4318; api and worker get `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel:4318` only when the profile is used), `AGENTS.md`,
`docs/agents/testing.md`.
- [ ] `docker compose --profile otel up -d`; run `smoke-ask.mjs` once; confirm in Grafana (Explore → Tempo) a trace with
  the HTTP span, SQL spans, the `chat` span and `execute_tool` spans; note the steps in `testing.md`. Phase gate. Commit.
