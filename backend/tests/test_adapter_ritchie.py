"""B5b: the Ritchie Bros. Market Data adapter (mkt) against source-sim's full mock (sim/vendors/ritchie).

Needs source-sim running; keep the worker stopped. Only mkt is reset and only its cursors and jobs are touched, and
the only fault added or removed is mkt's.
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
SID = "mkt"


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def forget_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )


@pytest.fixture(scope="module", autouse=True)
def clean():
    sim("DELETE", "/_sim/faults", params={"system": SID})
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with SessionLocal() as s:
        ensure_sources(s)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})
        conn.execute(
            text("UPDATE source_system SET status = 'live' WHERE id = :s AND status IN ('unavailable', 'auth_expired')"),
            {"s": SID},
        )
    forget_jobs()
    yield
    sim("DELETE", "/_sim/faults", params={"system": SID})
    forget_jobs()


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
                if not res.delta:
                    continue
                cursor = s.execute(
                    text("SELECT cursor FROM sync_cursor WHERE source_id = :s AND resource = :r"), {"s": SID, "r": res.name}
                ).scalar()
                assert cursor, f"no cursor for {res.name}"
                n += sum(1 for _ in res.read(client, cursor))
        finally:
            client.close()
            s.rollback()
    return n


def status() -> str:
    with SessionLocal() as s:
        return s.execute(text("SELECT status FROM source_system WHERE id = :s"), {"s": SID}).scalar_one()


def test_initial_sync_reproduces_the_facts():
    first = run_sync(SID, "initial")
    assert first["status"] == "ok" and first["records_failed"] == 0 and first["records_read"] > 0, first
    m = canonical("market", "MTR-2041")
    d = m["data"]
    assert d["sale_price"] == 5600.0 and d["comparables_count"] == 48 and d["grade"] == "B"
    assert d["comparable_high"] == 9700.0
    assert prov(m, "comparable_high") == ("SOLD_PRC", "8.1 L INR", "Currency + Lakh unit expanded")  # MAPPINGS.mkt
    top = next(c for c in d["comparables"] if c["sold_prc"] == "8.1 L INR")
    assert (top["price"], top["days_listed"], top["grade"]) == (9700.0, 17, "B")
    assert prov(m, "grade")[0::2] == ("CONDITION", "Dealer grade map")
    assert prov(m, "sale_price")[0] == "SOLD_PRC" and prov(m, "time_to_sell")[0] == "DAYS_LISTED"
    assert d["feed_updated_at"] == "2026-10-06T14:00:00+00:00" and d["latest_sale_date"] <= "2026-10-05"
    assert next(p for p in m["provenance"]["sale_price"] if p["source_id"] == SID)["authority"] is True
    drill = canonical("market", "DRL-0812")["data"]
    assert drill["comparables_count"] == 31 and drill["sale_price"] == 241.0  # RT-1049 "31 comparable sales, median $241"
    assert drill["refurb_grade"] == "A" and drill["refurb_comparables_count"] > 0
    assert canonical("market", "class:motor")["data"]["price_index_period"] == "2026-09"
    # an unchanged delta reads nothing
    assert delta_reads() == 0
    again = run_sync(SID, "schedule")
    assert again["status"] == "ok" and again["records_read"] < first["records_read"], again


def test_the_expired_feed_token():
    """The demo's starting state: the feed token expired (source-sim's demo fault, for mkt only)."""
    if not canonical("market", "MTR-2041")["data"].get("sale_price"):
        run_sync(SID, "initial")
    sim("POST", "/_sim/faults", json={"system": SID, "kind": "token_expired", "note": "Feed token expired 6 Oct"})
    try:
        out = run_sync(SID, "manual")
        assert out["status"] == "failed" and "401" in out["error"]
        assert status() == "auth_expired"
        assert canonical("market", "MTR-2041")["data"]["sale_price"] == 5600.0  # the last fresh comparables stay
    finally:
        sim("DELETE", "/_sim/faults", params={"system": SID})
    assert run_sync(SID, "manual")["status"] == "ok"
    assert status() == "live"
