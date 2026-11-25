"""P9-2.21 (story X-05; the ten-stage journey and the case run view of docs/reference/agent-first-workbench-pr.md): the
chain's twelve stages show as the journey's ten, from real stage records only (registry entries I-7 and I-12).

The tests play the worker (runtime.run_until_blocked) as tests/test_stage_chain.py does; a closed case is made by the real
actions (submit, approve, the enterprise system's acknowledgements), without the source-sim. The model test uses a
`FunctionModel` (no test reaches a provider). Every test ends with the starting state.
"""

import re
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.services.actions.pipeline import SYSTEM, Actor, CallContext, invoke
from di.services.agents import chain, registry, runtime
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.agents.journey import STAGES, journey
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key
from di.services.canonical.store import Fact
from di.services.cases import store
from tests import starting
from tests.helpers import call, client, h

models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

CASE = "RT-1048"
AT = "2026-09-30T08:00:00Z"
RECORDS = {  # the lease, return and shipment records of the asset, and the goods receipt: stages 1 to 3 have something to read
    "lease_record": {
        "serial": "SN-77",
        "model": "VM-22",
        "site": "Pune plant",
        "usage": "6,200 h",
        "lease_end": "2026-10-01",
        "terms": "36 months",
    },  # fmt: skip
    "customer_intent": {"intent": "return", "note": "The customer returns the motor because the line is closing."},
    "return_authorisation": {
        "ra_number": "RA-5001",
        "fees": 450,
        "replacement_order": "PO-9001",
        "book_value": 8200,
        "acquired_on": "2023-10-01",
    },  # fmt: skip
    "shipment": {"pickup_on": "2026-10-02", "eta": "2026-10-20", "freight_cost": 310, "carrier": "Northline"},
    "goods_receipt": {"received_on": "2026-10-06"},
}
NAMES = ["Lease end", "Return authorised", "Pickup and transit", "Received", "Inspect and grade", "Decide", "Approve",
         "Execute", "Outcome", "Reconcile"]  # fmt: skip


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))  # the stage records cascade
        s.execute(text("DELETE FROM agent_proposal"))
        s.execute(text("DELETE FROM provenance WHERE model = 'compliance'"))
        s.execute(text("DELETE FROM canonical WHERE model = 'compliance'"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    runtime.set_loop(None)
    starting.reset()
    _clean()


def _put_records() -> None:
    with SessionLocal() as s:
        c = store.get(s, CASE)
        assert c is not None
        asset = str(c["assetId"])
        for type_, value in RECORDS.items():
            row = {"asset_key": asset, "type": type_, "result": "pass", "at": AT, "value": value}
            canonical.apply(s, "manual", [Fact("compliance", compliance_key(asset, type_), f, v) for f, v in row.items()])
        s.commit()


def _drive(case: str = CASE) -> str:
    with SessionLocal() as s:
        run_id = runtime.start(s, "recover-chain", "stage_chain", case, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
    return run_id


def _trace(run_id: str) -> dict[str, Any]:
    out = call("agent.runTrace", {"run_id": run_id}, "admin")
    assert out["ok"], out
    return out["output"]


def _statuses(trace: dict[str, Any]) -> list[str]:
    return [j["status"] for j in trace["journey"]]


def _close_case() -> None:
    """RT-1048 submitted, approved and acknowledged by every system, so it is closed with no outcome yet."""
    assert call("decision.submit", {"case_id": CASE}, "planner-a")["ok"]
    approve = {"case_id": CASE, "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True}
    assert call("decision.approve", approve, "approver")["ok"]
    for _ in range(12):
        with SessionLocal() as s:
            if (store.get(s, CASE) or {})["stage"] == "closed":
                return
            r = invoke("adapter.acknowledge", {"case_id": CASE}, CallContext(actor=SYSTEM, session=s))
            s.commit() if r["ok"] else s.rollback()
    raise AssertionError("the case did not close")


def _case() -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, CASE)
    assert c is not None
    return c


def _confirm_by_person(run_id: str) -> None:
    """Finance confirms the outcome; the hook wakes the run and the worker runs it on."""
    assert call("outcome.confirm", {"case_id": CASE}, "finance")["ok"]
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)


def _snapshot() -> dict[str, Any]:
    """Every table a view must leave alone: the journal and the run's rows."""
    with SessionLocal() as s:
        return {
            t: s.execute(text(f"SELECT count(*) FROM {t}")).scalar()  # noqa: S608 - fixed table names
            for t in ("action_journal", "agent_run", "agent_run_step", "agent_stage_record", "agent_proposal", "work_item")
        }


def test_journey_maps_ten_stages():
    """A run through every record the first nine stages read: ten stages in order, with the mapped statuses."""
    _put_records()
    trace = _trace(_drive())
    assert [j["n"] for j in trace["journey"]] == list(range(1, 11))
    assert [j["name"] for j in trace["journey"]] == NAMES == [name for _, name, _, _ in STAGES]
    assert _statuses(trace) == ["Completed"] * 6 + ["Waiting for approval"] + ["Queued"] * 3
    assert trace["journey"][0]["agent"] == "stage-lease" and trace["journey"][6]["agent"] == "stage-disposition"


def test_journey_not_reached_stages_invent_nothing():
    """A stage with no record is Queued, "Not reached.", with no evidence, calls, result or reading."""
    trace = _trace(_drive())
    for j in trace["journey"][7:]:
        assert j["status"] == "Queued" and j["activity"] == "Not reached."
        assert (j["evidence"], j["calls"], j["result"], j["validation"], j["reading"]) == ([], [], {}, [], None)
    assert [j["agent"] for j in trace["journey"][7:]] == ["stage-follow", "stage-outcome", "stage-reconcile"]


def test_journey_decide_groups_four_stages():
    """Stage 6 lists demand, fit for use, valuation and disposition as sub-steps; stage 5 stays condition's."""
    trace = _trace(_drive())
    decide = trace["journey"][5]
    assert list(decide["result"]) == ["demand", "fit_for_use", "valuation", "disposition"]
    assert decide["agent"] == "stage-demand, stage-fit, stage-valuation, stage-disposition"
    assert {c["tool"] for c in decide["calls"]} <= {"case.reevaluate", "case.routes", "decision.submit"}
    assert "submitted" not in decide["result"]["demand"]  # a sub-step shows its own output, not the approval's


def test_journey_calls_sit_under_their_stage():
    run_id = _drive()
    j = _trace(run_id)["journey"]
    assert [c["tool"] for c in j[3]["calls"]] == ["case.evidence"]  # intake's read, not the lifecycle stages'
    assert j[0]["calls"] == [] and "decision.submit" in [c["tool"] for c in j[5]["calls"]]
    assert all(c["ok"] for c in j[5]["calls"]) and set(j[5]["calls"][0]) == {"n", "tool", "input", "ok", "held"}


def test_journey_approve_waits_for_role():
    """An unapproved case: stage 7 is "Waiting for approval" and says who approves."""
    trace = _trace(_drive())
    approve = trace["journey"][6]
    assert approve["status"] == "Waiting for approval"
    assert "Approver" in approve["activity"] and "Approver" in approve["next_step"]
    assert approve["result"] == {"submitted": True, "approved": False}
    assert trace["journey"][5]["next_step"] == "Next: Approve."


def test_journey_book_case():
    """RT-1048 has no lease records: stages 1 to 3 are Skipped with the reason, the rest are as before."""
    trace = _trace(_drive())
    assert _statuses(trace)[:3] == ["Skipped"] * 3
    assert _statuses(trace)[3:7] == ["Completed"] * 3 + ["Waiting for approval"]
    assert trace["journey"][0]["activity"] == "Skipped: not a lease return."


def test_journey_blocked_stage_says_why_and_never_skips():
    """A held stage is a Warning, names its reasons and offers escalation, and the stages after it stay Queued."""
    rows = [
        {"stage": "intake", "agent": "stage-intake", "status": "held", "output": {}, "sources": [], "confidence": 0.5,
         "threshold": 0.75, "reasons": [{"reason": "confidence", "detail": "Confidence 0.50 is below 0.75."}]},
    ]  # fmt: skip
    j = journey({"stages": rows, "calls": []})
    assert j[3].status == "Warning" and "below 0.75" in j[3].validation[0]
    assert "escalates to an Admin" in j[3].next_step
    assert [s.status for s in j[4:]] == ["Queued"] * 6


def test_journey_reads_a_stored_analytics_record_as_reconcile():
    """A run from before P9-2.21 stored `analytics`: it stays readable, as stage 10."""
    rows = [{"stage": "analytics", "agent": "stage-analytics", "status": "skipped", "output": {}, "sources": [], "reasons": [],
             "confidence": 1.0, "threshold": 0.75}]  # fmt: skip
    assert journey({"stages": rows, "calls": []})[9].status == "Skipped"
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run"))
        s.execute(text("INSERT INTO agent_run (id, agent, playbook, case_id, status, step, state) VALUES "
                       "('AR-old', 'recover-chain', 'stage_chain', :c, 'done', 9, '{}')"), {"c": CASE})  # fmt: skip
        s.execute(text("INSERT INTO agent_stage_record (run_id, stage, case_id, agent, kind, autonomy, status, output, "
                       "confidence, threshold, sources, reasons) VALUES ('AR-old', 'analytics', :c, 'stage-analytics', "
                       "'deterministic', 'alone', 'skipped', '{}', 1.0, 0.75, '[]', '[]')"), {"c": CASE})  # fmt: skip
        s.commit()
        assert [r.stage for r in chain.records_of(s, "AR-old")] == ["analytics"]
    assert _trace("AR-old")["journey"][9]["status"] == "Skipped"


def test_outcome_waits_for_person_confirm():
    """A closed case with no outcome: stage 9 waits. An agent-prepared `outcome.confirm` is refused; a person's confirm
    completes the stage and the run goes on."""
    _close_case()
    run_id = _drive()
    with SessionLocal() as s:
        run = runtime.get(s, run_id)
    assert run and run["status"] == "waiting" and run["state"]["waiting"] == "outcome"
    trace = _trace(run_id)
    assert trace["journey"][8]["status"] == "Running" and "Finance" in trace["journey"][8]["activity"]
    assert trace["journey"][9]["status"] == "Queued"
    with SessionLocal() as s:
        finance = policy.account("finance", load_context(s))
        assert finance is not None
        ctx = CallContext(actor=Actor(account=finance, ctx=load_context(s)), session=s, preparer="stage-outcome", run_id=run_id)
        refused = invoke("outcome.confirm", {"case_id": CASE}, ctx)
        s.rollback()
    assert refused["ok"] is False and "outcome" not in _case()
    assert "outcome.confirm" in FORBIDDEN_ACTIONS
    _confirm_by_person(run_id)
    trace = _trace(run_id)
    assert _statuses(trace)[8:] == ["Completed", "Completed"]
    result = trace["journey"][8]["result"]
    assert result["confirmed_by"] and result["realised_value"] == _case()["outcome"]["net"]
    assert [x["item"] for x in result["actual_costs"]] == [ln["label"] for ln in _case()["outcome"]["lines"]]


def test_reconcile_lines_computed():
    """Predicted against actual, line by line, equal the computed values; the learning record is written and open items go on."""
    _close_case()
    run_id = _drive()
    _confirm_by_person(run_id)
    with SessionLocal() as s:
        rec = {r.stage: r for r in chain.records_of(s, run_id)}["reconcile"]
    case = _case()
    route = case["chosen"] or case["recommendation"]
    expected = [
        {"item": t["label"], "predicted": float(t["amt"]), "actual": float(ln["act"]), "delta": round(ln["act"] - t["amt"], 2)}
        for t, ln in zip(route["terms"], case["outcome"]["lines"], strict=True)
    ]
    assert rec.status == "done" and rec.output["lines"] == expected
    assert rec.output["net"] == {
        "predicted": float(route["net"]), "actual": float(case["outcome"]["net"]),
        "delta": round(case["outcome"]["net"] - route["net"], 2),
    }  # fmt: skip
    assert rec.output["learning_id"] == f"LR-{CASE}" and rec.output["open_items"] == []
    with SessionLocal() as s:  # the learning record: the stage's row, beside the confirmed outcome the models learn from
        q = text("SELECT output->>'learning_id' FROM agent_stage_record WHERE run_id = :r AND stage = 'reconcile'")
        assert s.execute(q, {"r": run_id}).scalar() == f"LR-{CASE}"
    assert _trace(run_id)["journey"][9]["result"]["learning_id"] == f"LR-{CASE}"


def _reading(summary_for: Callable[[AgentInfo], ModelResponse]) -> None:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        m = re.search(r"Stage: (\w+)\.", str(messages))
        if m and m.group(1) == "reconcile":
            return summary_for(info)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": "Nothing."})])

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn)))


