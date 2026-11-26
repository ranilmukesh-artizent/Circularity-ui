"""Plan 9, P9-6.2: the device registry (`dvreg`) and device lab (`dvlab`) adapters, the device tables (migration 0047),
the canonical device facts and the trade-in reads, against source-sim's synthetic device mocks (P9-6.1).

Neither is a demo source: each starts unregistered, so every demo screen and count is unchanged. Synced (source.reconnect
registers and connects them, di.connectors.extra), they fill `condition.<field>` and `asset.<field>` keyed `IMEI:<imei>`;
`dvlab` also lands `device_tradein` and `device_dispute` rows. The mapping and landing tests run on literal records; the
sync tests need source-sim running with the mocks (restart it after the change, R14) and are skipped, with the reason,
when it lacks them. Story ids: DV-01 ... DV-05 (the facts the device case reads as evidence, I-3).
"""

import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.repositories import device_tradeins
from di.services.canonical import store
from di.services.canonical.schema import MODEL_FIELDS, check_fact
from di.services.modeler.pack import load_pack
from di.workflow import engine as eng
from tests import starting
from tests.helpers import call, client

SIM = get_settings().source_sim_url
IDS = ("dvreg", "dvlab")
REG_API = SIM + "/device-registry/v1"
LAB_API = SIM + "/device-lab/v1"
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
SAMPLE = "359990000000428"
TABLES = (
    "device_tradein", "device_price_point", "device_launch", "device_listing", "device_bid", "device_sale", "device_dispute",
    "device_replacement_demand",
)  # fmt: skip

TRADEIN = {
    "tradeInId": "TI-00428", "imei": SAMPLE,
    "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
    "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": "2026-09-20T10:00:00+00:00"},
    "partner": "P01", "batchId": "BATCH-0011", "bulk": False, "receivedAt": "2026-09-20T10:00:00+00:00", "payoutAmount": 410,
}  # fmt: skip
DIAGNOSTIC = {
    "imei": SAMPLE, "imeiRead": SAMPLE, "modelRead": "iPhone 14", "storageReadGb": 128, "functionalFails": [],
    "batteryHealthPct": 84, "testedAt": "2026-09-20T14:00:00+00:00",
}  # fmt: skip
GRADING = {
    "imei": SAMPLE, "cosmeticGrade": "B", "photoIds": ["PH-00428-front", "PH-00428-back", "PH-00428-screen"],
    "gradedAt": "2026-09-21T10:00:00+00:00",
}  # fmt: skip
WIPE = {
    "certificateId": "WC-00428", "imei": SAMPLE, "method": "Purge", "toolVersion": "4.2.1", "verification": "pass",
    "operator": "OP-03", "at": "2026-09-20T16:00:00+00:00",
}  # fmt: skip
PARTS = {"imei": SAMPLE, "status": "genuine", "declaredAt": "2026-09-20T13:00:00+00:00"}
CHECK = {
    "imei": SAMPLE, "blacklist": "reported_stolen", "activationLock": "on", "finance": "balance_owed",
    "checkedAt": "2026-09-20T11:00:00+00:00",
}  # fmt: skip
DISPUTE = {
    "disputeId": "DSP-0001", "imei": SAMPLE, "partner": "P02", "reason": "Screen graded before power-on", "declaredGrade": "B",
    "gradedGrade": "C", "raisedAt": "2026-09-22T10:00:00+00:00", "status": "open",
}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": list(IDS)})
        conn.execute(
            text(
                "DELETE FROM canonical c WHERE c.model IN ('condition', 'asset') AND c.key LIKE 'IMEI:%' "
                "AND NOT EXISTS (SELECT 1 FROM provenance p WHERE p.model = c.model AND p.key = c.key)"
            )
        )
        for t in TABLES:
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


@pytest.fixture(autouse=True)
def _empty_device_tables():
    with engine.begin() as conn:
        for t in TABLES:
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


def served() -> bool:
    try:
        return httpx.get(
            REG_API + "/checks", headers={"X-Api-Key": "dvreg-demo-key"}, timeout=10
        ).status_code == 200 and httpx.get(LAB_API + "/tradeins", params={"limit": 1}, timeout=10).status_code in (200, 401)
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the device mocks: restart it (R14)")


