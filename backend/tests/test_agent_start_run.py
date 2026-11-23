"""MVP-12.4: Admin starts an agent's playbook on a case from the Agents page (agent.startRun).

    agent.startRun  act  {agent, case_id, playbook?}   manageAgents (Admin); the run acts as the person who started it

The runtime (di.services.agents.runtime, MVP-11.5) had no way in: nothing called runtime.start. The test plays the
worker (runtime.run_until_blocked), as tests/test_agent_runtime.py does. The starting state is restored around each
test.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import runtime
from tests import starting
from tests.helpers import call

AGENT = {"id": "ext-autopilot", "name": "Autopilot", "tools": [], "autonomy": "propose"}
CASE = "RT-1048"


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
    assert call("agent.register", AGENT, "admin")["ok"] is True
    yield
    starting.reset()
    _clean()


def _run(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def test_admin_starts_autopilot_run():
    r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE}, "admin")
    assert r["ok"] is True, r
    run_id = r["output"]["run_id"]
    assert r["output"] == {"run_id": run_id, "agent": AGENT["id"], "playbook": "case_autopilot", "case_id": CASE}
    row = _run(run_id)
    assert (row["agent"], row["playbook"], row["case_id"], row["status"]) == (AGENT["id"], "case_autopilot", CASE, "running")
    assert row["state"]["account"] == "admin"
    with SessionLocal() as s:
        q = text("SELECT count(*) FROM job WHERE kind = 'agent.step' AND status = 'queued' AND payload->>'run_id' = :i")
        assert s.execute(q, {"i": run_id}).scalar_one() == 1
        runtime.run_until_blocked(s, run_id)
    after = _run(run_id)
    assert after["status"] == "waiting" and after["state"]["waiting"] == "proposal"  # the submit is held for a person


def test_worker_runs_on_an_opened_case():
    """The worker's agent.step job reads a case's scope from the database, so a case opened from data (not one of the
    demo's golden cases) is live to the run, as it is to the api."""
    from di import worker
    from di.services.actions import scope

    facts = {"cls": "motor", "grade": "A", "age": 4, "qty": 1}
    body = {"org_unit_id": "Customer A", "template_key": "industrial", "asset_key": "T-AG-1", "reason": "rma", "facts": facts}
    opened = call("case.open", body, "planner-a")
    assert opened["ok"], opened
    cid = opened["output"]["case_id"]
    run_id = call("agent.startRun", {"agent": AGENT["id"], "case_id": cid}, "admin")["output"]["run_id"]
    api_provider = scope._provider  # the api's (the database); a fresh worker process starts on golden
    scope.set_provider(scope._golden)
    try:
        worker._agent_step({"run_id": run_id})  # the job handler, as the worker calls it
    finally:
        scope.set_provider(api_provider)
    row = _run(run_id)
    assert row["status"] == "waiting", row["state"]
    assert row["state"]["waiting"] == "proposal"


def test_only_admin_starts_runs():
    for user in ("planner-a", "developer"):
        r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE}, user)
        assert r["ok"] is False and r["error"]["code"] == "out_of_scope", (user, r)


def test_unknown_agent_or_playbook_refused():
    r = call("agent.startRun", {"agent": "nobody", "case_id": CASE}, "admin")
    assert r["error"]["code"] == "not_found", r
    r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE, "playbook": "nope"}, "admin")
    assert r["error"]["code"] == "validation_error", r
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM agent_run")).scalar_one() == 0
