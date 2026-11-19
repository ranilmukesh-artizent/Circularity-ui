"""B5b contract tests: call the Oracle Transportation Management mock as an OTM REST client does."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim import scheduler
from sim.db import engine
from sim.main import app

API = "/otm/logisticsRestApi/resources/v2"
USER = ("NORTHFIELD.DI_CONNECTOR", "otm-demo-password")
LANE = "NORTHFIELD.RC-2026.2_WH-MAA-02>LOC-CHN-03"


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)  # no lifespan: /_sim/reset?system= builds the schema
    c.post("/_sim/reset", params={"system": "tms"}).raise_for_status()
    yield c
    c.post("/_sim/reset", params={"system": "tms"}).raise_for_status()


@pytest.fixture(scope="module")
def h(client):
    r = client.post("/otm/oauth2/v1/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "tms-demo-secret"))
    assert r.status_code == 200 and r.json()["token_type"] == "Bearer"
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def outbox(type_: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT data FROM sim.outbox WHERE source = 'tms' AND type = :t ORDER BY id"), {"t": type_})
        return [r.data for r in rows]


def test_auth_and_error_bodies(client, h):
    r = client.get(API + "/shipments")
    assert r.status_code == 401 and r.json()["status"] == 401 and r.json()["title"] == "Unauthorized"
    assert r.headers["content-type"].startswith("application/vnd.oracle.resource+json;type=error")
    assert client.get(API + "/shipments", auth=("NORTHFIELD.DI_CONNECTOR", "wrong")).status_code == 401
    assert client.get(API + "/shipments", headers={"Authorization": "Bearer nope"}).status_code == 401
    bad = client.post("/otm/oauth2/v1/token", data={"grant_type": "client_credentials"}, auth=("di-connector", "x"))
    assert bad.status_code == 401 and bad.json()["error"] == "invalid_client"
    assert client.get(API + "/shipments", auth=USER, params={"limit": 1}).status_code == 200  # Basic works too
    assert client.get(API + "/nope", headers=h).status_code == 404
    assert client.get(API + "/shipments/NORTHFIELD.NOPE", headers=h).status_code == 404
    r = client.get(API + "/shipments", headers=h, params={"q": 'shipmentXid eq "LD-21048'})
    assert r.status_code == 400 and "q" in r.json()["detail"]
    assert client.get(API + "/shipments", headers=h, params={"limit": "0"}).status_code == 400


def test_paging_links_and_total(client, h):
    r = client.get(API + "/xLanes", headers=h, params={"limit": 10, "offset": 0, "totalResults": "true"}).json()
    assert r["count"] == 10 and r["hasMore"] is True and r["totalResults"] > 10 and r["limit"] == 10
    nxt = next(x["href"] for x in r["links"] if x["rel"] == "next")
    assert "offset=10" in nxt
    seen, offset = [], 0
    while True:
        page = client.get(API + "/xLanes", headers=h, params={"limit": 25, "offset": offset}).json()
        seen += [x["xLaneGid"] for x in page["items"]]
        if not page["hasMore"]:
            break
        offset += 25
    assert len(seen) == len(set(seen)) == r["totalResults"]
    desc = client.get(API + "/locations", headers=h, params={"orderBy": "locationXid:desc", "limit": 2}).json()["items"]
    assert desc[0]["locationXid"] > desc[1]["locationXid"]
    only = client.get(API + "/locations", headers=h, params={"fields": "locationGid", "limit": 1}).json()["items"][0]
    assert set(only) == {"locationGid", "links"}


def test_lane_rate_and_carrier(client, h):
    """MAPPINGS.tms: lane WH-MAA-02>LOC-CHN-03, 34 km, INR 3,600 (= $43 at 83.5), carrier NLTL Northline 3PL."""
    g = client.get(f"{API}/rateGeos/{LANE}", headers=h, params={"expand": "costs"}).json()
    assert g["minCost"] == {"value": 3600.0, "currency": "INR"} and g["rateOfferingGid"] == "NORTHFIELD.RC-2026.2"
    assert [c["chargeAmount"]["value"] for c in g["costs"]["items"]] == [20.0, 1200.0]
    lane = client.get(API + "/xLanes/NORTHFIELD.WH-MAA-02%3ELOC-CHN-03", headers=h).json()
    assert lane["attributeNumber1"] == 34 and lane["destLocationGid"] == "NORTHFIELD.LOC-CHN-03"
    ro = client.get(API + "/rateOfferings/NORTHFIELD.RC-2026.2", headers=h).json()
    assert ro["servprovGid"] == "NORTHFIELD.NLTL" and ro["attribute1"] == "NL-MSA-2025-11"
    sp = client.get(API + "/serviceProviders", headers=h, params={"expand": "servprovAliases"}).json()["items"]
    assert {a["alias"] for s in sp for a in s["servprovAliases"]["items"]} == {"NLTL", "VLFR", "CSHL"}
    loc = client.get(API + "/locations/NORTHFIELD.NLTL", headers=h).json()
    assert loc["locationName"] == "Northline 3PL"


def test_inbound_return_of_rt_1048(client, h):
    r = client.get(
        API + "/shipments",
        headers=h,
        params={"q": 'refnums.shipmentRefnumValue eq "RT-1048"', "expand": "refnums,trackingEvents,statuses"},
    ).json()
    assert r["count"] == 1
    s = r["items"][0]
    assert s["shipmentXid"] == "LD-21048" and s["destLocationGid"] == "NORTHFIELD.WH-PNQ-01"
    assert s["endTime"]["value"].startswith("2026-10-03T10:00") and s["endTime"]["timezone"] == "Asia/Calcutta"
    refs = {x["shipmentRefnumQualGid"]: x["shipmentRefnumValue"] for x in s["refnums"]["items"]}
    assert refs["NORTHFIELD.ITEM_ID"] == "MTR-2041" and refs["NORTHFIELD.MOVE_TYPE"] == "RETURN_COLLECTION"
    d1 = next(e for e in s["trackingEvents"]["items"] if e["statusCodeGid"] == "PUBLIC.D1")
    assert d1["externalEventReference"] == "POD-21048"
    assert {x["statusValueGid"] for x in s["statuses"]["items"]} >= {"NORTHFIELD.ENROUTE_COMPLETED"}
    stops = client.get(f"{API}/shipments/{s['shipmentGid']}/stops", headers=h).json()
    assert [x["stopType"] for x in stops["items"]] == ["P", "D"]


def test_booking_validation(client, h):
    base = {"orderReleaseXid": "OR-TEST-BAD", "sourceLocationGid": "NORTHFIELD.WH-MAA-02"}
    assert client.post(API + "/orderReleases", headers=h, json=base).status_code == 400  # no destination
    r = client.post(API + "/orderReleases", headers=h, json=base | {"destLocationGid": "NORTHFIELD.NOWHERE"})
    assert r.status_code == 400 and "NOWHERE" in r.json()["detail"]
    r = client.post(
        API + "/orderReleases", headers=h, json=base | {"destLocationGid": "NORTHFIELD.LOC-CHN-03", "totalWeight": {"value": -1}}
    )
    assert r.status_code == 400
    # a lane without a rate record (site to site): created, not planned
    r = client.post(
        API + "/orderReleases",
        headers=h,
        json={
            "orderReleaseXid": "OR-TEST-NORATE",
            "sourceLocationGid": "NORTHFIELD.LOC-CHN-03",
            "destLocationGid": "NORTHFIELD.LOC-PNQ-01",
        },
    )
    assert r.status_code == 201 and r.json()["statuses"]["items"][0]["statusValueGid"] == "NORTHFIELD.PLANNING_NEW"
    assert outbox("otm.orderRelease.planningFailed")[-1]["orderReleaseGid"] == "NORTHFIELD.OR-TEST-NORATE"


def test_booking_plans_a_shipment_that_is_delivered_on_the_clock(client, h):
    body = {
        "orderReleaseXid": "OR-RT-1048-T",
        "sourceLocationGid": "NORTHFIELD.WH-MAA-02",
        "destLocationGid": "NORTHFIELD.LOC-CHN-03",
        "totalWeight": {"value": 370, "unit": "KG"},
        "refnums": {
            "items": [
                {"orderReleaseRefnumQualGid": "NORTHFIELD.CASE_REF", "orderReleaseRefnumValue": "RT-1048"},
                {"orderReleaseRefnumQualGid": "NORTHFIELD.ITEM_ID", "orderReleaseRefnumValue": "MTR-2041"},
                {"orderReleaseRefnumQualGid": "NORTHFIELD.MOVE_TYPE", "orderReleaseRefnumValue": "REDEPLOYMENT"},
            ]
        },
    }
    r = client.post(API + "/orderReleases", headers=h, json=body)
    assert r.status_code == 201, r.text
    assert r.headers["location"].endswith("/orderReleases/NORTHFIELD.OR-RT-1048-T")
    assert r.json()["statuses"]["items"][0]["statusValueGid"] == "NORTHFIELD.PLANNING_PLANNED - FINAL"
    assert client.post(API + "/orderReleases", headers=h, json=body).status_code == 400  # duplicate id
    found = client.get(
        API + "/shipments", headers=h, params={"q": 'orderReleases.orderReleaseGid eq "NORTHFIELD.OR-RT-1048-T"'}
    ).json()
    assert found["count"] == 1
    s = found["items"][0]
    assert s["shipmentXid"].startswith("LD-5") and s["servprovGid"] == "NORTHFIELD.NLTL"
    assert s["totalActualCost"] == {"value": 3600.0, "currency": "INR"} and s["loadedDistance"]["value"] == 34
    etd, eta = (datetime.fromisoformat(s[k]["value"]) for k in ("startTime", "endTime"))
    assert eta - etd == timedelta(hours=0.6)  # 34 km at 55 km/h
    assert outbox("otm.shipment.created")[-1]["shipmentGid"] == s["shipmentGid"]
    stamp = s["updateDate"]["value"]
    quiet = client.get(API + "/shipments", headers=h, params={"q": f'updateDate gt "{stamp}"'}).json()
    assert quiet["count"] == 0

    client.post("/_sim/clock/advance", json={"hours": 3.5}).raise_for_status()
    scheduler.tick()
    done = client.get(f"{API}/shipments/{s['shipmentGid']}", headers=h, params={"expand": "trackingEvents,statuses"}).json()
    codes = [e["statusCodeGid"] for e in done["trackingEvents"]["items"]]
    assert codes == ["PUBLIC.AF", "PUBLIC.X1", "PUBLIC.D1"]
    assert "NORTHFIELD.ENROUTE_COMPLETED" in {x["statusValueGid"] for x in done["statuses"]["items"]}
    pod = done["trackingEvents"]["items"][-1]
    assert (
        pod["externalEventReference"] == "POD-" + s["shipmentXid"][3:] and pod["ssContactName"] == "Receiving · Chennai Foundry"
    )
    assert [e["shipmentGid"] for e in outbox("otm.shipment.delivered")][-1] == s["shipmentGid"]
    # every shipment event carries the order release the caller booked and the refnums, to match it by
    for kind in ("created", "tenderAccepted", "departed", "arrived", "delivered"):
        ev = outbox(f"otm.shipment.{kind}")[-1]
        assert ev["shipmentGid"] == s["shipmentGid"] and ev["shipmentXid"] == s["shipmentXid"]
        assert ev["orderReleaseGids"] == ["NORTHFIELD.OR-RT-1048-T"] and ev["orderReleaseXids"] == ["OR-RT-1048-T"]
        refs = {r["shipmentRefnumQualGid"]: r["shipmentRefnumValue"] for r in ev["refnums"]}
        assert refs["NORTHFIELD.CASE_REF"] == "RT-1048" and refs["NORTHFIELD.MOVE_TYPE"] == "REDEPLOYMENT"
    assert outbox("otm.shipment.delivered")[-1]["externalEventReference"] == "POD-" + s["shipmentXid"][3:]
    changed = client.get(API + "/shipments", headers=h, params={"q": f'updateDate gt "{stamp}"'}).json()
    assert [x["shipmentGid"] for x in changed["items"]] == [s["shipmentGid"]]