def land(resource: str, doc: dict) -> None:
    """Land one literal lab record as a sync's reader does, in a session of its own, committed."""
    with SessionLocal() as s:
        if resource == "tradeins":
            lab.land_tradein(s, doc)
        else:
            lab.land_dispute(s, doc)
        s.commit()


def canonical(key: str, model: str = "condition") -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def mapped(sid: str, resource: str, key: str, doc: dict) -> dict:
    facts = ADAPTERS[sid].map(Record(resource, key, doc))
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []
    assert {f.key for f in facts} <= {f"IMEI:{doc['imei']}"}
    return {f.field: f.value for f in facts}


def count(table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608 - fixed names


# ------------------------------------------------------------------ registration (DV-01)
def test_device_adapters_start_unregistered():
    for sid in IDS:
        assert ADAPTERS[sid].extra and ADAPTERS[sid].source_type == sid and ADAPTERS[sid].provisioned is False
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not set(IDS) & ids  # the Fabric's source count is the demo's
    assert run_sync("dvreg", "manual")["status"] == "skipped"
    assert run_sync("dvlab", "manual")["status"] == "skipped"
    assert [ADAPTERS[s].auth_kind for s in IDS] == ["api_key", "oauth"]


def test_canonical_models_hold_the_device_fields():
    asset, cond = MODEL_FIELDS["asset"], MODEL_FIELDS["condition"]
    assert asset["imei"].type == "text" and asset["sku_key"].type == "text"
    want = {
        "device_blacklist": "text", "device_lock": "text", "device_finance": "text", "registry_checked_at": "date",
        "imei_read": "text", "model_read": "text", "storage_read_gb": "number", "functional_fails": "list",
        "battery_health_pct": "number", "cosmetic_grade": "text", "photo_refs": "list", "wipe_certificate": "object",
        "parts_status": "text",
    }  # fmt: skip
    assert {k: cond[k].type for k in want} == want


def test_migration_0047_creates_the_eight_tables_with_their_indexes():
    with engine.connect() as conn:
        cols = {
            t: {r[0]: (r[1], r[2]) for r in conn.execute(text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = :t"), {"t": t})}
            for t in TABLES
        }  # fmt: skip
        idx = set(conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'device_%'")).scalars())
    assert all(cols[t] for t in TABLES)
    assert cols["device_tradein"]["sku"][0] == "jsonb" and cols["device_tradein"]["org_unit_id"][1] == "YES"
    assert cols["device_tradein"]["payout"][1] == "YES" and cols["device_tradein"]["bulk"][0] == "boolean"
    assert cols["device_price_point"]["week"][0] == "date" and cols["device_price_point"]["price"][0] == "numeric"
    assert cols["device_replacement_demand"]["reserved"][0] == "jsonb"
    assert {"ix_device_tradein_imei", "ix_device_tradein_batch", "ix_device_listing_channel_status", "ix_device_bid_lot"} <= idx


# ------------------------------------------------------------------ mapping (literal records)
def test_dv01_lab_records_map_to_facts_by_imei():
    t = mapped("dvlab", "tradeins", "TI-00428", TRADEIN)
    assert t == {"imei": SAMPLE, "sku_key": "iPhone 14|128"}
    d = mapped("dvlab", "diagnostics", SAMPLE, DIAGNOSTIC)
    assert d == {
        "imei_read": SAMPLE, "model_read": "iPhone 14", "storage_read_gb": 128, "functional_fails": [], "battery_health_pct": 84,
    }  # fmt: skip
    g = mapped("dvlab", "gradings", SAMPLE, GRADING)
    assert g["cosmetic_grade"] == "B" and g["photo_refs"] == GRADING["photoIds"]
    assert mapped("dvlab", "partsDeclarations", SAMPLE, PARTS) == {"parts_status": "genuine"}
    w = mapped("dvlab", "wipes", "WC-00428", WIPE)
    assert w["wipe_certificate"] == {
        "certificate_id": "WC-00428", "method": "Purge", "tool_version": "4.2.1", "verification": "pass", "operator": "OP-03",
        "at": "2026-09-20T16:00:00+00:00",
    }  # fmt: skip
    assert ADAPTERS["dvlab"].map(Record("repairQuotes", "RQ-00428", {"quoteId": "RQ-00428", "imei": SAMPLE})) == []


def test_dv02_registry_check_maps_to_condition_facts():
    assert mapped("dvreg", "checks", SAMPLE, CHECK) == {
        "device_blacklist": "reported_stolen", "device_lock": "on", "device_finance": "balance_owed",
        "registry_checked_at": "2026-09-20T11:00:00+00:00",
    }  # fmt: skip


# ------------------------------------------------------------------ landing rows (literal records)
def test_dv01_tradein_and_dispute_rows_land_once_and_keep_the_case():
    land("tradeins", TRADEIN)
    land("tradeins", TRADEIN)  # a sync twice is a sync once
    land("disputes", DISPUTE)
    land("disputes", DISPUTE)
    assert ADAPTERS["dvlab"].map(Record("tradeins", "TI-00428", TRADEIN))  # map makes facts only
    assert count("device_tradein") == 1 and count("device_dispute") == 1
    with SessionLocal() as s:
        row = device_tradeins.by_imei(s, SAMPLE)
        assert row is not None and row.trade_in_id == "TI-00428" and row.case_id is None
        assert row.sku["model"] == "iPhone 14" and row.quote["amount"] == 410 and row.partner == "P01" and row.bulk is False
        assert row.batch_id == "BATCH-0011" and row.org_unit_id is None and row.source == "dvlab"
        assert row.payout == {"amount": 410, "currency": "USD", "source": "dvlab"}
        assert [r.trade_in_id for r in device_tradeins.pending(s, None)] == ["TI-00428"]
        s.execute(text("UPDATE device_tradein SET case_id = 'RT-9001'"))
        s.commit()
    land("tradeins", TRADEIN | {"partner": "P03"})  # the lab changed a field
    with SessionLocal() as s:
        row = device_tradeins.by_imei(s, SAMPLE)
        assert row is not None and row.partner == "P03" and row.case_id == "RT-9001"  # the case stays
        assert device_tradeins.pending(s, None) == [] and device_tradeins.by_imei(s, "359990000009999") is None
    with engine.connect() as conn:
        dsp = conn.execute(text("SELECT reason, outcome FROM device_dispute WHERE id = 'DSP-0001'")).one()
    assert dsp == ("Screen graded before power-on", "open")


def test_pending_is_oldest_first_and_for_the_org_and_shared():
    other = TRADEIN | {"tradeInId": "TI-00001", "imei": "359990000000001", "receivedAt": "2026-09-01T10:00:00+00:00"}
    land("tradeins", TRADEIN)
    land("tradeins", other)
    with engine.begin() as conn:
        conn.execute(text("UPDATE device_tradein SET org_unit_id = 'Customer B' WHERE trade_in_id = 'TI-00428'"))
    with SessionLocal() as s:
        assert [r.trade_in_id for r in device_tradeins.pending(s, "Customer B")] == ["TI-00001", "TI-00428"]
        assert [r.trade_in_id for r in device_tradeins.pending(s, "Customer A")] == ["TI-00001"]


# ------------------------------------------------------------------ the device pack's evidence types
def test_device_pack_names_its_evidence_types_with_field_and_freshness():
    pack = load_pack("device")  # parses at load: the pack schema accepts it
    types = {e["id"]: e for e in pack.valuer.params["evidence_types"]}
    assert list(types) == [
        "quote",
        "blacklist_check",
        "diagnostics",
        "photo_grade",
        "wipe_certificate",
        "parts_declaration",
        "grading_second",
    ]
    for e in types.values():
        assert {"id", "label", "source", "field", "freshness_days"} == set(e)
        if e["field"].startswith("condition."):
            assert e["field"].split(".", 1)[1] in MODEL_FIELDS["condition"]  # the canonical field exists
    assert types["blacklist_check"]["field"] == "condition.device_blacklist" and types["blacklist_check"]["source"] == "dvreg"
    assert types["wipe_certificate"]["field"] == "condition.wipe_certificate"


# ------------------------------------------------------------------ the wipe webhook (no source-sim call)
def test_wipe_event_queues_a_delta_sync_of_dvlab():
    with SessionLocal() as s:
        from di.connectors import extra

        extra.ensure_registered(s, "dvlab")
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = 'dvlab'"))
        s.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = 'dvlab'"))
        s.commit()
    ev = {
        "specversion": "1.0", "id": "dvlab-wipe-1", "source": "/source-sim/dvlab", "type": "devicelab.wipe.created",
        "subject": "WCX-00001", "time": "2026-10-07T10:00:00Z", "data": {"imei": SAMPLE},
    }  # fmt: skip
    body = json.dumps(ev).encode()
    sig = "sha256=" + hmac.new(get_settings().webhook_secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    out = client.post("/api/webhooks/source-sim", content=body, headers={"x-sim-signature": sig}).json()
    assert (
        out["accepted"] is True and out["source_id"] == "dvlab" and out["type"] == "devicelab.wipe.created" and out["queued_job"]
    )
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = 'dvlab'")
        ).scalar_one()
    assert n == 1


# ------------------------------------------------------------------ a sync against the mocks
@needs_mock
def test_dvlab_sync_lands_tradeins_and_facts():
    r = call("source.reconnect", {"source_id": "dvlab"}, "developer")
    assert r["ok"], r
    out = run_sync("dvlab", "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    assert count("device_tradein") == 600 and count("device_dispute") == 50
    cond = canonical(f"IMEI:{SAMPLE}")["data"]
    assert cond["battery_health_pct"] == 84 and cond["cosmetic_grade"] == "B"
    assert cond["parts_status"] in ("genuine", "non_genuine", "unknown") and len(cond["photo_refs"]) == 3
    assert canonical(f"IMEI:{SAMPLE}", "asset")["data"] == {"imei": SAMPLE, "sku_key": "iPhone 14|128"}
    with SessionLocal() as s:
        row = device_tradeins.by_imei(s, SAMPLE)
        assert row is not None and row.quote["amount"] == 410 and row.partner == "P01"
        held = s.execute(text("SELECT count(*) FROM failed_record WHERE source_id = 'dvlab'")).scalar_one()
    assert held == 0
    again = run_sync("dvlab", "manual", full=True)
    assert again["status"] == "ok" and count("device_tradein") == 600  # idempotent
    with engine.connect() as conn:
        wiped = conn.execute(
            text("SELECT count(*) FROM canonical WHERE model = 'condition' AND key LIKE 'IMEI:%' AND data ? 'wipe_certificate'")
        ).scalar_one()
    assert wiped == 588  # 12 devices of BATCH-0007 have no certificate (test_device_wipe_sim.py resets the mock it changes)


@needs_mock
def test_a_dry_or_sample_run_of_dvlab_writes_no_tradein_row():
    r = call("source.reconnect", {"source_id": "dvlab"}, "developer")
    assert r["ok"], r
    with SessionLocal() as s:
        res = eng.run_graph(
            s,
            {"id": None, "name": "Test", "src": "dvlab"},
            eng.default_graph("dvlab"),
            trigger="Test",
            dry=True,
            full=True,
            sample=25,
        )
    assert res.status in ("success", "warning"), res.error
    assert 0 < res.rows <= 25
    assert count("device_tradein") == 0 and count("device_dispute") == 0


@needs_mock
def test_dvreg_sync_lands_registry_facts():
    r = call("source.reconnect", {"source_id": "dvreg"}, "developer")
    assert r["ok"], r
    out = run_sync("dvreg", "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with engine.connect() as conn:
        flagged = conn.execute(
            text(
                "SELECT count(*) FROM canonical WHERE model = 'condition' AND key LIKE 'IMEI:%' "
                "AND data->>'device_blacklist' IS NOT NULL AND data->>'device_blacklist' <> 'clear'"
            )
        ).scalar_one()
        locked = conn.execute(
            text("SELECT count(*) FROM canonical WHERE model = 'condition' AND key LIKE 'IMEI:%' AND data->>'device_lock' = 'on'")
        ).scalar_one()
    assert flagged == 15 and locked == 24
    assert canonical(f"IMEI:{SAMPLE}")["data"]["device_blacklist"] == "clear"
    assert {x["source_id"] for x in canonical(f"IMEI:{SAMPLE}")["provenance"]["device_blacklist"]} == {"dvreg"}
