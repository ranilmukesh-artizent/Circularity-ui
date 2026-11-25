"""P9-2.1 (story X-05): the stage chain runs a case through the eleven stages, one agent per stage, each leaving a typed
record in `agent_stage_record` (registry entry I-7).

The tests play the worker (runtime.run_until_blocked), as tests/test_agent_runtime.py does. `case_autopilot` is an alias
that makes the same calls as before. The starting state is restored before and after each test.
"""

import subprocess
import sys
from decimal import Decimal

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import chain, runtime
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.agents.playbooks import stage_chain
from di.services.agents.stages import CHAIN, analytics, condition, valuation
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

CASE = "RT-1048"
BLOCKED = "RT-1051"  # evidence is missing: intake asks for it
LIFECYCLE = ["lease_end", "return_auth", "transit"]  # P9-2.20: skipped on a case with no lease records
ORDER = [*LIFECYCLE, "intake", "condition", "demand", "fit_for_use", "valuation", "disposition"]
D1_AUTONOMY = ["alone", "limits", "alone", "alone", "limits", "alone", "limits", "alone", "limits", "limits", "alone"]


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))  # the stage records cascade
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _drive(agent: str, playbook: str, case: str = CASE) -> str:
    with SessionLocal() as s:
        run_id = runtime.start(s, agent, playbook, case, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
    return run_id


def _run(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def _records(run_id: str) -> list[chain.StageRecord]:
    with SessionLocal() as s:
        return chain.records_of(s, run_id)


def _tools(run_id: str) -> list[str]:
    with SessionLocal() as s:
        q = text("SELECT tool FROM agent_run_step WHERE run_id = :i ORDER BY n")
        return list(s.execute(q, {"i": run_id}).scalars())


def _journal(run_id: str) -> dict[str, str]:
    with SessionLocal() as s:
        q = text("SELECT action, preparer FROM action_journal WHERE run_id = :i")
        return dict(s.execute(q, {"i": run_id}).tuples().all())


def test_x_05_chain_runs_stages_in_order():
    run_id = _drive("recover-chain", "stage_chain")
    run = _run(run_id)
    assert run["status"] == "waiting" and run["state"]["waiting"] == "approval"
    recs = _records(run_id)
    assert [r.stage for r in recs] == ORDER
    assert [r.status for r in recs] == ["skipped"] * 3 + ["done"] * 5 + ["waiting"]
    assert {r.agent for r in recs} == {
        "stage-lease",
        "stage-return",
        "stage-transit",
        "stage-intake",
        "stage-condition",
        "stage-demand",
        "stage-fit",
        "stage-valuation",
        "stage-disposition",
    }


def test_x_05_chain_finishes_after_approval():
    run_id = _drive("recover-chain", "stage_chain")
    approve = {"case_id": CASE, "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True}
    assert client.post("/api/actions/decision.approve", json=approve, headers=h("approver")).json()["ok"] is True
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
    assert _run(run_id)["status"] == "done"
    assert [r.stage for r in _records(run_id)] == [*ORDER, "follow_through", "analytics"]
    last = _records(run_id)[-1]
    assert last.status == "skipped"  # the case is not closed


def test_x_05_autopilot_calls_unchanged_on_chain():
    assert call("agent.register", {"id": "ext-autopilot", "name": "Autopilot", "tools": [], "autonomy": "act"}, "admin")["ok"]
    run_id = _drive("ext-autopilot", "case_autopilot")
    assert _tools(run_id) == ["case.evidence", "decision.submit"]
    assert _run(run_id)["state"]["waiting"] == "approval"
    assert _journal(run_id)["decision.submit"] == "ext-autopilot"  # the alias keeps the run's agent as the preparer


def test_x_05_each_stage_has_its_agent():
    run_id = _drive("recover-chain", "stage_chain", BLOCKED)
    assert _journal(run_id)["evidence.request"] == "stage-intake"
    run_id = _drive("recover-chain", "stage_chain")
    assert _journal(run_id)["decision.submit"] == "stage-disposition"


def test_x_05_proposing_agent_keeps_its_holds():
    assert call("agent.register", {"id": "ext-chain", "name": "Chain", "tools": [], "autonomy": "propose"}, "admin")["ok"]
    run_id = _drive("ext-chain", "stage_chain")
    run = _run(run_id)
    assert run["status"] == "waiting" and run["state"]["waiting"] == "proposal"  # a stage agent's autonomy never loosens it
    assert [r.status for r in _records(run_id)][-1] == "held"


def test_x_05_calls_carry_the_stage_context(monkeypatch):
    seen: list[tuple] = []
    real = runtime.invoke

    def spy(action, i, ctx):
        st = ctx.stage
        seen.append((action, ctx.preparer, st and (st.stage, st.autonomy, st.threshold, st.guardrail_holds)))
        return real(action, i, ctx)

    monkeypatch.setattr(runtime, "invoke", spy)
    _drive("recover-chain", "stage_chain")
    assert ("decision.submit", "stage-disposition", ("disposition", "limits", 0.75, [])) in seen
    assert ("case.evidence", "stage-intake", ("intake", "alone", 0.75, [])) in seen


def test_x_05_stage_record_has_confidence_and_threshold():
    recs = {r.stage: r for r in _records(_drive("recover-chain", "stage_chain"))}
    v = recs["valuation"]
    assert v.confidence is not None and 0.0 <= v.confidence <= 1.0 and v.threshold == 0.75
    assert v.output["best"] and v.output["best"]["route"]
    assert recs["disposition"].confidence == v.confidence  # the disposition carries the valuation's confidence
    case = {"id": "X", "evidenceRecords": [
        {"type": "grade", "source": "Repair system", "at": "2026-11-20T10:00:00Z", "result": "pass", "value": {"grade": "B"}},
        {"type": "rul", "source": "Telemetry", "at": "2026-11-21T10:00:00Z", "result": "pass", "value": {"months": 40}},
    ]}  # fmt: skip
    defn = chain.stage_defs(load_pack("industrial"))[1]
    rec = chain.build_record(defn, condition, {}, case, "done")
    assert rec.output == {"grade": "B", "grade_source": "Repair system", "estimate": False, "rul": {"months": 40}}
    assert rec.confidence == 1.0 and rec.sources[0]["source"] == "Repair system" and rec.sources[0]["at"]


def test_x_05_condition_confidence_for_estimate_and_missing():
    est = {"evidenceRecords": [
        {"type": "grade", "source": "Model", "at": "2026-11-20T10:00:00Z", "result": "pass",
         "value": {"grade": "C", "estimate": True, "probability": 0.7}},
    ]}  # fmt: skip
    assert condition.confidence({}, est) == 0.7 and condition.output({}, est)["estimate"] is True
    assert condition.confidence({}, {}) == 0.0 and condition.output({}, {})["grade"] is None


def test_x_05_valuation_confidence_formulas():
    def route(net, p10=None, p90=None):
        return {"id": f"r{net}", "plan": "P", "net": net, "excluded": False, "p10": p10, "p90": p90}

    apart = {"routes": [route(1000, 900, 1100), route(500, 400, 600)]}
    assert valuation.confidence({}, apart) == 1.0  # the intervals do not overlap
    half = {"routes": [route(1000, 900, 1100), route(950, 1000, 1200)]}
    assert valuation.confidence({}, half) == 0.5  # an overlap of 100 over a width of 200
    plain = {"routes": [route(1000), route(900)]}
    assert valuation.confidence({}, plain) == pytest.approx(0.6)  # 0.5 + the lead of 100 over the best net of 1000
    assert valuation.confidence({}, {"routes": []}) is None


def test_x_05_analytics_output_only_when_closed():
    case = {"stage": "closed", "recommendation": {"net": 100}, "outcome": {"net": 90}}
    assert analytics.output({}, case) == {"predicted_net": 100, "actual_net": 90}
    assert analytics.next_call(0, {}, {"stage": "approved"}).skipped is True  # type: ignore[union-attr]


def test_stage_defs_defaults_and_range():
    pack = load_pack("industrial")
    bare = chain.stage_defs(pack.model_copy(update={"stages": []}))
    assert [d.id for d in bare] == [m.ID for m in CHAIN] and len(bare) == 11
    assert [d.autonomy for d in bare] == D1_AUTONOMY
    assert {d.threshold for d in bare} == {0.75}
    assert [d.agent_id for d in bare][3:5] == ["stage-intake", "stage-condition"] and bare[6].agent_id == "stage-fit"
    assert bare[7].tools == ("case.reevaluate", "case.routes") and bare[0].value_limit is None
    bad = [pack.stages[0].model_copy(update={"confidence": 0.9}), *pack.stages[1:]]
    with pytest.raises(ValueError, match="0.65"):
        chain.stage_defs(pack.model_copy(update={"stages": bad}))


def test_stage_chain_never_reaches_forbidden():
    assert not [a for m in CHAIN for a in m.ACTIONS if a.startswith(FORBIDDEN_ACTIONS)]
    assert not [a for a in stage_chain.ACTIONS if a.startswith(FORBIDDEN_ACTIONS)]
    code = (
        "import di.services.agents.stages.intake as m\n"
        "m.ACTIONS = (*m.ACTIONS, 'decision.approve')\n"
        "import di.services.agents.runtime\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # noqa: S603
    assert r.returncode != 0 and "no agent may run" in r.stderr and "decision.approve" in r.stderr


def test_x_05_legacy_run_keeps_its_place():
    assert stage_chain.where({}, 0) == (3, 0) and stage_chain.where({}, 3) == (8, 0) and stage_chain.where({}, 4) == (8, 1)
    assert stage_chain.where({"stage": 4, "sub": 1}, 0) == (4, 1)


def test_x_05_start_run_accepts_stage_chain_and_the_run_page_shows_the_stage():
    r = call("agent.startRun", {"agent": "recover-chain", "case_id": CASE, "playbook": "stage_chain"}, "admin")
    assert r["ok"] is True and r["output"]["playbook"] == "stage_chain", r
    run_id = r["output"]["run_id"]
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
    runs = client.get("/api/screens/agents", headers=h("admin")).json()["runs"]
    (row,) = [x for x in runs if x["id"] == run_id]
    assert row["stage"] == "disposition" and row["status"] == "waiting"
    assert call("agent.startRun", {"agent": "recover-chain", "case_id": CASE, "playbook": "nope"}, "admin")["ok"] is False


def test_x_05_run_chain_returns_the_records():
    with SessionLocal() as s:
        out = chain.run_chain(s, CASE, account="planner-a")
    assert out.status == "waiting" and [r.stage for r in out.stages] == ORDER
    assert isinstance(out.stages[0].threshold, float) and Decimal(str(out.stages[0].threshold)) == Decimal("0.75")


def test_x_05_stage_record_is_one_row_per_run_and_stage():
    run_id = _drive("recover-chain", "stage_chain")
    with SessionLocal() as s:
        n = s.execute(
            text("SELECT count(*), count(DISTINCT stage) FROM agent_stage_record WHERE run_id = :i"), {"i": run_id}
        ).one()
    assert tuple(n) == (9, 9)