def test_reconcile_model_explains_deltas_and_code_checks_it():
    """R16: the model's explanation of the biggest delta is added to the record when its sources exist and it invents no
    number; one that invents a figure is refused and the stage keeps the rules' record."""
    _close_case()
    ok = {"text": "The largest delta is on the first cost line.", "source": "lines"}
    _reading(
        lambda info: ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"summary": "Close to plan.", "findings": [ok]})]
        )
    )
    run_id = _drive()
    _confirm_by_person(run_id)
    with SessionLocal() as s:
        rec = {r.stage: r for r in chain.records_of(s, run_id)}["reconcile"]
    assert rec.kind == "llm" and rec.output["reading"]["findings"] == [ok]
    assert rec.output["lines"] and rec.output["learning_id"] == f"LR-{CASE}"  # the computed output is unchanged
    reading = _trace(run_id)["journey"][9]["reading"]
    assert reading and reading["reading"]["summary"] == "Close to plan."

    invented = {"text": "The delta is 777777 over plan.", "source": "lines"}
    _reading(
        lambda info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": "x", "findings": [invented]})])
    )
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run"))
        s.commit()
    run_id = _drive()  # the outcome is confirmed already: the run goes straight through
    with SessionLocal() as s:
        rec = {r.stage: r for r in chain.records_of(s, run_id)}["reconcile"]
    assert rec.kind == "deterministic" and "reading" not in rec.output and rec.output["lines"]


