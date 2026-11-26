"""Plan 9 P9-9.6: call the synthetic vehicle auction platform (uc_auction) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`.
"""

from datetime import date
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import clock, scheduler
from sim.core.db import engine
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/vehicle-auction/v1"
KEY = {"x-api-key": "uc_auction-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_auction"}).raise_for_status()
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
    s = EXTRA_BY_ID["uc_auction"]
    assert (s.vendor, s.style, s.base_path) == ("Vehicle auction platform (synthetic)", "vendor", "/vehicle-auction")
    assert "uc_auction" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_auction" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_vehicle_auction_needs_the_key(client):
    assert client.get(f"{API}/fees").status_code == 401
    assert client.get(f"{API}/sales", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/consignments", json={}).status_code == 401


def test_vehicle_auction_fees_and_salvage_bids(client):
    assert client.get(f"{API}/fees", headers=KEY).json() == {"sellFee": 325, "transport": 120}
    bids = {b["vin"]: b for b in listing(client, "/salvage-bids")}
    assert len(bids) == 60 and bids[vin(8)]["amount"] == 3900 and bids[vin(1)]["amount"] == 2100
    one = client.get(f"{API}/salvage-bids", params={"vin": vin(8)}, headers=KEY).json()
    assert one["total"] == 1 and one["items"][0]["amount"] == 3900
    assert one["items"][0]["buyerId"] in {"SB-1", "SB-2", "SB-3"}
    assert client.get(f"{API}/salvage-bids", params={"vin": "SYNUC999"}, headers=KEY).json()["items"] == []


def test_vehicle_auction_sales_one_site_sells_six_days_ahead(client):
    today = clock.now().date()
    sales = listing(client, "/sales")
    assert sales and all(s["daysAhead"] >= 0 for s in sales)
    assert len({s["site"] for s in sales}) == 2
    east = [s for s in sales if s["returnCenter"] == "RC-East"]  # the site VIN ...001 returns to
    nxt = min(east, key=lambda s: s["saleDate"])
    assert nxt["daysAhead"] == (date.fromisoformat(nxt["saleDate"]) - today).days
    weekly = sorted(date.fromisoformat(s["saleDate"]) for s in east)
    assert {(b - a).days for a, b in pairwise(weekly)} == {7}
    if today == clock.AS_OF.date():
        assert nxt["daysAhead"] == 6
    only = listing(client, "/sales", site=nxt["site"])
    assert {s["site"] for s in only} == {nxt["site"]}


def test_vehicle_auction_results_by_segment_and_band(client):
    assert len(listing(client, "/results")) == 20
    suv = listing(client, "/results", segment="suv", band="0-40k")
    assert len(suv) == 1 and suv[0]["avgClearedPrice"] > 0 and suv[0]["count"] > 0
    assert {r["band"] for r in listing(client, "/results", segment="suv")} == {"0-40k", "40-80k", "80-120k", "120k+"}


def test_vehicle_auction_buyers(client):
    buyers = {b["buyerId"]: b for b in listing(client, "/buyers")}
    assert {"SB-1", "SB-2", "SB-3"} <= set(buyers)
    assert buyers["SB-2"]["salvage"] is True and buyers["SB-2"]["titleDbReporting"] is False
    assert buyers["SB-1"]["salvage"] is True and buyers["SB-1"]["titleDbReporting"] is True


def test_consignment_is_idempotent(client):
    body = {"vin": vin(1), "saleDate": "2026-10-13", "titleRef": "TT-0001", "disclosures": ["hail damage"]}
    first = client.post(f"{API}/consignments", json=body, headers=KEY)
    assert first.status_code == 201 and first.json()["consignmentId"] == "CN-0001"
    again = client.post(f"{API}/consignments", json=body, headers=KEY)
    assert again.status_code == 200 and again.json() == first.json()
    keyed = client.post(f"{API}/consignments", json=body | {"vin": vin(2)}, headers=KEY | {"Idempotency-Key": "k1"})
    assert keyed.status_code == 201 and keyed.json()["consignmentId"] == "CN-0002"
    repeat = client.post(f"{API}/consignments", json=body | {"vin": vin(3)}, headers=KEY | {"Idempotency-Key": "k1"})
    assert repeat.status_code == 200 and repeat.json() == keyed.json()


def test_consignment_bad_bodies(client):
    ok = {"vin": vin(1), "saleDate": "2026-10-13", "titleRef": "TT-0001", "disclosures": []}
    for bad in ({**ok, "vin": ""}, {**ok, "saleDate": "soon"}, {**ok, "titleRef": None}, {**ok, "disclosures": "x"}):
        assert client.post(f"{API}/consignments", json=bad, headers=KEY).status_code == 422
    assert client.post(f"{API}/consignments", content=b"not json", headers=KEY).status_code == 400


def test_salvage_sale_to_non_reporting_buyer_refused(client):
    r = client.post(f"{API}/salvage-sales", json={"vin": vin(8), "buyerId": "SB-2"}, headers=KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "buyer_not_reporting"
    unknown = client.post(f"{API}/salvage-sales", json={"vin": vin(8), "buyerId": "SB-99"}, headers=KEY)
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "invalid"
    ok = client.post(f"{API}/salvage-sales", json={"vin": vin(8), "buyerId": "SB-1"}, headers=KEY)
    assert ok.status_code == 201 and ok.json()["salvageSaleId"] == "SS-0001"
    again = client.post(f"{API}/salvage-sales", json={"vin": vin(8), "buyerId": "SB-1"}, headers=KEY)
    assert again.status_code == 200 and again.json() == ok.json()


def test_reset_drops_the_writes_and_the_seed_is_the_same_twice(client):
    before = listing(client, "/salvage-bids")
    client.post("/_sim/reset", params={"system": "uc_auction"}).raise_for_status()
    assert listing(client, "/salvage-bids") == before
    body = {"vin": vin(1), "saleDate": "2026-10-13", "titleRef": "TT-0001", "disclosures": []}
    again = client.post(f"{API}/consignments", json=body, headers=KEY)
    assert again.status_code == 201 and again.json()["consignmentId"] == "CN-0001"


def test_uc_23_consignment_sells_on_its_sale_date_at_the_cleared_price(client):
    """VIN ...001 (an SUV, 38,000 miles) consigned for 13 Oct sells at noon that day at the SUV 0-40k cleared price, once."""
    client.post("/_sim/reset", params={"system": "uc_auction"}).raise_for_status()
    body = {"vin": vin(1), "saleDate": "2026-10-13", "titleRef": "TT-0001", "disclosures": []}
    made = client.post(f"{API}/consignments", json=body, headers=KEY)
    assert made.status_code == 201
    assert client.post(f"{API}/consignments", json=body, headers=KEY).status_code == 200
    scheduler.tick()
    assert listing(client, "/sold", vin=vin(1)) == []
    client.post("/_sim/clock/advance", json={"days": 6}).raise_for_status()  # 7 Oct 09:00 -> 13 Oct 09:00: before noon
    scheduler.tick()
    assert listing(client, "/sold", vin=vin(1)) == []
    client.post("/_sim/clock/advance", json={"hours": 4}).raise_for_status()
    scheduler.tick()
    (sold,) = listing(client, "/sold", vin=vin(1))
    cleared = next(r for r in listing(client, "/results", segment="suv") if r["band"] == "0-40k")["avgClearedPrice"]
    assert (sold["consignmentId"], sold["price"], sold["daysToSale"]) == (made.json()["consignmentId"], cleared, 6)
    assert sold["soldAt"].startswith("2026-10-13T13:00")
    sql = text("SELECT data FROM sim.outbox WHERE source = 'uc_auction' AND type = 'auction.consignment.sold'")
    with engine.connect() as conn:
        events = [r.data for r in conn.execute(sql)]
    assert [(e["vin"], e["price"]) for e in events] == [(vin(1), cleared)]
    client.post("/_sim/clock/reset").raise_for_status()
    client.post("/_sim/reset", params={"system": "uc_auction"}).raise_for_status()
