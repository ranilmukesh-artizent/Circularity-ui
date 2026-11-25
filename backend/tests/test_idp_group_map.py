"""P9-8.10 (story X-10): directory groups map to roles as data, with maker-checker, and "test a user" says why.

Covers the table `idp_group_map` (migration 0057, seeded from policy.IDP_GROUPS), policy.group_role, the actions
access.saveGroupMap / approveGroupMap / testUser, and sign-in resolution reading the table. The identity provider is
not involved: resolution is called with the groups a token would carry.
"""

import pytest
from sqlalchemy import text

from di.core import policy, state
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.services import oidc
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from tests.helpers import call

GROUP_C = "circ-planners-customer-c"
MAKER_CHECKER = "Maker-checker: you changed this mapping, so another person must approve it."


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM idp_group_map WHERE created_by <> 'seed'"))
        conn.execute(text("UPDATE idp_group_map SET status = 'approved', approved_by = NULL WHERE created_by = 'seed'"))
    with SessionLocal() as s:
        for coll in ("accounts", "idp_users"):
            for item in state.items(s, coll):
                if str(item["id"]).startswith("sso-"):
                    state.delete(s, coll, item["id"])
        mine = "'access.provisionUser', 'access.saveGroupMap', 'access.approveGroupMap'"
        journal = f"SELECT seq FROM action_journal WHERE action IN ({mine})"  # noqa: S608 - a constant
        s.execute(text(f"DELETE FROM domain_event WHERE seq IN ({journal})"))  # noqa: S608 - a constant
        s.execute(text(f"DELETE FROM action_journal WHERE action IN ({mine})"))  # noqa: S608 - a constant
        s.execute(text("DELETE FROM state_item WHERE collection = 'events' AND data->>'type' LIKE 'identity.group_map.%'"))
        s.execute(text("DELETE FROM state_item WHERE collection = 'events' AND data->>'type' = 'user.provisioned'"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    yield
    _clean()


def _rule(group: str):
    with SessionLocal() as s:
        return policy.group_role(group, load_context(s))


def _save(body: dict, user: str = "admin") -> dict:
    return call("access.saveGroupMap", {"group_id": GROUP_C, "role": "Planner", "org_unit_id": "Customer C"} | body, user)


def _email(account_id: str) -> str:
    return next(u["email"] for u in policy.starting_idp_users() if u["id"] == account_id)


def _as_agent(action: str, body: dict, confirmed: bool = False) -> dict:
    with SessionLocal() as s:
        pctx = load_context(s)
        actor = Actor(account=policy.account("admin", pctx), ctx=pctx)
        r = invoke(action, body, CallContext(actor=actor, session=s, preparer="assembler", confirmed=confirmed))
        s.rollback()
    return r


def test_x_10_group_maps_role_with_scope():
    seeded = _rule("circ-planners-customer-b")
    assert seeded is not None and seeded.role == "Planner" and seeded.org_unit_id == "Customer B"
    saved = _save({"site": "Warehouse 2"})
    assert saved["ok"], saved
    assert _rule(GROUP_C).site == "Warehouse 1"  # a draft changes nothing
    assert call("access.approveGroupMap", {"id": saved["output"]["id"]}, "approver")["ok"]
    rule = _rule(GROUP_C)
    assert rule.role == "Planner" and rule.org_unit_id == "Customer C" and rule.site == "Warehouse 2"
    with SessionLocal() as s:  # resolution reads the table: the joiner gets the new scope
        account = oidc.resolve_directory_user(s, "joiner.two@example.com", [GROUP_C])
    assert account is not None and account.tenant == "Customer C" and account.site == "Warehouse 2"


def test_x_10_test_user_shows_roles_and_why():
    out = call("access.testUser", {"email": _email("planner-b")}, "admin")["output"]
    assert out["found"] is True and out["role"] == "Planner" and out["tenants"] == ["Customer B"]
    assert out["via_group"] == "circ-planners-customer-b" and out["source"] == "directory"
    assert out["why"] == "Role from group circ-planners-customer-b"
    assert "approval_limit" in out and "delegations" in out and "manageFlows" in out["permissions"]
    unknown = call("access.testUser", {"email": "nobody@example.com"}, "admin")["output"]
    assert unknown["found"] is False and unknown["source"] == "none" and unknown["role"] is None
    by_group = call("access.testUser", {"email": "nobody@example.com", "groups": [GROUP_C]}, "admin")["output"]
    assert by_group["source"] == "group map" and by_group["role"] == "Planner" and by_group["tenants"] == ["Customer C"]


def test_test_user_open_to_the_approver_but_not_a_planner():
    assert call("access.testUser", {"email": _email("planner-a")}, "approver")["ok"]
    assert call("access.testUser", {"email": _email("planner-a")}, "planner-a")["error"]["code"] == "out_of_scope"


def test_group_map_maker_cannot_approve():
    row = _save({})["output"]["id"]
    refused = call("access.approveGroupMap", {"id": row}, "admin")
    assert refused["ok"] is False and refused["error"]["message"] == MAKER_CHECKER
    assert call("access.approveGroupMap", {"id": row}, "approver")["ok"]
    with SessionLocal() as s:
        q = text("SELECT status, approved_by FROM idp_group_map WHERE group_id = :g ORDER BY id")
        rows = s.execute(q, {"g": GROUP_C}).all()
    assert [r.status for r in rows] == ["retired", "approved"] and rows[1].approved_by == "approver"  # the seed row retires


def test_group_map_needs_the_permissions():
    assert _save({}, "planner-a")["error"]["code"] == "out_of_scope"
    row = _save({})["output"]["id"]
    assert call("access.approveGroupMap", {"id": row}, "finance")["error"]["code"] == "out_of_scope"


def test_group_map_validation():
    assert _save({"role": "Admin"})["error"]["code"] == "validation_error"  # never Admin from a group
    assert _save({"valid_from": "2026-12-01", "valid_to": "2026-11-01"})["error"]["code"] == "validation_error"


def test_group_map_expired_row_does_not_resolve():
    row = _save({"valid_from": "2020-01-01", "valid_to": "2020-12-31"})["output"]["id"]
    assert call("access.approveGroupMap", {"id": row}, "approver")["ok"]
    assert _rule(GROUP_C) is None  # approved but out of date, and the seed row it retired is gone


def test_group_map_agent_cannot_approve():
    assert "access." in FORBIDDEN_ACTIONS
    row = _save({})["output"]["id"]
    for action, body in (
        ("access.saveGroupMap", {"group_id": GROUP_C, "role": "Planner"}),
        ("access.approveGroupMap", {"id": row}),
    ):
        for confirmed in (False, True):
            r = _as_agent(action, body, confirmed)
            assert r["ok"] is False and r["error"]["code"] == "approval_required", (action, r)
    r = _as_agent("access.testUser", {"email": _email("planner-b")})
    assert r["ok"] is True and r["output"]["role"] == "Planner"


def test_group_map_tenant_boundary():
    r = _save({"org_unit_id": "nowhere"})
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert r["error"]["message"] == "nowhere is not an organisation in this workspace."


def test_group_map_seed_parity():
    with SessionLocal() as s:
        ctx = load_context(s)
    assert len(policy.IDP_GROUPS) == 10
    for acct_id, group in policy.IDP_GROUPS.items():
        a = policy.account(acct_id, ctx)
        rule = policy.group_role(group, ctx)
        assert a is not None and rule is not None, group
        assert (rule.role, rule.org_unit_id, rule.site, rule.warehouse) == (a.role, a.tenant, a.site, a.warehouse), group
    assert call("access.syncDirectory", {}, "admin")["ok"]
    with SessionLocal() as s:
        notes = [e["note"] for e in state.items(s, "events") if e.get("type") == "directory.synced"]
    assert "Directory sync: 13 users, 10 mappings" in notes  # the demo has 13 directory users (the spec said 12)
