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
- **Identity:** `BearerGate` refuses any request without a valid account token (`Authorization: Bearer <JWT>`, the one
  /api/auth/login issues) with 401 before the SDK sees it. Each tool call then reads the token, `X-Agent` and
  `X-Tenant` from its HTTP request (the SDK hands the request to the handler) and goes to di.mcp.policy.call_tool,
  which resolves the account afresh (as every /api request does), checks, runs and logs the call. The database work
  runs in a worker thread, off the event loop.
"""

import contextlib
import json
from collections.abc import AsyncIterator

import anyio
import mcp_types as types
from fastapi import FastAPI
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from di.db import SessionLocal
from di.errors import envelope
from di.mcp import policy
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
    return types.ListToolsResult(tools=[_tool(t) for t in TOOLS.values()])


def _bearer(headers: Headers) -> str | None:
    scheme, _, token = (headers.get("authorization") or "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


async def call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    headers = ctx.request.headers if ctx.request is not None else Headers()
    who = policy.Caller(token=_bearer(headers), agent_id=headers.get(AGENT_HEADER), tenant=headers.get(TENANT_HEADER))

    def run() -> dict:
        with SessionLocal() as s:
            return policy.call_tool(s, who, params.name, params.arguments)

    answer = await anyio.to_thread.run_sync(run)
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


class BearerGate:
    """401 for a request without a valid account token, before the MCP transport reads it."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            token = _bearer(Headers(scope=scope))
            if await anyio.to_thread.run_sync(policy.account_of, token) is None:
                body = json.dumps(envelope("unauthenticated", "Sign in first: send the account's bearer token."))
                await send({
                    "type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
                })  # fmt: skip
                await send({"type": "http.response.body", "body": body.encode()})
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
