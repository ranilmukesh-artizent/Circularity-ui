"""MVP-12.2: a model candidate fitted on the confirmed outcomes, promoted by a different person, used for new intake only.

    model.fit      act     {template?}  a candidate: the calibration factors and the mean absolute error of the active
                                        model vs the candidate on the outcome rows (manageFlows)
    model.promote  commit  {id}         candidate -> active, the previous active one retired (approve.flows; never by
                                        its maker, never by an agent)

The outcomes are written straight onto five cases (as outcome.confirm stores them) and taken off again afterwards.
"""

import copy

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.mcp.policy import FORBIDDEN_ACTIONS
from di.services.actions.models import MAKER_CHECKER, intake_predictor
from di.services.cases import store
from di.services.engine.calibration import CalibratedPredictor
from di.services.engine.predictor import FormulaPredictor
from di.services.modeler.valuers.rng import mulberry32
from di.services.screens.orchestration import learning_status
from tests.helpers import call

RATIO = 0.8  # every outcome came in at 80% of its predicted net


def _group() -> list[store.Case]:
    """Five cases of one asset class whose recommendation is the same route."""
    with SessionLocal() as s:
        groups: dict[tuple[str, str], list[store.Case]] = {}
        for c in store.all_cases(s):
            r = c.get("recommendation")
            if r and r["net"]:
                groups.setdefault((c["cls"], r["id"]), []).append(c)
    return next(cs[:5] for cs in groups.values() if len(cs) >= 5)


@pytest.fixture
def outcomes():
    cases = _group()
    before = [copy.deepcopy(c) for c in cases]
    with SessionLocal() as s:
        s.execute(text("DELETE FROM model_version"))
        for k, c in enumerate(cases):
            net = c["recommendation"]["net"]
            c["outcome"] = {"net": net * RATIO, "lines": [], "order": None, "by": "Finance", "at": f"2026-10-2{k}T09:00Z"}
            store.save(s, c)
        s.commit()
    yield cases
    with SessionLocal() as s:
        for c in before:
            store.save(s, c)
        s.execute(text("DELETE FROM model_version"))
        s.commit()


def _key(cases: list[store.Case]) -> tuple[str, str, str]:
    return ("industrial", cases[0]["recommendation"]["id"], cases[0]["cls"])


def test_fit_creates_candidate_with_metrics(outcomes):
    out = call("model.fit", {}, "planner-a")
    assert out["ok"], out
    m = out["output"]
    assert m["status"] == "candidate"
    assert m["template"] == "industrial"
    route, cls = _key(outcomes)[1:]
    assert m["factors"] == [{"route": route, "cls": cls, "factor": pytest.approx(RATIO)}]
    met = m["metrics"]
    assert met["n"] == 5 and met["active_id"] is None
    want_active = sum(abs(c["recommendation"]["net"] * (1 - RATIO)) for c in outcomes) / 5
    assert met["mae_active"] == pytest.approx(want_active)
    assert met["mae_candidate"] == pytest.approx(0, abs=1e-6)
    with SessionLocal() as s:
        row = s.execute(text("SELECT status, created_by FROM model_version WHERE id = :i"), {"i": m["id"]}).one()
        status = learning_status(s, outcomes[0])
    assert (row.status, row.created_by) == ("candidate", "planner-a")
    assert status == f"candidate model {m['id']} awaiting promotion, for review"


def test_learning_status_without_candidate_is_the_demo_text(outcomes):
    with SessionLocal() as s:
        assert learning_status(s, outcomes[0]) == "queued for the next retraining, for review"


def test_fit_needs_manage_flows(outcomes):
    out = call("model.fit", {}, "approver")
    assert not out["ok"] and out["error"] == {"code": "out_of_scope", "message": "The Approver view cannot fit models."}


def test_maker_cannot_promote(outcomes):
    mid = call("model.fit", {}, "admin")["output"]["id"]
    out = call("model.promote", {"id": mid}, "admin")
    assert not out["ok"]
    assert out["error"]["message"] == MAKER_CHECKER == "Maker-checker: you created this model, so you cannot promote it."
    assert "model.promote" in FORBIDDEN_ACTIONS
    assert not call("model.promote", {"id": mid}, "planner-a")["ok"]  # no approve.flows


def test_promote_affects_new_intake_only(outcomes):
    rt = outcomes[0]["id"]
    with SessionLocal() as s:
        before = store.get(s, rt)
        assert isinstance(intake_predictor(s, FormulaPredictor(mulberry32(5)), outcomes[0]["cls"]), FormulaPredictor)
    first = call("model.fit", {}, "planner-a")["output"]["id"]
    out = call("model.promote", {"id": first}, "approver")
    assert out["ok"], out
    assert out["output"]["status"] == "active"
    second = call("model.fit", {}, "planner-a")["output"]
    assert second["metrics"]["active_id"] == first
    assert call("model.promote", {"id": second["id"]}, "approver")["ok"]
    with SessionLocal() as s:
        st = dict(s.execute(text("SELECT id, status FROM model_version")).all())
        assert st == {first: "retired", second["id"]: "active"}
        _, route, cls = _key(outcomes)
        p = intake_predictor(s, FormulaPredictor(mulberry32(5)), cls)
        assert isinstance(p, CalibratedPredictor)
        assert p.factors[("industrial", route, cls)] == pytest.approx(RATIO)
        after = store.get(s, rt)  # a book case keeps the routes it was opened with
    assert after["routes"] == before["routes"]
    assert after["recommendation"] == before["recommendation"]
