"""Plan 9, P9-10.5: the recycler portal (source `tn_recycler`) adapter against source-sim's synthetic mock.

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
from di.services.canonical.schema import MODEL_FIELDS, check_fact, serial_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "tn_recycler"
API = SIM + "/recycler-portal/api"
KEY = {"x-api-key": "tn_recycler-demo-key"}
ORG = "Customer A"

VENDOR = {
    "vendorId": "RV-1", "label": "Recycler one", "dgLane": True, "regions": ["North", "South"],
    "certificate": {"scheme": "R2v3", "ref": "R2V3-0001", "expires": "2027-06-30"},
}  # fmt: skip
CERT = {
    "certificateId": "DC-0001", "serial": "SN-TN-0010", "pickupId": "PU-0001", "vendorId": "RV-1",
    "issuedAt": "2026-10-09T09:01:00+00:00", "org_unit_id": ORG,
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(
            text("DELETE FROM canonical WHERE (model = 'vendor' AND key LIKE :v) OR key LIKE :s"),
            {"v": "RV-%", "s": "%:SN-TN-%"},
        )


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/vendors", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the recycler mock: restart it (R14)")


def test_recycler_fields_exist():
    assert MODEL_FIELDS["vendor"]["recycler_certificate"].type == "object"
    assert MODEL_FIELDS["vendor"]["dg_lane"].type == "bool"
    assert MODEL_FIELDS["condition"]["disposal_record_ref"].type == "ref"


def test_adapter_recycler_portal_maps_a_vendor():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "recycler_portal"
    facts = ADAPTERS[SID].map(Record("vendors", "RV-1", VENDOR))
    by = {f.field: f.value for f in facts}
    assert {f.model for f in facts} == {"vendor"} and {f.key for f in facts} == {"RV-1"}
    assert by["recycler_certificate"] == VENDOR["certificate"] and by["dg_lane"] is True and by["name"] == "Recycler one"
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_recycler_portal_keeps_a_false_dg_lane():
    rec = Record("vendors", "RV-2", VENDOR | {"vendorId": "RV-2", "dgLane": False})
    assert {f.field: f.value for f in ADAPTERS[SID].map(rec)}["dg_lane"] is False


def test_adapter_recycler_portal_maps_a_disposal_certificate():
    facts = ADAPTERS[SID].map(Record("certificates", "DC-0001", CERT))
    assert [(f.model, f.key, f.field, f.value) for f in facts] == [
        ("condition", serial_key(ORG, "SN-TN-0010"), "disposal_record_ref", "DC-0001")
    ]
    assert check_fact(facts[0]) is None
    shared = ADAPTERS[SID].map(Record("certificates", "DC-0001", CERT | {"org_unit_id": None}))
    assert shared[0].key == serial_key(None, "SN-TN-0010")


def test_recycler_starts_unregistered():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == 0
    assert run_sync(SID, "manual")["status"] == "skipped"


@needs_mock
def test_adapter_recycler_portal_sync():
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with SessionLocal() as s:
        one, two = store.get(s, "vendor", "RV-1"), store.get(s, "vendor", "RV-2")
    assert one is not None and one["data"]["dg_lane"] is True
    assert one["data"]["recycler_certificate"]["expires"] == "2027-06-30"
    assert two is not None and two["data"]["recycler_certificate"]["expires"] == "2026-10-31"
