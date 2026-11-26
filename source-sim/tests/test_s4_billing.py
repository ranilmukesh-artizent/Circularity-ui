"""P9-13.4 (X-16) contract tests: the S/4HANA mock's customer credit memo and its `amount` fault (sim/vendors/s4/billing.py)."""

import pytest
from fastapi.testclient import TestClient

from sim.main import app

AUTH = ("DI_CONNECTOR", "Circularity-demo-1")
PATH = "/sap/bc/srt/scs_ext/sap/creditmemo"
BODY = {"customer": "CUST-1", "amount": 160, "currency": "USD"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()
        yield c
        c.delete("/_sim/faults", params={"system": "erp"})
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()


def test_requires_authentication(client):
    assert client.post(PATH, json={}).status_code == 401


def test_memo_answers_the_posted_amount(client):
    r = client.post(PATH, auth=AUTH, json=BODY | {"externalReference": "APR-C-1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["amount"], d["currency"]) == (160, "USD") and d["creditMemo"]


def test_memo_is_idempotent_on_the_external_reference(client):
    first = client.post(PATH, auth=AUTH, json=BODY | {"externalReference": "APR-C-1"}).json()
    again = client.post(PATH, auth=AUTH, json=BODY | {"amount": 5, "externalReference": "APR-C-1"}).json()
    assert again == first


def test_missing_field_and_bad_amount_are_refused(client):
    assert client.post(PATH, auth=AUTH, json={"customer": "C"}).status_code == 422
    assert client.post(PATH, auth=AUTH, json=BODY | {"amount": 0, "externalReference": "APR-C-2"}).status_code == 422


def test_amount_fault_posts_a_different_amount(client):
    client.post("/_sim/faults", json={"system": "erp", "kind": "amount", "value": 15000}).raise_for_status()
    r = client.post(PATH, auth=AUTH, json=BODY | {"externalReference": "APR-C-3"}).json()
    client.delete("/_sim/faults", params={"system": "erp"})
    assert r["amount"] == 150
