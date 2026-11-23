"""A tiny MCP server for the MCP client source kind (plan 8, MVP-11.7). Not part of any vendor API; synthetic data.

POST /mcp-demo    Model Context Protocol over Streamable HTTP, stateless with JSON responses (as di's own server at
                  /mcp runs it): JSON-RPC `initialize`, `notifications/initialized`, `ping`, `tools/list` and
                  `tools/call`. One read tool:
    list_returns {since?: str, limit?: int}   synthetic returned assets: {items: [{return_id, asset_id, serial,
                                              model, reason, received_at, condition}]}; the answer is structured
                                              content, and its text content is the same JSON
GET  /mcp-demo    405: no server-to-client stream (stateless server)

The protocol is answered by hand (a few JSON-RPC methods) instead of through the `mcp` SDK, so source-sim needs no new
dependency; di's MCP client (the SDK's streamable HTTP client) talks to it as to any MCP server.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

router = APIRouter(tags=["MCP demo server"])
PATH = "/mcp-demo"
PROTOCOL = "2025-06-18"
REASONS = ("end of lease", "warranty return", "upgrade", "damaged in transit", "surplus")
CONDITIONS = ("A", "B", "C")
TOOL = {
    "name": "list_returns",
    "description": "Returned assets waiting for a disposition decision (synthetic).",
    "inputSchema": {
        "type": "object",
        "properties": {"since": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}},
        "required": [],
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
}


def returns() -> list[dict[str, Any]]:
    """Twelve synthetic returns, the same on every call."""
    start = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    return [
        {
            "return_id": f"RMA-{7001 + k}",
            "asset_id": f"MCP-AST-{101 + k}",
            "serial": f"SN-MCP-{5000 + 37 * k}",
            "model": ("Motor M-40", "Pump P-12", "Drive D-7")[k % 3],
            "reason": REASONS[k % len(REASONS)],
            "received_at": (start + timedelta(hours=9 * k)).isoformat().replace("+00:00", "Z"),
            "condition": CONDITIONS[k % len(CONDITIONS)],
        }
        for k in range(12)
    ]


def _list_returns(args: dict[str, Any]) -> dict[str, Any]:
    items = returns()
    since = args.get("since")
    if isinstance(since, str) and since:
        items = [r for r in items if r["received_at"] > since]
    limit = args.get("limit")
    if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        items = items[:limit]
    return {"items": items}


def _result(rid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _answer(msg: dict[str, Any]) -> dict[str, Any] | None:
    """The answer to one JSON-RPC message; None for a notification."""
    method, rid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if rid is None:  # a notification (notifications/initialized ...): nothing to answer
        return None
    if method == "initialize":
        return _result(rid, {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "circularity-mcp-demo", "version": "0.1.0"},
        })  # fmt: skip
    if method == "ping":
        return _result(rid, {})
    if method == "tools/list":
        return _result(rid, {"tools": [TOOL]})
    if method == "tools/call":
        if params.get("name") != TOOL["name"]:
            return _error(rid, -32602, f"Unknown tool {params.get('name')}")
        out = _list_returns(params.get("arguments") or {})
        return _result(rid, {"content": [{"type": "text", "text": json.dumps(out)}], "structuredContent": out, "isError": False})
    return _error(rid, -32601, f"Method not found: {method}")


@router.post(PATH)
async def post(request: Request) -> Response:
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)
    msgs = body if isinstance(body, list) else [body]
    answers = [a for m in msgs if isinstance(m, dict) and (a := _answer(m)) is not None]
    if not answers:
        return Response(status_code=202)
    return JSONResponse(answers if isinstance(body, list) else answers[0])


@router.get(PATH)
def get() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})
