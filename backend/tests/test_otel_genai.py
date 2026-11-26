"""Plan 5, Task 3: GenAI spans for Ask (di/services/ask: groq_model, service, tools).

The Groq provider runs on a mocked transport (as in test_ask.py); spans go to the in-memory exporter, metrics to the
in-memory reader. Names follow the OpenTelemetry GenAI conventions: `chat {model}` (CLIENT), `execute_tool {tool}`
(INTERNAL), the histogram `gen_ai.client.inference.duration`. No prompt, answer or tool argument is on a span unless
DI_OTEL_CAPTURE_CONTENT is on; no key is ever on one.
"""

import json

import httpx
import pytest

from di.core.config import get_settings
from di.main import app
from di.services.ask.model import get_model
from tests import starting
from tests.test_ask import _chunk, _groq, ask

QUESTION = "Why is RT-1048 recommended for redeploy?"
MODEL = "openai/gpt-oss-120b"


def setup_module():
    starting.reset()


def teardown_module():
    app.dependency_overrides.clear()
    starting.reset()


@pytest.fixture(scope="module")
def telemetry_out():
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from di import telemetry

    exporter, reader = InMemorySpanExporter(), InMemoryMetricReader()
    telemetry.setup_telemetry("di-api", exporter=exporter, metric_reader=reader)
    return exporter, reader


@pytest.fixture(autouse=True)
def _clean(telemetry_out):
    telemetry_out[0].clear()
    yield
    app.dependency_overrides.pop(get_model, None)


def _usage_chunk(finish: str | None, prompt: int, completion: int, model: str = MODEL) -> str:
    usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
    c = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": model,
         "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "x_groq": {"id": "r1", "usage": usage}}  # fmt: skip
    return "data: " + json.dumps(c) + "\n\n"


def _answer_handler(request: httpx.Request) -> httpx.Response:
    sse = _chunk({"content": "RT-1048 goes to redeploy."}) + _usage_chunk("stop", 120, 15) + "data: [DONE]\n\n"
    return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})


