"""Plan 9 P9-12.4: call the synthetic equipment rental system (rf_rental) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`. Story NS-RC-01.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/equipment-rental/api"
KEY = {"x-api-key": "rf_rental-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "rf_rental"}).raise_for_status()
        yield c


def get(client, path: str, **params):
    r = client.get(f"{API}/{path}", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["rf_rental"]
    assert (s.vendor, s.style, s.base_path) == ("Equipment rental system (synthetic)", "vendor", "/equipment-rental")
    assert "rf_rental" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "rf_rental" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_routes_need_the_key(client):
    for p in ("off-rent", "utilisation", "price-index", "damage-claims", "purchase-plans", "idle"):
        assert client.get(f"{API}/{p}").status_code == 401, p


def test_off_rent_and_utilisation(client):
    rows = get(client, "off-rent")
    assert set(rows[0]) == {"machineId", "assetClass", "hours", "branch", "ageYears", "bookValue", "offRentAt"}
    m = next(r for r in rows if r["machineId"] == "M-0001")
    assert (m["assetClass"], m["hours"], m["ageYears"], m["bookValue"], m["branch"]) == ("excavator_20t", 6200, 8, 52000, "BR-1")
    u = get(client, "utilisation")
    assert next(x for x in u if x["branch"] == "BR-1" and x["assetClass"] == "excavator_20t")["utilisation"] == 0.72


def test_price_index_damage_purchase_idle(client):
    p = get(client, "price-index", **{"class": "excavator_20t", "hoursBand": "6000-7000"})
    assert p["price"] == 61000 and p["assetClass"] == "excavator_20t"
    assert get(client, "price-index", **{"class": "nope", "hoursBand": "0-1"}) == {}
    d = get(client, "damage-claims")
    assert d and {"machineId", "renterRef", "amount"} <= set(d[0])
    assert get(client, "purchase-plans")[0]["branch"] == "BR-3"
    i = get(client, "idle")
    assert any(x["machineId"] == "M-0003" and x["idleDays"] == 44 and x["branch"] == "BR-2" for x in i)


def test_seed_is_the_same_twice(client):
    before = get(client, "off-rent")
    client.post("/_sim/reset", params={"system": "rf_rental"}).raise_for_status()
    assert get(client, "off-rent") == before
