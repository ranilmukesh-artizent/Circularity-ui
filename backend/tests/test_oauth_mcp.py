"""P9-13.10: OAuth for outside MCP clients (authorization code with PKCE, consent, audience-bound tokens; R21).

An outside client never gets more than the scopes it was registered for and the person granted; its token acts as the
person, prepared by the agent (a write holds); an agent never consents; codes are single use, short and stored hashed.
In process: the gate (`BearerGate`) wraps a stub app and tool calls go through `policy.call_tool` (the HTTP transport
needs the running api and is covered by tests/test_mcp_server.py).
"""

import base64
import hashlib
import json
import logging
import secrets
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.types import Receive, Scope, Send

from di.core.config import get_settings
from di.core.db import SessionLocal
from di.mcp import policy
from di.mcp.server import BearerGate
from di.services import agent_credentials
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
AGENT = "oauth-ag"
REDIRECT = "http://localhost:9999/cb"
RES = get_settings().mcp_resource_url
SECRET = get_settings().jwt_secret.get_secret_value()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO agent_identity (id, name, kind, tools, autonomy) "
                "VALUES (:i, 'OAuth test agent', 'external', :t, 'propose')"
            ),
            {"i": AGENT, "t": ["get_case_evidence", "request_missing_evidence"]},
        )
        s.commit()
    yield
    _clean()
    starting.reset()


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM oauth_code"))
        s.execute(text("DELETE FROM oauth_client"))
        s.execute(text("DELETE FROM agent_credential"))
        s.execute(text("DELETE FROM agent_proposal"))
        s.execute(text("DELETE FROM agent_identity WHERE id = :i"), {"i": AGENT})
        s.commit()


def register(scopes=("cases:read", "cases:write"), uris=(REDIRECT,), user="admin") -> str:
    r = call(
        "agent.registerClient",
        {"name": "Outside tool", "redirect_uris": list(uris), "agent_id": AGENT, "scopes": list(scopes)},
        user,
    )
    assert r["ok"], r
    return r["output"]["client_id"] if "output" in r else r["result"]["client_id"]


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def authorize_params(cid: str, challenge: str, **over: str) -> dict:
    q = {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT, "code_challenge": challenge,
         "code_challenge_method": "S256", "resource": RES, "scope": "cases:read cases:write", "state": "st1"}  # fmt: skip
    return {**q, **over}


def get_code(cid: str, challenge: str, user="planner-a", approve=True, **over: str) -> str:
    r = client.get("/oauth/authorize", params=authorize_params(cid, challenge, **over), follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert loc.startswith("/#/oauth/consent?req=")
    req = loc.split("req=", 1)[1]
    c = client.post("/api/oauth/consent", json={"req": req, "approve": approve}, headers=h(user))
    assert c.status_code == 200, c.text
    q = parse_qs(urlsplit(c.json()["redirect"]).query)
    assert q["state"] == ["st1"]
    return q["code"][0] if approve else q["error"][0]


def exchange(cid: str, code: str, verifier: str, **over: str):
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "client_id": cid,
        "redirect_uri": REDIRECT,
    }
    return client.post("/oauth/token", data={**form, **over})


def oauth_token(scopes=("cases:read", "cases:write"), user="planner-a") -> tuple[str, str]:
    cid = register(scopes)
    verifier, challenge = pkce()
    code = get_code(cid, challenge, user, scope=" ".join(scopes))
    r = exchange(cid, code, verifier)
    assert r.status_code == 200, r.text
    return r.json()["access_token"], cid


def _stub():
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}"})

    return TestClient(BearerGate(app))


def rpc(tool: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}})


def test_prm_served_and_linked_in_401():
    doc = client.get("/.well-known/oauth-protected-resource/mcp").json()
    issuer = RES.removesuffix("/mcp")
    assert doc["authorization_servers"] == [issuer]
    r = _stub().post("/mcp", content=rpc("get_case_evidence"))
    assert r.status_code == 401
    assert f'resource_metadata="{issuer}/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]


