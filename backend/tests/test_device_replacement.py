"""P9-6.16 (story DV-12): replacement stock as a device channel.

A received device of grade A or B in the `0-24m` age band can fill an open replacement demand for its SKU: the cash is the
avoided purchase (the demand's `unit_cost`) less the prep and logistics cost, with the reason "Avoids buying a replacement:
$340". Each demand unit is reserved by one case only, at the decision's approval (`decision.approve`, a person's action,
or the standing policy); a second case sees the remaining quantity, and a case that finds none left is refused at approval.
Nothing here writes language and no action is new, so there is no model call (R16) and no change to `forbidden.py` (R21):
the reservation is a step of the existing approval. The route is recover-only (a PO lot never has it) and not a path of the
default flow. Prep and logistics are the pack's defaults (R8: a customer sets its own in its overlay layer).
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories import device_market
from di.services.cases import intake, store
from di.services.device import inputs, replacement
from di.services.device import intake as device_intake
from di.services.execution.steps import EX_STEP, STEP_TPL, ex_kinds
from di.services.modeler.pack import load_pack
from di.services.modeler.templates import template_of_pack
from di.services.modeler.valuers import device, device_price
from tests import starting
from tests.device_registry import seed_registry
from tests.helpers import call

ORG = "Customer A"
SKU = "iPhone 15|128"
TODAY = clock.now().date()


def _lot(*, grade: str = "B", band: str = "0-24m", demand: dict | None = None, qty: int = 1) -> dict:
    lot = intake.device_lot("D-9160", {"grade": grade, "band": band, "ref": 300, "qty": qty, "model": "iPhone 14"})
    lot |= {"imei": "359990000000160", "sku_key": "iPhone 14|128", "storage_gb": 128, "quote": {"amount": 410}}
    lot["inputs"] = {"feed_price": 300, "feed_stale": False, "sales_90d": 50, "bands": {}, "replacement": demand}
    return lot


OPEN5 = {"demand_id": "RD-1", "unit_cost": 340.0, "open": 5}


def _by(lot: dict) -> dict[str, dict]:
    return {v["k"]: v for v in device.decide(lot, [])["all"]}


def test_dv_12_replacement_stock_avoided_purchase():
    v = _by(_lot(demand=OPEN5))["replacement"]
    assert v["ok"] and v["cash"] == pytest.approx(340 - 9 - 6) == pytest.approx(325)
    assert v["why"] == "Avoids buying a replacement: $340"
    assert v["replacement"] == {"demand_id": "RD-1", "unit_cost": 340.0, "open": 5}
    row = next(x for x in device_price.channels_view(_lot(demand=OPEN5)) if x["k"] == "replacement")
    assert row["name"] == "Replacement stock" and row["ok"] and row["cash"] == pytest.approx(325)
    assert row["replacement"] == {"demandId": "RD-1", "unitCost": 340.0, "open": 5}
    # a route of its own: after the others, steps reserve, move, finance, named in the pack
    assert list(_by(_lot(demand=OPEN5)))[-1] == "replacement" and device.DCN["replacement"] == "Replacement stock"
    assert STEP_TPL["replacement"] == ["reserve", "move", "finance"]
    assert all(k in EX_STEP for k in ex_kinds({"id": "replacement"}))


def test_dv_12_grade_c_not_eligible():
    for grade in ("C", "D"):
        v = _by(_lot(grade=grade, demand=OPEN5))["replacement"]
        assert not v["ok"] and v["why"] == "Replacement stock takes grade A or B" and "replacement" not in v
    v = _by(_lot(band="25-48m", demand=OPEN5))["replacement"]  # the age band is the pack's `0-24m`
    assert not v["ok"] and v["why"] == "Replacement stock is for the 0-24m age band"
    assert _by(_lot(grade="A", demand=OPEN5))["replacement"]["ok"]


def test_dv_12_no_demand_is_ineligible_and_bulk_lots_are_not_replaced():
    for demand in (None, {}):
        v = _by(_lot(demand=demand))["replacement"]
        assert not v["ok"] and v["why"] == "No open replacement demand"
    assert not _by(_lot(demand=OPEN5, qty=3))["replacement"]["ok"]  # one demand unit, one device


def test_dv_12_recover_only_not_in_the_default_flow():
    pack = load_pack("device")
    assert "replacement" in {r.id for r in pack.routes if r.recover_only}
    assert "replacement" not in [p.id for p in template_of_pack(pack).paths]
    po = device.sample_lots()[0]
    assert "replacement" not in device.channels_for(po) and "replacement" in device.channels_for(_lot())


# ---------------------------------------------------------------- the database
def _clean() -> None:
    with engine.begin() as conn:
        for t in ("device_tradein", "device_price_point", "device_replacement_demand"):
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


def _demand(did: str = "RD-1", qty: int = 5, cost: float = 340, grade_min: str = "B", sku: str = SKU) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_replacement_demand (id, sku_key, grade_min, qty, unit_cost, needed_by) "
                "VALUES (:i, :k, :g, :q, :c, NULL)"
            ),
            {"i": did, "k": sku, "g": grade_min, "q": qty, "c": cost},
        )


def _reserved(did: str = "RD-1") -> list[str]:
    with SessionLocal() as s:
        return list(s.execute(text("SELECT reserved FROM device_replacement_demand WHERE id = :i"), {"i": did}).scalar_one())


def test_dv_12_demand_filled_once():
    _demand(qty=5)
    with SessionLocal() as s:
        assert [device_market.reserve_replacement(s, "RD-1", f"D-{n}") for n in range(1, 7)] == [True] * 5 + [False]
        assert device_market.reserve_replacement(s, "RD-1", "D-2")  # the same case again: still one unit, not two
        assert device_market.replacement_demand(s, SKU, "B", TODAY) == 0
        s.commit()
    assert _reserved() == [f"D-{n}" for n in range(1, 6)]
    # the sixth case sees nothing left, so its replacement is ineligible with the reason
    with SessionLocal() as s:
        g = inputs.gather(s, {"id": "D-6", "imei": "359990000000160", "sku_key": SKU, "grade": "B"}, TODAY)
    assert g.replacement is None
    lot = _lot(demand=g.replacement)
    assert _by(lot)["replacement"]["why"] == "No open replacement demand" and not _by(lot)["replacement"]["ok"]
    # a case that holds a unit still sees its own (a later valuation of an approved case keeps the route)
    with SessionLocal() as s:
        mine = inputs.replacement_view(s, SKU, "B", "D-3")
        assert mine is not None and mine["demand_id"] == "RD-1" and mine["unit_cost"] == 340 and mine["open"] == 0
        # released again, a unit is open for the next case
        assert device_market.release_replacement(s, "D-3") == 1
        assert inputs.replacement_view(s, SKU, "B", "D-6") == {"demand_id": "RD-1", "unit_cost": 340.0, "open": 1}
        assert device_market.release_replacement(s, "D-3") == 0


def test_dv_12_demand_filters_by_sku_and_minimum_grade():
    _demand("RD-1", qty=2, cost=340, grade_min="B")
    _demand("RD-2", qty=1, cost=300, grade_min="C", sku="iPhone 15|256")
    with SessionLocal() as s:
        assert inputs.replacement_view(s, "iPhone 15|256", "B", None) == {"demand_id": "RD-2", "unit_cost": 300.0, "open": 1}
        assert inputs.replacement_view(s, "iPhone 15|512", "B", None) is None
        assert inputs.replacement_view(s, SKU, "A", None) == {"demand_id": "RD-1", "unit_cost": 340.0, "open": 2}
        assert inputs.replacement_view(s, SKU, None, None) is None and inputs.replacement_view(s, None, "B", None) is None


# ---------------------------------------------------------------- reserved at approval, released on rejection
def _land(imei: str, tid: str) -> None:
    when = (clock.now() - timedelta(days=5)).isoformat()
    seed_registry(imei)
    with SessionLocal() as s:
        lab.land_tradein(
            s,
            {
                "tradeInId": tid, "imei": imei,
                "sku": {"brand": "Apple", "model": "iPhone 15", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
                "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
                "partner": "P01", "batchId": None, "bulk": False, "receivedAt": when, "payoutAmount": 410,
            },
            ORG,
        )  # fmt: skip
        s.commit()


def _open_two() -> list[str]:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
                "VALUES (:k, 'B', :w, 400, 'USD', 'dvmkt')"
            ),
            {"k": SKU, "w": TODAY - timedelta(days=3)},
        )
    _land("359990000000161", "TI-T-0161")
    _land("359990000000162", "TI-T-0162")
    with SessionLocal() as s:
        ids = device_intake.open_pending(s, ORG)
        s.commit()
    assert len(ids) == 2
    return sorted(ids)


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _approve(cid: str, route: str = "replacement") -> dict:
    assert call("decision.submit", {"case_id": cid}, "admin")["ok"]
    c = _case(cid)
    r = next(x for x in c["routes"] if x["id"] == route)
    body = {"case_id": cid, "reviewed": True, "rationale": "Fills the open demand.", "route": r["plan"]}
    return call("decision.approve" if c["recommendation"]["id"] == route else "decision.override", body, "approver")


def test_dv_12_case_values_the_demand_when_it_opens():
    _demand(qty=1)
    a, _b = _open_two()
    c = _case(a)
    assert c["valuer"]["inputs"]["replacement"] == {"demand_id": "RD-1", "unit_cost": 340.0, "open": 1}
    r = next(x for x in c["routes"] if x["id"] == "replacement")
    assert not r["excluded"] and r["plan"] == "Replacement stock" and r["why"] == "Avoids buying a replacement: $340"
    assert ex_kinds(r) == ["reserve", "move", "finance", "credit"]


def test_dv_12_reserved_at_approval_and_refused_when_taken():
    _demand(qty=1)
    a, b = _open_two()
    assert _reserved() == []  # opening a case reserves nothing
    done = _approve(a)
    assert done["ok"], done
    assert _reserved() == [a]
    assert [s["k"] for s in _case(a)["exec"]["steps"]] == ["reserve", "move", "finance", "credit"]
    # the other case was valued before the unit was taken; its approval finds none left and is refused, reserving nothing
    refused = _approve(b)
    assert not refused["ok"] and refused["error"]["code"] == "conflict"
    assert refused["error"]["message"] == "No open replacement demand"
    assert _reserved() == [a] and _case(b).get("exec") is None
    # its next valuation shows the route ineligible with the same reason
    with SessionLocal() as s:
        c = store.get(s, b)
        assert c is not None
        inputs.refresh_listing(s, c, TODAY)
        assert c["valuer"]["inputs"]["replacement"] is None
    assert _by(c["valuer"])["replacement"]["why"] == "No open replacement demand"


def test_dv_12_another_route_reserves_nothing_and_a_decline_releases():
    _demand(qty=2)
    a, b = _open_two()
    assert _approve(a, "parts")["ok"] and _reserved() == []
    # a unit held for a case that is then declined goes back to the demand
    with SessionLocal() as s:
        assert device_market.reserve_replacement(s, "RD-1", b)
        s.commit()
    assert call("decision.submit", {"case_id": b}, "admin")["ok"]
    assert call("decision.decline", {"case_id": b, "reason": "Not wanted."}, "approver")["ok"]
    assert _reserved() == []
    with SessionLocal() as s:  # the helpers a hook calls: nothing to do for a case that reserved nothing
        assert replacement.on_decline(s, {"id": b}) == 0
