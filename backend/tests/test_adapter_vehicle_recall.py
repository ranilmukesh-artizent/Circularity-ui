"""Plan 9, P9-9.5: the vehicle recall database (source `uc_recall`) adapter against source-sim's synthetic mock.

`uc_recall` is no demo source: it starts unregistered (no source_system row). Its `lookup(client, vin)` is the per-VIN
check `evidence.refresh` (P9-9.9) calls; the mapping and the lookup run on literal records and a stub client, and a
second lookup runs on a real client when source-sim serves the mock (restart it after the change, R14; else skipped).
Nothing here resets or faults source-sim.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.adapters import vehicle_recall
from di.connectors.base import Record
from di.connectors.http import SourceClient
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import MODEL_FIELDS, check_fact, vin_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "uc_recall"
KEY = {"x-api-key": "uc_recall-demo-key"}
ORG = "Customer A"
CHECKED = "2026-10-07T09:00:05+00:00"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


OPEN_DOC = {
    "vin": vin(2), "checkedAt": CHECKED,
    "openRecalls": [{"campaignId": "SYN-24V-001", "component": "Fuel pump relay", "summary": "s", "remedyAvailable": True}],
    "remedied": [],
}  # fmt: skip
REMEDIED_DOC = {
    "vin": vin(60), "checkedAt": CHECKED, "openRecalls": [],
    "remedied": [{"campaignId": "SYN-25V-014", "remedyRef": "RR-0060", "remediedAt": "2026-08-01"}],
}  # fmt: skip


class Stub:
    """A client that serves one canned document and records the path asked."""

    def __init__(self, doc: dict):
        self.doc, self.paths = doc, []

    def get_json(self, path: str, **_kw):
        self.paths.append(path)
        return self.doc


def served() -> bool:
    try:
        return httpx.get(SIM + "/vehicle-recall/api/recalls", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the vehicle recall mock: restart it (R14)")


def by(facts) -> dict:
    return {f.field: f.value for f in facts}


def test_used_car_recall_source_starts_unregistered():
    a = ADAPTERS[SID]
    assert a.extra and a.source_type == "recall" and a.base_path == "/vehicle-recall/api"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == 0


def test_canonical_condition_holds_the_recall_fields():
    f = MODEL_FIELDS["condition"]
    assert (f["recall_open"].type, f["recall_campaigns"].type) == ("bool", "list")
    assert f["recall_checked_at"].type == "date" and f["recall_remedy_ref"].type == "ref"


def test_adapter_vehicle_recall_lookup_open():
    stub = Stub(OPEN_DOC)
    facts = vehicle_recall.lookup(stub, vin(2))
    assert stub.paths == [f"/recalls/vin/{vin(2)}"]
    assert {(f.model, f.key) for f in facts} == {("condition", vin_key(None, vin(2)))}
    v = by(facts)
    assert v["recall_open"] is True and v["recall_checked_at"] == CHECKED
    assert [c["campaignId"] for c in v["recall_campaigns"]] == ["SYN-24V-001"] and "recall_remedy_ref" not in v
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_vehicle_recall_lookup_remedied_and_org_key():
    facts = vehicle_recall.lookup(Stub(REMEDIED_DOC), vin(60), org_unit_id=ORG)
    v = by(facts)
    assert v["recall_open"] is False and v["recall_campaigns"] == [] and v["recall_remedy_ref"] == "RR-0060"
    assert {f.key for f in facts} == {vin_key(ORG, vin(60))}


def test_adapter_vehicle_recall_map_sync_record():
    facts = ADAPTERS[SID].map(Record("recalls", vin(2), OPEN_DOC | {"org_unit_id": ORG}))
    v = by(facts)
    assert {f.key for f in facts} == {vin_key(ORG, vin(2))} and v["recall_open"] is True
    assert [c["campaignId"] for c in v["recall_campaigns"]] == ["SYN-24V-001"]
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


@needs_mock
def test_adapter_vehicle_recall_lookup():
    a = ADAPTERS[SID]
    with SessionLocal() as s:
        client = SourceClient(SID, SIM + a.base_path, a.auth(), s)
        try:
            open_facts = vehicle_recall.lookup(client, "SYNUC000000000002")
            clean = vehicle_recall.lookup(client, "SYNUC000000000001")
        finally:
            client.close()
            s.rollback()
    v = by(open_facts)
    assert v["recall_open"] is True and v["recall_campaigns"][0]["campaignId"] == "SYN-24V-001"
    assert by(clean)["recall_open"] is False


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


@needs_mock
def test_adapter_vehicle_recall_sync_maps_condition_facts():
    """Registered and synced, the four recall rows give three open cars and one remedied (VINs ...002, 050, 055, 060)."""
    starting.reset()
    _forget()
    try:
        with SessionLocal() as s:
            assert extra.register(s, SID, ORG) == SID
            s.commit()
        r = call("source.reconnect", {"source_id": SID}, "developer")
        assert r["ok"], r
        out = run_sync(SID, "manual", full=True)
        assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 4, out
        with SessionLocal() as s:
            two = store.get(s, "condition", vin_key(ORG, vin(2)))
            sixty = store.get(s, "condition", vin_key(ORG, vin(60)))
        assert two and two["data"]["recall_open"] is True and two["data"]["recall_campaigns"][0]["campaignId"] == "SYN-24V-001"
        assert sixty and sixty["data"]["recall_open"] is False and sixty["data"]["recall_remedy_ref"] == "RR-0060"
        assert {x["source_id"] for x in two["provenance"]["recall_open"]} == {SID}
    finally:
        _forget()
        starting.reset()
