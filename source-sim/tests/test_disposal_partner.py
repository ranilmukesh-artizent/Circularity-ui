"""Plan 9 P9-11.5: call the synthetic disposal partner (mr_disposal) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
The certificate and the sanitisation record come after simulated time passes (the mock follows source-sim's clock).
Stories: MR-10, MR-19 (a patient-data device is never collected without a sanitisation record).
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/disposal-partner/api"
KEY = {"x-api-key": "mr_disposal-demo-key"}
PUMP = "SYN-MR-IP-0001"
MONITOR = "SYN-MR-PM-0001"  # patient monitors hold patient data


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "mr_disposal"}).raise_for_status()
        c.post("/_sim/clock/reset").raise_for_status()
        yield c
        c.post("/_sim/clock/reset")


def certificates(client, tag: str) -> list[dict]:
    r = client.get(f"{API}/certificates", params={"tag": tag}, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_disposal_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["mr_disposal"]
    assert (s.vendor, s.style, s.base_path) == ("Disposal partner (synthetic)", "vendor", "/disposal-partner")
    assert "mr_disposal" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mr_disposal" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_disposal_needs_the_key(client):
    assert client.get(f"{API}/certificates").status_code == 401
    assert client.post(f"{API}/collections", json={"tags": [PUMP]}).status_code == 401
    assert client.post(f"{API}/sanitisations", json={"tag": MONITOR}).status_code == 401


def test_disposal_needs_sanitisation_for_patient_data(client):
    r = client.post(f"{API}/collections", json={"tags": [MONITOR]}, headers=KEY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "sanitisation_missing"
    assert MONITOR in r.json()["error"]["message"]
    blank = client.post(f"{API}/collections", json={"tags": [PUMP, MONITOR], "sanitisationRef": " "}, headers=KEY)
    assert blank.status_code == 422 and blank.json()["error"]["code"] == "sanitisation_missing"
    ok = client.post(f"{API}/collections", json={"tags": [MONITOR], "sanitisationRef": "SAN-0001"}, headers=KEY)
    assert ok.status_code == 201 and ok.json()["collectionId"] == "COL-0001"
    no_data = client.post(f"{API}/collections", json={"tags": [PUMP]}, headers=KEY)  # a pump holds no patient data
    assert no_data.status_code == 201 and no_data.json()["collectionId"] == "COL-0002"
    for bad in ({"tags": []}, {"tags": ["x"]}, {"tags": "SYN-MR-IP-0001"}, {}):
        assert client.post(f"{API}/collections", json=bad, headers=KEY).status_code == 422
    assert client.post(f"{API}/collections", content=b"not json", headers=KEY).status_code == 400


def test_disposal_certificate_later(client):
    made = client.post(f"{API}/collections", json={"tags": [PUMP]}, headers=KEY).json()
    assert made["status"] == "collected" and certificates(client, PUMP) == []
    client.post("/_sim/clock/advance", json={"days": 1}).raise_for_status()
    assert certificates(client, PUMP) == []
    client.post("/_sim/clock/advance", json={"days": 1, "hours": 1}).raise_for_status()
    (cert,) = certificates(client, PUMP)
    assert cert["tag"] == PUMP and cert["collectionId"] == made["collectionId"] and cert["certificateId"].startswith("DC-")
    assert certificates(client, MONITOR) == []


def test_sanitisation_record_a_day_later(client):
    r = client.post(f"{API}/sanitisations", json={"tag": MONITOR}, headers=KEY)
    assert r.status_code == 201 and r.json()["sanitisationId"] == "SAN-0001" and r.json()["status"] == "pending"
    again = client.post(f"{API}/sanitisations", json={"tag": MONITOR}, headers=KEY)
    assert again.status_code == 200 and again.json()["sanitisationId"] == "SAN-0001"  # idempotent per tag
    assert client.get(f"{API}/sanitisations", params={"tag": MONITOR}, headers=KEY).json() == []
    client.post("/_sim/clock/advance", json={"days": 1, "hours": 1}).raise_for_status()
    (rec,) = client.get(f"{API}/sanitisations", params={"tag": MONITOR}, headers=KEY).json()
    assert (rec["sanitisationId"], rec["tag"], rec["status"]) == ("SAN-0001", MONITOR, "completed")
    assert client.post(f"{API}/sanitisations", json={"tag": "x"}, headers=KEY).status_code == 422
