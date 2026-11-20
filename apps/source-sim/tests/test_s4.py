"""B3 contract tests: call the S/4HANA mock the way a real S/4 client does (docs/backend-steps.md)."""

import pytest
from fastapi.testclient import TestClient

from sim.main import app

AUTH = ("DI_CONNECTOR", "Circularity-demo-1")
SRV = "/sap/opu/odata/sap"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "erp"}).raise_for_status()
        yield c


def csrf(client) -> dict:
    r = client.get(f"{SRV}/API_RESERVATION_DOCUMENT_SRV/", auth=AUTH, headers={"x-csrf-token": "Fetch"})
    assert r.status_code == 200 and r.headers["x-csrf-token"]
    return {"x-csrf-token": r.headers["x-csrf-token"]}


# ---------------- security
def test_requires_authentication(client):
    r = client.get(f"{SRV}/API_PRODUCT_SRV/A_Product")
    assert r.status_code == 401 and "SAP NetWeaver" in r.headers["www-authenticate"]
    assert client.get(f"{SRV}/API_PRODUCT_SRV/A_Product", auth=("DI_CONNECTOR", "wrong")).status_code == 401


def test_oauth_client_credentials(client):
    assert (
        client.post(
            "/sap/bc/sec/oauth2/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "bad")
        ).status_code
        == 401
    )
    tok = client.post(
        "/sap/bc/sec/oauth2/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "circularity-demo-secret")
    ).json()
    assert tok["token_type"] == "bearer" and tok["expires_in"] == 3600
    r = client.get(f"{SRV}/API_PRODUCT_SRV/A_Product('MTR-2041')", headers={"Authorization": "Bearer " + tok["access_token"]})
    assert r.status_code == 200


def test_post_without_csrf_token_is_refused(client):
    r = client.post(f"{SRV}/API_RESERVATION_DOCUMENT_SRV/A_ReservationDocumentHeader", auth=AUTH, json={})
    assert r.status_code == 403 and r.headers["x-csrf-token"] == "Required"
    assert r.text == "CSRF token validation failed"


# ---------------- reads
def test_product_by_key_matches_the_seed(client):
    d = client.get(f"{SRV}/API_PRODUCT_SRV/A_Product('MTR-2041')", auth=AUTH).json()["d"]
    assert d["Product"] == "MTR-2041" and d["ProductGroup"] == "MTR" and d["ManufacturerNumber"] == "Voltara"
    assert d["__metadata"]["type"] == "API_PRODUCT_SRV.A_ProductType"
    assert d["LastChangeDateTime"].startswith("/Date(") and d["LastChangeDateTime"].endswith("+0000)/")
    assert d["to_Description"]["__deferred"]["uri"].endswith("A_Product('MTR-2041')/to_Description")


def test_rt_1048_purchase_baseline(client):
    """The demo's mapping: EKPO-NETPR 10,02,000.00 INR at plant 1030 (Site 3) = 12,000 USD purchase baseline."""
    r = client.get(
        f"{SRV}/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder('49048')", auth=AUTH, params={"$expand": "to_PurchaseOrderItem"}
    ).json()["d"]
    assert r["PurchasingDocumentCategory"] == "F" and r["DocumentCurrency"] == "INR"
    item = r["to_PurchaseOrderItem"]["results"][0]
    assert (item["Plant"], item["NetPriceAmount"], item["OrderQuantity"]) == ("1030", "1002000.00", "1.000")


def test_query_options(client):
    url = f"{SRV}/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod"
    page = client.get(
        url,
        auth=AUTH,
        params={
            "$filter": "Plant eq '2010' and InventoryStockType eq '01'",
            "$select": "Material,Plant,MatlWrhsStkQtyInMatlBaseUnit",
            "$orderby": "Material desc",
            "$top": "5",
            "$skip": "1",
            "$inlinecount": "allpages",
            "$format": "json",
        },
    ).json()["d"]
    assert int(page["__count"]) >= 6 and len(page["results"]) == 5
    assert all(set(r) == {"__metadata", "Material", "Plant", "MatlWrhsStkQtyInMatlBaseUnit"} for r in page["results"])
    assert [r["Material"] for r in page["results"]] == sorted((r["Material"] for r in page["results"]), reverse=True)
    n = client.get(url + "/$count", auth=AUTH, params={"$filter": "Plant eq '2010' and InventoryStockType eq '01'"}).text
    assert n == page["__count"]


def test_delta_read(client):
    url = f"{SRV}/API_PRODUCT_SRV/A_Product"
    all_ = client.get(url, auth=AUTH, params={"$inlinecount": "allpages", "$top": "0"}).json()["d"]["__count"]
    assert int(all_) == 128
    after = client.get(url, auth=AUTH, params={"$filter": "LastChangeDateTime gt datetimeoffset'2100-01-01T00:00:00Z'"}).json()
    assert after["d"]["results"] == []


