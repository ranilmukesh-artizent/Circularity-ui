"""P9-1.7 (I-20): GET /api/screens/mywork, My work, the one work list: open work items for the account's role or assigned
to it, approvals and tasks (Home's list), the agents' proposals for the person and the conflicts that hold a decision,
each row with a kind, a due time and a link. Every test ends with the starting state."""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import process
from tests import starting
from tests.helpers import call, client, h

CASE = "RT-1051"  # Customer A
KINDS = {"exception", "approval", "needs_info", "proposal", "conflict", "task"}
AGENT = {"id": "ext-mywork", "name": "My work proposer", "tools": ["request_missing_evidence"], "autonomy": "propose"}


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item"))
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    starting.reset()
    yield
    _clean()
    starting.reset()


def _open(**kw) -> int:
    base = {
        "kind": "exception", "case_id": CASE, "org_unit_id": "Customer A", "type": "evidence_missing",
        "title": "Wipe certificate missing",
        "cause": "No certificate on file", "action": "Wait for the wipe certificate or chase the source", "owner_role": "Admin",
        "due_hours": None, "by": "system",
    }  # fmt: skip
    with SessionLocal() as s:
        item = process.open_item(s, **(base | kw))
        s.commit()
    return item


def _mywork(user: str) -> dict:
    r = client.get("/api/screens/mywork", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def test_mywork_requires_sign_in():
    assert client.get("/api/screens/mywork").status_code == 401


def test_mywork_shape_and_counts_for_every_role():
    for user in ("admin", "planner-a", "planner-b", "approver", "engineer", "finance", "developer", "executive", "wm-1", "wm-2"):
        body = _mywork(user)
        assert set(body) == {"items", "counts", "kpis"} and body["kpis"] == []
        assert set(body["counts"]) == KINDS
        assert all(
            set(i) == {"id", "kind", "case_id", "title", "cause", "action", "owner", "due", "overdue", "priority", "go"}
            for i in body["items"]
        )
        for k in KINDS:
            assert body["counts"][k] == sum(1 for i in body["items"] if i["kind"] == k)


def test_mywork_merges_sources():
    ex = _open(title="Exception for Admin")
    assert call("agent.register", AGENT, "admin")["ok"] is True
    held = client.post(
        "/api/actions/evidence.request", json={"case_id": CASE}, headers=h("planner-a") | {"X-Circularity-Preparer": AGENT["id"]}
    ).json()
    assert held["ok"] is True and "held" in held["output"], held
    body = _mywork("admin")
    kinds = {i["kind"] for i in body["items"]}
    assert {"exception", "approval", "proposal"} <= kinds, kinds
    row = next(i for i in body["items"] if i["id"] == f"w:{ex}")
    assert row["kind"] == "exception" and row["title"] == "Exception for Admin" and row["case_id"] == CASE
    assert row["owner"] == "Admin" and row["overdue"] is False and row["go"] == "product/" + CASE
    prop = next(i for i in body["items"] if i["kind"] == "proposal")
    assert prop["case_id"] == CASE and prop["id"] == f"p:{held['output']['held']}"


def test_mywork_sorts_by_priority_then_due_and_flags_overdue():
    late = _open(title="Late", due_hours=-3)
    soon = _open(title="Soon", due_hours=2)
    urgent = _open(title="Urgent", due_hours=10)
    with SessionLocal() as s:
        s.execute(text("UPDATE work_item SET priority = 10 WHERE id = :i"), {"i": urgent})
        s.commit()
    items = [i for i in _mywork("admin")["items"] if i["kind"] == "exception"]
    assert [i["title"] for i in items] == ["Urgent", "Late", "Soon"]
    by_id = {i["id"]: i for i in items}
    assert by_id[f"w:{late}"]["overdue"] is True and by_id[f"w:{soon}"]["overdue"] is False and by_id[f"w:{soon}"]["due"]


def test_mywork_hides_closed_items_and_other_tenants():
    _open(title="Visible")
    done = _open(title="Done one")
    other = _open(title="Customer B's", case_id=None, org_unit_id="Customer B", owner_role="Planner")
    with SessionLocal() as s:
        process.close_item(s, done, "resolved", "admin")
        s.commit()
    assert [i["title"] for i in _mywork("admin")["items"] if i["kind"] == "exception"] == ["Visible"]
    assert all(i["id"] != f"w:{other}" for i in _mywork("planner-a")["items"])
