"""P9-2.14: OAuth protected resource metadata for MCP (RFC 9728) and the audience and scope checks of the gate.

In process: the gate (`BearerGate`) wraps a stub app, so no running api is needed. The HTTP transport itself is not
under test here (tests/test_mcp_server.py covers it against the running api).
"""

import json

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from di.core.config import get_settings
from di.mcp import oauth
from di.mcp.server import BearerGate
from tests import helpers

PRM = "/.well-known/oauth-protected-resource"


def _stub(reached: list[bool]):
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        body = b""
        while True:  # the gate replays the body it read
            m = await receive()
            body += m.get("body", b"")
            if not m.get("more_body"):
                break
        reached.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    return app


def _gate():
    reached: list[bool] = []
    return TestClient(BearerGate(_stub(reached))), reached


def _own_token() -> str:
    return helpers.h("ops")["Authorization"].split(" ", 1)[1]


def _reissue(**extra) -> str:
    """The account's own token with more claims, signed with the server's key (stands in for a token with scope/aud)."""
    claims = jwt.decode(_own_token(), options={"verify_signature": False})
    claims.update(extra)
    return jwt.encode(claims, get_settings().jwt_secret.get_secret_value(), "HS256")


def _call(tool: str) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}}).encode()


def test_mcp_prm_document(client):
    for path in (PRM, PRM + "/mcp"):
        r = client.get(path)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["resource"] == get_settings().mcp_resource_url
        assert d["scopes_supported"] == ["cases:read", "cases:write", "flows:draft", "config:draft", "tools:read"]
        assert d["bearer_methods_supported"] == ["header"]
        assert d["authorization_servers"] == [
            get_settings().mcp_resource_url.removesuffix("/mcp")
        ]  # none configured: our own (P9-13.10)


def test_mcp_prm_lists_configured_authorization_servers(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mcp_auth_servers", ["https://idp.example.com"])
    assert client.get(PRM).json()["authorization_servers"] == ["https://idp.example.com"]


def test_mcp_401_points_to_metadata():
    c, reached = _gate()
    r = c.post("/mcp", content=b"{}")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")
    assert f'resource_metadata="{oauth.metadata_url()}"' in r.headers["www-authenticate"]
    assert oauth.metadata_url().endswith(PRM)
    assert not reached


def test_mcp_token_wrong_audience_refused():
    c, reached = _gate()
    r = c.post("/mcp", content=b"{}", headers={"Authorization": "Bearer " + _reissue(aud="other")})
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]
    assert not reached


def test_mcp_insufficient_scope_403():
    c, reached = _gate()
    h = {"Authorization": "Bearer " + _reissue(scope="cases:read")}
    r = c.post("/mcp", content=_call("request_missing_evidence"), headers=h)
    assert r.status_code == 403
    w = r.headers["www-authenticate"]
    assert 'error="insufficient_scope"' in w and 'scope="cases:write"' in w and "resource_metadata=" in w
    assert not reached


def test_mcp_scope_hierarchy_and_families():
    c, reached = _gate()
    h = {"Authorization": "Bearer " + _reissue(scope="cases:write")}
    assert c.post("/mcp", content=_call("get_case_evidence"), headers=h).status_code == 200  # write implies read
    assert c.post("/mcp", content=_call("get_decision_flow"), headers=h).status_code == 403  # flow.* needs flows:draft
    assert len(reached) == 1


@pytest.mark.parametrize(
    ("tool", "scope"),
    [("get_case_evidence", "cases:read"), ("propose_rule_change", "flows:draft"), ("tools_find", "tools:read")],
)
def test_mcp_needed_scope_map(tool, scope):
    assert oauth.needed_scope(tool) == scope


def test_mcp_account_token_unchanged():
    c, reached = _gate()
    h = {"Authorization": "Bearer " + _own_token()}  # aud "di", no scope: as the UI's tokens
    assert c.post("/mcp", content=_call("request_missing_evidence"), headers=h).status_code == 200
    assert c.post("/mcp", content=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}', headers=h).status_code == 200
    assert len(reached) == 2


def test_mcp_batch_with_a_denied_call_is_refused_whole():
    c, reached = _gate()
    body = json.dumps([json.loads(_call("get_case_evidence")), json.loads(_call("request_missing_evidence"))]).encode()
    r = c.post("/mcp", content=body, headers={"Authorization": "Bearer " + _reissue(scope="cases:read")})
    assert r.status_code == 403 and not reached