def test_reconcile_without_model_is_rules_only():
    _close_case()
    run_id = _drive()
    _confirm_by_person(run_id)
    with SessionLocal() as s:
        rec = {r.stage: r for r in chain.records_of(s, run_id)}["reconcile"]
    assert rec.kind == "deterministic" and _trace(run_id)["journey"][9]["reading"] is None


def test_replay_writes_nothing():
    """Replay steps through the stored records: reading them, again and again, changes no row."""
    _put_records()
    run_id = _drive()
    before = _snapshot()
    for _ in range(3):
        assert len(_trace(run_id)["journey"]) == 10
    assert client.get("/api/screens/agents", headers=h("admin")).status_code == 200
    assert _snapshot() == before


def test_back_writes_nothing():
    """Back changes the view only: the same reads, the same rows."""
    run_id = _drive()
    first = _trace(run_id)["journey"]
    before = _snapshot()
    assert _trace(run_id)["journey"] == first
    assert _snapshot() == before


def test_agents_screen_runs_answer_the_journey():
    run_id = _drive()
    body = client.get("/api/screens/agents", headers=h("admin")).json()
    run = next(r for r in body["runs"] if r["id"] == run_id)
    assert [j["name"] for j in run["journey"]] == NAMES and run["stage"] == "disposition"
    assert run["journey"] == _trace(run_id)["journey"]


def test_outcome_and_reconcile_agents_are_seeded_and_never_approve():
    assert [chain.AGENT_IDS[s] for s in ("outcome", "reconcile")] == ["stage-outcome", "stage-reconcile"]
    assert [chain.DEFAULT_AUTONOMY[s] for s in ("outcome", "reconcile")] == ["limits", "alone"]
    with SessionLocal() as s:
        for agent_id in ("stage-outcome", "stage-reconcile"):
            agent = registry.get(s, agent_id)
            assert agent is not None and agent.kind == "internal" and agent.enabled
            assert not [t for t in agent.tools if t.startswith(FORBIDDEN_ACTIONS)]
