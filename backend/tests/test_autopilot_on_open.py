"""P9-0.9 (G section 6 item 7): the case autopilot starts when a case opens, behind a deployment setting.

`case.open` queues `agent.autostart` only with DI_AUTOPILOT_ON_OPEN on; `runtime.autostart` (the worker's handler) starts
a `case_autopilot` run for the setting's agent when that agent is enabled with autonomy `act`, there is an account to act
for and no run exists yet. The run holds its decision.submit for a person (AGENTS.md rule 10). The test plays the worker.
"""

import logging

import pytest
from sqlalchemy import text

from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.agents import runtime
from di.services.cases import intake
from tests import starting
from tests.helpers import call

FACTS = {"cls": "motor", "grade": "B", "age": 4, "qty": 1, "demand": {"site": "Site 2", "confirmed": True}}
BODY = {"org_unit_id": "Customer A", "template_key": "industrial", "reason": "rma", "facts": FACTS}


def _clean() -> None:
    with SessionLocal() as s:
        for t in ("agent_run_step", "agent_run", "agent_proposal"):
            s.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names
        s.execute(text("DELETE FROM job WHERE kind IN ('agent.autostart', 'agent.step')"))
        s.execute(text("UPDATE agent_identity SET enabled = true, autonomy = 'act' WHERE id = 'coordinator'"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    runtime.log.disabled = False  # alembic's fileConfig() may have disabled it (di.core.logs)
    yield
    get_settings.cache_clear()
    starting.reset()
    _clean()


def setting(monkeypatch, on: bool = True, account: str = "") -> None:
    monkeypatch.setenv("DI_AUTOPILOT_ON_OPEN", "true" if on else "false")
    monkeypatch.setenv("DI_AUTOPILOT_ACCOUNT", account)
    get_settings.cache_clear()


def open_by(user: str, asset: str = "T-AP-1") -> str:
    r = call("case.open", BODY | {"asset_key": asset}, user)
    assert r["ok"], r
    return r["output"]["case_id"]


def autostart_jobs() -> list[dict]:
    with SessionLocal() as s:
        q = text("SELECT payload FROM job WHERE kind = 'agent.autostart' ORDER BY id")
        return [dict(p) for p in s.execute(q).scalars()]


def play_worker(case_id: str, account: str | None) -> str | None:
    with SessionLocal() as s:
        run_id = runtime.autostart(s, case_id, account)
        s.commit()
    return run_id


def runs(case_id: str) -> list[dict]:
    with SessionLocal() as s:
        q = text("SELECT * FROM agent_run WHERE case_id = :c ORDER BY id")
        return [dict(r) for r in s.execute(q, {"c": case_id}).mappings()]


def test_autostart_off_by_default():
    # P9-0.9: nothing in the environment turns it on, so a case opens as before
    open_by("planner-a")
    assert autostart_jobs() == []


def test_autostart_runs_autopilot_to_the_hold(monkeypatch):
    setting(monkeypatch)
    cid = open_by("planner-a")
    assert autostart_jobs() == [{"case_id": cid, "account": "planner-a"}]
    run_id = play_worker(cid, "planner-a")
    (r,) = runs(cid)
    assert (r["id"], r["agent"], r["playbook"], r["state"]["account"]) == (run_id, "coordinator", "case_autopilot", "planner-a")
    with SessionLocal() as s:
        assert runtime.run_until_blocked(s, run_id) == "waiting"
        s.commit()
    # an `act` agent submits the decision; approving it stays a person's (rule 10), so the run waits for that approval
    assert runs(cid)[0]["state"]["waiting"] == "approval"
    with SessionLocal() as s:
        q = text("SELECT tool FROM agent_run_step WHERE run_id = :r ORDER BY n")
        tools = list(s.execute(q, {"r": run_id}).scalars())
    assert tools[-1] == "decision.submit" and "decision.approve" not in tools


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        ("UPDATE agent_identity SET enabled = false WHERE id = 'coordinator'", "agent coordinator is stopped"),
        ("UPDATE agent_identity SET autonomy = 'propose' WHERE id = 'coordinator'", "agent coordinator only proposes"),
        ("UPDATE agent_identity SET autonomy = 'read' WHERE id = 'coordinator'", "agent coordinator only proposes"),
    ],
)
def test_autostart_skips_stopped_or_proposing_agent(monkeypatch, caplog, sql, why):
    setting(monkeypatch)
    cid = open_by("planner-a")
    with SessionLocal() as s:
        s.execute(text(sql))
        s.commit()
    with caplog.at_level(logging.INFO):
        assert play_worker(cid, "planner-a") is None
    assert runs(cid) == [] and why in caplog.text


def test_autostart_system_opener_uses_setting_account(monkeypatch, caplog):
    # a workflow-opened case passes no account: only the setting names who the agent acts for
    setting(monkeypatch, account="")
    i = {"org_unit_id": "Customer A", "template_key": "industrial", "asset_key": "T-AP-2", "reason": "rma", "facts": FACTS}
    with SessionLocal() as s:
        c = intake.open_case(s, i, "system")
        s.commit()
    assert autostart_jobs() == [{"case_id": c["id"], "account": None}]
    with caplog.at_level(logging.INFO):
        assert play_worker(c["id"], None) is None
    assert runs(c["id"]) == [] and "no account to act for" in caplog.text
    setting(monkeypatch, account="ops")
    run_id = play_worker(c["id"], None)
    (r,) = runs(c["id"])
    assert r["id"] == run_id and r["state"]["account"] == "ops"


def test_autostart_never_twice(monkeypatch, caplog):
    setting(monkeypatch)
    cid = open_by("planner-a")
    assert play_worker(cid, "planner-a") is not None
    with caplog.at_level(logging.INFO):
        assert play_worker(cid, "planner-a") is None
    assert len(runs(cid)) == 1 and "already running" in caplog.text


def test_autostart_setting_off_logs_and_starts_nothing(monkeypatch, caplog):
    setting(monkeypatch, on=False)
    with caplog.at_level(logging.INFO):
        assert play_worker("RT-1048", "planner-a") is None
    assert runs("RT-1048") == [] and "autopilot off" in caplog.text
