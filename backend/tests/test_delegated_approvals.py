"""Out-of-office delegation in approvals (plan 8 gaps, agent C).

Admin records an out-of-office delegation for the Approver (access.setOutOfOffice: a delegate who holds the Approver
role, from and until). While it is active (from <= the workspace's as-of day <= until), Admin has delegated decisions
to the Approver, and the delegate signs in to an account that holds the Approver role now:
- the case's "Waiting for ..." texts and the Approvals inbox name the delegate;
- what the delegate approves or declines is recorded "on behalf of" the absent Approver (journal output_ref, the
  approval, the case run), within the delegate's own limit; whoever acts first completes the item.
The seeded deputy (approver.deputy@example.com) has no sign-in account, so the tests map the Engineer's group to the
Approver role and name the Engineer as the delegate. With no active delegation everything is as before.
"""

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import engine
from di.services.cases import store
from tests.helpers import call, client, h

RATIONALE = "Redeploy to Site 3 as recommended; evidence snapshot reviewed."
DELEGATE = "engineer@example.com"
ABSENT = "approver@example.com"


@pytest.fixture
def fresh():
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
    store.reset()
    state.reset()
    yield
    store.reset()
    state.reset()


def _engineer_covers(frm: str = "2026-10-01", until: str = "2026-10-31") -> None:
    r = call("access.mapIdentity", {"acct": "engineer", "field": "role", "value": "Approver"}, "admin")
    assert r["ok"], r
    r = call("access.setOutOfOffice", {"to": "engineer", "from": frm, "until": until}, "admin")
    assert r["ok"], r


def _submit(case_id: str = "RT-1048") -> None:
    r = call("decision.submit", {"case_id": case_id}, "planner-a")
    assert r["ok"], r


def _case(case_id: str, user: str) -> dict:
    r = client.get(f"/api/screens/case/{case_id}", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def _cmd(path: str, user: str) -> dict:
    r = client.get(f"/api/screens/command/{path}", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def _journal(action: str) -> list:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT actor, output_ref FROM action_journal WHERE action = :a AND NOT undone ORDER BY seq"), {"a": action}
            ).all()
        )


def _stage7(page: dict) -> dict:
    return page["run"]["stages"][6]


def test_without_delegation_texts_are_the_demos(fresh):
    _submit()
    pg = _case("RT-1048", "planner-a")
    assert pg["next"]["label"] == "Waiting for an Approver"
    assert _stage7(pg)["result"] == "Submitted by Planner · Customer A; waiting for an Approver"
    assert "cover" not in _cmd("inbox", "approver")
    assert _cmd("handed", "planner-a")["awaiting"]["decider"] == "Approver"
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": RATIONALE, "reviewed": True}, "approver")
    assert r["ok"] and "on_behalf_of" not in r["output"], r
    assert _journal("decision.approve")[0].output_ref.get("on_behalf_of") is None


def test_delegate_is_named_while_the_approver_is_away(fresh):
    _engineer_covers()
    _submit()
    pg = _case("RT-1048", "planner-a")
    assert pg["next"]["label"] == f"Waiting for {DELEGATE} (covering for the Approver)"
    assert _stage7(pg)["result"] == f"Submitted by Planner · Customer A; waiting for {DELEGATE} (covering for the Approver)"
    assert pg["stages"][6]["res"].endswith(f"; waiting for {DELEGATE} (covering for the Approver).")
    assert _cmd("handed", "planner-a")["awaiting"]["decider"] == f"{DELEGATE} (for the Approver)"
    mine = _cmd("inbox", "engineer")["cover"]
    assert mine == {"delegate": DELEGATE, "for": ABSENT, "from": "2026-10-01", "until": "2026-10-31", "you": True}
    assert _cmd("inbox", "approver")["cover"]["you"] is False
    mine = next(x for x in _cmd("aome?all=true", "engineer")["items"] if x["t"] == "RT-1048 · approve or decline")
    assert mine["d"].endswith(f" · on behalf of {ABSENT}")
    theirs = next(x for x in _cmd("aome?all=true", "approver")["items"] if x["t"] == "RT-1048 · approve or decline")
    assert "on behalf of" not in theirs["d"]


def test_delegate_approves_on_behalf_of_the_approver(fresh):
    _engineer_covers()
    _submit()
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": RATIONALE, "reviewed": True}, "engineer")
    assert r["ok"], r
    assert r["output"]["on_behalf_of"] == ABSENT
    row = _journal("decision.approve")[0]
    assert row.actor == "engineer" and row.output_ref["on_behalf_of"] == ABSENT
    pg = _case("RT-1048", "planner-a")
    assert _stage7(pg)["result"].startswith(f"Approved by {DELEGATE} on behalf of {ABSENT} under APR-")
    assert pg["stages"][6]["res"].startswith(f"Approved by {DELEGATE} on behalf of {ABSENT} under APR-")


def test_delegate_declines_on_behalf_of_the_approver(fresh):
    _engineer_covers()
    _submit("RT-1049")
    r = call("decision.decline", {"case_id": "RT-1049", "reason": "Refurbish first: grade A listings are open."}, "engineer")
    assert r["ok"] and r["output"]["on_behalf_of"] == ABSENT, r
    assert _journal("decision.decline")[0].output_ref["on_behalf_of"] == ABSENT


def test_the_absent_approver_may_still_act_first(fresh):
    _engineer_covers()
    _submit()
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": RATIONALE, "reviewed": True}, "approver")
    assert r["ok"] and "on_behalf_of" not in r["output"], r
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": RATIONALE, "reviewed": True}, "engineer")
    assert not r["ok"] and r["error"]["code"] in ("conflict", "duplicate"), r


def test_delegate_stays_within_their_own_limit(fresh):
    _engineer_covers()
    assert call("access.setLimit", {"role": "Approver", "amount": 5000}, "admin")["ok"]
    _submit()
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": RATIONALE, "reviewed": True}, "engineer")
    assert not r["ok"] and r["error"]["code"] == "limit_exceeded", r


def test_inactive_or_accountless_delegations_change_nothing(fresh):
    # outside its dates
    _engineer_covers("2026-11-01", "2026-11-30")
    _submit()
    assert _case("RT-1048", "planner-a")["next"]["label"] == "Waiting for an Approver"
    assert "cover" not in _cmd("inbox", "engineer")
    # the seeded deputy has no sign-in account: recorded, but nobody can act for the Approver
    assert call("access.clearOutOfOffice", {"index": 0}, "admin")["ok"]
    assert call("access.setOutOfOffice", {"to": "dep-ap", "from": "2026-10-01", "until": "2026-10-31"}, "admin")["ok"]
    assert _case("RT-1048", "planner-a")["next"]["label"] == "Waiting for an Approver"
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": RATIONALE, "reviewed": True}, "engineer")
    assert r["ok"] and "on_behalf_of" not in r["output"], r


def test_admin_deciding_ignores_the_delegation(fresh):
    _engineer_covers()
    assert call("access.setDelegation", {"k": "decisions", "on": False}, "admin")["ok"]
    _submit()
    assert _case("RT-1048", "planner-a")["next"]["label"] == "Waiting for Admin"
    assert "cover" not in _cmd("inbox", "admin")
