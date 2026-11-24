"""Plan 8 UI gaps, agent A: tenant grants that reach the session, expire and can be revoked, the Planner's own view of
its requests and grants, and maker-checker on access requests and MCP server proposals.

- access.decideRequest takes an optional `expires_hours` (1 to 2160; absent or null: no end). An expired or revoked
  grant stops counting at once: the account's tenants (/api/auth/me) and every tenant check read only live grants.
- access.revokeGrant {account_id, tenant, note?}: Admin, or the Approver while the tenantAccess delegation is on.
- access.grants (read): the live grants, for those who may revoke them. access.myAccess (read): the signed-in account's
  own tenant requests, live grants and the tenants it may still ask for.
- Nobody decides their own request or proposal (out_of_scope), and the screens' can_decide is false for it.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import engine
from di.mcp.policy import FORBIDDEN_ACTIONS
from di.services.cases import store
from tests.helpers import call, client, h

OWN = "You made this request, so another person must decide it."


def _reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
    store.reset()
    state.reset()


@pytest.fixture
def fresh():
    _reset()
    yield
    _reset()


def me(acct: str) -> dict:
    r = client.get("/api/auth/me", headers=h(acct))
    assert r.status_code == 200, r.text
    return r.json()


def approve_304(by: str = "approver", **extra) -> dict:
    """The seeded request REQ-304: planner-b asks for Customer A."""
    return call("access.decideRequest", {"id": "REQ-304", "decision": "approve", **extra}, by)


# ---------------------------------------------------------------- maker-checker
def test_nobody_approves_their_own_mcp_proposal(fresh):
    spec = {"name": "Spare parts MCP", "owner": "Operations", "purpose": "Look up spare parts for repairs.",
            "access": "read", "data": "Part numbers", "tools": ["part.search"]}  # fmt: skip
    rid = call("mcp.propose", spec, "admin")["output"]["id"]
    got = call("access.decideRequest", {"id": rid, "decision": "approve"}, "admin")
    assert got["ok"] is False and got["error"] == {"code": "out_of_scope", "message": OWN}
    got = call("access.decideRequest", {"id": rid, "decision": "decline", "note": "Not needed now"}, "admin")
    assert got["error"]["code"] == "out_of_scope"
    rows = client.get("/api/screens/mcp/proposals", headers=h("admin")).json()["proposals"]
    assert next(r for r in rows if r["id"] == rid)["can_decide"] is False
    screen = client.get("/api/screens/access", headers=h("admin")).json()["requests"]
    assert rid not in screen["inbox"]
    # another person decides it
    assert call("access.decideRequest", {"id": rid, "decision": "approve"}, "approver")["ok"]


def test_nobody_approves_their_own_tenant_request(fresh):
    rid = call("access.requestTenant", {"tenant": "Customer A", "reason": "Checking the shared motor pool."}, "admin")
    rid = rid["output"]["id"]
    got = call("access.decideRequest", {"id": rid, "decision": "approve"}, "admin")
    assert got["error"] == {"code": "out_of_scope", "message": OWN}


def test_seeded_requests_still_decidable_as_before(fresh):
    rows = client.get("/api/screens/mcp/proposals", headers=h("admin")).json()["proposals"]
    assert {r["id"]: r["can_decide"] for r in rows} == {"REQ-301": True, "REQ-303": False, "REQ-302": False}


# ---------------------------------------------------------------- grants reach the session, expire, are revoked
def test_a_grant_without_end_shows_in_the_session(fresh):
    assert "Customer A" not in me("planner-b")["tenants"]
    assert approve_304()["ok"]
    m = me("planner-b")
    assert "Customer A" in m["tenants"]
    assert m["grants"] == [{"tenant": "Customer A", "expires_at": None}]
    assert call("case.get", {"case_id": "RT-1048"}, "planner-b")["ok"]


def test_a_time_limited_grant_expires(fresh):
    assert approve_304(expires_hours=8)["ok"]
    g = me("planner-b")["grants"]
    assert len(g) == 1 and g[0]["tenant"] == "Customer A" and g[0]["expires_at"]
    left = datetime.fromisoformat(g[0]["expires_at"]) - datetime.now(UTC)
    assert 7.9 * 3600 < left.total_seconds() <= 8 * 3600
    listed = call("access.grants", {}, "admin")["output"]["grants"]
    assert [(x["account_id"], x["tenant"]) for x in listed] == [("planner-b", "Customer A")]
    assert listed[0]["expires_at"] == g[0]["expires_at"]
    with engine.begin() as conn:  # the end has passed
        conn.execute(text("UPDATE tenant_grant SET expires_at = now() - interval '1 minute'"))
    assert "Customer A" not in me("planner-b")["tenants"]
    assert me("planner-b")["grants"] == []
    assert call("case.get", {"case_id": "RT-1048"}, "planner-b")["error"]["code"] == "tenant_boundary"
    assert call("access.grants", {}, "admin")["output"]["grants"] == []


@pytest.mark.parametrize("bad", [0, -1, 2161])
def test_an_expiry_out_of_range_is_refused(fresh, bad):
    got = approve_304(expires_hours=bad)
    assert got["ok"] is False and got["error"]["code"] == "validation_error"


def test_admin_revokes_a_grant(fresh):
    assert approve_304()["ok"]
    got = call("access.revokeGrant", {"account_id": "planner-b", "tenant": "Customer A"}, "planner-b")
    assert got["error"]["code"] == "out_of_scope"
    got = call("access.revokeGrant", {"account_id": "planner-b", "tenant": "Customer A", "note": "Pool review done"}, "admin")
    assert got["ok"] and got["output"] == {"account_id": "planner-b", "tenant": "Customer A"}
    assert "Customer A" not in me("planner-b")["tenants"]
    assert call("case.get", {"case_id": "RT-1048"}, "planner-b")["error"]["code"] == "tenant_boundary"
    again = call("access.revokeGrant", {"account_id": "planner-b", "tenant": "Customer A"}, "admin")
    assert again["error"]["code"] == "not_found"
    with engine.connect() as conn:
        row = conn.execute(text("SELECT revoked_by, revoked_at FROM tenant_grant")).one()
    assert row.revoked_by == "admin" and row.revoked_at is not None
    # a new request, approved, grants it again
    rid = call("access.requestTenant", {"tenant": "Customer A", "reason": "The pool review needs one more week."}, "planner-b")
    assert call("access.decideRequest", {"id": rid["output"]["id"], "decision": "approve", "expires_hours": 168}, "admin")["ok"]
    assert "Customer A" in me("planner-b")["tenants"]


def test_the_approver_revokes_only_with_the_delegation(fresh):
    assert approve_304()["ok"]
    assert call("access.setDelegation", {"k": "tenantAccess", "on": False}, "admin")["ok"]
    got = call("access.revokeGrant", {"account_id": "planner-b", "tenant": "Customer A"}, "approver")
    assert got["error"]["code"] == "out_of_scope"
    assert call("access.grants", {}, "approver")["error"]["code"] == "out_of_scope"
    assert call("access.setDelegation", {"k": "tenantAccess", "on": True}, "admin")["ok"]
    assert call("access.grants", {}, "approver")["ok"]
    assert call("access.revokeGrant", {"account_id": "planner-b", "tenant": "Customer A"}, "approver")["ok"]


def test_agents_never_revoke():
    assert any("access.revokeGrant".startswith(p) for p in FORBIDDEN_ACTIONS)


# ---------------------------------------------------------------- the Planner's own view
def test_my_access_lists_own_requests_grants_and_options(fresh):
    out = call("access.myAccess", {}, "planner-b")["output"]
    assert [r["id"] for r in out["requests"]] == ["REQ-304"] and out["requests"][0]["status"] == "pending"
    assert out["grants"] == []
    assert out["options"] == [
        {"id": "Customer A", "name": "Customer A", "pending": True},
        {"id": "Customer C", "name": "Customer C", "pending": False},
    ]
    assert approve_304(expires_hours=8)["ok"]
    out = call("access.myAccess", {}, "planner-b")["output"]
    assert out["requests"][0]["status"] == "approved"
    assert [g["tenant"] for g in out["grants"]] == ["Customer A"] and out["grants"][0]["expires_at"]
    assert [o["id"] for o in out["options"]] == ["Customer C"]
    # an account without the permission cannot read it
    assert call("access.myAccess", {}, "wm-1")["error"]["code"] == "out_of_scope"