def _tool_then_answer():
    n = []

    def handler(request: httpx.Request) -> httpx.Response:
        n.append(1)
        if len(n) == 1:
            sse = _chunk({"role": "assistant", "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                          "function": {"name": "get_case", "arguments": '{"case_id":"RT-1048"}'}}]}, "tool_calls")  # fmt: skip
            sse += _usage_chunk("tool_calls", 100, 10)
        else:
            sse = _chunk({"content": "RT-1048 goes to redeploy."}) + _usage_chunk("stop", 300, 20)
        return httpx.Response(200, text=sse + "data: [DONE]\n\n", headers={"content-type": "text/event-stream"})

    return handler


def _ours(exporter):
    """Ask's own spans (the SQL and HTTP spans of the libraries' instrumentation carry their own, separate rules)."""
    return [
        s for s in exporter.get_finished_spans() if s.name.startswith(("chat ", "execute_tool ", "invoke_agent ", "ask_fallback"))
    ]


def _spans(exporter, prefix: str):
    return [s for s in exporter.get_finished_spans() if s.name.startswith(prefix)]


def _count(reader, **attrs) -> int:
    data = reader.get_metrics_data()
    total = 0
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == "gen_ai.client.inference.duration":
                    for p in m.data.data_points:
                        if all(p.attributes.get(k) == v for k, v in attrs.items()):
                            total += p.count
    return total


def test_one_chat_span_with_the_genai_attributes(telemetry_out, monkeypatch):
    exporter, _ = telemetry_out
    _groq(monkeypatch, _answer_handler)
    _, first = ask("planner-a", QUESTION)
    chat = _spans(exporter, "chat ")
    assert [s.name for s in chat] == [f"chat {MODEL}"]
    s = chat[0]
    assert s.kind.name == "CLIENT"
    a = dict(s.attributes)
    assert a["gen_ai.operation.name"] == "chat" and a["gen_ai.provider.name"] == "groq"
    assert a["gen_ai.request.model"] == MODEL and a["gen_ai.response.model"] == MODEL
    assert tuple(a["gen_ai.response.finish_reasons"]) == ("stop",)
    assert a["gen_ai.usage.input_tokens"] == 120 and a["gen_ai.usage.output_tokens"] == 15
    assert "error.type" not in a
    # a follow-up in the same conversation names it on the span
    exporter.clear()
    ask("planner-a", "And after that?", conversation_id=first["conversation_id"])
    assert dict(_spans(exporter, "chat ")[0].attributes)["gen_ai.conversation.id"] == first["conversation_id"]


def test_the_inference_duration_histogram_records_one_value(telemetry_out, monkeypatch):
    _, reader = telemetry_out
    before = _count(reader, **{"gen_ai.request.model": MODEL})
    _groq(monkeypatch, _answer_handler)
    ask("planner-a", QUESTION)
    assert _count(reader, **{"gen_ai.request.model": MODEL}) == before + 1


def test_a_tool_call_is_an_execute_tool_span_under_the_ask_span(telemetry_out, monkeypatch):
    exporter, _ = telemetry_out
    _groq(monkeypatch, _tool_then_answer())
    ask("planner-a", QUESTION)
    root = _spans(exporter, "invoke_agent ")
    assert len(root) == 1
    tool = _spans(exporter, "execute_tool ")
    assert [s.name for s in tool] == ["execute_tool get_case"]
    t = dict(tool[0].attributes)
    assert t["gen_ai.operation.name"] == "execute_tool" and t["gen_ai.tool.name"] == "get_case"
    assert t["gen_ai.tool.call.id"] == "call_1"
    assert tool[0].parent.span_id == root[0].context.span_id
    chat = _spans(exporter, "chat ")
    assert len(chat) == 2 and all(c.parent.span_id == root[0].context.span_id for c in chat)
    assert tool[0].context.trace_id == root[0].context.trace_id


def test_no_prompt_answer_or_argument_on_a_span_by_default(telemetry_out, monkeypatch):
    exporter, _ = telemetry_out
    _groq(monkeypatch, _tool_then_answer())
    ask("planner-a", QUESTION)
    spans = _ours(exporter)
    assert spans
    for s in spans:
        for k, v in dict(s.attributes).items():
            assert not k.startswith(("gen_ai.input", "gen_ai.output", "gen_ai.system_instructions", "gen_ai.tool.call.arguments"))
            assert "RT-1048" not in str(v) and "test-key" not in str(v), (s.name, k)


def test_content_is_captured_only_when_switched_on_and_is_cut_to_4kb(telemetry_out, monkeypatch):
    exporter, _ = telemetry_out
    monkeypatch.setattr(get_settings(), "otel_capture_content", True)
    _groq(monkeypatch, _tool_then_answer())
    ask("planner-a", QUESTION)
    chat = _spans(exporter, "chat ")
    assert QUESTION in str(chat[0].attributes["gen_ai.input.messages"])
    assert "redeploy" in str(chat[1].attributes["gen_ai.output.messages"])
    tool = _spans(exporter, "execute_tool ")[0]
    assert "RT-1048" in str(tool.attributes["gen_ai.tool.call.arguments"])
    for s in _ours(exporter):
        for v in dict(s.attributes).values():
            assert len(str(v)) <= 4096 + 64
            assert "test-key" not in str(v)


def test_a_429_marks_the_chat_span_and_the_fallback_runs_under_its_own_span(telemetry_out, monkeypatch):
    exporter, reader = telemetry_out
    before = _count(reader, **{"error.type": "RateLimitError"})
    rate = {"error": {"message": "Rate limit reached", "code": "rate_limit_exceeded"}}
    _groq(monkeypatch, lambda r: httpx.Response(429, json=rate))
    _, final = ask("approver", "Compare the routes for RT-1049")
    assert final["provider"] == "fallback"
    chat = _spans(exporter, "chat ")
    assert len(chat) == 1
    assert chat[0].attributes["error.type"] == "RateLimitError"
    assert chat[0].status.status_code.name == "ERROR"
    fallback = _spans(exporter, "ask_fallback")
    assert len(fallback) == 1
    assert fallback[0].attributes["di.ask.fallback_reason"] == "rate_limited"
    assert fallback[0].parent.span_id == chat[0].parent.span_id  # siblings under the Ask span
    assert fallback[0].start_time >= chat[0].end_time
    assert _count(reader, **{"error.type": "RateLimitError"}) == before + 1
