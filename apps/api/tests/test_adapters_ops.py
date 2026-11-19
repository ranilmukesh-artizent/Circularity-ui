"""B9: the operations adapters (Maximo, Manhattan, Depot Repair, SafetyCulture, Optoro, ShipLane) against source-sim.

Needs source-sim running (docker compose) and the worker stopped. Only these six systems are reset, and only their
cursors and queued jobs are cleared, so other connectors' data is left alone. Other syncs may run at the same time
and deadlock on shared canonical rows; such records are counted as failed by the sync runner, so a run that hit one
is repeated in full before values are checked.
"""

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
MINE = ("eam", "wms", "repair", "insp", "rl", "tms")
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"
GRADE_CONFLICT = "SELECT * FROM conflict WHERE model = 'condition' AND key = 'MTR-2041' AND field = 'grade'"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def token(base: str, sid: str) -> dict:
    r = sim("POST", base + "/oauth/token", data={"grant_type": "client_credentials"}, auth=("di-connector", f"{sid}-demo-secret"))
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def clear_my_state() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = ANY(:m)"),
            {"m": list(MINE)},
        )
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = ANY(:m)"), {"m": list(MINE)})


@pytest.fixture(scope="module", autouse=True)
def reset_my_systems():
    for s in MINE:
        sim("DELETE", "/_sim/faults", params={"system": s})
        sim("POST", "/_sim/reset", params={"system": s})
    sim("POST", "/_sim/webhooks/deliver")  # deliver the reset events now, so they cannot void cursors mid-test
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = ANY(:m)"), {"m": list(MINE)})
        s.commit()
    clear_my_state()
    yield
    for s in MINE:
        sim("POST", "/_sim/reset", params={"system": s})
    sim("POST", "/_sim/webhooks/deliver")
    clear_my_state()


def sync(source_id: str, trigger: str = "schedule") -> dict:
    out = run_sync(source_id, trigger)
    assert out["status"] in ("ok", "partial"), out
    if out["status"] == "partial":
        assert "deadlock" in (out["error"] or "").lower(), out  # only a concurrent sync may make a record fail
        again = run_sync(source_id, "manual", full=True)
        assert again["status"] in ("ok", "partial"), again
    return out


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, (model, key)
    return rec


def prov(model: str, key: str, field: str, source_id: str) -> dict:
    rows = [p for p in canonical(model, key)["provenance"].get(field, []) if p["source_id"] == source_id]
    assert rows, (model, key, field, source_id)
    return rows[0]


def mapping(p: dict) -> tuple:
    return p["source_field"], p["source_value"], p["value"], p["transform"]


# ------------------------------------------------------------------ Oracle Depot Repair
def test_depot_repair_initial_sync_reproduces_the_demo_mapping():
    out = sync("repair", "initial")
    assert out["records_read"] >= 53 + 53  # repair orders, plus task and test-result groups
    iv = canonical("intervention", "MTR-2041")["data"]
    assert (iv["cost"], iv["scope"], iv["hours"], iv["repair_order_ref"]) == (1800.0, "Light repair + test", 22.0, "RO-61048")
    assert mapping(prov("intervention", "MTR-2041", "cost", "repair")) == (
        "repair_cost",
        "1,800.00 USD",
        1800.0,
        "Currency kept in USD",
    )
    assert mapping(prov("intervention", "MTR-2041", "process", "repair")) == (
        "scope",
        "Light repair + test",
        "light repair + test",
        "Process map",
    )
    assert mapping(prov("intervention", "MTR-2041", "predicted_condition", "repair")) == (
        "result_state",
        "B",
        "B",
        "Grade table v3",
    )
    cond = canonical("condition", "MTR-2041")
    assert cond["data"]["grade"] == "B" and cond["data"]["test_result"] == "pass" and cond["data"]["inspection_ref"] == "RO-61048"
    assert prov("condition", "MTR-2041", "grade", "repair")["authority"] is True
    assert canonical("asset", "MTR-2041")["data"]["case_ref"] == "RT-1048"


