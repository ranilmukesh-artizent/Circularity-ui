"""Plan 9, P9-9.6: the vehicle auction platform (source `uc_auction`) adapter against source-sim's synthetic mock.

`uc_auction` is no demo source: it starts unregistered. Registered and synced it fills, per car keyed
`vin_key(org unit, vin)`, the `market` facts of the auction (`auction_next_sale_days` of the car's return centre's site,
`auction_sell_fee`, `auction_transport`, `salvage_bid`, `salvage_buyer`) and, per buyer keyed by the buyer id,
`vendor.title_db_reporting`. The site comes from the car's `return_center` already in the store (the lease system's
fact), so sync the lease system first. The mapping tests run on literal records; the sync test needs source-sim running
with the mocks (restart it after the change, R14) and is skipped, with the reason, when it lacks them.
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
SID = "uc_auction"
ORG = "Customer A"
KEYS = {
    "uc_lease": {"x-api-key": "uc_lease-demo-key"},
    "uc_auction": {"x-api-key": "uc_auction-demo-key"},
    "uc_price": {"x-api-key": "uc_price-demo-key"},
}
PATHS = {
    "uc_lease": "/vehicle-lease/api/v1/lease-returns",
    "uc_auction": "/vehicle-auction/v1/fees",
    "uc_price": "/vehicle-pricing/v3/values?vin=SYNUC000000000001",
}
BUYERS = ("SB-1", "SB-2", "SB-3", "RB-1")


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


CAR = {
    "vin": vin(1), "org_unit_id": ORG, "site": "AUC-E", "nextSaleDays": 6, "sellFee": 325, "transport": 120,
    "bestBid": {"amount": 2100, "buyerId": "SB-1"},
}  # fmt: skip
BUYER = {"buyerId": "SB-2", "name": "Salvage buyer 2 (synthetic)", "salvage": True, "titleDbReporting": False}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["uc_lease", "uc_auction", "uc_price"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})
        conn.execute(text("DELETE FROM canonical WHERE model = 'vendor' AND key = ANY(:k)"), {"k": list(BUYERS)})


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
def test_adapter_vehicle_auction_maps_a_car():
    facts = ADAPTERS[SID].map(Record("vin_auction", vin(1), CAR))
    assert {f.model for f in facts} == {"market"} and {f.key for f in facts} == {vin_key(ORG, vin(1))}
    by = {f.field: f.value for f in facts}
    assert by == {
        "auction_next_sale_days": 6, "auction_sell_fee": 325, "auction_transport": 120, "salvage_bid": 2100,
        "salvage_buyer": "SB-1",
    }  # fmt: skip
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_vehicle_auction_without_a_site_or_bid_writes_no_empty_fact():
    facts = ADAPTERS[SID].map(Record("vin_auction", vin(1), CAR | {"site": None, "nextSaleDays": None, "bestBid": None}))
    assert {f.field for f in facts} == {"auction_sell_fee", "auction_transport"}


def test_adapter_vehicle_auction_maps_a_buyer_to_a_vendor_fact_keyed_by_buyer_id():
    facts = ADAPTERS[SID].map(Record("buyers", "SB-2", BUYER))
    assert [(f.model, f.key, f.field, f.value) for f in facts] == [("vendor", "SB-2", "title_db_reporting", False)]
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_vehicle_auction_sales_and_results_make_no_fact():
    assert ADAPTERS[SID].map(Record("results", "R", {"segment": "suv", "band": "0-40k", "avgClearedPrice": 20000})) == []


# ------------------------------------------------------------------ a sync against the mock
@needs_mock
def test_adapters_auction_pricing_map_facts():
    """Lease system first (VIN ...001's return centre), then the auction platform and the pricing guide."""
    for sid in ("uc_lease", SID, "uc_price"):
        with SessionLocal() as s:
            assert extra.register(s, sid, ORG) == sid
            s.commit()
        assert call("source.reconnect", {"source_id": sid}, "developer")["ok"]
        out = run_sync(sid, "manual", full=True)
        assert out["status"] == "ok" and out["records_failed"] == 0, out
    market = canonical("market", vin_key(ORG, vin(1)))
    data = market["data"]
    assert (data["retail_guide_price"], data["wholesale_guide_price"]) == (24000, 21500)
    assert (data["auction_sell_fee"], data["auction_transport"], data["salvage_bid"]) == (325, 120, 2100)
    assert data["auction_next_sale_days"] == 6 and data["salvage_buyer"] in {"SB-1", "SB-2", "SB-3"}
    assert market["provenance"]["salvage_bid"][0]["source_id"] == SID
    assert market["provenance"]["retail_guide_price"][0]["source_id"] == "uc_price"
    assert canonical("market", vin_key(ORG, vin(8)))["data"]["salvage_bid"] == 3900
    assert canonical("market", vin_key(ORG, vin(8)))["data"]["retail_guide_price"] == 21000
    assert canonical("vendor", "SB-2")["data"]["title_db_reporting"] is False
    assert canonical("vendor", "SB-1")["data"]["title_db_reporting"] is True
