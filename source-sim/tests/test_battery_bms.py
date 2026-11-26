"""Plan 9 P9-12.7: call the synthetic battery management mock (bat_bms): the packs with their state of health. Stories NS-BAT-01 to
NS-BAT-03. The mock is no demo source (sim/core/registry.py EXTRA_SYSTEMS); API key in `x-api-key`.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/battery-bms/api"
KEY = {"x-api-key": "bat_bms-demo-key"}
FIELDS = {"packId", "vinRef", "chemistry", "sohPct", "expectedLifeYears", "readAt", "thermalEvent", "damaged", "safetyClass",
          "market"}  # fmt: skip


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "bat_bms"}).raise_for_status()
        yield c


def packs(client):
    r = client.get(f"{API}/packs", headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["bat_bms"]
    assert (s.vendor, s.style, s.base_path) == ("Battery management data (synthetic)", "vendor", "/battery-bms")
    assert "bat_bms" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "bat_bms" in MOCKS


def test_packs_need_the_key(client):
    assert client.get(f"{API}/packs").status_code == 401
    assert client.get(f"{API}/packs", headers={"x-api-key": "wrong"}).status_code == 401


def test_pack_shape_and_the_car_link(client):
    rows = packs(client)
    assert rows and all(set(r) == FIELDS for r in rows)
    by = {r["packId"]: r for r in rows}
    assert by["BP-044"]["vinRef"] == "SYNUC000000000044" and by["BP-044"]["market"] == "EU"
    assert by["BP-044"]["chemistry"] in ("NMC", "LFP") and by["BP-044"]["sohPct"] == 74
    assert any(r["damaged"] for r in rows) and any(r["thermalEvent"] for r in rows)
    assert any(r["market"] == "US" for r in rows) and any(r["vinRef"] is None for r in rows)  # an industrial pack has no car


def test_battery_seed_is_the_same_twice(client):
    before = packs(client)
    client.post("/_sim/reset", params={"system": "bat_bms"}).raise_for_status()
    assert packs(client) == before
