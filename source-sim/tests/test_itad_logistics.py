"""Plan 9 P9-12.2: call the synthetic ITAD logistics mock (it_logistics): pickups with manifests and custody, and erasures.

The mock is no demo source (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`. Story NS-IT-01.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/itad-logistics/api"
KEY = {"x-api-key": "it_logistics-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "it_logistics"}).raise_for_status()
        yield c


def get(client, path: str, **params):
    r = client.get(f"{API}/{path}", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["it_logistics"]
    assert (s.vendor, s.style, s.base_path) == (
        "ITAD logistics and chain of custody (synthetic)", "vendor", "/itad-logistics",
    )  # fmt: skip
    assert "it_logistics" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "it_logistics" in MOCKS


def test_pickups_and_erasures_need_the_key(client):
    for path in ("pickups", "erasures"):
        assert client.get(f"{API}/{path}").status_code == 401
        assert client.get(f"{API}/{path}", headers={"x-api-key": "wrong"}).status_code == 401


def test_pickup_one_has_two_missing_and_one_extra(client):
    pickups = {p["pickupId"]: p for p in get(client, "pickups")}
    p1 = pickups["PU-01"]
    assert len(p1["manifest"]) == 50 and len(p1["received"]) == 49
    assert set(p1["manifest"]) - set(p1["received"]) == {"SN-IT-0017", "SN-IT-0042"}
    assert set(p1["received"]) - set(p1["manifest"]) == {"SN-IT-9999"}
    assert [c["event"] for c in p1["custody"]] == ["picked_up", "in_transit", "received"]
    assert set(p1["custody"][0]) == {"event", "at", "by"}
    p2 = pickups["PU-02"]
    assert len(p2["manifest"]) == 20 and set(p2["manifest"]) == set(p2["received"])


def test_erasures_by_media_serial(client):
    rows = get(client, "erasures")
    assert rows and set(rows[0]) == {"mediaSerial", "method", "tool", "toolVersion", "verification", "operatorRef", "at"}
    assert {r["method"] for r in rows} <= {"clear", "purge", "destruct"}
    by = {r["mediaSerial"]: r for r in rows}
    assert by["MS-IT-0004-1"]["method"] == "clear" and by["MS-IT-0008-1"]["verification"] == "failed"
    assert [r["mediaSerial"] for r in get(client, "erasures", mediaSerial="MS-IT-0001-1")] == ["MS-IT-0001-1"]
    assert not any(r["mediaSerial"].startswith("MS-IT-9999") for r in rows)  # the extra serial has no erasure record


def test_logistics_seed_is_the_same_twice(client):
    before = get(client, "pickups"), get(client, "erasures")
    client.post("/_sim/reset", params={"system": "it_logistics"}).raise_for_status()
    assert (get(client, "pickups"), get(client, "erasures")) == before
