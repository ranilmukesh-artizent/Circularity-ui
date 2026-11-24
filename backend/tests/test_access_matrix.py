"""P9-0.13: Access shows the role matrix and tests a directory user (G §6 item 11; G §7.3 A3, A4).

- access.roleMatrix {} (read, manageIdentity): roles, permission rows and page rows, each {role: bool}, computed with
  policy.can and policy.can_page for an account of each role.
- access.testUser {user_id} (read, manageIdentity): what a directory user gets: role and why, account, tenants,
  warehouse, pages, permissions, approval limit and self-approval.
Both sit in the forbidden "access." family, so an agent's call is refused by the pipeline like the other access actions.
"""

from tests.helpers import call


def _row(rows: list[dict], key: str, name: str) -> dict:
    return next(r for r in rows if r[key] == name)["roles"]


def test_role_matrix_planner_row():
    out = call("access.roleMatrix", {}, "admin")["output"]
    assert "Planner" in out["roles"] and "Approver" in out["roles"]
    flows = _row(out["permissions"], "perm", "manageFlows")
    assert flows["Planner"] is True and flows["Approver"] is False
    appr = _row(out["permissions"], "perm", "approve.flows")
    assert appr["Approver"] is True and appr["Planner"] is False
    assert _row(out["pages"], "page", "modeler")["Planner"] is True
    assert _row(out["pages"], "page", "agents")["Planner"] is False
    assert all(set(r["roles"]) == set(out["roles"]) for r in out["permissions"] + out["pages"])


def test_test_user_planner_a():
    out = call("access.testUser", {"user_id": "planner-a"}, "admin")["output"]
    assert out["user_id"] == "planner-a" and out["role"] == "Planner"
    assert out["tenants"] == ["Customer A"]
    assert "circ-planners-customer-a" in out["why"]
    assert out["why"] == "Group circ-planners-customer-a maps to Planner"
    assert out["account"] is not None and out["group"] == "circ-planners-customer-a"
    assert "manageFlows" in out["permissions"] and "approve.flows" not in out["permissions"]
    assert "modeler" in out["pages"]
    assert out["self_approve"] is False


def test_test_user_deputy():
    out = call("access.testUser", {"user_id": "dep-ap"}, "admin")["output"]
    assert out["role"] == "Approver" and out["account"] is None
    assert out["why"] == "Directory deputy without an account: role Approver from the directory"
    assert "approve.flows" in out["permissions"]


def test_test_user_unknown():
    r = call("access.testUser", {"user_id": "nobody"}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "not_found"
    assert r["error"]["message"] == "No directory user nobody."


def test_role_matrix_needs_manage_identity():
    for action, body in (("access.roleMatrix", {}), ("access.testUser", {"user_id": "planner-a"})):
        r = call(action, body, "planner.a")
        assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
