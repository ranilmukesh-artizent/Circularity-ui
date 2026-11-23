"""Plan 8 MVP-11.5: the agent runtime runs the case autopilot playbook step by step through the action pipeline.

A run starts with an `agent.step` job; the test plays the worker (runtime.run_until_blocked). An agent with autonomy
`propose` holds its decision.submit for a person; accepting the proposal wakes the run (a new job); the run then waits
for the approval, which decision.approve wakes. The kill switch and the run limit stop a run. The starting state is
restored before and after each test.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import runtime
from tests import starting
from tests.helpers import call, client, h

AGENT = {"id": "ext-autopilot", "name": "Autopilot", "tools": [], "autonomy": "propose"}
CASE = "RT-1048"
APPROVE = {"case_id": CASE, "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True}


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def register(autonomy: str = "propose") -> None:
    assert call("agent.register", {**AGENT, "autonomy": autonomy}, "admin")["ok"] is True


def start() -> str:
    with SessionLocal() as s:
        run_id = runtime.start(s, "ext-autopilot", "case_autopilot", CASE, account="planner-a")
        s.commit()
    return run_id


def drive(run_id: str) -> dict:
    """The worker's agent.step job, then the run as it stands."""
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
        return run(run_id)


def run(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def steps(run_id: str) -> list[str]:
    with SessionLocal() as s:
        q = text("SELECT tool FROM agent_run_step WHERE run_id = :i ORDER BY n")
        return list(s.execute(q, {"i": run_id}).scalars())


def queued(run_id: str) -> int:
    with SessionLocal() as s:
        q = text("SELECT count(*) FROM job WHERE kind = 'agent.step' AND status = 'queued' AND payload->>'run_id' = :i")
        return int(s.execute(q, {"i": run_id}).scalar_one())


def test_autopilot_runs_to_hold():
    register()
    run_id = start()
    assert queued(run_id) == 1
    r = drive(run_id)
    assert r["status"] == "waiting" and r["state"]["waiting"] == "proposal"
    assert steps(run_id)[0] == "case.evidence" and steps(run_id)[-1] == "decision.submit"
    with SessionLocal() as s:
        p = s.execute(text("SELECT * FROM agent_proposal WHERE id = :i"), {"i": r["state"]["proposal"]}).mappings().one()
    assert (p["action"], p["run_id"], p["status"]) == ("decision.submit", run_id, "pending")


def test_accept_resumes():
    register()
    run_id = start()
    pid = drive(run_id)["state"]["proposal"]
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job"))
        s.commit()
    assert call("proposal.accept", {"id": pid}, "planner-a")["ok"] is True
    assert run(run_id)["status"] == "running" and queued(run_id) == 1
    r = drive(run_id)
    assert r["status"] == "waiting" and r["state"]["waiting"] == "approval"
    # the person approves in the approval card: the run wakes and finishes
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job"))
        s.commit()
    ap = client.post("/api/actions/decision.approve", json=APPROVE, headers=h("approver")).json()
    assert ap["ok"] is True, ap
    assert run(run_id)["status"] == "running" and queued(run_id) == 1
    assert drive(run_id)["status"] == "done"
    with SessionLocal() as s:
        q = text("SELECT actor, preparer, run_id FROM action_journal WHERE action = 'decision.submit'")
        assert [tuple(x) for x in s.execute(q)] == [("planner-a", "ext-autopilot", run_id)]


def test_rejected_proposal_stops_run():
    register()
    run_id = start()
    pid = drive(run_id)["state"]["proposal"]
    assert call("proposal.reject", {"id": pid, "reason": "Not this one, thanks."}, "planner-a")["ok"] is True
    assert run(run_id)["status"] == "stopped"


def test_stopped_agent_stops_run():
    register()
    run_id = start()
    with SessionLocal() as s:
        assert runtime.step(s, run_id) == "running"  # case.evidence
        s.commit()
    assert call("agent.setEnabled", {"id": "ext-autopilot", "on": False}, "admin")["ok"] is True
    r = drive(run_id)
    assert r["status"] == "stopped" and steps(run_id) == ["case.evidence"]


def test_run_limit_stops_run():
    register("act")  # no holds: the run calls the actions itself
    assert call("access.setRunLimits", {"actions": 1, "bulk": 100}, "admin")["ok"] is True
    run_id = start()
    # an action already journaled in this run uses its one allowed action
    hdr = h("planner-a") | {"X-Circularity-Preparer": "ext-autopilot", "X-Circularity-Run": run_id}
    assert client.post("/api/actions/evidence.request", json={"case_id": "RT-1051"}, headers=hdr).json()["ok"] is True
    r = drive(run_id)
    assert r["status"] == "stopped" and r["state"]["reason"] == "Run limit reached: 1 actions."
    assert steps(run_id) == ["case.evidence", "decision.submit"]


def test_unknown_playbook_and_agent_refused():
    register()
    with SessionLocal() as s, pytest.raises(ValueError, match="unknown playbook"):
        runtime.start(s, "ext-autopilot", "nope", CASE, account="planner-a")
    with SessionLocal() as s, pytest.raises(ValueError, match="unknown agent"):
        runtime.start(s, "nobody", "case_autopilot", CASE, account="planner-a")
