"""Plan 9 P9-9.6: call the synthetic vehicle pricing guide (uc_price) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/vehicle-pricing/v3"
KEY = {"x-api-key": "uc_price-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_price"}).raise_for_status()
        yield c


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def value(client, n: int) -> dict:
    r = client.get(f"{API}/values", params={"vin": vin(n)}, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_price"]
    assert (s.vendor, s.style, s.base_path) == ("Vehicle pricing guide (synthetic)", "vendor", "/vehicle-pricing")
    assert "uc_price" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_price" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_vehicle_pricing_needs_the_key(client):
    assert client.get(f"{API}/values", params={"vin": vin(1)}).status_code == 401


def test_vehicle_pricing_values(client):
    one = value(client, 1)
    assert (one["vin"], one["retail"], one["wholesale"], one["segment"], one["band"]) == (
        vin(1), 24000, 21500, "suv", "0-40k",
    )  # fmt: skip
    assert set(one) == {"vin", "retail", "wholesale", "segment", "band", "asOf"} and one["asOf"].startswith("2026-10-07")
    assert value(client, 8)["retail"] == 21000


def test_vehicle_pricing_covers_every_car_and_wholesale_is_below_retail(client):
    for n in (2, 30, 60, 61, 100):
        v = value(client, n)
        assert 0 < v["wholesale"] < v["retail"] and v["band"] in {"0-40k", "40-80k", "80-120k", "120k+"}


def test_vehicle_pricing_errors(client):
    assert client.get(f"{API}/values", params={"vin": "SYNUC000000000999"}, headers=KEY).status_code == 404
    r = client.get(f"{API}/values", headers=KEY)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_vehicle_pricing_seed_is_the_same_twice(client):
    before = value(client, 5)
    client.post("/_sim/reset", params={"system": "uc_price"}).raise_for_status()
    assert value(client, 5) == before
