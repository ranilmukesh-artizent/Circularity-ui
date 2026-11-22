"""B9: the operations adapters (Maximo, Manhattan, Depot Repair, SafetyCulture, Optoro, ShipLane) against source-sim.

Needs source-sim running (docker compose) and the worker stopped. Only these six systems are reset, and only their
cursors and queued jobs are cleared, so other connectors' data is left alone. Other syncs may run at the same time
and deadlock on shared canonical rows; such records are counted as failed by the sync runner, so a run that hit one
is repeated in full before values are checked.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
MINE = ("eam", "insp")
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
# ------------------------------------------------------------------ ShipLane TMS
