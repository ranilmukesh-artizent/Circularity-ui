"""P9-6.10 (story DV-06): the price of a received device on each channel with its interval, the feed week and the model; the
floor GR-D2 and the price confidence GR-D8 hold the case for a person. Pure tests on `device.decide` and `decide_case` (no
database): the bands are in the lot's inputs, as `gather` leaves them. Nothing here writes language: no model call."""

from datetime import date

import pytest

from di.core import clock
from di.services.agents.stages import valuation
from di.services.cases import intake
from di.services.cases.decide import Decision, decide_case, write_back
from di.services.engine.predictor import PriceBand
from di.services.modeler import overlay
from di.services.modeler.compile import FlowVersion
from di.services.modeler.overlay import OverlayError
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import device, device_price

NOW = clock.now().isoformat()
CERT = {"certificate_id": "WC-1", "method": "Purge", "tool_version": "4.2", "verification": "pass", "operator": "OP-1", "at": NOW}
FEED_WEEK = "2026-10-05"
CHANNELS = ("buynow", "offers", "auction", "wholesale")


def _band(p50: float, share: float = 0.0, model_id: str | None = "PM-1") -> dict:
    half = p50 * share / 2
    return {"p10": p50 - half, "p50": p50, "p90": p50 + half, "model_id": model_id, "feed_week": FEED_WEEK}


def _wide(share: float) -> dict:
    """Buy Now on a band of the given width, the other channels far below it (so the top two do not overlap)."""
    return {k: _band(285, share) if k == "buynow" else _band(20) for k in CHANNELS}


def _lot(ref: float = 300, *, imei: bool = True, bands: dict | None = None, sales: int | None = 50, **over) -> dict:
    lot = intake.device_lot("D-9100", {"grade": "B", "band": "25-48m", "ref": ref, "qty": 1, "model": "iPhone 14"})
    if not imei:
        return lot | over
    lot |= {"imei": "359990000009100", "sku_key": "iPhone 14|128", "storage_gb": 128, "quote": {"amount": 410}}
    lot["inputs"] = {
        "feed_price": ref, "feed_stale": False, "sales_90d": sales,
        "registry": {"state": "clear", "status": "clear", "hits": [], "checked_at": NOW[:10], "checked_ts": NOW, "age_days": 1.0},
        "wipe": {"state": "ok", "certificate": CERT, "missing": []},
        "bands": bands if bands is not None else {k: _band(ref * 0.95, 0.2) for k in CHANNELS},
    }  # fmt: skip
    return lot | over


def _decide(lot: dict, pack=None) -> Decision:
    return decide_case({"id": lot["id"], "valuer": lot}, pack or load_pack("device"), FlowVersion(None, 3, ()))


def test_dv_06_channels_with_interval_and_feed_date():
    lot = _lot()
    by = {v["k"]: v for v in device.decide(lot)["all"]}
    assert tuple(by) == CHANNELS
    for k, v in by.items():
        assert v["p10_cash"] < v["cash"] < v["p90_cash"], k
        assert v["feed_week"] == FEED_WEEK and v["model_id"] == "PM-1", k
    assert by["wholesale"]["why"] == "No live bid: index estimate"
    # the sale price is the band's P50 (not the reference times the index), and the interval is the same formula at P10 and P90
    band = PriceBand(285.0 - 28.5, 285.0, 285.0 + 28.5, "PM-1", date(2026, 10, 5))
    got = device.score(lot, "buynow", band)
    assert got["cash"] == pytest.approx(device.score(_lot(), "buynow", band)["cash"])
    assert got["p10_cash"] < got["cash"] < got["p90_cash"]


def test_dv_06_score_without_a_band_is_today():
    lot = _lot(imei=False, qty=3, doh=10)
    plain = device.score(lot, "buynow")
    assert "p10_cash" not in plain and "feed_week" not in plain
    assert device.score(lot, "buynow", None) == plain
    assert tuple(v["k"] for v in device.decide(lot)["all"]) == tuple(device.DCH)  # a PO lot has no wholesale channel


def test_dv_06_wholesale_takes_the_best_bid_over_the_index_estimate():
    lot = _lot(bands={})
    est = device.score(lot, "wholesale")
    assert est["why"] == "No live bid: index estimate"
    # index B 0.66, fee 2%, fixed, logistics, holding
    assert est["cash"] == pytest.approx(0.66 * 300 * 0.98 - 0.5 - 1.5 - 0.35 * 10)
    lot["inputs"]["bid_per_unit"] = 250.0
    bid = device.score(lot, "wholesale")
    assert bid["why"] == "Best open bid" and bid["cash"] > est["cash"]


