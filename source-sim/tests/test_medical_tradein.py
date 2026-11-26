"""Plan 9 P9-12.9: call the synthetic medical trade-in register (mc_tradein) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`. Stories NS-MED-01 to NS-MED-03.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/medical-tradein/api"
KEY = {"x-api-key": "mc_tradein-demo-key"}
FIELDS = {
    "tag", "deviceClass", "model", "udi", "singleUse", "hasPatientData", "market", "targetMarket", "serviceRecordRef",
    "recallsClosed",
}  # fmt: skip


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "mc_tradein"}).raise_for_status()
        yield c


def every(client, **params) -> list[dict]:
    r = client.get(f"{API}/tradeins", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["mc_tradein"]
    assert (s.vendor, s.style, s.base_path) == ("Medical trade-in register (synthetic)", "vendor", "/medical-tradein")
    assert "mc_tradein" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mc_tradein" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_tradeins_need_the_key(client):
    assert client.get(f"{API}/tradeins").status_code == 401
    assert client.get(f"{API}/tradeins", headers={"x-api-key": "wrong"}).status_code == 401


def test_seed_shape_and_filter(client):
    rows = every(client)
    assert len(rows) == 12 and rows[0]["tag"] == "SYN-MC-0001" and all(set(r) == FIELDS for r in rows)
    assert {r["deviceClass"] for r in rows} >= {"imaging_system", "patient_monitor", "infusion_pump"}
    assert all(r["hasPatientData"] for r in rows if r["deviceClass"] in ("imaging_system", "patient_monitor"))
    assert any(r["singleUse"] for r in rows) and any(r["targetMarket"] != r["market"] for r in rows)
    assert any(r["udi"] is None for r in rows) and any(not r["recallsClosed"] for r in rows)
    assert [r["tag"] for r in every(client, tag="SYN-MC-0005")] == ["SYN-MC-0005"] and every(client, tag="NOPE") == []


def test_seed_is_the_same_twice(client):
    before = every(client)
    client.post("/_sim/reset", params={"system": "mc_tradein"}).raise_for_status()
    assert every(client) == before
