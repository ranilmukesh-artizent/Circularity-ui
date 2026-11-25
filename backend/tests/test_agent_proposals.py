"""Plan 8 MVP-11.4: proposals that hold for a person (edge case 26).

An agent registered with autonomy `propose` that calls a write does not run it: the pipeline stores a proposal and
answers {held: id}. A person with the held action's own permission (and the case in their tenants) accepts it, and
the action runs as that person, prepared by the agent; or rejects it. A decision.* commit is never held: the agent
gate refuses it, as before. Home lists the proposals a person may decide. The starting state is restored before and
after each test.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from tests import starting
from tests.helpers import call, client, h

AGENT = {"id": "ext-proposer", "name": "External proposer", "tools": ["request_missing_evidence"], "autonomy": "propose"}
EVIDENCE = {"case_id": "RT-1051"}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()
    assert call("agent.register", AGENT, "admin")["ok"] is True
    yield
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


def prepared(action: str, body: dict, user: str = "planner-a", **headers: str) -> dict:
    hdr = h(user) | {"X-Circularity-Preparer": "ext-proposer"} | headers
    return client.post(f"/api/actions/{action}", json=body, headers=hdr).json()


def journal(action: str) -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT actor, preparer FROM action_journal WHERE action = :a ORDER BY seq"), {"a": action})
        return [dict(r._mapping) for r in rows]


def proposal(pid: int) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_proposal WHERE id = :i"), {"i": pid}).mappings().one())


def held() -> int:
    r = prepared("evidence.request", EVIDENCE)
    assert r["ok"] is True and set(r["output"]) == {"held", "reasons"}, r
    return int(r["output"]["held"])


def test_propose_holds():
    pid = held()
    p = proposal(pid)
    assert (p["agent"], p["action"], p["input"], p["case_id"], p["status"]) == (
        "ext-proposer", "evidence.request", EVIDENCE, "RT-1051", "pending",
    )  # fmt: skip
    assert journal("evidence.request") == []  # nothing ran
    # reads are not held
    assert prepared("case.evidence", EVIDENCE)["output"].get("held") is None
    # Home lists it for a person who may decide it, and for the person the agent acted for as their own (they only
    # reject it: maker-checker, audit F3a); not for another tenant's planner
    mine = client.get("/api/screens/home/proposals", headers=h("admin")).json()
    assert [x["id"] for x in mine] == [pid] and mine[0]["agentName"] == "External proposer"
    [own] = client.get("/api/screens/home/proposals", headers=h("planner-a")).json()
    assert own["id"] == pid and own["own"] is True  # listed, but only to reject: accept refuses them
    assert client.get("/api/screens/home/proposals", headers=h("planner-b")).json() == []


def test_accept_runs_as_person():
    pid = held()
    assert call("proposal.accept", {"id": pid}, "planner-a")["error"]["code"] == "conflict"  # the agent acted for them
    r = call("proposal.accept", {"id": pid}, "admin")
    assert r["ok"] is True and r["output"]["status"] == "accepted" and r["output"]["output"]["ref"].startswith("WO-")
    assert journal("evidence.request") == [{"actor": "admin", "preparer": "ext-proposer"}]
    p = proposal(pid)
    assert (p["status"], p["decided_by"], p["requested_by"]) == ("accepted", "admin", "planner-a")
    assert p["result"]["output"]["ref"].startswith("WO-")
    assert call("proposal.accept", {"id": pid}, "admin")["error"]["code"] == "conflict"


def test_accept_needs_permission():
    pid = held()
    r = call("proposal.accept", {"id": pid}, "executive")
    assert r["error"]["code"] == "out_of_scope", r
    r = call("proposal.accept", {"id": pid}, "planner-b")  # the held action's tenant boundary, as the person
    assert r["error"]["code"] == "tenant_boundary", r
    assert proposal(pid)["status"] == "pending"
    # an agent cannot accept a proposal, even a confirmed call
    r = prepared("proposal.accept", {"id": pid}, **{"X-Circularity-Confirmed": "true"})
    assert r["error"]["code"] == "approval_required"


def test_reject():
    pid = held()
    assert call("proposal.reject", {"id": pid, "reason": "no"}, "planner-a")["error"]["code"] == "validation_error"
    r = call("proposal.reject", {"id": pid, "reason": "Inspection already booked."}, "planner-a")
    assert r["ok"] is True and r["output"] == {"id": pid, "status": "rejected"}
    p = proposal(pid)
    assert (p["status"], p["result"]) == ("rejected", {"reason": "Inspection already booked."})
    assert journal("evidence.request") == []
    assert call("proposal.accept", {"id": pid}, "planner-a")["error"]["code"] == "conflict"


def test_decision_actions_never_held_but_refused():
    body = {"case_id": "RT-1048", "rationale": "Redeploy to Site 3 as recommended.", "reviewed": True}
    r = prepared("decision.approve", body, "approver")
    assert r["error"] == {
        "code": "approval_required",
        "message": "Decisions are approved, overridden or declined only in the approval card, by a person.",
    }
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM agent_proposal")).scalar_one() == 0
