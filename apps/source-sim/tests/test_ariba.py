"""B4 contract tests: call the Ariba mock the way an Ariba API client does (docs/backend-steps.md)."""

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from sim.main import app
from sim.seed import seed

API = "/ariba/api"
REALM = {"realm": "northfield-T"}
KEY = {"apiKey": "circularity-demo-ariba-key"}
RANGE = json.dumps({"updatedDateFrom": "2026-01-01T00:00:00Z", "updatedDateTo": "2026-12-31T00:00:00Z"})


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "proc"}).raise_for_status()
        yield c


@pytest.fixture(scope="module")
def h(client):
    r = client.post(
        "/ariba/v2/oauth/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "circularity-demo-ariba-secret")
    )
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    return KEY | {"Authorization": "Bearer " + r.json()["access_token"]}


def get_all(client, h, path, params=None, key="payload", token="pageToken"):
    out, params = [], dict(REALM | (params or {}))
    while True:
        body = client.get(API + path, headers=h, params=params).json()
        out += body[key]
        if not body.get(token):
            return out
        params["pageToken"] = body[token]


# ---------------- security
def test_needs_api_key_token_and_realm(client, h):
    url = API + "/supplier-data/v4/prod/suppliers"
    assert client.get(url, params=REALM).status_code == 401  # nothing
    assert client.get(url, headers=KEY, params=REALM).status_code == 401  # no token
    assert client.get(url, headers=h | {"apiKey": "wrong"}, params=REALM).status_code == 401
    assert client.get(url, headers=h).status_code == 400  # no realm
    assert client.get(url, headers=h, params={"realm": "other-T"}).status_code == 403
    assert client.get(url, headers=h, params=REALM).status_code == 200
    bad = client.post("/ariba/v2/oauth/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "nope"))
    assert bad.status_code == 401


# ---------------- the demo's mapping example: RT-1048
def test_rt_1048_quote_matches_the_demo_mapping(client, h):
    """QuotedUnitPrice €10,400.00 → $11,300 at 0.92; SupplierLeadTime 21 days; SupplierId SUP-88120."""
    ev = client.get(API + "/sourcing-event/v2/prod/events/Doc1048", headers=h, params=REALM).json()
    assert ev["externalReference"] == "49048" and ev["plant"] == "1030" and ev["currency"] == "EUR"
    bids = client.get(API + "/sourcing-event/v2/prod/events/Doc1048/bids", headers=h, params=REALM).json()["payload"]
    best = bids[0]
    assert (best["supplierId"], best["supplierName"], best["leadTimeDays"]) == ("SUP-88120", "Voltara", 21)
    assert best["unitPrice"] == {"amount": 10400.0, "currency": "EUR"}
    assert round(Decimal("10400") / Decimal("0.92"), -2) == 11300
    assert [b["unitPrice"]["amount"] for b in bids] == sorted(b["unitPrice"]["amount"] for b in bids)


def test_supplier_links_to_s4(client, h):
    s = client.get(API + "/supplier-data/v4/prod/suppliers/SUP-88120", headers=h, params=REALM).json()
    assert s["name"] == "Voltara" and s["erpVendorId"].startswith("00100000")
    assert client.get(API + "/supplier-data/v4/prod/suppliers/SUP-1", headers=h, params=REALM).status_code == 404


# ---------------- paging and totals
def test_events_page_through_every_planned_purchase(client, h):
    events = get_all(client, h, "/sourcing-event/v2/prod/events")
    expected = {
        f"Doc{c.facts.id.split('-')[1]}"
        for c in seed().cases.values()
        if c.facts.demand.internal and any(t.kind == "purchase" and t.amt > 0 for r in c.facts.routes for t in r.terms)
    }
    assert {e["eventId"] for e in events} == expected and len(expected) > 25  # more than one page
    assert get_all(client, h, "/sourcing-event/v2/prod/events", {"status": "Completed"}) == []


def test_reporting_view_needs_a_date_range_and_pages(client, h):
    url = API + "/procurement-reporting-details/v2/prod/views/PurchaseOrders"
    assert client.get(url, headers=h, params=REALM).status_code == 400
    too_long = json.dumps({"updatedDateFrom": "2024-01-01T00:00:00Z", "updatedDateTo": "2026-12-31T00:00:00Z"})
    assert client.get(url, headers=h, params=REALM | {"filters": too_long}).status_code == 400
    pos = get_all(
        client,
        h,
        "/procurement-reporting-details/v2/prod/views/PurchaseOrders",
        {"filters": RANGE},
        key="Records",
        token="PageToken",
    )
    events = get_all(client, h, "/sourcing-event/v2/prod/events")
    assert len(pos) == len(events)
    rt = next(p for p in pos if p["ERPPONumber"] == "49048")
    assert rt["StatusString"] == "Composing" and rt["TotalCost"] == {"amount": 10400.0, "currency": "EUR"}
    assert client.get(url, headers=h, params=REALM | {"filters": RANGE, "pageToken": "!!"}).status_code == 400


def test_suppliers_cover_every_manufacturer(client, h):
    names = {m for c in seed().world.classes.values() for m in c.mfr}
    assert {s["name"] for s in get_all(client, h, "/supplier-data/v4/prod/suppliers")} == names
