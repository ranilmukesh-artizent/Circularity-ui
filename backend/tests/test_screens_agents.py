"""Plan 8 MVP-11.8: the Agents page's endpoint (GET /api/screens/agents) and its menu entry.

The page shows the agent registry (Admin edits it with agent.update), the agent runs with their steps and what a
waiting run waits for, the proposals the signed-in person may accept or reject, and the tool catalogue. Admin and
Developer open it; only Admin manages agents. The starting state is restored before and after each test.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import runtime
from di.services.agents.catalog import catalog
from tests import starting
from tests.helpers import client, h

URL = "/api/screens/agents"
AGENT = {"id": "ext-autopilot", "name": "Autopilot", "tools": ["get_case_evidence"], "autonomy": "propose"}
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
    yield
    starting.reset()
    _clean()


def _get(acct: str):
    return client.get(URL, headers=h(acct))


def _held_run() -> tuple[str, int]:
    """An autopilot run of a propose-only agent, driven until it holds its decision.submit for a person."""
    r = client.post("/api/actions/agent.register", json=AGENT, headers=h("admin")).json()
    assert r["ok"] is True, r
    with SessionLocal() as s:
        run_id = runtime.start(s, AGENT["id"], "case_autopilot", CASE, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
        pid = int(s.execute(text("SELECT state->>'proposal' FROM agent_run WHERE id = :i"), {"i": run_id}).scalar_one())
    return run_id, pid


def test_admin_sees_registry_runs_proposals_and_tools():
    run_id, pid = _held_run()
    r = _get("admin")
    assert r.status_code == 200, r.text
    out = r.json()
    kinds = [a["kind"] for a in out["agents"]]
    assert kinds == ["internal"] * (len(kinds) - 1) + ["external"]  # the seeded agents, then the registered one
    a = out["agents"][-1]
    assert (a["id"], a["name"]) == ("ext-autopilot", "Autopilot")
    assert (a["kind"], a["autonomy"], a["enabled"], a["tools"], a["org_scope"]) == (
        "external", "propose", True, ["get_case_evidence"], [],
    )  # fmt: skip
    assert "Customer A" in out["orgs"] and "workspace" in out["orgs"]
    assert "get_case_evidence" in out["mcp_tools"]
    assert out["can"] == {"manage": True}

    (run,) = out["runs"]
    assert (run["id"], run["agent"], run["agentName"], run["playbook"], run["case_id"], run["status"]) == (
        run_id, "ext-autopilot", "Autopilot", "case_autopilot", CASE, "waiting",
    )  # fmt: skip
    assert run["waiting"] == {"kind": "proposal", "proposal": pid}
    assert run["steps"][0]["tool"] == "case.evidence" and run["steps"][0]["ok"] is True
    last = run["steps"][-1]
    assert (last["tool"], last["ok"], last["note"]) == ("decision.submit", True, f"Held for a person as proposal {pid}.")
    assert [s["n"] for s in run["steps"]] == list(range(1, len(run["steps"]) + 1))

    (p,) = out["proposals"]
    want = (pid, "ext-autopilot", "decision.submit", CASE, run_id)
    assert (p["id"], p["agent"], p["action"], p["case_id"], p["run_id"]) == want

    assert [t["action"] for t in out["tools"]] == [t["action"] for t in catalog()]
    approve = next(t for t in out["tools"] if t["action"] == "decision.approve")
    assert approve["agent_allowed"] is False


def test_run_waiting_for_approval_links_the_case():
    run_id, pid = _held_run()
    assert client.post("/api/actions/proposal.accept", json={"id": pid}, headers=h("planner-a")).json()["ok"] is True
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
    (run,) = _get("admin").json()["runs"]
    assert run["status"] == "waiting" and run["waiting"] == {"kind": "approval", "case_id": CASE}
    assert _get("admin").json()["proposals"] == []


def test_developer_reads_without_managing():
    r = _get("developer")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["can"] == {"manage": False} and {a["kind"] for a in out["agents"]} == {"internal"}


@pytest.mark.parametrize("acct", ["planner-a", "approver", "executive", "wm-1"])
def test_other_roles_refused(acct):
    r = _get(acct)
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"


@pytest.mark.parametrize("acct", ["admin", "developer", "planner-a"])
def test_nav_lists_agents_after_mcp(acct):
    groups = client.get("/api/screens/nav", headers=h(acct)).json()["groups"]
    got = [g for g in groups if g["id"] == "agents"]
    if acct == "planner-a":
        assert got == []
        return
    assert got == [{"id": "agents", "label": "Agents", "sub": "Registry, runs, proposals and tools", "icon": "bot",
                    "section": "More", "leaf": True, "href": "#/agents", "kids": []}]  # fmt: skip
    ids = [g["id"] for g in groups]
    assert ids[ids.index("agents") - 1] == "mcp"


def test_session_lists_the_agents_page():
    assert client.get("/api/auth/me", headers=h("developer")).json()["pages"]["agents"] == []
    assert "agents" not in client.get("/api/auth/me", headers=h("planner-a")).json()["pages"]
