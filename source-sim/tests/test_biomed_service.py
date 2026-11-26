"""Plan 9 P9-11.4: call the synthetic biomedical service system (mr_biomed) the way a JSON-API client does.

Not a demo source: it registers beside the 21 demo systems (sim/core/registry.py EXTRA_SYSTEMS). API key in `x-api-key`.
Stories: MR-06 (PM and certification), MR-07 (functional and electrical safety tests), MR-10 (repair estimate),
MR-15 (field safety notices), MR-16 (servicing assessment).
"""

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, EXTRA_BY_ID, SYSTEMS
from sim.main import MOCKS, app

API = "/biomed-service/api"
KEY = {"x-api-key": "mr_biomed-demo-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "mr_biomed"}).raise_for_status()
        yield c


def get(client, path: str):
    r = client.get(f"{API}{path}", headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()


def test_registered_beside_the_demo_systems(client):
    s = EXTRA_BY_ID["mr_biomed"]
    assert (s.vendor, s.style, s.base_path) == ("Biomedical service system (synthetic)", "vendor", "/biomed-service")
    assert "mr_biomed" not in BY_SOURCE_ID and len(SYSTEMS) == 21 and "mr_biomed" in MOCKS
    body = client.get("/health").json()
    assert (body["status"], body["missing_schemas"]) == ("ok", [])


def test_biomed_needs_the_key(client):
    for path in ("/assets", "/assets/SYN-MR-IP-0001/service", "/corrections", "/assessments/SYN-MR-EB-0040"):
        assert client.get(f"{API}{path}").status_code == 401
        assert client.get(f"{API}{path}", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post(f"{API}/service-orders", json={}).status_code == 401


def test_biomed_service_seed(client):
    one = get(client, "/assets/SYN-MR-IP-0001/service")
    assert (one["certificationExpiry"], one["pmDue"]) == ("2027-03-31", "2027-02-15")
    assert one["functionalTest"]["result"] == "pass"
    assert one["electricalSafety"]["standard"] == "IEC 62353" and one["electricalSafety"]["result"] == "pass"
    assert one["notes"] == [{"text": "Housing scuff", "kind": "cosmetic"}]
    assert set(one) >= {"tag", "pmDue", "pmCode", "lastPm", "certificationExpiry", "functionalTest", "electricalSafety",
                        "notes", "repairEstimate", "faults"}  # fmt: skip
    assert get(client, "/assets/SYN-MR-IP-0002/service")["certificationExpiry"] == "2026-12-07"
    monitor = get(client, "/assets/SYN-MR-PM-0007/service")
    assert monitor["repairEstimate"] == 1350 and monitor["notes"][0]["kind"] == "fault"
    rows = get(client, "/assets")
    assert len(rows) == 80 and len({r["tag"] for r in rows}) == 80 and rows[0]["tag"] == "SYN-MR-IP-0001"
    assert client.get(f"{API}/assets/SYN-MR-IP-9999/service", headers=KEY).status_code == 404


def test_biomed_assessments(client):
    a = get(client, "/assessments/SYN-MR-EB-0040")
    assert (a["result"], a["tag"]) == ("servicing", "SYN-MR-EB-0040") and a["plannedWork"] and a["assessedBy"] and a["at"]
    assert get(client, "/assessments/SYN-MR-EB-0041")["result"] == "full_refurbishment"
    assert {a["tag"] for a in get(client, "/assessments")} == {"SYN-MR-EB-0040", "SYN-MR-EB-0041"}
    assert client.get(f"{API}/assessments/SYN-MR-IP-0001", headers=KEY).status_code == 404


def test_biomed_corrections_cover_serial_range(client):
    notices = get(client, "/corrections")
    fsn = next(n for n in notices if n["noticeId"] == "FSN-031")
    assert (fsn["model"], fsn["serialFrom"], fsn["serialTo"], fsn["status"]) == ("IP-300", 3000, 3099, "open")
    assert fsn["correctionRef"] and {n["status"] for n in notices} == {"open", "closed"}
    covered = get(client, "/assets/SYN-MR-IP-0030/service")
    assert covered["model"] == fsn["model"] and fsn["serialFrom"] <= covered["serialNo"] <= fsn["serialTo"]
    outside = get(client, "/assets/SYN-MR-IP-0031/service")  # same model, serial just beyond the range
    assert outside["model"] == fsn["model"] and outside["serialNo"] > fsn["serialTo"]
    assert get(client, "/assets/SYN-MR-IP-0001/service")["model"] != fsn["model"]


def test_biomed_service_order_idempotent(client):
    body = {"tag": "SYN-MR-IP-0001", "kind": "pm", "dueBy": "2027-02-15"}
    first = client.post(f"{API}/service-orders", json=body, headers=KEY)
    assert first.status_code == 201, first.text
    doc = first.json()
    assert doc["status"] == "accepted" and doc["orderId"].startswith("SO-") and doc["tag"] == body["tag"]
    again = client.post(f"{API}/service-orders", json=body, headers=KEY)
    assert again.status_code == 200 and again.json() == doc
    other = client.post(f"{API}/service-orders", json=body | {"kind": "certification"}, headers=KEY)
    assert other.status_code == 201 and other.json()["orderId"] != doc["orderId"]


def test_biomed_service_order_validates(client):
    post = lambda b: client.post(f"{API}/service-orders", json=b, headers=KEY)  # noqa: E731
    assert post({"kind": "pm", "dueBy": "2027-02-15"}).status_code == 422
    assert post({"tag": "SYN-MR-IP-0001", "kind": "scrap", "dueBy": "2027-02-15"}).status_code == 422
    assert post({"tag": "SYN-MR-IP-0001", "kind": "pm", "dueBy": "soon"}).status_code == 422
    assert client.post(f"{API}/service-orders", content=b"{", headers=KEY).status_code == 400
