"""Plan 9, P9-6.18 (story DV-14): a retrained price model is shadowed before a person promotes it.

The worker's `device.priceRefit` job fits a candidate (as the system) once 200 sales settled since the active model's window;
it never proposes or promotes. While a candidate is proposed, every valuation of a received device records the candidate's band
in the case's `priceShadow` beside the active model's, and changes nothing the case decides. `model.promote` of a price model is
refused until `min_shadow` (the pack's, 30) cases are shadowed, then follows the maker-checker rules of plan 8. The metrics
compare the candidate and the active model on the shadowed cases whose device sold.
"""

import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from di import worker
from di.core import clock
from di.core.db import SessionLocal
from di.services.cases import intake, store
from di.services.device import price_shadow
from di.services.models import price_rows
from tests import starting
from tests.helpers import call, client, h
from tests.test_device_intake import IMEI, _clean, _doc, _land, _open_pending, _price
from tests.test_price_model import fit, synthetic_rows

MIN = "A price model is shadowed on 30 evaluations before promotion ({n} so far)."
CASES = "SHT-CASE-"


def _wipe_models() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM model_version WHERE template = 'device' AND kind = 'price'"))
        s.execute(text("DELETE FROM case_record WHERE id LIKE :p"), {"p": CASES + "%"})
        s.execute(text("DELETE FROM device_sale WHERE sale_id LIKE 'SHT-%'"))
        s.commit()


@pytest.fixture
def made(monkeypatch):
    """`model.fit` reads the synthetic rows; the price models, shadow cases and sales of this file go afterwards."""
    monkeypatch.setattr(price_rows, "training_rows", lambda s, as_of: synthetic_rows(400))
    _wipe_models()
    ids: list[str] = []
    yield ids
    _wipe_models()


def _band(p50: float, half: float) -> dict:
    return {"p10": p50 - half, "p50": p50, "p90": p50 + half}


def _shadow_cases(model_id: str, n: int, *, sold: bool = False, first: int = 0) -> None:
    """`n` case records that carry a shadow of the model; with `sold`, each device sold for 100 on the wholesale channel and the
    candidate's P50 was 100 + 2k (band half-width 5), the active model's 100 + 4k (half-width 6)."""
    with SessionLocal() as s:
        for k in range(first, first + n):
            imei = f"3599900{k:08d}"
            shadow = {
                "model_id": model_id, "at": (clock.now() - timedelta(days=2)).date().isoformat(), "imei": imei,
                "bands": {"wholesale": _band(100 + 2 * k, 5)},
                "active": {"model_id": None, "bands": {"wholesale": _band(100 + 4 * k, 6)}},
            }  # fmt: skip
            s.execute(
                text(
                    "INSERT INTO case_record (id, owner, location, stage, data) "
                    "VALUES (:i, 'Customer A', 'x', 'intake', CAST(:d AS jsonb))"
                ),
                {"i": f"{CASES}{k}", "d": json.dumps({"id": f"{CASES}{k}", "priceShadow": shadow})},
            )
            if sold:
                s.execute(
                    text(
                        "INSERT INTO device_sale (sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, "
                        "case_ids) VALUES (:i, NULL, 'LOT-SHT', CAST(:m AS jsonb), 100, 0, 0, :at, '[]')"
                    ),
                    {"i": f"SHT-{k}", "m": json.dumps([imei]), "at": clock.now()},
                )
        if sold:  # the candidate was trained on data up to well before these sales
            to = (clock.now() - timedelta(days=30)).date().isoformat()
            s.execute(
                text("UPDATE model_version SET metrics = coalesce(metrics, '{}'::jsonb) || CAST(:w AS jsonb) WHERE id = :i"),
                {"i": model_id, "w": json.dumps({"window": {"from": "2025-01-01", "to": to}})},
            )
        s.commit()


def _candidate(made: list[str], proposer: str = "admin") -> str:
    mid = fit("planner-a", made)["output"]["id"]
    assert call("model.propose", {"id": mid}, proposer)["ok"]
    return mid


