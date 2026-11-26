"""P9-6.15 (story DV-11): a received device's routes beyond the sale channels: repair then sell, parts and recycle.

Repair then sell takes the lab's repair quote (cost, the price uplift, extra days) and the best listing channel: cash is the
repaired price net of the channel less the repair cost and the holding cost of the extra days, with the evidence line "battery
swap +$28 price, −$24 cost, +5 days". Parts is the pack's share of the grade-A feed price less the teardown cost; recycle is the
material value less the recycler's fee, through a certified recycler with a certificate. An activation-locked or blacklisted
device may take only `parts` and `recycle` ("as law allows", the gate's `locked_routes`); Compliance's item stays open. A PO lot
keeps its sale channels. All figures are computed from the quote, the feed and the pack: nothing here writes language, so there
is no model call (R16). No new action and no new approvable object (R21): the routes are valued by code and approved as any case.
"""

import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.cases import intake, store
from di.services.device import inputs
from di.services.device import intake as device_intake
from di.services.execution.steps import EX_STEP, STEP_TPL, ex_kinds
from di.services.modeler.pack import load_pack
from di.services.modeler.templates import template_of_pack
from di.services.modeler.valuers import device, routes_adapter
from tests import starting
from tests.device_registry import seed_registry
from tests.helpers import client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
IMEI = "359990000000428"
QUOTE = {"quote_id": "RQ-00428", "repair": "Battery swap", "cost": 24.0, "price_uplift": 28.0, "days": 5.0}
LINE = "battery swap +$28 price, −$24 cost, +5 days"


def _lot(*, quote: dict | None = QUOTE, grade: str = "B", ref: float = 300, qty: int = 1, a: float | None = 360) -> dict:
    lot = intake.device_lot("D-9150", {"grade": grade, "band": "25-48m", "ref": ref, "qty": qty, "model": "iPhone 14"})
    lot |= {"imei": IMEI, "sku_key": "iPhone 14|128", "storage_gb": 128, "quote": {"amount": 410}}
    lot["inputs"] = {
        "feed_price": ref,
        "feed_price_a": a,
        "feed_stale": False,
        "sales_90d": 50,
        "repair_quote": quote,
        "bands": {},
    }
    return lot


def _by(lot: dict) -> dict[str, dict]:
    return {v["k"]: v for v in device.decide(lot, [])["all"]}


def test_dv_11_repair_then_sell_net_of_days():
    lot = _lot()
    v = _by(lot)["repair_sell"]
    want = []
    for ch in (
        "buynow",
        "offers",
        "auction",
    ):  # the formula, channel by channel: repaired price net of the channel, less the cost
        price = lot["ref"] * device.DST["B"]["25-48m"][ch][3] + 28
        cash, days = device._cash(lot, ch, price)
        want.append((cash - 24 - device.DG["hold"] * 5, days + 5, ch))
    best = max(want)
    assert v["ok"] and v["cash"] == pytest.approx(best[0]) and v["days"] == pytest.approx(best[1]) and v["via"] == best[2]
    assert v["why"] == LINE == device.repair_line(QUOTE)
    # the extra days cost money: the same quote with 10 more days is worth exactly the holding cost of them less
    slower = _by(_lot(quote=QUOTE | {"days": 15.0}))["repair_sell"]
    assert slower["cash"] == pytest.approx(v["cash"] - device.DG["hold"] * 10)
    # no quote, no route
    none = _by(_lot(quote=None))["repair_sell"]
    assert not none["ok"] and none["why"] == "No repair quote on file"


def test_dv_11_parts_and_recycle_values():
    by = _by(_lot(grade="B", a=360))
    assert by["parts"]["cash"] == pytest.approx(0.18 * 360 - 6) and by["parts"]["ok"]
    assert by["recycle"]["cash"] == pytest.approx(2.5 - 1.0) and by["recycle"]["ok"]
    assert list(by) == device.channels_for(_lot()) and list(by)[-3:] == ["repair_sell", "parts", "recycle"]
    # without a grade-A feed price: the reference value scaled to grade A
    assert _by(_lot(grade="B", ref=340, a=None))["parts"]["cash"] == pytest.approx(0.18 * 340 / 0.85 - 6)


def test_dv_11_routes_carry_their_steps_and_names():
    assert STEP_TPL["repair_sell"] == ["repair", "reserve", "list", "ship", "fulfil", "receipt"]
    assert STEP_TPL["parts"] == ["teardown", "partsput", "partsxfer", "finance"]
    assert STEP_TPL["recycle"] == ["release", "collect", "process", "cert"]
    assert all(k in EX_STEP for r in ("repair_sell", "parts", "recycle") for k in ex_kinds({"id": r}))
    assert {device.DCN[k] for k in device.EXTRA} == {"Repair then sell", "Parts", "Recycle"}


def test_dv_11_po_lots_have_no_new_routes():
    for lot in device.sample_lots():
        assert device.channels_for(lot) == device.DCH
        assert [v["k"] for v in device.decide(lot)["all"]] == ["buynow", "offers", "auction", "market"]


