"""B17: Admin's agent-first settings in Access (the demo's AF.cfg): approval limits, self-approval, autonomy, the
per-agent kill switch and run limits. Each is allowed for Admin, refused for everyone else, shows in the Access
page's reads, and changes the rule that uses it (decision.approve for the limits and self-approval, the MCP server
for the kill switch). The starting state is restored before and after each test.
"""

import pytest
from sqlalchemy import text

from di.db import SessionLocal
from di.mcp.policy import Caller, call_tool
from tests import starting
from tests.test_writes_decisions import call, client, h

APPROVE = {"case_id": "RT-1048", "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def page(section: str) -> dict:
    r = client.get("/api/screens/access", headers=h("admin"))
    assert r.status_code == 200, r.text
    return r.json()[section]


def journaled(action: str) -> list[str]:
    """Who the journal says did this action."""
    with SessionLocal() as s:
        return list(s.execute(text("SELECT actor FROM action_journal WHERE action = :a ORDER BY seq"), {"a": action}).scalars())


@pytest.mark.parametrize(
    "action, body",
    [
        ("access.setLimit", {"role": "Approver", "amount": 1000}),
        ("access.setSelfApprove", {"on": True}),
        ("access.setAutonomy", {"role": "Planner", "type": "evidence", "level": "act"}),
        ("agent.setEnabled", {"id": "assembler", "on": False}),
        ("access.setRunLimits", {"actions": 10, "bulk": 20}),
    ],
)
def test_only_admin_may_change_the_settings(action, body):
    for user in ("approver", "planner-a", "developer", "executive"):
        r = call(action, body, user)
        assert r["ok"] is False and r["error"]["code"] == "out_of_scope", (user, r)
    assert call(action, body, "admin")["ok"] is True
    assert journaled(action) == ["admin"]  # refusals are not journaled; the change is


# ---------------------------------------------------------------- approval limits and self-approval
def test_approval_limit_is_read_back_and_applies_to_decision_approve():
    r = call("access.setLimit", {"role": "Approver", "amount": 1000}, "admin")
    assert r == {**r, "ok": True, "output": {"role": "Approver", "limit": 1000}}
    assert page("limits")["limits"]["Approver"] == 1000
    refused = call("decision.approve", APPROVE, "approver")
    assert refused["ok"] is False and refused["error"]["code"] == "limit_exceeded"
    assert "above your approval limit of $1,000. It escalates to Admin." in refused["error"]["message"]
    assert refused["error"]["escalate"] == "admin"
    # back to unlimited: the same approval goes through
    assert call("access.setLimit", {"role": "Approver", "amount": None}, "admin")["output"] == {"role": "Approver", "limit": None}
    assert page("limits")["limits"]["Approver"] is None
    assert call("decision.approve", APPROVE, "approver")["ok"] is True


def test_limit_guards():
    assert call("access.setLimit", {"role": "Nobody", "amount": 5}, "admin")["error"] == {"code": "not_found", "message": "Unknown role."}
    bad = call("access.setLimit", {"role": "Planner", "amount": -1}, "admin")["error"]
    assert bad == {"code": "validation_error", "message": "A limit cannot be negative."}


def test_a_planner_limit_lets_planners_approve_and_self_approval_is_a_separate_rule():
    assert call("decision.approve", APPROVE, "planner-a")["error"]["code"] == "out_of_scope"  # $0: cannot approve
    assert call("access.setLimit", {"role": "Planner", "amount": 10_000_000}, "admin")["ok"]
    me = client.get("/api/auth/me", headers=h("planner-a")).json()
    assert "approve.decisions" in me["permissions"]
    assert call("decision.submit", {"case_id": "RT-1048"}, "planner-a")["ok"]
    own = call("decision.approve", APPROVE, "planner-a")
    assert own["ok"] is False and own["error"]["code"] == "out_of_scope" and "another person must approve" in own["error"]["message"]
    r = call("access.setSelfApprove", {"on": True}, "admin")
    assert r["output"] == {"on": True} and page("limits")["self_approve"] is True
    assert call("decision.approve", APPROVE, "planner-a")["ok"] is True
    assert call("access.setSelfApprove", {"on": False}, "admin")["output"] == {"on": False}
    assert page("limits")["self_approve"] is False


# ---------------------------------------------------------------- autonomy
def test_autonomy_is_read_back_and_capped_by_the_risk_tier():
    r = call("access.setAutonomy", {"role": "Planner", "type": "evidence", "level": "act"}, "admin")
    assert r["output"] == {"role": "Planner", "type": "evidence", "level": "act"}
    m = page("autonomy")["matrix"]
    assert m["Planner"]["evidence"] == "act" and m["Planner"]["notify"] == "prepare" and m["Approver"]["evidence"] == "prepare"
    capped = call("access.setAutonomy", {"role": "Planner", "type": "decisions", "level": "act"}, "admin")["error"]
    assert capped["code"] == "conflict"
    assert capped["message"] == "Approve, override or decline decisions; confirm outcomes is capped at Prepare by its risk tier."
    assert call("access.setAutonomy", {"role": "X", "type": "evidence", "level": "off"}, "admin")["error"]["message"] == "Unknown role."
    assert call("access.setAutonomy", {"role": "Planner", "type": "x", "level": "off"}, "admin")["error"]["message"] == "Unknown action type."
    assert call("access.setAutonomy", {"role": "Planner", "type": "evidence", "level": "x"}, "admin")["error"]["code"] == "validation_error"


# ---------------------------------------------------------------- kill switch
def _evidence(user: str, agent: str) -> dict:
    token = h(user)["Authorization"].split(" ", 1)[1]
    with SessionLocal() as s:
        return call_tool(s, Caller(token, agent, None), "get_case_evidence", {"case_id": "RT-1048"})


def test_a_stopped_agent_is_refused_by_the_mcp_server_until_started_again():
    assert _evidence("planner-a", "assembler")["ok"] is True
    assert call("agent.setEnabled", {"id": "assembler", "on": False}, "admin")["output"] == {"id": "assembler", "on": False}
    rows = {a["id"]: a for a in page("agentsx")["agents"]}
    assert rows["assembler"]["stopped"] is True and rows["finder"]["stopped"] is False
    a = _evidence("planner-a", "assembler")
    assert a["ok"] is False and a["error"] == {
        "code": "out_of_scope",
        "message": "Evidence Assembler is stopped by Admin, so it cannot prepare anything.",
    }
    assert call("agent.setEnabled", {"id": "assembler", "on": True}, "admin")["ok"]
    assert {a["id"]: a for a in page("agentsx")["agents"]}["assembler"]["stopped"] is False
    assert _evidence("planner-a", "assembler")["ok"] is True
    assert call("agent.setEnabled", {"id": "intruder", "on": False}, "admin")["error"] == {"code": "not_found", "message": "Unknown agent."}


# ---------------------------------------------------------------- run limits
def test_run_limits_are_read_back_and_bounded():
    assert page("limits")["run_limits"] == {"actions": 50, "bulk": 100}
    assert call("access.setRunLimits", {"actions": 10, "bulk": 20}, "admin")["output"] == {"actions": 10, "bulk": 20}
    assert page("limits")["run_limits"] == {"actions": 10, "bulk": 20}
    for body in ({"actions": 0, "bulk": 20}, {"actions": 10, "bulk": 1001}, {"actions": 501, "bulk": 1}):
        r = call("access.setRunLimits", body, "admin")
        assert r["error"] == {"code": "validation_error", "message": "Use 1–500 actions and 1–1,000 items."}
    assert page("limits")["run_limits"] == {"actions": 10, "bulk": 20}
