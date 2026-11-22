"""B5b contract tests: call the MasterControl mock the way a MasterControl REST client does."""

import base64
from datetime import UTC, timedelta

import pytest
from fastapi.testclient import TestClient

from sim.core import clock
from sim.core.registry import BY_SOURCE_ID
from sim.main import app
from sim.seed import seed
from sim.vendors.mastercontrol import seed as mc_seed

API = "/mastercontrol/mc/api"
KEY = {"X-API-KEY": "circularity-demo-mastercontrol-apikey"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "qms"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "qms"}).raise_for_status()


def get_all(client, path, **params):
    out, cursor = [], None
    while True:
        r = client.get(API + path, headers=KEY, params=params | ({"cursor": cursor} if cursor else {}))
        assert r.status_code == 200, r.text
        body = r.json()
        out += body["data"]
        cursor = body["paging"]["nextCursor"]
        if not cursor:
            return out


def test_registry_and_seed():
    assert BY_SOURCE_ID["qms"].base_path == "/mastercontrol"
    d = mc_seed.rows(seed())
    (cert,) = [c for c in d["certificate"] if c["data_fields"]["ASSET_ID"] == "MTR-2041"]
    assert (cert["certificate_number"], cert["data_fields"]["CERTIFIED_LIFE_MONTHS"]) == ("QMS-2906", 24)


def test_auth(client):
    url = API + "/v2/certificates"
    r = client.get(url)
    assert r.status_code == 401 and r.json()["errorCode"] == "UNAUTHORIZED" and r.json()["path"] == url
    assert client.get(url, headers={"X-API-KEY": "nope"}).status_code == 401
    bad = client.post(API + "/oauth2/token", data={"grant_type": "client_credentials", "client_id": "x", "client_secret": "y"})
    assert bad.status_code == 401 and bad.json()["error"] == "invalid_client"
    basic = base64.b64encode(b"circularity-di:circularity-demo-mastercontrol-secret").decode()
    tok = client.post(
        API + "/oauth2/token", data={"grant_type": "client_credentials"}, headers={"Authorization": "Basic " + basic}
    )
    assert tok.status_code == 200 and tok.json()["token_type"] == "bearer"
    r = client.get(url, headers={"Authorization": "Bearer " + tok.json()["access_token"]}, params={"limit": 1})
    assert r.status_code == 200 and len(r.json()["data"]) == 1


def test_rt_1048_certificate(client):
    (c,) = get_all(client, "/v2/certificates", assetId="MTR-2041")
    assert (c["recordId"], c["certificateNumber"], c["certificateType"], c["status"]) == (
        "CERT-MTR-2041",
        "QMS-2906",
        "LIFE_CERTIFICATION",
        "Active",
    )
    f = c["dataFields"]
    assert (f["CERT_EXPIRY"], f["REUSE_CLASS"], f["TEST_RESULT"], f["CERTIFIED_LIFE_MONTHS"]) == (
        "2027-03-01",
        "ALLOWED_CAT2",
        "PASS",
        24,
    )
    rq = client.get(API + "/v2/certificates/CERT-CTL-0122", headers=KEY).json()
    assert rq["certificateType"] == "REQUALIFICATION" and rq["issuedDate"] == "2026-09-12"  # CF-32
    assert client.get(API + "/v2/certificates/NOPE", headers=KEY).json()["errorCode"] == "NOT_FOUND"


def test_cursor_paging_and_errors(client):
    total = client.get(API + "/v2/certificates", headers=KEY).json()["totalCount"]
    assert len(get_all(client, "/v2/certificates", limit=7)) == total > 50
    assert client.get(API + "/v2/certificates", headers=KEY, params={"limit": 5000}).json()["errorCode"] == "INVALID_PARAMETER"
    assert client.get(API + "/v2/certificates", headers=KEY, params={"cursor": "%%"}).status_code == 400


