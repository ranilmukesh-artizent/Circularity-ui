"""Plan 9 P9-9.13 (UC-04): call the synthetic legacy body-shop system (uc_bodyshop) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). It has no di adapter:
a connector is built from its OpenAPI document (`GET /body-shop/openapi.json`). API key in `x-api-key`.
"""

import math

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/body-shop"
KEY = {"x-api-key": "uc_bodyshop-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_bodyshop"}).raise_for_status()
        yield c


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def page(client, number: int, size: int = 100) -> dict:
    r = client.get(f"{API}/repairs", params={"page": number, "size": size}, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def every_repair(client) -> list[dict]:
    first = page(client, 1)
    out = list(first["repairs"])
    for n in range(2, first["pages"] + 1):
        out += page(client, n)["repairs"]
    return out


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_bodyshop"]
    assert (s.vendor, s.style, s.base_path) == ("Legacy body-shop system (synthetic)", "generic-rest", "/body-shop")
    assert "uc_bodyshop" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_bodyshop" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_body_shop_needs_the_key(client):
    assert client.get(f"{API}/repairs").status_code == 401
    assert client.get(f"{API}/repairs", headers={"x-api-key": "wrong"}).status_code == 401
    r = client.get(f"{API}/openapi.json")  # the description of the API is open: a connector is built from it
    assert r.status_code == 200 and r.json()["openapi"].startswith("3.0")


def test_uc_04_body_shop_seed_is_600_repairs_over_100_cars(client):
    rows = every_repair(client)
    assert len(rows) == 600 and len({r["repairId"] for r in rows}) == 600
    assert {r["vin"] for r in rows} == {vin(n) for n in range(1, 101)}
    assert all(sum(1 for r in rows if r["vin"] == vin(n)) == 6 for n in (1, 50, 100))
    first = rows[0]
    assert set(first) == {"repairId", "vin", "damageArea", "repairDate", "cost", "insuranceClaim"}
    assert isinstance(first["cost"], int | float) and isinstance(first["insuranceClaim"], bool)
    assert all(len(r["repairDate"]) == 10 and r["repairDate"] < "2026-10-08" for r in rows)  # a date, before the demo's now
    assert page(client, 1) == page(client, 1)  # fixed: the same page twice


def test_body_shop_paging(client):
    p = page(client, 1, 50)
    assert (p["page"], p["pages"], len(p["repairs"])) == (1, 12, 50)
    assert len(page(client, 12, 50)["repairs"]) == 50 and page(client, 13, 50)["repairs"] == []
    assert page(client, 1)["pages"] == math.ceil(600 / 100)
    default = client.get(f"{API}/repairs", headers=KEY).json()
    assert (default["page"], len(default["repairs"])) == (1, 50)
    for bad in ({"page": 0}, {"size": 101}, {"size": "x"}):
        r = client.get(f"{API}/repairs", params=bad, headers=KEY)
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_uc_04_openapi_describes_the_next_endpoint(client):
    doc = client.get(f"{API}/openapi.json").json()
    assert list(doc["paths"]) == ["/repairs"] and doc["servers"] == [{"url": "/body-shop"}]
    get = doc["paths"]["/repairs"]["get"]
    params = {p["name"]: p for p in get["parameters"]}
    assert set(params) == {"page", "size"} and params["size"]["schema"]["maximum"] == 100
    schema = doc["components"]["schemas"]
    assert set(schema["RepairPage"]["properties"]) == {"repairs", "page", "pages", "total"}
    assert set(schema["Repair"]["properties"]) == {"repairId", "vin", "damageArea", "repairDate", "cost", "insuranceClaim"}
    assert doc["components"]["securitySchemes"]["apiKey"] == {"type": "apiKey", "in": "header", "name": "x-api-key"}
    assert doc["security"] == [{"apiKey": []}]
