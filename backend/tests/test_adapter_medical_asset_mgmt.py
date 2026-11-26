"""Plan 9, P9-11.2: the asset management system (source `mr_assets`) adapter against source-sim's synthetic mock.

`mr_assets` is no demo source: it starts unregistered, so every demo screen and count is unchanged. Registered
(di.connectors.extra) and synced, it fills `asset.*` and `market.residual_sale_value` facts keyed by
`tag_key(org unit, tag)`. The mapping tests run on literal records; the sync test needs source-sim running with the mock
(restart it after the change, R14) and is skipped, with the reason, when it lacks it.

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
from di.services.canonical.schema import MODEL_FIELDS, check_fact, tag_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "mr_assets"
API = SIM + "/asset-management/api"
KEY = {"x-api-key": "mr_assets-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"
TAG = "SYN-MR-IP-0001"

DEVICE = {
    "tag": TAG, "serial": "SN-IP-00001", "model": "Synthetic Volumetric Pump V2", "deviceClass": "infusion_pump",
    "manufacturerCode": "MFR-A", "inServiceDate": "2023-10-07", "bookValue": 1150, "residualSaleValue": 1100,
    "hasPatientData": False, "org_unit_id": ORG,
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["mr_assets", "mr_rental"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/devices", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the asset management mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_tag_key_is_per_org_unit():
    assert tag_key("Customer A", TAG) == f"Customer A:{TAG}"
    assert tag_key(None, TAG) == f"shared:{TAG}" and tag_key("Customer B", TAG) != tag_key("Customer A", TAG)


def test_medical_sources_start_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "assets" and ADAPTERS["mr_rental"].extra
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not {SID, "mr_rental"} & ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_models_hold_the_medical_rental_fields():
    assert {
        "tag", "device_class", "model", "serial", "in_service_date", "age_years", "book_value", "has_patient_data", "depot",
        "checked_in_at", "hospital", "ward_type", "turnaround",
    } <= set(MODEL_FIELDS["asset"])  # fmt: skip
    assert "residual_sale_value" in MODEL_FIELDS["market"] and MODEL_FIELDS["market"]["residual_sale_value"].type == "number"
    assert {"rental_requests", "region_forecast"} <= set(MODEL_FIELDS["demand"])
    assert MODEL_FIELDS["asset"]["has_patient_data"].type == "bool" and MODEL_FIELDS["asset"]["turnaround"].type == "object"


def test_adapter_medical_asset_mgmt_maps_facts_literal():
    facts = ADAPTERS[SID].map(Record("devices", TAG, DEVICE))
    assert {f.key for f in facts} == {tag_key(ORG, TAG)} and {f.model for f in facts} == {"asset", "market"}
    by = {(f.model, f.field): f.value for f in facts}
    assert by[("asset", "tag")] == TAG and by[("asset", "device_class")] == "infusion_pump"
    assert (by[("asset", "model")], by[("asset", "serial")]) == ("Synthetic Volumetric Pump V2", "SN-IP-00001")
    assert by[("asset", "in_service_date")] == "2023-10-07" and by[("asset", "has_patient_data")] is False
    assert by[("asset", "book_value")] == 1150 and by[("market", "residual_sale_value")] == 1100
    assert by[("asset", "age_years")] == 3.0  # the pinned clock is 7 Oct 2026
    assert "manufacturer_code" not in {f for _, f in by}
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_medical_asset_mgmt_without_an_org_unit_is_shared():
    facts = ADAPTERS[SID].map(Record("devices", TAG, DEVICE | {"org_unit_id": None}))
    assert {f.key for f in facts} == {tag_key(None, TAG)}


@needs_mock
def test_adapter_medical_asset_mgmt_maps_facts():
    """After register(s, "mr_assets", "Customer A") and a sync, the 80 devices hold their facts."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 80, out
    asset = canonical("asset", tag_key(ORG, TAG))["data"]
    assert (asset["device_class"], asset["book_value"], asset["age_years"], asset["has_patient_data"]) == (
        "infusion_pump",
        1150,
        3.0,
        False,
    )
    assert canonical("market", tag_key(ORG, TAG))["data"]["residual_sale_value"] == 1100
    assert canonical("asset", tag_key(ORG, "SYN-MR-PM-0001"))["data"]["has_patient_data"] is True
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM canonical WHERE model = 'asset' AND key LIKE :k"), {"k": f"{ORG}:SYN-MR-%"}
        ).scalar_one()
    assert n == 80
