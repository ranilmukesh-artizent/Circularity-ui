"""GET /.well-known/oauth-protected-resource[/mcp]: the MCP server's OAuth protected resource metadata (RFC 9728).

Owns: the two public routes (the root form the `WWW-Authenticate` challenge points to, and the path-inserted form RFC
9728 section 3 builds for the resource `/mcp`). Both serve the same document, built by `di.mcp.oauth.document`.
Never does: authenticate (the document is public by design), issue tokens, or name an authorization server that is
not configured (`mcp_auth_servers`) or, when none is, this server's own (P9-13.10).
"""

from fastapi import APIRouter

from di.mcp import oauth
from di.services import oauth as authorization_server

router = APIRouter()


@router.get(oauth.WELL_KNOWN)
@router.get(oauth.WELL_KNOWN + "/mcp")
def protected_resource() -> dict:
    return oauth.document()


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata() -> dict:
    """RFC 8414: our authorization server for outside MCP clients (P9-13.10)."""
    return authorization_server.metadata()
