"""Plan 9 P9-10.2: call the synthetic network inventory (tn_inv) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`. Stories TN-04, TN-05, TN-12, TN-13.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core import scheduler
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/network-inventory/api"
KEY = {"x-api-key": "tn_inv-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "tn_inv"}).raise_for_status()
        yield c


def every_element(client, limit=50, **params) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        r = client.get(f"{API}/elements", params={"limit": limit, "offset": offset, **params}, headers=KEY)
        assert r.status_code == 200, r.text
        out += r.json()["elements"]
        offset = r.json()["next"]
    return out


def serial(n: int) -> str:
    return f"SN-TN-{n:04d}"


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["tn_inv"]
    assert (s.vendor, s.style, s.base_path) == ("Network inventory (synthetic)", "vendor", "/network-inventory")
    assert "tn_inv" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "tn_inv" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_elements_need_the_key(client):
    assert client.get(f"{API}/elements").status_code == 401
    assert client.get(f"{API}/elements", headers={"x-api-key": "wrong"}).status_code == 401


def test_network_inventory_seed_and_paging(client):
    first = client.get(f"{API}/elements", params={"limit": 50}, headers=KEY).json()
    assert (len(first["elements"]), first["next"]) == (50, 50)
    last = client.get(f"{API}/elements", params={"limit": 50, "offset": 100}, headers=KEY).json()
    assert (len(last["elements"]), last["next"]) == (20, None)
    rows = every_element(client)
    assert [r["serial"] for r in rows] == [serial(n) for n in range(1, 121)]
    assert set(rows[0]) == {
        "serial", "model", "partNumber", "hwRevision", "firmware", "manufacturer", "site", "siteKind", "region", "status",
        "exportClassInferred", "exportClassConfirmed",
    }  # fmt: skip
    assert {r["region"] for r in rows} == {"North", "South", "East", "West"}
    assert {r["siteKind"] for r in rows} == {"core", "edge"}
    assert {r["status"] for r in rows} <= {"in_service", "removed", "spare"}
    rad = [r for r in rows if r["model"] == "RAD-7700"]
    assert rad and {r["exportClassConfirmed"] for r in rad} == {"5A002"}
    rru = [r for r in rows if r["model"] == "RRU-4410"]
    assert rru and {r["exportClassInferred"] for r in rru} == {"5A992"} and {r["exportClassConfirmed"] for r in rru} == {None}
    assert not {serial(n) for n in range(201, 209)} & {r["serial"] for r in rows}


def test_network_inventory_filters(client):
    one = client.get(f"{API}/elements", params={"serial": serial(5)}, headers=KEY).json()
    assert [r["serial"] for r in one["elements"]] == [serial(5)] and one["next"] is None
    site = one["elements"][0]["site"]
    at = every_element(client, site=site)
    assert at and {r["site"] for r in at} == {site}
    assert client.get(f"{API}/elements", params={"limit": 0}, headers=KEY).status_code == 400
    assert client.get(f"{API}/elements", params={"offset": "x"}, headers=KEY).status_code == 400


def test_inventory_seed_is_the_same_twice(client):
    before = every_element(client)
    client.post("/_sim/reset", params={"system": "tn_inv"}).raise_for_status()
    assert every_element(client) == before


def test_inventory_element_created_later(client):
    client.post("/_sim/reset", params={"system": "tn_inv"}).raise_for_status()
    assert not every_element(client, serial=serial(201))
    scheduler.tick()
    assert not every_element(client, serial=serial(201))  # not yet due
    client.post("/_sim/clock/advance", json={"days": 1, "minutes": 1}).raise_for_status()
    scheduler.tick()
    got = every_element(client, serial=serial(201))
    assert [r["serial"] for r in got] == [serial(201)] and got[0]["status"] == "removed"
    scheduler.tick()
    events = client.get("/_sim/outbox", params={"source": "tn_inv", "limit": 200}).json()
    created = [e for e in events if e["type"] == "inventory.element.created" and e["subject"] == serial(201)]
    assert len(created) == 1
    assert len(every_element(client)) == 121


def test_transfer_orders_and_retirements_are_idempotent(client):
    client.post("/_sim/reset", params={"system": "tn_inv"}).raise_for_status()
    body = {"serial": serial(7), "toSite": "SITE-112"}
    a = client.post(f"{API}/transfer-orders", json=body, headers=KEY)
    b = client.post(f"{API}/transfer-orders", json=body, headers=KEY)
    assert a.status_code == 201 and b.status_code == 200 and a.json() == b.json()
    assert a.json()["serial"] == serial(7) and a.json()["toSite"] == "SITE-112"
    pool = client.post(f"{API}/transfer-orders", json={"serial": serial(7), "toPool": "POOL-NORTH"}, headers=KEY)
    assert pool.status_code == 201 and pool.json()["orderId"] != a.json()["orderId"]
    for bad in ({"serial": serial(7)}, {"serial": serial(7), "toSite": "S", "toPool": "P"}, {"toSite": "S"}):
        assert client.post(f"{API}/transfer-orders", json=bad, headers=KEY).status_code == 422
    assert client.post(f"{API}/transfer-orders", json={"serial": "SN-NOPE", "toSite": "S"}, headers=KEY).status_code == 404
    r1 = client.post(f"{API}/retirements", json={"serial": serial(8)}, headers=KEY)
    r2 = client.post(f"{API}/retirements", json={"serial": serial(8)}, headers=KEY)
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.json() == r2.json()
    assert client.post(f"{API}/retirements", json={"serial": "SN-NOPE"}, headers=KEY).status_code == 404
    assert client.post(f"{API}/retirements", json={"serial": serial(8)}).status_code == 401
