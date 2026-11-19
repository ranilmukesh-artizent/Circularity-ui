"""B5b/B9: the Oracle Lease and Finance Management adapter (lease) against source-sim's EBS OKL mock.

Needs source-sim running and the worker stopped. Only lease is reset, and only its cursors and queued jobs cleared.
"""

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
SID = "lease"
REST = "/oracle-lease/webservices/rest"
USER = ("DI_CONNECTOR", "lease-demo-password")


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
def reset_lease():
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


def prov(rec: dict, field: str) -> tuple:
    p = next(p for p in rec["provenance"][field] if p["source_id"] == SID)
    return p["source_field"], p["source_value"], p["transform"]


def test_initial_sync_reproduces_ownership_and_rate():
    out = sync("initial")
    assert out["records_read"] >= 128 + 1 + 129  # contracts, assets (+ MTR-2077), renewals
    a = canonical("asset", "MTR-2041")
    d = a["data"]
    assert (d["lease_ref"], d["contract_end"], d["owner_tenant"], d["lessee"], d["lease_rate"]) == (
        "LC-004417",
        "2026-12-31",
        "Customer A",
        "Customer A",
        2400.0,
    )
    assert prov(a, "lease_ref") == ("LEASE_CONTRACT_ID", "LC-004417", "Pass-through")
    assert prov(a, "contract_end") == ("CONTRACT_END_DATE", "2026-12-31", "ISO date")
    assert prov(a, "owner_tenant") == ("LESSEE_NAME", "CUSTOMER_A", "Tenant key")
    assert prov(a, "lease_rate") == ("MONTHLY_RENTAL", "2400.00 USD", "Currency + period normalised")
    assert next(p for p in a["provenance"]["owner_tenant"] if p["source_id"] == SID)["authority"] is True
    assert canonical("asset", "MTR-2077")["data"]["owner_tenant"] == "Customer A"  # the demo's CF-31: lease says A
    ls = canonical("demand", "LS-5530")["data"]
    assert ls["asset_ref"] == "MTR-2041" and ls["lease_ref"] == "LC-004417" and ls["need_by"] == "2026-12-31"


def test_delta_reads_nothing_then_an_asset_return():
    assert run_sync(SID, "schedule")["records_read"] == 0
    assets = sim("GET", REST + "/xxoklleasequery/get_lease_assets/", auth=USER, params={"P_ASSET_NUMBER": "MTR-2077"}).json()
    kle = assets["OutputParameters"]["X_ASSETS"]["X_ASSETS_ITEM"][0]["KLE_ID"]
    body = {
        "CREATE_ASSET_RETURN_Input": {
            "RESTHeader": {"RespApplication": "OKL"},
            "InputParameters": {"P_API_VERSION": "1.0", "P_ARTV_REC": {"KLE_ID": kle, "ARS_CODE": "RETURNED"}},
        }
    }
    o = sim("POST", REST + "/oklamassetreturn/create_asset_return/", auth=USER, json=body).json()["OutputParameters"]
    assert o["X_RETURN_STATUS"] == "S"
    assert sync()["records_read"] == 1  # the lease asset
    d = canonical("asset", "MTR-2077")["data"]
    assert d["lease_status"] == "returned" and d["returned_on"] == o["X_ARTV_REC"]["DATE_RETURNED"]
    assert run_sync(SID, "schedule")["records_read"] == 0
