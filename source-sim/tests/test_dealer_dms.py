"""Plan 9 P9-9.2: call the synthetic dealer management system (uc_dms) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import scheduler
from sim.core.db import engine
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/dealer-dms/api/v1"
KEY = {"x-api-key": "uc_dms-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_dms"}).raise_for_status()
        yield c


def listing(client, path: str, **params) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        r = client.get(f"{API}{path}", params={"limit": 25, "offset": offset} | params, headers=KEY)
        assert r.status_code == 200, r.text
        out += r.json()["items"]
        offset = r.json()["next"]
    return out


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_dms"]
    assert (s.vendor, s.style, s.base_path) == ("Dealer management system (synthetic)", "vendor", "/dealer-dms")
    assert "uc_dms" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_dms" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_dms_needs_the_key(client):
    assert client.get(f"{API}/lots").status_code == 401
    assert client.post(f"{API}/transfers", json={}).status_code == 401


def test_dms_trade_ins(client):
    rows = listing(client, "/trade-ins")
    assert [r["vin"] for r in rows] == [vin(n) for n in range(61, 101)]
    assert set(rows[0]) == {
        "tradeId", "vin", "tradeAllowance", "payoffAmount", "payoffConfirmed", "mileage", "modelYear", "segment",
        "powertrain", "receivedAt", "store",
    }  # fmt: skip
    assert {r["vin"] for r in rows if not r["payoffConfirmed"]} == {vin(62)}


def test_dms_lots_and_lot_sales(client):
    lots = listing(client, "/lots")
    assert [(x["lotId"], x["name"], x["distanceMiles"]) for x in lots] == [
        ("LOT-N", "North lot", 12), ("LOT-C", "Central lot", 40), ("LOT-S", "South lot", 95),
    ]  # fmt: skip
    suv = listing(client, "/lot-sales", segment="suv")
    assert len(suv) == 12
    cell = {x["lotId"]: x for x in suv if x["mileageBand"] == "0-40k"}
    assert [cell[lot]["avgPrice"] for lot in ("LOT-N", "LOT-C", "LOT-S")] == [23600, 24000, 24300]
    assert [(cell[lot]["avgDaysToSale"], cell[lot]["count"], cell[lot]["spread"]) for lot in ("LOT-N", "LOT-C", "LOT-S")] == [
        (34, 12, 1500), (21, 22, 1300), (15, 18, 1200),
    ]  # fmt: skip
    ev = listing(client, "/lot-sales", segment="ev_crossover")
    for band in {x["mileageBand"] for x in ev}:
        days = {x["lotId"]: x["avgDaysToSale"] for x in ev if x["mileageBand"] == band}
        assert days == {"LOT-N": 58, "LOT-C": 33, "LOT-S": 29}
    assert len(listing(client, "/lot-sales")) == 60
    assert {x["lotId"] for x in listing(client, "/lot-sales", lotId="LOT-C")} == {"LOT-C"}
    assert {x["mileageBand"] for x in suv} == {"0-40k", "40-80k", "80-120k", "120k+"}


def test_dms_partner_bids_and_stock(client):
    bids = listing(client, "/partner-bids", vin=vin(1))
    assert [b["amount"] for b in bids] == [20900] and bids[0]["vin"] == vin(1)
    assert listing(client, "/partner-bids", vin=vin(99)) == []
    stock = listing(client, "/stock")
    assert len(stock) == 30 and len({s["vin"] for s in stock}) == 30
    assert min(s["daysOnLot"] for s in stock) == 3 and max(s["daysOnLot"] for s in stock) == 72
    old = [s for s in stock if s["daysOnLot"] > 45]
    assert len(old) == 7
    assert sorted(s["vin"] for s in old if s["segment"] == "ev_crossover" and s["lotId"] == "LOT-N") == [
        vin(n) for n in range(41, 46)
    ]


def test_dms_writes_are_idempotent(client):
    body = {"vin": vin(1), "estimate": 1200, "lines": [{"part": "brake pads", "cost": 300}]}
    one = client.post(f"{API}/recon-orders", json=body, headers=KEY | {"Idempotency-Key": "k-1"})
    two = client.post(f"{API}/recon-orders", json=body, headers=KEY | {"Idempotency-Key": "k-1"})
    assert one.status_code == 201 and two.status_code == 200 and one.json() == two.json()
    assert one.json()["vin"] == vin(1) and one.json()["estimate"] == 1200
    other = client.post(f"{API}/recon-orders", json=body, headers=KEY | {"Idempotency-Key": "k-2"})
    assert other.status_code == 201 and other.json()["orderId"] != one.json()["orderId"]
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM dealer_dms.written WHERE kind = 'recon-orders'")).scalar_one()
    assert n == 2


def test_dms_other_writes_and_validation(client):
    t = client.post(f"{API}/transfers", json={"vin": vin(41), "fromLot": "LOT-N", "toLot": "LOT-S"}, headers=KEY)
    assert t.status_code == 201 and (t.json()["fromLot"], t.json()["toLot"]) == ("LOT-N", "LOT-S")
    body = {"vin": vin(1), "lotId": "LOT-C", "price": 24000, "disclosures": ["prior lease"]}
    li = client.post(f"{API}/listings", json=body, headers=KEY)
    assert li.status_code == 201 and li.json()["listingId"]
    trade = {"vin": vin(1), "partner": "Partner A", "price": 20900, "titleRef": "T-1"}
    tr = client.post(f"{API}/dealer-trades", json=trade, headers=KEY)
    assert tr.status_code == 201 and tr.json()["titleRef"] == "T-1"
    same = {"vin": vin(41), "fromLot": "LOT-N", "toLot": "LOT-N"}
    assert client.post(f"{API}/transfers", json=same, headers=KEY).status_code == 422
    unknown = {"vin": vin(41), "fromLot": "LOT-N", "toLot": "LOT-X"}
    assert client.post(f"{API}/transfers", json=unknown, headers=KEY).status_code == 422
    assert client.post(f"{API}/recon-orders", json={"vin": vin(1)}, headers=KEY).status_code == 422
    assert client.post(f"{API}/listings", content=b"nope", headers=KEY).status_code == 400


def _sold_events() -> list[dict]:
    sql = text("SELECT data FROM sim.outbox WHERE source = 'uc_dms' AND type = 'dms.listing.sold' ORDER BY id")
    with engine.connect() as conn:
        return [r.data for r in conn.execute(sql)]


def test_uc_23_listing_sells_after_the_lots_average_days_to_sale(client):
    """VIN ...001 (an SUV, 38,000 miles) listed at LOT-S sells at that lot's 24,300 after its 15 days, once, with an event."""
    body = {"vin": vin(1), "lotId": "LOT-S", "price": 25000, "disclosures": []}
    made = client.post(f"{API}/listings", json=body, headers=KEY | {"Idempotency-Key": "k-sale-1"})
    assert made.status_code == 201
    again = client.post(f"{API}/listings", json=body, headers=KEY | {"Idempotency-Key": "k-sale-1"})
    assert again.status_code == 200  # a repeat schedules no second sale
    mine = {"vin": vin(1), "lotId": "LOT-S"}
    scheduler.tick()
    assert listing(client, "/sales", **mine) == []
    client.post("/_sim/clock/advance", json={"days": 14}).raise_for_status()
    scheduler.tick()
    assert listing(client, "/sales", **mine) == []  # day 14: not yet
    client.post("/_sim/clock/advance", json={"days": 1}).raise_for_status()
    scheduler.tick()
    (sold,) = listing(client, "/sales", **mine)
    assert (sold["listingId"], sold["price"], sold["daysToSale"]) == (made.json()["listingId"], 24300, 15)
    assert set(sold) == {"listingId", "vin", "lotId", "price", "listedAt", "soldAt", "daysToSale"}
    scheduler.tick()
    assert listing(client, "/sales", **mine) == [sold]
    mine_event = [e for e in _sold_events() if e["vin"] == vin(1) and e["price"] == 24300]
    assert [(e["vin"], e["price"], e["soldAt"]) for e in mine_event] == [(vin(1), 24300, sold["soldAt"])]
    client.post("/_sim/clock/reset").raise_for_status()


def test_uc_23_listing_of_an_unknown_car_never_sells(client):
    body = {"vin": "SYNUC000000000999", "lotId": "LOT-C", "price": 20000, "disclosures": []}
    assert client.post(f"{API}/listings", json=body, headers=KEY).status_code == 201
    client.post("/_sim/clock/advance", json={"days": 90}).raise_for_status()
    scheduler.tick()
    assert listing(client, "/sales", vin="SYNUC000000000999") == []
    client.post("/_sim/clock/reset").raise_for_status()
