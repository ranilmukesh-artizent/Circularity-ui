"""Plan 9, P9-10.2: the decommission tracker (source `tn_decom`) adapter against source-sim's synthetic tracker mock.

Starts unregistered like every extra source. The mapping tests run on literal records; the sync test is skipped, with
the reason, when source-sim does not serve the mock (restart it, R14).
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
SID = "tn_decom"
API = SIM + "/decommission/api/v2"
KEY = {"x-api-key": "tn_decom-demo-key"}
ORG = "Customer A"

UNIT = {
    "jobId": "RJ-09", "siteId": "SITE-301", "removedAt": "2026-10-05", "programme": "decommission",
    "serial": "SN-TN-0201", "model": "RAD-7700", "org_unit_id": ORG,
}  # fmt: skip
DEMAND = {
    "demandId": "SD-207", "siteId": "SITE-207", "model": "RTR-880", "minFirmwareMajor": 7, "needBy": "2026-11-20",
    "region": "East",
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["tn_inv", "tn_decom"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p OR key LIKE 'SD-%'"), {"p": "%:SN-TN-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/removal-jobs", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the decommission mock: restart it (R14)")


def test_adapter_decommission_tracker_maps_jobs():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "decommission_tracker"
    facts = ADAPTERS[SID].map(Record("removal_jobs", "RJ-09:SN-TN-0201", UNIT))
    assert {f.key for f in facts} == {serial_key(ORG, "SN-TN-0201")} and {f.model for f in facts} == {"asset"}
    by = {f.field: f.value for f in facts}
    assert (by["serial"], by["model"], by["removal_job"], by["removed_at"], by["programme"]) == (
        "SN-TN-0201", "RAD-7700", "RJ-09", "2026-10-05", "decommission",
    )  # fmt: skip
    assert "site" not in by  # the site of the unit is the inventory's fact
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_decommission_tracker_maps_site_demand():
    facts = ADAPTERS[SID].map(Record("site_demand", "SD-207", DEMAND))
    assert [(f.model, f.key, f.field) for f in facts] == [("demand", "SD-207", "site_demand")]
    assert facts[0].value == DEMAND and check_fact(facts[0]) is None


def test_decommission_tracker_starts_unregistered():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == 0
    assert run_sync(SID, "manual")["status"] == "skipped"


@needs_mock
def test_adapter_decommission_tracker_sync():
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with SessionLocal() as s:
        eight = [store.get(s, "asset", serial_key(ORG, f"SN-TN-{n:04d}")) for n in range(201, 209)]
        demand = store.get(s, "demand", "SD-112")
    assert all(a is not None and a["data"]["removal_job"] == "RJ-09" for a in eight)
    assert demand is not None and demand["data"]["site_demand"]["model"] == "RRU-4410"
