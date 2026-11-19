"""B5 contract tests: call the IBM Sterling OMS mock the way a Sterling REST client does (docs/BACKEND_STEPS.md)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.db import engine
from sim.main import app
from sim.seed import seed

API = "/sterling/smcfs/restapi"
CLIENT = ("di-connector", "circularity-demo-sterling-secret")
RT_1048_SO = "20261007001048" + "01"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "oms"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "oms"}).raise_for_status()


@pytest.fixture(scope="module")
def h(client):
    r = client.post(API + "/oauth/token", data={"grant_type": "client_credentials"}, auth=CLIENT)
    assert r.status_code == 200 and r.json()["token_type"] == "Bearer"
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def get_all(client, h, path, params=None):
    out, page = [], 1
    while True:
        body = client.get(API + path, headers=h, params=(params or {}) | {"PageNumber": page, "PageSize": 25}).json()
        out += body["Order"]
        if body["IsLastPage"] == "Y":
            assert len(out) == body["TotalOrderList"]
            return out
        page += 1


def outbox(type_: str) -> list[dict]:
    with engine.connect() as conn:
        return [
            r.data
            for r in conn.execute(
                text("SELECT data FROM sim.outbox WHERE source = 'oms' AND type = :t ORDER BY id"), {"t": type_}
            )
        ]


# ---------------- security
def test_oauth_and_errors(client, h):
    assert client.get(API + "/order").status_code == 401
    r = client.get(API + "/order", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.json()["errors"][0]["ErrorCode"] == "YFS10001" and r.json()["errors"][0]["httpcode"] == 401
    bad = client.post(API + "/oauth/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "wrong"))
    assert bad.status_code == 401 and bad.json()["error"] == "invalid_client"
    form = {"grant_type": "client_credentials", "client_id": CLIENT[0], "client_secret": CLIENT[1]}
    assert client.post("/sterling/oauth2/token", data=form).status_code == 200
    assert client.post(API + "/oauth/token", data={"grant_type": "password"}, auth=CLIENT).status_code == 400
    assert client.get(API + "/order", headers=h, params={"PageSize": "0"}).json()["errors"][0]["ErrorCode"] == "YFC0101"
    assert client.get(API + "/order", headers=h, params={"FromModifyts": "yesterday"}).status_code == 400
    assert client.get(API + "/order/NOPE", headers=h).status_code == 404


# ---------------- the demo's mapping example: RT-1048 → SO-48102 line 10
def test_rt_1048_order_matches_the_demo_mapping(client, h):
    """OrderNo SO-48102, PrimeLineNo 10, ShipToKey LOC-CHN-03, ReqDeliveryDate 2026-10-17T00:00:00+05:30."""
    body = client.get(API + "/order", headers=h, params={"OrderNo": "SO-48102"}).json()
    assert body["TotalOrderList"] == 1
    o = body["Order"][0]
    assert o["OrderHeaderKey"] == RT_1048_SO and o["DocumentType"] == "0001" and o["EnterpriseCode"] == "NORTHFIELD"
    assert o["BuyerOrganizationCode"] == "CUSTOMER_A" and o["ShipToKey"] == "LOC-CHN-03"
    assert o["PersonInfoShipTo"]["AddressLine1"] == "Chennai Foundry" and o["PersonInfoShipTo"]["AddressLine2"] == "Site 3"
    assert o["ReqDeliveryDate"] == "2026-10-17T00:00:00+05:30" and o["Extn"]["ExtnDemandStatus"] == "CONFIRMED"
    (line,) = o["OrderLines"]["OrderLine"]
    assert (line["PrimeLineNo"], line["SubLineNo"], line["Status"], line["MaxLineStatus"]) == ("10", "1", "Created", "1100")
    assert line["Item"]["ItemID"] == "MTR-55KW" and line["OrderedQty"] == "1.00"
    assert line["LinePriceInfo"]["UnitPrice"] == "12000.00"  # "a new one would cost $12,000"
    assert line["Extn"]["ExtnAcceptsRefurbished"] == "Y" and line["Extn"]["ExtnAvoidedPurchaseOrder"] == "PO-49048"
    lines = client.get(f"{API}/order/{RT_1048_SO}/lines", headers=h).json()
    assert lines["TotalLineList"] == 1 and lines["OrderLine"][0]["OrderLineKey"] == line["OrderLineKey"]


def test_rt_1048_return_authorisation(client, h):
    body = client.get(API + "/return", headers=h, params={"SerialNo": "MTR-2041"}).json()
    assert body["TotalOrderList"] == 1
    r = body["Order"][0]
    assert r["OrderNo"] == "RMA-56509" and r["DocumentType"] == "0003" and r["ReceivingNode"] == "WH01"
    assert r["Extn"]["ExtnReceiptNo"] == "GR-570262" and r["Extn"]["ExtnCustomerIntent"]
    (line,) = r["OrderLines"]["OrderLine"]
    assert line["SerialNo"] == "MTR-2041" and line["Status"] == "Return Received" and line["ReturnReason"]
    assert line["Extn"]["ExtnReceivedDate"] == "2026-10-03T05:30:00+05:30"
    assert client.get(f"{API}/return/{r['OrderHeaderKey']}", headers=h).json()["OrderNo"] == "RMA-56509"
    assert client.get(f"{API}/return/{RT_1048_SO}", headers=h).status_code == 404  # a sales order is not a return


# ---------------- lists, filters, paging
def test_orders_and_returns_cover_the_world(client, h):
    cases = list(seed().cases.values())
    orders = get_all(client, h, "/order")
    internal = [c for c in cases if c.facts.demand.internal]
    assert len(orders) == len(internal) == 71
    assert len({o["OrderNo"] for o in orders}) == 71
    returns = get_all(client, h, "/return")
    assert len(returns) == len(cases) == 128 and len({r["OrderNo"] for r in returns}) == 128
    assert {r["OrderLines"]["OrderLine"][0]["SerialNo"] for r in returns} == {c.facts.asset_id for c in cases}
    # filters
    a = client.get(API + "/order", headers=h, params={"BuyerOrganizationCode": "CUSTOMER_A", "PageSize": 200}).json()
    assert 0 < a["TotalOrderList"] < 71 and {o["BuyerOrganizationCode"] for o in a["Order"]} == {"CUSTOMER_A"}
    assert client.get(API + "/order", headers=h, params={"EnterpriseCode": "OTHER"}).json()["TotalOrderList"] == 0
    rt = client.get(API + "/order", headers=h, params={"DocumentType": "0003", "OrderNo": "RMA-56509"}).json()
    assert rt["TotalOrderList"] == 1
    created = client.get(API + "/order", headers=h, params={"Status": "1100", "PageSize": 200}).json()
    assert created["TotalOrderList"] > 0 and all(o["MinOrderStatus"] == "1100" for o in created["Order"])
    multi = [o for o in orders if len(o["OrderLines"]["OrderLine"]) > 1]
    assert multi and all(o["Status"] == "Partially Delivered" for o in multi)
    for o in multi:  # earlier contract lines are new equipment only: never allocatable
        assert all(ln["Extn"]["ExtnAcceptsRefurbished"] == "N" for ln in o["OrderLines"]["OrderLine"][:-1])


# ---------------- writes: allocate, then fulfil to delivered
def test_allocate_rt_1048_once_then_fulfil_to_delivered(client, h):
    since = "2026-10-07T00:00:00Z"
    assert client.get(API + "/order", headers=h, params={"FromModifyts": since}).json()["TotalOrderList"] == 0

    alloc = {"OrderNo": "SO-48102", "PrimeLineNo": "10", "SerialNo": "MTR-2041", "Reference": "DEC-1048"}
    r = client.post(API + "/order/allocate", headers=h | {"Idempotency-Key": "k1"}, json=alloc)
    assert r.status_code == 200, r.text
    line = r.json()["OrderLines"]["OrderLine"][0]
    assert line["Status"] == "Scheduled" and line["ShipNode"] == "WH01" and line["Item"]["ProductClass"] == "REFURB"
    res = line["OrderLineReservations"]["OrderLineReservation"][0]
    assert res["SerialNo"] == "MTR-2041" and res["ReturnOrderNo"] == "RMA-56509" and res["Node"] == "WH01"

    # nothing is promised twice
    again = client.post(API + "/order/allocate", headers=h | {"Idempotency-Key": "k1"}, json=alloc)
    assert again.status_code == 200  # the same request retried
    dup = client.post(API + "/order/allocate", headers=h, json=alloc)
    assert dup.status_code == 409 and dup.json()["errors"][0]["ErrorCode"] == "YFS10260"
    # RT-1062 (also a 55 kW motor, "needed at Site 5") has its own order line that MTR-2041 would fit
    other_so = "2026100700106201"
    last = client.get(f"{API}/order/{other_so}/lines", headers=h).json()["OrderLine"][-1]
    assert last["Item"]["ItemID"] == "MTR-55KW" and last["Status"] == "Created"
    taken = client.post(
        API + "/order/allocate",
        headers=h,
        json={"OrderHeaderKey": other_so, "PrimeLineNo": last["PrimeLineNo"], "SerialNo": "MTR-2041"},
    )
    assert taken.status_code == 409 and taken.json()["errors"][0]["ErrorCode"] == "YFS10261"
    assert "SO-48102 line 10" in taken.json()["errors"][0]["ErrorDescription"]

    # the change shows up in a delta read and as an outbox event
    delta = client.get(API + "/order", headers=h, params={"FromModifyts": since}).json()
    assert [o["OrderNo"] for o in delta["Order"]] == ["SO-48102"]
    ev = outbox("sterling.order.allocated")
    assert ev and ev[-1]["SerialNo"] == "MTR-2041" and ev[-1]["PrimeLineNo"] == "10" and ev[-1]["Reference"] == "DEC-1048"

    url = f"{API}/order/{RT_1048_SO}/fulfil"
    skip = client.post(url, headers=h, json={"PrimeLineNo": "10", "Action": "DELIVER"})
    assert skip.status_code == 409 and skip.json()["errors"][0]["ErrorCode"] == "YFS10270"
    assert client.post(url, headers=h, json={"PrimeLineNo": "10", "Action": "RELEASE"}).json()["Status"] == "Released"
    shipped = client.post(url, headers=h, json={"PrimeLineNo": "10", "SCAC": "NLTL", "TrackingNo": "NL-778812"}).json()
    assert shipped["Status"] == "Shipped" and shipped["OrderLines"]["OrderLine"][0]["Shipment"]["TrackingNo"] == "NL-778812"
    no_pod = client.post(url, headers=h, json={"PrimeLineNo": "10", "Action": "DELIVER"})
    assert no_pod.status_code == 400
    pod = {"ReceivedBy": "Site 3 stores, Customer A", "DeliveryDate": "2026-10-13T08:36:00+05:30", "PODReference": "POD-1"}
    done = client.post(url, headers=h, json={"PrimeLineNo": "10", "Action": "DELIVER", "ProofOfDelivery": pod})
    assert done.status_code == 200
    o = done.json()
    line = o["OrderLines"]["OrderLine"][0]
    assert o["Status"] == "Delivered" and line["MaxLineStatus"] == "3700.7777"
    assert line["ProofOfDelivery"]["ReceivedBy"] == pod["ReceivedBy"]
    assert line["ProofOfDelivery"]["DeliveryDate"] == "2026-10-13T08:36:00+05:30"
    assert [s["Status"] for s in line["OrderStatuses"]["OrderStatus"]] == ["1100", "1500", "3200", "3700", "3700.7777"]
    assert client.post(url, headers=h, json={"PrimeLineNo": "10"}).status_code == 409  # nothing left to do
    for kind in ("released", "shipped", "fulfilled"):
        assert outbox(f"sterling.order.{kind}")[-1]["OrderNo"] == "SO-48102"


def test_allocation_is_refused_when_it_does_not_fit(client, h):
    multi = next(o for o in get_all(client, h, "/order") if len(o["OrderLines"]["OrderLine"]) > 1)
    key = multi["OrderHeaderKey"]
    new_only = client.post(
        API + "/order/allocate", headers=h, json={"OrderHeaderKey": key, "PrimeLineNo": "10", "SerialNo": "MTR-2041"}
    )
    assert new_only.status_code in (400, 409)
    last = multi["OrderLines"]["OrderLine"][-1]
    unknown = client.post(
        API + "/order/allocate",
        headers=h,
        json={"OrderHeaderKey": key, "PrimeLineNo": last["PrimeLineNo"], "SerialNo": "XXX-0000"},
    )
    assert unknown.status_code == 404 and unknown.json()["errors"][0]["ErrorCode"] == "YFS10005"
    pump = next(
        r["OrderLines"]["OrderLine"][0]["SerialNo"]
        for r in get_all(client, h, "/return")
        if not r["OrderLines"]["OrderLine"][0]["Item"]["ItemID"].startswith(last["Item"]["ItemID"][:3])
    )
    wrong = client.post(
        API + "/order/allocate", headers=h, json={"OrderHeaderKey": key, "PrimeLineNo": last["PrimeLineNo"], "SerialNo": pump}
    )
    assert wrong.status_code == 400 and wrong.json()["errors"][0]["ErrorCode"] == "YFS10255"
    assert (
        client.post(API + "/order/allocate", headers=h, json={"OrderNo": "SO-1", "PrimeLineNo": 10, "SerialNo": "X"}).status_code
        == 404
    )
    assert client.post(API + "/order/allocate", headers=h, json={"OrderNo": "SO-48102"}).status_code == 400
    assert client.post(API + "/order/allocate", headers=h, content=b"not json").status_code == 400
    assert client.post(f"{API}/order/{key}/fulfil", headers=h, json={"PrimeLineNo": "999"}).status_code == 404


def test_reset_restores_the_seed(client, h):
    client.post("/_sim/reset", params={"system": "oms"}).raise_for_status()
    o = client.get(f"{API}/order/{RT_1048_SO}", headers=h).json()
    assert o["Status"] == "Created" and "OrderLineReservations" not in o["OrderLines"]["OrderLine"][0]
