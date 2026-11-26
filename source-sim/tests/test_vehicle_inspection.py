"""Plan 9 P9-9.4: call the synthetic vehicle inspection app (uc_insp) the way a JSON-API client does.

No demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
The battery assessment completes on the simulated clock (sim/core/scheduler.py): the tests advance it and tick.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import scheduler
from sim.core.db import engine
from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/vehicle-inspection/api"
KEY = {"x-api-key": "uc_insp-demo-key"}
EVENT = "inspection.battery.completed"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "uc_insp"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "uc_insp"}).raise_for_status()


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def every_inspection(client, **params) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        r = client.get(f"{API}/inspections", params={"limit": 50, "offset": offset} | params, headers=KEY)
        assert r.status_code == 200, r.text
        out += r.json()["data"]
        offset = r.json()["next"]
    return out


def outbox() -> list[dict]:
    sql = text("SELECT data FROM sim.outbox WHERE source = 'uc_insp' AND type = :t ORDER BY id")
    with engine.connect() as conn:
        return [r.data for r in conn.execute(sql, {"t": EVENT})]


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["uc_insp"]
    assert (s.vendor, s.style, s.base_path) == ("Vehicle inspection app (synthetic)", "vendor", "/vehicle-inspection")
    assert "uc_insp" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "uc_insp" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_inspections_need_the_key(client):
    assert client.get(f"{API}/inspections").status_code == 401
    assert client.get(f"{API}/inspections", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/battery-assessments", json={"vin": vin(44)}).status_code == 401


def test_vehicle_inspection_seed(client):
    rows = every_inspection(client)
    assert [r["vin"] for r in rows] == [vin(n) for n in range(1, 101)]
    by = {r["vin"]: r for r in rows}
    assert by[vin(7)]["reconEstimate"] == 2800 and by[vin(8)]["reconEstimate"] == 16500
    assert by[vin(90)]["status"] == "scheduled"
    assert {v for v, r in by.items() if r["status"] == "scheduled"} == {vin(n) for n in range(90, 94)}
    one = by[vin(1)]
    assert (one["conditionScore"], one["reconEstimate"], one["status"]) == (4, 1200, "complete")
    assert one["reconLines"] == [
        {"label": "Paint and panel, rear door", "amount": 700, "excessWear": True},
        {"label": "Tyres", "amount": 500, "excessWear": False},
    ]
    assert by[vin(4)]["odometerPhotoReading"] == 61240
    assert {v for v, r in by.items() if r["batterySoh"] is not None} == {vin(n) for n in range(41, 49)}
    assert by[vin(44)]["batterySoh"] == 74
    hail = {v for v, r in by.items() if r["hailDamage"]}
    assert hail == {vin(n) for n in range(30, 35)} and all(by[v]["reconEstimate"] < 2500 for v in hail)
    assert {v for v, r in by.items() if r["pairedDevices"]} == {vin(n) for n in range(15, 20)}
    for r in rows:
        assert {"inspectionId", "photos", "damage", "tyres", "brakes", "completedAt"} <= set(r)
        if r["status"] == "complete":
            assert sum(x["amount"] for x in r["reconLines"]) == r["reconEstimate"] and 1 <= r["conditionScore"] <= 5
    assert by[vin(90)]["completedAt"] is None and by[vin(90)]["conditionScore"] is None


def test_filters_paging_and_updated_since(client):
    assert [r["vin"] for r in every_inspection(client, vin=vin(7))] == [vin(7)]
    page = client.get(f"{API}/inspections", params={"limit": 40}, headers=KEY).json()
    assert (len(page["data"]), page["next"]) == (40, 40)
    rows = every_inspection(client)
    newer = every_inspection(client, updatedSince=rows[89]["updatedAt"])
    assert [r["vin"] for r in newer] == [r["vin"] for r in rows[90:]]
    assert client.get(f"{API}/inspections", params={"updatedSince": "x"}, headers=KEY).status_code == 400
    assert client.get(f"{API}/inspections", params={"limit": 0}, headers=KEY).status_code == 400


def test_seed_is_the_same_twice(client):
    before = every_inspection(client)
    client.post("/_sim/reset", params={"system": "uc_insp"}).raise_for_status()
    assert every_inspection(client) == before


def test_battery_assessment_completes_later(client):
    h = KEY | {"Idempotency-Key": "k-44"}
    r = client.post(f"{API}/battery-assessments", json={"vin": vin(44)}, headers=h)
    assert r.status_code == 201, r.text
    made = r.json()
    assert made["status"] == "scheduled" and made["assessmentId"]
    again = client.post(f"{API}/battery-assessments", json={"vin": vin(44)}, headers=h)
    assert again.status_code == 200 and again.json() == made  # a repeat: the first assessment, no second one
    scheduler.tick()
    first = client.get(f"{API}/battery-assessments/{made['assessmentId']}", headers=KEY).json()
    assert first["status"] == "scheduled" and outbox() == []
    client.post("/_sim/clock/advance", json={"days": 1}).raise_for_status()
    scheduler.tick()
    done = client.get(f"{API}/battery-assessments/{made['assessmentId']}", headers=KEY).json()
    assert done["status"] == "complete" and done["batterySoh"] == 74 and done["result"] == "pack_replacement_needed"
    (event,) = outbox()
    assert event["vin"] == vin(44) and event["result"] == "pack_replacement_needed"
    listed = client.get(f"{API}/battery-assessments", params={"vin": vin(44)}, headers=KEY).json()
    assert [a["assessmentId"] for a in listed["data"]] == [made["assessmentId"]]


def test_a_healthy_pack_is_fit_for_retail_and_bad_requests_are_refused(client):
    made = client.post(f"{API}/battery-assessments", json={"vin": vin(41)}, headers=KEY).json()
    client.post("/_sim/clock/advance", json={"days": 1}).raise_for_status()
    scheduler.tick()
    assert client.get(f"{API}/battery-assessments/{made['assessmentId']}", headers=KEY).json()["result"] == "fit_for_retail"
    assert client.post(f"{API}/battery-assessments", json={"vin": vin(1)}, headers=KEY).status_code == 422  # not an EV
    assert client.post(f"{API}/battery-assessments", json={"vin": "NOPE"}, headers=KEY).status_code == 404
    assert client.post(f"{API}/battery-assessments", json={}, headers=KEY).status_code == 422
    assert client.get(f"{API}/battery-assessments/BA-9999", headers=KEY).status_code == 404
