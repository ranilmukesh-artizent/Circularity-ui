"""B5b: Optoro mock, called as an Optoro API client would (see sim/vendors/optoro)."""

import pytest
from fastapi.testclient import TestClient

from sim import scheduler
from sim.main import app

B = "/optoro"


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.post("/_sim/reset", params={"system": "rl"}).raise_for_status()
    yield c
    c.post("/_sim/reset", params={"system": "rl"}).raise_for_status()


@pytest.fixture(scope="module")
def h(client):
    r = client.post(
        B + "/auth/oauth/token",
        json={"grant_type": "client_credentials", "client_id": "di-connector", "client_secret": "rl-demo-secret"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer" and body["expires_in"] == 90000 and body["scope"] == "read write"
    assert isinstance(body["created_at"], int)
    return {"Authorization": "Bearer " + body["access_token"]}


def list_all(client, h, path, key, **params) -> list[dict]:
    out, q = [], dict(params) | {"per_page": 7}
    for _ in range(200):
        r = client.get(B + path, headers=h, params=q)
        assert r.status_code == 200, r.text
        body = r.json()
        out += body[key]
        if body["next_page"] is None:
            assert int(r.headers["record_count"]) == len(out)
            return out
        assert body["next_page"]["path"].startswith(path)
        q["offset"] = body["next_page"]["offset"]
    raise AssertionError("paging did not end")


def test_auth(client, h):
    bad = client.post(B + "/auth/oauth/token", json={"grant_type": "client_credentials", "client_id": "x", "client_secret": "y"})
    assert bad.status_code == 401 and bad.json()["error"] == "invalid_client"
    r = client.get(B + "/returns/rmas")
    assert r.status_code == 401 and r.content == b""
    assert client.get(B + "/returns/rmas", headers={"X-Api-Key": "rl-demo-key"}).status_code == 200
    assert client.get(B + "/returns/rmas", headers=h, params={"per_page": 500}).status_code == 422
    assert client.get(B + "/returns/rmas/RMA-0", headers=h).json() == {"message": "Not Found"}


def test_rt_1048_reads(client, h):
    rmas = list_all(client, h, "/returns/rmas", "rmas")
    assert len(rmas) > 50 and len({r["rma_identifier"] for r in rmas}) == len(rmas)
    (rma,) = list_all(client, h, "/returns/rmas", "rmas", secondary_identifier="RT-1048")
    item = rma["items"][0]
    assert rma["rma_identifier"] == "RMA-56509" and item["sku"] == "MTR-2041"
    assert item["exchange_order_identifier"] == "SO-48102" and item["receiving_status"] == "RECEIVED"
    assert rma["warehouse_id"] == "WH01" and rma["receiving_complete"] is True
    one = client.get(B + "/returns/rmas/RMA-56509", headers=h)
    assert one.status_code == 200 and one.json() == rma
    (rcpt,) = list_all(client, h, "/inventory/inventory_receipts", "inventory_receipts", sku="MTR-2041")
    assert rcpt["received_at"] == "2026-10-03T15:28:00-04:00" and rcpt["to"]["original_identifier"] == "WH01"
    assert rcpt["reference"] == {"type": "RMA", "identifier": "RMA-56509", "alternate_identifier": "RT-1048"}
    (asn,) = list_all(client, h, "/asn/asns", "asns", sku="MTR-2041")
    assert asn["shipment_identifier"] == "LD-21048" and asn["status"] == "delivered"
    disp = list_all(client, h, "/returns/dispositions", "dispositions", sku="MTR-2041")
    assert [d["to_disposition"] for d in disp] == ["rts"]  # grade B
    every = list_all(client, h, "/returns/dispositions", "dispositions")
    assert {"rts", "refurbish"} <= {d["to_disposition"] for d in every}
    # delta: nothing changed after the seed
    later = client.get(B + "/returns/rmas", headers=h, params={"updated_at": "2026-10-07T09:00:00Z"}).json()
    assert later["rmas"] == []


def _advance(client, days: float):
    client.post("/_sim/clock/advance", json={"days": days}).raise_for_status()
    scheduler.tick()


def test_return_authorisation_receive_and_dispose(client, h):
    client.post("/_sim/reset", params={"system": "rl"}).raise_for_status()
    bad = client.post(B + "/returns/rmas", headers=h, json={"items": [{"sku": "MTR-2041"}], "return_method": "teleport"})
    assert bad.status_code == 422
    fields = {(e["field"], e["code"]) for e in bad.json()["errors"]}
    assert ("return_method", "invalid") in fields and ("items[0].order_identifier", "missing_field") in fields
    r = client.post(
        B + "/returns/rmas",
        headers=h,
        json={
            "items": [
                {
                    "sku": "DRL-0001",
                    "order_identifier": "LC-4100",
                    "secondary_identifier": "RT-9001",
                    "return_reason": "early return",
                }
            ],
            "return_method": "home-pickup",
            "warehouse_id": "WH02",
        },
    )
    assert r.status_code == 201, r.text
    rma = r.json()
    assert rma["status"] == "CREATED" and rma["items"][0]["receiving_status"] == "PENDING"
    rid = rma["rma_identifier"]
    asn = {
        "program_identifier": "lease_returns",
        "from": {"identifier": "LOC-CHN-03", "type": "CustomerSite"},
        "to": {"identifier": "WH02", "type": "Warehouse"},
        "asn_number": "SHP-T1",
        "status": "shipped",
        "details_type": "unit",
        "carrier": "Northline 3PL",
        "cartons": [
            {
                "reference": {"type": "RMA", "identifier": rid},
                "details": [{"line_identifier": "1", "sku": "DRL-0001", "quantity": 1}],
            }
        ],
    }
    assert client.post(B + "/asn/asns", headers=h, json=asn).status_code == 202
    assert client.post(B + "/asn/asns", headers=h, json=asn).status_code == 422  # duplicate
    assert client.put(B + "/asn/asns/SHP-T1", headers=h, json=asn | {"tracking_number": "NLTL1"}).status_code == 202
    receipt = {
        "program_identifier": "lease_returns",
        "asn_number": "SHP-T1",
        "from": {"identifier": "LOC-CHN-03", "type": "CustomerSite"},
        "to": {"identifier": 102, "type": "Warehouse", "original_identifier": "WH02"},
        "reference": {"type": "RMA", "identifier": rid, "alternate_identifier": "RT-9001"},
        "unit_identifier": "LPTEST0001",
        "sku": "DRL-0001",
        "initial_condition": "TT",
        "initial_channel": "needs_testing",
        "ot_user_login": "receiving.wh02@northfield",
    }
    wrong = client.post(B + "/inventory/inventory_receipt", headers=h, json=receipt | {"sku": "OTHER"})
    assert wrong.status_code == 422
    first = client.post(B + "/inventory/inventory_receipt", headers=h, json=receipt)
    assert first.status_code == 201, first.text
    assert first.json()["received_at"].endswith("-04:00")
    again = client.post(B + "/inventory/inventory_receipt", headers=h, json=receipt)
    assert again.status_code == 200 and again.json() == first.json()
    got = client.get(B + f"/returns/rmas/{rid}", headers=h).json()
    assert got["items"][0]["receiving_status"] == "RECEIVED" and got["receiving_complete"] is True
    shipped = client.get(B + "/asn/asns/SHP-T1", headers=h).json()
    assert shipped["status"] == "delivered" and shipped["receptions"] == 1
    assert client.put(B + "/asn/asns/SHP-T1", headers=h, json=asn).status_code == 422  # received against

    # dispositions: not received -> refused; assign refurbish, then supersede with rts; only rts is finalised
    assert (
        client.post(
            B + "/returns/dispositions", headers=h, json={"optiturn_lp": "NOPE", "to_disposition": "rts", "to_condition": "B"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            B + "/returns/dispositions",
            headers=h,
            json={"optiturn_lp": "LPTEST0001", "to_disposition": "sell", "to_condition": "B"},
        ).status_code
        == 422
    )
    d1 = client.post(
        B + "/returns/dispositions",
        headers=h,
        json={"optiturn_lp": "LPTEST0001", "to_disposition": "refurbish", "to_condition": "C"},
    )
    assert d1.status_code == 201 and d1.json()["from_disposition"] == "needs_testing"
    d2 = client.post(
        B + "/returns/dispositions", headers=h, json={"optiturn_lp": "LPTEST0001", "to_disposition": "rts", "to_condition": "B"}
    )
    assert d2.status_code == 201 and d2.json()["from_disposition"] == "refurbish"
    _advance(client, 1.01)
    finals = list_all(client, h, "/returns/final_dispositions", "final_dispositions", optiturn_lp="LPTEST0001")
    assert [(f["disposition"], f["condition"]) for f in finals] == [("rts", "B")]
    _advance(client, 2.1)  # the superseded refurbish disposition does not finalise
    assert len(list_all(client, h, "/returns/final_dispositions", "final_dispositions", optiturn_lp="LPTEST0001")) == 1
    late = client.post(
        B + "/returns/dispositions",
        headers=h,
        json={"optiturn_lp": "LPTEST0001", "to_disposition": "recycle", "to_condition": "X"},
    )
    assert late.status_code == 422
    types = [e["type"] for e in client.get("/_sim/outbox", params={"source": "rl", "limit": 100}).json()]
    for t in (
        "optoro.rma.created",
        "optoro.asn.created",
        "optoro.inventory_receipt.created",
        "optoro.rma.updated",
        "optoro.disposition.updated",
        "optoro.final_disposition.created",
    ):
        assert t in types
