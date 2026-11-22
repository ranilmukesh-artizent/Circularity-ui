"""B5b: the Machinio adapter (dlr) against source-sim's full mock (sim/vendors/machinio).

Needs source-sim running; keep the worker stopped. Only dlr is reset and only its cursors and jobs are touched.
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
SID = "dlr"
KEY = {"X-Api-Key": "mch_demo_circularity_4f7b2e91"}


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def forget_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )


def reset() -> None:
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})
    forget_jobs()


@pytest.fixture(scope="module", autouse=True)
def clean():
    with SessionLocal() as s:
        ensure_sources(s)
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_system SET status = 'live' WHERE id = :s AND status = 'unavailable'"), {"s": SID})
    reset()
    yield
    reset()


def canonical(key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, "market", key)
    assert rec is not None, f"market.{key} missing"
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
                assert cursor, f"no cursor for {res.name}"
                n += sum(1 for _ in res.read(client, cursor))
        finally:
            client.close()
            s.rollback()
    return n


def test_initial_sync_reproduces_the_facts():
    first = run_sync(SID, "initial")
    assert first["status"] == "ok" and first["records_failed"] == 0 and first["records_read"] > 0, first
    m = canonical("MTR-2041")
    d = m["data"]
    assert (d["dealer_offer"], d["dealer_offer_ref"], d["dealer_fees"], d["dealer_time_to_sell"]) == (
        5600.0,
        "MO-91048",
        800.0,
        12,
    )
    assert prov(m, "dealer_offer") == ("offer_amount", 5600.0, "Currency")  # MAPPINGS.dlr
    assert d["dealer_offer_status"] == "open" and d["dealer_offer_kind"] == "indicative"
    assert d["dealer_fees_detail"]["freight_lanes"] == ["WH-PNQ-01>EXT-BOM"]
    assert d["open_listings"] == 5 and d["listing_grade"] == "B" and d["listing_status"] == "active"
    assert isinstance(d["listing_time_to_sell"], int) and prov(m, "listing_time_to_sell")[0] == "listing_age_days"
    drill = canonical("DRL-0812")["data"]
    assert drill["listing_count_by_grade"]["A"] == 14  # RT-1049: "Grade A listings: 14 open"
    assert canonical("CTL-0301")["data"]["dealer_offer_kind"] == "firm"  # RT-1033 "Offer from dealer" $460
    # an unchanged delta reads nothing
    assert delta_reads() == 0
    again = run_sync(SID, "schedule")
    assert again["status"] == "ok" and again["records_read"] == 0, again


def test_delta_picks_up_an_accepted_offer():
    if not canonical("MTR-2041")["data"].get("dealer_offer"):
        run_sync(SID, "initial")
    sim("POST", "/machinio/v1/offers/MO-91048/accept", headers=KEY)
    out = run_sync(SID, "schedule")
    assert out["status"] == "ok" and out["records_read"] == 2, out  # the offer and its listing
    d = canonical("MTR-2041")["data"]
    assert d["dealer_offer_status"] == "accepted" and d["listing_status"] == "pending_sale"
