"""OAuth resource-server rules of the MCP endpoint (plan 9, P9-2.14; RFC 9728, MCP authorization, rev. 2026-07-28).

    document() -> dict                the protected resource metadata: resource, authorization_servers (only when
                                      configured), scopes_supported, bearer_methods_supported ["header"]
    metadata_url() -> str             the URL the `WWW-Authenticate` challenge names (resource_metadata)
    challenge(error, scope) -> str    the `WWW-Authenticate` value of a 401 or 403
    audience_ok(claims) -> bool       a token that names an audience must name us (or the account audience "di")
    needed_scope(tool) -> str | None  the scope family of a tool's action
    granted(claims) -> set | None     the scopes a token carries (None: no `scope` claim, as the UI's tokens)
    missing(claims, tools) -> str | None   the scope a call lacks, space-separated, or None when it may go on

Scope families: read actions on cases `cases:read`, case writes `cases:write`, `flow.*` `flows:draft`, `config.*`
`config:draft`, `tools.find` `tools:read`. A broader scope implies a narrower one (the spec's scope hierarchies):
`cases:write` covers `cases:read`.

Owns: the metadata, the challenges, the audience and scope decisions (pure; the gate in di.mcp.server applies them).
Never does: verify a token (di.core.auth does, in `policy.account_of`), log a token, or forward a client's token to
another service (a tool call runs as the account the token names, with no token passed on). A token with neither `aud`
nor `scope`, like the UI's own account JWTs (aud "di"), is judged as before.
"""

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import jwt

from di.core.auth import AUDIENCE
from di.core.config import get_settings
from di.mcp import catalog_tools
from di.mcp.tools import ACTIONS_OF, TOOLS

WELL_KNOWN = "/.well-known/oauth-protected-resource"
SCOPES = ["cases:read", "cases:write", "flows:draft", "config:draft", "tools:read"]
IMPLIES = {"cases:write": {"cases:read"}}


def document() -> dict[str, Any]:
    s = get_settings()
    doc: dict[str, Any] = {"resource": s.mcp_resource_url}
    u = urlsplit(s.mcp_resource_url)
    doc["authorization_servers"] = list(s.mcp_auth_servers) or [f"{u.scheme}://{u.netloc}"]  # else our own (P9-13.10)
    return {**doc, "scopes_supported": SCOPES, "bearer_methods_supported": ["header"]}


def metadata_url() -> str:
    u = urlsplit(get_settings().mcp_resource_url)
    return f"{u.scheme}://{u.netloc}{WELL_KNOWN}"


def challenge(error: str | None = None, scope: str | None = None) -> str:
    parts = [f'resource_metadata="{metadata_url()}"']
    if error:
        parts.insert(0, f'error="{error}"')
    if scope:
        parts.insert(1 if error else 0, f'scope="{scope}"')
    return "Bearer " + ", ".join(parts)


def peek(token: str) -> dict[str, Any] | None:
    """The claims of a token WITHOUT checking its signature: only to refuse early or to read the scope of a token the
    gate has already verified. Never a reason to accept a token."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    return claims if isinstance(claims, dict) else None


def audience_ok(claims: dict[str, Any]) -> bool:
    aud = claims.get("aud")
    if aud is None:
        return True
    names = [aud] if isinstance(aud, str) else list(aud)
    return get_settings().mcp_resource_url in names or AUDIENCE in names


def granted(claims: dict[str, Any]) -> set[str] | None:
    raw = claims.get("scope", claims.get("scp"))
    if raw is None:
        return None
    items = raw.split() if isinstance(raw, str) else [str(x) for x in raw]
    return set(items).union(*(IMPLIES.get(i, set()) for i in items))


def needed_scope(tool: str) -> str | None:
    """The scope a call to this tool needs; None for a tool that does not exist (the call itself will say so)."""
    spec = TOOLS.get(tool)
    if spec is not None:
        action = (ACTIONS_OF[tool] or ("",))[0]
        return _family(action, write=spec["rw"] != "read")
    gen = catalog_tools.action_of(tool)
    return _family(gen.id, write=gen.risk != "read") if gen is not None else None


def _family(action: str, *, write: bool) -> str:
    if action.startswith("flow."):
        return "flows:draft"
    if action.startswith("config."):
        return "config:draft"
    if action == "tools.find":
        return "tools:read"
    return "cases:write" if write else "cases:read"


def missing(claims: dict[str, Any], tools: Iterable[str]) -> str | None:
    """The scopes (space-separated, all of them in one challenge) the token lacks for these tool calls."""
    have = granted(claims)
    if have is None:
        return None
    lacking = dict.fromkeys(n for t in tools if (n := needed_scope(t)) and n not in have)
    return " ".join(lacking) or None
