"""Plan 9, P9-3.2: the recall register (`recall`), connected-tool telematics (`tooltel`) and tool service, stock and trade
demand (`parts`) adapters against source-sim's synthetic mocks.

None is a demo source: each starts unregistered, so every demo screen and count is unchanged. Synced (source.reconnect
registers and connects them, di.connectors.extra), they fill `recall.<recallId>`, `condition.<serial>` (telematics
facts), `demand.<id>` (open repair orders, sales orders, pool requests, trade bids) and `stock_unit.<unitId>`. The
mapping tests run on literal records; the sync test needs source-sim running with the mocks (restart it after the
change, R14) and is skipped, with the reason, when it lacks them.
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
IDS = ("recall", "tooltel", "parts")
RECALL_API = SIM + "/recalls/api"
PARTS_API = SIM + "/parts/api"
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}

NOTICE = {
    "recallId": "RC-2026-014", "toolClass": "CRH", "model": "CRH-22V Plus", "serialFrom": "CRH-44000", "serialTo": "CRH-44999",
    "remedy": "replace", "affectedParts": ["Brushless motor"], "status": "active", "publishedAt": "2026-08-12T00:00:00+00:00",
}  # fmt: skip
TOOL = {
    "serial": "CMH-48213", "runHours": 820, "highLoadShare": 0.3, "events": {"overheat": 0, "drop": 0, "overload": 0},
    "lastSeen": "2026-10-04T08:15:00+00:00", "coveragePct": 95,
}  # fmt: skip
RO = {
    "roId": "RO-60007", "customer": "Granite Civil", "partName": "Brushless motor", "toolClass": "CRH", "backorder": True,
    "needBy": "2026-10-20",
}  # fmt: skip
UNIT = {
    "unitId": "RU-7012", "serial": "CRH-80012", "toolClass": "CRH", "grade": "B", "rulPct": 61, "site": "Denver",
    "status": "available", "refurbishedAt": "2026-09-14",
}  # fmt: skip
SO = {
    "soId": "SO-80004",
    "customer": "Westmark Supply",
    "toolClass": "CMH",
    "site": "Houston",
    "needBy": "2026-10-22",
    "price": 820.0,
}
POOL = {
    "requestId": "TPR-0003", "site": "Atlanta", "toolClass": "BRK", "needBy": "2026-10-30", "avoidedPurchase": 1710.0,
    "quoteRef": "PR-1003",
}  # fmt: skip
BID = {
    "bidId": "BID-00012",
    "dealer": "Crestline Tool Traders",
    "toolClass": "AGR",
    "gradeMin": "B",
    "price": 95.0,
    "expires": "2026-10-18",
}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": list(IDS)})
        conn.execute(text("DELETE FROM canonical WHERE model IN ('recall', 'stock_unit')"))
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
        return (
            httpx.get(RECALL_API + "/notices", headers={"x-api-key": "recall-demo-key"}, timeout=10).status_code == 200
            and httpx.get(PARTS_API + "/catalogue", headers={"x-api-key": "parts-demo-key"}, timeout=10).status_code == 200
        )
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(
    not served(), reason="source-sim does not serve the recall, telematics and parts mocks: restart it (R14)"
)


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def mapped(sid: str, resource: str, key: str, doc: dict):
    facts = ADAPTERS[sid].map(Record(resource, key, doc))
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []
    return facts, {f.field: f.value for f in facts}


# ------------------------------------------------------------------ registration
def test_extra_sources_start_unregistered():
    for sid in IDS:
        assert ADAPTERS[sid].extra and ADAPTERS[sid].source_type == sid
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not set(IDS) & ids
    assert run_sync("recall", "manual")["status"] == "skipped"
    assert [ADAPTERS[s].auth_kind for s in IDS] == ["api_key", "oauth", "api_key"]


def test_canonical_models_hold_the_new_fields():
    assert {"recall", "stock_unit"} <= set(MODEL_FIELDS)
    assert MODEL_FIELDS["recall"]["recall_id"].required and MODEL_FIELDS["stock_unit"]["unit_id"].required
    assert MODEL_FIELDS["condition"]["event_counts"].type == "object" and MODEL_FIELDS["condition"]["run_hours"].type == "number"
    assert {"high_load_share", "telemetry_at", "telemetry_coverage_pct"} <= set(MODEL_FIELDS["condition"])
    assert {"part_name", "backorder", "grade_min", "price", "expires"} <= set(MODEL_FIELDS["demand"])
    assert MODEL_FIELDS["demand"]["backorder"].type == "bool" and MODEL_FIELDS["demand"]["expires"].type == "date"


# ------------------------------------------------------------------ mapping (literal records)
def test_recall_notice_maps_every_field_in_snake_case():
    facts, by = mapped("recall", "notices", "RC-2026-014", NOTICE)
    assert {f.model for f in facts} == {"recall"} and {f.key for f in facts} == {"RC-2026-014"}
    assert by["recall_id"] == "RC-2026-014" and by["tool_class"] == "CRH" and by["model"] == "CRH-22V Plus"
    assert (by["serial_from"], by["serial_to"], by["remedy"], by["status"]) == ("CRH-44000", "CRH-44999", "replace", "active")
    assert by["affected_parts"] == ["Brushless motor"] and by["published_at"].startswith("2026-08-12")


def test_telematics_maps_to_condition_by_serial():
    facts, by = mapped("tooltel", "tools", "CMH-48213", TOOL)
    assert {f.model for f in facts} == {"condition"} and {f.key for f in facts} == {"CMH-48213"}
    assert by == {
        "run_hours": 820, "high_load_share": 0.3, "event_counts": {"overheat": 0, "drop": 0, "overload": 0},
        "telemetry_at": "2026-10-04T08:15:00+00:00", "telemetry_coverage_pct": 95,
    }  # fmt: skip


def test_open_repair_order_is_a_wo_demand():
    facts, by = mapped("parts", "openRepairOrders", "RO-60007", RO)
    assert {f.model for f in facts} == {"demand"} and {f.key for f in facts} == {"RO-60007"}
    assert (by["kind"], by["part_name"], by["tool_class"], by["backorder"], by["need_by"], by["buyer"]) == (
        "wo", "Brushless motor", "CRH", True, "2026-10-20", "Granite Civil",
    )  # fmt: skip


def test_sales_order_pool_request_and_bid_are_demand():
    _, so = mapped("parts", "salesOrders", "SO-80004", SO)
    assert (so["kind"], so["tool_class"], so["site"], so["need_by"], so["price"], so["buyer"]) == (
        "so", "CMH", "Houston", "2026-10-22", 820.0, "Westmark Supply",
    )  # fmt: skip
    _, proj = mapped("parts", "poolRequests", "TPR-0003", POOL)
    assert (proj["kind"], proj["amount"], proj["order_ref"], proj["site"], proj["tool_class"]) == (
        "proj", 1710.0, "PR-1003", "Atlanta", "BRK",
    )  # fmt: skip
    _, bid = mapped("parts", "bids", "BID-00012", BID)
    assert (bid["kind"], bid["grade_min"], bid["price"], bid["expires"], bid["buyer"], bid["tool_class"]) == (
        "bid", "B", 95.0, "2026-10-18", "Crestline Tool Traders", "AGR",
    )  # fmt: skip


def test_refurbished_unit_maps_to_stock_unit_and_the_catalogue_makes_no_fact():
    facts, by = mapped("parts", "stock", "RU-7012", UNIT)
    assert {f.model for f in facts} == {"stock_unit"} and {f.key for f in facts} == {"RU-7012"}
    assert (by["unit_id"], by["serial"], by["tool_class"], by["grade"], by["rul_pct"], by["site"], by["status"]) == (
        "RU-7012", "CRH-80012", "CRH", "B", 61, "Denver", "available",
    )  # fmt: skip
    assert by["refurbished_at"] == "2026-09-14"
    cat = {"partNo": "PN-1001", "partName": "Gearbox", "toolClass": "CMH", "price": 180.0, "market": "US"}
    assert ADAPTERS["parts"].map(Record("catalogue", "PN-1001", cat)) == []


# ------------------------------------------------------------------ a sync against the mocks
@needs_mock
def test_sync_fills_recall_telematics_demand_and_stock():
    for sid in IDS:
        r = call("source.reconnect", {"source_id": sid}, "developer")
        assert r["ok"], r
        out = run_sync(sid, "manual", full=True)
        assert out["status"] == "ok" and out["records_failed"] == 0, (sid, out)
    rc = canonical("recall", "RC-2026-014")["data"]
    assert rc["serial_from"] == "CRH-44000" and rc["affected_parts"] == ["Brushless motor"] and rc["remedy"] == "replace"
    assert canonical("recall", "RC-2026-017")["data"]["affected_parts"] == ["Impact mechanism"]
    cond = canonical("condition", "CMH-48213")
    assert cond["data"]["run_hours"] == 820 and cond["data"]["telemetry_coverage_pct"] == 95
    assert cond["data"]["telemetry_at"].startswith("2026-10-04")
    assert {x["source_id"] for x in cond["provenance"]["run_hours"]} == {"tooltel"}
    assert canonical("condition", "CMH-48777")["data"]["telemetry_at"].startswith("2026-09-29")
    assert canonical("condition", "CRH-44120")["data"]["telemetry_coverage_pct"] == 80
    with engine.connect() as conn:
        n = dict(
            conn.execute(text("SELECT model, count(*) FROM canonical WHERE model IN ('recall', 'stock_unit') GROUP BY 1")).all()
        )
        wo = conn.execute(text("SELECT count(*) FROM canonical WHERE model = 'demand' AND key LIKE 'RO-6%'")).scalar_one()
        kinds = conn.execute(
            text(
                "SELECT count(*) FROM canonical WHERE model = 'demand' "
                "AND (key LIKE 'SO-8%' OR key LIKE 'TPR-%' OR key LIKE 'BID-%')"
            )
        ).scalar_one()
    assert n["stock_unit"] == 48 and n["recall"] >= 2
    assert wo == 120 and kinds == 20 + 10 + 30
