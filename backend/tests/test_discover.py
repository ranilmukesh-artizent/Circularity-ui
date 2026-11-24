"""Plan 6 B5: Source Tables from what the source really sends (di/connectors/discover.py).

- a source created in the Connection Fabric shows one table per resource it has landed, columns from the payload keys
  with an inferred type, the id field first, and a suggested foreign key where ≥ 90 % of a column's values are keys
  of another table
- a table a person adds or edits (tables.update) is kept and marked manual; a suggested key a person removes is not
  suggested again; the other tables follow what the source sends
- the demo systems' seeded table models stay exactly as the demo seeds them
"""

import json

from sqlalchemy import text

from di.connectors import discover
from di.core import golden
from di.core.db import SessionLocal, engine
from tests import starting
from tests.helpers import call, client, h

SID = "t3disc"
G = golden.load("screens/integration")


def setup_module():
    starting.reset()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner) "
                "VALUES (:i, 'Sandbox HR', 'crm', 'live', 30, '{}', 'Integration Engineering') ON CONFLICT (id) DO NOTHING"
            ),
            {"i": SID},
        )
        rows = [("departments", f"D{n}", {"dept_id": f"D{n}", "name": f"Dept {n}", "budget": 1000 * n}) for n in range(1, 4)]
        rows += [
            ("workers", f"W{n}", {"worker_id": f"W{n}", "dept_id": f"D{1 + n % 3}", "hired": "2025-03-0" + str(1 + n % 9),
                                  "active": n % 2 == 0, "updated_at": "2026-10-01T09:00:00Z", "tags": ["a"]})
            for n in range(1, 21)
        ]  # fmt: skip
        for res, ext, p in rows:
            c.execute(
                text(
                    "INSERT INTO raw_record (source_id, resource, ext_id, payload, fetched_at) "
                    "VALUES (:s, :r, :e, CAST(:p AS jsonb), now()) ON CONFLICT (source_id, resource, ext_id) DO NOTHING"
                ),
                {"s": SID, "r": res, "e": ext, "p": json.dumps(p)},
            )


def teardown_module():
    starting.reset()  # removes the source made here with its raw records, and the table models collection


def _model() -> dict:
    r = client.get("/api/screens/integration/tables", params={"source": SID}, headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()["models"][SID]


def test_discovered_tables():
    with SessionLocal() as s:
        tables = discover.discover(s, SID)
    assert [t["n"] for t in tables] == ["departments", "workers"]
    m = _model()
    w = next(t for t in m["t"] if t["n"] == "workers")
    assert w["cols"][0] == ["worker_id", "Record key · text"] and w["rows"] == "20"
    assert dict(w["cols"]) == {
        "worker_id": "Record key · text", "dept_id": "text", "hired": "date", "active": "bool",
        "updated_at": "datetime", "tags": "list",
    }  # fmt: skip
    d = next(t for t in m["t"] if t["n"] == "departments")
    assert d["cols"][0] == ["dept_id", "Record key · text"] and dict(d["cols"])["budget"] == "number"
    assert [f[:2] for f in m["fk"]] == [["workers.dept_id", "departments.dept_id"]]
    assert m["fk"][0][2].startswith("Suggested: 100%")


def test_people_changes_are_kept():
    r = call("tables.update", {"src": SID, "op": "add", "table": {"n": "Notes", "cols": ["note_id", "text"]}}, "developer")
    assert r["ok"], r
    r = call(
        "tables.update", {"src": SID, "op": "edit", "name": "departments", "table": {"cols": ["dept_id", "name"]}}, "developer"
    )
    assert r["ok"], r
    r = call("tables.update", {"src": SID, "op": "fkDel", "index": 0}, "developer")
    assert r["ok"], r
    with engine.begin() as c:  # the source sends a new field on departments and workers
        c.execute(text('UPDATE raw_record SET payload = payload || \'{"region": "EU"}\'::jsonb WHERE source_id = :s'), {"s": SID})
    m = _model()
    by = {t["n"]: t for t in m["t"]}
    assert by["Notes"]["manual"] and [c[0] for c in by["Notes"]["cols"]] == ["note_id", "text"]
    assert by["departments"]["manual"] and [c[0] for c in by["departments"]["cols"]] == ["dept_id", "name"]
    assert "region" in [c[0] for c in by["workers"]["cols"]] and not by["workers"].get("manual")
    assert m["fk"] == []  # the removed suggestion stays removed


def test_demo_models_unchanged():
    got = client.get("/api/screens/integration/tables", headers=h("developer")).json()["models"]
    for k, m in G["table_models"].items():
        assert got[k] == m, k
    with SessionLocal() as s:
        assert discover.materialize(s, "crm") is None and SID in discover.configured_sources(s)
        assert not set(discover.configured_sources(s)) & discover.demo_ids()


def test_discovery_samples_500():  # G6-12 (P9-0.14): the newest 500 records are the sample
    sid = "t3disc500"
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner) "
                "VALUES (:i, 'Sandbox HR', 'crm', 'live', 30, '{}', 'Integration Engineering') ON CONFLICT (id) DO NOTHING"
            ),
            {"i": sid},
        )
        for n in range(520):  # n = 0 is the newest; the oldest 20 are the only ones with "old_only"
            p = {"rec_id": f"R{n}", "common": n} | ({"old_only": 1} if n >= 500 else {}) | ({"new_only": 1} if n < 5 else {})
            c.execute(
                text(
                    "INSERT INTO raw_record (source_id, resource, ext_id, payload, fetched_at) VALUES "
                    "(:s, 'items', :e, CAST(:p AS jsonb), now() - make_interval(secs => :age)) "
                    "ON CONFLICT (source_id, resource, ext_id) DO NOTHING"
                ),
                {"s": sid, "e": f"R{n}", "p": json.dumps(p), "age": n + 1},
            )
    try:
        with SessionLocal() as s:
            tables = discover.discover(s, sid)
        cols = {col[0] for t in tables for col in t["cols"]}
        assert discover.SAMPLE == 500
        assert "new_only" in cols and "common" in cols and "old_only" not in cols
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM raw_record WHERE source_id = :s"), {"s": sid})
            c.execute(text("DELETE FROM source_system WHERE id = :s"), {"s": sid})
