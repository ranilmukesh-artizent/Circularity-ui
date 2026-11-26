"""Plan 9, P9-10.3: the test bench (source `tn_bench`) adapter against source-sim's synthetic bench mock. Stories TN-06,
TN-10, TN-13.

Starts unregistered like every extra source. The mapping tests run on literal records; the sync test is skipped, with the
reason, when source-sim does not serve the mock (restart it, R14).
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
from di.services.canonical.schema import check_fact, serial_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "tn_bench"
API = SIM + "/test-bench/api"
KEY = {"x-api-key": "tn_bench-demo-key"}
ORG = "Customer A"

UNIT = {
    "serial": "SN-TN-0040", "tests": {"passed": 17, "total": 18}, "firmware": "5.2", "firmwareLatest": "7.1",
    "wipe": {"status": "verified", "attempts": 2, "tool": "WipeTool-X", "toolVersion": "4.2",
             "scope": ["configuration", "credentials", "keys", "logs"], "verifiedAt": "2026-10-03T09:40:00Z",
             "certificateRef": "WC-0040"},
    "boards": [{"boardId": "BRD-0040-1", "partNumber": "PN-BRD-10", "health": "good"}],
    "weightKg": 11.0, "battery": None, "org_unit_id": ORG,
}  # fmt: skip
POWER = {
    "serial": "SN-TN-0103", "tests": {"passed": 18, "total": 18}, "firmware": "3.2", "firmwareLatest": "3.2",
    "wipe": {"status": "none", "attempts": 0, "tool": None, "toolVersion": None, "scope": [], "verifiedAt": None,
             "certificateRef": None},
    "boards": [], "weightKg": 40.0, "battery": {"chemistry": "lithium", "damaged": True}, "org_unit_id": ORG,
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["tn_bench"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SN-TN-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/results", params={"serial": "SN-TN-0001"}, headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the test bench mock: restart it (R14)")


def facts_of(payload: dict) -> dict[tuple[str, str], object]:
    facts = ADAPTERS[SID].map(Record("results", payload["serial"], payload))
    assert [(f.model, f.field, check_fact(f)) for f in facts if check_fact(f)] == []
    assert {f.key for f in facts} == {serial_key(ORG, payload["serial"])}
    return {(f.model, f.field): f.value for f in facts}


def test_adapter_test_bench_maps_facts():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "test_bench"
    by = facts_of(UNIT)
    assert (by["condition", "bench_passed"], by["condition", "bench_total"]) == (17, 18)
    assert (by["condition", "firmware"], by["condition", "firmware_latest"], by["condition", "firmware_major_gap"]) == (
        "5.2", "7.1", 2,
    )  # fmt: skip
    assert (by["condition", "wipe_status"], by["condition", "wipe_attempts"]) == ("verified", 2)
    assert by["condition", "wipe_scope"] == ["configuration", "credentials", "keys", "logs"]
    assert (by["condition", "wipe_certificate_ref"], by["condition", "wipe_verified_at"]) == ("WC-0040", "2026-10-03T09:40:00Z")
    assert by["condition", "boards"][0]["boardId"] == "BRD-0040-1" and by["asset", "weight_kg"] == 11.0
    assert ("condition", "battery_chemistry") not in by  # no battery on a router: no fact


def test_adapter_test_bench_maps_battery_and_no_wipe():
    by = facts_of(POWER)
    assert (by["condition", "battery_chemistry"], by["condition", "battery_damaged"]) == ("lithium", True)
    assert by["condition", "wipe_status"] == "none" and ("condition", "wipe_certificate_ref") not in by
    assert by["condition", "firmware_major_gap"] == 0 and by["asset", "weight_kg"] == 40.0


def test_test_bench_starts_unregistered():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == 0
    assert run_sync(SID, "manual")["status"] == "skipped"


@needs_mock
def test_adapter_test_bench_sync():
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with SessionLocal() as s:
        one = store.get(s, "condition", serial_key(ORG, "SN-TN-0001"))
        old = store.get(s, "condition", serial_key(ORG, "SN-TN-0040"))
        asset = store.get(s, "asset", serial_key(ORG, "SN-TN-0001"))
    assert one is not None and one["data"]["wipe_certificate_ref"] == "WC-0001" and one["data"]["bench_passed"] == 18
    assert old is not None and old["data"]["firmware_major_gap"] == 2
    assert asset is not None and asset["data"]["weight_kg"] == 9.5
