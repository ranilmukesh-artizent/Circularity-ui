"""Plan 8 MVP-11.2: the tool catalogue is generated from the action registry (GET /api/agents/tools)."""

import pytest

from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import SCHEMA, catalog
from tests.helpers import client, h


def test_every_action_appears_once():
    names = [t["action"] for t in catalog()]
    assert sorted(names) == sorted(ACTIONS) and len(names) == len(set(names))
    assert len({t["name"] for t in catalog()}) == len(names)


def test_decision_approve_is_not_agent_allowed():
    by = {t["action"]: t for t in catalog()}
    for a in ("decision.approve", "decision.override", "decision.decline", "access.setAutonomy", "agent.setEnabled"):
        assert by[a]["agent_allowed"] is False, a
    assert by["adapter.acknowledge"]["agent_allowed"] is False  # system only
    assert by["case.evidence"]["agent_allowed"] is True and by["decision.submit"]["agent_allowed"] is True


def _schema_lists_required(action_id: str) -> None:
    t = next(x for x in catalog() if x["action"] == action_id)
    s = t["input_schema"]
    assert s["$schema"] == SCHEMA and s["type"] == "object"
    want = [k for k, v in ACTIONS[action_id].input.items() if v.get("req")]
    assert want and s["required"] == want
    assert all(s["properties"][k]["type"] == ACTIONS[action_id].input[k]["t"] for k in want)


def test_case_open_schema_lists_the_required_fields():
    if "case.open" not in ACTIONS:
        pytest.skip("case.open is declared by plan 8 MVP-8.1")
    _schema_lists_required("case.open")


def test_decision_approve_schema_lists_the_required_fields():
    _schema_lists_required("decision.approve")
    t = next(x for x in catalog() if x["action"] == "decision.approve")
    assert t["input_schema"]["properties"]["rationale"]["minLength"] == 15


def test_endpoint_is_filtered_to_the_actors_permissions():
    assert client.get("/api/agents/tools").status_code == 401
    admin = {t["action"] for t in client.get("/api/agents/tools", headers=h("admin")).json()}
    planner = {t["action"] for t in client.get("/api/agents/tools", headers=h("planner.a")).json()}
    assert admin == set(ACTIONS)
    assert "case.evidence" in planner and "access.setAutonomy" not in planner and planner < admin
