"""B7: sign-in, tokens and server-side enforcement."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text

from di.core.auth import Principal, principal
from di.core.config import get_settings
from di.core.db import engine
from di.main import app


# a probe endpoint that uses the same dependency every real endpoint will use
@app.get("/api/_test/case/{case_id}")
def _probe(case_id: str, tenant: str, location: str, p: Principal = Depends(principal)):
    p.require_page("product", "case")
    p.require_record(case_id, tenant, location)
    return {"ok": True, "as": p.account.id}


client = TestClient(app)


def login(user: str) -> dict:
    r = client.post("/api/auth/login", json={"username": user, "password": "any-password"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def setup_module():
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))


def test_login_returns_the_policy_summary():
    r = client.post("/api/auth/login", json={"username": "planner.a@northfield.example", "password": "x"}).json()
    assert r["account"]["id"] == "planner-a" and r["home"] == "home" and r["tenants"] == ["Customer A"]
    assert "submit" in r["permissions"] and "approve.decisions" not in r["permissions"]
    assert "integration" not in r["pages"] and "received" in r["pages"]["product"]


def test_login_errors():
    assert client.post("/api/auth/login", json={"username": "", "password": "x"}).status_code == 400
    assert client.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "exec", "password": ""}).status_code == 400


def test_me_needs_a_valid_token():
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert client.get("/api/auth/me", headers=login("exec")).json()["account"]["role"] == "Executive"


def _token(**claims) -> str:
    now = datetime.now(UTC)
    base = {"sub": "admin", "iat": now, "exp": now + timedelta(minutes=5), "iss": "di-api", "aud": "di"}
    return jwt.encode(
        {k: v for k, v in (base | claims).items() if v is not None}, get_settings().jwt_secret.get_secret_value(), "HS256"
    )


def test_tokens_carry_issuer_and_audience():
    token = login("exec")["Authorization"][7:]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "di-api" and claims["aud"] == "di" and claims["sub"] == "executive"
    assert {"exp", "iat"} <= claims.keys()


@pytest.mark.parametrize(
    "claims",
    [{"aud": None}, {"aud": "other"}, {"iss": None}, {"iss": "someone-else"}, {"exp": None}, {"iat": None}, {"sub": None}],
)
def test_a_token_without_the_required_claims_is_refused(claims):
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + _token()}).status_code == 200
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer " + _token(**claims)})
    assert r.status_code == 401, claims
    assert r.json()["error"] == {"code": "unauthenticated", "message": "Your session has ended. Sign in again."}


def test_a_stream_ticket_needs_a_valid_access_token():
    url = "/api/auth/stream-ticket"
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer " + _token(aud="other")}).status_code == 401
    r = client.post(url, headers=login("warehouse2"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expires_in"] == 60 and set(body) == {"ticket", "expires_in"}
    claims = jwt.decode(body["ticket"], options={"verify_signature": False})
    assert claims["aud"] == "stream" and claims["iss"] == "di-api" and claims["sub"] == "wm-2"
    assert claims["role"] == "Warehouse Manager" and {"exp", "iat", "tenant"} <= claims.keys()
    assert 0 < claims["exp"] - claims["iat"] <= 60


def test_a_stream_ticket_is_not_an_access_token():
    from di.mcp.policy import account_of

    ticket = client.post("/api/auth/stream-ticket", headers=login("admin")).json()["ticket"]
    as_bearer = {"Authorization": "Bearer " + ticket}
    r = client.get("/api/auth/me", headers=as_bearer)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
    # no second ticket from a ticket, no action (an unknown caller is refused), no MCP
    assert client.post("/api/auth/stream-ticket", headers=as_bearer).status_code == 401
    assert client.post("/api/actions/decision.submit", json={"case_id": "RT-1048"}, headers=as_bearer).status_code == 401
    assert client.get("/api/actions", headers=as_bearer).status_code == 401
    assert account_of(ticket) is None
    assert account_of(login("admin")["Authorization"][7:]) is not None


def test_tenant_boundary_and_warehouse_lock():
    rt1048 = {"tenant": "Customer A", "location": "Warehouse 1"}
    assert client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("ops")).status_code == 200
    r = client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("planner.b"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_boundary"
    assert client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("warehouse1")).status_code == 200
    r = client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("warehouse2"))
    assert r.status_code == 403 and "outside your warehouse" in r.json()["error"]["message"]
    assert client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("developer")).status_code == 403  # no case pages


def test_admin_delegation_takes_effect_for_the_approver_at_once():
    approver = login("approver")
    assert "approve.decisions" in client.get("/api/auth/me", headers=approver).json()["permissions"]
    assert client.put("/api/access/delegations/decisions", json={"enabled": False}, headers=approver).status_code == 403
    admin = login("admin")
    assert client.put("/api/access/delegations/decisions", json={"enabled": False}, headers=admin).status_code == 200
    assert "approve.decisions" not in client.get("/api/auth/me", headers=approver).json()["permissions"]
    client.put("/api/access/delegations/decisions", json={"enabled": True}, headers=admin)
    assert "approve.decisions" in client.get("/api/auth/me", headers=approver).json()["permissions"]
    assert client.put("/api/access/delegations/nope", json={"enabled": True}, headers=admin).status_code == 404
