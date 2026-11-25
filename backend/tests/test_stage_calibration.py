"""P9-2.9 (story X-05; registry entries I-7 and I-10): a stage's confidence is calibrated on the outcomes of people's
decisions about it, never the model's own number (R16).

`calibrate.fit` is isotonic regression (pool-adjacent-violators) over (raw confidence, accepted unchanged) points. The
action `stage.fitCalibration` stores a `<pack>.stage.<stage>` candidate in `model_version`; `model.propose` and
`model.promote` (maker-checker, forbidden to agents) activate it; the runtime passes a stage's raw confidence through the
active one before the hold policy reads it. Models are per template, so R21's tenant-boundary test does not apply as
such: the last test asserts the pack boundary instead (an unknown pack is refused, not fitted).
"""

import json

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.repositories import stage_outcomes
from di.services.actions.models import MAKER_CHECKER
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents import calibrate, runtime
from tests import starting
from tests.helpers import call
from tests.test_hold_policy import held_reasons, prepared, stage

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

POINTS = [(0.6, 0), (0.7, 0), (0.7, 1), (0.8, 1), (0.9, 1)] * 5


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run"))  # stage records go with their run
        s.execute(text("DELETE FROM model_version"))
        s.commit()


def seed_labels(stage_id: str, points: list[tuple[float, int]], action: str = "decision.submit", case: str = "RT-1048") -> None:
    """One run, stage record and decided proposal per point: accepted (1) or rejected (0) at the stage's raw confidence."""
    with SessionLocal() as s:
        for k, (conf, label) in enumerate(points):
            rid = f"run-cal-{stage_id}-{k}"
            s.execute(
                text(
                    "INSERT INTO agent_run (id, agent, playbook, case_id, status) "
                    "VALUES (:r, 'stage-x', 'stage_chain', :c, 'done')"
                ),
                {"r": rid, "c": case},
            )
            s.execute(
                text(
                    "INSERT INTO agent_stage_record (run_id, stage, case_id, agent, kind, autonomy, status, "
                    "confidence, threshold) "
                    "VALUES (:r, :st, :c, 'stage-x', 'deterministic', 'limits', 'held', :conf, 0.75)"
                ),
                {"r": rid, "st": stage_id, "c": case, "conf": conf},
            )
            s.execute(
                text("INSERT INTO agent_proposal (agent, action, case_id, run_id, status) VALUES ('stage-x', :a, :c, :r, :st)"),
                {"a": action, "c": case, "r": rid, "st": "accepted" if label else "rejected"},
            )
        s.commit()


def test_x_05_calibration_fits_isotonic():
    steps = calibrate.fit(POINTS)
    assert steps is not None
    cal = [c for _, c in steps]
    assert cal == sorted(cal), "isotonic: the calibrated share never falls as raw confidence rises"
    assert calibrate.apply(steps, 0.65) < calibrate.apply(steps, 0.85)
    assert calibrate.apply(steps, 0.1) == cal[0] and calibrate.apply(steps, 0.99) == cal[-1]  # beyond the steps: the end step


def test_x_05_calibration_pools_violators():
    steps = calibrate.fit([(0.6, 1), (0.7, 0)] * 10)  # the lower raw confidence did better: pooled into one step
    assert steps is not None and {round(c, 3) for _, c in steps} == {0.5}


def test_x_05_calibration_needs_min_n():
    assert calibrate.fit(POINTS[:19]) is None
    assert calibrate.fit(POINTS[:19], min_n=10) is not None
    with SessionLocal() as s:  # nothing active: the stage keeps its raw confidence
        sc = runtime.calibrated(s, stage("alone", sid="disposition", confidence=0.8), "industrial")
    assert sc.confidence == 0.8


