"""P9-6.14 (story DV-10): the customer's diversions on a received device (I-4 operations through `apply_overlay`).

The pack offers two sample diversions: a device from retail partner P02 or P04 adds the step "Second grading check" (the case
waits for a second lab grading, the evidence `grading_second`, and values no channel meanwhile); grade C of a model over 36 months
old goes straight to the wholesale lot (only `wholesale` is valued). Both run after the gates (R20): a shortcut never brings back
a channel a gate blocked. The age is counted from the model's first week in the market feed, never by a language model (R16); the
numbers here are counted, so there is no model call to check. No new approvable object and no new action: the diversion is an
overlay operation, so its maker-checker, tenant boundary and refusal for agents are the overlay's own (tests of the overlay).
Partner codes are synthetic (P01-P05).
"""

from datetime import date

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import intake
from di.services.cases.decide import decide_case
from di.services.device import inputs
from di.services.modeler.compile import FlowVersion
from di.services.modeler.overlay import apply_overlay, parse_ops
from di.services.modeler.pack import Pack, load_pack
from tests import starting

NOW = clock.now().isoformat()
IMEI = "359990000014001"
MODEL = "Zed Phone 1"


def _samples() -> dict[str, dict]:
    """The pack's own sample diversions, as ops with an id (the Modeler adds the id when the customer saves them)."""
    out = {}
    for i, s in enumerate(load_pack("device").customer_layer.sample_diversions, start=1):
        if not s.blocked:
            out[s.op.get("to") or "step"] = {**s.op, "id": f"op-{i}"}
    return out


def _pack() -> Pack:
    ops = list(_samples().values())
    assert len(ops) == 2, ops
    return apply_overlay(load_pack("device"), parse_ops(ops))


def _lot(*, partner="P01", grade="B", age=20.0, second=None, clear=True) -> dict:
    inputs_ = {
        "feed_price": 200.0, "feed_stale": False, "sales_90d": 50, "model_age_months": age,
        "registry": {"state": "clear", "status": "clear", "hits": [], "checked_at": NOW[:10], "checked_ts": NOW, "age_days": 1.0}
        if clear else {"state": "hit", "status": "reported stolen", "hits": ["reported stolen"], "checked_at": NOW[:10]},
        "wipe": {"state": "ok", "certificate": {"certificate_id": "WC-1", "method": "Purge", "tool_version": "4.2",
                                                 "verification": "pass", "operator": "OP-1", "at": NOW}, "missing": []}
        if clear else {"state": "none", "certificate": None},
        "bands": {k: {"p10": v * 0.9, "p50": v, "p90": v * 1.1, "model_id": None, "feed_week": "2026-10-05"}
                  for k, v in (("buynow", 150.0), ("offers", 160.0), ("auction", 170.0), ("wholesale", 140.0))},
        "evidence": {"grading_second": second},
    }  # fmt: skip
    lot = intake.device_lot("D-9014", {"grade": grade, "band": "25-48m", "ref": 200, "qty": 1}) | {
        "imei": IMEI, "sku_key": "iPhone 14|128",
        "storage_gb": 128, "quote": {"amount": 210}, "partner": partner, "model": "iPhone 14", "inputs": inputs_,
    }  # fmt: skip
    return {"id": "D-9014", "valuer": lot}


def _decide(case: dict, session=None):
    return decide_case(case, _pack(), FlowVersion(None, 3, ()), session=session)


# ---------------------------------------------------------------- the pack's samples
def test_dv_10_pack_offers_both_diversions():
    ops = _samples()
    step, short = ops["step"], ops["wholesale"]
    assert step["step"] == "Second grading check" and step["when"][0] == {
        "fact": "valuer.partner",
        "op": "in",
        "value": ["P02", "P04"],
    }
    assert {c["fact"] for c in short["when"]} == {"valuer.grade", "valuer.inputs.model_age_months"}


