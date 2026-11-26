"""Plan 9, P9-4.11 (story SD-11): the take-up curve learned from past offers, as a model candidate a person promotes.

`fit_curve` is worked on synthetic offers drawn from a known curve; `model.fit` (kind `take_up`, template tool_fleet) is driven
through the action pipeline on rows of our own (the synced stack's offers are not ours to assert on). Maker-checker as for every
model (R21). No language model anywhere in this task (R16): a trained logistic curve, so no model tests.
"""

import math
import random
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories import upgrade_offers
from di.repositories.upgrade_offers import OfferRow
from di.services.actions.models import MAKER_CHECKER, PROPOSER_CHECKER, intake_predictor
from di.services.agents.forbidden import forbidden
from di.services.engine.predictor import FormulaPredictor
from di.services.models.take_up import MIN_OFFERS, TakeUpFit, fit_curve
from di.services.service_desk import inputs
from tests.helpers import call, client, h

A, B = -3.2, 9.0
TOO_FEW = "A take-up model needs at least 200 offers in 24 months."


def synthetic(n: int = 2400, seed: int = 11) -> list[OfferRow]:
    rng = random.Random(seed)  # noqa: S311 - synthetic offers, not secrets
    out = []
    for i in range(n):
        pct = round(rng.uniform(0.10, 0.45), 4)
        p = 1 / (1 + math.exp(-(A + B * pct)))
        out.append(OfferRow(f"UO-T{i}", "ACC-1", "US", "CRH", date(2026, 3, 1), pct, 100.0, "USD", rng.random() < p))
    return out


@pytest.fixture(scope="module")
def rows() -> list[OfferRow]:
    return synthetic()


@pytest.fixture
def made(monkeypatch, rows):
    """`model.fit` reads the synthetic offers; the models it makes go."""
    monkeypatch.setattr(upgrade_offers, "window", lambda s, since, until, market=None: rows)
    ids: list[str] = []
    yield ids
    with SessionLocal() as s:
        for i in ids:
            s.execute(text("DELETE FROM model_version WHERE id = :i"), {"i": i})
        s.commit()


def fit(user: str, made: list[str], **extra) -> dict:
    out = call("model.fit", {"template": "tool_fleet", "kind": "take_up", **extra}, user)
    if out["ok"]:
        made.append(out["output"]["id"])
    return out


def test_sd_11_fit_curve_recovers_the_curve(rows):
    f = fit_curve(rows)
    assert isinstance(f, TakeUpFit) and f.n == 2400
    assert abs(f.b - B) < 1.0 and abs(f.a - A) < 0.4
    assert len(f.bands) == 8 and sum(b["offered"] for b in f.bands) == 2400
    assert sum(b["accepted"] for b in f.bands) == sum(r.accepted for r in rows)
    assert 0 < f.brier < 0.25 and 0 < f.log_loss < math.log(2)
    assert fit_curve(rows) == f  # deterministic


def test_sd_11_fit_curve_needs_200_offers(rows):
    assert MIN_OFFERS == 200
    with pytest.raises(ValueError, match="at least 200 offers"):
        fit_curve(rows[:199])


def test_sd_11_take_up_candidate_with_error(made):
    out = fit("planner-a", made)
    assert out["ok"], out
    m = out["output"]
    assert (m["kind"], m["template"], m["status"]) == ("take_up", "tool_fleet", "candidate")
    assert abs(m["factors"][0]["b"] - B) < 1.0 and abs(m["factors"][0]["a"] - A) < 0.4
    met = m["metrics"]
    assert {"log_loss", "brier", "baseline_log_loss", "baseline_brier", "n", "bands"} <= set(met)
    assert met["n"] == 2400 and len(met["bands"]) == 8
    assert met["baseline_log_loss"] > 0  # the pack's prior on the same rows


def test_sd_11_fit_with_too_few_offers_is_refused(monkeypatch, rows):
    monkeypatch.setattr(upgrade_offers, "window", lambda s, since, until, market=None: rows[:50])
    out = call("model.fit", {"template": "tool_fleet", "kind": "take_up"}, "planner-a")
    assert not out["ok"] and out["error"] == {"code": "validation_error", "message": TOO_FEW}


