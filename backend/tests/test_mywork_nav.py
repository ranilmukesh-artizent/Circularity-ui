"""P9-1.8 (G 2.11): the `mywork` badge is the length of process.items_for for the account. 28 Nov 2026 (decision log):
My work left the menu (My Tasks is the one page; `mine` is its count, the list without data conflicts) and Set up is the
entry after Home for who makes or approves a composition. Home's `tasks` count is unchanged (test_screens_reference)."""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import process
from tests import starting
from tests.helpers import client, h

ACCOUNTS = [
    "admin", "approver", "developer", "engineer", "executive", "finance", "planner-a", "planner-b", "planner-c", "wm-1", "wm-2",
]  # fmt: skip
ENTRY = {"id": "setup", "label": "Set up", "sub": "Describe the business, connect systems, publish", "icon": "flag",
         "section": "", "leaf": True, "href": "#/setup", "kids": []}  # fmt: skip
SETS_UP = {"admin", "approver", "planner-a", "planner-b", "planner-c"}


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    starting.reset()
    yield
    _clean()
    starting.reset()


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_nav_has_one_tasks_entry_and_set_up_after_home(acct):
    out = client.get("/api/screens/nav", headers=h(acct)).json()
    groups = out["groups"]
    ids = [g["id"] for g in groups]
    assert ids[0] == "home" and "mywork" not in ids and "tasks" in ids
    assert (groups[1] == ENTRY) == (acct in SETS_UP) and ("setup" in ids) == (acct in SETS_UP)
    items = client.get("/api/screens/mywork", headers=h(acct)).json()["items"]
    assert out["badges"]["mine"] == sum(1 for i in items if i["kind"] != "conflict")


def _open(**kw) -> None:
    base = {"kind": "exception", "case_id": "RT-1051", "org_unit_id": "Customer A", "type": "evidence_missing",
            "title": "Wipe certificate missing", "cause": "none", "action": "chase", "owner_role": "Planner",
            "due_hours": None, "by": "system"}  # fmt: skip
    with SessionLocal() as s:
        process.open_item(s, **(base | kw))
        s.commit()


@pytest.mark.parametrize("acct", ["admin", "planner-a", "approver", "wm-1", "developer"])
def test_mywork_badge_counts_items(acct):
    def badge() -> int:
        return client.get("/api/screens/nav", headers=h(acct)).json()["badges"]["mywork"]

    n = len(client.get("/api/screens/mywork", headers=h(acct)).json()["items"])
    assert badge() == n
    _open(owner_role="Admin")
    _open(owner_role="Planner", title="Another")
    body = client.get("/api/screens/mywork", headers=h(acct)).json()
    assert badge() == len(body["items"]) and len(body["items"]) >= n


def test_badge_leaves_the_golden_tasks_count_alone():
    out = client.get("/api/screens/nav", headers=h("planner-a")).json()
    assert isinstance(out["tasks"], int) and "mywork" not in out["badges"]["sections"]
