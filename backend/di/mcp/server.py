"""The MCP server on the official Python SDK (`mcp` 2.x) and its place in the FastAPI app.

- **Server:** the SDK's low-level `mcp.server.Server` with two handlers, `tools/list` and `tools/call`. (mcp 2 renamed
  FastMCP to `MCPServer`, which derives each tool's schema from a Python signature; the low-level server lets the
  schemas come from the demo's TOOLS table as they are.)
- **Transport:** Streamable HTTP through the SDK's `StreamableHTTPSessionManager`, stateless with JSON responses: no
  MCP session is kept between requests, so every request carries its own identity and is checked on its own. The
  SDK's DNS-rebinding protection stays on, for the hosts the api is reached by (localhost, and `api` from the web
  container's proxy).
- **Mount:** `mount(app)` (di.main) adds the route `/mcp` (exactly, no redirect) to the FastAPI app and runs the session
  manager inside the app's lifespan, as the SDK's session manager documents (`async with session_manager.run()`).
- **OAuth (P9-2.14):** the gate also answers 401 with the resource metadata URL, refuses a token for another audience
  and a call outside the token's scope (403 insufficient_scope): di.mcp.oauth.
- **Identity:** `BearerGate` refuses any request without a valid account token (`Authorization: Bearer <JWT>`, the one
  /api/auth/login issues) with 401 before the SDK sees it. Each tool call then reads the token, `X-Agent` and
  `X-Tenant` from its HTTP request (the SDK hands the request to the handler) and goes to di.mcp.policy.call_tool,
  which resolves the account afresh (as every /api request does), checks, runs and logs the call. The database work
  runs in a worker thread, off the event loop.
- **Telemetry (plan 5):** the SDK wraps every request in its own SERVER span (`tools/call {tool}`); `_observe` adds the
  call's outcome and the histogram `mcp.server.operation.duration`.
"""

import contextlib
import json
import time
from collections.abc import AsyncIterator, MutableMapping
from typing import Any

import anyio
import mcp_types as types
from fastapi import FastAPI
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from opentelemetry import trace
from starlette.datastructures import Headers
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from di import telemetry
from di.core.db import SessionLocal
from di.core.errors import envelope
from di.mcp import oauth, policy
from di.mcp.tools import TOOLS, schema

PATH = "/mcp"
AGENT_HEADER, TENANT_HEADER = "x-agent", "x-tenant"


def _tool(t: dict) -> types.Tool:
    human, read = t["approval"] == "human approval required", t["rw"] == "read"
    return types.Tool(
        name=t["id"],
        description=t["desc"],
        input_schema=schema(t),
        annotations=types.ToolAnnotations(read_only_hint=read, destructive_hint=False, idempotent_hint=read),
        meta={"approval": t["approval"], "requiresHumanApproval": human, "steps": t["step"]},
    )


