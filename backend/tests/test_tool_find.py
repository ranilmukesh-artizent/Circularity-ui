"""P9-2.12: richer tool schemas (descriptions, enums) and the `tools.find` read (find, don't list)."""

import pytest

from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import agent_allowed, catalog, find_tools
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

REACHED = (
    "case.evidence", "case.routes", "case.reevaluate", "evidence.request", "decision.submit", "instruction.resend",
    "flow.get", "flow.propose", "flow.simulate", "flow.saveDraft", "config.read", "config.draft", "fraud.hold",
    "exception.explain", "tools.find",
)  # fmt: skip


def _entry(action: str) -> dict:
    return next(t for t in catalog() if t["action"] == action)


def test_find_tools_ranks_by_text():
    hits = find_tools("request missing evidence", allowed=lambda a: True)
    assert hits and hits[0]["action"] == "evidence.request"
    assert len(hits) <= 10


def test_find_tools_excludes_forbidden():
    hits = find_tools("approve decision", limit=50, allowed=lambda a: True)
    assert "decision.approve" not in {t["action"] for t in hits}
    assert all(agent_allowed(ACTIONS[t["action"]]) for t in hits)


def test_find_tools_respects_the_allowed_filter_and_limit():
    assert find_tools("case evidence", allowed=lambda a: False) == []
    assert len(find_tools("case", limit=2, allowed=lambda a: True)) == 2
    assert find_tools("   ", allowed=lambda a: True) == []


def test_catalog_schema_has_descriptions_and_enums():
    props = _entry("decision.submit")["input_schema"]["properties"]
    assert props["case_id"]["description"]
    for action in REACHED:
        if action not in ACTIONS:
            continue
        s = _entry(action)["input_schema"]
        for k in s["required"]:
            assert s["properties"][k].get("description"), f"{action}.{k} has no description"
    # an enum is merged where the notes give one, and the golden input is never edited
    enums = [p for t in catalog() for p in t["input_schema"]["properties"].values() if "enum" in p]
    assert enums
    assert "description" not in ACTIONS["decision.submit"].input["case_id"]


def test_catalog_destructive_flag():
    assert _entry("scenario.delete")["destructive"] is True
    assert _entry("scenario.delete")["agent_mode"] == "no"  # agents never delete (25 Nov)


def test_tools_find_is_a_read_an_agent_may_call():
    a = ACTIONS["tools.find"]
    assert a.risk == "read" and a.perm is None and agent_allowed(a)
    assert _entry("tools.find")["agent_mode"] == "yes"


def test_tools_find_action_filters_to_what_the_caller_may_call():
    r = call("tools.find", {"query": "request missing evidence"}, "planner.a")
    assert r["ok"], r
    tools = r["output"]["tools"]
    assert tools[0]["action"] == "evidence.request"
    assert all(t["agent_mode"] != "no" for t in tools)
    # a Planner has no manageAgents: agent.update never shows for them
    r = call("tools.find", {"query": "change an agent tools autonomy", "limit": 50}, "planner.a")
    assert "agent.update" not in {t["action"] for t in r["output"]["tools"]}
    r = call("tools.find", {"query": "approve decision", "limit": 50}, "admin")
    assert "decision.approve" not in {t["action"] for t in r["output"]["tools"]}


def test_tools_find_validates_the_limit():
    r = call("tools.find", {"query": "case", "limit": 0}, "planner.a")
    assert not r["ok"]
