"""Plan 9, P9-6.12 (story DV-09): a device sold on a channel is listed, settled and learned from.

An approved Recover case on a listing channel (`buynow`, `offers`, `auction`) has a `list` step that posts the listing to
the device market (`dvmkt`), idempotent on `<case id>:<channel>`; a person (or the standing policy) approved it, never an
agent. A sale the market reports for the case lands its `settlement`: the realised price against the forecast P50, computed
(no language model, no model call). Finance confirms the outcome with `outcome.confirm` (forbidden to agents); the
confirmed row is the case's realised net against its predicted one, which `model.fit` learns from. The tests seed their own
sales (ids `SAL-T-*`), never the mock's.
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.connectors.adapters.device_market import DeviceMarketAdapter
from di.connectors.base import Record
from di.connectors.http import SourceError
from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories import device_market, outcomes
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.device import settle
from di.services.execution.steps import EX_STEP, STEP_TPL, ex_kinds
from di.services.instructions import queue, writers
from di.services.modeler.valuers import device
from tests import starting
from tests.device_registry import seed_registry
from tests.helpers import call, client, h

ORG = "Customer A"
IMEI = "359990000000912"
AGENT = {"X-Circularity-Preparer": "gap", "X-Circularity-Confirmed": "true"}


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        for t in ("device_tradein", "device_price_point"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names
        conn.execute(text("DELETE FROM device_sale WHERE sale_id LIKE 'SAL-T-%'"))
        conn.execute(text("DELETE FROM instruction WHERE kind = 'list'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


@pytest.fixture
def sending(monkeypatch):
    """The suite sends no instructions; a test that looks at the queued rows switches sending on."""
    monkeypatch.setattr(queue, "enabled", lambda: True)


def _open() -> dict:
    """A received iPhone 14 (grade B, feed $330) and its case, awaiting approval."""
    when = (clock.now() - timedelta(days=5)).isoformat()
    seed_registry(IMEI)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) "
                "VALUES ('iPhone 14|128', 'B', :w, 330, 'USD', 'dvmkt')"
            ),
            {"w": clock.now().date() - timedelta(days=3)},
        )
    with SessionLocal() as s:
        lab.land_tradein(
            s,
            {
                "tradeInId": "TI-T-0912", "imei": IMEI,
                "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
                "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
                "partner": "P01", "batchId": None, "bulk": False, "receivedAt": when, "payoutAmount": 410,
            },
            ORG,
        )  # fmt: skip
        s.commit()
    from di.services.device import intake as device_intake

    with SessionLocal() as s:
        (cid,) = device_intake.open_pending(s, ORG)
        s.commit()
    return _case(cid)


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _approve(cid: str, route: str = "buynow") -> dict:
    """A person approves the channel (the recommendation, else an override), as the maker-checker pair the pipeline asks for."""
    assert call("decision.submit", {"case_id": cid}, "admin")["ok"]
    c = _case(cid)
    r = next(x for x in c["routes"] if x["id"] == route)
    body = {"case_id": cid, "reviewed": True, "rationale": "Channel reviewed.", "route": r["plan"]}
    return call("decision.approve" if c["recommendation"]["id"] == route else "decision.override", body, "approver")


def _ack(cid: str, step: int) -> dict:
    with SessionLocal() as s:
        r = invoke("adapter.acknowledge", {"case_id": cid, "step": step, "simulated": True}, CallContext(actor=SYSTEM, session=s))
        assert r["ok"], r
        s.commit()
    return r


def _sale(cid: str, price: float, fees: float = 9.54, returns: float = 0, sale_id: str = "SAL-T-1") -> device_market.SaleRow:
    return device_market.SaleRow(sale_id, "LST-T-1", None, [IMEI], price, fees, returns, clock.now(), [cid])


def _forecast(c: dict, channel: str = "buynow") -> float:
    v = c["valuer"]
    band = (v.get("inputs") or {}).get("bands", {}).get(channel)
    return float(band["p50"]) if band else v["ref"] * device.DST[v["grade"]][v["band"]][channel][3]


class Fake:
    """The device market as the writer calls it: a POST with an existing listing id is a 409, as the mock answers."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.calls: list[tuple] = []

    def request(self, method, path, **kw):
        self.calls.append((method, path, kw))
        if method == "POST":
            body = kw["json"]
            if body["listingId"] in self.docs:
                raise SourceError("client", "listings already exists", 409)
            self.docs[body["listingId"]] = body

    def get_json(self, path, **kw):
        self.calls.append(("GET", path, kw))
        return self.docs[path.rsplit("/", 1)[1]]

    def close(self):
        pass


