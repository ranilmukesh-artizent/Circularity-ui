"""Plan 8 MVP-11.7: the tiny MCP server at /mcp-demo (JSON-RPC over Streamable HTTP, stateless, JSON answers)."""

from fastapi.testclient import TestClient

from sim.main import app
from sim.routes.mcp_demo import PATH

client = TestClient(app)


def rpc(method: str, params: dict | None = None, rid: int | None = 1) -> dict:
    msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    if rid is not None:
        msg["id"] = rid
    r = client.post(PATH, json=msg, headers={"Accept": "application/json, text/event-stream"})
    return {"status": r.status_code, "body": r.json() if r.content else None}


def test_initialize_and_list_the_one_read_tool():
    init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert init["status"] == 200 and init["body"]["result"]["protocolVersion"] == "2025-06-18"
    assert rpc("notifications/initialized", rid=None) == {"status": 202, "body": None}
    tools = rpc("tools/list")["body"]["result"]["tools"]
    assert [t["name"] for t in tools] == ["list_returns"] and tools[0]["annotations"]["readOnlyHint"] is True


def test_list_returns_is_synthetic_and_stable():
    out = rpc("tools/call", {"name": "list_returns", "arguments": {"limit": 2}})["body"]["result"]
    items = out["structuredContent"]["items"]
    assert [x["return_id"] for x in items] == ["RMA-7001", "RMA-7002"] and out["isError"] is False
    assert len(rpc("tools/call", {"name": "list_returns", "arguments": {}})["body"]["result"]["structuredContent"]["items"]) == 12
    since = rpc("tools/call", {"name": "list_returns", "arguments": {"since": "2026-10-05T00:00:00Z"}})
    assert all(x["received_at"] > "2026-10-05" for x in since["body"]["result"]["structuredContent"]["items"])


def test_unknown_tool_and_method_are_json_rpc_errors():
    assert rpc("tools/call", {"name": "drop_tables", "arguments": {}})["body"]["error"]["code"] == -32602
    assert rpc("resources/list")["body"]["error"]["code"] == -32601
    assert client.get(PATH).status_code == 405
