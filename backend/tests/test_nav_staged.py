"""Plan 11 A1, A2, A4: the staged menu (Home, Set up and Access until a setup is published), the four sections and
the new names, and the landing. Hiding is display only: the pages stay open to whoever the policy lets in."""

import pytest

from di.core import policy
from di.services.screens import nav as svc
from tests.helpers import client, h

ACCOUNTS = [
    "admin", "approver", "developer", "engineer", "executive", "finance", "planner-a", "planner-b", "planner-c", "wm-1", "wm-2",
]  # fmt: skip


def _g(i: str, sec: str = "More", label: str | None = None) -> dict:
    return {"id": i, "label": label or i, "sub": "", "icon": "x", "sec": sec, "leaf": True, "kids": []}


def test_regroup_orders_by_section_and_relabels():
    names = ["settings", "audit", "command", "product", "home", "tasks", "setup", "analytics", "agents", "zzz"]
    out = svc.regroup([_g(i, "Old", "Old " + i) for i in names])
    assert [g["id"] for g in out] == [
        "home", "setup", "tasks", "product", "command", "analytics", "agents", "audit", "settings", "zzz",
    ]  # fmt: skip
    by = {g["id"]: g for g in out}
    assert (by["command"]["label"], by["product"]["label"]) == ("Pulse", "Cases")
    assert by["command"]["sec"] == "Understand" and by["product"]["sec"] == "Decide" and by["audit"]["sec"] == "Advanced"
    assert by["zzz"]["sec"] == "More" and by["zzz"]["label"] == "Old zzz"  # not in the table: last, name kept


def test_staged_filter_keeps_home_set_up_and_access():
    gs = [_g(i) for i in ("home", "setup", "tasks", "product", "access", "settings")]
    assert [g["id"] for g in svc.staged_filter(gs, False)] == ["home", "setup", "access"]
    assert svc.staged_filter(gs, True) == gs


def test_staged_filter_keeps_my_tasks_when_a_setup_waits_for_approval():
    gs = [_g(i) for i in ("home", "setup", "tasks", "product", "access", "settings")]
    assert [g["id"] for g in svc.staged_filter(gs, False, waiting=True)] == ["home", "setup", "tasks", "access"]
    assert [g["id"] for g in svc.staged_filter(gs, False, waiting=False)] == ["home", "setup", "access"]
    assert svc.staged_filter(gs, True, waiting=True) == gs


def test_a_submitted_setup_keeps_my_tasks_in_the_staged_menu(monkeypatch):
    monkeypatch.setattr(svc, "has_published_setup", lambda p, s, c: False)
    monkeypatch.setattr(svc, "has_submitted_setup", lambda p, s: True)
    out = client.get("/api/screens/nav", headers=h("admin")).json()
    assert out["staged"] is True
    assert [g["id"] for g in out["groups"]] == ["home", "setup", "tasks", "access"]


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_demo_accounts_see_the_sections_and_every_page(acct):
    out = client.get("/api/screens/nav", headers=h(acct)).json()
    secs = [g["section"] for g in out["groups"]]
    assert out["staged"] is False and out["landing"] is None
    assert secs == sorted(secs, key=[s for s, _ in svc.SECTION_LAYOUT].index)  # each section is one run, in order
    ids = {g["id"] for g in out["groups"]}
    for pg in ("product", "analytics", "tasks", "command"):  # every page the account may open is still there
        assert (pg in ids) == policy.can_page(policy.account(acct), pg), pg
    for g in out["groups"]:
        assert g["href"].startswith("#/" + g["id"])  # routes never change


def test_pulse_and_cases_keep_their_routes():
    g = {x["id"]: x for x in client.get("/api/screens/nav", headers=h("admin")).json()["groups"]}
    assert (g["command"]["label"], g["command"]["section"]) == ("Pulse", "Understand")
    assert g["product"]["label"] == "Cases" and g["orchestration"]["label"] == "Data pipelines and runs"
    assert g["integration"]["section"] == "Advanced" and g["settings"]["section"] == "More"


@pytest.mark.parametrize("acct", ["admin", "approver", "planner-a", "executive", "developer", "wm-1"])
def test_before_publish_the_menu_is_home_set_up_and_access(acct, monkeypatch):
    monkeypatch.setattr(svc, "has_published_setup", lambda p, s, c: False)
    out = client.get("/api/screens/nav", headers=h(acct)).json()
    a = policy.account(acct)
    assert out["staged"] is True
    want = [i for i in ("home", "setup", "access") if policy.can_page(a, i)]
    assert [g["id"] for g in out["groups"]] == want
    assert out["landing"] == ("setup" if policy.can_page(a, "setup") else None)
    # display only: the server still answers what the role may open
    assert client.get("/api/screens/mywork", headers=h(acct)).status_code in (200, 403)


def test_admin_before_publish_has_three_entries(monkeypatch):
    monkeypatch.setattr(svc, "has_published_setup", lambda p, s, c: False)
    out = client.get("/api/screens/nav", headers=h("admin")).json()
    assert [g["id"] for g in out["groups"]] == ["home", "setup", "access"]
    assert out["landing"] == "setup"