def test_dv_11_pack_routes_are_recover_only():
    pack = load_pack("device")
    assert {r.id for r in pack.routes if r.recover_only} == {"wholesale", "repair_sell", "parts", "recycle"}
    assert [p.id for p in template_of_pack(pack).paths] == [
        "buynow",
        "offers",
        "auction",
        "market",
    ]  # not a path of the default flow
    assert sorted(routes_adapter.LISTING_CHANNELS) == ["auction", "buynow", "offers"]  # repair then sell is not a listing variant


# ---------------------------------------------------------------- the database
def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw_record WHERE source_id = 'dvlab' AND resource = 'repairQuotes'"))
        for t in ("device_tradein", "device_price_point"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _raw(ext: str, payload: dict, request: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_record (source_id, resource, ext_id, payload, request) "
                "VALUES ('dvlab', 'repairQuotes', :e, CAST(:p AS jsonb), :r)"
            ),
            {"e": ext, "p": json.dumps(payload), "r": request},
        )


def _quote_doc(n: str = "RQ-00428", **over) -> dict:
    return {"quoteId": n, "imei": IMEI, "repair": "Battery swap", "cost": 24, "priceUplift": 28, "days": 5, "currency": "USD",
            "quotedAt": "2026-09-20T16:00:00+00:00"} | over  # fmt: skip


def test_dv_11_gather_reads_the_newest_repair_quote_and_the_grade_a_price():
    _raw("RQ-1", _quote_doc("RQ-1", cost=30, quotedAt="2026-09-19T10:00:00+00:00"))
    _raw("RQ-2", _quote_doc("RQ-2"))
    _raw("RQ-3", _quote_doc("RQ-3", cost=1, quotedAt="2026-09-30T10:00:00+00:00"), request="dry-run sample: GET /repair-quotes")
    _raw("RQ-4", _quote_doc("RQ-4", imei="359990000009999", cost=2, quotedAt="2026-10-01T10:00:00+00:00"))
    day = clock.now().date()
    with engine.begin() as conn:
        for g, p in (("A", 380), ("B", 330)):
            conn.execute(
                text(
                    "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
                    "VALUES ('iPhone 14|128', :g, :w, :p, 'USD', 'dvmkt')"
                ),
                {"g": g, "w": day - timedelta(days=3), "p": p},
            )
    with SessionLocal() as s:
        g = inputs.gather(s, {"imei": IMEI, "sku_key": "iPhone 14|128", "grade": "B"}, day)
        assert inputs.repair_quote(s, "359990000000001") is None and inputs.repair_quote(s, None) is None
    assert g.repair_quote == QUOTE | {"quote_id": "RQ-2"}  # the newest quote of this device; a dry-run sample is never read
    assert g.feed_price_a == 380 and g.feed_price == 330


def _open(**registry) -> dict:
    when = (clock.now() - timedelta(days=5)).isoformat()
    doc = {
        "tradeInId": "TI-00428", "imei": IMEI,
        "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
        "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
        "partner": "P01", "batchId": "BATCH-0011", "bulk": False, "receivedAt": when, "payoutAmount": 410,
    }  # fmt: skip
    seed_registry(IMEI, **registry)
    with SessionLocal() as s:
        lab.land_tradein(s, doc, ORG)
        (cid,) = device_intake.open_pending(s, ORG)
        s.commit()
        c = store.get(s, cid)
    assert c is not None
    return c


@pytest.mark.parametrize("over", [{"lock": "on"}, {"blacklist": "reported_stolen"}, {"finance": "balance_owed"}])
def test_dv_11_locked_parts_or_recycle_only(over):
    c = _open(**over)
    eligible = {r["id"] for r in c["routes"] if not r["excluded"]}
    assert eligible == {"parts", "recycle"}
    assert {r["id"] for r in c["routes"] if r["excluded"]} >= {"buynow", "offers", "auction", "wholesale", "repair_sell"}
    assert all(
        "Blacklist or lock check hit (GR-D7)" in r["failReason"]
        for r in c["routes"]
        if r["id"] in ("buynow", "offers", "auction", "wholesale")
    )
    assert c["recommendation"]["id"] in eligible
    # Compliance still holds the case: its item stays open and the page names the routes the device may still take
    with SessionLocal() as s:
        status = s.execute(
            text("SELECT status FROM work_item WHERE case_id = :c AND type = 'blacklist_hit'"), {"c": c["id"]}
        ).scalars().all()  # fmt: skip
    assert status == ["open"]
    page = client.get(f"/api/screens/case/{c['id']}", headers=h("admin")).json()["case"]["device"]
    assert page["registry"]["allowedRoutes"] == ["parts", "recycle"] and page["registry"]["item"] == "open"
    names = {x["k"]: x["name"] for x in page["channels"]}
    assert names["parts"] == "Parts" and names["recycle"] == "Recycle"


def test_dv_11_page_names_the_repair_evidence():
    _raw("RQ-00428", _quote_doc())
    c = _open()  # a clear registry
    page = client.get(f"/api/screens/case/{c['id']}", headers=h("admin")).json()["case"]["device"]
    row = next(x for x in page["channels"] if x["k"] == "repair_sell")
    assert row["ok"] and row["why"] == LINE
    assert row["repair"] == {"repair": "Battery swap", "cost": 24, "priceUplift": 28, "days": 5}
    assert all("repair" not in x for x in page["channels"] if x["k"] != "repair_sell")
