"""Plan 9 P9-11.5: call the synthetic parts supplier portal (mr_parts) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
Stories: MR-08 (what a part costs, how long it takes, what a harvested one is worth), MR-10.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/parts-portal/api"
KEY = {"x-api-key": "mr_parts-demo-key"}
PUMP = "Synthetic Volumetric Pump V2"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "mr_parts"}).raise_for_status()
        yield c


def parts(client, **params) -> list[dict]:
    r = client.get(f"{API}/parts", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_parts_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["mr_parts"]
    assert (s.vendor, s.style, s.base_path) == ("Parts supplier portal (synthetic)", "vendor", "/parts-portal")
    assert "mr_parts" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mr_parts" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_parts_need_the_key(client):
    assert client.get(f"{API}/parts").status_code == 401
    assert client.get(f"{API}/parts", headers={"x-api-key": "wrong"}).status_code == 401


def test_parts_prices_and_leads(client):
    rows = parts(client, model=PUMP)
    assert all(set(r) == {"partNo", "label", "price", "leadDays", "harvestValue", "model"} for r in rows)
    by = {r["label"]: r for r in rows}
    assert by["Pump motor"]["price"] == 240 and by["Controller"]["price"] == 310
    assert all(r["leadDays"] > 0 and 0 < r["harvestValue"] < r["price"] and r["model"] == PUMP for r in rows)
    assert by["Pump motor"]["leadDays"] < by["Controller"]["leadDays"]  # the controller is the slower part
    assert len({r["partNo"] for r in rows}) == len(rows)
    every = parts(client)
    assert {r["model"] for r in every} >= {PUMP, "Synthetic Smart Pump S4", "Synthetic Bedside Monitor B1"}
    assert len({(r["model"], r["partNo"]) for r in every}) == len(every) > len(rows)
    assert client.get(f"{API}/parts", params={"model": "Nothing"}, headers=KEY).status_code == 404
