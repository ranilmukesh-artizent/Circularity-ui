"""Plan 9, P9-11.5: the parts supplier portal (source `mr_parts`) adapter against source-sim's synthetic mock.

`mr_parts` is no demo source: it starts unregistered, so every demo screen and count is unchanged. Registered
(di.connectors.extra) and synced, it fills `market.part_prices` and `market.harvest_values` per device model, keyed by
`tag_key(org unit, model)`. The mapping tests run on literal records; the sync test needs source-sim running with the mock
(restart it after the change, R14) and is skipped, with the reason, when it lacks it.

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
SID = "mr_parts"
API = SIM + "/parts-portal/api"
KEY = {"x-api-key": "mr_parts-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"
MODEL = "Synthetic Volumetric Pump V2"

PARTS = [
    {"partNo": "PRT-PUMP-MOTOR", "label": "Pump motor", "price": 240, "leadDays": 5, "harvestValue": 168, "model": MODEL},
    {"partNo": "PRT-PUMP-CTRL", "label": "Controller", "price": 310, "leadDays": 9, "harvestValue": 217, "model": MODEL},
]  # fmt: skip
RECORD = {"model": MODEL, "parts": PARTS, "org_unit_id": ORG}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:Synthetic %"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/parts", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the parts portal mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_parts_portal_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "parts"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_market_holds_the_parts_fields():
    assert MODEL_FIELDS["market"]["part_prices"].type == "list" and MODEL_FIELDS["market"]["harvest_values"].type == "list"


def test_adapters_parts_disposal_map_facts_parts_literal():
    facts = ADAPTERS[SID].map(Record("parts", MODEL, RECORD))
    assert {f.key for f in facts} == {tag_key(ORG, MODEL)} and {f.model for f in facts} == {"market"}
    by = {f.field: f.value for f in facts}
    assert by["part_prices"] == [
        {"part_no": "PRT-PUMP-MOTOR", "label": "Pump motor", "price": 240, "lead_days": 5},
        {"part_no": "PRT-PUMP-CTRL", "label": "Controller", "price": 310, "lead_days": 9},
    ]  # fmt: skip
    assert by["harvest_values"] == [
        {"part_no": "PRT-PUMP-MOTOR", "label": "Pump motor", "harvest_value": 168},
        {"part_no": "PRT-PUMP-CTRL", "label": "Controller", "harvest_value": 217},
    ]  # fmt: skip
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []
    shared = ADAPTERS[SID].map(Record("parts", MODEL, RECORD | {"org_unit_id": None}))
    assert {f.key for f in shared} == {tag_key(None, MODEL)}


@needs_mock
def test_adapters_parts_disposal_map_facts_parts_sync():
    """After register(s, "mr_parts", "Customer A") and a sync, each device model holds its prices."""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] >= 3, out
    prices = canonical("market", tag_key(ORG, MODEL))["data"]["part_prices"]
    by = {p["label"]: p for p in prices}
    assert (by["Pump motor"]["price"], by["Controller"]["price"]) == (240, 310) and by["Controller"]["lead_days"] > 0
    harvest = canonical("market", tag_key(ORG, MODEL))["data"]["harvest_values"]
    assert {h["label"] for h in harvest} == set(by)
    assert all(0 < h["harvest_value"] < by[h["label"]]["price"] for h in harvest)
