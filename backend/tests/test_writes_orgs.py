"""Org actions (plan 8, MVP-1.3): org.create, org.update, org.move (Admin, manageOrgs, journaled) and the read org.tree.

Every unit a test makes has an id starting "t-org-" and is removed afterwards, with any grant on it; the seeded tree
(workspace, Customer A/B/C) is never changed.
"""

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from tests.helpers import call


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tenant_grant WHERE tenant LIKE 't-org-%'"))
        conn.execute(text("DELETE FROM org_unit WHERE id LIKE 't-org-%'"))


@pytest.fixture(autouse=True)
def clean_orgs():
    _cleanup()
    yield
    _cleanup()


def _create(uid: str, parent: str, kind: str, name: str | None = None, user: str = "admin") -> dict:
    return call("org.create", {"id": uid, "parent_id": parent, "kind": kind, "name": name or uid}, user)


def _row(uid: str):
    with engine.connect() as conn:
        return conn.execute(text("SELECT id, parent_id, kind, name FROM org_unit WHERE id = :i"), {"i": uid}).first()


def _grant(account_id: str, unit: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO tenant_grant (account_id, tenant, granted_by) VALUES (:a, :t, 'test')"),
                     {"a": account_id, "t": unit})  # fmt: skip


def _ctx() -> policy.Context:
    with SessionLocal() as s:
        return load_context(s)


def test_create_company_under_group():
    assert _create("t-org-group", "workspace", "group", "Test group")["ok"]
    r = _create("t-org-co", "t-org-group", "company", "Test company")
    assert r["ok"], r
    assert tuple(_row("t-org-co")) == ("t-org-co", "t-org-group", "company", "Test company")
    assert "t-org-co" in policy.tenants(_ctx())

    again = _create("t-org-co", "workspace", "company")
    assert again["error"] == {"code": "conflict", "message": "Org unit t-org-co already exists."}
    bad = _create("t-org-x!", "workspace", "company")
    assert bad["error"]["code"] == "validation_error"
    assert _create("t-org-y", "t-org-missing", "company")["error"]["code"] == "not_found"
    assert _create("t-org-z", "workspace", "planet")["error"]["code"] == "validation_error"


def test_update_renames():
    _create("t-org-co", "workspace", "company", "Old name")
    r = call("org.update", {"id": "t-org-co", "name": "New name"}, "admin")
    assert r["ok"], r
    assert _row("t-org-co").name == "New name"
    assert call("org.update", {"id": "t-org-none", "name": "X"}, "admin")["error"]["code"] == "not_found"


def test_move_sub_company():
    _create("t-org-east", "workspace", "group")
    _create("t-org-west", "workspace", "group")
    _create("t-org-sub", "t-org-east", "company")
    _create("t-org-site", "t-org-sub", "site")
    _grant("planner-c", "t-org-west")
    planner_c = policy.account("planner-c")
    assert not policy.tenant_ok(planner_c, "t-org-sub", _ctx())

    r = call("org.move", {"id": "t-org-sub", "parent_id": "t-org-west"}, "admin")
    assert r["ok"], r
    ctx = _ctx()
    # edge case 1: the moved company's cases (and its site's) are visible to a grant on the new parent
    assert policy.tenant_ok(planner_c, "t-org-sub", ctx) and policy.tenant_ok(planner_c, "t-org-site", ctx)
    assert policy.tenant_ok(planner_c, "Customer C", ctx)  # its own tenant is kept
    assert not policy.tenant_ok(planner_c, "Customer A", ctx)


def test_tenant_access_to_a_new_company():
    """MVP-12.4: the existing tenant access flow reaches a unit Admin created (not only the seeded customers)."""
    _create("t-org-co", "workspace", "company")
    planner_a = policy.account("planner-a")
    try:
        r = call("access.requestTenant", {"tenant": "t-org-co", "reason": "Planning its returns"}, "planner-a")
        assert r["ok"], r
        d = call("access.decideRequest", {"id": r["output"]["id"], "decision": "approve"}, "approver")
        assert d["ok"], d
        assert policy.tenant_ok(planner_a, "t-org-co", _ctx())
        nowhere = call("access.requestTenant", {"tenant": "t-org-nowhere", "reason": "No such unit"}, "planner-a")
        assert nowhere["error"]["code"] == "not_found"
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM state_item WHERE collection = 'requests' AND data->>'tenant' LIKE 't-org-%'"))


def test_cycle_refused():
    _create("t-org-top", "workspace", "group")
    _create("t-org-mid", "t-org-top", "segment")
    msg = "An org unit cannot move under itself or its own children."
    for parent in ("t-org-mid", "t-org-top"):
        r = call("org.move", {"id": "t-org-top", "parent_id": parent}, "admin")
        assert r["error"] == {"code": "conflict", "message": msg}, parent
    r = call("org.move", {"id": "workspace", "parent_id": "t-org-top"}, "admin")
    assert r["error"] == {"code": "conflict", "message": "The workspace root cannot move."}
    assert _row("t-org-top").parent_id == "workspace"


def test_planner_refused_out_of_scope():
    for action, body in (
        ("org.create", {"id": "t-org-p", "parent_id": "workspace", "kind": "company", "name": "P"}),
        ("org.update", {"id": "Customer A", "name": "Renamed"}),
        ("org.move", {"id": "Customer A", "parent_id": "workspace"}),
    ):
        r = call(action, body, "planner-a")
        assert r["error"]["code"] == "out_of_scope", (action, r)
    assert _row("t-org-p") is None and _row("Customer A").name == "Customer A"


def test_journal_row_per_write():
    def n() -> int:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT count(*) FROM action_journal WHERE action LIKE 'org.%' AND input->>'id' LIKE 't-org-%'")
            ).scalar_one()

    before = n()
    _create("t-org-a", "workspace", "group")
    _create("t-org-b", "workspace", "company")
    call("org.update", {"id": "t-org-b", "name": "B"}, "admin")
    call("org.move", {"id": "t-org-b", "parent_id": "t-org-a"}, "admin")
    call("org.tree", {}, "admin")  # a read: not journaled
    assert n() - before == 4


def test_tree():
    _create("t-org-g", "workspace", "group")
    _create("t-org-c", "t-org-g", "company")
    r = call("org.tree", {}, "admin")
    assert r["ok"], r
    (root,) = r["output"]["units"]
    assert {k: root[k] for k in ("id", "parent_id", "kind", "name")} == {
        "id": "workspace", "parent_id": None, "kind": "group", "name": "Workspace"}  # fmt: skip
    kids = {k["id"]: k for k in root["children"]}
    assert {"Customer A", "Customer B", "Customer C", "t-org-g"} <= set(kids)
    assert [c["id"] for c in kids["t-org-g"]["children"]] == ["t-org-c"]
