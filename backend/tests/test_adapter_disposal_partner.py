"""Plan 9, P9-11.5: the disposal partner (source `mr_disposal`) adapter against source-sim's synthetic mock.

`mr_disposal` is no demo source: it starts unregistered, so every demo screen and count is unchanged. Registered
(di.connectors.extra) and synced, it fills `condition.sanitisation_record_ref` and `condition.disposal_certificate_ref`
keyed by `tag_key(org unit, tag)`. The mapping tests run on literal records. The sync test makes a collection and a
sanitisation, moves source-sim's simulated clock past the certificate's two days and puts it back, so it runs on the lead's
serial pass (it needs source-sim running with the mock: restart it after the change, R14; skipped, with the reason, without).

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
SID = "mr_disposal"
API = SIM + "/disposal-partner/api"
KEY = {"x-api-key": "mr_disposal-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"
PUMP = "SYN-MR-IP-0001"
MONITOR = "SYN-MR-PM-0001"

SANITISATION = {"sanitisationId": "SAN-0001", "tag": MONITOR, "status": "completed", "completedAt": "2026-10-08T09:00:00+00:00"}
CERTIFICATE = {"certificateId": "DC-0001-1", "tag": PUMP, "collectionId": "COL-0001", "issuedAt": "2026-10-09T09:00:00+00:00"}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/certificates", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the disposal partner mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_disposal_partner_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "disposal"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_condition_holds_the_disposal_fields():
    assert MODEL_FIELDS["condition"]["sanitisation_record_ref"].type == "ref"
    assert MODEL_FIELDS["condition"]["disposal_certificate_ref"].type == "ref"


def test_adapters_parts_disposal_map_facts_disposal_literal():
    (san,) = ADAPTERS[SID].map(Record("sanitisations", "SAN-0001", SANITISATION | {"org_unit_id": ORG}))
    assert (san.model, san.key, san.field) == ("condition", tag_key(ORG, MONITOR), "sanitisation_record_ref")
    assert san.value == "SAN-0001"
    (cert,) = ADAPTERS[SID].map(Record("certificates", "DC-0001-1", CERTIFICATE | {"org_unit_id": None}))
    assert (cert.model, cert.key, cert.field, cert.value) == (
        "condition",
        tag_key(None, PUMP),
        "disposal_certificate_ref",
        "DC-0001-1",
    )
    assert [check_fact(f) for f in (san, cert) if check_fact(f)] == []


@needs_mock
def test_adapters_parts_disposal_map_facts_disposal_sync():
    """A collected pump and a sanitised monitor hold their record references once simulated time has passed."""
    try:
        httpx.post(SIM + "/_sim/reset", params={"system": SID}, timeout=10).raise_for_status()
        httpx.post(SIM + "/_sim/clock/reset", timeout=10).raise_for_status()
        assert httpx.post(API + "/sanitisations", json={"tag": MONITOR}, headers=KEY, timeout=10).status_code == 201
        col = httpx.post(API + "/collections", json={"tags": [PUMP]}, headers=KEY, timeout=10)
        assert col.status_code == 201, col.text
        httpx.post(SIM + "/_sim/clock/advance", json={"days": 2, "hours": 1}, timeout=10).raise_for_status()
        with SessionLocal() as s:
            assert extra.register(s, SID, ORG) == SID
            s.commit()
        r = call("source.reconnect", {"source_id": SID}, "developer")
        assert r["ok"], r
        out = run_sync(SID, "manual", full=True)
        assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 2, out
        assert canonical("condition", tag_key(ORG, MONITOR))["data"]["sanitisation_record_ref"] == "SAN-0001"
        assert canonical("condition", tag_key(ORG, PUMP))["data"]["disposal_certificate_ref"].startswith("DC-")
    finally:
        httpx.post(SIM + "/_sim/clock/reset", timeout=10)
        httpx.post(SIM + "/_sim/reset", params={"system": SID}, timeout=10)
