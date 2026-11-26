"""Plan 9 P9-10.5: call the synthetic recycler portal (tn_recycler). Stories TN-07, TN-08, TN-11, TN-24."""

import pytest
from fastapi.testclient import TestClient

from sim.core import scheduler
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/recycler-portal/api"
KEY = {"x-api-key": "tn_recycler-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "tn_recycler"}).raise_for_status()
        yield c


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["tn_recycler"]
    assert (s.vendor, s.style, s.base_path) == ("Recycler portal (synthetic)", "vendor", "/recycler-portal")
    assert "tn_recycler" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "tn_recycler" in MOCKS
    assert client.get("/health").json()["missing_schemas"] == []


def test_recycler_needs_the_key(client):
    assert client.get(f"{API}/vendors").status_code == 401
    assert client.get(f"{API}/certificates", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/pickups", json={}).status_code == 401


def test_recycler_vendors(client):
    rows = client.get(f"{API}/vendors", headers=KEY).json()
    by = {v["vendorId"]: v for v in rows}
    assert set(by) == {"RV-1", "RV-2"}
    assert all(set(v) == {"vendorId", "label", "certificate", "dgLane", "regions"} for v in rows)
    assert all(set(v["certificate"]) == {"scheme", "ref", "expires"} for v in rows)
    assert by["RV-1"]["certificate"]["expires"] == "2027-06-30" and by["RV-1"]["dgLane"] is True
    assert by["RV-2"]["certificate"]["expires"] == "2026-10-31"
    assert {v["certificate"]["scheme"] for v in rows} <= {"R2v3", "e-Stewards"}
    assert all(isinstance(v["regions"], list) and v["regions"] for v in rows)


PICKUP = {"serials": ["SN-TN-0010", "SN-TN-0011"], "vendorId": "RV-1", "weeeCategory": "IT-telecom", "weightKg": 42.5}


def test_recycler_pickup_with_an_expired_certificate_is_refused(client):
    r = client.post(f"{API}/pickups", json=PICKUP | {"vendorId": "RV-2"}, headers=KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "certificate_expired"
    assert client.get(f"{API}/certificates", headers=KEY).json() == []


def test_recycler_pickups_are_idempotent_and_validated(client):
    a = client.post(f"{API}/pickups", json=PICKUP, headers=KEY)
    b = client.post(f"{API}/pickups", json=PICKUP | {"serials": list(reversed(PICKUP["serials"]))}, headers=KEY)
    assert (a.status_code, b.status_code) == (201, 200) and a.json() == b.json()
    assert a.json()["vendorId"] == "RV-1" and a.json()["status"] == "scheduled"
    assert sorted(a.json()["serials"]) == PICKUP["serials"]
    for bad in (PICKUP | {"serials": []}, PICKUP | {"weightKg": 0}, PICKUP | {"weeeCategory": ""}, {"vendorId": "RV-1"}):
        assert client.post(f"{API}/pickups", json=bad, headers=KEY).status_code == 422
    assert client.post(f"{API}/pickups", json=PICKUP | {"vendorId": "RV-9"}, headers=KEY).status_code == 404
    assert client.post(f"{API}/pickups", content=b"x", headers=KEY).status_code == 400


def test_recycler_disposal_certificates_arrive_two_days_later(client):
    client.post("/_sim/reset", params={"system": "tn_recycler"}).raise_for_status()
    assert client.post(f"{API}/pickups", json=PICKUP, headers=KEY).status_code == 201
    scheduler.tick()
    assert client.get(f"{API}/certificates", params={"serial": "SN-TN-0010"}, headers=KEY).json() == []  # not yet due
    client.post("/_sim/clock/advance", json={"days": 2, "minutes": 1}).raise_for_status()
    scheduler.tick()
    got = client.get(f"{API}/certificates", params={"serial": "SN-TN-0010"}, headers=KEY).json()
    assert len(got) == 1 and got[0]["serial"] == "SN-TN-0010" and got[0]["vendorId"] == "RV-1"
    assert set(got[0]) == {"certificateId", "serial", "pickupId", "vendorId", "issuedAt"}
    scheduler.tick()
    assert len(client.get(f"{API}/certificates", headers=KEY).json()) == 2  # one per serial, never issued twice
    assert client.get(f"{API}/certificates", params={"serial": "SN-TN-0050"}, headers=KEY).json() == []
    events = client.get("/_sim/outbox", params={"source": "tn_recycler", "limit": 200}).json()
    assert len([e for e in events if e["type"] == "recycler.certificate.issued"]) == 2


def test_recycler_seed_is_the_same_twice(client):
    before = client.get(f"{API}/vendors", headers=KEY).json()
    client.post("/_sim/reset", params={"system": "tn_recycler"}).raise_for_status()
    assert client.get(f"{API}/vendors", headers=KEY).json() == before
