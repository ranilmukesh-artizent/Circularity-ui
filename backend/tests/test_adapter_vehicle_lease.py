"""Plan 9, P9-9.2: the vehicle lease system (source `uc_lease`) adapter against source-sim's synthetic lease mock.

`uc_lease` is no demo source: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. Registered (di.connectors.extra) and synced, it fills `asset.*` and `condition.*` facts keyed by
`vin_key(org unit, vin)`. The mapping tests run on literal records; the sync test needs source-sim running with the
lease mock (restart it after the change, R14) and is skipped, with the reason, when it lacks it.

The module starts and ends with the demo reset (tests/starting.py), which removes the sources it registered, and removes
the facts it wrote.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import MODEL_FIELDS, check_fact, vin_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "uc_lease"
API = SIM + "/vehicle-lease/api/v1"
KEY = {"x-api-key": "uc_lease-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


RETURN = {
    "leaseId": "LS-0004", "vin": vin(4), "lesseeRef": "L-0004", "leaseEnd": "2026-10-03", "residualValue": 14000,
    "contractMileage": 36000, "odometerAtReturn": 61240, "odometerLastService": 46240, "odometerStatementRef": "OS-0004",
    "odometerNotActual": False, "modelYear": 2021, "segment": "midsize", "powertrain": "petrol", "returnCenter": "RC-East",
    "sellerFleetSize": 0, "status": "returned", "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
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
        return httpx.get(API + "/lease-returns", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the vehicle lease mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


# ------------------------------------------------------------------ registration
def test_used_car_sources_start_unregistered():
    """Neither used-car system has a source_system row after the demo's starting state."""
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "lease" and "uc_dms" in ADAPTERS
    assert ADAPTERS["uc_dms"].extra and ADAPTERS["uc_dms"].source_type == "dms"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not {"uc_lease", "uc_dms"} & ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_vin_key_is_per_org_unit():
    assert vin_key("Customer A", vin(1)) == f"Customer A:{vin(1)}"
    assert vin_key(None, vin(1)) == f"shared:{vin(1)}" and vin_key("Customer B", vin(1)) != vin_key("Customer A", vin(1))


def test_canonical_models_hold_the_used_car_fields():
    assert {
        "vin", "return_kind", "lease_ref", "book_value", "mileage_at_return", "mileage_lease_record", "model_year",
        "segment", "powertrain", "return_center", "seller_fleet_size", "lot_id", "days_on_lot",
    } <= set(MODEL_FIELDS["asset"])  # fmt: skip
    assert {"odometer_statement_ref", "odometer_not_actual", "payoff_confirmed"} <= set(MODEL_FIELDS["condition"])
    assert {"lot_avg_price", "lot_days_to_sale", "lot_spread", "lot_comparables", "lot_distance_miles", "dealer_bid"} <= set(
        MODEL_FIELDS["market"]
    )
    assert MODEL_FIELDS["market"]["lot_days_to_sale"].type == "object" and MODEL_FIELDS["market"]["dealer_bid"].type == "number"
    assert MODEL_FIELDS["condition"]["odometer_not_actual"].type == "bool"


# ------------------------------------------------------------------ mapping (literal records)
def test_adapter_vehicle_lease_maps_two_mileage_fields():
    facts = ADAPTERS[SID].map(Record("lease_returns", "LS-0004", RETURN))
    assert {f.key for f in facts} == {vin_key(ORG, vin(4))} and {f.model for f in facts} == {"asset", "condition"}
    by = {(f.model, f.field): f.value for f in facts}
    assert by[("asset", "mileage_at_return")] == 61240 and by[("asset", "mileage_lease_record")] == 46240
    assert (by[("asset", "return_kind")], by[("asset", "lease_ref")], by[("asset", "book_value")]) == (
        "lease_end",
        "LS-0004",
        14000,
    )
    assert (by[("asset", "segment")], by[("asset", "powertrain")], by[("asset", "model_year")]) == ("midsize", "petrol", 2021)
    assert (by[("asset", "return_center")], by[("asset", "seller_fleet_size")], by[("asset", "vin")]) == ("RC-East", 0, vin(4))
    assert by[("condition", "odometer_not_actual")] is False and by[("condition", "odometer_statement_ref")] == "OS-0004"
    assert "lessee" not in {f for _, f in by} and "lessee_ref" not in {f for _, f in by}  # a code, kept raw only
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_vehicle_lease_without_an_org_unit_is_shared():
    facts = ADAPTERS[SID].map(Record("lease_returns", "LS-0004", RETURN | {"org_unit_id": None}))
    assert {f.key for f in facts} == {vin_key(None, vin(4))}


# ------------------------------------------------------------------ a sync against the mock
@needs_mock
def test_adapter_vehicle_lease_maps_facts():
    """After register(s, "uc_lease", "Customer A") and a sync, VIN ...004 holds both mileage readings."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 60, out
    asset = canonical("asset", vin_key(ORG, vin(4)))
    assert asset["data"]["mileage_at_return"] == 61240 and asset["data"]["mileage_lease_record"] == 46240
    assert asset["data"]["return_kind"] == "lease_end" and asset["data"]["return_center"] == "RC-East"
    assert {x["source_id"] for x in asset["provenance"]["mileage_at_return"]} == {SID}
    one = canonical("asset", vin_key(ORG, vin(1)))["data"]
    assert (one["book_value"], one["model_year"], one["segment"], one["mileage_at_return"]) == (19500, 2022, "suv", 38000)
    assert canonical("condition", vin_key(ORG, vin(11)))["data"]["odometer_not_actual"] is True
    assert canonical("asset", vin_key(ORG, vin(50)))["data"]["seller_fleet_size"] == 40
    assert canonical("asset", vin_key(ORG, vin(31)))["data"]["return_center"] == "RC-West"
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM canonical WHERE model = 'asset' AND key LIKE :k"), {"k": f"{ORG}:SYNUC%"}
        ).scalar_one()
    assert n == 60
