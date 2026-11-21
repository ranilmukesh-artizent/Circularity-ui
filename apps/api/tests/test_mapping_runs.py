"""Plan 6 A4: the mapping a person edits is the one a sync applies (di/connectors/mapping.py).

- with no edits (no saved version, or the demo's own rows saved back) every demo adapter produces exactly the facts
  its code produces, on the raw records it has landed
- the rules (copy, upper, lower, number, int, date, utc, units, fx, code) and the dotted paths
- on SafetyCulture: a changed rule changes the provenance transform after a sync, an added row replaces the code's
  fact and changes the canonical value, Revert (a new version equal to v1) restores both; a row whose source field is
  missing fails the records it feeds with "missing field {src}" (counted, not fatal)
- source.update writes a version; mapping.preview shows a sample record mapped with a draft; mapping.revert
"""

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors import mapping
from di.connectors.base import Record
from di.connectors.mapping import MapRow, MissingField
from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine
from tests import starting
from tests.helpers import call, client, h

SIM = get_settings().source_sim_url
SID = "insp"


def _records(s, sid: str, n: int = 150) -> list[Record]:
    rows = s.execute(
        text("SELECT resource, ext_id, payload FROM raw_record WHERE source_id = :s ORDER BY resource, ext_id LIMIT :n"),
        {"s": sid, "n": n},
    ).all()
    return [Record(r.resource, r.ext_id, r.payload) for r in rows]


# ---------------------------------------------------------------- no edits: the same facts
@pytest.mark.parametrize("sid", sorted(ADAPTERS))
def test_no_edits_same_facts(sid):
    """The demo's own rows (all `code`) over the adapter's facts change nothing, on every landed record."""
    stored = mapping.rows_from_maps(sid, mapping.starting_maps(sid))
    assert all(r["rule"] == mapping.CODE for r in stored)
    rows, base = mapping.to_rows(stored), mapping.builtin(sid)
    with SessionLocal() as s:
        recs = _records(s, sid)
        assert mapping.mapper(s, sid, True) is None or mapping.active_version(s, sid) is not None
    a = ADAPTERS[sid]
    for rec in recs:
        try:
            facts = a.map(rec)
        except Exception:  # noqa: BLE001 - a record the code cannot map fails the same way with or without rows
            facts = None
        if facts is not None:
            assert mapping.overlay(facts, rec, rows, base) == facts, (sid, rec.resource, rec.ext_id)


# ---------------------------------------------------------------- rules (pure)
def test_rules():
    ar = mapping.apply_rule
    assert ar("copy", "x") == "x" and ar("upper", "Grade b") == "GRADE B" and ar("lower", "AB") == "ab"
    assert ar("number", "1,800.00 USD") == 1800 and ar("number", "12.5") == 12.5 and ar("int", "12.6") == 13
    assert ar("utc", "2026-10-05T10:11:00-04:00") == "2026-10-05T14:11:00Z"
    assert ar("date", "2026-10-05T23:30:00-04:00") == "2026-10-06" and ar("date", "2026-10-05") == "2026-10-05"
    assert ar("units:kg>t", 1500) == 1.5 and ar("units:c>f", 100) == 212 and ar("units:lb>kg", "10") == 4.535924
    assert ar("fx:INR", "₹10,02,000.00") == 12000.0 and ar("fx:EUR", 92) == 100.0
    assert ar("code:grade", "Grade B") == "B" and ar("code:bool", "Yes") is True
    p = mapping.parse_rule
    assert p("Upper case") == "upper" and p("fx:inr") == "fx:INR" and p("units: KG > t") == "units:kg>t"
    assert p("Timestamp to UTC") == "utc" and p("Integer") == "int" and p("Grade table v3") is None
    assert p("units:kg>m") is None and p("code:nope") is None
    assert mapping.rule_label("fx:INR") == "Currency at 83.5 INR/USD" and mapping.rule_label("upper") == "Upper case"