def test_sd_11_take_up_kind_is_for_the_tool_fleet_template():
    out = call("model.fit", {"template": "device", "kind": "take_up"}, "planner-a")
    assert not out["ok"] and out["error"]["code"] == "validation_error"


def _gather_take_up() -> dict:
    with SessionLocal() as s:
        return inputs.take_up_of(s, 0.0, "US")


def test_sd_11_promoted_by_another_person(made):
    mid = fit("planner-a", made)["output"]["id"]
    assert call("model.promote", {"id": mid}, "approver")["error"]["message"].startswith("Propose")
    assert call("model.propose", {"id": mid}, "admin")["ok"]
    assert call("model.promote", {"id": mid}, "planner-a")["ok"] is False  # the maker, and a Planner may not approve
    assert call("model.promote", {"id": mid}, "admin")["error"]["message"] == PROPOSER_CHECKER
    me = fit("admin", made)["output"]["id"]
    assert call("model.propose", {"id": me}, "planner-a")["ok"]
    out = call("model.promote", {"id": me}, "admin")
    assert not out["ok"] and out["error"]["code"] == "conflict" and out["error"]["message"] == MAKER_CHECKER
    assert _gather_take_up()["source"] == "prior"
    ok = call("model.promote", {"id": mid}, "approver")
    assert ok["ok"], ok
    try:
        t = _gather_take_up()
        assert t["source"] == f"model {mid}"
        with SessionLocal() as s:
            art = s.execute(text("SELECT factors FROM model_version WHERE id = :i"), {"i": mid}).scalar_one()
        assert (t["a"], t["b"]) == (art[0]["a"], art[0]["b"])
    finally:
        with SessionLocal() as s:
            s.execute(text("UPDATE model_version SET status = 'retired' WHERE id = :i"), {"i": mid})
            s.commit()
    assert _gather_take_up()["source"] == "prior"


def test_sd_11_a_model_for_one_market_is_not_used_in_another(made):
    mid = fit("planner-a", made, market="US")["output"]["id"]
    assert call("model.propose", {"id": mid}, "planner-a")["ok"] and call("model.promote", {"id": mid}, "approver")["ok"]
    try:
        with SessionLocal() as s:
            assert inputs.take_up_of(s, 0.0, "US")["source"] == f"model {mid}"
            assert inputs.take_up_of(s, 0.0, "DE")["source"] == "prior"
    finally:
        with SessionLocal() as s:
            s.execute(text("UPDATE model_version SET status = 'retired' WHERE id = :i"), {"i": mid})
            s.commit()


def test_take_up_model_agent_cannot_promote(made):
    mid = fit("planner-a", made)["output"]["id"]
    assert forbidden("model.promote") and forbidden("model.propose")
    for action in ("model.propose", "model.promote"):
        r = client.post(
            f"/api/actions/{action}", json={"id": mid}, headers=h("admin") | {"X-Circularity-Preparer": "coordinator"}
        ).json()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", (action, r)


def test_calibration_ignores_take_up_kind(made):
    base = FormulaPredictor()
    with SessionLocal() as s:
        before = intake_predictor(s, base, "motor")
    mid = fit("planner-a", made)["output"]["id"]
    assert call("model.propose", {"id": mid}, "planner-a")["ok"] and call("model.promote", {"id": mid}, "approver")["ok"]
    try:
        with SessionLocal() as s:
            after = intake_predictor(s, base, "motor")
        assert type(after) is type(before) and after is base
    finally:
        with SessionLocal() as s:
            s.execute(text("UPDATE model_version SET status = 'retired' WHERE id = :i"), {"i": mid})
            s.commit()


def test_sd_11_models_screen_lists_the_take_up_model(made):
    mid = fit("planner-a", made)["output"]["id"]
    r = client.get("/api/screens/agents/models", headers=h("planner-a")).json()
    row = next(m for m in r["models"] if m["id"] == mid)
    assert row["kind"] == "take_up" and len(row["metrics"]["bands"]) == 8
    assert "activeTakeUp" in r


def test_sd_11_window_is_the_last_24_months():
    assert timedelta(days=700) < date(2026, 11, 26) - upgrade_offers.window_start(date(2026, 11, 26)) < timedelta(days=740)
