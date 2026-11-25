"""P9-1.8 (G 2.11): My work is the menu's first entry for every role, with its own badge: the length of
process.items_for for the account. Home's `tasks` count and the golden menu are unchanged (test_screens_reference)."""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import process
from tests import starting
from tests.helpers import client, h

ACCOUNTS = [
    "admin", "approver", "developer", "engineer", "executive", "finance", "planner-a", "planner-b", "planner-c", "wm-1", "wm-2",
]  # fmt: skip
ENTRY = {"id": "mywork", "label": "My work", "sub": "Exceptions, approvals and questions for you", "icon": "inbox",
         "section": "", "leaf": True, "href": "#/mywork", "kids": []}  # fmt: skip


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
def test_nav_lists_mywork_for_every_role(acct):
    groups = client.get("/api/screens/nav", headers=h(acct)).json()["groups"]
    assert groups[0] == ENTRY and groups[1]["id"] == "home"


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
