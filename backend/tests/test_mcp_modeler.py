"""MVP-5.5: the Modeler's tools on the MCP server (get_decision_flow, propose_rule_change). They read: a proposal is
never applied, and no tool reaches flow.publish (or approve, reject, rollback). Over real HTTP, as test_mcp_server."""

from di.mcp.policy import FORBIDDEN_ACTIONS
from di.mcp.tools import ACTIONS_OF, MODELER_TOOLS
from tests import flowkit, starting
from tests.test_mcp_server import action, call, headers, with_client

AGENT = "flow-reader"


def setup_module():
    """No seeded agent gets the Modeler's tools (the demo's nine keep their scopes); an Admin registers one that has
    them, through agent.register (MVP-11.3). starting.reset removes it again."""
    starting.reset()
    flowkit.reset_flows()
    body = {"id": AGENT, "name": "Flow reader", "tools": list(MODELER_TOOLS), "autonomy": "read"}
    assert action("admin", "agent.register", body)["ok"] is True


def teardown_module():
    flowkit.reset_flows()
    starting.reset()


def test_mcp_lists_flow_tools():
    async def go(c):
        return {t.name: t for t in (await c.list_tools()).tools}

    everything = with_client(headers("admin"), go)
    assert {"get_decision_flow", "propose_rule_change"} <= set(everything)
    t = everything["get_decision_flow"]
    assert t.annotations.read_only_hint is True and t.meta["requiresHumanApproval"] is False
    assert t.input_schema["required"] == ["template"]
    assert everything["propose_rule_change"].input_schema["required"] == ["flow_id", "text"]
    assert list(with_client(headers("admin", AGENT), go)) == ["get_decision_flow", "propose_rule_change", "tools_find"]


def test_get_decision_flow_reads_the_flow():
    a = call("admin", AGENT, "get_decision_flow", {"template": "tool_fleet", "org": "workspace"})
    assert a["ok"] is True and a["outcome"] == "ok"
    r = a["result"]
    assert r["flow"]["name"] == "Tool fleet returns" and [x["id"] for x in r["compiled"]][:2] == ["BR-01", "BR-02"]
    b = call("planner-a", AGENT, "get_decision_flow", {"template": "industrial", "org": "Customer B"})
    assert b["ok"] is False and b["error"]["code"] == "tenant_boundary"


def test_an_agent_without_the_tools_is_refused():
    async def go(c):
        return [t.name for t in (await c.list_tools()).tools]

    assert not {"get_decision_flow", "propose_rule_change"} & set(with_client(headers("admin", "assembler"), go))
    a = call("admin", "assembler", "get_decision_flow", {"template": "industrial"})
    assert a["ok"] is False and a["error"]["code"] == "out_of_scope"


def test_mcp_propose_does_not_change_draft():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    a = call("admin", AGENT, "propose_rule_change", {"flow_id": fid, "text": "Never recycle construction lasers"})
    assert a["ok"] is True
    # This test talks over HTTP to the RUNNING api, whose model-first reader (flow.propose, ai-tasks I10) may use the dev
    # database's real key, so the reading is not repeatable: a rule (BR-03) or the model's one question. The exact
    # proposals are asserted in-process with a fake model (test_flow_propose_model.py). What holds either way: no change.
    r = a["result"]
    assert r["read_by"] in ("model", "rules") and r["kind"] in ("rule", "unclear")
    if r["kind"] == "rule":
        assert r["rid"] == "BR-03"
    f, versions = flowkit.get(fid)
    assert (f.status, f.draft, f.ver, versions) == ("pub", None, 1, [])


def test_mcp_cannot_publish():
    for a in ("flow.publish", "flow.approve", "flow.reject", "flow.rollback"):
        assert a.startswith(FORBIDDEN_ACTIONS), a
    reached = {a for acts in ACTIONS_OF.values() for a in acts}
    assert {"flow.get", "flow.propose"} <= reached
    assert not {a for a in reached if a.startswith("flow.") and a not in ("flow.get", "flow.propose")}