async def list_tools(ctx: ServerRequestContext, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:  # noqa: ARG001 - the MCP SDK's handler signature
    """Every tool when no agent is named (discovery; a call names one); else only the agent's own (MVP-11.6)."""
    headers = ctx.request.headers if ctx.request is not None else Headers()
    agent_id = await anyio.to_thread.run_sync(policy.effective_agent, _bearer(headers), headers.get(AGENT_HEADER))
    allowed = await anyio.to_thread.run_sync(policy.tools_for, agent_id)
    tools = [_tool(t) for t in TOOLS.values() if allowed is None or t["id"] in allowed]
    if agent_id:  # a named agent also gets the tools generated from the action catalogue (P9-2.13)
        tools += await anyio.to_thread.run_sync(policy.generated_tools, agent_id)
    return types.ListToolsResult(tools=tools)


def _bearer(headers: Headers) -> str | None:
    scheme, _, token = (headers.get("authorization") or "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def _observe(tool: str, answer: dict, seconds: float) -> None:
    """Plan 5: what di adds to the SDK's span `tools/call {tool}` (mcp.server._otel, on by default: the SERVER span with
    mcp.method.name, gen_ai.tool.name, jsonrpc.request.id, the parent from `params._meta` and `error.type=tool_error` when
    the result is an error): the call's outcome ("ok", "held for approval", "denied · …"), and one sample of the histogram
    `mcp.server.operation.duration`. No argument, result or token is recorded. A no-op while telemetry is off."""
    if not telemetry.enabled():
        return
    outcome = str(answer.get("outcome") or ("ok" if answer.get("ok") else "error"))
    trace.get_current_span().set_attribute("di.mcp.outcome", outcome)
    attrs: dict[str, Any] = {"mcp.method.name": "tools/call", "gen_ai.tool.name": tool}
    if not answer.get("ok"):
        attrs["error.type"] = "tool_error"
    telemetry.record_duration("mcp.server.operation.duration", seconds, attrs, "Duration of an MCP request on the server")


async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    headers = ctx.request.headers if ctx.request is not None else Headers()
    who = policy.Caller(token=_bearer(headers), agent_id=headers.get(AGENT_HEADER), tenant=headers.get(TENANT_HEADER))

    def run() -> dict:
        with SessionLocal() as s:
            return policy.call_tool(s, who, params.name, params.arguments)

    t0 = time.monotonic()
    answer = await anyio.to_thread.run_sync(run)
    _observe(params.name, answer, time.monotonic() - t0)
    return types.CallToolResult(
        content=[types.TextContent(text=policy.text_of(answer))],
        structured_content=answer,
        is_error=not answer["ok"],
    )


server = Server(
    "circularity-di",
    version="0.2.0",
    instructions=(
        "Circularity's governed agent tools. Send the account's bearer token, the agent you act as (X-Agent) and, "
        "optionally, the tenant you act for (X-Tenant). Answers are data; write tools stop at a human approval."
    ),
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)

SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["localhost:*", "127.0.0.1:*", "[::1]:*", "api:*"],
    allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"],
)
_manager: StreamableHTTPSessionManager | None = None  # the running one (a manager runs once; each lifespan makes one)


def _refuse(status: int, code: str, message: str, www: str) -> list[dict]:
    body = json.dumps(envelope(code, message)).encode()
    return [
        {"type": "http.response.start", "status": status,
         "headers": [(b"content-type", b"application/json"), (b"www-authenticate", www.encode())]},
        {"type": "http.response.body", "body": body},
    ]  # fmt: skip


def _tools_called(body: bytes) -> list[str]:
    """The tool names of the tools/call requests in a JSON-RPC body (one request or a batch); [] if it is not JSON."""
    try:
        msgs = json.loads(body)
    except ValueError:
        return []
    out = []
    for m in msgs if isinstance(msgs, list) else [msgs]:
        if isinstance(m, dict) and m.get("method") == "tools/call" and isinstance(m.get("params"), dict):
            name = m["params"].get("name")
            if isinstance(name, str):
                out.append(name)
    return out


class BearerGate:
    """The gate of /mcp: 401 for a request without a valid account token (the challenge names the resource metadata),
    401 for a token that names another audience, 403 `insufficient_scope` for a token whose `scope` lacks a call's family
    (di.mcp.oauth). A token without `scope` (the UI's account tokens) is checked as before."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def _send(self, send: Send, status: int, code: str, message: str, www: str) -> None:
        for m in _refuse(status, code, message, www):
            await send(m)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _bearer(Headers(scope=scope))
        claims = oauth.peek(token) if token else None  # unverified: only to refuse early
        if claims is not None and not oauth.audience_ok(claims):
            wrong = "This token was not issued for this server."
            await self._send(send, 401, "unauthenticated", wrong, oauth.challenge("invalid_token"))
            return
        if await anyio.to_thread.run_sync(policy.account_of, token) is None:
            www = oauth.challenge("invalid_token") if token else oauth.challenge()
            await self._send(send, 401, "unauthenticated", "Sign in first: send the account's bearer token.", www)
            return
        if claims is not None and oauth.granted(claims) is not None and scope["method"] == "POST":  # a verified token with scope
            body, more = b"", True
            while more:
                chunk = await receive()
                body += chunk.get("body", b"")
                more = chunk.get("more_body", False)
            lacking = oauth.missing(claims, _tools_called(body))
            if lacking:
                why = f"This token lacks the scope {lacking} for this call."
                await self._send(send, 403, "out_of_scope", why, oauth.challenge("insufficient_scope", lacking))
                return
            sent = False

            async def replay() -> MutableMapping[str, Any]:
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
            return
        await self.app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001 - FastAPI's lifespan signature
    """Runs the transport's session manager for the life of the app."""
    global _manager
    _manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True, security_settings=SECURITY)
    async with _manager.run():
        yield
    _manager = None


async def transport(scope: Scope, receive: Receive, send: Send) -> None:
    """The SDK's Streamable HTTP endpoint (StreamableHTTPASGIApp) of the running session manager."""
    if _manager is None:
        raise RuntimeError("The MCP session manager is not running: start the app with di.mcp.server.lifespan.")
    await StreamableHTTPASGIApp(_manager)(scope, receive, send)


def mount(app: FastAPI) -> None:
    """Serve MCP at /mcp in the FastAPI app (its lifespan must be `lifespan` above)."""
    app.router.routes.append(Route(PATH, endpoint=BearerGate(transport)))
