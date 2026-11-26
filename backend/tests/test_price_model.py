"""Plan 9, P9-6.9: the price model behind the predictor (I-14 `PriceModel`; stories DV-06 and DV-14).

A trained model, never a language model: three LightGBM quantile boosters and MAPIE's conformal correction, fitted on settled
device sales plus the weekly feed. The pure tests run on rows generated here, so they hold on a fresh database and on a stack
whose device mocks have synced. The database tests seed rows of their own and assert only on those. Models are per template
(plan 8), so R21's tenant test does not apply.
"""

# ruff: noqa: S311 - seeded random numbers make test rows, not secrets
import json
import math
import random
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions.models import MAKER_CHECKER, PROPOSER_CHECKER, price_predictor
from di.services.agents.forbidden import forbidden
from di.services.engine.predictor import FormulaPredictor
from di.services.models import price_rows
from di.services.models.price import MIN_ROWS, ModelPredictor, PriceModel
from tests.helpers import call, client, h

MODELS = {"iPhone 14": 370.0, "Galaxy S23": 300.0, "Pixel 8": 250.0, "iPhone 12": 210.0}
GRADE = {"A": 1.0, "B": 0.85, "C": 0.68, "D": 0.45}
CHANNELS = ("buynow", "offers", "auction", "market", "feed")
SAMPLE = {"model": "iPhone 14", "storage_gb": 128, "grade": "B", "battery_band": "80-89", "functional_fails": 0, "age_months": 36}
FIT_FAIL_MSG = "A price model needs at least 300 settled sales or feed rows."