# ---------------------------------------------------------------- DV-10 partner
def test_dv_10_retail_partner_second_grading():
    for partner in ("P02", "P04"):
        d = _decide(_lot(partner=partner))
        assert d.diversions == ["op-1"], d.diversions
        assert [x["step"] for x in d.required_steps] == ["Second grading check"]
        assert d.hold is not None and d.hold["gates"] == ["grading_second"]  # the case waits for the second grading
        assert d.recommendation is None and d.route is None
        assert all(r["excluded"] for r in d.routes)
    seen = _decide(_lot(partner="P02", second="B"))  # the lab's second grading is on file: the case goes on
    assert seen.hold is None and seen.recommendation is not None and seen.diversions == ["op-1"]
    plain = _decide(_lot(partner="P01"))  # another partner: no diversion, no wait
    assert plain.diversions == [] and plain.hold is None and not plain.required_steps and plain.recommendation is not None


def test_dv_10_second_grading_read_from_the_canonical_store_when_a_session_is_given():
    with SessionLocal() as s:
        assert _decide(_lot(partner="P02"), s).hold is not None
        canonical.apply(s, "dvlab", [Fact("condition", f"IMEI:{IMEI}", "cosmetic_grade_second", "B")])
        d = _decide(_lot(partner="P02"), s)
        assert d.hold is None and d.recommendation is not None
        s.rollback()


# ---------------------------------------------------------------- DV-10 grade C, old model
def test_dv_10_grade_c_old_model_to_wholesale():
    old = _decide(_lot(grade="C", age=40.0))
    assert old.diversions == ["op-2"] and old.route == "wholesale"
    assert [r["id"] for r in old.routes if not r["excluded"]] == ["wholesale"]  # only wholesale is eligible
    young = _decide(_lot(grade="C", age=20.0))  # normal ranking
    assert young.diversions == [] and len([r for r in young.routes if not r["excluded"]]) > 1
    exactly = _decide(_lot(grade="C", age=36.0))  # "over 36 months" is not 36
    assert exactly.diversions == []
    better = _decide(_lot(grade="B", age=40.0))
    assert better.diversions == []


def test_dv_10_a_shortcut_never_bypasses_a_gate():
    """R20: wholesale is blocked by the wipe and lock gates, so grade C over 36 months still gets no route."""
    d = _decide(_lot(grade="C", age=40.0, clear=False))
    assert "op-2" in d.diversions
    assert d.route is None and d.recommendation is None and all(r["excluded"] for r in d.routes if r["id"] != "recycle")
    assert {g.gate_id for g in d.gates if not g.passed} >= {"G-DEV-WIPE", "G-DEV-LOCK"}


# ---------------------------------------------------------------- the model's age
@pytest.fixture
def feed():
    starting.reset()
    with engine.begin() as c:
        c.execute(text("DELETE FROM device_price_point WHERE sku_key LIKE :m"), {"m": f"{MODEL}|%"})
        for sku, week in ((f"{MODEL}|128", "2023-09-04"), (f"{MODEL}|256", "2023-11-06"), (f"{MODEL}|128", "2024-01-01")):
            c.execute(
                text("INSERT INTO device_price_point VALUES (:k, 'B', :w, 100, 'USD', 'dvmkt') ON CONFLICT DO NOTHING"),
                {"k": sku, "w": week},
            )
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM device_price_point WHERE sku_key LIKE :m"), {"m": f"{MODEL}|%"})


def test_dv_10_model_age_months_from_the_first_feed_week(feed):
    with SessionLocal() as s:
        assert inputs.model_age_months(s, MODEL, date(2026, 10, 5)) == 37.0  # 2023-09-04 to 2026-10-05, 1127 days
        assert inputs.model_age_months(s, MODEL, date(2023, 9, 4)) == 0.0
        assert inputs.model_age_months(s, "A Model Never Sold", date(2026, 10, 5)) is None
        assert inputs.model_age_months(s, MODEL, date(2023, 1, 1)) is None  # not in the feed yet
