"""Plan 9 P9-10.3: call the synthetic test bench (tn_bench) the way a JSON-API client does. Stories TN-06, TN-10, TN-13.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`.
"""

import pytest
from fastapi.testclient import TestClient

from sim.core import scheduler
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/test-bench/api"
KEY = {"x-api-key": "tn_bench-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "tn_bench"}).raise_for_status()
        yield c


def serial(n: int) -> str:
    return f"SN-TN-{n:04d}"


def result(client, n: int) -> dict:
    r = client.get(f"{API}/results", params={"serial": serial(n)}, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["tn_bench"]
    assert (s.vendor, s.style, s.base_path) == ("Test bench (synthetic)", "vendor", "/test-bench")
    assert "tn_bench" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "tn_bench" in MOCKS
    assert client.get("/health").json()["missing_schemas"] == []


def test_results_need_the_key(client):
    assert client.get(f"{API}/results", params={"serial": serial(1)}).status_code == 401
    assert client.post(f"{API}/wipe-jobs", json={"serial": serial(1)}, headers={"x-api-key": "wrong"}).status_code == 401


def test_test_bench_seed(client):
    one = result(client, 1)
    assert set(one) == {"serial", "tests", "firmware", "firmwareLatest", "wipe", "boards", "weightKg", "battery"}
    assert one["tests"] == {"passed": 18, "total": 18} and one["firmware"] == one["firmwareLatest"]
    assert (one["wipe"]["status"], one["wipe"]["attempts"], one["wipe"]["certificateRef"]) == ("verified", 1, "WC-0001")
    assert one["wipe"]["scope"] == ["configuration", "credentials", "keys", "logs"] and one["battery"] is None
    assert set(one["wipe"]) == {"status", "attempts", "tool", "toolVersion", "scope", "verifiedAt", "certificateRef"}
    assert set(one["boards"][0]) == {"boardId", "partNumber", "health"}
    assert (result(client, 14)["wipe"]["status"], result(client, 14)["wipe"]["attempts"]) == ("failed", 1)
    assert (result(client, 15)["wipe"]["status"], result(client, 15)["wipe"]["attempts"]) == ("failed", 2)  # two failed attempts
    old = result(client, 40)
    assert (old["firmware"], old["firmwareLatest"]) == ("5.2", "7.1")
    power = {n: result(client, n)["battery"] for n in range(100, 111)}
    assert all(power[n]["chemistry"] == "lithium" for n in range(100, 106))
    assert all(power[n]["chemistry"] == "lead_acid" for n in range(106, 111))
    assert [n for n, b in power.items() if b["damaged"]] == [103]
    assert result(client, 100)["wipe"]["status"] == "none"
    assert client.get(f"{API}/results", params={"serial": "SN-TN-9999"}, headers=KEY).status_code == 404


def test_results_list_pages(client):
    page = client.get(f"{API}/results", params={"limit": 50}, headers=KEY).json()
    assert (len(page["results"]), page["next"]) == (50, 50)
    rest = client.get(f"{API}/results", params={"limit": 50, "offset": 50}, headers=KEY).json()
    assert (len(rest["results"]), rest["next"]) == (1, None)


def test_wipe_rerun_completes_later(client):
    client.post("/_sim/reset", params={"system": "tn_bench"}).raise_for_status()
    r = client.post(f"{API}/wipe-jobs", json={"serial": serial(15)}, headers=KEY)
    assert r.status_code == 201 and r.json()["status"] == "running"
    again = client.post(f"{API}/wipe-jobs", json={"serial": serial(15)}, headers=KEY)
    assert (again.status_code, again.json()["jobId"]) == (200, r.json()["jobId"])
    scheduler.tick()
    assert result(client, 15)["wipe"]["status"] == "failed"  # not yet due
    client.post("/_sim/clock/advance", json={"hours": 3, "minutes": 59}).raise_for_status()
    scheduler.tick()
    assert result(client, 15)["wipe"]["status"] == "failed"
    client.post("/_sim/clock/advance", json={"minutes": 2}).raise_for_status()
    scheduler.tick()
    wipe = result(client, 15)["wipe"]
    assert (wipe["status"], wipe["attempts"], wipe["certificateRef"], wipe["verifiedAt"] is not None) == (
        "verified", 3, "WC-0015", True,
    )  # fmt: skip
    scheduler.tick()
    assert result(client, 15)["wipe"]["attempts"] == 3
    events = client.get("/_sim/outbox", params={"source": "tn_bench", "limit": 200}).json()
    assert len([e for e in events if e["type"] == "bench.wipe.completed" and e["subject"] == serial(15)]) == 1
    assert client.post(f"{API}/wipe-jobs", json={"serial": "SN-TN-9999"}, headers=KEY).status_code == 404
    assert client.post(f"{API}/wipe-jobs", json={}, headers=KEY).status_code == 422


def test_refurb_orders_and_teardowns_are_idempotent(client):
    client.post("/_sim/reset", params={"system": "tn_bench"}).raise_for_status()
    a = client.post(f"{API}/refurb-orders", json={"serial": serial(3)}, headers=KEY)
    b = client.post(f"{API}/refurb-orders", json={"serial": serial(3)}, headers=KEY)
    assert (a.status_code, b.status_code, b.json()) == (201, 200, a.json())
    boards = [x["boardId"] for x in result(client, 3)["boards"]]
    t = client.post(f"{API}/teardowns", json={"serial": serial(3), "boards": boards}, headers=KEY)
    u = client.post(f"{API}/teardowns", json={"serial": serial(3), "boards": list(reversed(boards))}, headers=KEY)
    assert (t.status_code, u.status_code, u.json()) == (201, 200, t.json())
    bad = client.post(f"{API}/teardowns", json={"serial": serial(3), "boards": ["BRD-X"]}, headers=KEY)
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "unknown_board")
    assert client.post(f"{API}/teardowns", json={"serial": serial(3), "boards": []}, headers=KEY).status_code == 422
    assert client.post(f"{API}/refurb-orders", json={"serial": "SN-TN-9999"}, headers=KEY).status_code == 404


def test_test_bench_seed_is_the_same_twice(client):
    client.post("/_sim/reset", params={"system": "tn_bench"}).raise_for_status()
    before = client.get(f"{API}/results", params={"limit": 200}, headers=KEY).json()
    client.post("/_sim/reset", params={"system": "tn_bench"}).raise_for_status()
    assert client.get(f"{API}/results", params={"limit": 200}, headers=KEY).json() == before