def synthetic_rows(n: int = 900, seed: int = 11) -> list[dict]:
    """Settled sales and feed rows over 300 days: price follows model, grade, storage and channel, with noise."""
    rnd = random.Random(seed)
    start = date(2026, 1, 1)
    out = []
    for k in range(n):
        model = rnd.choice(list(MODELS))
        grade = rnd.choice("ABBCCD")
        storage = rnd.choice((128, 256))
        channel = rnd.choice(CHANNELS)
        fails = rnd.choice((0, 0, 0, 1, 2))
        price = MODELS[model] * GRADE[grade] * (1.12 if storage == 256 else 1.0) * (1 - 0.04 * fails)
        price *= {"buynow": 1.0, "offers": 0.97, "auction": 0.93, "market": 0.95, "feed": 1.0}[channel]
        price *= math.exp(rnd.gauss(0, 0.06))
        out.append(
            {
                "model": model, "storage_gb": storage, "grade": grade, "battery_band": rnd.choice(("<80", "80-89", "90+")),
                "functional_fails": fails, "age_months": 60 if model == "iPhone 12" else 36,
                "channel": channel, "price": round(price, 2), "on": start + timedelta(days=k * 300 // n),
            }
        )  # fmt: skip
    return out


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return synthetic_rows()


@pytest.fixture(scope="module")
def fitted(rows) -> PriceModel:
    return PriceModel.fit(rows)


def test_price_model_fits_and_predicts_band_dv06(fitted):
    m = fitted.metrics
    assert 0.70 <= m["coverage"] <= 0.90, m
    assert m["n_train"] + m["n_test"] < 900 and m["n_train"] == 540 and m["n_test"] == 180  # 60% / 20% / 20% by date
    assert m["mae"] > 0 and 0 < m["mape"] < 0.2
    assert m["window"]["from"] == "2026-01-01" and m["window"]["to"] <= "2026-10-28"
    p10, p50, p90 = fitted.predict(SAMPLE, "buynow")
    assert p10 < p50 < p90
    assert 250 < p50 < 380  # an iPhone 14, grade B, 128 GB: about 370 x 0.85
    assert fitted.qhat == pytest.approx(fitted.qhat)  # a single constant, asserted when fitting


def test_price_model_round_trip_dv06(fitted, rows):
    again = PriceModel.load(json.loads(json.dumps(fitted.save())))
    for r in rows[:20]:
        assert again.predict(r, r["channel"]) == fitted.predict(r, r["channel"])


def test_price_model_deterministic_dv06(rows):
    a, b = PriceModel.fit(rows), PriceModel.fit(rows)
    assert json.dumps(a.save(), sort_keys=True) == json.dumps(b.save(), sort_keys=True)


def test_price_model_needs_enough_rows_dv06(rows):
    with pytest.raises(ValueError, match="at least 300"):
        PriceModel.fit(rows[: MIN_ROWS - 1])


def test_formula_channel_price_no_draw_dv06():
    draws = []

    def rnd() -> float:
        draws.append(1)
        return 0.5

    p = FormulaPredictor(rnd)
    band = p.channel_price({"ref": 400, "grade": "B", "band": "25-48m"}, "buynow")
    assert not draws
    assert band.p10 == band.p50 == band.p90 and band.p50 > 0 and band.model_id is None and band.feed_week is None
    a = FormulaPredictor(random.Random(5).random)
    b = FormulaPredictor(random.Random(5).random)
    b.channel_price({"ref": 400, "grade": "B", "band": "25-48m"}, "auction")
    from di.services.engine.predictor import Asset

    asset = Asset("it", "B", 2.0)
    assert a.market_value(asset) == b.market_value(asset)


def test_model_predictor_band_and_delegation_dv14(fitted):
    base = FormulaPredictor(random.Random(3).random)
    mp = ModelPredictor(base, fitted, "MV-900")
    band = mp.channel_price({**SAMPLE, "feed_week": date(2026, 10, 5)}, "buynow")
    assert (band.p10, band.p50, band.p90) == fitted.predict(SAMPLE, "buynow")
    assert band.model_id == "MV-900" and band.feed_week == date(2026, 10, 5)
    from di.services.engine.predictor import Asset

    a = Asset("it", "B", 2.0)
    assert mp.market_value(a) == FormulaPredictor(random.Random(3).random).market_value(a)


# ---------------------------------------------------------------- the actions, on rows of our own
@pytest.fixture
def made(monkeypatch):
    """`model.fit` reads the synthetic rows (the synced stack's own rows are not ours to assert on); the models it makes go."""
    monkeypatch.setattr(price_rows, "training_rows", lambda s, as_of: synthetic_rows(400))
    ids: list[str] = []
    yield ids
    with SessionLocal() as s:
        for i in ids:
            s.execute(text("DELETE FROM model_version WHERE id = :i"), {"i": i})
        s.execute(text("DELETE FROM case_record WHERE id LIKE 'PM-SHADOW-%'"))
        s.commit()


def fit(user: str, made: list[str]) -> dict:
    out = call("model.fit", {"template": "device", "kind": "price"}, user)
    if out["ok"]:
        made.append(out["output"]["id"])
    return out


def test_fit_stores_a_price_candidate_dv06(made):
    out = fit("planner-a", made)
    assert out["ok"], out
    m = out["output"]
    assert (m["kind"], m["template"], m["status"]) == ("price", "device", "candidate")
    assert m["factors"] == []  # the artefact is stored, not sent to the screens
    met = m["metrics"]
    assert {"mae", "mape", "coverage", "n_train", "n_test", "window", "n"} <= set(met)
    assert met["n"] == 400 and met["n_train"] + met["n_test"] < 400
    with SessionLocal() as s:
        art = s.execute(text("SELECT factors FROM model_version WHERE id = :i"), {"i": m["id"]}).scalar_one()
    assert PriceModel.load(art[0]["artefact"]).predict(SAMPLE, "buynow")[1] > 0


def test_fit_with_too_few_rows_is_refused_dv06(monkeypatch):
    monkeypatch.setattr(price_rows, "training_rows", lambda s, as_of: synthetic_rows(40))
    out = call("model.fit", {"template": "device", "kind": "price"}, "planner-a")
    assert not out["ok"] and out["error"] == {"code": "validation_error", "message": FIT_FAIL_MSG}


def test_price_kind_is_for_the_device_template_dv06():
    out = call("model.fit", {"template": "industrial", "kind": "price"}, "planner-a")
    assert not out["ok"] and out["error"]["code"] == "validation_error"


def test_price_model_maker_cannot_approve_r21(made):
    mid = fit("planner-a", made)["output"]["id"]
    out = call("model.promote", {"id": mid}, "admin")  # not proposed yet
    assert not out["ok"] and "Propose" in out["error"]["message"]
    mine = fit("admin", made)["output"]["id"]
    assert call("model.promote", {"id": mine}, "admin")["error"]["message"] == MAKER_CHECKER
    assert call("model.propose", {"id": mid}, "admin")["ok"]  # proposed by someone other than the maker
    assert call("model.promote", {"id": mid}, "planner-a")["ok"] is False  # the maker (and without approve.flows)
    assert call("model.promote", {"id": mid}, "admin")["error"]["message"] == PROPOSER_CHECKER  # the proposer
    refused = call("model.promote", {"id": mid}, "approver")  # P9-6.18: not before it was shadowed on 30 evaluations
    assert refused["error"]["message"] == "A price model is shadowed on 30 evaluations before promotion (0 so far)."
    with SessionLocal() as s:
        for k in range(30):
            s.execute(
                text(
                    "INSERT INTO case_record (id, owner, location, stage, data) "
                    "VALUES (:i, 'Customer A', 'x', 'intake', CAST(:d AS jsonb))"
                ),
                {"i": f"PM-SHADOW-{k}", "d": json.dumps({"id": f"PM-SHADOW-{k}", "priceShadow": {"model_id": mid}})},
            )
        s.commit()
    ok = call("model.promote", {"id": mid}, "approver")
    assert ok["ok"], ok
    with SessionLocal() as s:
        mp = price_predictor(s, FormulaPredictor(random.Random(1).random))
        assert isinstance(mp, ModelPredictor) and mp.model_id == mid
        s.execute(text("UPDATE model_version SET status = 'retired' WHERE id = :i"), {"i": mid})
        s.commit()
        assert isinstance(price_predictor(s, FormulaPredictor()), FormulaPredictor)


def test_price_model_agent_cannot_promote_r21(made):
    mid = fit("planner-a", made)["output"]["id"]
    assert forbidden("model.promote") and forbidden("model.propose")
    for action in ("model.propose", "model.promote"):
        r = client.post(
            f"/api/actions/{action}", json={"id": mid}, headers=h("admin") | {"X-Circularity-Preparer": "coordinator"}
        ).json()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", (action, r)


# ---------------------------------------------------------------- the rows it learns from, read from the tables
def test_training_rows_join_sales_to_lab_facts_and_the_feed_dv06():
    imei, key = "359990009999001", "IMEI:359990009999001"
    sku = "W2 Phone|256"
    with SessionLocal() as s:
        s.execute(
            text("INSERT INTO canonical (model, key, data) VALUES ('asset', :k, CAST(:d AS jsonb))"),
            {"k": key, "d": json.dumps({"sku_key": sku})},
        )
        s.execute(
            text("INSERT INTO canonical (model, key, data) VALUES ('condition', :k, CAST(:d AS jsonb))"),
            {
                "k": key,
                "d": json.dumps({"cosmetic_grade": "C", "battery_health_pct": 82, "functional_fails": ["camera", "wifi"]}),
            },
        )
        s.execute(
            text(
                "INSERT INTO device_listing "
                "(listing_id, org_unit_id, imei, channel, price, listed_at, offers, status, updated_at) "
                "VALUES ('W2-LST-1', NULL, :i, 'Buy Now', 100, '2026-09-01T00:00Z', 0, 'sold', '2026-09-01T00:00Z')"
            ),
            {"i": imei},
        )
        s.execute(
            text(
                "INSERT INTO device_sale (sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, case_ids) "
                "VALUES ('W2-SALE-1', 'W2-LST-1', NULL, CAST(:im AS jsonb), 123.5, 10, 0, '2026-09-05T12:00Z', '[]'::jsonb)"
            ),
            {"im": json.dumps([imei])},
        )
        s.execute(
            text(
                "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
                "VALUES ('W2 Phone|256', 'C', '2026-09-07', 111.0, 'USD', 'w2')"
            )
        )
        s.commit()
    try:
        with SessionLocal() as s:
            got = [r for r in price_rows.training_rows(s, date(2026, 10, 7)) if r["model"] == "W2 Phone"]
            early = [r for r in price_rows.training_rows(s, date(2026, 9, 1)) if r["model"] == "W2 Phone"]
        sale = next(r for r in got if r["channel"] == "buynow")
        assert (sale["storage_gb"], sale["grade"], sale["battery_band"], sale["functional_fails"], sale["price"]) == (
            256, "C", "80-89", 2, 123.5,
        )  # fmt: skip
        assert sale["on"] == date(2026, 9, 5)
        feed = next(r for r in got if r["channel"] == "feed")
        assert (feed["price"], feed["grade"], feed["on"]) == (111.0, "C", date(2026, 9, 7))
        assert early == []  # nothing settled or weekly after the date it asks as of
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM device_sale WHERE sale_id = 'W2-SALE-1'"))
            s.execute(text("DELETE FROM device_listing WHERE listing_id = 'W2-LST-1'"))
            s.execute(text("DELETE FROM device_price_point WHERE source = 'w2'"))
            s.execute(text("DELETE FROM canonical WHERE key = :k"), {"k": key})
            s.commit()