def test_as_metadata():
    d = client.get("/.well-known/oauth-authorization-server").json()
    assert d["authorization_endpoint"].endswith("/oauth/authorize") and d["token_endpoint"].endswith("/oauth/token")
    assert d["code_challenge_methods_supported"] == ["S256"]
    assert d["grant_types_supported"] == ["authorization_code", "client_credentials"]


def test_authorize_requires_s256_and_exact_redirect():
    cid = register()
    _, challenge = pkce()
    for over in (
        {"code_challenge_method": "plain"},
        {"redirect_uri": REDIRECT + "/"},
        {"resource": "http://other.example/mcp"},
        {"response_type": "token"},
    ):
        r = client.get("/oauth/authorize", params=authorize_params(cid, challenge, **over), follow_redirects=False)
        assert r.status_code == 400, (over, r.text)
    no_pkce = authorize_params(cid, challenge)
    del no_pkce["code_challenge"]
    assert client.get("/oauth/authorize", params=no_pkce, follow_redirects=False).status_code == 400


def test_outside_client_never_gets_more_than_its_scopes():
    cid = register(scopes=("cases:read",))
    verifier, challenge = pkce()
    r = client.get("/oauth/authorize", params=authorize_params(cid, challenge), follow_redirects=False)  # asks for cases:write
    assert r.status_code == 400 and r.json()["error"] == "invalid_scope"
    code = get_code(cid, challenge, scope="cases:read")
    tok = exchange(cid, code, verifier).json()
    assert tok["scope"] == "cases:read"
    assert (
        call("agent.registerClient", {"name": "x", "redirect_uris": [REDIRECT], "agent_id": AGENT, "scopes": ["admin"]}, "admin")[
            "ok"
        ]
        is False
    )