def test_depot_repair_delta_reads_nothing_then_a_new_repair_order():
    assert run_sync("repair", "schedule")["records_read"] == 0
    base = "/depot-repair/webservices/rest/csd"
    r = sim(
        "POST",
        base + "/repair-orders",
        headers=token(base, "repair"),
        json={"serial": "TST-OPS-1", "scope": "Clean, test and certify", "repair_cost": 950.0, "repair_cost_currency": "USD"},
    )
    out = sync("repair")
    assert out["records_read"] == 1
    iv = canonical("intervention", "TST-OPS-1")["data"]
    assert (iv["cost"], iv["repair_order_ref"]) == (950.0, r.json()["repair_number"])


# ------------------------------------------------------------------ IBM Maximo
def test_maximo_initial_sync_maps_assets_and_service_history():
    out = sync("eam", "initial")
    assert out["records_read"] >= 1448 + 128  # every asset, plus the work-order history of every asset that has one
    a = canonical("asset", "MTR-2041")
    d = a["data"]
    assert (d["asset_id"], d["site"], d["criticality"], d["manufacturer"], d["run_hours"], d["rated_power_kw"]) == (
        "MTR-2041",
        "WH01",
        8,
        "Voltara",
        18450.0,
        55.0,
    )
    ident = prov("asset", "MTR-2041", "asset_id", "eam")
    assert ident["authority"] is True and mapping(ident) == ("ASSETNUM", "MTR-2041", "MTR-2041", "Pass-through; identity key")
    assert mapping(prov("asset", "MTR-2041", "rated_power_kw", "eam")) == ("RATED_PWR", "55000 W", 55.0, "Unit normalised W → kW")
    assert mapping(prov("condition", "MTR-2041", "grade", "eam")) == (
        "CONDITIONCODE",
        "B+",
        "B",
        "Grade table v3 (B+ → B); source value kept",
    )
    assert mapping(prov("condition", "MTR-2041", "service_date", "eam")) == (
        "LASTSERVICEDATE",
        "2026-03-14T08:20:00+05:30",
        "2026-03-14T02:50:00Z",
        "Timestamp to UTC",
    )
    assert d["failure_codes"] == ["BRG-WEAR"] and d["case_ref"] == "RT-1048"
    assert d["failure_history"][0]["cause"] == "LUBE-LOSS" and d["labour_cost"] > 0
    wo = prov("asset", "MTR-2041", "work_order_ref", "eam")
    assert wo["value"] == "1048009" and wo["authority"] is True  # the open periodic inspection
    assert canonical("condition", "MTR-2041")["data"]["inspection_work_order"] == "1048008"


def test_maximo_delta_picks_up_a_new_work_order_and_a_condition_change():
    assert run_sync("eam", "schedule")["records_read"] == 0
    h = {"apikey": "circularity-demo-maximo-apikey"}
    r = sim(
        "POST",
        "/maximo/api/os/mxwo",
        params={"lean": "1"},
        headers=h | {"properties": "wonum,status"},
        json={
            "assetnum": "MTR-2041",
            "siteid": "RC01",
            "worktype": "REFURB",
            "status": "APPR",
            "description": "Refurbish, test and certify - MTR-2041",
            "externalrefid": "WO-47034",
        },
    )
    wonum = r.json()["wonum"]
    out = sync("eam")
    assert out["records_read"] == 1  # one asset's work-order history, re-read whole
    assert canonical("asset", "MTR-2041")["data"]["work_order_ref"] == wonum
    assert prov("asset", "MTR-2041", "work_order_type", "eam")["value"] == "REFURB"

    # Maximo now says grade C; Depot Repair (the authority over the grade) says B: a conflict naming repair
    href = (
        sim("GET", "/maximo/api/os/mxasset", params={"lean": "1", "oslc.where": 'assetnum="MTR-2041"'}, headers=h)
        .json()["member"][0]["href"]
        .removeprefix(SIM)
    )
    patch = {**h, "x-method-override": "PATCH"}
    sim("POST", href, headers=patch, json={"conditioncode": "C"})
    assert sync("eam")["records_read"] == 1
    with SessionLocal() as s:
        c = s.execute(text(GRADE_CONFLICT + " AND status = 'open'")).mappings().one()
    assert c["authority"] == "repair" and c["values"]["eam"] == "C" and c["values"]["repair"] == "B"
    assert canonical("condition", "MTR-2041")["data"]["grade"] == "B"  # the authority's value counts
    sim("POST", href, headers=patch, json={"conditioncode": "B+"})
    sync("eam")
    with SessionLocal() as s:
        last = s.execute(text(GRADE_CONFLICT + " ORDER BY id DESC LIMIT 1")).mappings().one()
    assert last["status"] == "resolved" and last["id"] == c["id"]  # the sources agree again


