"""Plan 9 P9-12.10: call the synthetic retail returns portal (b2c_ret) the way a JSON-API client does. Stories NS-B2C-01/02.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
No retailer is named; the data is synthetic.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/retail-returns/api"
KEY = {"x-api-key": "b2c_ret-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "b2c_ret"}).raise_for_status()
        yield c


def returns(client, **params) -> list[dict]:
    r = client.get(f"{API}/returns", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["b2c_ret"]
    assert (s.vendor, s.style, s.base_path) == ("Retail returns portal (synthetic)", "vendor", "/retail-returns")
    assert "b2c_ret" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "b2c_ret" in MOCKS


def test_returns_need_the_key(client):
    assert client.get(f"{API}/returns").status_code == 401
    assert client.get(f"{API}/returns", headers={"x-api-key": "wrong"}).status_code == 401


def test_returns_shape_and_classes(client):
    rows = returns(client)
    assert rows and set(rows[0]) == {"itemId", "serial", "imei", "itemClass", "sku", "unsold", "exceptionEvidence"}
    assert {r["itemClass"] for r in rows} == {"phone", "tablet", "apparel", "footwear"}
    assert all(r["imei"] for r in rows if r["itemClass"] in ("phone", "tablet"))
    assert all(r["imei"] is None for r in rows if r["itemClass"] in ("apparel", "footwear"))
    assert all(r["serial"] for r in rows) and len({r["itemId"] for r in rows}) == len(rows)
    assert any(r["unsold"] and r["itemClass"] == "apparel" and r["exceptionEvidence"] is None for r in rows)
    assert any(r["exceptionEvidence"] for r in rows)


def test_returns_seed_is_the_same_twice(client):
    before = returns(client)
    client.post("/_sim/reset", params={"system": "b2c_ret"}).raise_for_status()
    assert returns(client) == before
