"""Plan 8 MVP-11.1: Admin's agent settings are enforced in the action pipeline (step 8) when an agent prepared the call.

- autonomy per role and action type (access.setAutonomy): Off refuses (the demo's afAgentAllowed text); Suggest
  allows no write unless a person confirmed it;
- run limits (access.setRunLimits): the run's journaled actions and the items of a bulk input;
- the kill switch (agent.setEnabled): a stopped agent prepares nothing.
People's own calls are unaffected. The starting state is restored before and after each test.
"""

import pytest

from di.services.actions.registry import ACTIONS, ActionDef
from tests import starting
from tests.helpers import client, h

EVIDENCE = {"case_id": "RT-1051"}
BULK = "test.agentBulk"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def act(action: str, body: dict, user: str = "planner.a", agent: str | None = "gap", **headers: str) -> dict:
    hdr = h(user) | ({"X-Circularity-Preparer": agent} if agent else {}) | headers
    return client.post(f"/api/actions/{action}", json=body, headers=hdr).json()


def admin(action: str, body: dict) -> None:
    assert act(action, body, user="admin", agent=None)["ok"] is True


def test_autonomy_suggest_refuses_an_agents_write():
    admin("access.setAutonomy", {"role": "Planner", "type": "evidence", "level": "suggest"})
    r = act("evidence.request", EVIDENCE)
    msg = "Gap Requester may only prepare this; a person must confirm it."
    assert r["error"] == {"code": "approval_required", "message": msg}
    # a person who pressed the final button on the agent's plan lets it through
    assert act("evidence.request", EVIDENCE, **{"X-Circularity-Confirmed": "true"})["ok"] is True


def test_autonomy_off_refuses_with_the_demos_text():
    admin("access.setAutonomy", {"role": "Planner", "type": "evidence", "level": "off"})
    a = ACTIONS["evidence.request"]
    r = act("evidence.request", EVIDENCE, **{"X-Circularity-Confirmed": "true"})
    verb = a.verb or a.title.lower()
    assert r["error"] == {"code": "out_of_scope", "message": f"The agent may not {verb} for the Planner role (autonomy: Off)."}


def test_default_autonomy_lets_the_agent_prepare():
    assert act("evidence.request", EVIDENCE)["ok"] is True


@pytest.fixture
def bulk_action():
    a = ActionDef(
        id=BULK, title="Test bulk", desc="", risk="act", perm=None, scope="none", input={"items": {"t": "array", "req": True}}
    )
    a.handler = lambda i, ctx: {"n": len(i["items"])}
    ACTIONS[BULK] = a
    yield
    ACTIONS.pop(BULK, None)


def test_run_limit(bulk_action):
    admin("access.setRunLimits", {"actions": 2, "bulk": 100})
    run = {"X-Circularity-Run": "RUN-T-1"}
    for _ in range(2):
        assert act(BULK, {"items": [1]}, **run)["ok"] is True
    r = act(BULK, {"items": [1]}, **run)
    assert r["error"] == {"code": "conflict", "message": "Run limit reached: 2 actions."}
    # another run, and a call outside any run, are not counted against it
    assert act(BULK, {"items": [1]}, **{"X-Circularity-Run": "RUN-T-2"})["ok"] is True
    assert act(BULK, {"items": [1]})["ok"] is True


def test_bulk_limit(bulk_action):
    admin("access.setRunLimits", {"actions": 50, "bulk": 3})
    assert act(BULK, {"items": [1, 2, 3]})["ok"] is True
    r = act(BULK, {"items": [1, 2, 3, 4]})
    assert r["error"] == {"code": "conflict", "message": "Bulk limit reached: 3 items."}
    assert act(BULK, {"items": [1, 2, 3, 4]}, agent=None)["ok"] is True  # a person's bulk is not limited


def test_stopped_agent_is_refused():
    admin("agent.setEnabled", {"id": "gap", "on": False})
    r = act("case.evidence", EVIDENCE)  # reads too: a stopped agent does nothing
    assert r["error"] == {"code": "out_of_scope", "message": "Gap Requester is stopped by Admin, so it cannot prepare anything."}
    assert act("case.evidence", EVIDENCE, agent="finder")["ok"] is True  # another agent is not stopped


def test_person_unaffected(bulk_action):
    admin("access.setAutonomy", {"role": "Planner", "type": "evidence", "level": "off"})
    admin("access.setRunLimits", {"actions": 1, "bulk": 1})
    admin("agent.setEnabled", {"id": "gap", "on": False})
    assert act("evidence.request", EVIDENCE, agent=None)["ok"] is True
    run = {"X-Circularity-Run": "RUN-T-3"}
    for _ in range(3):
        assert act(BULK, {"items": [1, 2]}, agent=None, **run)["ok"] is True