# ------------------------------------------------------------------ Manhattan WMS
def test_manhattan_initial_sync_maps_location_and_availability():
    out = sync("wms", "initial")
    assert out["records_read"] >= 128 + 128  # inventory and movements
    d = canonical("asset", "MTR-2041")["data"]
    assert (d["location"], d["availability"], d["qty"], d["stock_age_days"], d["case_ref"]) == (
        "Warehouse 1",
        "available",
        1,
        4,
        "RT-1048",
    )
    loc = prov("asset", "MTR-2041", "location", "wms")
    assert loc["authority"] is True and mapping(loc) == ("locationId", "WH01-RT-09", "Warehouse 1", "Zone collapsed to facility")
    assert mapping(prov("asset", "MTR-2041", "qty", "wms")) == ("onHandQuantity", "1 EACH", 1, "UoM normalised")
    assert prov("asset", "MTR-2041", "last_movement_at", "wms")["value"] == "2026-10-03T00:00:00Z"


def test_manhattan_delta_picks_up_a_reservation():
    assert run_sync("wms", "schedule")["records_read"] == 0
    base = "/manhattan/wms/api"
    rsv = sim(
        "POST",
        base + "/reservations",
        headers=token(base, "wms"),
        json={"itemId": "MTR-2041", "quantity": 1, "status": "ACTIVE", "orderReference": "SO-48102"},
    ).json()
    assert sync("wms")["records_read"] == 1
    p = prov("asset", "MTR-2041", "reservation_ref", "wms")
    assert mapping(p) == ("reservationId", rsv["reservationId"], rsv["reservationId"], "Pass-through")
    assert canonical("asset", "MTR-2041")["data"]["reserved_for"] == "SO-48102"


# ------------------------------------------------------------------ SafetyCulture
def test_safetyculture_grades_and_references():
    out = sync("insp", "initial")
    assert out["records_read"] == 59
    with SessionLocal() as s:
        key = s.execute(
            text(
                "SELECT key FROM provenance WHERE source_id = 'insp' AND field = 'grade' "
                "AND source_value = CAST('\"Grade B\"' AS jsonb) ORDER BY key LIMIT 1"
            )
        ).scalar_one()
    g = prov("condition", key, "grade", "insp")
    assert mapping(g) == ("grade_text", "Grade B", "B", "Grade table v3") and g["authority"] is False  # repair has authority
    ref = prov("condition", key, "inspection_ref", "insp")
    assert ref["source_field"] == "audit_id" and ref["source_value"].startswith("audit_") and ref["value"].startswith("INS-")
    assert ref["transform"] == "Reference prefix"
    pc = prov("condition", key, "photo_count", "insp")
    assert pc["transform"] == "Integer" and pc["value"] == pc["source_value"] > 0
    assert run_sync("insp", "schedule")["records_read"] == 0


# ------------------------------------------------------------------ Optoro
def test_optoro_returns_and_dispositions():
    sync("rl", "initial")
    d = canonical("asset", "MTR-2041")["data"]
    assert (d["return_ref"], d["received_at"], d["disposition"], d["case_ref"]) == (
        "RMA-56509",
        "2026-10-03T19:28:00Z",
        "restock",
        "RT-1048",
    )
    rcv = prov("asset", "MTR-2041", "received_at", "rl")
    assert rcv["authority"] is True and mapping(rcv) == (
        "RECEIVED_AT",
        "2026-10-03T15:28:00-04:00",
        "2026-10-03T19:28:00Z",
        "Timestamp to UTC",
    )
    assert mapping(prov("asset", "MTR-2041", "return_ref", "rl")) == ("RMA_ID", "RMA-56509", "RMA-56509", "Pass-through")
    assert prov("asset", "MTR-2041", "inbound_load", "rl")["value"] == "LD-21048"  # shipment mapped through its return
    with SessionLocal() as s:
        refurb = s.execute(
            text(
                "SELECT value, transform FROM provenance WHERE source_id = 'rl' AND field = 'disposition' "
                "AND source_value = CAST('\"REFURB\"' AS jsonb) LIMIT 1"
            )
        ).one()
    assert tuple(refurb) == ("refurbish", "Disposition map")


