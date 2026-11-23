"""A source read through an MCP server (plan 8, MVP-11.7): Circularity as an MCP client (story O; edge case 27).

A source whose connection has protocol "mcp" (source.update mode "mcp": {url, tool, arguments, resource_key}) is read
by calling one tool on that server with the `mcp` SDK's streamable HTTP client (the client tests/test_mcp_server.py
uses against di's own server):
    base_url    the server's MCP endpoint (e.g. source-sim's /mcp-demo)
    resources   [{name: resource_key, path: "mcp:<tool>", tool, arguments, id_field?}]
The tool's JSON answer (its structured content, else its text content parsed as JSON) gives the rows: a list, or
the list under "items". Each row becomes a Record of the resource, mapped with the source's field mapping, exactly as
the configured adapter's records are (McpAdapter is a ConfiguredAdapter that only reads differently), so the
workflow engine, raw records, mapping and canonical checks are the same.

A server that does not answer, refuses, or answers with an error is a SourceError: the sync fails, the source is
`failing` and retries on the sync reliability schedule (di.connectors.sync), as any source that is down.
"""

import json
from collections.abc import Iterator
from typing import Any

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.orm import Session

from di.connectors.configured import ConfiguredAdapter, active_rows
from di.connectors.connection import Connection, connection_for
from di.connectors.http import SourceClient, SourceError

PROTOCOL = "mcp"
TIMEOUT = 20.0


def call_tool(url: str, tool: str, arguments: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    """Call one tool on an MCP server; its JSON answer. Raises SourceError when the server fails or refuses."""

    async def go() -> Any:
        async with (
            httpx2.AsyncClient(headers=headers or {}, timeout=TIMEOUT) as hc,
            Client(streamable_http_client(url, http_client=hc)) as c,
        ):
            return await c.call_tool(tool, arguments)

    try:
        r = anyio.run(go)
    except Exception as e:  # the SDK raises transport and protocol errors in several shapes (and exception groups)
        raise SourceError("unavailable", f"MCP server {url} did not answer {tool}: {type(e).__name__}") from e
    if r.is_error:
        text = next((c.text for c in r.content if getattr(c, "type", None) == "text"), "")
        raise SourceError("client", f"MCP tool {tool} refused: {text[:200]}")
    if r.structured_content is not None:
        return r.structured_content
    text = next((c.text for c in r.content if getattr(c, "type", None) == "text"), "")
    try:
        return json.loads(text)
    except ValueError as e:
        raise SourceError("client", f"MCP tool {tool} did not answer JSON") from e


def rows_of(answer: Any) -> list[dict[str, Any]]:
    items = answer.get("items") if isinstance(answer, dict) else answer
    return [x for x in items or [] if isinstance(x, dict)] if isinstance(items, list) else []


class McpAdapter(ConfiguredAdapter):
    """The configured adapter, reading each resource with one MCP tool call instead of paged GETs."""

    protocol = PROTOCOL

    def pages(self, client: SourceClient, r: dict[str, Any], since: str | None) -> Iterator[tuple[dict, str]]:  # noqa: ARG002 - one call reads the resource in full
        rows = rows_of(call_tool(self.conn.base_url, str(r.get("tool") or ""), dict(r.get("arguments") or {})))
        url = f"{self.conn.base_url}#{r.get('tool')}"
        yield from ((row, url) for row in rows)


def resource(tool: str, arguments: dict[str, Any], resource_key: str, id_field: str | None = None) -> dict[str, Any]:
    """The resource entry source.update stores for mode "mcp"."""
    out: dict[str, Any] = {"name": resource_key, "path": f"mcp:{tool}", "tool": tool, "arguments": arguments}
    return out | ({"id_field": id_field} if id_field else {})


def is_mcp(conn: Connection | None) -> bool:
    return conn is not None and conn.protocol == PROTOCOL


def adapter_for(s: Session, source_id: str) -> McpAdapter | None:
    """The MCP adapter when the source's connection is an MCP one, else None."""
    conn = connection_for(s, source_id)
    if conn is None or not is_mcp(conn):
        return None
    return McpAdapter(conn, active_rows(s, source_id))