def test_errors_use_the_sap_body(client):
    r = client.get(f"{SRV}/API_PRODUCT_SRV/A_Product", auth=AUTH, params={"$filter": "Nope eq 1"})
    assert (
        r.status_code == 400 and r.json()["error"]["message"]["lang"] == "en" and "Nope" in r.json()["error"]["message"]["value"]
    )
    assert client.get(f"{SRV}/API_NOPE_SRV/A_X", auth=AUTH).status_code == 404
    assert client.get(f"{SRV}/API_PRODUCT_SRV/A_Product('NOPE')", auth=AUTH).status_code == 404


def test_metadata(client):
    r = client.get(f"{SRV}/API_PURCHASEORDER_PROCESS_SRV/$metadata", auth=AUTH)
    assert r.status_code == 200 and "application/xml" in r.headers["content-type"]
    assert '<EntitySet Name="A_PurchaseOrder"' in r.text and 'Name="NetPriceAmount" Type="Edm.Decimal"' in r.text


# ---------------- writes
def stock(client, material, plant, sloc="RT01") -> str:
    r = client.get(
        f"{SRV}/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod",
        auth=AUTH,
        params={
            "$filter": f"Material eq '{material}' and Plant eq '{plant}' and StorageLocation eq '{sloc}'"
            " and InventoryStockType eq '01'"
        },
    )
    res = r.json()["d"]["results"]
    return res[0]["MatlWrhsStkQtyInMatlBaseUnit"] if res else "0"


def test_reservation_then_transfer_moves_rt_1048_to_site_3(client):
    """The redeploy instruction for RT-1048: reserve the motor in Warehouse 1, then transfer it to Site 3."""
    h = csrf(client)
    assert stock(client, "MTR-2041", "2010") == "1.000"
    r = client.post(
        f"{SRV}/API_RESERVATION_DOCUMENT_SRV/A_ReservationDocumentHeader",
        auth=AUTH,
        headers=h,
        json={
            "GoodsMovementType": "311",
            "IssuingOrReceivingPlant": "1030",
            "GoodsRecipientName": "Customer A",
            "YY1_CircularityRef_RSV": "APR-2026-10-0161",
            "to_ReservationDocumentItem": {
                "results": [
                    {"Product": "MTR-2041", "Plant": "2010", "StorageLocation": "RT01", "ResvnItmRequiredQtyInBaseUnit": "1"}
                ]
            },
        },
    )
    assert r.status_code == 201, r.text
    res = r.json()["d"]
    rsnum = res["Reservation"]
    assert len(rsnum) == 10 and res["to_ReservationDocumentItem"]["results"][0]["Product"] == "MTR-2041"
    assert r.headers["location"].endswith(f"A_ReservationDocumentHeader('{rsnum}')")

    # a second reservation for the same unit is refused: nothing is promised twice
    again = client.post(
        f"{SRV}/API_RESERVATION_DOCUMENT_SRV/A_ReservationDocumentHeader",
        auth=AUTH,
        headers=h,
        json={"to_ReservationDocumentItem": [{"Product": "MTR-2041", "Plant": "2010", "ResvnItmRequiredQtyInBaseUnit": "1"}]},
    )
    assert again.status_code == 400 and again.json()["error"]["code"] == "M7/021"

    md = client.post(
        f"{SRV}/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader",
        auth=AUTH,
        headers=h,
        json={
            "GoodsMovementCode": "04",
            "PostingDate": "2026-10-08T00:00:00",
            "MaterialDocumentHeaderText": "Redeploy RT-1048",
            "to_MaterialDocumentItem": {
                "results": [
                    {
                        "Material": "MTR-2041",
                        "Plant": "2010",
                        "StorageLocation": "RT01",
                        "GoodsMovementType": "301",
                        "IssuingOrReceivingPlant": "1030",
                        "IssuingOrReceivingStorageLoc": "RT01",
                        "QuantityInEntryUnit": "1",
                        "Reservation": rsnum,
                        "ReservationItem": "0001",
                    }
                ]
            },
        },
    )
    assert md.status_code == 201, md.text
    doc = md.json()["d"]
    assert doc["MaterialDocument"].startswith("49") and doc["MaterialDocumentYear"] == "2026"
    assert stock(client, "MTR-2041", "2010") == "0.000"
    assert stock(client, "MTR-2041", "1030") == "1.000"

    # the change shows up in a delta read and as an outbox event
    rows = client.get(
        f"{SRV}/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod",
        auth=AUTH,
        params={"$filter": "Material eq 'MTR-2041' and LastChangeDateTime gt datetimeoffset'2026-10-07T09:00:00Z'"},
    ).json()["d"]["results"]
    assert {r["Plant"] for r in rows} == {"2010", "1030"}


def test_goods_issue_cannot_go_negative(client):
    h = csrf(client)
    r = client.post(
        f"{SRV}/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader",
        auth=AUTH,
        headers=h,
        json={
            "GoodsMovementCode": "03",
            "to_MaterialDocumentItem": [
                {"Material": "PMP-0320", "Plant": "2010", "GoodsMovementType": "261", "QuantityInEntryUnit": "99"}
            ],
        },
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "M7/021"


def test_reset_restores_the_seed(client):
    client.post("/_sim/reset", params={"system": "erp"}).raise_for_status()
    assert stock(client, "MTR-2041", "2010") == "1.000"
    assert stock(client, "MTR-2041", "1030") == "0"
