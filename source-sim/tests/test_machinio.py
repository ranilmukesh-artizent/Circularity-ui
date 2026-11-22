"""B5b contract tests: call the Machinio mock (Dealer API v1) as its client would."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from sim.core import clock
from sim.core.db import engine
from sim.main import app
from sim.vendors.machinio.seed import OFFERS

API = "/machinio/v1"
KEY = {"X-Api-Key": "mch_demo_circularity_4f7b2e91"}


@pytest.fixture
def client():
    c = TestClient(app)  # no lifespan: the reset builds the schema
    with engine.begin() as conn:
        clock.reset(conn)  # offers expire on the simulated clock; earlier tests may have advanced it
    c.post("/_sim/reset", params={"system": "dlr"}).raise_for_status()
    yield c
    c.post("/_sim/reset", params={"system": "dlr"}).raise_for_status()


def get(client, path, **params):
    r = client.get(API + path, headers=KEY, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def everything(client, path, **params) -> list[dict]:
    out, cursor = [], None
    while True:
        body = get(client, path, limit=10, **params, **({"cursor": cursor} if cursor else {}))
        out += body["data"]
        if not body["meta"]["has_more"]:
            assert body["meta"]["next_cursor"] is None and len(out) == body["meta"]["total"]
            return out
        cursor = body["meta"]["next_cursor"]


def test_auth_and_errors(client):
    r = client.get(API + "/offers")
    assert r.status_code == 401 and r.json()["error"]["code"] == "api_key_missing"
    r = client.get(API + "/offers", headers={"X-Api-Key": "mch_wrong"})
    assert r.status_code == 401 and r.json()["error"] == {
        "type": "authentication_error",
        "code": "api_key_invalid",
        "message": "Invalid API key provided",
    }
    r = client.get(API + "/offers", headers=KEY, params={"colour": "red"})
    assert r.status_code == 400 and r.json()["error"]["param"] == "colour"
    assert client.get(API + "/offers", headers=KEY, params={"cursor": "!!"}).status_code == 400
    assert client.get(API + "/offers", headers=KEY, params={"limit": 101}).status_code == 400
    assert client.get(API + "/offers/MO-1", headers=KEY).json()["error"]["code"] == "resource_missing"
    assert get(client, "/account")["id"] == "acct_7Q2M4K"


def test_rt1048_offer_and_fees(client):
    offers = everything(client, "/offers", stock_number="MTR-2041")
    assert len(offers) == 1
    o = offers[0]
    assert (o["id"], o["offer_amount"], o["offer_currency"], o["status"]) == ("MO-91048", 5600.0, "USD", "open")
    assert o["fees"]["freight_inr"] + o["fees"]["channel_fee_inr"] == round(800 * 83.5) and o["fees"]["total_usd"] == 800.0
    assert o["fees"]["freight_lanes"] == ["WH-PNQ-01>EXT-BOM"] and o["dealer_contact"].endswith(".example")
    firm = everything(client, "/offers", offer_kind="firm")
    assert any(x["offer_amount"] == 460.0 for x in firm)  # RT-1033 "Offer from dealer"
    lot = next(x for x in firm if x["stock_number"] == "BAT-0126")  # RT-1052 "Lot proceeds (20 x $128)"
    assert (lot["offer_type"], lot["quantity"], lot["unit_amount"]) == ("lot", 20, 128.0)


def test_listings_and_listing_demand(client):
    mine = everything(client, "/listings", stock_number="DRL-0812")
    assert len(mine) == 1 and mine[0]["status"] == "active" and mine[0]["listing_age_days"] >= 2
    similar = everything(client, f"/listings/{mine[0]['id']}/similar")
    grade_a = [x for x in similar if x["condition"] == "Excellent"]
    assert len(grade_a) == 14 and all(x["status"] == "active" for x in similar)  # RT-1049: "Grade A listings: 14 open"
    assert len(everything(client, f"/listings/{mine[0]['id']}/similar", condition="Excellent")) == 14
    own = everything(client, "/listings", stock_number="MTR-2041")[0]
    assert len(everything(client, f"/listings/{own['id']}/similar")) == 5
    drafts = everything(client, "/listings", status="draft")  # refurbish-then-sell only: listed after the repair
    assert drafts and all(d["listed_at"] is None and d["listing_age_days"] is None for d in drafts)


def test_delta_by_updated_since(client):
    now = clock.now().isoformat()
    assert get(client, "/offers", updated_since=now)["meta"]["total"] == 0
    assert get(client, "/listings", updated_since=now)["meta"]["total"] == 0
    assert client.get(API + "/offers", headers=KEY, params={"updated_since": "2026-10-07T09:00:00"}).status_code == 400


def test_counter_accept_and_listing_status(client):
    r = client.post(API + "/offers/MO-91048/counter", headers=KEY, json={"amount": 5000})
    assert r.status_code == 400 and r.json()["error"]["param"] == "amount"
    r = client.post(API + "/offers/MO-91048/counter", headers=KEY, json={"amount": 5900, "message": "Best we can do"})
    assert r.status_code == 200 and r.json()["status"] == "countered" and r.json()["counter_amount"] == 5900.0
    assert client.post(API + "/offers/MO-91048/counter", headers=KEY, json={"amount": 6000}).status_code == 409
    r = client.post(API + "/offers/MO-91048/accept", headers=KEY)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert get(client, "/listings/ML-91048-01")["status"] == "pending_sale"
    assert client.post(API + "/offers/MO-91048/decline", headers=KEY).json()["error"]["code"] == "offer_not_open"
    # listing status flow
    r = client.patch(API + "/listings/ML-91048-01", headers=KEY, json={"status": "draft"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "listing_status_transition"
    r = client.patch(API + "/listings/ML-91048-01", headers=KEY, json={"status": "sold"})
    assert r.status_code == 200 and r.json()["status"] == "sold"
    assert client.patch(API + "/listings/ML-91048-01", headers=KEY, json={"price": {"amount": -1}}).status_code == 400
    types = [e["type"] for e in client.get("/_sim/outbox", params={"source": "dlr"}).json()]
    for t in ("machinio.offer.countered", "machinio.offer.accepted", "machinio.listing.updated", "machinio.listing.sold"):
        assert t in types


def test_offer_validity_window_on_the_clock(client):
    # move this offer's window into the past (the shared clock is not advanced)
    past = clock.now() - timedelta(minutes=1)
    with engine.begin() as conn:
        conn.execute(update(OFFERS).where(OFFERS.c.offer_id == "MO-91062").values(expires_at=past))
    o = get(client, "/offers/MO-91062")
    assert o["status"] == "expired" and datetime.fromisoformat(o["updated_at"].replace("Z", "+00:00")) >= past
    r = client.post(API + "/offers/MO-91062/accept", headers=KEY)
    assert r.status_code == 409 and r.json()["error"]["code"] == "offer_expired"
    assert get(client, "/offers/MO-91048")["status"] == "open"
    assert any(e["type"] == "machinio.offer.expired" for e in client.get("/_sim/outbox", params={"source": "dlr"}).json())