def test_token_audience_bound():
    tok, _ = oauth_token()
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert claims["aud"] == RES and claims["sub"] == "planner-a" and claims["act"] == {"sub": "agent:" + AGENT}
    other = jwt.encode({**claims, "aud": "http://other.example/mcp"}, SECRET, "HS256")
    r = _stub().post("/mcp", content=rpc("get_case_evidence"), headers={"Authorization": f"Bearer {other}"})
    assert r.status_code == 401
    assert _stub().post("/mcp", content=rpc("get_case_evidence"), headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    # no passthrough: the MCP token is no bearer token for the api's own endpoints
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert (
        client.post(
            "/api/actions/evidence.request", json={"case_id": "RT-1051"}, headers={"Authorization": f"Bearer {tok}"}
        ).status_code
        == 401
    )


def test_code_single_use_and_expiry(caplog):
    caplog.set_level(logging.DEBUG)
    cid = register()
    verifier, challenge = pkce()
    code = get_code(cid, challenge)
    with SessionLocal() as s:
        stored = s.execute(text("SELECT code FROM oauth_code")).scalar()
    assert stored != code and stored == hashlib.sha256(code.encode()).hexdigest()  # only the hash is stored
    first = exchange(cid, code, verifier)
    assert first.status_code == 200 and "refresh_token" not in first.json()
    second = exchange(cid, code, verifier)
    assert second.status_code == 400 and second.json()["error"] == "invalid_grant"
    code2 = get_code(cid, challenge)
    with SessionLocal() as s:  # 61 seconds on
        s.execute(text("UPDATE oauth_code SET expires_at = now() - interval '1 second' WHERE used_at IS NULL"))
        s.commit()
    assert exchange(cid, code2, verifier).status_code == 400
    assert code not in caplog.text and first.json()["access_token"] not in caplog.text


def test_verifier_and_redirect_must_match():
    cid = register()
    verifier, challenge = pkce()
    code = get_code(cid, challenge)
    assert exchange(cid, code, pkce()[0]).status_code == 400  # wrong verifier burns the code
    assert exchange(cid, code, verifier).status_code == 400
    code = get_code(cid, challenge)
    assert exchange(cid, code, verifier, redirect_uri=REDIRECT + "/").status_code == 400


def test_consent_requires_signed_in_person():
    cid = register()
    _, challenge = pkce()
    req = (
        client.get("/oauth/authorize", params=authorize_params(cid, challenge), follow_redirects=False)
        .headers["location"]
        .split("req=", 1)[1]
    )
    assert client.post("/api/oauth/consent", json={"req": req, "approve": True}).status_code == 401
    assert client.post("/api/oauth/consent", json={"req": "garbage", "approve": True}, headers=h("planner-a")).status_code == 400
    with SessionLocal() as s:  # an agent's own token cannot give consent
        cred = agent_credentials.issue(s, AGENT, "planner-a")
        s.commit()
    tok = client.post("/oauth/token", data={"grant_type": "client_credentials", **cred}).json()["access_token"]
    r = client.post("/api/oauth/consent", json={"req": req, "approve": True}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert get_code(cid, challenge, approve=False) == "access_denied"


def test_token_act_claim_sets_preparer():
    tok, _ = oauth_token()
    with SessionLocal() as s:
        read = policy.call_tool(s, policy.Caller(tok, None, None), "get_case_evidence", {"case_id": "RT-1051"})
        wrote = policy.call_tool(
            s, policy.Caller(tok, None, None), "request_missing_evidence", {"case_id": "RT-1051", "kind": "photo"}
        )
    assert read["agent"] == AGENT and read["ok"], read
    assert wrote["agent"] == AGENT, wrote
    with SessionLocal() as s:
        row = s.execute(text("SELECT agent, requested_by, status FROM agent_proposal")).first()
    assert tuple(row) == (AGENT, "planner-a", "pending")  # the person's, prepared by the agent; a write holds
    assert policy.effective_agent(tok, "gap") == AGENT


def test_insufficient_scope_403():
    tok, _ = oauth_token(scopes=("cases:read",))
    ok = _stub().post("/mcp", content=rpc("get_case_evidence"), headers={"Authorization": f"Bearer {tok}"})
    assert ok.status_code == 200
    r = _stub().post("/mcp", content=rpc("request_missing_evidence"), headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403 and 'error="insufficient_scope"' in r.headers["www-authenticate"]


def test_revoked_client_and_stopped_agent_refused():
    tok, cid = oauth_token()
    gate = _stub()
    assert gate.post("/mcp", content=rpc("get_case_evidence"), headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    with SessionLocal() as s:
        s.execute(text("UPDATE agent_identity SET enabled = false WHERE id = :i"), {"i": AGENT})
        s.commit()
    assert gate.post("/mcp", content=rpc("get_case_evidence"), headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    with SessionLocal() as s:
        s.execute(text("UPDATE agent_identity SET enabled = true WHERE id = :i"), {"i": AGENT})
        s.commit()
    assert call("agent.revokeClient", {"client_id": cid}, "admin")["ok"]
    assert gate.post("/mcp", content=rpc("get_case_evidence"), headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_register_client_forbidden_to_agents():
    with SessionLocal() as s:
        cred = agent_credentials.issue(s, AGENT, "admin")
        s.commit()
    tok = client.post("/oauth/token", data={"grant_type": "client_credentials", **cred}).json()["access_token"]
    body = {"name": "x", "redirect_uris": [REDIRECT], "agent_id": AGENT, "scopes": ["cases:read"]}
    r = client.post("/api/actions/agent.registerClient", json=body, headers={"Authorization": f"Bearer {tok}"})
    assert r.json()["error"]["code"] == "approval_required", r.text
    for who in ("planner-a", "exec"):  # only Admin (manageAgents) registers
        assert call("agent.registerClient", body, who)["ok"] is False
    listed = call("agent.clients", {}, "admin")
    assert listed["ok"]
