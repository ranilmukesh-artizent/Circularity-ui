"""Gap 12 of the 2026-11-26 UI audit: the Agent activity read (GET /api/screens/agent-activity), read-only, for every
role that has My work. A role sees what the agents did on the cases of its own tenants only (AGENTS.md rule 9)."""

import json

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from tests import starting
from tests.helpers import client, h

URL = "/api/screens/agent-activity"
CASE_A, CASE_B = "RT-1002", "RT-1001"  # Customer A and Customer B


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


def _seed() -> None:
    with SessionLocal() as s:
        for case, run in ((CASE_A, "run-act-a"), (CASE_B, "run-act-b")):
            s.execute(
                text(
                    "INSERT INTO agent_run (id, agent, playbook, case_id, status, step, state) "
                    "VALUES (:i, 'case-autopilot', 'case_autopilot', :c, 'done', 2, '{}')"
                ),
                {"i": run, "c": case},
            )
            s.execute(
                text(
                    "INSERT INTO agent_run_step (run_id, n, tool, input, output, at) "
                    "VALUES (:i, 1, 'decision.submit', '{}', CAST(:o AS jsonb), now())"
                ),
                {"i": run, "o": json.dumps({"ok": False, "error": {"message": "Refused: not allowed for an agent."}})},
            )
            for st in ("pending", "accepted", "rejected"):
                s.execute(
                    text(
                        "INSERT INTO agent_proposal (agent, action, input, case_id, run_id, status) "
                        "VALUES ('case-autopilot', 'decision.submit', '{}', :c, :r, :st)"
                    ),
                    {"c": case, "r": run, "st": st},
                )
        s.commit()


def _cases(r) -> set[str | None]:
    return {e["case_id"] for e in r.json()["events"]}


def test_planner_sees_only_its_tenants_activity():
    _seed()
    r = client.get(URL, headers=h("planner-a"))
    assert r.status_code == 200, r.text
    assert _cases(r) == {CASE_A}
    kinds = {e["kind"] for e in r.json()["events"]}
    assert kinds == {"held", "accepted", "rejected", "refused", "run"}
    assert r.json()["can"] == {"runAgent": True}


def test_other_tenant_planner_sees_the_other_case():
    _seed()
    assert _cases(client.get(URL, headers=h("planner-b"))) == {CASE_B}


def test_executive_reads_and_has_no_run_button():
    _seed()
    r = client.get(URL, headers=h("executive"))
    assert r.status_code == 200, r.text
    assert r.json()["can"] == {"runAgent": False}


def test_events_name_the_pack_and_agent():
    _seed()
    e = client.get(URL, headers=h("planner-a")).json()["events"][0]
    assert e["agentName"] and e["pack"] and e["at"]
