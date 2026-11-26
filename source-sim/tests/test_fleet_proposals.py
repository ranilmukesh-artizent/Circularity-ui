"""Plan 9, P9-5.5 (story CR-05): the mocks take what an approved contract refresh writes.

The fleet contract system takes a proposal and its draft lines under the ids the client names (`PR-`, `DL-`; the generic create keeps a
given id), each emitting the event that completes its step (`fleet.proposal.created`, `fleet.draft_line.created`); the parts system
takes the reservation of a refurbished unit (PATCH `status` "reserved") and emits `parts.stock.updated` with the instruction key.
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


def test_cr_05_fleet_takes_a_proposal_and_its_draft_lines(client):
    h = headers(client, FLEET)
    key = "APR-2026-10-3161.0.propsend"
    body = {"proposalId": "PR-40201", "contractId": "FC-30117", "feeMonthProposed": 184.1, "status": "sent", "issuedKey": key}
    r = client.post(FLEET.base_path + "/proposals", headers=h, json=body)
    assert r.status_code == 201 and r.json()["proposalId"] == "PR-40201"
    assert client.get(FLEET.base_path + "/proposals/PR-40201", headers=h).json()["status"] == "sent"
    assert client.get(FLEET.base_path + "/proposals/PR-no-such", headers=h).status_code == 404
    ev = _events(client, "fleet")[0]
    assert ev["type"] == "fleet.proposal.created" and ev["data"]["issuedKey"] == key and ev["data"]["proposalId"] == "PR-40201"
    line = {"draftLineId": "DL-40214-01", "draftRef": "DL-40214", "proposalId": "PR-40201", "serial": "CMH-1", "issuedKey": "k2"}
    assert client.post(FLEET.base_path + "/draft-lines", headers=h, json=line).status_code == 201
    ev = _events(client, "fleet")[0]
    assert ev["type"] == "fleet.draft_line.created" and ev["data"]["draftRef"] == "DL-40214"
    assert client.get(FLEET.base_path + "/draft-lines/DL-40214-01", headers=h).json()["proposalId"] == "PR-40201"


def test_cr_05_parts_stock_unit_takes_the_reservation(client):
    h = headers(client, PARTS)
    unit = client.get(PARTS.base_path + "/refurbished-units", headers=h, params={"status": "available", "limit": 1}).json()["items"][0]
    body = {"status": "reserved", "reservedFor": "RT-0001", "reserveRef": "RU-40227", "issuedKey": "APR-1.2.propreserve"}
    r = client.patch(PARTS.base_path + "/refurbished-units/" + unit["unitId"], headers=h, json=body)
    assert r.status_code == 200 and r.json()["status"] == "reserved" and r.json()["unitId"] == unit["unitId"]
    got = client.get(PARTS.base_path + "/refurbished-units/" + unit["unitId"], headers=h).json()
    assert got["status"] == "reserved" and got["reservedFor"] == "RT-0001"
    ev = _events(client, "parts")[0]
    assert ev["type"] == "parts.stock.updated" and ev["data"]["issuedKey"] == "APR-1.2.propreserve"
    assert ev["data"]["reserveRef"] == "RU-40227"
    assert client.patch(PARTS.base_path + "/refurbished-units/RU-no-such", headers=h, json=body).status_code == 404
