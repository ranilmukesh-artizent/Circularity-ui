"""Plan 9 P9-9.5: call the synthetic vehicle recall database (uc_recall) the way a JSON-API client does.

The mock is no demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in
`x-api-key`. A per-VIN lookup is a fresh check: `checkedAt` is the simulated now of the call.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/vehicle-recall/api"
KEY = {"x-api-key": "uc_recall-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_recall"}).raise_for_status()
        yield c
        c.post("/_sim/clock/reset").raise_for_status()


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def lookup(client, v: str) -> dict:
    r = client.get(f"{API}/recalls/vin/{v}", headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_recall"]
    assert (s.vendor, s.style, s.base_path) == ("Vehicle recall database (synthetic)", "vendor", "/vehicle-recall")
    assert "uc_recall" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_recall" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_vehicle_recall_needs_the_key(client):
    assert client.get(f"{API}/recalls/vin/{vin(2)}").status_code == 401
    assert client.get(f"{API}/recalls", headers={"x-api-key": "wrong"}).status_code == 401


def test_vehicle_recall_seed(client):
    two = lookup(client, vin(2))
    assert two["vin"] == vin(2) and two["remedied"] == []
    assert [(c["campaignId"], c["remedyAvailable"]) for c in two["openRecalls"]] == [("SYN-24V-001", True)]
    assert set(two["openRecalls"][0]) == {"campaignId", "component", "summary", "remedyAvailable"}
    for n in (50, 55):
        assert [c["campaignId"] for c in lookup(client, vin(n))["openRecalls"]] == ["SYN-24V-001"]
    sixty = lookup(client, vin(60))
    assert sixty["openRecalls"] == [] and len(sixty["remedied"]) == 1
    assert sixty["remedied"][0]["campaignId"] == "SYN-25V-014" and sixty["remedied"][0]["remedyRef"] == "RR-0060"
    assert set(sixty["remedied"][0]) == {"campaignId", "remedyRef", "remediedAt"}
    clean = lookup(client, vin(1))
    assert clean["openRecalls"] == [] and clean["remedied"] == []


def test_vehicle_recall_lookup_is_fresh(client):
    first = datetime.fromisoformat(lookup(client, vin(2))["checkedAt"])
    client.post("/_sim/clock/advance", json={"days": 3}).raise_for_status()
    second = datetime.fromisoformat(lookup(client, vin(2))["checkedAt"])
    assert 2.99 < (second - first).total_seconds() / 86400 < 3.1


def test_vehicle_recall_bad_vin(client):
    assert client.get(f"{API}/recalls/vin/NOPE", headers=KEY).status_code == 400


def test_vehicle_recall_bulk_list_and_delta(client):
    body = client.get(f"{API}/recalls", headers=KEY).json()
    assert body["total"] == 4 and body["next"] is None
    by = {(r["vin"], r["campaignId"]): r for r in body["items"]}
    assert set(by) == {(vin(2), "SYN-24V-001"), (vin(50), "SYN-24V-001"), (vin(55), "SYN-24V-001"), (vin(60), "SYN-25V-014")}
    assert by[(vin(60), "SYN-25V-014")]["status"] == "remedied" and by[(vin(60), "SYN-25V-014")]["remedyRef"] == "RR-0060"
    assert by[(vin(2), "SYN-24V-001")]["status"] == "open"
    paged = client.get(f"{API}/recalls", params={"limit": 3}, headers=KEY).json()
    assert (len(paged["items"]), paged["next"]) == (3, 3)
    newest = max(r["updatedAt"] for r in body["items"])
    assert client.get(f"{API}/recalls", params={"updatedSince": newest}, headers=KEY).json()["items"] == []
    assert client.get(f"{API}/recalls", params={"updatedSince": "garbage"}, headers=KEY).status_code == 400
