"""P9-6.19 (story DV-15): the undercut and parts declaration checks of a device's channels.

GR-D5: the `market` channel is excluded when its cash price is below the live Buy Now price of the same SKU and grade
(`inputs.live_buynow`); no live Buy Now listing (a PO lot has none) changes nothing. GR-D9: a Recover device (a lot with an
IMEI whose case opened with a `parts_status` fact, `gather` always leaves one) without a genuine-parts declaration cannot be
listed on Buy Now, Offers or Auction; wholesale is unaffected; a `non_genuine` declaration is allowed and shown. Counted, never
a model's guess (R16): the checks are code over the listing and the lab's declaration.
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.device import inputs
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import device
from tests.test_device_channels import _lot

LISTING = ("buynow", "offers", "auction")
IMEI = "359990000009199"


def _market_lot(live: float | None) -> dict:
    """A PO lot (no IMEI), as the sample lots are, with the listing facts a market lot would carry."""
    lot = _lot(imei=False)
    lot["inputs"] = {"live_buynow": live}
    return lot


def _by(lot: dict) -> dict[str, dict]:
    return {v["k"]: v for v in device.decide(lot)["all"]}


def test_dv_15_marketplace_undercut_blocked():
    lot = _market_lot(None)
    cash = _by(lot)["market"]["cash"]
    assert _by(lot)["market"]["ok"] is True
    live = round(cash) + 15  # a live Buy Now price above the market cash
    v = _by(_market_lot(float(live)))["market"]
    assert v["ok"] is False
    assert v["why"] == f"Marketplace never undercuts the live Buy Now price (GR-D5): ${round(cash)} < ${live}"
    assert _by(_market_lot(float(round(cash) - 15)))["market"]["ok"] is True  # at or above: allowed
    assert [v["ok"] for k, v in _by(lot).items() if k != "market"] == [
        v["ok"] for k, v in _by(_market_lot(float(live))).items() if k != "market"
    ]


def test_dv_15_listing_without_parts_declaration_blocked():
    for status in (None, "unknown"):
        lot = _lot()
        lot["inputs"]["parts_status"] = status
        by = _by(lot)
        for k in LISTING:
            assert by[k]["ok"] is False and by[k]["why"] == "No genuine-parts declaration (GR-D9)", (status, k)
        assert by["wholesale"]["ok"] is True
        best = device.decide(lot)["best"]
        assert best is not None and best["k"] == "wholesale"


def test_dv_15_declared_parts_allow_the_listing_and_non_genuine_is_shown():
    genuine = _lot()
    genuine["inputs"]["parts_status"] = "genuine"
    assert all(_by(genuine)[k]["ok"] and "GR-D9" not in _by(genuine)[k]["why"] for k in LISTING)
    other = _lot()
    other["inputs"]["parts_status"] = "non_genuine"
    for k in LISTING:
        assert _by(other)[k]["ok"] is True and _by(other)[k]["why"] == "Parts declared non-genuine (GR-D9)"


def test_device_po_lots_unchanged():
    lot = device.sample_lots()[0]
    assert all(v["why"] == "" for v in device.decide(lot)["all"])
    assert device.channels_for(lot) == device.DCH


def test_dv_15_gr_d9_is_a_locked_compliance_guardrail_of_the_pack():
    g = next(x for x in load_pack("device").guardrails if x.id == "GR-D9")
    assert (g.type, g.stage, g.locked) == ("Compliance", "decide", True)


@pytest.fixture
def listings():
    def clean() -> None:
        with engine.begin() as c:
            c.execute(text("DELETE FROM device_listing WHERE listing_id LIKE 'LST-T19-%'"))
            c.execute(text("DELETE FROM canonical WHERE key LIKE 'IMEI:3599900000091%'"))

    clean()
    yield
    clean()


def _seed(n: int, imei: str, sku: str, grade: str, channel: str, price: float, status: str = "live") -> None:
    key = f"IMEI:{imei}"
    with engine.begin() as c:
        for model, data in (("asset", {"sku_key": sku}), ("condition", {"cosmetic_grade": grade})):
            c.execute(
                text(
                    "INSERT INTO canonical (model, key, data, version, updated_at) VALUES (:m, :k, CAST(:d AS jsonb), 1, now())"
                ),
                {"m": model, "k": key, "d": __import__("json").dumps(data)},
            )
        c.execute(
            text(
                "INSERT INTO device_listing (listing_id, imei, channel, price, listed_at, offers, status, updated_at) "
                "VALUES (:i, :im, :ch, :p, :at, 0, :st, now())"
            ),
            {"i": f"LST-T19-{n}", "im": imei, "ch": channel, "p": price, "st": status, "at": clock.now() - timedelta(days=1)},
        )


def test_dv_15_live_buynow_is_the_lowest_live_price_of_the_same_sku_and_grade(listings):
    _seed(1, "359990000009101", "iPhone 14|128", "B", "Buy Now", 305)
    _seed(2, "359990000009102", "iPhone 14|128", "B", "Buy Now", 330)
    _seed(3, "359990000009103", "iPhone 14|128", "B", "Offers", 250)  # another channel
    _seed(4, "359990000009104", "iPhone 14|128", "C", "Buy Now", 200)  # another grade
    _seed(5, "359990000009105", "iPhone 14|256", "B", "Buy Now", 150)  # another SKU
    _seed(6, "359990000009106", "iPhone 14|128", "B", "Buy Now", 100, status="sold")
    today = clock.now().date()
    with SessionLocal() as s:
        assert inputs.live_buynow(s, "iPhone 14|128", "B", today) == 305
        assert inputs.live_buynow(s, "iPhone 14|128", "A", today) is None
        assert inputs.live_buynow(s, None, "B", today) is None


def test_dv_15_f7_repair_then_sell_carries_the_parts_declaration_check():
    """Repair then sell lists the device on a listing channel, so GR-D9 holds for it as for those channels."""
    from tests.test_device_routes_more import QUOTE
    from tests.test_device_routes_more import _lot as repair_lot

    for status in (None, "unknown"):
        lot = repair_lot()
        lot["inputs"]["parts_status"] = status
        v = _by(lot)["repair_sell"]
        assert v["ok"] is False and v["why"] == "No genuine-parts declaration (GR-D9)", status
    genuine = repair_lot()
    genuine["inputs"]["parts_status"] = "genuine"
    assert _by(genuine)["repair_sell"]["ok"] is True and "GR-D9" not in _by(genuine)["repair_sell"]["why"]
    other = repair_lot()
    other["inputs"]["parts_status"] = "non_genuine"
    v = _by(other)["repair_sell"]
    assert v["ok"] is True and "Parts declared non-genuine (GR-D9)" in v["why"] and device.repair_line(QUOTE) in v["why"]
