"""Plan 9 P9-10.4: call the synthetic spares planning system (tn_spares). Stories TN-11, TN-12, TN-18, TN-19."""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/spares-planning/api"
KEY = {"x-api-key": "tn_spares-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "tn_spares"}).raise_for_status()
        yield c


def get(client, path):
    r = client.get(f"{API}/{path}", headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["tn_spares"]
    assert (s.vendor, s.style, s.base_path) == ("Spares planning (synthetic)", "vendor", "/spares-planning")
    assert "tn_spares" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "tn_spares" in MOCKS
    assert client.get("/health").json()["missing_schemas"] == []


def test_spares_needs_the_key(client):
    assert client.get(f"{API}/catalogue").status_code == 401
    assert client.get(f"{API}/targets", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/requisitions/PR-3301/reduce", json={"qty": 1, "reason": "x"}).status_code == 401


def test_spares_catalogue_targets_forecast(client):
    cat = {c["model"]: c for c in get(client, "catalogue")}
    assert {m: (c["newPrice"], c["generation"]) for m, c in cat.items()} == {
        "RRU-4410": (9800, "current"), "BBU-2200": (4200, "previous"), "RTR-880": (6500, "current"),
        "PSU-48": (1100, "current"), "RAD-7700": (7300, "current"),
    }  # fmt: skip
    assert all(isinstance(c["failureRate12m"], float) for c in cat.values())
    targets = get(client, "targets")
    assert len(targets) == 20 and all(set(t) == {"region", "model", "target", "stock", "useProbability12m"} for t in targets)
    north = next(t for t in targets if (t["region"], t["model"]) == ("North", "RRU-4410"))
    assert (north["target"], north["stock"], north["useProbability12m"]) == (4, 2, 0.55)
    forecast = get(client, "forecast6m")
    assert forecast and all(set(f) == {"region", "model", "need"} for f in forecast)
    assert len(forecast) == 20  # one row per target cell
    assert [f["need"] for f in forecast if f["model"] == "BBU-2200"] == [0, 0, 0, 0]  # on file, and no region needs it
    stock = get(client, "stock")
    psu = sorted(u["idleDays"] for u in stock if (u["region"], u["model"]) == ("North", "PSU-48"))
    assert len(psu) == 3 and all(41 <= d <= 60 for d in psu)
    for t in targets:  # the pool agrees with the targets
        assert t["stock"] == sum(1 for u in stock if (u["region"], u["model"]) == (t["region"], t["model"]))
    assert len({u["serial"] for u in stock}) == len(stock)
    reqs = {r["reqId"]: r for r in get(client, "requisitions")}
    assert [(r["region"], r["model"], r["quantity"]) for r in map(reqs.get, ("PR-3301", "PR-3302"))] == [
        ("West", "PSU-48", 3), ("North", "RRU-4410", 1),
    ]  # fmt: skip


def test_requisition_reduce_idempotent(client):
    client.post("/_sim/reset", params={"system": "tn_spares"}).raise_for_status()
    url, h = f"{API}/requisitions/PR-3301/reduce", KEY | {"Idempotency-Key": "k-1"}
    first = client.post(url, json={"qty": 1, "reason": "idle stock in North"}, headers=h)
    assert first.status_code == 200 and first.json()["quantity"] == 2
    again = client.post(url, json={"qty": 1, "reason": "idle stock in North"}, headers=h)
    assert again.status_code == 200 and again.json() == first.json()  # one key, one cut
    assert next(r for r in get(client, "requisitions") if r["reqId"] == "PR-3301")["quantity"] == 2
    other = client.post(url, json={"qty": 1, "reason": "again"}, headers=KEY | {"Idempotency-Key": "k-2"})
    assert other.json()["quantity"] == 1
    assert client.post(url, json={"qty": 5, "reason": "x"}, headers=KEY).status_code == 422
    assert client.post(url, json={"qty": 1}, headers=KEY).status_code == 422
    assert client.post(f"{API}/requisitions/PR-0000/reduce", json={"qty": 1, "reason": "x"}, headers=KEY).status_code == 404
    last = client.post(url, json={"qty": 1, "reason": "all"}, headers=KEY | {"Idempotency-Key": "k-3"})
    assert last.json()["status"] == "cancelled" and "PR-3301" not in {r["reqId"] for r in get(client, "requisitions")}
    assert client.post(url, json={"qty": 1, "reason": "x"}, headers=KEY | {"Idempotency-Key": "k-4"}).status_code == 409
    client.post("/_sim/reset", params={"system": "tn_spares"}).raise_for_status()
    assert {r["reqId"]: r["quantity"] for r in get(client, "requisitions")} == {"PR-3301": 3, "PR-3302": 1}
