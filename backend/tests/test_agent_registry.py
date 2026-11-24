"""Plan 8 MVP-11.3: the agent registry at runtime (table agent_identity).

- the demo's nine agents are seeded (internal, each with its own tools);
- Admin registers an external agent (agent.register) and it calls a read tool over MCP; nobody else may register;
- an agent that is not registered is refused, by the MCP server and by the action pipeline;
- an agent's org scope limits the cases it reaches (edge case 25);
- agent.setEnabled and agent.update write the row.
The starting state is restored before and after each test (registered agents removed, every agent started).
"""

import pytest

from di.core import golden
from di.core.db import SessionLocal
from di.mcp.policy import FORBIDDEN_ACTIONS, Caller, call_tool
from di.services.agents import registry
from tests import starting
from tests.helpers import call, client, h

EXT = {"id": "ext-copilot", "name": "External copilot", "tools": ["get_case_evidence"], "autonomy": "read"}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def tool(user: str, agent: str, name: str, args: dict, tenant: str | None = None) -> dict:
    token = h(user)["Authorization"].split(" ", 1)[1]
    with SessionLocal() as s:
        return call_tool(s, Caller(token, agent, tenant), name, args)


def prepared(action: str, body: dict, user: str, agent: str) -> dict:
    return client.post(f"/api/actions/{action}", json=body, headers=h(user) | {"X-Circularity-Preparer": agent}).json()


UNBUILT = {"analytics.query", "audit.search", "sources.health", "mapping.suggest", "tables.suggestLinks", "import.clean"}


def test_seeded_agents():
    with SessionLocal() as s:
        got = {a.id: a for a in registry.all_agents(s)}
    want = golden.load("tools")["agents"]
    assert set(got) == {a["id"] for a in want} | {"ask"}
    for a in want:
        g = got[a["id"]]
        assert (g.name, g.kind, g.tools, g.enabled, g.org_scope, g.autonomy) == (
            a["name"],
            "internal",
            [t for t in a["tools"] if t not in UNBUILT],  # P9-0.4: migration 0029 drops the tools with no handler
            True,
            [],
            "act",
        )
    ask = got["ask"]  # Ask Circularity's read tools run as this agent; it changes nothing
    assert (ask.name, ask.kind, ask.tools, ask.autonomy) == ("Ask Circularity", "internal", [], "read")


def test_register_external_agent_and_call_read_tool():
    assert call("agent.register", EXT, "planner-a")["error"]["code"] == "out_of_scope"
    r = call("agent.register", EXT, "admin")
    assert r["ok"] is True and r["output"] == {"id": "ext-copilot"}
    with SessionLocal() as s:
        a = registry.get(s, "ext-copilot")
    assert a is not None and (a.kind, a.autonomy, a.created_by) == ("external", "read", "admin")
    assert call("agent.register", EXT, "admin")["error"]["code"] == "duplicate"
    ok = tool("planner-a", "ext-copilot", "get_case_evidence", {"case_id": "RT-1048"})
    assert ok["ok"] is True and ok["agent"] == "ext-copilot" and ok["result"]["case_id"] == "RT-1048"
    no = tool("planner-a", "ext-copilot", "find_demand", {"case_id": "RT-1048"})
    assert no["error"]["code"] == "out_of_scope"
    # a read-only agent changes nothing, even through the pipeline
    w = prepared("evidence.request", {"case_id": "RT-1051"}, "planner-a", "ext-copilot")
    assert w["error"] == {"code": "out_of_scope", "message": "External copilot may only read."}


def test_agents_never_reach_access_or_outbound_settings():
    """AGENTS.md rule 10 / plan R7: the registry's and the org's settings are actions no agent may run."""
    for a in ("agent.register", "agent.update", "agent.setEnabled", "org.setPilot", "org.create", "decision.approve"):
        assert a.startswith(FORBIDDEN_ACTIONS), a


def test_register_refuses_unknown_tools_and_orgs():
    bad = call("agent.register", {**EXT, "tools": ["drop_tables"]}, "admin")
    assert bad["error"] == {"code": "validation_error", "message": "Unknown tools: drop_tables."}
    bad = call("agent.register", {**EXT, "org_scope": ["Nowhere"]}, "admin")
    assert bad["error"] == {"code": "validation_error", "message": "Unknown org units: Nowhere."}


def test_unknown_agent_refused():
    a = tool("planner-a", "nobody", "get_case_evidence", {"case_id": "RT-1048"})
    assert a["error"]["code"] == "out_of_scope" and "X-Agent" in a["error"]["message"]
    r = prepared("case.evidence", {"case_id": "RT-1048"}, "planner-a", "nobody")
    assert r["error"] == {"code": "out_of_scope", "message": "Unknown agent nobody. Admin registers agents in Agents."}


def test_org_scope_limits_cases():
    assert call("agent.register", {**EXT, "org_scope": ["Customer A"]}, "admin")["ok"] is True
    # admin may see every tenant; the agent only Customer A
    assert tool("admin", "ext-copilot", "get_case_evidence", {"case_id": "RT-1048"}, "Customer A")["ok"] is True
    b = tool("admin", "ext-copilot", "get_case_evidence", {"case_id": "RT-1001"}, "Customer B")
    assert b["error"] == {"code": "tenant_boundary", "message": "External copilot is not scoped for Customer B."}
    r = prepared("case.evidence", {"case_id": "RT-1001"}, "admin", "ext-copilot")
    assert r["error"] == {
        "code": "tenant_boundary",
        "message": "RT-1001 belongs to Customer B, outside the org scope of External copilot.",
    }
    assert prepared("case.evidence", {"case_id": "RT-1048"}, "admin", "ext-copilot")["ok"] is True
    # widening the scope to the root covers every org below it
    assert call("agent.update", {"id": "ext-copilot", "org_scope": ["workspace"]}, "admin")["ok"] is True
    assert prepared("case.evidence", {"case_id": "RT-1001"}, "admin", "ext-copilot")["ok"] is True


def test_kill_switch_and_update_write_the_row():
    assert call("agent.register", EXT, "admin")["ok"] is True
    assert call("agent.setEnabled", {"id": "ext-copilot", "on": False}, "admin")["ok"] is True
    with SessionLocal() as s:
        assert registry.get(s, "ext-copilot").enabled is False
    stopped = tool("planner-a", "ext-copilot", "get_case_evidence", {"case_id": "RT-1048"})
    assert stopped["error"]["message"] == "External copilot is stopped by Admin, so it cannot prepare anything."
    u = call("agent.update", {"id": "ext-copilot", "enabled": True, "autonomy": "propose", "tools": []}, "admin")
    assert u["ok"] is True and (u["output"]["enabled"], u["output"]["autonomy"], u["output"]["tools"]) == (True, "propose", [])
    assert call("agent.update", {"id": "nobody"}, "admin")["error"] == {"code": "not_found", "message": "Unknown agent."}
