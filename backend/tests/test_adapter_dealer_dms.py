"""Plan 9, P9-9.2: the dealer management system (source `uc_dms`) adapter against source-sim's synthetic DMS mock.

`uc_dms` is no demo source: it starts unregistered. Registered and synced it fills, keyed `vin_key(org unit, vin)`:
trade-ins (`asset.*`, `condition.payoff_confirmed`), cars on the lots (`asset.lot_id`, `asset.days_on_lot`) and, per
car, the market facts of each lot (`market.lot_*`, an object keyed by lot id) with the best partner bid. A car's segment
and mileage band come from its trade-in or, for a lease return, from the lease system's facts already in the store, so
sync the lease system first. The mapping tests run on literal records; the sync test needs source-sim running with both
mocks (restart it after the change, R14) and is skipped, with the reason, when it lacks them.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import check_fact, vin_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "uc_dms"
ORG = "Customer A"
KEYS = {"uc_lease": {"x-api-key": "uc_lease-demo-key"}, "uc_dms": {"x-api-key": "uc_dms-demo-key"}}
PATHS = {"uc_lease": "/vehicle-lease/api/v1/lease-returns", "uc_dms": "/dealer-dms/api/v1/lots"}


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


TRADE = {
    "tradeId": "TI-0062", "vin": vin(62), "tradeAllowance": 9000, "payoffAmount": 5400, "payoffConfirmed": False,
    "mileage": 71000, "modelYear": 2019, "segment": "truck", "powertrain": "diesel", "receivedAt": "2026-10-05T10:00:00+00:00",
    "store": "Store 3", "org_unit_id": ORG,
}  # fmt: skip
STOCK = {
    "stockId": "ST-001", "vin": vin(41), "lotId": "LOT-N", "segment": "ev_crossover", "powertrain": "ev", "daysOnLot": 52,
    "askingPrice": 28500, "org_unit_id": ORG,
}  # fmt: skip
CELL = {"avgPrice": 23600, "avgDaysToSale": 34, "count": 12, "spread": 1500}
MARKET = {
    "vin": vin(1), "segment": "suv", "mileage": 38000, "band": "0-40k", "org_unit_id": ORG,
    "lots": {
        "LOT-N": {"distanceMiles": 12, **CELL},
        "LOT-C": {"distanceMiles": 40, "avgPrice": 24000, "avgDaysToSale": 21, "count": 22, "spread": 1300},
    },
    "bids": [{"bidId": "PB-0001", "vin": vin(1), "partner": "Partner A", "amount": 20900}],
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["uc_lease", "uc_dms"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return all(httpx.get(SIM + PATHS[s], headers=KEYS[s], timeout=10).status_code == 200 for s in PATHS)
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the used-car mocks: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


# ------------------------------------------------------------------ mapping (literal records)
def test_adapter_dealer_dms_maps_a_trade_in():
    facts = ADAPTERS[SID].map(Record("trade_ins", "TI-0062", TRADE))
    assert {f.key for f in facts} == {vin_key(ORG, vin(62))}
    by = {(f.model, f.field): f.value for f in facts}
    assert (by[("asset", "return_kind")], by[("asset", "book_value")], by[("asset", "mileage_at_return")]) == (
        "trade_in", 9000, 71000,
    )  # fmt: skip
    assert by[("condition", "payoff_confirmed")] is False and by[("asset", "segment")] == "truck"
    assert "mileage_lease_record" not in {f for _, f in by}  # a trade-in has no lease record
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_dealer_dms_maps_a_car_on_a_lot():
    facts = ADAPTERS[SID].map(Record("stock", "ST-001", STOCK))
    assert {(f.model, f.field, f.value) for f in facts} == {("asset", "lot_id", "LOT-N"), ("asset", "days_on_lot", 52)}
    assert {f.key for f in facts} == {vin_key(ORG, vin(41))}


def test_adapter_dealer_dms_maps_lot_facts_from_a_record():
    facts = ADAPTERS[SID].map(Record("vin_market", vin(1), MARKET))
    by = {f.field: f.value for f in facts}
    assert {f.model for f in facts} == {"market"} and {f.key for f in facts} == {vin_key(ORG, vin(1))}
    assert by["lot_days_to_sale"] == {"LOT-N": 34, "LOT-C": 21} and by["lot_avg_price"] == {"LOT-N": 23600, "LOT-C": 24000}
    assert by["lot_spread"] == {"LOT-N": 1500, "LOT-C": 1300} and by["lot_comparables"] == {"LOT-N": 12, "LOT-C": 22}
    assert by["lot_distance_miles"] == {"LOT-N": 12, "LOT-C": 40} and by["dealer_bid"] == 20900
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_dealer_dms_without_bids_or_lots_writes_no_empty_fact():
    facts = ADAPTERS[SID].map(Record("vin_market", vin(1), MARKET | {"bids": [], "lots": {}}))
    assert facts == []


def test_adapter_dealer_dms_lots_make_no_fact():
    assert ADAPTERS[SID].map(Record("lots", "LOT-N", {"lotId": "LOT-N", "name": "North lot", "distanceMiles": 12})) == []


# ------------------------------------------------------------------ a sync against the mock
@needs_mock
def test_adapter_dealer_dms_maps_lot_facts():
    """Lease system first (it holds VIN ...001's segment and mileage), then the DMS: ...001's days to sale per lot."""
    for sid in ("uc_lease", SID):
        with SessionLocal() as s:
            assert extra.register(s, sid, ORG) == sid
            s.commit()
        assert call("source.reconnect", {"source_id": sid}, "developer")["ok"]
        out = run_sync(sid, "manual", full=True)
        assert out["status"] == "ok" and out["records_failed"] == 0, out
    market = canonical("market", vin_key(ORG, vin(1)))["data"]
    assert market["lot_days_to_sale"] == {"LOT-N": 34, "LOT-C": 21, "LOT-S": 15}
    assert market["lot_avg_price"] == {"LOT-N": 23600, "LOT-C": 24000, "LOT-S": 24300}
    assert market["lot_comparables"] == {"LOT-N": 12, "LOT-C": 22, "LOT-S": 18}
    assert market["lot_spread"] == {"LOT-N": 1500, "LOT-C": 1300, "LOT-S": 1200}
    assert market["lot_distance_miles"] == {"LOT-N": 12, "LOT-C": 40, "LOT-S": 95} and market["dealer_bid"] == 20900
    ev = canonical("market", vin_key(ORG, vin(41)))["data"]
    assert ev["lot_days_to_sale"] == {"LOT-N": 58, "LOT-C": 33, "LOT-S": 29}
    trade = canonical("asset", vin_key(ORG, vin(62)))["data"]
    assert (
        trade["return_kind"] == "trade_in" and canonical("condition", vin_key(ORG, vin(62)))["data"]["payoff_confirmed"] is False
    )
    assert canonical("condition", vin_key(ORG, vin(63)))["data"]["payoff_confirmed"] is True
    stocked = canonical("asset", vin_key(ORG, vin(41)))["data"]
    assert (stocked["lot_id"], stocked["days_on_lot"]) == ("LOT-N", 52) and stocked["return_kind"] == "lease_end"
    assert canonical("asset", vin_key(ORG, vin(41)))["provenance"]["lot_id"][0]["source_id"] == SID
