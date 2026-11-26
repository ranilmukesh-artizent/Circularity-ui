"""Plan 9, P9-11.3: the decontamination log (source `mr_decon`) adapter against source-sim's synthetic mock.

`mr_decon` is no demo source: it starts unregistered, so every demo screen and count is unchanged. Registered
(di.connectors.extra) and synced, it fills `condition.decon_*` facts keyed by `tag_key(org unit, tag)`. The mapping
tests run on literal records; the sync test needs source-sim running with the mock (restart it after the change, R14)
and is skipped, with the reason, when it lacks it. Stories: MR-03 (the gate uses the end of the cycle), MR-05, MR-12.

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
SID = "mr_decon"
API = SIM + "/decon-log/api"
KEY = {"x-api-key": "mr_decon-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"
TAG = "SYN-MR-IP-0005"

CYCLE = {
    "cycleId": "DC-0005", "tag": TAG, "method": "standard", "enhanced": False,
    "cycleStartedAt": "2026-11-21T21:00:00+00:00", "cycleEndedAt": "2026-11-22T00:00:00+00:00",
    "operatorRef": "OP-02", "result": "pass", "org_unit_id": ORG,
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["mr_decon", "mr_rental", "mr_assets"]})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/cycles", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the decontamination log mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_decon_source_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "decontamination"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_condition_holds_the_decon_fields():
    fields = {
        "decon_started_at": "date", "decon_ended_at": "date", "decon_record_ref": "ref", "decon_enhanced": "bool",
        "decon_result": "text",
    }  # fmt: skip
    assert {k: MODEL_FIELDS["condition"][k].type for k in fields} == fields


def test_adapter_decon_log_uses_cycle_end():
    """Two timestamps (MR-03): the start and the end are separate facts, and the end is the cycle's end, not its start."""
    facts = ADAPTERS[SID].map(Record("cycles", "DC-0005", CYCLE))
    assert {f.key for f in facts} == {tag_key(ORG, TAG)} and {f.model for f in facts} == {"condition"}
    by = {f.field: f.value for f in facts}
    assert by == {
        "decon_started_at": "2026-11-21T21:00:00+00:00", "decon_ended_at": "2026-11-22T00:00:00+00:00",
        "decon_record_ref": "DC-0005", "decon_enhanced": False, "decon_result": "pass",
    }  # fmt: skip
    ended = next(f for f in facts if f.field == "decon_ended_at")
    assert (ended.source_field, ended.source_value) == ("cycleEndedAt", CYCLE["cycleEndedAt"])
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []
    assert "operator_ref" not in by and "method" not in by


def test_adapter_decon_log_without_an_org_unit_is_shared():
    facts = ADAPTERS[SID].map(Record("cycles", "DC-0005", CYCLE | {"org_unit_id": None}))
    assert {f.key for f in facts} == {tag_key(None, TAG)}


@needs_mock
def test_adapter_decon_log_syncs_cycles():
    """After register(s, "mr_decon", "Customer A") and a sync, every cycle of the seed holds its facts."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    rows = httpx.get(API + "/cycles", headers=KEY, timeout=10).json()
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == len(rows) >= 39, out
    cond = canonical("condition", tag_key(ORG, TAG))["data"]
    assert cond["decon_record_ref"] == "DC-0005" and cond["decon_enhanced"] is False and cond["decon_result"] == "pass"
    assert cond["decon_started_at"] < cond["decon_ended_at"]
    assert canonical("condition", tag_key(ORG, "SYN-MR-IP-0010"))["data"]["decon_enhanced"] is True