def test_only_effective_revisions_are_policy(client):
    revs = {d["revision"]: d for d in get_all(client, "/v2/controlled-documents", documentNumber="POL-REUSE-MTR")}
    assert revs["3.1"]["status"] == "Superseded" and revs["3.1"]["supersededDate"] == "2026-04-01"
    assert revs["3.2"]["status"] == "Effective" and revs["3.2"]["dataFields"]["REUSE_CLASS"] == "ALLOWED_CAT2"
    assert revs["3.3"]["status"] == "In Approval" and revs["3.3"]["effectiveDate"] is None
    eff = get_all(client, "/v2/controlled-documents", status="Effective", documentType="Policy")
    assert sorted(d["documentNumber"] for d in eff if d["documentNumber"].startswith("POL-REUSE")) == sorted(
        f"POL-REUSE-{p}" for p in ("MTR", "PMP", "CTL", "DRL", "BAT", "ITE")
    )
    assert len(get_all(client, "/v2/test-criteria", assetClass="motor")) == 4
    dev = get_all(client, "/v2/deviations", assetId="MTR-2041")
    assert dev[0]["deviationId"] == "DEV-118" and dev[0]["approverName"] == "Q. Lead"


def _new(today, **over):
    body = {
        "certificateNumber": "QMS-T-1",
        "certificateType": "LIFE_CERTIFICATION",
        "issuedDate": (today - timedelta(days=400)).isoformat(),
        "dataFields": {
            "ASSET_ID": "MTR-TEST-1",
            "CERT_EXPIRY": (today - timedelta(days=1)).isoformat(),
            "TEST_RESULT": "PASS",
            "CERTIFIED_LIFE_MONTHS": 12,
            "DOCUMENT_NUMBER": "POL-REUSE-MTR",
        },
    }
    return body | over


def test_write_validation_expiry_revoke_and_delta(client):
    today = clock.now().astimezone(UTC).date()
    url = API + "/v2/certificates"
    r = client.post(url, headers=KEY, json={"certificateType": "X"})
    assert r.status_code == 400 and r.json()["errorCode"] == "VALIDATION_ERROR"
    assert {e["field"] for e in r.json()["errors"]} >= {"certificateNumber", "certificateType", "issuedDate"}
    future = _new(today, issuedDate=(today + timedelta(days=3)).isoformat())
    assert client.post(url, headers=KEY, json=future).status_code == 400
    draft_only = _new(today)
    draft_only["dataFields"] = draft_only["dataFields"] | {"DOCUMENT_NUMBER": "POL-NOT-THERE"}
    assert client.post(url, headers=KEY, json=draft_only).json()["errorCode"] == "DOCUMENT_NOT_EFFECTIVE"

    mark = client.get(url, headers=KEY, params={"assetId": "MTR-2041"}).json()["data"][0]["lastModifiedDate"]
    before = client.get(url, headers=KEY, params={"modifiedSince": clock.now().isoformat()}).json()["totalCount"]
    r = client.post(url, headers=KEY, json=_new(today))
    assert r.status_code == 201, r.text
    c = r.json()
    assert r.headers["Location"].endswith(c["recordId"]) and c["status"] == "Expired"  # expired the day after CERT_EXPIRY
    assert c["dataFields"]["REUSE_CLASS"] == "ALLOWED_CAT2"  # from the effective revision 3.2
    assert client.post(url, headers=KEY, json=_new(today)).json()["errorCode"] == "DUPLICATE_CERTIFICATE_NUMBER"
    since = client.get(url, headers=KEY, params={"modifiedSince": mark}).json()["data"]
    assert c["recordId"] in {x["recordId"] for x in since} and before == 0

    valid = _new(today, certificateNumber="QMS-T-2")
    valid["dataFields"] = valid["dataFields"] | {
        "ASSET_ID": "MTR-TEST-2",
        "CERT_EXPIRY": (today + timedelta(days=30)).isoformat(),
    }
    v = client.post(url, headers=KEY, json=valid).json()
    assert v["status"] == "Active"
    rv = client.post(f"{url}/{v['recordId']}/revoke", headers=KEY, json={"reason": "Failed audit"})
    assert rv.status_code == 200 and rv.json()["status"] == "Revoked"
    assert client.post(f"{url}/{v['recordId']}/revoke", headers=KEY, json={"reason": "again"}).status_code == 409
    revoked = get_all(client, "/v2/certificates", status="Revoked")
    assert [x["recordId"] for x in revoked] == [v["recordId"]]
