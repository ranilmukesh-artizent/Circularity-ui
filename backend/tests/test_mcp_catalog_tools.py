"""P9-2.13: MCP tools generated from the action catalogue (di.mcp.catalog_tools), in process (no HTTP): the tool list
of a named agent, the hints, the forbidden list, a held call and the unchanged list without X-Agent."""

from types import SimpleNamespace

import anyio
import pytest
from sqlalchemy import text
from starlette.datastructures import Headers

from di.core import state
from di.core.db import SessionLocal
from di.mcp import server
from di.mcp.catalog_tools import tools_for
from di.mcp.policy import Caller, call_tool
from di.mcp.tools import TOOLS
from di.services.actions.registry import ACTIONS
from di.services.agents import catalog, registry
from tests import starting
from tests.helpers import call, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
AGENT = "cat-agent"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def register(tools: list[str], autonomy: str = "propose") -> registry.Agent:
    r = call("agent.register", {"id": AGENT, "name": "Catalogue agent", "tools": tools, "autonomy": autonomy}, "admin")
    assert r["ok"] is True, r
    with SessionLocal() as s:
        a = registry.get(s, AGENT)
    assert a is not None
    return a


def tool(user: str, name: str, args: dict, tenant: str | None = None) -> dict:
    token = h(user)["Authorization"].split(" ", 1)[1]
    with SessionLocal() as s:
        return call_tool(s, Caller(token, AGENT, tenant), name, args)


def test_mcp_catalog_tools_listed_for_agent():  # P9-2.13
    a = register(["case.evidence", "evidence.request"])
    assert {t.name for t in tools_for(a)} == {"case_evidence", "evidence_request", "tools_find"}


def test_mcp_catalog_never_lists_forbidden():  # P9-2.13, R16
    with SessionLocal() as s:
        agents = registry.all_agents(s)
    assert agents
    for a in agents:
        names = {t.name for t in tools_for(a)}
        bad = [i for i, d in ACTIONS.items() if catalog.tool_name(i) in names and not catalog.agent_allowed(d)]
        assert not bad, (a.id, bad)
    # a forbidden action written straight into an agent's tool list (past agent.register) still is no tool
    register(["case.evidence"])
    with SessionLocal() as s:
        s.execute(
            text("UPDATE agent_identity SET tools = CAST(:t AS text[]) WHERE id = :i"),
            {"t": ["case.evidence", "decision.approve", "scenario.delete", "flow.discard", "access.grant"], "i": AGENT},
        )
        s.commit()
        row = registry.get(s, AGENT)
    assert row is not None
    assert {t.name for t in tools_for(row)} == {"case_evidence", "tools_find"}
    a = tool("admin", "decision_approve", {"case_id": "RT-1048"})
    assert a["ok"] is False and a["error"]["code"] in ("not_found", "out_of_scope")


def test_mcp_catalog_call_runs_pipeline_and_holds():  # P9-2.13
    register(["case.evidence", "evidence.request"], "propose")
    a = tool("planner-a", "evidence_request", {"case_id": "RT-1051"})
    assert a["ok"] is False and a["outcome"] == "held for approval", a
    assert a["error"]["code"] == "held" and isinstance(a["error"]["proposal"], int)
    with SessionLocal() as s:
        row = s.execute(
            text("SELECT status, agent, action FROM agent_proposal WHERE id = :i"), {"i": a["error"]["proposal"]}
        ).one()
        assert tuple(row) == ("pending", AGENT, "evidence.request")
        assert any(c["tool"] == "evidence_request" and c["outcome"] == "held for approval" for c in state.items(s, "mcp_calls"))


def test_mcp_catalog_read_call_and_find():  # P9-2.13
    register(["case.evidence"], "read")
    r = tool("planner-a", "case_evidence", {"case_id": "RT-1048"})
    assert r["ok"] is True and r["outcome"] == "ok" and r["result"]["items"]
    f = tool("planner-a", "tools_find", {"query": "evidence"})
    assert f["ok"] is True and "evidence.request" in {t["action"] for t in f["result"]["tools"]}
    no = tool("planner-a", "evidence_request", {"case_id": "RT-1051"})  # not in this agent's tools
    assert no["ok"] is False and no["error"]["code"] == "out_of_scope"


def test_mcp_catalog_hints():  # P9-2.13
    a = register(["case.evidence", "evidence.request", "tables.update"])
    by = {t.name: t for t in tools_for(a)}
    ev = by["case_evidence"]
    assert ev.annotations.read_only_hint is True and ev.annotations.destructive_hint is False
    assert ev.annotations.idempotent_hint is True and ev.meta["requiresHumanApproval"] is False
    assert by["evidence_request"].annotations.read_only_hint is False
    assert by["evidence_request"].meta["requiresHumanApproval"] is True  # a propose agent's write is held
    assert by["tables_update"].annotations.destructive_hint is True  # held for a person whatever the autonomy
    assert by["tools_find"].annotations.read_only_hint is True


def test_mcp_without_agent_unchanged():  # P9-2.13
    ctx = SimpleNamespace(request=SimpleNamespace(headers=Headers()))

    async def go(headers: Headers):
        ctx.request.headers = headers
        return [t.name for t in (await server.list_tools(ctx, None)).tools]  # type: ignore[arg-type]

    assert anyio.run(go, Headers()) == list(TOOLS) and len(TOOLS) == 12
    register(["case.evidence"])
    assert anyio.run(go, Headers({"x-agent": AGENT})) == ["case_evidence", "tools_find"]
