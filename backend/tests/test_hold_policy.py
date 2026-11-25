"""P9-2.4 (story X-05; registry entry I-10): the hold policy, the last step of evaluation, holds an agent's write for a person
with typed reasons (risk, value, confidence, taint, destructive, autonomy).

`evaluate_hold` is pure and tested on its own; the pipeline tests make an agent-prepared call through `invoke` with the
stage context the runtime would set. Review Focus 4: a stage set to `recommend` never writes. The starting state is
restored before and after each test.
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.services.actions import hold
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.actions.registry import ACTIONS
from di.services.agents import chain, proposals
from di.services.agents.catalog import catalog
from di.services.agents.stage_context import StageContext
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

SUBMIT = {"case_id": "RT-1048"}
EVIDENCE = {"case_id": "RT-1051"}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


def stage(autonomy="limits", *, sid="disposition", confidence=0.9, value=300, limit=600, threshold=0.75, guardrails=None):
    return StageContext(
        stage=sid, autonomy=autonomy, confidence=confidence, threshold=threshold, value=None if value is None else Decimal(value),
        value_limit=None if limit is None else Decimal(limit), bulk_limit=None, guardrail_holds=guardrails or [],
    )  # fmt: skip


def prepared(action: str, i: dict, st: StageContext | None, *, agent="stage-disposition", user="planner-a", taint=False) -> dict:
    """An agent-prepared call through the pipeline, as the runtime makes it; committed, so the test can read the result."""
    with SessionLocal() as s:
        pctx = load_context(s)
        account = policy.account(user, pctx)
        ctx = CallContext(actor=Actor(account=account, ctx=pctx), session=s, preparer=agent, stage=st, taint=taint)
        r = invoke(action, i, ctx)
        s.commit()
        return r


def held_reasons(r: dict) -> list[str]:
    assert r["ok"] is True and "held" in r["output"], r
    return [x["reason"] for x in r["output"]["reasons"]]


def journaled(action: str) -> int:
    with SessionLocal() as s:
        return int(s.execute(text("SELECT count(*) FROM action_journal WHERE action = :a"), {"a": action}).scalar_one())


def set_ceiling(level: str, kind: str = "evidence") -> None:
    assert call("access.setAutonomy", {"role": "Planner", "type": kind, "level": level}, "admin")["ok"] is True


def eval_hold(**kw):
    base = {
        "action": ACTIONS["decision.submit"], "autonomy": "limits", "confidence": 0.9, "value": Decimal(300), "bulk": 1,
        "open_exception": False, "conflict": False, "guardrail_holds": [], "taint": False,
        "policy": hold.HoldPolicy(Decimal(600), 100, 0.75),
    }  # fmt: skip
    return hold.evaluate_hold(**(base | kw))


# --- the pipeline: what each autonomy level holds --------------------------------------------------------------------


def test_x_05_recommend_always_holds():
    r = prepared("decision.submit", SUBMIT, stage("recommend", confidence=0.95, value=100))
    assert held_reasons(r) == ["autonomy"]
    assert r["output"]["reasons"][0]["detail"] == "Disposition is set to Recommend only"
    assert journaled("decision.submit") == 0  # nothing ran


def test_x_05_limits_holds_above_value():
    r = prepared("decision.submit", SUBMIT, stage("limits", value=900, limit=600))
    assert held_reasons(r) == ["value"]
    assert r["output"]["reasons"][0]["detail"] == "Value $900 is above the $600 limit"
    assert journaled("decision.submit") == 0


def test_x_05_limits_runs_within():
    r = prepared("decision.submit", SUBMIT, stage("limits", value=300, limit=600, confidence=0.9))
    assert r["ok"] is True and "held" not in r["output"], r
    assert journaled("decision.submit") == 1


def test_x_05_alone_holds_below_threshold():
    set_ceiling("act")
    r = prepared("evidence.request", EVIDENCE, stage("alone", sid="intake", confidence=0.70, threshold=0.75))
    assert held_reasons(r) == ["confidence"]
    assert r["output"]["reasons"][0]["detail"] == "Confidence 0.70 is below 0.75"


def test_x_05_alone_ignores_value():
    set_ceiling("act")
    r = prepared("evidence.request", EVIDENCE, stage("alone", sid="intake", value=5000, limit=600, confidence=0.9))
    assert r["ok"] is True and "held" not in r["output"], r
    assert journaled("evidence.request") == 1


def test_x_05_guardrail_holds_at_every_level():
    set_ceiling("act")
    guard = ["AP-VALUE needs Approver"]
    for level in ("recommend", "limits", "alone"):
        r = prepared("evidence.request", EVIDENCE, stage(level, sid="intake", guardrails=guard))
        assert "risk" in held_reasons(r), level
        assert "Guardrail AP-VALUE needs Approver" in [x["detail"] for x in r["output"]["reasons"]], level
    assert journaled("evidence.request") == 0


def test_x_05_held_item_shows_recommendation_and_reason():
    r = prepared("decision.submit", SUBMIT, stage("recommend"), taint=True)
    assert held_reasons(r) == ["taint", "autonomy"]
    with SessionLocal() as s:
        pctx = load_context(s)
        [p] = proposals.pending_for(s, policy.account("admin", pctx), pctx)
    assert p["id"] == r["output"]["held"] and p["why"] == ACTIONS["decision.submit"].desc and p["why"]
    assert [x["reason"] for x in p["reasons"]] == ["taint", "autonomy"]
    assert all(x["detail"] for x in p["reasons"])


# --- every level: destructive and taint ------------------------------------------------------------------------------


def test_hold_destructive_always():
    r = prepared("scenario.delete", {"case_id": "RT-1048", "id": "SCN-1"}, stage("alone", sid="valuation", confidence=1.0))
    assert held_reasons(r) == ["destructive"]
    assert catalog_entry("scenario.delete")["destructive"] is True


def test_hold_destructive_covers_the_five_declared_and_held_for_person():
    declared = ("scenario.delete", "flow.discard", "workflow.draft.discard", "task.cancel", "mapping.revert")
    by = {t["action"]: t for t in catalog()}
    for a in declared:
        assert ACTIONS[a].destructive is True and by[a]["destructive"] is True, a
    for a in ("tables.update", "mapping.save"):  # P9-0.4's HELD_FOR_PERSON is folded into the reason
        assert by[a]["destructive"] is True and by[a]["agent_mode"] == "held", a
    assert by["evidence.request"]["destructive"] is False


def test_hold_taint_always():
    set_ceiling("act")
    r = prepared("evidence.request", EVIDENCE, stage("alone", sid="intake", confidence=1.0), taint=True)
    assert held_reasons(r) == ["taint"]
    assert journaled("evidence.request") == 0
    # a call outside the chain (no stage) is held for taint too
    r = prepared("evidence.request", EVIDENCE, None, taint=True)
    assert held_reasons(r) == ["taint"]


def test_hold_access_ceiling_lowers_level():
    set_ceiling("prepare")  # Admin's Access level for the Planner: prepare = limits
    r = prepared("evidence.request", EVIDENCE, stage("alone", sid="intake", value=900, limit=600))
    assert held_reasons(r) == ["value"]  # the stage says alone, the ceiling says limits
    set_ceiling("act")
    r = prepared("evidence.request", EVIDENCE, stage("alone", sid="intake", value=900, limit=600))
    assert "held" not in r["output"], r


def test_hold_person_unaffected():
    r = call("decision.submit", SUBMIT, "planner.a")
    assert r["ok"] is True and "held" not in r["output"], r
    assert journaled("decision.submit") == 1
    assert "held" not in call("scenario.delete", {"case_id": "RT-1048", "id": "SCN-1"}, "planner.a")["output"]


def test_hold_forbidden_still_refused_not_held():
    r = prepared(
        "decision.approve", {"case_id": "RT-1048", "rationale": "ok " * 10, "reviewed": True}, stage("alone"), user="approver"
    )
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM agent_proposal")).scalar_one() == 0


def test_hold_a_confirmed_call_is_not_held():
    """proposal.accept runs the held action as the person with confirmed=True: never held again."""
    r = prepared("decision.submit", SUBMIT, stage("recommend"))
    pid = r["output"]["held"]
    out = call("proposal.accept", {"id": pid}, "admin")
    assert out["ok"] is True and out["output"]["status"] == "accepted", out
    assert journaled("decision.submit") == 1


def test_hold_propose_agent_still_holds_with_reason_autonomy():
    assert call("agent.register", {"id": "ext-prop", "name": "External proposer", "tools": [], "autonomy": "propose"}, "admin")[
        "ok"
    ]
    r = prepared("evidence.request", EVIDENCE, None, agent="ext-prop")
    assert held_reasons(r) == ["autonomy"]
    assert r["output"]["reasons"][0]["detail"] == "External proposer may only propose"


def test_hold_open_exception_holds_at_limits_only():
    from di.services.cases import process

    with SessionLocal() as s:
        process.open_item(
            s, kind="exception", case_id="RT-1048", org_unit_id=None, type="test", title="Open exception", cause=None,
            action=None, owner_role="Planner", due_hours=None, by="planner-a",
        )  # fmt: skip
        s.commit()
    r = prepared("decision.submit", SUBMIT, stage("limits"))
    assert held_reasons(r) == ["risk"] and r["output"]["reasons"][0]["detail"] == "The case has an open exception"


# --- parity: the industrial chain is not held ------------------------------------------------------------------------


def test_x_05_industrial_case_without_grade_has_no_confidence_hold():
    """An industrial case has no `grade` record: the condition stage reads 0.0, which must not hold its calls."""
    from di.services.agents import runtime

    sc = stage("limits", sid="condition", confidence=0.0)
    assert runtime.stage_confidence(sc, {"id": "X"}).confidence is None
    assert eval_hold(confidence=None, autonomy="alone") == []
    assert runtime.stage_confidence(stage("alone", sid="intake", confidence=0.2), {"id": "X"}).confidence is None  # completeness
    assert runtime.stage_confidence(stage("limits", sid="valuation", confidence=0.5), {"id": "X"}).confidence == 0.5
    graded = {
        "id": "X",
        "evidenceRecords": [
            {"type": "grade", "source": "R", "at": "2026-11-20T10:00:00Z", "result": "pass", "value": {"grade": "B"}}
        ],
    }
    assert runtime.stage_confidence(stage("limits", sid="condition", confidence=1.0), graded).confidence == 1.0


# --- evaluate_hold is pure -------------------------------------------------------------------------------------------


def test_evaluate_hold_nothing_to_hold():
    assert eval_hold() == []
    assert eval_hold(autonomy="alone", value=Decimal(99999), open_exception=True, conflict=True, bulk=10**6) == []


def test_evaluate_hold_reasons_by_level():
    assert [x.reason for x in eval_hold(autonomy="limits", open_exception=True, conflict=True, bulk=500, value=Decimal(900))] == [
        "value", "risk", "risk", "risk",
    ]  # fmt: skip
    assert [x.reason for x in eval_hold(autonomy="limits", confidence=0.62)] == ["confidence"]
    assert eval_hold(autonomy="limits", confidence=0.62)[0].detail == "Confidence 0.62 is below 0.75"
    assert [x.reason for x in eval_hold(autonomy="alone", confidence=0.1)] == ["confidence"]
    assert [x.reason for x in eval_hold(autonomy="recommend", taint=True, action=ACTIONS["scenario.delete"])] == [
        "destructive", "taint", "autonomy",
    ]  # fmt: skip
    assert hold.Hold("value", "x") == hold.Hold("value", "x")  # frozen dataclasses


def test_evaluate_hold_threshold_comes_from_the_policy():
    p = hold.HoldPolicy(None, None, 0.85)
    assert [x.reason for x in eval_hold(autonomy="alone", confidence=0.8, policy=p)] == ["confidence"]
    assert eval_hold(autonomy="alone", confidence=0.8, policy=hold.HoldPolicy(None, None, 0.65)) == []


def test_policy_of_reads_the_stage():
    pack = load_pack("industrial")
    defn = chain.stage_defs(pack)[5]
    pol = hold.policy_of(pack, defn)
    assert (pol.value_limit, pol.bulk_limit, pol.threshold) == (defn.value_limit, defn.bulk_limit, defn.threshold)
    assert hold.effective_autonomy("alone", "limits") == "limits" and hold.effective_autonomy("limits", "alone") == "limits"
    assert hold.effective_autonomy("alone", None) == "alone"


# --- the migration and the API ---------------------------------------------------------------------------------------


def test_migration_0037_adds_reasons_and_is_idempotent():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0037_proposal_reasons.py"
    spec = importlib.util.spec_from_file_location("m0037", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with SessionLocal() as s:
        for _ in range(2):
            s.execute(text(mod.SQL))
        row = s.execute(
            text(
                "SELECT is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = 'agent_proposal' AND column_name = 'reasons'"
            )  # fmt: skip
        ).one()
        assert row[0] == "NO" and "[]" in row[1]


def test_x_05_home_inbox_returns_reasons():
    r = prepared("decision.submit", SUBMIT, stage("limits", value=900, limit=600))
    [row] = client.get("/api/screens/home/proposals", headers=h("admin")).json()
    assert row["id"] == r["output"]["held"]
    assert row["reasons"] == [{"reason": "value", "detail": "Value $900 is above the $600 limit"}]


def catalog_entry(action: str) -> dict:
    return next(t for t in catalog() if t["action"] == action)