def test_rows_paths_and_overlay():
    rec = Record("audits", "a1", {"asset_id": "X-1", "grade_text": "Grade B", "audit_data": {"status": "done"},
                                 "items": [{"label": "Seal"}], "EKPO-NETPR": "5"})  # fmt: skip
    assert mapping.lookup(rec.payload, "audit_data.status") == "done" and mapping.lookup(rec.payload, "items.0.label") == "Seal"
    assert mapping.lookup(rec.payload, "EKPO-NETPR") == "5"
    code = [store.Fact("condition", "X-1", "grade", "B", "grade_text", "Grade B", "Grade table v3"),
            store.Fact("condition", "X-1", "inspector", "Ann", None, None, "Pass-through")]  # fmt: skip
    base = {("condition", "grade"), ("condition", "photo_count")}
    # edited: replaces the code's fact; a removed builtin row drops it; facts the tab does not show stay
    got = mapping.overlay(code, rec, [MapRow("grade_text", "condition", "grade", "upper")], base)
    assert [(f.field, f.value, f.transform) for f in got] == [
        ("inspector", "Ann", "Pass-through"),
        ("grade", "GRADE B", "Upper case"),
    ]
    assert [f.field for f in mapping.overlay(code, rec, [], base)] == ["inspector"]
    # added: a new field from the record; absent in this record: skipped
    got = mapping.overlay(code, rec, [MapRow("grade_text", "condition", "grade", "code"),
                                      MapRow("audit_data.status", "condition", "inspection_status", "upper"),
                                      MapRow("nope", "condition", "checklist", "copy")], base)  # fmt: skip
    assert [(f.field, f.value) for f in got] == [("grade", "B"), ("inspector", "Ann"), ("inspection_status", "DONE")]
    # an edited row whose source field is missing where the code produced that field fails the record
    with pytest.raises(MissingField, match="missing field grade_txt"):
        mapping.overlay(code, rec, [MapRow("grade_txt", "condition", "grade", "code:grade")], base)
    # configured sources: rows alone; the key row gives the key
    rows = [MapRow("asset_id", "asset", "key", "copy"), MapRow("grade_text", "condition", "grade", "code:grade"),
            MapRow("asset_id", "condition", "key", "copy")]  # fmt: skip
    got = mapping.apply_rows(rows, rec)
    assert [(f.model, f.key, f.field, f.value) for f in got] == [("condition", "X-1", "grade", "B")]
    with pytest.raises(MissingField, match="missing field gone"):
        mapping.apply_rows([MapRow("gone", "asset", "status", "copy")], rec)
    assert mapping.apply_rows([MapRow("gone", "asset", "status", "copy", "other")], rec) == []


def test_rows_from_maps_validation():
    start = mapping.starting_maps(SID)
    edited = [list(m) for m in start]
    edited[0][4] = "lower"
    rows = mapping.rows_from_maps(SID, [*edited, ["audit_data.status", "", "condition.inspection_status", "", "anything"]])
    assert [r["rule"] for r in rows] == ["lower", "code", "code", "copy"]
    with pytest.raises(ValueError, match="no canonical model widget"):
        mapping.rows_from_maps(SID, [["a", "", "widget.x", "", "copy"]])
    with pytest.raises(ValueError, match="Row 1"):
        mapping.rows_from_maps(SID, [["a", "", "nofield", "", "copy"]])


# ---------------------------------------------------------------- SafetyCulture end to end
def _sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


@pytest.fixture(scope="module")
def insp():
    starting.reset()
    _sim("DELETE", "/_sim/faults", params={"system": SID})
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = :i"), {"i": SID})
        s.commit()
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
    assert run_sync(SID, "manual", full=True)["status"] == "ok"  # the code's facts again
    starting.reset()


def _key(s) -> str:
    """An asset whose inspection status only SafetyCulture gives."""
    return s.execute(
        text(
            "SELECT key FROM provenance p WHERE source_id = 'insp' AND model = 'condition' AND field = 'inspection_status' "
            "AND NOT EXISTS (SELECT 1 FROM provenance q WHERE q.model = p.model AND q.key = p.key AND q.field = p.field "
            "AND q.source_id <> 'insp') ORDER BY key LIMIT 1"
        )
    ).scalar_one()


def _prov(s, key: str, field: str) -> dict:
    rec = store.get(s, "condition", key)
    return rec["data"].get(field), next(p for p in rec["provenance"][field] if p["source_id"] == SID)


