"""Plan 5, Task 4: MCP spans (di/mcp/server.py).

The MCP SDK (mcp 2.x) wraps every inbound request in a SERVER span `tools/call {tool}` of its own tracer
(mcp.server._otel.OpenTelemetryMiddleware, on by default; it takes the parent from `params._meta` and sets
`error.type=tool_error` on an error result). The tests prove that this reaches our exporter for di's own handler, and that
di adds what the SDK cannot know: the call's outcome on the span and the histogram `mcp.server.operation.duration`.

They run in process (a small app with di's MCP lifespan and the BearerGate, `TestClient` on host `localhost`), so unlike
test_mcp_server.py they need no running api. Tools run through di.mcp.policy as always; no secret reaches a span.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from di.mcp import server as mcp_server
from tests import starting
from tests.helpers import h

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


@pytest.fixture(scope="module")
def mcp():
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from di import telemetry

    exporter, reader = InMemorySpanExporter(), InMemoryMetricReader()
    telemetry.setup_telemetry("di-api", exporter=exporter, metric_reader=reader)
    app = FastAPI(lifespan=mcp_server.lifespan)
    mcp_server.mount(app)
    with TestClient(app, base_url="http://localhost:8000") as c:
        yield c, exporter, reader


def rpc(c, user: str, agent: str | None, tool: str, args: dict, *, rid: int = 7, meta: dict | None = None) -> dict:
    headers = {**h(user), "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if agent:
        headers["X-Agent"] = agent
    params: dict = {"name": tool, "arguments": args}
    if meta:
        params["_meta"] = meta
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": params}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _call_spans(exporter, tool: str):
    return [s for s in exporter.get_finished_spans() if s.name == f"tools/call {tool}"]


def _duration_points(reader, **attrs):
    data = reader.get_metrics_data()
    out = []
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == "mcp.server.operation.duration":
                    out += [p for p in m.data.data_points if all(p.attributes.get(k) == v for k, v in attrs.items())]
    return out


def test_a_tool_call_is_a_server_span_with_the_mcp_attributes(mcp):
    c, exporter, _ = mcp
    exporter.clear()
    res = rpc(c, "planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1048"}, rid=41)
    assert res["isError"] is False
    spans = _call_spans(exporter, "get_case_evidence")
    assert len(spans) == 1
    s = spans[0]
    a = dict(s.attributes)
    assert s.kind.name == "SERVER"
    assert a["mcp.method.name"] == "tools/call" and a["gen_ai.tool.name"] == "get_case_evidence"
    assert a["jsonrpc.request.id"] == "41" and a["gen_ai.operation.name"] == "execute_tool"
    assert "error.type" not in a
    assert a["di.mcp.outcome"] == "ok"


def test_a_held_or_refused_call_is_a_tool_error(mcp):
    c, exporter, _ = mcp
    exporter.clear()
    held = rpc(c, "planner-a", "coordinator", "send_instruction", {"case_id": "RT-1048"})
    assert held["isError"] is True
    denied = rpc(c, "planner-a", "assembler", "request_missing_evidence", {"case_id": "RT-1051", "kind": "inspection"})
    assert denied["isError"] is True
    h_span = _call_spans(exporter, "send_instruction")[0]
    d_span = _call_spans(exporter, "request_missing_evidence")[0]
    assert h_span.attributes["error.type"] == "tool_error" and h_span.attributes["di.mcp.outcome"] == "held for approval"
    assert d_span.attributes["error.type"] == "tool_error" and d_span.attributes["di.mcp.outcome"].startswith("denied")


def test_traceparent_in_params_meta_becomes_the_parent(mcp):
    c, exporter, _ = mcp
    exporter.clear()
    rpc(c, "planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1048"}, meta={"traceparent": TRACEPARENT})
    s = _call_spans(exporter, "get_case_evidence")[0]
    assert format(s.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c"
    assert format(s.parent.span_id, "016x") == "b7ad6b7169203331"


def test_the_operation_duration_histogram_records_each_call(mcp):
    c, _, reader = mcp
    before = sum(p.count for p in _duration_points(reader, **{"gen_ai.tool.name": "get_case_evidence"}))
    rpc(c, "planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1048"})
    pts = _duration_points(reader, **{"gen_ai.tool.name": "get_case_evidence"})
    assert sum(p.count for p in pts) == before + 1
    assert all(p.attributes["mcp.method.name"] == "tools/call" for p in pts)


def test_no_secret_or_argument_on_an_mcp_span(mcp):
    c, exporter, _ = mcp
    exporter.clear()
    rpc(c, "planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1048"})
    token = h("planner-a")["Authorization"].split(" ", 1)[1]
    for s in exporter.get_finished_spans():
        for k, v in dict(s.attributes).items():
            assert token not in str(v), (s.name, k)
            assert "RT-1048" not in str(v), (s.name, k)
            assert k != "gen_ai.tool.call.arguments"
