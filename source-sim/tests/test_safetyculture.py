"""B5, batch 2: system-specific values for ShipLane, Optoro, SafetyCulture, Oracle Depot Repair, Ritchie Bros. and
Machinio (RT-1048 / RT-1049 facts and the demo's MAPPINGS examples). The generic contract runs in
tests/test_generic_specs.py; it is repeated here without the app lifespan, so these systems can be checked on their
own (each test resets only its own system)."""

import pytest
from fastapi.testclient import TestClient
from test_generic_specs import SPECS, headers
from test_generic_specs import test_contract as contract

from sim.main import app

MINE = ("insp",)
BY_ID = {s.source_id: s for s in SPECS if s.source_id in MINE}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)  # no lifespan: /_sim/reset?system= builds each schema


def get(client, sid: str, path: str, **params) -> list[dict]:
    spec = BY_ID[sid]
    client.post("/_sim/reset", params={"system": sid}).raise_for_status()
    r = client.get(
        spec.base_path + path,
        headers=headers(client, spec),
        params=params | {spec.paging.size_param if spec.paging.style == "page" else spec.paging.limit_param: 200},
    )
    assert r.status_code == 200, r.text
    return r.json()[spec.paging.items_key]


@pytest.mark.parametrize("sid", MINE)
def test_contract_standalone(client, sid):
    contract(client, BY_ID[sid])


def test_safetyculture_rt_1049(client):
    audits = get(client, "insp", "/audits", asset_id="DRL-0812")
    assert len(audits) == 1
    audits = [a for a in get(client, "insp", "/audits") if a["header_items"]["return_reference"] == "RT-1049"]
    assert len(audits) == 1 and audits[0]["grade_text"] == "Grade B" and audits[0]["media_count"] > 0
    spec = BY_ID["insp"]
    h = headers(client, spec)
    one = client.get(f"{spec.base_path}/audits/{audits[0]['audit_id']}", headers=h)
    assert one.status_code == 200 and one.json()["audit_id"] == audits[0]["audit_id"]
    search = client.get(f"{spec.base_path}/audits/search", headers=h)
    assert search.status_code == 200 and "modified_at" in search.json()["data"][0]
    media = get(client, "insp", "/media", audit_id=audits[0]["audit_id"])
    assert len(media) == audits[0]["media_count"]
    # RT-1048 was inspected by the depot (MRO evidence), not in iAuditor
    assert not [a for a in get(client, "insp", "/audits") if a["header_items"]["return_reference"] == "RT-1048"]