# ---------------------------------------------------------------- the plan and the listing
def test_dv_09_a_listing_channel_has_a_list_step_and_wholesale_does_not():
    assert EX_STEP["list"]["label"] == "List on the channel" and EX_STEP["list"]["sys"] == "Marketplace · listing"
    assert (EX_STEP["list"]["doc"], EX_STEP["list"]["owner"]) == (("LST", "Listing"), "Channel ops")
    for k in ("buynow", "offers", "auction"):
        assert ex_kinds({"id": k, "variant": "listing"}) == ["reserve", "list", "ship", "fulfil", "receipt"]
        assert ex_kinds({"id": k}) == STEP_TPL[k]  # a PO lot: unchanged
    c = _open()
    assert [r.get("variant") for r in c["routes"]] == ["listing", "listing", "listing", None]  # not the wholesale lot
    assert [r["id"] for r in c["routes"]] == ["buynow", "offers", "auction", "wholesale"]


def test_dv_09_listing_instruction(monkeypatch, sending):
    c = _open()
    assert _approve(c["id"])["ok"]
    assert [s["k"] for s in _case(c["id"])["exec"]["steps"]] == ["reserve", "list", "ship", "fulfil", "receipt"]
    _ack(c["id"], 0)  # the reservation is acknowledged: the listing goes next
    with SessionLocal() as s:
        (ins,) = [r for r in queue.for_case(s, c["id"]) if r["kind"] == "list"]
    assert ins["system"] == "dvmkt" and ins["step"] == 1 and ins["status"] == "queued"
    fake = Fake()
    monkeypatch.setattr(writers, "client", lambda s, source: fake)
    outs = []
    for _ in range(2):
        with SessionLocal() as s:
            outs.append(writers.WRITERS["list"](s, ins, _case(c["id"]), {}))
    assert list(fake.docs) == [f"LST-{c['id']}-buynow"]
    body = fake.docs[f"LST-{c['id']}-buynow"]
    assert (body["imei"], body["channel"], body["status"]) == (IMEI, "Buy Now", "live")
    assert body["price"] == pytest.approx(round(_forecast(c), 2)) and body["caseKey"] == f"{c['id']}:buynow"
    assert [x[0] for x in fake.calls] == ["POST", "POST", "GET"]  # the second POST is a 409, then the writer reads the first
    assert outs[0].doc_ref == outs[1].doc_ref == f"LST-{c['id']}-buynow" and outs[1].detail["duplicate"] is True


def test_dv_09_a_wholesale_case_lists_nothing():
    c = _open()
    wholesale = next(r for r in c["routes"] if r["id"] == "wholesale")
    assert ex_kinds(wholesale) == STEP_TPL["wholesale"] and "list" not in ex_kinds(wholesale)
    assert settle.listing_body(c | {"chosen": wholesale}) is None


# ---------------------------------------------------------------- the sale
def test_dv_09_settlement_posts_realised_vs_forecast():
    c = _open()
    assert _approve(c["id"])["ok"]
    for k in range(4):
        _ack(c["id"], k)
    forecast = _forecast(c)
    price = round(forecast * 0.986, 2)
    with SessionLocal() as s:
        settle.on_sale(s, _sale(c["id"], price))
        s.commit()
    _ack(c["id"], 4)
    got = _case(c["id"])
    st = got["settlement"]
    assert st["price"] == price and st["fees"] == 9.54 and st["buyer_returns"] == 0 and st["sale_id"] == "SAL-T-1"
    assert st["forecast_p50"] == pytest.approx(round(forecast, 2))
    assert st["realised_vs_forecast"] == pytest.approx(round(price / st["forecast_p50"], 4))
    assert 0.98 < st["realised_vs_forecast"] < 0.99 and got["stage"] == "closed"
    page = client.get(f"/api/screens/case/{c['id']}", headers=h("admin")).json()["case"]["device"]["settlement"]
    assert (page["price"], page["fees"], page["buyerReturns"], page["saleId"]) == (price, 9.54, 0, "SAL-T-1")
    assert page["realisedVsForecast"] == st["realised_vs_forecast"] and page["forecastP50"] == st["forecast_p50"]


