"""P9-13.1 (X-13) contract tests: the S/4HANA mock's fixed-asset retirement and transfer postings (sim/vendors/s4/assets.py)."""

import pytest
from fastapi.testclient import TestClient

from sim.main import app

AUTH = ("DI_CONNECTOR", "Circularity-demo-1")
RETIRE = "/sap/bc/srt/scs_ext/sap/fixedassetretirement"
TRANSFER = "/sap/bc/srt/scs_ext/sap/fixedassettransfer"
VIN = "SYNUC000000000001"  # the first car: book value 18,000 USD


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()


def test_requires_authentication(client):
    assert client.post(RETIRE, json={}).status_code == 401


def test_retirement_answers_gain_against_book_value(client):
    r = client.post(RETIRE, auth=AUTH, json={"assetKey": VIN, "proceeds": 19250, "externalReference": "APR-T-1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["proceeds"], d["bookValue"], d["gainLoss"], d["currency"]) == (19250, 18000, 1250, "USD")
    assert d["assetDocument"] and d["assetNumber"]


def test_retirement_is_idempotent_on_the_external_reference(client):
    first = client.post(RETIRE, auth=AUTH, json={"assetKey": VIN, "proceeds": 1, "externalReference": "APR-T-1"})
    assert first.status_code == 200 and first.json()["proceeds"] == 19250  # the first document, nothing rewritten


def test_a_retired_asset_is_refused_under_a_new_reference(client):
    r = client.post(RETIRE, auth=AUTH, json={"assetKey": VIN, "proceeds": 5, "externalReference": "APR-T-2"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "asset_retired"


def test_unknown_asset_and_missing_field(client):
    r = client.post(RETIRE, auth=AUTH, json={"assetKey": "NOPE", "proceeds": 5, "externalReference": "APR-T-3"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "asset_not_found"
    assert client.post(RETIRE, auth=AUTH, json={"assetKey": VIN, "externalReference": "APR-T-4"}).status_code == 422


def test_transfer_moves_the_asset_and_is_idempotent(client):
    body = {"assetKey": "SN-TN-0001", "toLocation": "SITE-3", "externalReference": "APR-T-5"}
    a = client.post(TRANSFER, auth=AUTH, json=body)
    assert a.status_code == 200 and a.json()["toLocation"] == "SITE-3"
    assert client.post(TRANSFER, auth=AUTH, json=body | {"toLocation": "SITE-9"}).json() == a.json()
