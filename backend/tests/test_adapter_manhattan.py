"""B5b/B9: the Manhattan Active WM adapter against source-sim's full Manhattan mock.

Needs source-sim running (docker compose) and the worker stopped. Only wms is reset, and only its cursors and queued
jobs are cleared. A run that hit a deadlock with a concurrent sync is repeated in full before values are checked.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
SID = "wms"
H = {"SelectedOrganization": "NORTHFIELD", "SelectedLocation": "WH01"}


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def bearer() -> dict:
    r = sim(
        "POST",
        "/manhattan/oauth/token",
        data={"grant_type": "password", "username": "circularity.integration@northfield", "password": "wms-demo-password"},
        auth=("di-connector", "wms-demo-secret"),
    )
    return {"Authorization": "Bearer " + r.json()["access_token"]} | H


def clear_state() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})


@pytest.fixture(scope="module", autouse=True)
def reset_wms():
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
    assert out["records_read"] >= 128 + 128  # inventory and PIX receipts
    d = data("MTR-2041")
    assert (d["location"], d["availability"], d["qty"], d["case_ref"], d["facility_id"]) == (
        "Warehouse 1",
        "available",
        1,
        "RT-1048",
        "WH01",
    )
    assert d["stock_age_days"] >= 4 and d["stock_received_date"] == "2026-10-03"
    loc = prov("MTR-2041", "location")
    assert loc["authority"] is True and mapping(loc) == ("LocationId", "WH01-RT-09", "Warehouse 1", "Zone collapsed to facility")
    assert mapping(prov("MTR-2041", "qty")) == ("OnHand", "1 UNIT", 1, "UoM normalised")
    mv = prov("MTR-2041", "last_movement_at")
    assert mv["value"] == "2026-10-03T00:00:00Z" and mv["transform"] == "Timestamp to UTC"


def test_unchanged_delta_reads_nothing():
    assert run_sync(SID, "schedule")["records_read"] == 0


def test_delta_picks_up_a_reservation_and_a_shipped_transfer():
    rsv = sim(
        "POST",
        "/manhattan/dcinventory/api/dcinventory/reservation/save",
        headers=bearer(),
        json={"ItemId": "MTR-2041", "Quantity": 1, "OrderId": "SO-48102"},
    ).json()["data"]
    out = sync()
    assert out["records_read"] == 2  # the reservation and the inventory it allocated
    assert mapping(prov("MTR-2041", "reservation_ref")) == (
        "ReservationId",
        rsv["ReservationId"],
        rsv["ReservationId"],
        "Pass-through",
    )
    d = data("MTR-2041")
    assert (d["reserved_for"], d["availability"], d["allocated_qty"]) == ("SO-48102", "allocated", 1)
    order = sim(
        "POST",
        "/manhattan/dcorder/api/dcorder/order/save",
        headers=bearer(),
        json={
            "OrderType": "OUTBOUND",
            "DestinationFacilityId": "ST03",
            "CarrierId": "NLTL",
            "OrderLine": [{"ItemId": "MTR-2041", "OrderedQuantity": 1, "ReservationId": rsv["ReservationId"]}],
        },
    ).json()["data"]
    for _ in range(3):  # pick, pack, ship
        sim("POST", "/_sim/clock/advance", json={"hours": 2.05})
        sim("POST", "/_sim/tick")
    sync()
    d = data("MTR-2041")
    assert (d["transfer_ref"], d["transfer_status"], d["transfer_to"], d["qty"]) == (
        order["OrderId"],
        "Shipped",
        "Chennai Foundry",
        0,
    )
    assert d["reservation_status"] == "CONSUMED" and d["last_movement_type"] == "SHIPMENT"