def _save(maps: list[list[str]]) -> dict:
    r = call(
        "source.update",
        {"mode": "edit", "id": SID, "d": _draft(), "ops": {"read": _cur()["read"], "write": _cur()["write"]}, "maps": maps},
        "developer",
    )
    assert r["ok"], r
    return r["output"]


def _cur() -> dict:
    return client.get(f"/api/screens/integration/sources/{SID}", headers=h("developer")).json()["source"]


def _draft() -> dict:
    c = _cur()
    return {k: c.get(k) for k in ("name", "vendor", "ver", "env", "url", "method", "cfg", "auth", "owner", "interval")} | {
        "type": c["type"]
    }


def test_edit_runs_then_revert(insp):
    assert run_sync(SID, "manual", full=True)["status"] == "ok"
    with SessionLocal() as s:
        key = _key(s)
        status0, _ = _prov(s, key, "inspection_status")
        g0 = _prov(s, key, "grade")[1]
    assert g0["transform"] == "Grade table v3"
    start = mapping.starting_maps(SID)
    edited = [list(m) for m in start]
    edited[0][4] = "code:grade"  # the grade row: same values, another rule
    edited.append(["audit_data.status", "", "condition.inspection_status", "", "upper"])
    out = _save(edited)
    assert "field mapping (4 rows)" in out["changes"]
    with SessionLocal() as s:
        assert [v["version"] for v in mapping.versions(s, SID)] == [2, 1]
    run = run_sync(SID, "manual", full=True)
    assert run["status"] == "ok" and run["records_failed"] == 0, run
    with SessionLocal() as s:
        status1, p1 = _prov(s, key, "inspection_status")
        _, g1 = _prov(s, key, "grade")
    assert status1 == status0.upper() != status0 and p1["transform"] == "Upper case"
    assert p1["source_field"] == "audit_data.status"
    assert g1["transform"] == "Code table grade" and g1["value"] == g0["value"]
    # the preview shows the draft on a sample record, without saving
    pv = call("mapping.preview", {"source_id": SID, "maps": start}, "developer")
    assert pv["ok"], pv
    assert pv["output"]["version"] == 2 and pv["output"]["record"]["ext_id"]
    assert all(f["transform"] != "Upper case" for f in pv["output"]["facts"])
    # Revert: a new version equal to v1
    rv = call("mapping.revert", {"source_id": SID, "version": 1}, "developer")
    assert rv["ok"], rv
    assert rv["output"]["version"] == 3
    with SessionLocal() as s:
        assert mapping.active_rows(s, SID) == mapping.to_rows(mapping.rows_from_maps(SID, start))
    assert run_sync(SID, "manual", full=True)["status"] == "ok"
    with SessionLocal() as s:
        status2, p2 = _prov(s, key, "inspection_status")
        _, g2 = _prov(s, key, "grade")
    assert status2 == status0 and p2["transform"] == "Pass-through" and g2["transform"] == "Grade table v3"


def test_missing_field_fails_the_record(insp):
    edited = [list(m) for m in mapping.starting_maps(SID)]
    edited[0][0], edited[0][4] = "grade_txt", "code:grade"
    _save(edited)
    run = run_sync(SID, "manual", full=True)
    assert run["status"] == "partial" and run["records_failed"] > 0
    assert "missing field grade_txt" in run["error"]
    pv = call("mapping.preview", {"source_id": SID}, "developer")["output"]
    assert pv["error"] is None or "missing field grade_txt" in pv["error"]
    with engine.begin() as c:
        c.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})


def test_preview_and_revert_refusals(insp):
    assert not call("mapping.preview", {"source_id": SID}, "planner.a")["ok"]
    assert not call("mapping.revert", {"source_id": SID, "version": 1}, "engineer")["ok"]
    r = call("mapping.revert", {"source_id": SID, "version": 99}, "developer")
    assert not r["ok"] and r["error"]["code"] == "not_found"
    bad = call("mapping.preview", {"source_id": SID, "maps": [["a", "", "widget.x", "", "copy"]]}, "developer")
    assert not bad["ok"] and bad["error"]["code"] == "validation_error"
