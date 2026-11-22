"""B5b contract tests: call the AssetWise mock the way an OData v4 client with a Bentley IMS token does."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core import clock
from sim.core.db import engine
from sim.main import app
from sim.seed import seed
from sim.vendors.assetwise.routes import validity

ODATA = "/assetwise/eB/Service/OData/Engineering"
IMS = {
    "grant_type": "client_credentials",
    "client_id": "service-circularity-di",
    "client_secret": "circularity-demo-ims-secret",
    "scope": "assetwise-odata",
}
CONNECTOR = ("di.connector", "Circularity-demo-aw-1")
APPROVER = ("eng.approver", "Circularity-demo-aw-approver")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "eng"}).raise_for_status()
        tok = c.post("/assetwise/ims/connect/token", data=IMS).json()["access_token"]
        c.headers["Authorization"] = "Bearer " + tok
        yield c
        c.post("/_sim/reset", params={"system": "eng"}).raise_for_status()


def get(client, path: str, **params) -> dict:
    r = client.get(ODATA + path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- authentication
def test_ims_tokens_and_basic_auth():
    with TestClient(app) as c:
        url = "/assetwise/ims/connect/token"
        ok = c.post(url, data=IMS).json()
        assert (ok["token_type"], ok["expires_in"], ok["scope"]) == ("Bearer", 3600, "assetwise-odata")
        assert c.post(url, data=IMS | {"client_secret": "x"}).json() == {"error": "invalid_client"}
        assert c.post(url, data=IMS | {"scope": "itwin-platform"}).json() == {"error": "invalid_scope"}
        r = c.post(url, data=IMS | {"grant_type": "password"})
        assert r.status_code == 400 and r.json() == {"error": "unsupported_grant_type"}
        r = c.get(ODATA + "/Standards")
        assert r.status_code == 401 and r.json()["error"]["message"] == "Authorization has been denied for this request."
        assert "Bearer" in r.headers["WWW-Authenticate"]
        assert c.get(ODATA + "/Standards", auth=("di.connector", "wrong")).status_code == 401
        assert c.get(ODATA + "/Standards", auth=CONNECTOR).status_code == 200
        assert c.get(ODATA + "/Standards", headers={"Authorization": "Bearer " + ok["access_token"]}).status_code == 200


# ---------------------------------------------------------------- reading
def test_service_document_and_metadata(client):
    assert [s["name"] for s in get(client, "/")["value"]] == ["LifeAssessments", "Standards", "EngineeringLimits"]
    xml = client.get(ODATA + "/$metadata").text
    assert 'EntitySet Name="LifeAssessments"' in xml and 'Action Name="Approve"' in xml
    r = client.get("/assetwise/eB/Service/OData/Finance/Standards")
    assert r.status_code == 404 and "error" in r.json()


def test_the_demo_mapping_example(client):
    """MAPPINGS.eng: RUL_MONTHS 36 → "36 months"; STANDARD_REF IEC 60034-1; REQUAL_STATUS APPROVED."""
    a = get(client, "/LifeAssessments('LA-MTR-2041')")
    assert a["@odata.context"].endswith("$metadata#LifeAssessments/$entity")
    assert (a["RUL_MONTHS"], a["STANDARD_REF"], a["REQUAL_STATUS"]) == (36, "IEC 60034-1", "APPROVED")
    assert (a["RUL_LOW_MONTHS"], a["RUL_HIGH_MONTHS"], a["NEXT_INSPECTION_DATE"]) == (30, 40, "2027-04-01")
    assert (a["APPROVAL_STATUS"], a["VALIDITY"], a["APPROVED_BY"]) == ("Approved", "VALID", "Engineering Standards")
    months = (datetime.fromisoformat(a["VALID_UNTIL"]) - datetime.fromisoformat(a["VALID_FROM"])).days / 30.4
    assert round(months) == 24  # the IEC 60034-1 requalification interval
    std = get(client, "/Standards", **{"$filter": "ASSET_CLASS eq 'motor' and MIN_RUL_MONTHS ne null"})["value"]
    assert [(s["STANDARD_REF"], s["REQUAL_INTERVAL_MONTHS"]) for s in std] == [("IEC 60034-1", 24)]
    missing = [c for c in seed().cases.values() if any(e.k == "eng" and e.state == "missing" for e in c.facts.evidence)]
    assert int(client.get(ODATA + "/LifeAssessments/$count").text) == 128 - len(missing)
    assert client.get(ODATA + "/LifeAssessments('LA-NONE')").status_code == 404


def test_query_options_and_paging(client):
    body = get(client, "/LifeAssessments", **{"$count": "true", "$select": "ASSESSMENT_ID,MODIFIED_ON"})
    assert len(body["value"]) == min(100, body["@odata.count"])  # the server's page size
    assert set(body["value"][0]) == {"ASSESSMENT_ID", "MODIFIED_ON"}
    seen, url, params = [], ODATA + "/LifeAssessments", {"$orderby": "ASSET_ID desc", "$select": "ASSET_ID"}
    while url:
        r = client.get(url, params=params, headers={"Prefer": "odata.maxpagesize=30"})
        seen += [v["ASSET_ID"] for v in r.json()["value"]]
        url, params = r.json().get("@odata.nextLink"), None
    assert seen == sorted(seen, reverse=True) and len(seen) == body["@odata.count"]
    lim = get(
        client,
        "/EngineeringLimits",
        **{"$filter": "LIMIT_TYPE eq 'MAX' and LIMIT_VALUE lt 3 and contains(PARAMETER,'Vibration')"},
    )
    assert [x["LIMIT_ID"] for x in lim["value"]] == ["LIM-MTR-VIB"]
    r = client.get(ODATA + "/Standards", params={"$filter": "COLOUR eq 'red'"})
    assert r.status_code == 400 and "COLOUR" in r.json()["error"]["message"]
    assert client.get(ODATA + "/Standards", params={"$select": "NOPE"}).status_code == 400


# ---------------------------------------------------------------- the approval workflow and validity
def test_validity_is_worked_out_against_the_clock():
    row = {"APPROVAL_STATUS": "Approved", "VALID_FROM": "2026-01-01T00:00:00Z", "VALID_UNTIL": "2027-01-01T00:00:00Z"}
    assert validity(row, datetime(2026, 6, 1, tzinfo=UTC)) == "VALID"
    assert validity(row, datetime(2027, 1, 1, tzinfo=UTC)) == "EXPIRED"
    assert validity(row, datetime(2025, 12, 31, tzinfo=UTC)) == "NOT_YET_VALID"
    assert validity(row | {"APPROVAL_STATUS": "Submitted"}, datetime(2026, 6, 1, tzinfo=UTC)) == "NOT_APPROVED"


def test_approval_workflow(client):
    url = ODATA + "/LifeAssessments('LA-MTR-2041')"
    assert client.patch(url, json={"RUL_MONTHS": 40}).status_code == 409  # approved: read-only
    drafts = get(client, "/LifeAssessments", **{"$filter": "APPROVAL_STATUS eq 'Draft'"})["value"]
    assert drafts and all(d["VALIDITY"] == "NOT_APPROVED" and d["REQUAL_STATUS"] == "PENDING" for d in drafts)
    key = drafts[0]["ASSESSMENT_ID"]
    url = ODATA + f"/LifeAssessments('{key}')"
    assert client.post(url + "/AssetWise.Submit").status_code == 400  # no remaining life yet
    assert client.patch(url, json={"ASSET_ID": "X"}).status_code == 400
    assert client.patch(url, json={"RUL_MONTHS": 30, "RUL_LOW_MONTHS": 32}).status_code == 400  # outside its range
    assert (
        client.patch(url, json={"RUL_MONTHS": 8, "RUL_LOW_MONTHS": 6, "RUL_HIGH_MONTHS": 10, "CONFIDENCE": "LOW"}).status_code
        == 204
    )
    assert client.post(url + "/AssetWise.Approve", auth=APPROVER).status_code == 409  # not submitted
    assert client.post(url + "/AssetWise.Submit").status_code == 204
    assert client.post(url + "/AssetWise.Approve", auth=CONNECTOR).status_code == 403  # the submitter (via IMS) cannot approve
    r = client.post(url + "/AssetWise.Approve", auth=APPROVER)
    assert r.status_code == 400 and "below the minimum" in r.json()["error"]["message"]
    assert client.post(url + "/AssetWise.Reject", auth=APPROVER).status_code == 204
    assert get(client, f"/LifeAssessments('{key}')")["REQUAL_STATUS"] == "REJECTED"

    with engine.connect() as conn:
        before = clock.now(conn)
    assert client.patch(url, json={"RUL_MONTHS": 30, "RUL_LOW_MONTHS": 25, "RUL_HIGH_MONTHS": 34}).status_code == 204
    a = get(client, f"/LifeAssessments('{key}')")
    assert (a["APPROVAL_STATUS"], a["LIFE_TEXT"]) == ("Draft", "30 months")
    assert client.post(url + "/AssetWise.Submit").status_code == 204
    assert client.post(url + "/AssetWise.Approve", auth=APPROVER, json={"Comment": "Reviewed"}).status_code == 204
    a = get(client, f"/LifeAssessments('{key}')")
    assert (a["APPROVAL_STATUS"], a["REQUAL_STATUS"], a["VALIDITY"], a["APPROVED_BY"]) == (
        "Approved",
        "APPROVED",
        "VALID",
        "eng.approver",
    )
    assert datetime.fromisoformat(a["APPROVED_AT"]) >= before.replace(microsecond=0)
    since = before.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = get(client, "/LifeAssessments", **{"$filter": f"MODIFIED_ON ge {since}", "$select": "ASSESSMENT_ID"})["value"]
    assert [c["ASSESSMENT_ID"] for c in changed] == [key]
    with engine.connect() as conn:
        types = [
            r.type
            for r in conn.execute(
                text("SELECT type FROM sim.outbox WHERE source = 'eng' AND subject = :k ORDER BY id"), {"k": key}
            )
        ]
    assert types[-2:] == ["com.bentley.assetwise.LifeAssessment.Submitted", "com.bentley.assetwise.LifeAssessment.Approved"]
