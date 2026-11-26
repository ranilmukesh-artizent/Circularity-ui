"""Plan 9, P9-10.2: the network inventory (source `tn_inv`) adapter against source-sim's synthetic inventory mock.

`tn_inv` is no demo source: it starts unregistered (no source_system row), so every demo screen and count is unchanged.
The mapping tests run on literal records (they need no source-sim); the sync test needs source-sim running with the
mock (restart it after the change, R14) and is skipped, with the reason, when it lacks it.
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
from di.services.canonical.schema import MODEL_FIELDS, check_fact, serial_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "tn_inv"
API = SIM + "/network-inventory/api"
KEY = {"x-api-key": "tn_inv-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"

RRU = {
    "serial": "SN-TN-0002", "model": "RRU-4410", "partNumber": "PN-4410-02", "hwRevision": "B2", "firmware": "3.1.2",
    "manufacturer": "MFR-B", "site": "SITE-101", "siteKind": "edge", "region": "North", "status": "removed",
    "exportClassInferred": "5A992", "exportClassConfirmed": None, "org_unit_id": ORG,
}  # fmt: skip
RAD = RRU | {"serial": "SN-TN-0006", "model": "RAD-7700", "exportClassInferred": None, "exportClassConfirmed": "5A002"}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["tn_inv", "tn_decom"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SN-TN-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/elements", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the network inventory mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_network_inventory_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "network_inventory"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not {"tn_inv", "tn_decom"} & ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_serial_key_is_per_org_unit():
    assert serial_key("Customer A", "SN-TN-0001") == "Customer A:SN-TN-0001"
    assert serial_key(None, "SN-TN-0001") == "shared:SN-TN-0001"
    assert serial_key("Customer B", "SN-TN-0001") != serial_key("Customer A", "SN-TN-0001")


def test_canonical_models_hold_the_network_fields():
    assert {
        "serial", "model", "part_number", "hw_revision", "firmware", "manufacturer", "site", "site_kind", "region",
        "export_class", "export_class_inferred", "inventory_status", "removal_job", "removed_at", "programme",
    } <= set(MODEL_FIELDS["asset"])  # fmt: skip
    assert MODEL_FIELDS["demand"]["site_demand"].type == "object"


def test_adapter_network_inventory_keeps_inferred_class_apart():
    facts = ADAPTERS[SID].map(Record("elements", "SN-TN-0002", RRU))
    assert {f.key for f in facts} == {serial_key(ORG, "SN-TN-0002")} and {f.model for f in facts} == {"asset"}
    by = {f.field: f.value for f in facts}
    assert "export_class" not in by or not by["export_class"]
    assert by["export_class_inferred"] == "5A992"
    assert (by["serial"], by["model"], by["part_number"], by["hw_revision"], by["firmware"]) == (
        "SN-TN-0002", "RRU-4410", "PN-4410-02", "B2", "3.1.2",
    )  # fmt: skip
    assert (by["manufacturer"], by["site"], by["site_kind"], by["region"], by["inventory_status"]) == (
        "MFR-B", "SITE-101", "edge", "North", "removed",
    )  # fmt: skip
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_network_inventory_confirmed_class_fills_export_class():
    by = {f.field: f.value for f in ADAPTERS[SID].map(Record("elements", "SN-TN-0006", RAD))}
    assert by["export_class"] == "5A002" and "export_class_inferred" not in by


def test_adapter_network_inventory_without_an_org_unit_is_shared():
    facts = ADAPTERS[SID].map(Record("elements", "SN-TN-0002", RRU | {"org_unit_id": None}))
    assert {f.key for f in facts} == {serial_key(None, "SN-TN-0002")}


@needs_mock
def test_adapter_network_inventory_sync():
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] >= 120, out
    rad = canonical("asset", serial_key(ORG, "SN-TN-0006"))["data"]
    assert rad["model"] == "RAD-7700" and rad["export_class"] == "5A002"
    rru = next(
        canonical("asset", serial_key(ORG, f"SN-TN-{n:04d}"))["data"]
        for n in range(1, 121)
        if canonical("asset", serial_key(ORG, f"SN-TN-{n:04d}"))["data"]["model"] == "RRU-4410"
    )
    assert "export_class" not in rru and rru["export_class_inferred"] == "5A992"
