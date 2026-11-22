"""B5b: the Persefoni (esg) adapter against source-sim's full Persefoni mock.

Needs source-sim running and the worker stopped. Only esg is reset, and only its cursors and queued jobs are touched.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
SID = "esg"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def clear() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :s"), {"s": SID})


@pytest.fixture(scope="module", autouse=True)
def clean():
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    clear()
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(
            text("UPDATE source_system SET status = 'live' WHERE id = :s AND status IN ('unavailable', 'auth_expired')"),
            {"s": SID},
        )
        s.commit()
    yield
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    clear()
    run_sync(SID, "manual", full=True)  # put the seeded footprints back into the shared canonical store
    clear()


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(rec: dict, field: str) -> tuple:
    p = next(x for x in rec["provenance"][field] if x["source_id"] == SID)
    return p["source_field"], p["source_value"], p["transform"]


def delta_reads() -> int:
    a = ADAPTERS[SID]
    n = 0
    with SessionLocal() as s:
        client = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            for res in a.resources():
                cursor = s.execute(
                    text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = :r"), {"s": SID, "r": res.name}
                ).scalar()
                assert cursor, res.name
                n += sum(1 for _ in res.read(client, cursor))
        finally:
            client.close()
            s.rollback()
    return n


def token() -> dict:
    form = {
        "grant_type": "client_credentials",
        "client_id": "circularity-di-connector",
        "client_secret": "circularity-demo-persefoni-secret",
    }
    return {"Authorization": "Bearer " + sim("POST", "/persefoni/oauth/token", data=form).json()["access_token"]}


def test_initial_sync_reproduces_the_demo_mappings():
    out = run_sync(SID, "initial")
    if out["status"] == "partial" and "Deadlock" in (out["error"] or ""):
        out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] > 0, out
    f = canonical("sustainability", "class:motor")
    assert f["data"]["emission_factor"] == 420.0 and f["data"]["boundary"] == "cradle-to-gate"
    assert f["data"]["factor_version"] == "2026.2"
    assert prov(f, "emission_factor") == ("factor_kgco2e", 420.0, "Unit kept")
    assert prov(f, "boundary") == ("scope", "Cradle-to-gate", "Boundary map")
    assert next(p for p in f["provenance"]["emission_factor"] if p["source_id"] == SID)["authority"] is True
    assert canonical("sustainability", "route:redeploy")["data"]["avoided_share"] == 0.7
    s = canonical("sustainability", "MTR-2041")
    d = s["data"]
    assert d["footprint"]["redeploy"] == 294.0 and d["case_ref"] == "RT-1048" and d["footprint_method"] == "estimated"
    assert prov(s, "footprint")[2].startswith("mtCO2e → kgCO2e")
    assert canonical("sustainability", "PMP-1007")["data"]["decision_footprints"][0]["measured_kg"] == 147.0

    # unchanged: a delta reads nothing, and so does the next scheduled sync (every resource is a delta)
    assert delta_reads() == 0
    again = run_sync(SID, "schedule")
    assert again["status"] == "ok" and again["records_read"] == 0, again


def test_new_activity_is_calculated_and_picked_up():
    body = {
        "activity_type": "route_estimate",
        "asset_id": "TEST-ESG-1",
        "external_reference": "RT-TEST",
        "quantity": 2,
        "quantity_unit": "unit",
        "emission_factor_id": "ef_embodied_motor",
        "route": "material",
    }
    r = sim("POST", "/persefoni/v1/activities", headers=token(), json=body)
    assert r.json()["included"][0]["avoided_co2e"] == 0.0672  # 2 units x 420 kgCO2e/unit x 0.08 = 67.2 kg
    assert delta_reads() == 1  # the footprints of TEST-ESG-1
    out = run_sync(SID, "schedule")
    assert out["status"] == "ok" and out["records_read"] == 1, out
    d = canonical("sustainability", "TEST-ESG-1")["data"]
    assert d["footprint"] == {"material": 67.2} and d["case_ref"] == "RT-TEST"
    assert delta_reads() == 0
