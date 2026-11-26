"""Plan 9, P9-11.4: the biomedical service system (source `mr_biomed`) adapter against source-sim's synthetic mock.

`mr_biomed` is no demo source: it starts unregistered, so every demo screen and count is unchanged. Registered
(di.connectors.extra) and synced, it fills `condition.*` and `intervention.repair_estimate` facts keyed by
`tag_key(org unit, tag)`. The mapping tests run on literal records; the sync test needs source-sim running with the mock
(restart it after the change, R14) and is skipped, with the reason, when it lacks it.

The module starts and ends with the demo reset (tests/starting.py), which removes the sources it registered, and removes
the facts it wrote.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.adapters.biomed_service import covering_notice
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
SID = "mr_biomed"
API = SIM + "/biomed-service/api"
KEY = {"x-api-key": "mr_biomed-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"
TAG = "SYN-MR-IP-0001"

SERVICE = {
    "tag": TAG, "model": "IP-200", "serialNo": 2001, "pmDue": "2027-02-15", "pmCode": "PM-12M", "lastPm": "2026-02-15",
    "certificationExpiry": "2027-03-31", "functionalTest": {"result": "pass", "at": "2026-09-30"},
    "electricalSafety": {"standard": "IEC 62353", "result": "pass", "at": "2026-09-30"},
    "notes": [{"text": "Housing scuff", "kind": "cosmetic"}], "repairEstimate": 0, "faults": [], "notice": None,
    "org_unit_id": ORG,
}  # fmt: skip
NOTICE = {
    "noticeId": "FSN-031",
    "model": "IP-300",
    "serialFrom": 3000,
    "serialTo": 3099,
    "status": "open",
    "correctionRef": "FSN-031-A",
}
CLOSED = {
    "noticeId": "FSN-018",
    "model": "IP-300",
    "serialFrom": 3000,
    "serialTo": 3099,
    "status": "closed",
    "correctionRef": "FSN-018-B",
}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["mr_biomed"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/assets", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the biomedical service mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def by(facts) -> dict:
    return {(f.model, f.field): f.value for f in facts}


def test_biomed_source_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "service"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_models_hold_the_biomed_fields():
    assert {
        "pm_due", "pm_code", "certification_expiry", "functional_test", "electrical_safety", "notes", "correction_open",
        "correction_ref", "servicing_assessment",
    } <= set(MODEL_FIELDS["condition"])  # fmt: skip
    assert MODEL_FIELDS["intervention"]["repair_estimate"].type == "number"
    assert MODEL_FIELDS["condition"]["correction_open"].type == "bool" and MODEL_FIELDS["condition"]["notes"].type == "list"


def test_covering_notice_matches_model_and_serial_range():
    assert covering_notice([NOTICE], "IP-300", 3030) == NOTICE
    assert covering_notice([NOTICE], "IP-300", 3000) == NOTICE and covering_notice([NOTICE], "IP-300", 3099) == NOTICE
    assert covering_notice([NOTICE], "IP-300", 3100) is None and covering_notice([NOTICE], "IP-300", 2999) is None
    assert covering_notice([NOTICE], "IP-200", 3030) is None and covering_notice([NOTICE], "IP-300", None) is None
    assert covering_notice([CLOSED, NOTICE], "IP-300", 3030) == NOTICE  # an open notice wins


def test_adapter_biomed_service_maps_facts_literal():
    facts = ADAPTERS[SID].map(Record("service", TAG, SERVICE))
    assert {f.key for f in facts} == {tag_key(ORG, TAG)} and {f.model for f in facts} == {"condition", "intervention"}
    v = by(facts)
    assert (v[("condition", "pm_due")], v[("condition", "pm_code")]) == ("2027-02-15", "PM-12M")
    assert v[("condition", "certification_expiry")] == "2027-03-31"
    assert v[("condition", "functional_test")] == {"result": "pass", "at": "2026-09-30"}
    assert v[("condition", "electrical_safety")]["standard"] == "IEC 62353"
    assert v[("condition", "notes")] == [{"text": "Housing scuff", "kind": "cosmetic"}]
    assert v[("intervention", "repair_estimate")] == 0
    assert v[("condition", "correction_open")] is False and ("condition", "correction_ref") not in v
    assert "last_pm" not in {f for _, f in v}
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_biomed_service_maps_a_covering_notice():
    v = by(ADAPTERS[SID].map(Record("service", TAG, SERVICE | {"notice": NOTICE})))
    assert v[("condition", "correction_open")] is True and v[("condition", "correction_ref")] == "FSN-031-A"
    v = by(ADAPTERS[SID].map(Record("service", TAG, SERVICE | {"notice": CLOSED})))
    assert v[("condition", "correction_open")] is False and v[("condition", "correction_ref")] == "FSN-018-B"


def test_adapter_biomed_service_maps_an_assessment():
    rec = Record("assessments", "SYN-MR-EB-0040", {"tag": "SYN-MR-EB-0040", "result": "servicing", "org_unit_id": None})
    facts = ADAPTERS[SID].map(rec)
    assert [(f.model, f.key, f.field, f.value) for f in facts] == [
        ("condition", tag_key(None, "SYN-MR-EB-0040"), "servicing_assessment", "servicing")
    ]
    assert [check_fact(f) for f in facts if check_fact(f)] == []


@needs_mock
def test_adapter_biomed_service_maps_facts():
    """After register(s, "mr_biomed", "Customer A") and a sync, the service records, notices and assessments hold facts."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 82, out
    c = canonical("condition", tag_key(ORG, TAG))["data"]
    assert (c["pm_due"], c["certification_expiry"], c["correction_open"]) == ("2027-02-15", "2027-03-31", False)
    assert c["electrical_safety"]["standard"] == "IEC 62353"
    covered = canonical("condition", tag_key(ORG, "SYN-MR-IP-0030"))["data"]
    assert covered["correction_open"] is True and covered["correction_ref"] == "FSN-031-A"
    assert canonical("condition", tag_key(ORG, "SYN-MR-IP-0031"))["data"]["correction_open"] is False
    assert canonical("intervention", tag_key(ORG, "SYN-MR-PM-0007"))["data"]["repair_estimate"] == 1350
    assert canonical("condition", tag_key(ORG, "SYN-MR-EB-0040"))["data"]["servicing_assessment"] == "servicing"
    assert canonical("condition", tag_key(ORG, "SYN-MR-EB-0041"))["data"]["servicing_assessment"] == "full_refurbishment"
