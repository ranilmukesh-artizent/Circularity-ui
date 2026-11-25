"""Plan 9, P9-9.4: the vehicle inspection app (source `uc_insp`) adapter against source-sim's synthetic mock.

`uc_insp` is no demo source: it starts unregistered, so every demo screen and count is unchanged. Registered
(di.connectors.extra) and synced, it fills `condition.*` facts keyed by `vin_key(org unit, vin)`. The mapping tests run
on literal records; the sync test needs source-sim running with the mock (restart it, R14) and skips otherwise.
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
SID = "uc_insp"
API = SIM + "/vehicle-inspection/api"
KEY = {"x-api-key": "uc_insp-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


INSPECTION = {
    "inspectionId": "INS-0004", "vin": vin(4), "status": "complete", "conditionScore": 3, "odometerPhotoReading": 61240,
    "photos": [{"photoId": "PH-0004-1", "area": "odometer"}], "damage": [], "hailDamage": False, "tyres": "ok",
    "brakes": "ok", "reconEstimate": 900, "reconLines": [{"label": "Tyres", "amount": 900, "excessWear": False}],
    "batterySoh": None, "pairedDevices": False, "completedAt": "2026-10-05T10:00:00+00:00",
    "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
}  # fmt: skip
ASSESSMENT = {
    "assessmentId": "BA-0001", "vin": vin(44), "status": "complete", "batterySoh": 74, "result": "pack_replacement_needed",
    "requestedAt": "2026-10-07T09:00:00+00:00", "completedAt": "2026-10-08T09:00:00+00:00", "org_unit_id": ORG,
}  # fmt: skip
PENDING = ASSESSMENT | {"assessmentId": "BA-0002", "status": "scheduled", "result": None, "batterySoh": None, "completedAt": None}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["uc_insp"]})
        conn.execute(text("DELETE FROM canonical WHERE model = 'condition' AND key LIKE :p"), {"p": "%:SYNUC%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/inspections", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the inspection mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_inspection_source_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "inspection"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_condition_holds_the_inspection_fields():
    assert {
        "inspection_ref", "condition_score", "odometer_photo_reading", "recon_estimate", "recon_lines", "hail_damage",
        "paired_devices", "battery_soh", "battery_assessment_ref", "battery_assessment_result", "inspection_at",
        "inspection_status",
    } <= set(MODEL_FIELDS["condition"])  # fmt: skip
    assert MODEL_FIELDS["condition"]["recon_lines"].type == "list" and MODEL_FIELDS["condition"]["hail_damage"].type == "bool"


def test_adapter_vehicle_inspection_maps_facts_from_a_record():
    facts = ADAPTERS[SID].map(Record("inspections", "INS-0004", INSPECTION))
    assert {f.key for f in facts} == {vin_key(ORG, vin(4))} and {f.model for f in facts} == {"condition"}
    by = {f.field: f.value for f in facts}
    assert by["odometer_photo_reading"] == 61240 and by["condition_score"] == 3 and by["recon_estimate"] == 900
    assert (by["inspection_ref"], by["inspection_status"], by["hail_damage"]) == ("INS-0004", "complete", False)
    assert by["paired_devices"] is False and by["inspection_at"] == "2026-10-05T10:00:00+00:00"
    assert by["recon_lines"] == INSPECTION["reconLines"] and "battery_soh" not in by  # None is no fact
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_vehicle_inspection_maps_an_assessment():
    facts = ADAPTERS[SID].map(Record("battery_assessments", "BA-0001", ASSESSMENT))
    by = {f.field: f.value for f in facts}
    assert {f.key for f in facts} == {vin_key(ORG, vin(44))}
    assert by == {"battery_assessment_ref": "BA-0001", "battery_assessment_result": "pack_replacement_needed", "battery_soh": 74}
    pending = {f.field: f.value for f in ADAPTERS[SID].map(Record("battery_assessments", "BA-0002", PENDING))}
    assert pending == {"battery_assessment_ref": "BA-0002"}  # nothing is claimed before it completes


@needs_mock
def test_adapter_vehicle_inspection_maps_facts():
    """After register and a sync, VIN ...004's odometer photo reading is 61240."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] >= 100, out
    c = canonical("condition", vin_key(ORG, vin(4)))
    assert c["data"]["odometer_photo_reading"] == 61240
    assert {x["source_id"] for x in c["provenance"]["odometer_photo_reading"]} == {SID}
    assert canonical("condition", vin_key(ORG, vin(7)))["data"]["recon_estimate"] == 2800
    assert canonical("condition", vin_key(ORG, vin(90)))["data"]["inspection_status"] == "scheduled"
    assert canonical("condition", vin_key(ORG, vin(44)))["data"]["battery_soh"] == 74