def test_optoro_delta_picks_up_a_return_authorisation():
    assert run_sync("rl", "schedule")["records_read"] == 0
    ra = sim(
        "POST",
        "/optoro/v1/return-authorizations",
        headers={"X-Api-Key": "rl-demo-key"},
        json={"SKU": "MTR-2041", "CLIENT_REF": "RT-1048", "RMA_ID": "RMA-56509", "QTY": 1, "STATUS": "OPEN"},
    ).json()
    assert sync("rl")["records_read"] == 1
    assert canonical("asset", "MTR-2041")["data"]["return_authorization_ref"] == ra["RA_ID"]


# ------------------------------------------------------------------ ShipLane TMS
def test_shiplane_lanes_and_inbound_loads():
    out = sync("tms", "initial")
    assert out["records_read"] >= 3 + 1 + 63 + 128  # carriers, rate card, lanes, loads
    lane = "WH-MAA-02>LOC-CHN-03"
    d = canonical("route", lane)["data"]
    assert (d["leg"], d["lane_rate"], d["lane_rate_inr"], d["carrier"], d["distance_km"]) == (
        "WH-MAA-02 → LOC-CHN-03",
        43.0,
        3600.0,
        "Northline 3PL",
        34,
    )
    rate = prov("route", lane, "lane_rate", "tms")
    assert rate["authority"] is True and mapping(rate) == ("RateAmt", "3600.00 INR", 43.0, RATE_NOTE)
    assert mapping(prov("route", lane, "carrier", "tms")) == ("CarrierSCAC", "NLTL", "Northline 3PL", "Carrier lookup")
    assert mapping(prov("route", lane, "leg", "tms")) == ("LaneId", lane, "WH-MAA-02 → LOC-CHN-03", "Lane decode")
    a = canonical("asset", "MTR-2041")
    assert (a["data"]["inbound_load"], a["data"]["inbound_eta"], a["data"]["inbound_pod_ref"]) == (
        "LD-21048",
        "2026-10-03T10:00",
        "POD-21048",
    )
    # Optoro and ShipLane agree on the inbound leg: both are on record, no conflict
    assert {p["source_id"] for p in a["provenance"]["inbound_load"]} >= {"rl", "tms"}
    assert {p["source_id"] for p in a["provenance"]["inbound_freight"]} >= {"rl", "tms"}
    with SessionLocal() as s:
        n = s.execute(
            text("SELECT count(*) FROM conflict WHERE key = 'MTR-2041' AND field LIKE 'inbound_%' AND status = 'open'")
        ).scalar_one()
    assert n == 0


def test_shiplane_delta_picks_up_a_new_load_and_its_update():
    assert run_sync("tms", "schedule")["records_read"] == 0
    base = "/shiplane/v3"
    h = token(base, "tms")
    load = sim(
        "POST",
        base + "/loads",
        headers=h,
        json={
            "Direction": "OUTBOUND",
            "LoadType": "REDEPLOYMENT",
            "Status": "BOOKED",
            "ItemId": "MTR-2041",
            "ReturnReference": "RT-1048",
            "LaneId": "WH-MAA-02>LOC-CHN-03",
            "OriginLocationCode": "WH-MAA-02",
            "DestinationLocationCode": "LOC-CHN-03",
            "CarrierSCAC": "NLTL",
            "RateAmt": 3600.0,
            "RateCurrency": "INR",
            "ETA": "2026-10-13T08:36:00+05:30",
        },
    ).json()
    lid = load["LoadId"]
    assert sync("tms")["records_read"] == 1
    assert mapping(prov("route", lid, "eta", "tms")) == ("ETA", "2026-10-13T08:36:00+05:30", "2026-10-13T08:36", "Site time kept")
    d = canonical("route", lid)["data"]
    assert (d["carrier"], d["freight"], d["status"]) == ("Northline 3PL", 43.0, "BOOKED")
    assert canonical("asset", "MTR-2041")["data"]["outbound_load"] == lid
    sim("PATCH", f"{base}/loads/{lid}", headers=h, json={"Status": "IN_TRANSIT"})
    assert sync("tms")["records_read"] == 1
    assert canonical("route", lid)["data"]["status"] == "IN_TRANSIT"
