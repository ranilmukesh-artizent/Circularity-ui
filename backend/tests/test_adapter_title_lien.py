"""Plan 9, P9-9.3: the title and lien service (source `uc_title`) adapter against source-sim's synthetic title mock.

`uc_title` is no demo source: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. Registered (di.connectors.extra) and synced, it fills `condition.*` facts keyed by `vin_key(org unit, vin)`:
title_status, lien_open, lien_release_ref, title_brand, title_checked_at. The mapping tests run on literal records; the
sync test needs source-sim running with the title mock (restart it after the change, R14) and is skipped, with the
reason, when it lacks it. Title, lien and
brand rules are state law and differ: the mock models generic evidence only.

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
from di.services.canonical.schema import MODEL_FIELDS, check_fact, vin_key
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "uc_title"
API = SIM + "/title-lien/api/v2"
KEY = {"x-api-key": "uc_title-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
ORG = "Customer A"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


LIEN = {"lienId": "LN-0003", "holderRef": "H-004", "amount": 8200, "released": False, "releaseRef": None, "releasedAt": None}
OPEN = {
    "vin": vin(3), "titleStatus": "lien", "brand": None, "brandSource": None, "liens": [LIEN],
    "checkedAt": "2026-10-07T09:00:00+00:00", "org_unit_id": ORG,
}  # fmt: skip
RELEASED = OPEN | {
    "titleStatus": "clear",
    "liens": [LIEN | {"released": True, "releaseRef": "LR-000003", "releasedAt": "2026-10-09T09:00:00+00:00"}],
}
FLOOD = {
    "vin": vin(21), "titleStatus": "clear", "brand": "flood", "brandSource": "state title", "liens": [],
    "checkedAt": "2026-10-07T09:00:00+00:00", "org_unit_id": ORG,
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/titles", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the title and lien mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def mapped(payload: dict) -> dict[str, object]:
    facts = ADAPTERS[SID].map(Record("titles", payload["vin"], payload))
    assert {f.key for f in facts} == {vin_key(payload.get("org_unit_id"), payload["vin"])}
    assert {f.model for f in facts} == {"condition"}
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []
    return {f.field: f.value for f in facts}


# ------------------------------------------------------------------ registration
def test_title_source_starts_unregistered():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "title"
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and SID not in ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_condition_holds_the_title_fields():
    assert {"title_status", "lien_open", "lien_release_ref", "title_brand", "title_checked_at"} <= set(MODEL_FIELDS["condition"])
    assert MODEL_FIELDS["condition"]["lien_open"].type == "bool" and MODEL_FIELDS["condition"]["title_status"].type == "text"


# ------------------------------------------------------------------ mapping (literal records)
def test_adapter_title_lien_maps_an_open_lien():
    by = mapped(OPEN)
    assert (by["title_status"], by["lien_open"], by["title_checked_at"]) == ("lien", True, "2026-10-07T09:00:00+00:00")
    assert "lien_release_ref" not in by and "title_brand" not in by  # empty in the source: no fact


def test_adapter_title_lien_maps_a_released_lien():
    by = mapped(RELEASED)
    assert (by["title_status"], by["lien_open"], by["lien_release_ref"]) == ("clear", False, "LR-000003")
    assert "holder_ref" not in by and "lien_holder" not in by  # a code, kept raw only


def test_adapter_title_lien_maps_a_brand_and_a_clear_title():
    by = mapped(FLOOD)
    assert (by["title_status"], by["lien_open"], by["title_brand"]) == ("clear", False, "flood")


def test_adapter_title_lien_without_an_org_unit_is_shared():
    facts = ADAPTERS[SID].map(Record("titles", vin(3), OPEN | {"org_unit_id": None}))
    assert {f.key for f in facts} == {vin_key(None, vin(3))}


# ------------------------------------------------------------------ a sync against the mock
@needs_mock
def test_adapter_title_lien_maps_facts():
    """`condition.lien_open` follows the live title: true for VIN ...003 until its scheduled release, false after;
    VIN ...070 never releases. (The shared sim's clock may already be past the release: the test reads the title.)"""
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0 and out["records_read"] == 100, out
    live = httpx.get(f"{API}/titles/{vin(3)}", headers=KEY, timeout=10).json()
    three = canonical("condition", vin_key(ORG, vin(3)))
    assert three["data"]["title_status"] == live["titleStatus"]
    assert three["data"]["lien_open"] is (live["titleStatus"] == "lien")
    if live["titleStatus"] == "clear":
        assert three["data"]["lien_release_ref"] == live["liens"][0]["releaseRef"]
    assert {x["source_id"] for x in three["provenance"]["lien_open"]} == {SID}
    assert canonical("condition", vin_key(ORG, vin(70)))["data"]["lien_open"] is True
    assert canonical("condition", vin_key(ORG, vin(21)))["data"]["title_brand"] == "flood"
    assert canonical("condition", vin_key(ORG, vin(23)))["data"]["title_brand"] == "salvage"
    one = canonical("condition", vin_key(ORG, vin(1)))["data"]
    assert (one["lien_open"], one["title_status"]) == (False, "clear") and "title_brand" not in one
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM canonical WHERE model = 'condition' AND key LIKE :k AND jsonb_exists(data, 'lien_open')"),
            {"k": f"{ORG}:SYNUC%"},
        ).scalar_one()
    assert n == 100
