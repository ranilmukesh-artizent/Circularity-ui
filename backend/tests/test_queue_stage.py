"""P9-2.8 (story X-05, enabler): the Disposition stage waits for the queue plan when the pack names a planner (I-5, I-7).

    Disposition with a planner   Wait("queue") and one deduped job `queue.plan {pack, org_unit_id}` (the fan-in)
    queue_job.plan(s, pack, org) the org's open cases planned together, `queuePlan` written into each, runs woken
    runtime.wake_queue           runs waiting `queue` for the pack and org run on

The tests play the worker (runtime.run_until_blocked, queue_job.plan). Every test ends with the starting state.
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import chain, queue_job, runtime
from di.services.cases import store
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, tool_case_facts

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

ORDER = {"kind": "lease", "id": "L-1", "renew": True, "who": "Acme Rentals", "site": "Houston", "need": 9, "rate": 900,
         "term": 24, "what": "Fleet contract L-1 renews", "when": "renewal confirmed"}  # fmt: skip
JOB = "queue.plan"


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))
        s.execute(text("DELETE FROM agent_proposal"))
        s.execute(text("DELETE FROM job WHERE kind IN ('queue.plan', 'agent.step')"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _open(asset: str, grade: str) -> str:
    facts = {"cls": "CMH", "grade": grade, "ft": "Repair center", "site": "Houston", "rul": 62, "dem": {"lease": [ORDER]}}
    body = {
        "org_unit_id": "Customer A",
        "template_key": "tool_fleet",
        "asset_key": asset,
        "reason": "manual",
        "facts": tool_case_facts(asset, facts),
    }
    r = call("case.open", body, "planner-a")
    assert r["ok"], r
    return r["output"]["case_id"]


def _drive(case: str) -> str:
    with SessionLocal() as s:
        run_id = runtime.start(s, "recover-chain", "stage_chain", case, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
    return run_id


def _run(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _jobs(kind: str = JOB) -> list[dict]:
    with SessionLocal() as s:
        q = text("SELECT payload, dedupe_key FROM job WHERE kind = :k AND status IN ('queued', 'running')")
        return [dict(r) for r in s.execute(q, {"k": kind}).mappings()]


def _record(run_id: str):
    with SessionLocal() as s:
        return {r.stage: r for r in chain.records_of(s, run_id)}["disposition"]


def _plan(org: str = "Customer A") -> list[str]:
    with SessionLocal() as s:
        woken = queue_job.plan(s, "tool_fleet", org)
        s.commit()
    return woken


def test_x_05_queue_stage_waits_and_wakes():
    first, second = _open("T-QS-1", "B"), _open("T-QS-2", "A")
    r1, r2 = _drive(first), _drive(second)
    for rid in (r1, r2):
        run = _run(rid)
        assert run["status"] == "waiting" and run["state"]["waiting"] == "queue", run
        rec = _record(rid)
        assert rec.status == "waiting" and rec.kind == "queue"
    jobs = _jobs()
    assert len(jobs) == 1 and jobs[0]["payload"] == {"pack": "tool_fleet", "org_unit_id": "Customer A"}
    assert jobs[0]["dedupe_key"] == "queue.plan:tool_fleet:Customer A"
    assert sorted(_plan()) == sorted([r1, r2])
    for rid in (r1, r2):
        assert _run(rid)["status"] == "running"
        with SessionLocal() as s:
            runtime.run_until_blocked(s, rid)
    for cid, rid in ((first, r1), (second, r2)):
        c = _case(cid)
        qp = c["queuePlan"]
        assert qp["route"] == c["recommendation"]["id"] and qp["reason"]
        # the run went on to the decision: submitted, or held for a person by the hold policy
        run = _run(rid)
        assert c.get("submitted") or run["state"].get("waiting") == "proposal", (c.get("submitted"), run)
    assert _case(second)["queuePlan"]["holds"] == "L-1" and _case(first)["queuePlan"]["holds"] != "L-1"


def test_queue_plan_dedupe_per_pack_org():
    _drive(_open("T-QS-3", "B"))
    _drive(_open("T-QS-4", "A"))
    assert len(_jobs()) == 1
    _drive(_open("T-QS-5", "C"))  # a third case arriving while the job is queued
    assert len(_jobs()) == 1


def test_queue_stage_without_planner_decides_alone():
    with SessionLocal() as s:
        assert load_pack("industrial").valuer.params.get("planner") is None
        assert [d.kind for d in chain.stage_defs(load_pack("industrial")) if d.id == "disposition"] == ["deterministic"]
        assert [d.kind for d in chain.stage_defs(load_pack("tool_fleet")) if d.id == "disposition"] == ["queue"]
        s.rollback()
    rid = _drive("RT-1048")
    assert _run(rid)["state"].get("waiting") != "queue"
    assert _jobs() == []
    assert _record(rid).kind == "deterministic"
