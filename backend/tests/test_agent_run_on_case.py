"""Gap 15 of the 2026-11-26 UI audit: a Planner or Approver runs the case autopilot on a case of their tenants
(agent.startRun, permission runAgent). The run only prepares: every write it makes holds for a person
(proposals.run_holds), whatever the agent's own autonomy is. Other playbooks and other roles stay refused."""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import proposals
from tests import starting
from tests.helpers import call

AGENT = {"id": "ext-autopilot", "name": "Autopilot", "tools": [], "autonomy": "act"}
CASE_A, CASE_B = "RT-1002", "RT-1001"  # Customer A, Customer B


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


def _holds(run_id: str) -> bool:
    with SessionLocal() as s:
        return proposals.run_holds(s, run_id)


def test_planner_runs_propose_only():
    r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE_A}, "planner-a")
    assert r["ok"] is True, r
    assert _holds(r["output"]["run_id"]) is True  # an agent that acts alone still only holds for this run


def test_admin_run_is_not_forced_to_hold():
    r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE_A}, "admin")
    assert r["ok"] is True, r
    assert _holds(r["output"]["run_id"]) is False


def test_other_tenants_planner_is_refused():
    r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE_B}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r


def test_planner_may_not_start_another_playbook():
    r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE_A, "playbook": "stage_chain"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r


def test_executive_and_developer_are_refused():
    for user in ("executive", "developer"):
        r = call("agent.startRun", {"agent": AGENT["id"], "case_id": CASE_A}, user)
        assert r["ok"] is False and r["error"]["code"] == "out_of_scope", (user, r)
