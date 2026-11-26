"""Plan 9, P9-3.17: the fleet contract system takes the issued serial on a contract line, the parts system the part on an open
repair order; each update emits the event that completes the tool-fleet step (di/services/instructions/events.py).

Each test resets only the system it writes to.
"""

import pytest
from fastapi.testclient import TestClient
from test_generic_specs import SPECS, headers

from sim.main import app

FLEET = next(s for s in SPECS if s.source_id == "fleet")
PARTS = next(s for s in SPECS if s.source_id == "parts")


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)  # no lifespan: /_sim/reset?system= builds the schema
    for spec in (FLEET, PARTS):
        c.post("/_sim/reset", params={"system": spec.source_id}).raise_for_status()
    yield c
    for spec in (FLEET, PARTS):
        c.post("/_sim/reset", params={"system": spec.source_id}).raise_for_status()


def _events(client, source: str) -> list[dict]:
    return client.get("/_sim/outbox", params={"source": source, "limit": 20}).json()


def test_tf_10_fleet_line_takes_the_issued_serial(client):
    h = headers(client, FLEET)
    line = client.get(FLEET.base_path + "/contract-lines/FL-30117-03", headers=h).json()
    assert line["status"] == "returned" and line["serial"] == "CMH-48213"
    body = {"status": "issued", "issuedSerial": "CMH-48213", "issuedKey": "APR-1.3.lease", "issuedFor": "FC-30117-R"}
    r = client.patch(FLEET.base_path + "/contract-lines/FL-30117-03", headers=h, json=body)
    assert r.status_code == 200 and r.json()["status"] == "issued" and r.json()["issuedSerial"] == "CMH-48213"
    again = client.get(FLEET.base_path + "/contract-lines/FL-30117-03", headers=h).json()
    assert again["status"] == "issued" and again["issuedKey"] == "APR-1.3.lease" and again["lineId"] == "FL-30117-03"
    ev = _events(client, "fleet")[0]
    assert ev["type"] == "fleet.line.updated" and ev["data"]["issuedKey"] == "APR-1.3.lease"
    assert client.patch(FLEET.base_path + "/contract-lines/FL-no-such", headers=h, json=body).status_code == 404


def test_tf_10_parts_repair_order_takes_the_part(client):
    h = headers(client, PARTS)
    ro = client.get(PARTS.base_path + "/repair-orders/open", headers=h, params={"limit": 1}).json()["items"][0]
    body = {"status": "part_issued", "issuedPart": ro["partName"], "issuedFrom": "CMH-48213", "issuedKey": "APR-1.3.partsxfer"}
    r = client.patch(PARTS.base_path + "/repair-orders/open/" + ro["roId"], headers=h, json=body)
    assert r.status_code == 200 and r.json()["status"] == "part_issued" and r.json()["roId"] == ro["roId"]
    ev = _events(client, "parts")[0]
    assert ev["type"] == "parts.repair_order.updated" and ev["data"]["roId"] == ro["roId"]
