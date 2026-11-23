"""Plan 6 B1: canonical schema checks and failed records.

Every fact a sync maps is checked against its canonical model (di/services/canonical/schema.py MODEL_FIELDS: canonical.json
plus the fields the demo's connectors write, di/services/canonical/fields.py). A fact with an unknown field or a value of the
wrong type is held in `failed_record` with the reason and counted in the run's records_failed; the record's other
facts are stored. The 21 demo sources hold nothing on a full sync, so their canonical data stays the same.

Needs source-sim running; runs full syncs of the demo sources (the worker is stopped by scripts/dev/api-test.sh).
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core import golden
from di.core.db import SessionLocal, engine
from di.services.canonical import failed, store
from di.services.canonical.schema import MODEL_FIELDS, MODELS, bom_key, check_fact, part_key, split_facts
from di.services.canonical.store import Fact


# ---------------------------------------------------------------- the schema
def test_model_fields_cover_canonical_json():
    for m in golden.load("canonical")["models"]:
        ns = {"Asset & component": "asset", "Condition & eligibility": "condition", "Demand opportunity": "demand"}.get(m["n"])
        if ns:
            for f in m["fields"]:
                assert f.split("[")[0].split("(")[0] in MODEL_FIELDS[ns], (ns, f)
    assert MODEL_FIELDS["asset"]["asset_id"].required and MODEL_FIELDS["demand"]["need_by"].type == "date"
    assert MODEL_FIELDS["demand"]["purchase_baseline"].type == "number" and MODEL_FIELDS["asset"]["components"].type == "list"


def test_check_fact():
    assert check_fact(Fact("asset", "MTR-1", "owner_tenant", "Customer A")) is None
    assert check_fact(Fact("demand", "PO-1", "purchase_baseline", Decimal("12000.00"))) is None
    assert check_fact(Fact("condition", "MTR-1", "certificates[0].expires", "2027-03-01")) is None  # nested: top field
    assert check_fact(Fact("outcome", "APR-1", "line.DECOM", {"act": 1.0})) is None
    assert check_fact(Fact("asset", "MTR-1", "lease_term_months", None)) is None  # empty values are allowed
    assert check_fact(Fact("asset", "MTR-1", "colour", "red")) == "Unknown field asset.colour"
    assert check_fact(Fact("condition", "MTR-1", "photo_count", "twelve")).startswith("condition.photo_count must be a number")
    assert check_fact(Fact("condition", "MTR-1", "photo_count", True)).startswith("condition.photo_count must be a number")
    assert check_fact(Fact("demand", "SO-1", "need_by", "31/12/2026")).startswith("demand.need_by must be a date")
    assert check_fact(Fact("asset", "MTR-1", "asset_id", "")) == "asset.asset_id is required"
    ok, bad = split_facts([Fact("asset", "A", "qty", 1), Fact("asset", "A", "qty", "1")])
    assert len(ok) == 1 and bad[0][0].value == "1" and "must be a number" in bad[0][1]


def test_iot_facts_fit_the_schema():
    """AWS IoT starts not provisioned (B5c), so a full sync does not read it: its mapping is checked on a shadow."""
    rec = Record(
        "shadows",
        "cm-mtr-2041",
        {
            "thing": {"thingName": "cm-mtr-2041", "attributes": {"assetTag": "MTR-2041"}},
            "shadow": {
                "state": {
                    "reported": {
                        "operatingHours": 41230.5, "dutyCyclePct": 96.4, "vibrationMmS": 2.8, "vibrationZone": "B",
                        "bearingTempC": 71.5, "sampleAt": 1791100000000,
                        "events": [{"type": "vibration", "ts": 1791000000000, "value": 7.2, "threshold": 7.1, "unit": "mm/s"}],
                    }
                }
            },
        },
    )  # fmt: skip
    facts = ADAPTERS["iot"].map(rec)
    assert len(facts) >= 8
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


# ---------------------------------------------------------------- PLM parts and BOM lines (plan 8, MVP-9.1)
def test_part_keys_per_org():
    """The same part number in two org units never collides (edge case 4); each key keeps its own revision (5)."""
    assert {"part", "bom"} <= set(MODELS)
    assert part_key("Customer A", "PN-100") == "Customer A:PN-100"
    assert part_key(None, "PN-100") == part_key("", "PN-100") == "shared:PN-100"
    assert part_key("Customer A", "PN-100") != part_key("Customer B", "PN-100")
    assert {f: s.type for f, s in MODEL_FIELDS["part"].items()} == {
        "number": "text", "revision": "text", "state": "text", "name": "text", "unit_cost": "number", "org_unit_id": "text",
    }  # fmt: skip
    assert MODEL_FIELDS["part"]["number"].required
    assert check_fact(Fact("part", part_key("Customer A", "PN-100"), "unit_cost", "cheap")).startswith(
        "part.unit_cost must be a number"
    )
    with SessionLocal() as s:
        a, b = part_key("Customer A", "PN-T91"), part_key("Customer B", "PN-T91")
        store.apply(s, "manual", [
            Fact("part", a, "number", "PN-T91"), Fact("part", a, "revision", "B.2"), Fact("part", a, "org_unit_id", "Customer A"),
            Fact("part", b, "number", "PN-T91"), Fact("part", b, "revision", "C.1"), Fact("part", b, "org_unit_id", "Customer B"),
        ])  # fmt: skip
        q = "SELECT key, data FROM canonical WHERE model = 'part' AND key = ANY(:k)"
        rows = dict(s.execute(text(q), {"k": [a, b]}).all())
        assert {k: (d["revision"], d["org_unit_id"]) for k, d in rows.items()} == {
            a: ("B.2", "Customer A"), b: ("C.1", "Customer B"),
        }  # fmt: skip
        q = "SELECT count(*) FROM conflict WHERE model = 'part' AND key = ANY(:k)"
        assert s.execute(text(q), {"k": [a, b]}).scalar() == 0
        s.rollback()


def test_bom_line_fields():
    assert {f: s.type for f, s in MODEL_FIELDS["bom"].items()} == {
        "parent": "text", "child": "text", "qty": "number", "parent_revision": "text", "harvestable": "bool",
    }  # fmt: skip
    assert MODEL_FIELDS["bom"]["parent"].required and MODEL_FIELDS["bom"]["child"].required
    k1, k2 = bom_key("Customer A", "ASM-1", "A.1", "PN-100"), bom_key("Customer A", "ASM-1", "B.1", "PN-100")
    assert k1 == "Customer A:ASM-1@A.1>PN-100" and k1 != k2  # a line per parent revision (as built vs released)
    assert bom_key(None, "ASM-1", "A.1", "PN-100").startswith("shared:ASM-1@")
    line = [
        Fact("bom", k1, "parent", "ASM-1"), Fact("bom", k1, "child", "PN-100"), Fact("bom", k1, "qty", 2),
        Fact("bom", k1, "parent_revision", "A.1"), Fact("bom", k1, "harvestable", True),
    ]  # fmt: skip
    assert [check_fact(f) for f in line] == [None] * 5
    assert check_fact(Fact("bom", k1, "harvestable", "yes")).startswith("bom.harvestable must be true or false")
    assert check_fact(Fact("bom", k1, "qty", "2")).startswith("bom.qty must be a number")
    assert check_fact(Fact("bom", k1, "child", "")) == "bom.child is required"


# ---------------------------------------------------------------- holding
def test_hold_writes_a_failed_record():
    with SessionLocal() as s:
        fid = failed.hold(
            s, run_kind="import", run_id="IMP-T", source_id="manual", reason="qty must be a positive whole number",
            field="asset.qty", rule="row", value="-1", payload={"asset_id": "MTR-9001"},
        )  # fmt: skip
        row = s.execute(text("SELECT * FROM failed_record WHERE id = :i"), {"i": fid}).mappings().one()
        assert (row["status"], row["value"], row["payload"], row["run_id"]) == ("held", "-1", {"asset_id": "MTR-9001"}, "IMP-T")
        assert [r["id"] for r in failed.held(s, run_kind="import", run_id="IMP-T")] == [fid]
        with pytest.raises(ValueError, match="unknown run kind"):
            failed.hold(s, run_kind="nightly", reason="x")
        s.rollback()


def test_sync_holds_facts_that_do_not_fit(monkeypatch):
    adapter = ADAPTERS["insp"]
    real = adapter.map
    seen: list[str] = []

    def bad_map(rec):
        facts = real(rec)
        if facts and not seen:
            key = facts[0].key
            seen.append(key)
            facts = [*facts, Fact("condition", key, "colour", "red"), Fact("condition", key, "photo_count", "twelve")]
        return facts

    monkeypatch.setattr(adapter, "map", bad_map)
    try:
        out = run_sync("insp", "manual", full=True)
        assert seen and out["status"] == "partial" and out["records_failed"] == 1, out
        with SessionLocal() as s:
            rows = failed.held(s, run_kind="sync", run_id=out["run_id"])
            assert sorted((r["field"], r["rule"], r["value"]) for r in rows) == [
                ("condition.colour", "schema", "red"),
                ("condition.photo_count", "schema", "twelve"),
            ]
            assert {r["reason"] for r in rows} >= {"Unknown field condition.colour"}
            assert all(r["source_id"] == "insp" and r["step"] == "canonical" and r["payload"] for r in rows)
            data = s.execute(text("SELECT data FROM canonical WHERE model = 'condition' AND key = :k"), {"k": seen[0]}).scalar()
            assert "colour" not in data and data.get("photo_count") != "twelve"  # the record's other facts are stored
            run = s.execute(text("SELECT records_failed FROM sync_run WHERE id = :i"), {"i": out["run_id"]}).scalar_one()
            assert run == 1
    finally:
        monkeypatch.undo()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM failed_record WHERE run_kind = 'sync' AND source_id = 'insp'"))
        assert run_sync("insp", "manual", full=True)["status"] == "ok"  # its last run is clean again


def test_demo_sources_hold_nothing():
    """The schema accepts every fact the demo sources send, so the check stores exactly what was stored before it:
    their canonical data cannot change. (A digest of the canonical table before and after is no test of that: a
    full sync can legitimately fill it further, e.g. Aras reads the configuration items Teamcenter wrote.)"""
    runs = {}
    for sid in sorted(ADAPTERS):
        out = run_sync(sid, "manual", full=True)
        if out["status"] == "failed":  # source-sim did not answer in time (a slow mock under load): once more
            out = run_sync(sid, "manual", full=True)
        if out["status"] == "skipped":  # AWS IoT starts not provisioned (test_iot_facts_fit_the_schema)
            continue
        runs[sid] = out
    assert len(runs) >= 20, sorted(runs)
    assert {
        sid: (o["status"], o["records_failed"], o["error"])
        for sid, o in runs.items()
        if o["records_failed"] or o["status"] != "ok"
    } == {}
    with SessionLocal() as s:
        n = s.execute(
            text("SELECT count(*) FROM failed_record WHERE run_kind = 'sync' AND run_id = ANY(:ids)"),
            {"ids": [str(o["run_id"]) for o in runs.values()]},
        ).scalar_one()
    assert n == 0
