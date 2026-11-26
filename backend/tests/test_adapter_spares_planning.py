"""Plan 9, P9-10.4: the spares planning (source `tn_spares`) adapter against source-sim's synthetic mock.

Starts unregistered like every extra source. The mapping tests run on literal records; the sync test is skipped, with
the reason, when source-sim does not serve the mock (restart it, R14). Stories TN-11, TN-12, TN-18, TN-19.
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
from di.services.canonical.schema import SHARED_ORG, check_fact, serial_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "tn_spares"
API = SIM + "/spares-planning/api"
KEY = {"x-api-key": "tn_spares-demo-key"}
ORG = "Customer A"


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p OR key LIKE :q"), {"p": "%:SN-SP-%", "q": "%:PSU-48"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/catalogue", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the spares mock: restart it (R14)")


def facts(resource: str, rid: str, payload: dict):
    return ADAPTERS[SID].map(Record(resource, rid, payload | {"org_unit_id": ORG}))


def test_adapter_spares_planning_maps_facts():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "spares_planning"
    cat = facts("catalogue", "BBU-2200", {"model": "BBU-2200", "newPrice": 4200, "generation": "previous"})
    assert {(f.model, f.key, f.field, f.value) for f in cat} == {
        ("market", f"{ORG}:BBU-2200", "new_price", 4200),
        ("market", f"{ORG}:BBU-2200", "generation", "previous"),
    }
    cell = {"region": "North", "model": "RRU-4410"}
    tgt = facts("targets", "North:RRU-4410", cell | {"target": 4, "stock": 2, "useProbability12m": 0.55})
    assert {(f.model, f.key, f.field, f.value) for f in tgt} == {
        ("demand", f"{ORG}:North:RRU-4410", "spares_target", 4),
        ("demand", f"{ORG}:North:RRU-4410", "use_probability", 0.55),
    }
    need = facts("forecast6m", "North:RRU-4410", {"region": "North", "model": "RRU-4410", "need": 2})
    assert [(f.key, f.field, f.value) for f in need] == [(f"{ORG}:North:RRU-4410", "need_6m", 2)]
    reqs = [{"reqId": "PR-3302", "quantity": 1, "status": "open"}]
    pr = facts("requisitions", "North:RRU-4410", {"region": "North", "model": "RRU-4410", "requisitions": reqs})
    assert [(f.key, f.field, f.value) for f in pr] == [(f"{ORG}:North:RRU-4410", "requisitions", reqs)]
    unit = facts("stock", "SN-SP-0001", {"serial": "SN-SP-0001", "model": "PSU-48", "region": "North", "idleDays": 41})
    assert {f.key for f in unit} == {serial_key(ORG, "SN-SP-0001")} and {f.model for f in unit} == {"asset"}
    assert {f.field: f.value for f in unit}["idle_days"] == 41
    psu = {"model": "PSU-48", "newPrice": 1100, "generation": "current", "org_unit_id": None}
    shared = ADAPTERS[SID].map(Record("catalogue", "PSU-48", psu))
    assert {f.key for f in shared} == {f"{SHARED_ORG}:PSU-48"}
    assert [(f.field, check_fact(f)) for f in cat + tgt + need + pr + unit if check_fact(f)] == []


def test_spares_planning_starts_unregistered():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == 0
    assert run_sync(SID, "manual")["status"] == "skipped"


@needs_mock
def test_adapter_spares_planning_sync():
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with SessionLocal() as s:
        price = store.get(s, "market", f"{ORG}:RRU-4410")
        cell = store.get(s, "demand", f"{ORG}:North:RRU-4410")
    assert price is not None and price["data"]["new_price"] == 9800
    assert cell is not None and (cell["data"]["spares_target"], cell["data"]["use_probability"]) == (4, 0.55)
    assert [r["reqId"] for r in cell["data"]["requisitions"]] == ["PR-3302"]