def test_dv_14_candidate_with_mae_and_coverage(made):
    """The refit job: 200 sales settled since the active model's window give a candidate with MAE and coverage, fitted as the
    system; it is not proposed, not promoted, and no second candidate follows while one waits."""
    with SessionLocal() as s:
        for k in range(200):
            s.execute(
                text(
                    "INSERT INTO device_sale (sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, "
                    "case_ids) VALUES (:i, NULL, 'LOT-SHT', '[]', 100, 0, 0, :at, '[]')"
                ),
                {"i": f"SHT-R{k}", "at": clock.now() - timedelta(days=1)},
            )
        s.commit()
    worker.HANDLERS["device.priceRefit"]({})
    with SessionLocal() as s:
        row = s.execute(text("SELECT id, status, created_by, approved_by, metrics FROM model_version WHERE kind = 'price'")).one()
    assert (row.status, row.created_by, row.approved_by) == ("candidate", "system", None)
    assert row.metrics["mae"] > 0 and 0 < row.metrics["coverage"] <= 1
    assert "proposal" not in row.metrics
    worker.HANDLERS["device.priceRefit"]({})  # a candidate waits: nothing more is fitted
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM model_version WHERE kind = 'price'")).scalar_one() == 1


def test_dv_14_refit_waits_for_200_sales(made):
    with SessionLocal() as s:
        for k in range(199):
            s.execute(
                text(
                    "INSERT INTO device_sale (sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, "
                    "case_ids) VALUES (:i, NULL, 'LOT-SHT', '[]', 100, 0, 0, :at, '[]')"
                ),
                {"i": f"SHT-R{k}", "at": clock.now() - timedelta(days=1)},
            )
        s.commit()
        # the synced stack may hold sales of its own: the job counts every sale when no model is active
        due = price_shadow.refit_due(s, clock.now().date())
        own = s.execute(text("SELECT count(*) FROM device_sale WHERE sale_id NOT LIKE 'SHT-%'")).scalar_one()
    assert due is (199 + own >= 200)


def test_dv_14_shadow_before_promotion(made):
    mid = _candidate(made)
    _shadow_cases(mid, 12)
    out = call("model.promote", {"id": mid}, "approver")
    assert not out["ok"] and out["error"]["message"] == MIN.format(n=12), out
    screen = client.get("/api/screens/agents/models", headers=h("approver")).json()
    mine = next(m for m in screen["models"] if m["id"] == mid)
    assert mine["blocks"]["promote"] == MIN.format(n=12)
    assert mine["metrics"]["shadow"]["n"] == 12 and mine["metrics"]["shadow"]["min"] == 30
    _shadow_cases(mid, 18, first=12)
    ok = call("model.promote", {"id": mid}, "approver")
    assert ok["ok"] and ok["output"]["status"] == "active", ok


def test_dv_14_promoted_by_another_person(made):
    mid = _candidate(made)  # fitted by planner-a, proposed by admin
    _shadow_cases(mid, 30)
    out = call("model.promote", {"id": mid}, "admin")  # the proposer
    assert not out["ok"] and out["error"]["message"].startswith("Maker-checker: you proposed"), out
    assert call("model.promote", {"id": mid}, "planner-a")["ok"] is False  # the maker
    assert call("model.promote", {"id": mid}, "approver")["ok"]  # another person


def test_dv_14_shadow_metrics_on_settled_cases(made):
    """MAE and coverage of the candidate and of the active model on the shadowed cases whose device sold."""
    mid = _candidate(made)
    _shadow_cases(mid, 5, sold=True)
    _shadow_cases(mid, 2, first=5)  # shadowed, not sold yet: counted, not scored
    with SessionLocal() as s:
        st = price_shadow.stats(s, mid)
    assert (st["n"], st["settled"], st["min"]) == (7, 5, 30)
    assert st["mae"] == pytest.approx(4.0) and st["mae_active"] == pytest.approx(8.0)
    assert st["coverage"] == pytest.approx(0.6) and st["coverage_active"] == pytest.approx(0.4)


