"""B5b: Manhattan Active WM mock, called as a real Manhattan Active client would (see sim/vendors/manhattan)."""

import pytest
from fastapi.testclient import TestClient

from sim import scheduler
from sim.main import app

B = "/manhattan"
INV = B + "/dcinventory/api/dcinventory/inventory/search"
RSV = B + "/dcinventory/api/dcinventory/reservation"
ORDER = B + "/dcorder/api/dcorder/order"


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.post("/_sim/reset", params={"system": "wms"}).raise_for_status()
    yield c
    c.post("/_sim/reset", params={"system": "wms"}).raise_for_status()


def token(client) -> str:
    r = client.post(
        B + "/oauth/token",
        data={"grant_type": "password", "username": "circularity.integration@northfield", "password": "wms-demo-password"},
        auth=("di-connector", "wms-demo-secret"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["scope"] == "omni" and body["refresh_token"]
    return body["access_token"]


@pytest.fixture(scope="module")
def h(client):
    return {"Authorization": "Bearer " + token(client), "SelectedOrganization": "NORTHFIELD", "SelectedLocation": "WH01"}


def search(client, h, path, query="", size=100, page=0, **hdr):
    r = client.post(path, headers=h | hdr, json={"Query": query, "Size": size, "Page": page})
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_and_errors(client, h):
    assert client.post(INV, json={}).status_code == 401
    bad = client.post(
        B + "/oauth/token",
        data={"grant_type": "password", "username": "x", "password": "y"},
        auth=("di-connector", "wms-demo-secret"),
    )
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_grant"
    assert (
        client.post(B + "/oauth/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "nope")).status_code
        == 401
    )
    cc = client.post(B + "/oauth/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "wms-demo-secret"))
    assert cc.status_code == 200
    r = client.post(INV, headers={"Authorization": h["Authorization"], "SelectedOrganization": "NORTHFIELD"}, json={})
    body = r.json()
    assert r.status_code == 400 and body["success"] is False and body["statusCode"] == "BAD_REQUEST"
    assert body["messages"]["Message"][0]["MessageKey"] == "com.manh.cp.common.invalidLocation"
    q = client.post(INV, headers=h, json={"Query": "ItemId = = 'x'"})
    assert q.status_code == 400 and q.json()["messages"]["Message"][0]["Code"] == "invalidQuery"


def test_inventory_search_rt_1048(client, h):
    body = search(client, h, INV, "InventoryAttribute1 = 'RT-1048'")
    assert body["success"] and body["cloudComponent"] == "com-manh-cp-dcinventory"
    assert body["requestUri"] == "/dcinventory/api/dcinventory/inventory/search"
    (inv,) = body["data"]
    assert (inv["ItemId"], inv["FacilityId"], inv["OnHand"], inv["ProductStatusId"], inv["LocationId"]) == (
        "MTR-2041",
        "WH01",
        1,
        "AVAILABLE",
        "WH01-RT-09",
    )
    assert inv["ReceivedDate"] == "2026-10-03" and body["header"]["totalCount"] == 1
    # scoped by SelectedLocation: WH02 does not see it
    assert search(client, h, INV, "ItemId = 'MTR-2041'", SelectedLocation="WH02")["data"] == []


def test_paging_and_query_operators(client, h):
    full = search(client, h, INV, size=1000)
    total = full["header"]["totalCount"]
    assert total == len(full["data"]) > 10
    seen, page = [], 0
    while True:
        b = search(client, h, INV, size=7, page=page)
        seen += [d["InventoryId"] for d in b["data"]]
        page += 1
        if page >= b["header"]["totalPages"]:
            break
    assert seen == [d["InventoryId"] for d in full["data"]]
    some = search(client, h, INV, "ItemId in ('MTR-2041','nope') or (OnHand > 1000 and ItemId like 'MTR%')")["data"]
    assert [d["ItemId"] for d in some] == ["MTR-2041"]
    fac = search(client, h, B + "/facility/api/facility/facility/search", "FacilityId in ('WH01','RC01','ST03')")["data"]
    assert {f["FacilityId"]: f["Description"] for f in fac}["WH01"] == "Warehouse 1" and len(fac) == 3
    pix = search(client, h, B + "/pix/api/pix/pix/search", "ReferenceId = 'RT-1048'")["data"]
    assert pix[0]["TransactionType"] == "RECEIPT" and pix[0]["TransactionTimestamp"].startswith("2026-10-03")


def test_reservation_allocates_and_refuses_double_allocation(client, h):
    client.post("/_sim/reset", params={"system": "wms"}).raise_for_status()
    r = client.post(RSV + "/save", headers=h, json={"ItemId": "MTR-2041", "Quantity": 1, "OrderId": "SO-48102"})
    assert r.status_code == 200, r.text
    rsv = r.json()["data"]
    assert rsv["ReservationStatus"] == "RESERVED" and rsv["ReservationId"].startswith("R-77")
    inv = search(client, h, INV, "ItemId = 'MTR-2041'")["data"][0]
    assert (inv["Allocated"], inv["Available"]) == (1, 0)
    again = client.post(RSV + "/save", headers=h, json={"ItemId": "MTR-2041", "Quantity": 1})
    assert again.status_code == 409 and again.json()["messages"]["Message"][0]["Code"] == "alreadyAllocated"
    # status change refused while allocated
    st = client.post(
        B + "/dcinventory/api/dcinventory/inventory/changeProductStatus",
        headers=h,
        json={"InventoryId": inv["InventoryId"], "ProductStatusId": "HOLD"},
    )
    assert st.status_code == 409
    got = client.get(RSV + "/reservationId/" + rsv["ReservationId"], headers=h)
    assert got.status_code == 200 and got.json()["data"]["OrderId"] == "SO-48102"
    cancel = client.post(RSV + "/cancel", headers=h, json={"ReservationId": rsv["ReservationId"]})
    assert cancel.status_code == 200 and cancel.json()["data"]["ReservationStatus"] == "CANCELLED"
    assert search(client, h, INV, "ItemId = 'MTR-2041'")["data"][0]["Available"] == 1
    types = [e["type"] for e in client.get("/_sim/outbox", params={"source": "wms"}).json()]
    assert {"manhattan.reservation.created", "manhattan.reservation.cancelled"} <= set(types)


def test_status_change_and_hold_blocks_allocation(client, h):
    client.post("/_sim/reset", params={"system": "wms"}).raise_for_status()
    st = client.post(
        B + "/dcinventory/api/dcinventory/inventory/changeProductStatus",
        headers=h,
        json={"InventoryId": "INV-MTR-2041", "ProductStatusId": "HOLD", "ReasonCode": "QA"},
    )
    assert st.status_code == 200 and st.json()["data"]["ProductStatusId"] == "HOLD"
    r = client.post(RSV + "/save", headers=h, json={"ItemId": "MTR-2041", "Quantity": 1})
    assert r.status_code == 400 and r.json()["messages"]["Message"][0]["Code"] == "inventoryNotAvailable"
    bad = client.post(
        B + "/dcinventory/api/dcinventory/inventory/changeProductStatus",
        headers=h,
        json={"InventoryId": "INV-MTR-2041", "ProductStatusId": "LOST"},
    )
    assert bad.status_code == 400


def _advance(client, hours: float):
    client.post("/_sim/clock/advance", json={"hours": hours}).raise_for_status()
    scheduler.tick()


def test_transfer_pick_pack_ship_on_the_clock(client, h):
    client.post("/_sim/reset", params={"system": "wms"}).raise_for_status()
    rsv = client.post(RSV + "/save", headers=h, json={"ItemId": "MTR-2041", "Quantity": 1, "OrderId": "SO-48102"}).json()["data"]
    bad = client.post(
        ORDER + "/save", headers=h, json={"OrderType": "TRANSFER", "DestinationFacilityId": "XX", "OrderLine": [{}]}
    )
    assert bad.status_code == 400
    r = client.post(
        ORDER + "/save",
        headers=h,
        json={
            "OrderType": "OUTBOUND",
            "DestinationFacilityId": "ST03",
            "ExternalReference": "RT-1048/EX-4",
            "CarrierId": "NLTL",
            "OrderLine": [{"ItemId": "MTR-2041", "OrderedQuantity": 1, "ReservationId": rsv["ReservationId"]}],
        },
    )
    assert r.status_code == 200, r.text
    order = r.json()["data"]
    oid = order["OrderId"]
    assert order["FulfillmentStatus"] == "Allocated"
    assert client.get(RSV + "/reservationId/" + rsv["ReservationId"], headers=h).json()["data"]["ReservationStatus"] == "CONSUMED"
    tasks = search(client, h, B + "/task/api/task/task/search", f"OrderId = '{oid}'")["data"]
    assert [t["TaskType"] for t in tasks] == ["PICK"]

    def status():
        return client.get(ORDER + "/orderId/" + oid, headers=h).json()["data"]["FulfillmentStatus"]

    _advance(client, 2.05)
    assert status() == "Picked"
    inv = search(client, h, INV, "ItemId = 'MTR-2041'")["data"][0]
    assert inv["LocationId"] == "WH01-STAGE" and inv["OnHand"] == 1
    _advance(client, 1.05)
    assert status() == "Packed"
    _advance(client, 1.05)
    assert status() == "Shipped"
    inv = search(client, h, INV, "ItemId = 'MTR-2041'")["data"][0]
    assert (inv["OnHand"], inv["Allocated"], inv["Available"]) == (0, 0, 0)
    shp = search(client, h, B + "/shipment/api/shipment/shipment/search", f"OrderId = '{oid}'")["data"]
    assert len(shp) == 1 and shp[0]["ShipmentStatus"] == "Shipped" and shp[0]["CarrierId"] == "NLTL"
    kinds = [p["TransactionType"] for p in search(client, h, B + "/pix/api/pix/pix/search", f"ReferenceId = '{oid}'")["data"]]
    assert sorted(kinds) == ["INVENTORY_MOVE", "SHIPMENT"]
    types = [e["type"] for e in client.get("/_sim/outbox", params={"source": "wms"}).json()]
    assert types.index("manhattan.order.shipped") < types.index("manhattan.order.packed") < types.index("manhattan.order.picked")
    evs = {e["type"]: e["data"] for e in reversed(client.get("/_sim/outbox", params={"source": "wms"}).json())}
    for kind in ("allocated", "picked", "packed", "shipped"):
        ev = evs[f"manhattan.order.{kind}"]
        assert (ev["OrderId"], ev["ExternalReference"]) == (oid, "RT-1048/EX-4") and ev["order"]["OrderId"] == oid
    assert evs["manhattan.order.shipped"]["shipment"]["ExternalReference"] == "RT-1048/EX-4"
    # the delta query sees the changes
    changed = search(client, h, INV, "UpdatedTimestamp > '2026-10-07T00:00:00.000'")["data"]
    assert "MTR-2041" in [d["ItemId"] for d in changed]
    # nothing left to allocate
    again = client.post(RSV + "/save", headers=h, json={"ItemId": "MTR-2041", "Quantity": 1})
    assert again.status_code == 400
