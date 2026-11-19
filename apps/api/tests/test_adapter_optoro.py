"""B5b/B9: the Optoro adapter against source-sim's full Optoro mock.

Needs source-sim running (docker compose) and the worker stopped. Only rl is reset, and only its cursors and queued
jobs are cleared. A run that hit a deadlock with a concurrent sync is repeated in full before values are checked.
"""

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
SID = "rl"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def bearer() -> dict:
    r = sim(
        "POST",
        "/optoro/auth/oauth/token",
        json={"grant_type": "client_credentials", "client_id": "di-connector", "client_secret": "rl-demo-secret"},
    )
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def clear_state() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})


@pytest.fixture(scope="module", autouse=True)
def reset_rl():
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


def prov(key: str, field: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, "asset", key)
    rows = [p for p in rec["provenance"].get(field, []) if p["source_id"] == SID]
    assert rows, (key, field)
    return rows[0]


def data(key: str) -> dict:
    with SessionLocal() as s:
        return store.get(s, "asset", key)["data"]


def mapping(p: dict) -> tuple:
    return p["source_field"], p["source_value"], p["value"], p["transform"]


def test_initial_sync_reproduces_the_facts_and_mappings():
    out = sync("initial")
    assert out["records_read"] >= 128 * 3  # RMAs, receipts, ASNs (+ dispositions)
    d = data("MTR-2041")
    assert (d["return_ref"], d["received_at"], d["disposition"], d["case_ref"], d["replacement_order"]) == (
        "RMA-56509",
        "2026-10-03T19:28:00Z",
        "restock",
        "RT-1048",
        "SO-48102",
    )
    assert (d["inbound_load"], d["receiving_facility"], d["disposition_final"]) == ("LD-21048", "WH01", False)
    rcv = prov("MTR-2041", "received_at")
    assert rcv["authority"] is True and mapping(rcv) == (
        "received_at",
        "2026-10-03T15:28:00-04:00",
        "2026-10-03T19:28:00Z",
        "Timestamp to UTC",
    )
    assert mapping(prov("MTR-2041", "return_ref")) == ("rma_identifier", "RMA-56509", "RMA-56509", "Pass-through")
    fr = prov("MTR-2041", "inbound_freight")
    assert fr["transform"] == "Pass-through (USD)" and "USD" in fr["source_value"] and "INR" in fr["source_value"]
    with SessionLocal() as s:
        refurb = s.execute(
            text(
                "SELECT value, transform FROM provenance WHERE source_id = 'rl' AND field = 'disposition' "
                "AND source_value = CAST('\"refurbish\"' AS jsonb) LIMIT 1"
            )
        ).one()
    assert tuple(refurb) == ("refurbish", "Disposition map")


def test_unchanged_delta_reads_nothing():
    assert run_sync(SID, "schedule")["records_read"] == 0


def test_delta_picks_up_a_new_disposition_and_its_final_disposition():
    lp = "LPNF0001048"
    sim(
        "POST",
        "/optoro/returns/dispositions",
        headers=bearer(),
        json={"optiturn_lp": lp, "to_disposition": "refurbish", "to_condition": "C"},
    )
    assert sync()["records_read"] == 1
    p = prov("MTR-2041", "disposition")
    assert mapping(p) == ("to_disposition", "refurbish", "refurbish", "Disposition map")
    assert data("MTR-2041")["disposition_status"] == "PROPOSED"
    sim("POST", "/_sim/clock/advance", json={"days": 3.01})
    sim("POST", "/_sim/tick")
    assert sync()["records_read"] == 1
    d = data("MTR-2041")
    assert (d["disposition"], d["disposition_status"], d["disposition_final"]) == ("refurbish", "FINAL", True)


def test_delta_picks_up_a_return_authorisation():
    rma = sim(
        "POST",
        "/optoro/returns/rmas",
        headers=bearer(),
        json={
            "items": [
                {
                    "sku": "MTR-2041",
                    "order_identifier": "LC-4100",
                    "secondary_identifier": "RT-1048",
                    "return_reason": "early return",
                }
            ],
            "return_method": "home-pickup",
        },
    ).json()
    assert sync()["records_read"] == 1
    p = prov("MTR-2041", "return_authorization_ref")
    assert p["value"] == rma["rma_identifier"] and p["source_field"] == "rma_identifier"