def test_dv_06_floor_text_and_owner():
    assert device_price.floor_reason(105, 200, 0.55) == (
        "Below the recovery floor: $105 is 52.5% of the $200 reference value (floor 55%)"
    )
    # a received device whose every channel prices far under the reference value
    d = _decide(_lot(200, bands={k: _band(60) for k in CHANNELS}))
    hold = next(h for h in d.approval["holds"] if h["id"] == "GR-D2")
    assert hold["owner"] == "Recommerce finance" and d.approval["role"] == "Approver" and d.approval["kind"] == "person"
    assert hold["reason"].startswith("Below the recovery floor: $") and hold["reason"].endswith(
        "of the $200 reference value (floor 55%)"
    )


def test_dv_06_below_floor_waits_for_analyst():
    lot = _lot(8, imei=False, qty=5, doh=5)  # a PO lot: fees take most of $8
    d = _decide(lot)
    best = device.decide(lot, [])["best"]
    assert d.approval is not None and [h["id"] for h in d.approval["holds"]] == ["GR-D2"]
    assert d.route == best["k"] and d.net == pytest.approx(best["score"], abs=0.5)  # the route and net are what they were
    assert d.approval["holds"][0]["owner"] == "Recommerce finance"
    assert _decide(_lot(300, imei=False, qty=5, doh=5)).approval is None  # above the floor: nothing to say


def test_dv_06_low_confidence_waits_for_analyst():
    feed = {k: _band(285) for k in CHANNELS}  # the feed alone: no interval
    d = _decide(_lot(bands=feed, sales=0))
    hold = next(h for h in d.approval["holds"] if h["id"] == "GR-D8")
    assert hold["owner"] == "Pricing analyst" and hold["signals"] == ["unseen SKU"]
    assert [h["id"] for h in _decide(_lot(bands=feed, sales=50)).approval["holds"]] == []
    stale = _lot(bands=feed)
    stale["inputs"]["feed_stale"] = True
    assert next(h for h in _decide(stale).approval["holds"])["signals"] == ["stale feed"]


def test_dv_06_interval_share_decides_the_confidence_at_the_threshold():
    assert device_price.confidence(75, 100, 125) == pytest.approx(0.75)  # share 0.5, at the threshold
    assert device_price.confidence(70, 100, 130) == pytest.approx(0.70)  # share 0.6
    assert device_price.confidence(0, 0, 0) == 0.0
    at = _decide(_lot(bands=_wide(0.5)))
    assert at.approval["confidence"] == pytest.approx(0.75) and at.approval["holds"] == []  # not held at the threshold
    under = _decide(_lot(bands=_wide(0.6)))
    assert under.approval["confidence"] == pytest.approx(0.70)
    assert under.approval["holds"][0]["signals"] == ["wide interval"] and under.approval["holds"][0]["owner"] == "Pricing analyst"


def test_dv_06_the_hold_policy_reads_the_case():
    """The confidence and the holds go on the case the way a tool return's do, for the hold policy (I-10) to read."""
    d = _decide(_lot(bands=_wide(0.6)))
    case: dict = {"id": "D-9100"}
    write_back(case, d)
    assert case["decisionConfidence"] == pytest.approx(0.70) and valuation.confidence({}, case) == pytest.approx(0.70)
    assert [h["id"] for h in case["approvalHolds"]] == ["GR-D8"]
    assert case["approvalRoute"]["role"] == "Approver"


def test_dv_06_channels_overlap_is_a_signal():
    wide = {k: _band(285, 0.3) for k in CHANNELS}  # four channels on the same wide band: the top two overlap fully
    d = _decide(_lot(bands=wide))
    assert next(h for h in d.approval["holds"] if h["id"] == "GR-D8")["signals"] == ["channels overlap"]


def test_dv_06_a_customer_may_raise_the_floor_never_lower_it():
    pack = load_pack("device")
    assert device_price.floor_pct(pack) == 0.55
    raised = overlay.apply_overlay(pack, [overlay.SetParam(id="op-1", op="set_param", path="device.floor", value=0.7, seen=0.55)])
    assert device_price.floor_pct(raised) == 0.7
    with pytest.raises(OverlayError):
        overlay.apply_overlay(pack, [overlay.SetParam(id="op-2", op="set_param", path="device.floor", value=0.4, seen=0.55)])
    lot = _lot(200, bands={k: _band(120) for k in CHANNELS})  # best cash a little over 55% and under 70% of 200
    assert not [h for h in _decide(lot).approval["holds"] if h["id"] == "GR-D2"]
    assert [h for h in _decide(lot, raised).approval["holds"] if h["id"] == "GR-D2"]
