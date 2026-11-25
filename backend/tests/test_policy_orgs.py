"""The access policy reads org units (plan 8, MVP-1.2): a tenant check is a subtree check on the org tree, and the
MVP's new permissions and pages are declared beside the golden ones.

Parity: the seeded tree is `workspace` with Customer A/B/C under it, so every account sees exactly what it saw before
(tests/test_policy.py checks the golden figures; this module checks the same through the database's tree).
"""

import pytest
from sqlalchemy import text

from di.core import orgs, policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.core.golden import load

FIGURES = load("figures")["accounts"]


def _ctx() -> policy.Context:
    with SessionLocal() as s:
        return load_context(s)


@pytest.fixture
def grant_workspace_to_planner_b():
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant_grant (account_id, tenant, granted_by) VALUES ('planner-b', 'workspace', 'test') "
                 "ON CONFLICT DO NOTHING")
        )  # fmt: skip
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tenant_grant WHERE account_id = 'planner-b' AND tenant = 'workspace'"))


def test_load_context_reads_the_org_tree():
    units = _ctx().org_units
    assert units is not None
    assert units["workspace"] == orgs.OrgUnit("workspace", None, "group", "Workspace")
    assert units["Customer B"] == orgs.OrgUnit("Customer B", "workspace", "customer", "Customer B")


def test_tenants_keep_the_seeded_order():
    assert policy.tenants() == ["Customer A", "Customer B", "Customer C"]
    assert policy.tenants(_ctx())[:3] == ["Customer A", "Customer B", "Customer C"]


def test_subtree_and_ancestors():
    units = {
        "g": orgs.OrgUnit("g", None, "group", "G"),
        "s": orgs.OrgUnit("s", "g", "segment", "S"),
        "c": orgs.OrgUnit("c", "s", "company", "C"),
        "x": orgs.OrgUnit("x", "g", "customer", "X"),
    }
    assert orgs.subtree(units, "s") == {"s", "c"}
    assert orgs.subtree(units, "g") == {"g", "s", "c", "x"}
    assert orgs.subtree(units, "missing") == set()
    assert orgs.ancestors(units, "c") == ["c", "s", "g"]
    assert orgs.ancestors(units, "g") == ["g"]


@pytest.mark.parametrize("account_id", sorted(FIGURES))
def test_every_account_keeps_its_tenants(account_id):
    a = policy.account(account_id)
    ctx = _ctx()
    ctx.grants = {}  # the demo's start: no grants
    assert policy.allowed_tenants(a, ctx) == FIGURES[account_id]["allowed_tenants"]


def test_planner_a_still_sees_only_customer_a():
    a = policy.account("planner-a")
    ctx = _ctx()
    ctx.grants = {}
    assert policy.allowed_tenants(a, ctx) == ["Customer A"]
    assert policy.tenant_ok(a, "Customer A", ctx)
    assert not policy.tenant_ok(a, "Customer B", ctx) and not policy.tenant_ok(a, "Customer C", ctx)
    assert not policy.tenant_ok(a, "workspace", ctx)


@pytest.mark.usefixtures("grant_workspace_to_planner_b")
def test_grant_on_group_sees_children():
    a = policy.account("planner-b")
    ctx = _ctx()
    assert policy.tenant_ok(a, "Customer C", ctx)
    assert policy.allowed_tenants(a, ctx)[:3] == ["Customer A", "Customer B", "Customer C"]
    assert not policy.tenant_ok(policy.account("planner-a"), "Customer C", ctx)  # the grant is planner-b's only


def test_new_permissions():
    planner, approver, executive, admin = (policy.account(i) for i in ("planner-a", "approver", "executive", "admin"))
    assert policy.can(planner, "manageFlows") and not policy.can(planner, "approve.flows")
    assert policy.can(approver, "approve.flows") and not policy.can(approver, "manageFlows")
    assert not policy.can(executive, "manageFlows") and not policy.can(executive, "approve.flows")
    for perm in policy.EXTRA_PERMS:
        assert policy.can(admin, perm), perm
        assert perm in policy.permissions(), perm
    assert policy.can(policy.account("developer"), "openCases") and not policy.can(policy.account("developer"), "manageOrgs")
    assert not policy.can(planner, "manageOrgs") and not policy.can(planner, "manageAgents")


def test_can_page_modeler():
    seen = {a.id for a in policy.accounts() if policy.can_page(a, "modeler")}
    assert seen == {"admin", "planner-a", "planner-b", "planner-c", "approver", "executive", "finance"}  # Finance: P9-4.2
    assert {a.id for a in policy.accounts() if policy.can_page(a, "agents")} == {"admin", "developer"}
    assert {a.id for a in policy.accounts() if policy.can_page(a, "access", "orgs")} == {"admin"}
    assert not policy.can_page(policy.account("planner-a"), "modeler", "anything")
