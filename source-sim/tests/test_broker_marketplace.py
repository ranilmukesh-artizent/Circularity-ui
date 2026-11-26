"""Plan 9 P9-10.5: call the synthetic broker marketplace (tn_broker). Stories TN-07, TN-08, TN-11, TN-24."""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/broker-market/api"
KEY = {"x-api-key": "tn_broker-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "tn_broker"}).raise_for_status()
        yield c


def bids(client, model=None):
    r = client.get(f"{API}/bids", params={"model": model} if model else {}, headers=KEY)
    assert r.status_code == 200
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["tn_broker"]
    assert (s.vendor, s.style, s.base_path) == ("Broker marketplace (synthetic)", "vendor", "/broker-market")
    assert "tn_broker" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "tn_broker" in MOCKS
    assert client.get("/health").json()["missing_schemas"] == []


def test_broker_needs_the_key(client):
    assert client.get(f"{API}/bids").status_code == 401
    assert client.get(f"{API}/cleared", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/listings", json={}).status_code == 401


def test_broker_bids_best_first_per_model(client):
    rru = bids(client, "RRU-4410")
    assert rru[0]["unitPrice"] == 3400 and rru[0]["domestic"] is True and len(rru) >= 2
    assert [b["unitPrice"] for b in rru] == sorted((b["unitPrice"] for b in rru), reverse=True)
    assert set(rru[0]) == {"bidId", "model", "qty", "unitPrice", "buyerCountry", "domestic", "endUserScreening"}
    assert set(rru[0]["endUserScreening"]) == {"result", "ref"}
    assert {b["model"] for b in rru} == {"RRU-4410"}
    assert bids(client, "BBU-2200")[0]["unitPrice"] == 1450 and bids(client, "BBU-2200")[0]["domestic"] is True
    rad = bids(client, "RAD-7700")
    assert len(rad) == 1
    assert (rad[0]["bidId"], rad[0]["qty"], rad[0]["unitPrice"], rad[0]["domestic"]) == ("BID-7700-OS", 40, 1900, False)
    assert rad[0]["endUserScreening"]["result"] == "none"
    assert {b["endUserScreening"]["result"] for b in bids(client)} <= {"clear", "refer", "none"}
    assert bids(client, "NO-SUCH") == []
    assert {b["model"] for b in bids(client)} >= {"RRU-4410", "BBU-2200", "RAD-7700"}


def test_broker_cleared_sales(client):
    r = client.get(f"{API}/cleared", params={"model": "RRU-4410"}, headers=KEY)
    rows = r.json()
    assert r.status_code == 200 and rows and {c["model"] for c in rows} == {"RRU-4410"}
    assert set(rows[0]) == {"saleId", "model", "qty", "unitPrice", "soldAt"}
    assert [c["soldAt"] for c in rows] == sorted((c["soldAt"] for c in rows), reverse=True)
    assert {c["model"] for c in client.get(f"{API}/cleared", headers=KEY).json()} >= {"RRU-4410", "BBU-2200", "RAD-7700"}


def test_broker_listings_are_idempotent(client):
    body = {"serials": ["SN-TN-0002", "SN-TN-0001"], "unitPrice": 3400, "bidId": "BID-4410-A"}
    a = client.post(f"{API}/listings", json=body, headers=KEY)
    b = client.post(f"{API}/listings", json=body | {"serials": ["SN-TN-0001", "SN-TN-0002"]}, headers=KEY)
    assert (a.status_code, b.status_code) == (201, 200) and a.json() == b.json()
    assert a.json()["bidId"] == "BID-4410-A" and a.json()["status"] == "listed"
    assert sorted(a.json()["serials"]) == ["SN-TN-0001", "SN-TN-0002"] and a.json()["unitPrice"] == 3400
    other = client.post(f"{API}/listings", json=body | {"serials": ["SN-TN-0003"]}, headers=KEY)
    assert other.status_code == 201 and other.json()["listingId"] != a.json()["listingId"]


def test_broker_listings_refuse_bad_bodies(client):
    ok = {"serials": ["SN-TN-0009"], "unitPrice": 100, "bidId": "BID-4410-A"}
    bad_bodies = (ok | {"serials": []}, ok | {"serials": "SN-TN-0009"}, ok | {"unitPrice": 0}, ok | {"unitPrice": "x"}, {"serials": ["a"]})
    for bad in bad_bodies:
        assert client.post(f"{API}/listings", json=bad, headers=KEY).status_code == 422
    assert client.post(f"{API}/listings", json=ok | {"bidId": "BID-NOPE"}, headers=KEY).status_code == 404
    assert client.post(f"{API}/listings", content=b"not json", headers=KEY).status_code == 400


def test_broker_seed_is_the_same_twice(client):
    before = (bids(client), client.get(f"{API}/cleared", headers=KEY).json())
    client.post("/_sim/reset", params={"system": "tn_broker"}).raise_for_status()
    assert (bids(client), client.get(f"{API}/cleared", headers=KEY).json()) == before
