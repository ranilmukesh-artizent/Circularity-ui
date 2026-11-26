"""Plan 8 UI gaps (agent E): registering an agent from the Agents page, and model fit and promotion on a screen.

- agent.register and agent.update refuse a tool no agent may use (di.mcp.policy.FORBIDDEN_ACTIONS, system actions);
  Admin only (manageAgents); the new agent shows in the registry of GET /api/screens/agents.
- model.propose (new): a person proposes a candidate for promotion; model.promote needs that proposal and is refused to
  the model's maker and to its proposer (maker-checker). Agents never propose, promote or register.
- GET /api/screens/agents/models: the base model, the active model per template and every fitted model with its
  metrics, its proposal and, for the signed-in person, why they may not propose or approve it.
The starting state is restored before and after each test (no model versions, only the demo's agents).
"""

import pytest

from di.mcp.policy import FORBIDDEN_ACTIONS
from di.services.actions.models import MAKER_CHECKER, PROPOSER_CHECKER
from di.services.agents.catalog import catalog
from tests import starting
from tests.helpers import call, client, h

AGENTS = "/api/screens/agents"
MODELS = "/api/screens/agents/models"
TOOLS = ["get_case_evidence", "cases.list"]
EXT = {"id": "ext-helper", "name": "Helper", "kind": "external", "tools": TOOLS, "autonomy": "propose"}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


# ---------------------------------------------------------------- register an agent
def test_register_shows_in_registry():
    r = call("agent.register", EXT, "admin")
    assert r["ok"] is True, r
    out = client.get(AGENTS, headers=h("admin")).json()
    a = out["agents"][-1]
    assert (a["id"], a["name"], a["kind"], a["tools"], a["autonomy"], a["created_by"]) == (
        "ext-helper", "Helper", "external", ["get_case_evidence", "cases.list"], "propose", "admin",
    )  # fmt: skip


@pytest.mark.parametrize("acct", ["developer", "planner-a", "approver"])
def test_only_admin_registers(acct):
    assert call("agent.register", EXT, acct)["error"]["code"] == "out_of_scope"


@pytest.mark.parametrize("bad", ["decision.approve", "model.promote", "agent.register", "access.decideRequest", "flow.publish"])
def test_register_refuses_forbidden_tools(bad):
    r = call("agent.register", {**EXT, "tools": ["get_case_evidence", bad]}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == f"No agent may use: {bad}."


def test_update_refuses_forbidden_tools_but_keeps_seeded_ones():
    assert call("agent.register", EXT, "admin")["ok"] is True
    r = call("agent.update", {"id": "ext-helper", "tools": ["decision.override"]}, "admin")
    assert r["error"] == {"code": "validation_error", "message": "No agent may use: decision.override."}
    for a in client.get(AGENTS, headers=h("admin")).json()["agents"]:  # every seeded agent's tools stay allowed
        assert call("agent.update", {"id": a["id"], "tools": a["tools"]}, "admin")["ok"] is True, a["id"]


def test_new_actions_are_forbidden_to_agents():
    for a in ("agent.register", "model.promote", "model.propose"):
        assert a.startswith(FORBIDDEN_ACTIONS)
    allowed = {t["action"]: t["agent_allowed"] for t in catalog()}
    assert allowed["model.propose"] is False and allowed["agent.register"] is False


# ---------------------------------------------------------------- models
def _models(acct: str) -> dict:
    r = client.get(MODELS, headers=h(acct))
    assert r.status_code == 200, r.text
    return r.json()


def test_models_screen_empty():
    out = _models("admin")
    assert out["base"] == "v1.3"
    assert {"industrial", "tool_fleet", "device"} <= set(out["active"]) and set(out["active"].values()) == {None}  # every pack
    assert out["models"] == []
    assert out["can"] == {"fit": True, "promote": True}
    assert _models("planner-a")["can"] == {"fit": True, "promote": False}
    assert _models("approver")["can"] == {"fit": False, "promote": True}
    assert _models("developer")["can"] == {"fit": False, "promote": False}


@pytest.mark.parametrize("acct", ["wm-1", "finance"])
def test_models_screen_refused(acct):
    r = client.get(MODELS, headers=h(acct))
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"


def test_fit_propose_promote():
    mid = call("model.fit", {}, "planner-a")["output"]["id"]
    # not proposed yet: nobody approves it
    r = call("model.promote", {"id": mid}, "approver")
    assert r["error"] == {"code": "conflict", "message": f"Propose {mid} for promotion first."}
    (m,) = _models("approver")["models"]
    assert (m["id"], m["status"], m["created_by"], m["proposal"]) == (mid, "candidate", "planner-a", None)
    assert m["metrics"]["n"] == 0 and "mae_candidate" in m["metrics"]
    assert m["blocks"]["promote"] == f"Propose {mid} for promotion first."
    assert _models("planner-a")["models"][0]["blocks"]["propose"] is None

    p = call("model.propose", {"id": mid}, "planner-a")
    assert p["ok"] is True, p
    assert p["output"]["proposal"]["by"] == "planner-a"
    again = call("model.propose", {"id": mid}, "planner-a")
    assert again["error"]["code"] == "conflict"
    (m,) = _models("approver")["models"]
    assert m["proposal"]["by"] == "planner-a"
    assert m["blocks"] == {"propose": "Only a Planner or Admin proposes a model for promotion.", "promote": None}
    assert _models("planner-a")["models"][0]["blocks"] == {
        "propose": f"{mid} is already proposed.", "promote": "Only an Approver or Admin approves a promotion.",
    }  # fmt: skip

    ok = call("model.promote", {"id": mid}, "approver")
    assert ok["ok"] is True, ok
    out = _models("approver")
    assert out["active"]["industrial"] == mid
    assert out["models"][0]["status"] == "active" and out["models"][0]["approved_by"] == "approver"


def test_maker_and_proposer_cannot_approve():
    mine = call("model.fit", {}, "admin")["output"]["id"]
    assert call("model.propose", {"id": mine}, "admin")["ok"] is True
    assert call("model.promote", {"id": mine}, "admin")["error"] == {"code": "conflict", "message": MAKER_CHECKER}
    assert _models("admin")["models"][0]["blocks"]["promote"] == MAKER_CHECKER

    theirs = call("model.fit", {}, "planner-a")["output"]["id"]
    assert call("model.propose", {"id": theirs}, "admin")["ok"] is True
    assert call("model.promote", {"id": theirs}, "admin")["error"] == {"code": "conflict", "message": PROPOSER_CHECKER}
    row = next(m for m in _models("admin")["models"] if m["id"] == theirs)
    assert row["blocks"]["promote"] == PROPOSER_CHECKER
    assert call("model.promote", {"id": theirs}, "approver")["ok"] is True


def test_propose_needs_manage_flows_and_a_person():
    mid = call("model.fit", {}, "planner-a")["output"]["id"]
    assert call("model.propose", {"id": mid}, "approver")["error"]["code"] == "out_of_scope"
    r = client.post(
        "/api/actions/model.propose", json={"id": mid}, headers=h("planner-a") | {"X-Circularity-Preparer": "analyst"}
    ).json()
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    assert call("model.propose", {"id": "MV-999"}, "planner-a")["error"]["code"] == "not_found"