def test_dv_09_a_sale_lands_once_and_a_sale_without_a_case_changes_nothing():
    c = _open()
    assert _approve(c["id"])["ok"]
    with SessionLocal() as s:
        settle.on_sale(s, _sale(c["id"], 300))
        settle.on_sale(s, _sale(c["id"], 250, sale_id="SAL-T-2"))  # a second sale does not move a settled case
        settle.on_sale(s, device_market.SaleRow("SAL-T-3", None, None, ["1"], 5, 1, 0, clock.now(), ["RT-9999"]))
        s.commit()
    assert _case(c["id"])["settlement"]["sale_id"] == "SAL-T-1"


def test_dv_09_the_adapter_settles_a_new_sale_it_lands():
    c = _open()
    assert _approve(c["id"])["ok"]
    doc = {"saleId": "SAL-T-1", "listingId": "LST-T-1", "imeis": [IMEI], "price": 300, "fees": 9, "buyerReturns": 0,
           "settledAt": clock.now().isoformat()}  # fmt: skip
    with engine.begin() as conn:  # the trade-in has its case (the adapter links the sale to it by IMEI)
        conn.execute(text("UPDATE device_tradein SET case_id = :c WHERE imei = :i"), {"c": c["id"], "i": IMEI})
    for _ in range(2):  # a sync twice is a sync once
        with SessionLocal() as s:
            DeviceMarketAdapter.land(s, "sales", [Record("sales", "SAL-T-1", doc)], ORG)
            s.commit()
    got = _case(c["id"])["settlement"]
    assert (got["sale_id"], got["price"]) == ("SAL-T-1", 300)


# ---------------------------------------------------------------- the outcome and learning
def _settled(price: float = 300.0) -> dict:
    c = _open()
    assert _approve(c["id"])["ok"]
    for k in range(4):
        _ack(c["id"], k)
    with SessionLocal() as s:
        settle.on_sale(s, _sale(c["id"], price, fees=9.0))
        s.commit()
    _ack(c["id"], 4)
    return _case(c["id"])


def test_dv_09_error_feeds_calibration():
    c = _settled()
    assert call("outcome.confirm", {"case_id": c["id"]}, "finance")["ok"]
    with SessionLocal() as s:
        rows = [r for r in outcomes.outcome_rows(s) if r["case_id"] == c["id"]]
    (row,) = rows
    st = c["settlement"]
    net = st["price"] - st["fees"] - st["logistics"] - st["buyer_returns"]
    risk = next(t["amt"] for t in c["chosen"]["terms"] if t["kind"] == "risk")
    assert row["template"] == "device" and row["route"] == "buynow" and row["predicted_net"] == c["chosen"]["net"]
    assert row["actual_net"] == pytest.approx(net + risk)
    out = call("model.fit", {"template": "device"}, "planner-a")
    assert out["ok"] and out["output"]["metrics"]["n"] >= 1


def test_dv_09_the_outcome_lines_are_the_settlements():
    c = _settled()
    assert call("outcome.confirm", {"case_id": c["id"]}, "finance")["ok"]
    lines = _case(c["id"])["outcome"]["lines"]
    sale = next(x for x in lines if x["kind"] == "sale")
    assert sale["act"] == pytest.approx(c["settlement"]["price"] - c["settlement"]["fees"] - c["settlement"]["logistics"])
    assert sale["src"] == "Device market sale SAL-T-1" and sale["model"] is None


def test_outcome_confirm_agent_still_refused():
    c = _settled()
    assert forbidden("outcome.confirm")
    r = client.post("/api/actions/outcome.confirm", json={"case_id": c["id"]}, headers=h("finance") | AGENT).json()
    assert not r["ok"] and _case(c["id"]).get("outcome") is None