def test_dv_14_shadow_changes_no_decision(made):
    """The shadow band is recorded only while a candidate is proposed, and never changes a case's channel or net."""
    starting.reset()
    _clean()
    try:
        _price("B", 330)
        _land(_doc())
        (cid,) = _open_pending()

        def revalue() -> dict:
            with SessionLocal() as s:
                c = store.get(s, cid, for_update=True)
                assert c is not None
                intake.revalue(s, c)
                store.save(s, c)
                s.commit()
                return store.get(s, cid)  # type: ignore[return-value]

        def decision(c: dict) -> tuple:
            return json.dumps(c["routes"], sort_keys=True), c["recommendation"]["id"], c["recommendation"]["net"]

        base = revalue()
        assert "priceShadow" not in base
        mid = fit("planner-a", made)["output"]["id"]
        assert "priceShadow" not in revalue()  # a candidate nobody proposed is not shadowed
        assert call("model.propose", {"id": mid}, "admin")["ok"]
        shadowed = revalue()
        ps = shadowed["priceShadow"]
        assert ps["model_id"] == mid and ps["imei"] == IMEI
        assert {"buynow", "offers", "auction"} <= set(ps["bands"])
        assert ps["bands"]["buynow"]["p10"] <= ps["bands"]["buynow"]["p90"]
        assert set(ps["active"]["bands"]) >= {"buynow"}
        assert decision(shadowed) == decision(base)
        with SessionLocal() as s:
            assert price_shadow.stats(s, mid)["n"] == 1
    finally:
        starting.reset()
        _clean()


def test_dv_14_f10_stats_exclude_sales_before_the_shadow_and_the_training_window(made):
    """The candidate is graded only on sales settled after its shadow was taken and after its training window."""
    mid = _candidate(made)
    now = clock.now()
    with SessionLocal() as s:
        for k in range(3):
            imei = f"3599900{k:08d}"
            shadow = {"model_id": mid, "at": (now - timedelta(days=3)).date().isoformat(), "imei": imei,
                      "bands": {"wholesale": _band(100, 5)},
                      "active": {"model_id": None, "bands": {"wholesale": _band(100, 6)}}}  # fmt: skip
            s.execute(
                text(
                    "INSERT INTO case_record (id, owner, location, stage, data) "
                    "VALUES (:i, 'Customer A', 'x', 'intake', CAST(:d AS jsonb))"
                ),
                {"i": f"{CASES}{k}", "d": json.dumps({"id": f"{CASES}{k}", "priceShadow": shadow})},
            )
            when = [now - timedelta(days=5), now - timedelta(days=1), now - timedelta(days=1)][k]  # k=0 before the shadow
            s.execute(
                text(
                    "INSERT INTO device_sale (sale_id, listing_id, lot_ref, imeis, price, fees, buyer_returns, settled_at, "
                    "case_ids) "
                    "VALUES (:i, NULL, 'LOT-SHT', CAST(:m AS jsonb), 100, 0, 0, :at, '[]')"
                ),
                {"i": f"SHT-{k}", "m": json.dumps([imei]), "at": when},
            )
        s.execute(text("UPDATE model_version SET metrics = coalesce(metrics, '{}'::jsonb) - 'window' WHERE id = :i"), {"i": mid})
        s.commit()
        assert price_shadow.stats(s, mid)["settled"] == 2  # the sale before the shadow is not graded
        s.execute(
            text("UPDATE model_version SET metrics = coalesce(metrics, '{}'::jsonb) || CAST(:w AS jsonb) WHERE id = :i"),
            {"i": mid, "w": json.dumps({"window": {"from": "2026-01-01", "to": (now - timedelta(days=1)).date().isoformat()}})},
        )
        s.commit()
        assert price_shadow.stats(s, mid)["settled"] == 0  # settled within the training window: in-sample
