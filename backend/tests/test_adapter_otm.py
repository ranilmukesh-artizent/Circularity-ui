"""B5b/B9: the Oracle Transportation Management adapter (tms) against source-sim's OTM mock.

Needs source-sim running and the worker stopped. Only tms is reset, and only its cursors and queued jobs cleared.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
SID = "tms"
API = "/otm/logisticsRestApi/resources/v2"
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"
LANE = "WH-MAA-02>LOC-CHN-03"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def clear_state() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})


@pytest.fixture(scope="module", autouse=True)
def reset_tms():
    sim("DELETE", "/_sim/faults", params={"system": SID})
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = :s"), {"s": SID})
        s.commit()
    clear_state()
    yield
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    clear_state()


def sync(trigger: str = "schedule") -> dict:
    out = run_sync(SID, trigger)
    assert out["status"] in ("ok", "partial"), out
    if out["status"] == "partial":
        assert "deadlock" in (out["error"] or "").lower(), out
        again = run_sync(SID, "manual", full=True)
        assert again["status"] in ("ok", "partial"), again
    return out


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, (model, key)
    return rec


def prov(model: str, key: str, field: str) -> dict:
    rows = [p for p in canonical(model, key)["provenance"].get(field, []) if p["source_id"] == SID]
    assert rows, (model, key, field)
    return rows[0]


def mapping(p: dict) -> tuple:
    return p["source_field"], p["source_value"], p["value"], p["transform"]


def test_initial_sync_reproduces_lanes_carriers_and_inbound_loads():
    out = sync("initial")
    assert out["records_read"] >= 3 + 1 + 63 + 128  # carriers, rate offering, rate records, shipments
    d = canonical("route", LANE)["data"]
    assert (d["leg"], d["lane_rate"], d["lane_rate_inr"], d["carrier"], d["distance_km"], d["destination_facility"]) == (
        "WH-MAA-02 → LOC-CHN-03",
        43.0,
        3600.0,
        "Northline 3PL",
        34,
        "ST03",
    )
    assert d["rate_basis"] == "34 km · minimum charge ₹3,600"
    rate = prov("route", LANE, "lane_rate")
    assert rate["authority"] is True and mapping(rate) == ("minCost", "3600.00 INR", 43.0, RATE_NOTE)
    assert mapping(prov("route", LANE, "carrier")) == ("servprovGid", "NLTL", "Northline 3PL", "Carrier lookup")
    assert mapping(prov("route", LANE, "leg")) == ("xLaneGid", LANE, "WH-MAA-02 → LOC-CHN-03", "Lane decode")
    card = canonical("route", "RC-2026.2")["data"]
    assert (card["carrier"], card["contract_ref"], card["minimum_charge_inr"]) == ("Northline 3PL", "NL-MSA-2025-11", 3600)
    assert canonical("vendor", "NLTL")["data"]["name"] == "Northline 3PL"
    a = canonical("asset", "MTR-2041")["data"]
    assert (a["inbound_load"], a["inbound_eta"], a["inbound_pod_ref"], a["inbound_lane"]) == (
        "LD-21048",
        "2026-10-03T10:00",
        "POD-21048",
        "LOC-PNQ-01>WH-PNQ-01",
    )
    load = canonical("route", "LD-21048")["data"]
    assert (load["direction"], load["status"], load["case_ref"]) == ("INBOUND", "DELIVERED", "RT-1048")


def test_delta_reads_nothing_then_a_booking_and_its_delivery():
    assert run_sync(SID, "schedule")["records_read"] == 0
    r = sim(
        "POST",
        API + "/orderReleases",
        auth=("NORTHFIELD.DI_CONNECTOR", "otm-demo-password"),
        json={
            "orderReleaseXid": "OR-ADAPTER-T1",
            "sourceLocationGid": "NORTHFIELD.WH-MAA-02",
            "destLocationGid": "NORTHFIELD.LOC-CHN-03",
            "totalWeight": {"value": 370, "unit": "KG"},
            "refnums": {
                "items": [
                    {"orderReleaseRefnumQualGid": "NORTHFIELD.ITEM_ID", "orderReleaseRefnumValue": "MTR-2041"},
                    {"orderReleaseRefnumQualGid": "NORTHFIELD.CASE_REF", "orderReleaseRefnumValue": "RT-1048"},
                    {"orderReleaseRefnumQualGid": "NORTHFIELD.MOVE_TYPE", "orderReleaseRefnumValue": "REDEPLOYMENT"},
                ]
            },
        },
    )
    assert r.status_code == 201
    out = sync()
    assert out["records_read"] == 1
    ships = sim(
        "GET",
        API + "/shipments",
        auth=("NORTHFIELD.DI_CONNECTOR", "otm-demo-password"),
        params={"q": 'orderReleases.orderReleaseGid eq "NORTHFIELD.OR-ADAPTER-T1"'},
    ).json()["items"]
    lid = ships[0]["shipmentXid"]
    d = canonical("route", lid)["data"]
    assert (d["carrier"], d["freight"], d["status"], d["direction"]) == ("Northline 3PL", 43.0, "BOOKED", "OUTBOUND")
    eta = prov("route", lid, "eta")
    assert eta["source_field"] == "endTime" and eta["value"] == eta["source_value"][:16] and eta["transform"] == "Site time kept"
    assert canonical("asset", "MTR-2041")["data"]["outbound_load"] == lid

    sim("POST", "/_sim/clock/advance", json={"hours": 3.5})  # runs the scheduled tracking events
    assert sync()["records_read"] == 1
    d = canonical("route", lid)["data"]
    assert d["status"] == "DELIVERED" and d["pod_ref"] == "POD-" + lid[3:] and d["delivered_at"]
    assert run_sync(SID, "schedule")["records_read"] == 0
