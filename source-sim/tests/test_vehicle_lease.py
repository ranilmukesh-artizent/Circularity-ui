"""Plan 9 P9-9.2: call the synthetic vehicle lease system (uc_lease) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS), so the demo's
systems and counts stay as they were. API key in `x-api-key`.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/vehicle-lease/api/v1"
KEY = {"x-api-key": "uc_lease-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_lease"}).raise_for_status()
        yield c


def every_return(client, limit=25) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        r = client.get(f"{API}/lease-returns", params={"limit": limit, "offset": offset}, headers=KEY)
        assert r.status_code == 200, r.text
        out += r.json()["items"]
        offset = r.json()["next"]
    return out


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_lease"]
    assert (s.vendor, s.style, s.base_path) == ("Vehicle lease system (synthetic)", "vendor", "/vehicle-lease")
    assert "uc_lease" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_lease" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_lease_returns_need_the_key(client):
    assert client.get(f"{API}/lease-returns").status_code == 401
    assert client.get(f"{API}/lease-returns", headers={"x-api-key": "wrong"}).status_code == 401


def test_lease_returns_paging_and_seed(client):
    first = client.get(f"{API}/lease-returns", params={"limit": 25}, headers=KEY).json()
    assert (len(first["items"]), first["next"], first["total"]) == (25, 25, 60)
    last = client.get(f"{API}/lease-returns", params={"limit": 25, "offset": 50}, headers=KEY).json()
    assert (len(last["items"]), last["next"]) == (10, None)
    rows = every_return(client)
    assert [r["vin"] for r in rows] == [vin(n) for n in range(1, 61)]
    by = {r["vin"]: r for r in rows}
    assert set(rows[0]) == {
        "leaseId", "vin", "lesseeRef", "leaseEnd", "residualValue", "contractMileage", "odometerAtReturn",
        "odometerLastService", "odometerStatementRef", "odometerNotActual", "modelYear", "segment", "powertrain",
        "returnCenter", "sellerFleetSize", "status", "updatedAt",
    }  # fmt: skip
    assert (by[vin(4)]["odometerAtReturn"], by[vin(4)]["odometerLastService"]) == (61240, 46240)
    assert by[vin(5)]["odometerAtReturn"] == 133000
    one = by[vin(1)]
    assert (one["modelYear"], one["segment"], one["odometerAtReturn"], one["residualValue"], one["contractMileage"]) == (
        2022, "suv", 38000, 19500, 36000,
    )  # fmt: skip
    assert one["odometerLastService"] == 38000 and one["powertrain"] == "petrol" and one["status"] == "returned"
    assert {v for v, r in by.items() if r["odometerNotActual"]} == {vin(11), vin(12)}
    assert {v for v, r in by.items() if r["segment"] == "ev_crossover"} == {vin(n) for n in range(41, 49)}
    assert {r["powertrain"] for r in by.values() if r["segment"] == "ev_crossover"} == {"ev"}
    assert {v: r["sellerFleetSize"] for v, r in by.items() if r["sellerFleetSize"]} == {vin(50): 40}
    assert {r["returnCenter"] for v, r in by.items() if int(v[-3:]) <= 30} == {"RC-East"}
    assert {r["returnCenter"] for v, r in by.items() if int(v[-3:]) > 30} == {"RC-West"}
    assert all(r["lesseeRef"].startswith("L-") and r["lesseeRef"][2:].isdigit() for r in rows)


def test_lease_seed_is_the_same_twice(client):
    before = every_return(client)
    client.post("/_sim/reset", params={"system": "uc_lease"}).raise_for_status()
    assert every_return(client) == before


def test_lease_return_by_id_and_updated_since(client):
    rows = every_return(client)
    one = client.get(f"{API}/lease-returns/{rows[3]['leaseId']}", headers=KEY)
    assert one.status_code == 200 and one.json() == rows[3]
    assert client.get(f"{API}/lease-returns/LS-9999", headers=KEY).status_code == 404
    cut = rows[44]["updatedAt"]
    newer = client.get(f"{API}/lease-returns", params={"updatedSince": cut, "limit": 200}, headers=KEY).json()
    assert [r["vin"] for r in newer["items"]] == [r["vin"] for r in rows[45:]] and newer["total"] == 15
    assert client.get(f"{API}/lease-returns", params={"updatedSince": "yesterday"}, headers=KEY).status_code == 400
    assert client.get(f"{API}/lease-returns", params={"limit": 0}, headers=KEY).status_code == 400
