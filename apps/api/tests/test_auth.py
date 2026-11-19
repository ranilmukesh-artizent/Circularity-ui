"""B7: sign-in, tokens and server-side enforcement."""

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text

from di.auth import Principal, principal
from di.db import engine
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


def test_tenant_boundary_and_warehouse_lock():
    rt1048 = {"tenant": "Customer A", "location": "Warehouse 1"}
    assert client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("ops")).status_code == 200
    r = client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("planner.b"))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "tenant_boundary"
    assert client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("warehouse1")).status_code == 200
    r = client.get("/api/_test/case/RT-1048", params=rt1048, headers=login("warehouse2"))
    assert r.status_code == 403 and "outside your warehouse" in r.json()["detail"]["message"]
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
