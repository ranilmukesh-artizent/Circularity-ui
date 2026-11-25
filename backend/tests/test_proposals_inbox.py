"""Gaps-B: the agents' proposals on Home ("Proposals for you"), for every account that may act on one.

GET /api/screens/home/proposals lists the pending proposals the signed-in person may decide: they hold the held
action's own permission and the case is in their tenants (and warehouse). A proposal on a case the server cannot
place is never listed (fail closed). Each row says what the agent proposes, for which case, why and when. Accepting
runs the held action as the accepting person, with that person's permissions; the journal names them. Holding a
proposal emits a journal event, so the live stream refreshes Home. The starting state is restored around each test.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from tests import starting
from tests.helpers import call, client, h

AGENT = {"id": "ext-inbox", "name": "Inbox proposer", "tools": ["request_missing_evidence"], "autonomy": "propose"}
CASE = "RT-1051"  # Customer A


def _clear() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clear()
    assert call("agent.register", AGENT, "admin")["ok"] is True
    yield
    starting.reset()
    _clear()


def held(user: str = "planner-a", case_id: str = CASE) -> int:
    hdr = h(user) | {"X-Circularity-Preparer": AGENT["id"]}
    r = client.post("/api/actions/evidence.request", json={"case_id": case_id}, headers=hdr).json()
    assert r["ok"] is True and set(r["output"]) == {"held", "reasons"}, r
    return int(r["output"]["held"])


def inbox(user: str) -> list[dict]:
    r = client.get("/api/screens/home/proposals", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def insert(action: str, case_id: str | None, i: dict) -> int:
    """A pending proposal as an agent run would leave it (for shapes the pipeline cannot produce today)."""
    import json

    with SessionLocal() as s:
        pid = s.execute(
            text(
                "INSERT INTO agent_proposal (agent, action, input, case_id, status, created_at) "
                "VALUES (:a, :act, CAST(:i AS jsonb), :c, 'pending', now()) RETURNING id"
            ),
            {"a": AGENT["id"], "act": action, "i": json.dumps(i), "c": case_id},
        ).scalar_one()
        s.commit()
        return int(pid)


def test_row_says_what_for_which_case_why_and_when():
    pid = held()
    [p] = inbox("planner-a")
    assert p["id"] == pid and p["agentName"] == "Inbox proposer" and p["action"] == "evidence.request"
    assert p["title"] == "Request evidence" and p["case_id"] == CASE and p["at"]
    # why: the action's own purpose when the agent gave no reason
    assert p["why"].startswith("Ask the owning system or team for missing evidence")


def test_why_is_the_agents_reason_when_it_gave_one():
    pid = insert("evidence.request", CASE, {"case_id": CASE, "reason": "The inspection report is missing."})
    [p] = [x for x in inbox("planner-a") if x["id"] == pid]
    assert p["why"] == "The inspection report is missing."


def test_listed_only_for_accounts_that_may_act():
    pid = held()
    assert [x["id"] for x in inbox("planner-a")] == [pid]
    assert [x["id"] for x in inbox("admin")] == [pid]  # every tenant, every permission
    assert inbox("planner-b") == []  # another tenant: the tenant boundary
    assert inbox("executive") == []  # no permission to request evidence
    # what the list says matches what accept allows
    for user in ("planner-b", "executive"):
        assert call("proposal.accept", {"id": pid}, user)["ok"] is False


def test_unplaceable_case_or_unknown_action_is_never_listed():
    insert("evidence.request", "RT-0000", {"case_id": "RT-0000"})  # no such case: fail closed
    insert("no.such.action", None, {})
    assert inbox("admin") == [] and inbox("planner-a") == []


def test_accept_runs_as_the_accepting_person():
    pid = held("planner-a")
    r = call("proposal.accept", {"id": pid}, "admin")
    assert r["ok"] is True, r
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT actor, role, preparer FROM action_journal WHERE action = 'evidence.request' ORDER BY seq")
        ).all()
        decided = s.execute(text("SELECT decided_by FROM agent_proposal WHERE id = :i"), {"i": pid}).scalar_one()
    assert [tuple(x) for x in rows] == [("admin", "Admin", AGENT["id"])]
    assert decided == "admin"
    assert inbox("planner-a") == [] and inbox("admin") == []  # decided: off every inbox


def test_accept_checks_the_accepting_persons_permissions_not_the_preparers():
    # planner-a (Customer A) let the agent prepare it; planner-b cannot run it on a Customer A case
    pid = held("planner-a")
    r = call("proposal.accept", {"id": pid}, "planner-b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    r = call("proposal.reject", {"id": pid, "reason": "Not my tenant at all."}, "planner-b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM agent_proposal WHERE id = :i"), {"i": pid}).scalar_one() == "pending"


def test_holding_emits_a_journal_event_for_the_live_stream():
    pid = held()
    with SessionLocal() as s:
        ev = s.execute(
            text("SELECT type, case_id, payload FROM domain_event WHERE type = 'proposal.held' ORDER BY id DESC LIMIT 1")
        ).one()
        streamed = s.execute(
            text("SELECT kind, tenant FROM stream_event WHERE kind = 'journal' AND payload->>'type' = 'proposal.held'")
        ).all()
    assert ev.case_id == CASE and ev.payload == {"id": pid, "action": "evidence.request", "agent": AGENT["id"]}
    assert streamed and streamed[-1].tenant is not None  # filtered by the case's tenant on the stream
