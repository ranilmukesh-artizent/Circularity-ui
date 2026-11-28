"""Plan 9 P9-11.2: call the synthetic rental system (mr_rental) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
Stories: MR-04 (nearest demand), MR-09 (decontamination queue), MR-17 (isolation-ward returns), MR-18 (repeat request).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/rental-system/api"
KEY = {"x-api-key": "mr_rental-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "mr_rental"}).raise_for_status()
        yield c


def get(client, path, **params):
    r = client.get(f"{API}/{path}", params=params, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["mr_rental"]
    assert (s.vendor, s.style, s.base_path) == ("Rental system (synthetic)", "vendor", "/rental-system")
    assert "mr_rental" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mr_rental" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_rental_system_needs_the_key(client):
    for path in ("returns", "requests", "hospitals", "depots", "demand-forecast", "turnaround"):
        assert client.get(f"{API}/{path}").status_code == 401, path
        assert client.get(f"{API}/{path}", headers={"x-api-key": "wrong"}).status_code == 401, path
    assert client.post(f"{API}/dispatches", json={}).status_code == 401


def test_rental_system_seed(client):
    """Five open requests (four for pumps, one for the patient monitor), the six hospitals, East with one decontamination line
    and the others with two."""
    reqs = get(client, "requests")
    assert [r["reqId"] for r in reqs] == ["REQ-1", "REQ-2", "REQ-3", "REQ-4", "REQ-5"]
    assert [r["hospitalId"] for r in reqs] == ["HOSP-A", "HOSP-B", "HOSP-C", "HOSP-B", "HOSP-A"]
    assert [r["deviceClass"] for r in reqs] == ["infusion_pump"] * 4 + ["patient_monitor"]
    assert {(r["startDate"], r["days"], r["region"]) for r in reqs} == {("2026-11-27", 30, "EAST")}
    assert set(reqs[0]) == {"reqId", "hospitalId", "deviceClass", "startDate", "days", "region", "requestedAt"}
    first, again = (datetime.fromisoformat(r["requestedAt"]) for r in (reqs[1], reqs[3]))
    assert 0 < (again - first).total_seconds() <= 24 * 3600  # HOSP-B asks again within 24 h
    hospitals = get(client, "hospitals")
    assert [h["hospitalId"] for h in hospitals] == [f"HOSP-{c}" for c in "ABCDEF"]
    assert hospitals[0]["label"] == "Hospital A (synthetic)"
    assert set(hospitals[0]) == {"hospitalId", "label", "latitude", "longitude", "region"}
    depots = {d["depotId"]: d for d in get(client, "depots")}
    assert set(depots) == {"EAST", "WEST", "NORTH"}
    assert (depots["EAST"]["deconLines"], depots["WEST"]["deconLines"], depots["NORTH"]["deconLines"]) == (1, 2, 2)
    assert {"latitude", "longitude", "label", "region"} <= set(depots["EAST"])


def test_rental_returns_and_isolation_ward(client):
    rows = get(client, "returns")
    by = {r["tag"]: r for r in rows}
    assert set(rows[0]) == {"returnId", "tag", "hospitalId", "ward", "wardType", "depot", "checkedInAt", "previousRentalEnd"}
    assert len(by) == len(rows) == 46 and by["SYN-MR-IP-0001"]["depot"] == "EAST"  # 45 pumps and the monitor SYN-MR-PM-0007
    iso = sorted(r["tag"] for r in rows if r["wardType"] == "isolation")
    assert iso == ["SYN-MR-IP-0010", "SYN-MR-IP-0011"]
    assert {by[t]["hospitalId"] for t in iso} == {"HOSP-D"}
    assert {r["wardType"] for r in rows} == {"general", "isolation"}
    west = get(client, "returns", depot="WEST")
    assert west and {r["depot"] for r in west} == {"WEST"}


def test_rental_demand_forecast_east_trough(client):
    east = get(client, "demand-forecast", region="EAST")
    assert len(east) == 8 and {r["region"] for r in east} == {"EAST"}
    low = min(east, key=lambda r: r["requests"])
    assert low["weekStart"] == "2026-12-07" and sum(r["requests"] == low["requests"] for r in east) == 1
    assert len(get(client, "demand-forecast")) == 24
    assert client.get(f"{API}/demand-forecast", params={"region": "MARS"}, headers=KEY).status_code == 404


def test_rental_turnaround_east_is_slow(client):
    def avg(depot):
        rows = get(client, "turnaround", depot=depot, days=14)
        assert rows and {r["depot"] for r in rows} == {depot}
        assert set(rows[0]["waitingDays"]) == {"decon_queue", "service", "transport"}
        return sum(r["totalDays"] for r in rows) / len(rows)

    assert avg("EAST") == pytest.approx(3.4, abs=0.01)
    assert avg("WEST") == pytest.approx(1.6, abs=0.01) and avg("NORTH") == pytest.approx(1.6, abs=0.01)
    east = get(client, "turnaround", depot="EAST", days=14)
    total = sum(sum(r["waitingDays"].values()) for r in east)
    assert sum(r["waitingDays"]["decon_queue"] for r in east) > total / 2  # the one decontamination line is the queue
    assert len(get(client, "turnaround", depot="EAST", days=28)) == len(east) + 10  # returns rose 30 %: 13 against 10
    assert client.get(f"{API}/turnaround", params={"days": "x"}, headers=KEY).status_code == 400


EVIDENCE = {"serviceRef": "SVC-0001", "certExpiry": "2027-03-01", "deconRef": "DEC-0001"}


def test_rental_dispatch_idempotent(client):
    client.post("/_sim/reset", params={"system": "mr_rental"}).raise_for_status()
    body = {"tag": "SYN-MR-IP-0001", "reqId": "REQ-2", "evidence": EVIDENCE}
    one = client.post(f"{API}/dispatches", json=body, headers=KEY)
    assert one.status_code == 201, one.text
    doc = one.json()
    assert doc["dispatchId"] == "DSP-0001" and doc["status"] == "dispatched"
    assert (doc["tag"], doc["reqId"], doc["evidence"]) == ("SYN-MR-IP-0001", "REQ-2", EVIDENCE)
    two = client.post(f"{API}/dispatches", json=body, headers=KEY)
    assert two.status_code == 200 and two.json() == doc  # a repeat: the first document, nothing new
    assert [r["reqId"] for r in get(client, "requests")] == ["REQ-1", "REQ-3", "REQ-4", "REQ-5"]  # dispatched: no longer open
    other = client.post(f"{API}/dispatches", json=body | {"tag": "SYN-MR-IP-0002"}, headers=KEY)
    assert other.status_code == 409
    third = client.post(f"{API}/dispatches", json=body | {"reqId": "REQ-3"}, headers=KEY)
    assert third.status_code == 201 and third.json()["dispatchId"] == "DSP-0002"
    client.post("/_sim/reset", params={"system": "mr_rental"}).raise_for_status()
    assert len(get(client, "requests")) == 5


def test_rental_dispatch_validates(client):
    ok = {"tag": "SYN-MR-IP-0001", "reqId": "REQ-1", "evidence": EVIDENCE}
    cases = [
        (ok | {"tag": ""}, 422),
        (ok | {"tag": "pump 1"}, 422),
        (ok | {"evidence": {"serviceRef": "SVC-1", "certExpiry": "2027-03-01"}}, 422),
        (ok | {"evidence": EVIDENCE | {"certExpiry": "soon"}}, 422),
        (ok | {"reqId": "REQ-99"}, 404),
    ]
    for body, status in cases:
        assert client.post(f"{API}/dispatches", json=body, headers=KEY).status_code == status, body
    assert client.post(f"{API}/dispatches", content=b"not json", headers=KEY).status_code == 400
    assert len(get(client, "requests")) == 5
