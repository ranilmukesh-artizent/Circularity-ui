"""MVP-12.1: the outcome dataset (what outcome.confirm stores) and the calibration fitted on it.

`fit` takes the median of actual/predicted net per (template, route, asset class) with at least `min_n` rows, clipped
to [0.5, 1.5]; `CalibratedPredictor` scales the route's value estimate by that factor, drawing the same random numbers
as the predictor it wraps.
"""

import pytest

from di.repositories.outcomes import outcome_rows
from di.services.cases import store
from di.services.engine.calibration import CalibratedPredictor, OutcomeRow, fit
from di.services.engine.evaluate import build_routes
from di.services.engine.jsmath import js_round
from di.services.engine.predictor import Asset, FormulaPredictor
from di.services.modeler.valuers.rng import mulberry32


def _row(i: int, route: str, cls: str, predicted: float, actual: float, template: str = "industrial") -> OutcomeRow:
    return {
        "case_id": f"RT-{i}",
        "template": template,
        "cls": cls,
        "route": route,
        "predicted_net": predicted,
        "actual_net": actual,
        "confirmed_at": "2026-11-01T00:00:00Z",
    }


def test_fit_exact_factors():
    ratios = [0.8, 0.9, 1.0, 1.1, 0.95]  # median 0.95
    rows = [_row(i, "redeploy", "motor", 1000, 1000 * r) for i, r in enumerate(ratios)]
    rows += [_row(10 + i, "resale", "pump", 200, 200 * r) for i, r in enumerate([1.2, 1.3, 1.25, 1.2, 1.3, 1.1])]
    got = fit(rows)
    assert got == {
        ("industrial", "redeploy", "motor"): pytest.approx(0.95),
        ("industrial", "resale", "pump"): pytest.approx(1.225),  # even count: the mean of the middle two
    }


def test_fewer_than_min_n_gives_no_factor():
    rows = [_row(i, "redeploy", "motor", 1000, 900) for i in range(4)]
    rows += [_row(10 + i, "redeploy", "pump", 1000, 900) for i in range(5)]
    rows += [_row(20 + i, "redeploy", "motor", 1000, 900, template="tool_fleet") for i in range(4)]
    assert fit(rows) == {("industrial", "redeploy", "pump"): pytest.approx(0.9)}
    assert fit(rows, min_n=4) == {
        ("industrial", "redeploy", "motor"): pytest.approx(0.9),
        ("industrial", "redeploy", "pump"): pytest.approx(0.9),
        ("tool_fleet", "redeploy", "motor"): pytest.approx(0.9),
    }


def test_zero_prediction_is_not_a_row():
    rows = [_row(i, "exit", "it", 0, -50) for i in range(5)] + [_row(9, "exit", "it", -100, -120)]
    assert fit(rows) == {}


def test_factors_are_clipped():
    rows = [_row(i, "relase", "drill", 100, 300) for i in range(5)]
    rows += [_row(10 + i, "material", "drill", 100, 10) for i in range(5)]
    assert fit(rows) == {("industrial", "relase", "drill"): 1.5, ("industrial", "material", "drill"): 0.5}


def test_calibrated_predictor_scales_the_route_value():
    a = Asset("motor", "B", 6.4)
    base = FormulaPredictor(mulberry32(7))
    plain = FormulaPredictor(mulberry32(7))
    cal = CalibratedPredictor(base, {("industrial", "redeploy", "motor"): 0.9, ("industrial", "resale", "pump"): 1.2}, "motor")
    assert cal.avoided_purchase(a) == js_round(plain.avoided_purchase(a) * 0.9)
    assert cal.lease_income(a) == plain.lease_income(a)  # no factor for (industrial, relase, motor)
    assert cal.market_value(a) == plain.market_value(a)


def test_calibrated_routes_differ_only_in_the_scaled_route():
    case = {"id": "X", "cls": "pump", "grade": "B", "age": 3, "qty": 1, "demand": {}}
    plain = build_routes(dict(case), FormulaPredictor(mulberry32(3)))
    factors = {("industrial", "resale", "pump"): 1.2}
    cal = build_routes(dict(case), CalibratedPredictor(FormulaPredictor(mulberry32(3)), factors, "pump"))
    by_id = {r["id"]: r for r in plain}
    for r in cal:
        if r["id"] == "resale":
            assert r["terms"][0]["amt"] > by_id["resale"]["terms"][0]["amt"]
        else:
            assert r["terms"] == by_id[r["id"]]["terms"], r["id"]


def test_outcome_rows_read_what_outcome_confirm_stores(session):
    c = store.get(session, "RT-1048", for_update=True)
    assert c is not None
    c["outcome"] = {"net": 9230, "lines": [], "order": "SO-48102", "by": "Finance", "at": "2026-10-20T09:00:00.000Z"}
    store.save(session, c)
    try:
        rows = [r for r in outcome_rows(session) if r["case_id"] == "RT-1048"]
        assert rows == [
            {
                "case_id": "RT-1048",
                "template": "industrial",
                "cls": "motor",
                "route": "redeploy",
                "predicted_net": 9600,
                "actual_net": 9230,
                "confirmed_at": "2026-10-20T09:00:00.000Z",
            }
        ]
    finally:
        session.rollback()