def test_x_05_labels_from_proposals_and_decisions():
    seed_labels("disposition", [(0.7, 1), (0.6, 0)])
    with SessionLocal() as s:
        assert sorted(stage_outcomes.rows(s, "industrial", "disposition")) == [(0.6, 0), (0.7, 1)]
        assert stage_outcomes.rows(s, "industrial", "valuation") == []
        assert stage_outcomes.rows(s, "tool_fleet", "disposition") == []  # another pack's cases are not this pack's labels
        s.execute(
            text(
                "INSERT INTO agent_run (id, agent, playbook, case_id, status) "
                "VALUES ('run-dec', 'stage-x', 'stage_chain', 'RT-1049', 'done')"
            )
        )
        s.execute(
            text(
                "INSERT INTO agent_stage_record (run_id, stage, case_id, agent, kind, autonomy, status, "
                "confidence, threshold) "
                "VALUES ('run-dec', 'disposition', 'RT-1049', 'stage-x', 'deterministic', 'alone', 'done', 0.9, 0.75)"
            )
        )
        s.execute(
            text(
                "INSERT INTO action_journal (action, input, actor, role, case_id, at) "
                "VALUES ('decision.override', '{}', 'planner-a', 'Planner', 'RT-1049', now() + interval '1 minute')"
            )
        )
        s.commit()
        assert (0.9, 0) in stage_outcomes.rows(s, "industrial", "disposition")  # an overridden decision is a 0


def test_x_05_calibrated_confidence_drives_hold():
    steps = [{"raw": 0.5, "cal": 0.4}, {"raw": 0.8, "cal": 0.7}, {"raw": 1.0, "cal": 0.95}]
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO model_version (id, template, factors, status, created_by, metrics, created_at) "
                "VALUES ('MV-900', 'industrial.stage.disposition', CAST(:f AS jsonb), 'active', 'planner-a', '{}', now())"
            ),
            {"f": json.dumps(steps)},
        )
        s.commit()
        sc = runtime.calibrated(s, stage("alone", sid="disposition", confidence=0.80, threshold=0.75), "industrial")
    assert sc.confidence == pytest.approx(0.70)
    r = prepared("decision.submit", {"case_id": "RT-1048"}, sc)
    assert held_reasons(r) == ["confidence"]


def test_stage_calibration_fit_needs_labels_and_known_stage():
    r = call("stage.fitCalibration", {"pack": "industrial", "stage": "disposition"}, "planner-a")
    assert not r["ok"] and r["error"]["code"] == "conflict" and "20" in r["error"]["message"]
    for bad in ({"pack": "nope", "stage": "disposition"}, {"pack": "industrial", "stage": "nope"}):
        r = call("stage.fitCalibration", bad, "planner-a")
        assert not r["ok"] and r["error"]["code"] == "validation_error"
    assert not call("stage.fitCalibration", {"pack": "industrial", "stage": "disposition"}, "finance")["ok"]  # manageFlows


def test_stage_calibration_promote_maker_checker():
    seed_labels("disposition", POINTS)
    out = call("stage.fitCalibration", {"pack": "industrial", "stage": "disposition"}, "admin")
    assert out["ok"], out
    m = out["output"]
    assert m["template"] == "industrial.stage.disposition" and m["status"] == "candidate" and m["metrics"]["n"] == 25
    assert call("model.propose", {"id": m["id"]}, "admin")["ok"]  # the template key passes the propose guard
    mine = call("model.promote", {"id": m["id"]}, "admin")
    assert not mine["ok"] and mine["error"]["message"] == MAKER_CHECKER
    other = call("model.promote", {"id": m["id"]}, "approver")  # and the promote guard
    assert other["ok"] and other["output"]["status"] == "active", other
    with SessionLocal() as s:
        sc = runtime.calibrated(s, stage("alone", sid="disposition", confidence=0.6), "industrial")
    assert sc.confidence == pytest.approx(0.0)  # the fitted steps now apply


def test_stage_calibration_agent_cannot_promote():
    seed_labels("disposition", POINTS)
    m = call("stage.fitCalibration", {"pack": "industrial", "stage": "disposition"}, "planner-a")["output"]
    for action, user in (("model.propose", "planner-a"), ("model.promote", "approver")):
        with SessionLocal() as s:
            pctx = load_context(s)
            account = policy.account(user, pctx)
            ctx = CallContext(actor=Actor(account=account, ctx=pctx), session=s, preparer="stage-disposition")
            r = invoke(action, {"id": m["id"]}, ctx)
        assert not r["ok"] and r["error"]["code"] == "approval_required", r


def test_stage_calibration_pack_boundary():
    """Models are per template (plan 8), so the tenant test is a pack test: an unknown pack is refused, not fitted."""
    r = call("stage.fitCalibration", {"pack": "customer_b_pack", "stage": "disposition"}, "planner-b")
    assert not r["ok"] and r["error"]["code"] == "validation_error"
