"""Plan 9, P9-3.1: the fleet contract system (source `fleet`) adapter against source-sim's synthetic fleet mock.

`fleet` is no demo source: it starts unregistered (no source_system row), so every demo screen and count is unchanged.
Registered by source.reconnect (di.connectors.extra) and synced, it fills `contract.<id>`, `contract_line.<serial>` and
the named lease `demand.<id>`. The mapping tests run on literal records; the sync tests need source-sim running with the
fleet mock (restart it after the change, R14) and are skipped, with the reason, when it lacks it.

The module starts and ends with the demo reset (tests/starting.py), which removes the sources it registered, and removes
the facts it wrote.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import MODEL_FIELDS, check_fact
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "fleet"
API = SIM + "/fleet/api/v1"
KEY = {"x-api-key": "fleet-demo-key"}
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}

LINE = {
    "lineId": "FL-30117-03", "contractId": "FC-30117", "serial": "CMH-48213", "toolClass": "CMH", "model": "CMH-12 Pro",
    "status": "returned", "returnReason": "end_of_term", "theftClaimOpen": False, "claimRef": None,
    "damageChargeOpen": False, "chargeRef": None, "feeMonth": 55.0, "coverType": "full", "coverActive": True,
    "coverUntil": "2027-03-01", "swapAllowed": True, "nonReturnFee": 0.0, "monthsOnContract": 33,
    "updatedAt": "2026-10-06T10:00:00+00:00",
}  # fmt: skip
CONTRACT = {
    "contractId": "FC-30117", "customer": "Brightline Mechanical", "market": "US", "startDate": "2024-01-05",
    "endDate": "2027-01-05", "noticeDate": None, "termMonths": 36, "status": "active", "rateCardVersion": "v4",
    "feeMonth": 1210.0, "keyAccount": False, "ownerOrg": "Fleet North America", "renewalStatus": "open",
    "lineIds": ["FL-30117-01", "FL-30117-03"], "updatedAt": "2026-10-06T10:00:00+00:00",
}  # fmt: skip
RENEWAL = {
    "demandId": "FC-30117-R", "kind": "lease", "contractId": "FC-30117", "customer": "Brightline Mechanical",
    "site": "Houston", "needBy": "2026-10-26", "rateMonth": 55.0, "termMonths": 12, "renew": True, "toolClass": "CMH",
    "status": "open",
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["fleet", "repairlog"]})
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line', 'repair_event')"))
        conn.execute(
            text(
                "DELETE FROM canonical c WHERE c.model IN ('condition', 'demand') AND NOT EXISTS "
                "(SELECT 1 FROM provenance p WHERE p.model = c.model AND p.key = c.key)"
            )
        )


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/contracts", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the fleet mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


# ------------------------------------------------------------------ registration
def test_extra_sources_start_unregistered():
    """Neither extra system has a source_system row after the demo's starting state: the demo's 21 are all there is."""
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "fleet" and "repairlog" in ADAPTERS
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not {"fleet", "repairlog"} & ids
    assert run_sync(SID, "manual")["status"] == "skipped"


def test_canonical_models_hold_the_fleet_fields():
    assert {"contract", "contract_line", "repair_event"} <= set(MODEL_FIELDS)
    assert MODEL_FIELDS["contract"]["contract_id"].required and MODEL_FIELDS["contract_line"]["line_id"].required
    assert MODEL_FIELDS["repair_event"]["event_id"].required
    assert {"tool_class", "term_months", "renew", "site", "need_days"} <= set(MODEL_FIELDS["demand"])
    assert MODEL_FIELDS["demand"]["renew"].type == "bool" and MODEL_FIELDS["demand"]["need_days"].type == "number"


# ------------------------------------------------------------------ mapping (literal records)
def test_fleet_maps_a_contract_line_to_the_serial():
    facts = ADAPTERS[SID].map(Record("lines", "FL-30117-03", LINE))
    assert {f.key for f in facts} == {"CMH-48213"} and {f.model for f in facts} == {"contract_line"}
    by = {f.field: f.value for f in facts}
    assert (by["contract_id"], by["status"], by["return_reason"]) == ("FC-30117", "returned", "end_of_term")
    assert by["tool_class"] == "CMH"
    assert by["cover_active"] is True and by["non_return_fee"] == 0.0 and by["line_id"] == "FL-30117-03"
    assert "claim_ref" not in by  # an empty field is left out
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_fleet_maps_a_contract_and_a_renewal():
    contract = ADAPTERS[SID].map(Record("contracts", "FC-30117", CONTRACT))
    by = {f.field: f.value for f in contract}
    assert {f.key for f in contract} == {"FC-30117"} and by["key_account"] is False and by["end_date"] == "2027-01-05"
    assert by["line_ids"] == ["FL-30117-01", "FL-30117-03"] and "notice_date" not in by
    demand = ADAPTERS[SID].map(Record("renewals", "FC-30117-R", RENEWAL))
    d = {f.field: f.value for f in demand}
    assert {f.model for f in demand} == {"demand"} and {f.key for f in demand} == {"FC-30117-R"}
    assert (d["kind"], d["need_by"], d["lease_rate"], d["term_months"], d["renew"], d["site"], d["tool_class"], d["buyer"]) == (
        "lease", "2026-10-26", 55.0, 12, True, "Houston", "CMH", "Brightline Mechanical",
    )  # fmt: skip
    assert [(f.field, check_fact(f)) for f in contract + demand if check_fact(f)] == []


def test_fleet_returns_and_history_make_no_fact():
    assert ADAPTERS[SID].map(Record("returns", "FR-70001", {"returnId": "FR-70001", "serial": "CMH-48213"})) == []
    assert ADAPTERS[SID].map(Record("history", "FC-20101", {"contractId": "FC-20101", "outcome": "lapsed"})) == []


# ------------------------------------------------------------------ a sync against the mock
def mock_all(path: str) -> list[dict]:
    out, offset = [], 0
    while offset is not None:
        body = httpx.get(API + path, headers=KEY, params={"limit": 200, "offset": offset}, timeout=30).json()
        out += body["items"]
        offset = body["next"]
    return out


@needs_mock
def test_fleet_adapter_maps_contract_line():
    """source.reconnect registers the unregistered fleet source and connects it; a full sync stores the contract lines
    by serial with their provenance."""
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    line = canonical("contract_line", "CMH-48213")
    assert line["data"]["contract_id"] == "FC-30117"
    assert line["data"]["status"] == "returned" and line["data"]["return_reason"] == "end_of_term"
    assert {x["source_id"] for x in line["provenance"]["status"]} == {SID}
    lines = mock_all("/contract-lines")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM canonical WHERE model = 'contract_line'")).scalar_one()
        c = conn.execute(text("SELECT count(*) FROM canonical WHERE model = 'contract'")).scalar_one()
        raw = dict(
            conn.execute(text("SELECT resource, count(*) FROM raw_record WHERE source_id = :i GROUP BY 1"), {"i": SID}).all()
        )
    assert n == len(lines) == 403 and c == 41  # 40 contracts and FC-30141, the service desk's tools
    assert (raw["returns"], raw["renewals"], raw["history"]) == (18, 25, 60)  # read, kept raw, no fact


@needs_mock
def test_fleet_sync_maps_contract_and_named_renewal():
    contract = canonical("contract", "FC-30117")["data"]
    assert (contract["customer"], contract["market"], contract["key_account"], contract["end_date"]) == (
        "Brightline Mechanical", "US", False, "2027-01-05",
    )  # fmt: skip
    assert len(contract["line_ids"]) == 14 and "notice_date" not in contract
    d = canonical("demand", "FC-30117-R")["data"]
    assert (d["tool_class"], d["site"], d["lease_rate"], d["term_months"], d["kind"], d["need_by"]) == (
        "CMH", "Houston", 55, 12, "lease", "2026-10-26",
    )  # fmt: skip
    assert canonical("contract_line", "BRK-51007")["data"]["theft_claim_open"] is True
