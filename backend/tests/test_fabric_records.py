"""Connection Fabric records: Source Tables (tables.update), Manual Import (import.commit) and the Conflict Queue
(conflict.resolve, conflict.escalate), with the demo's rules and texts (index.html, defAction('tables.update' ...),
ACT.tgAddOk ..., defAction('import.commit' ...), defAction('conflict.resolve' ...))."""

import pytest
from sqlalchemy import text

from di.connectors import manual
from di.core import state
from di.core.db import SessionLocal, engine
from di.services.canonical import failed, store
from di.services.canonical.store import Fact
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()
    with SessionLocal() as s:
        manual.remove(s)
        s.commit()


def teardown_module():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM conflict WHERE key LIKE 'FRT-%'"))
    with SessionLocal() as s:  # the imports' canonical data, raw records and held rows (plan 6 B3)
        manual.remove(s)
        s.commit()
    starting.reset()


def tables(src: str = "erp") -> dict:
    r = client.get("/api/screens/integration/tables", params={"source": src}, headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()["models"][src]


def events() -> list[dict]:
    return client.get("/api/screens/integration/events", headers=h("admin")).json()["events"]


# ---------------------------------------------------------------- tables.update
def test_tables_add_edit_delete_and_links_persist():
    before = tables()
    n0, f0 = len(before["t"]), len(before["fk"])
    kpis0 = client.get("/api/screens/integration/tables", headers=h("developer")).json()["counts"]
    add = {
        "src": "erp",
        "op": "add",
        "table": {
            "n": "T001L",
            "cl": "inv",
            "desc": "Storage locations per plant.",
            "cols": [["LGORT", ""], ["WERKS", ""]],
            "rows": "—",
            "x": 24,
            "y": 900,
        },
    }
    r = call("tables.update", add, "developer")
    assert r["ok"] and r["output"] == {"op": "add", "name": "T001L"}, r
    m = tables()
    assert len(m["t"]) == n0 + 1 and m["t"][-1]["n"] == "T001L" and m["t"][-1]["cols"] == [["LGORT", ""], ["WERKS", ""]]
    kpis = client.get("/api/screens/integration/tables", headers=h("developer")).json()["counts"]
    assert kpis["tables"] == kpis0["tables"] + 1
    # the same name again (any case) is refused with the demo's text
    again = call("tables.update", add | {"table": add["table"] | {"n": "t001l"}}, "developer")
    assert again["error"] == {"code": "duplicate", "message": "t001l is already in this model"}
    bad = call("tables.update", add | {"table": add["table"] | {"n": "1bad"}}, "developer")
    assert bad["error"]["message"] == "Enter a table name: letters, numbers and underscores."
    # link it, then edit away the linked column: the link goes with it
    r = call("tables.update", {"src": "erp", "op": "fkAdd", "fk": ["T001L.WERKS", "MARC.WERKS", ""]}, "developer")
    assert r["ok"] and r["output"] == {"op": "fkAdd", "from": "T001L.WERKS", "to": "MARC.WERKS"}
    assert tables()["fk"][-1] == ["T001L.WERKS", "MARC.WERKS", "Foreign key link"]
    dup = call("tables.update", {"src": "erp", "op": "fkAdd", "fk": ["T001L.WERKS", "MARC.WERKS", "x"]}, "developer")
    assert dup["error"] == {"code": "duplicate", "message": "That foreign key already exists"}
    r = call(
        "tables.update",
        {"src": "erp", "op": "edit", "name": "T001L", "table": {"cols": ["LGORT", "LGOBE"], "desc": "", "cl": "inv"}},
        "developer",
    )
    assert r["ok"]
    m = tables()
    t = next(x for x in m["t"] if x["n"] == "T001L")
    assert t["cols"] == [["LGORT", ""], ["LGOBE", ""]] and t["desc"] == "Storage locations per plant."  # empty desc keeps the old
    assert len(m["fk"]) == f0
    for cols, msg in (
        (["A", "a"], "Column names must be unique."),
        (["A-B"], "Use letters, numbers and underscores only."),
        ([], "Add at least one column."),
    ):
        e = call(
            "tables.update",
            {"src": "erp", "op": "edit", "name": "T001L", "table": {"cols": cols, "desc": "", "cl": "inv"}},
            "developer",
        )
        assert e["error"]["message"] == msg
    # delete a table with links: they go too, and the output carries what restore needs
    marc = sum(1 for f in m["fk"] if "MARC" in (f[0].split(".")[0], f[1].split(".")[0]))
    r = call("tables.update", {"src": "erp", "op": "delete", "name": "MARC"}, "developer")
    assert r["ok"] and r["output"]["fks"] == marc and r["output"]["name"] == "MARC"
    gone = tables()
    assert all(x["n"] != "MARC" for x in gone["t"]) and len(gone["fk"]) == f0 - marc
    r = call(
        "tables.update",
        {"src": "erp", "op": "restore", "table": r["output"]["table"], "index": r["output"]["index"], "fk": r["output"]["gone"]},
        "developer",
    )
    assert r["ok"]
    back = tables()
    assert [x["n"] for x in back["t"]] == [x["n"] for x in m["t"]] and len(back["fk"]) == f0
    # remove a link by index, put it back where it was
    first = back["fk"][0]
    r = call("tables.update", {"src": "erp", "op": "fkDel", "index": 0}, "developer")
    assert r["output"] == {"op": "fkDel", "from": first[0], "to": first[1], "fk": first, "index": 0}
    assert (
        call("tables.update", {"src": "erp", "op": "fkDel", "index": 999}, "developer")["error"]["message"]
        == "No such foreign key."
    )
    call("tables.update", {"src": "erp", "op": "fkAdd", "fk": first, "index": 0}, "developer")
    assert tables()["fk"][0] == first


def test_tables_layout_is_kept():
    m = tables("wms")
    name = m["t"][0]["n"]
    r = call("tables.update", {"src": "wms", "op": "layout", "table": {"pos": {name: [400, 312], "NOPE": [1, 1]}}}, "developer")
    assert r["ok"] and r["output"] == {"op": "layout", "moved": 1}
    t = tables("wms")["t"][0]
    assert (t["x"], t["y"]) == (400, 312)


def test_tables_refusals():
    assert call("tables.update", {"src": "nope", "op": "add", "table": {}}, "developer")["error"] == {
        "code": "not_found",
        "message": "No table model for nope.",
    }
    assert call("tables.update", {"src": "erp", "op": "zap"}, "developer")["error"]["message"] == "Unknown table operation zap."
    assert (
        call("tables.update", {"src": "erp", "op": "delete", "name": "NOPE"}, "developer")["error"]["message"] == "No table NOPE."
    )
    r = client.post("/api/actions/tables.update", json={"src": "erp", "op": "delete", "name": "MARA"}, headers=h("planner.a"))
    assert r.status_code == 403


# ---------------------------------------------------------------- import.commit
ROWS = [
    {
        "asset_id": "MTR-3101",
        "qty": "1",
        "grade": "B",
        "location": "Warehouse 1",
        "owner": "Customer A",
        "received": "2026-10-05",
    },
    {
        "asset_id": "DRL-2090",
        "qty": "6",
        "grade": "B",
        "location": "Warehouse 1",
        "owner": "Customer C",
        "received": "2026-10-06",
    },
]


def test_import_commit_records_the_rows_once():
    r = call("import.commit", {"ok": 2, "err": 1, "hash": "abc123def", "rows": ROWS}, "developer")
    assert r["ok"] and r["output"]["ok"] == 2, r
    with SessionLocal() as s:
        imps = state.items(s, "imports")
    assert (
        len(imps) == 1 and imps[0]["ok"] == 2 and imps[0]["err"] == 1 and imps[0]["tag"] == "manual" and imps[0]["rows"] == ROWS
    )
    e = events()[0]
    assert e["type"] == "import.evaluated" and e["key"] == "imp-abc123" and e["dest"] == "Controlled CSV import"
    assert e["note"] == "2 rows loaded as manual evaluation data; no outbound instruction possible"
    dup = call("import.commit", {"ok": 2, "err": 1, "hash": "abc123def", "rows": ROWS}, "developer")
    assert dup["error"] == {"code": "duplicate", "message": "These rows were already loaded. Nothing was created twice."}


def test_import_commit_refusals():
    assert call("import.commit", {"ok": 0, "err": 3, "hash": "zzz"}, "developer")["error"] == {
        "code": "conflict",
        "message": "No valid rows to load.",
    }
    bad = call("import.commit", {"ok": 1, "err": 0, "hash": "bad1", "rows": [ROWS[0] | {"owner": "Customer D"}]}, "developer")
    assert bad["error"]["code"] == "validation_error" and "owner is not a tenant on this account" in bad["error"]["message"]
    n = call("import.commit", {"ok": 3, "err": 0, "hash": "bad2", "rows": ROWS}, "developer")
    assert n["error"]["code"] == "validation_error"
    r = client.post("/api/actions/import.commit", json={"ok": 1, "err": 0, "hash": "x"}, headers=h("planner.a"))
    assert r.status_code == 403
    # counts only (the demo's input) still loads
    assert call("import.commit", {"ok": 4, "err": 0, "hash": "countsonly"}, "admin")["ok"]


IMP_ROWS = [
    {"asset_id": "MTR-9901", "qty": "2", "grade": "C", "location": "Warehouse 1", "owner": "Customer A", "received": "2026-10-07"}
]
REJECTED = [{"asset_id": "XYZ-1", "qty": "0", "grade": "F", "location": "Mars", "owner": "Customer A", "received": "07/10/2026"}]


def test_import_lands_through_the_pipeline_and_holds_rejected_rows():
    """Plan 6 B3: rows land in raw_record from source `manual`, map to canonical facts (no confidence, no freshness)
    that the asset's canonical record shows, never queue an instruction or a job; rejected rows are held."""
    with SessionLocal() as s:
        before = s.execute(text("SELECT (SELECT count(*) FROM instruction), (SELECT count(*) FROM job)")).one()
    r = call("import.commit", {"ok": 1, "err": 1, "hash": "b3pipeline1", "rows": IMP_ROWS, "rejected": REJECTED}, "developer")
    assert r["ok"] and r["output"]["facts"] == 6 and r["output"]["held"] == 1, r
    imp = r["output"]["id"]
    with SessionLocal() as s:
        raw = s.execute(
            text("SELECT ext_id, payload FROM raw_record WHERE source_id = 'manual' AND resource = 'import' AND ext_id LIKE :l"),
            {"l": imp + ":%"},
        ).all()
        assert [(x.ext_id, x.payload) for x in raw] == [(imp + ":1", IMP_ROWS[0])]
        held = failed.held(s, run_kind="import", run_id=imp)
        after = s.execute(text("SELECT (SELECT count(*) FROM instruction), (SELECT count(*) FROM job)")).one()
        assert s.execute(text("SELECT count(*) FROM source_system WHERE id = 'manual'")).scalar_one() == 0  # not a source
    assert len(held) == 1 and held[0]["step"] == "validate" and held[0]["payload"]["asset_id"] == "XYZ-1"
    assert "qty must be a positive whole number" in held[0]["reason"] and "received must be YYYY-MM-DD" in held[0]["reason"]
    assert tuple(after) == tuple(before)  # no instruction, no job
    a = client.get("/api/canonical/asset/MTR-9901", headers=h("admin")).json()
    assert (a["data"]["location"], a["data"]["qty"], a["data"]["owner_tenant"], a["data"]["received_at"]) == (
        "Warehouse 1", 2, "Customer A", "2026-10-07",
    )  # fmt: skip
    p = a["provenance"]["location"][0]
    assert (
        p["source_id"] == "manual" and p["confidence"] is None and p["resource"] == "import" and "Manual import" in p["transform"]
    )
    assert client.get("/api/canonical/condition/MTR-9901", headers=h("admin")).json()["data"]["grade"] == "C"
    dup = call("import.commit", {"ok": 1, "err": 1, "hash": "b3pipeline1", "rows": IMP_ROWS, "rejected": REJECTED}, "developer")
    assert dup["error"]["code"] == "duplicate"
    with SessionLocal() as s:
        n = s.execute(text("SELECT count(*) FROM raw_record WHERE source_id = 'manual' AND ext_id LIKE 'IMP-%'")).scalar_one()
        assert n == 3  # this import's row and the two of test_import_commit_records_the_rows_once, loaded once each
        manual.remove(s, imp)
        s.commit()
        assert store.get(s, "asset", "MTR-9901") is None and failed.held(s, run_kind="import", run_id=imp) == []


# plan 8 MVP-8.4: a bulk end-of-lease file opens a case for each row (edge case 24)
LEASE_ROWS = [
    {
        "asset_id": "MTR-9811",
        "qty": "1",
        "grade": "B",
        "location": "Warehouse 1",
        "owner": "Customer A",
        "received": "2026-10-08",
    },
    {
        "asset_id": "PMP-9812",
        "qty": "2",
        "grade": "C",
        "location": "Warehouse 2",
        "owner": "Customer C",
        "received": "2026-10-08",
    },
]
OPEN = {"template": "industrial", "reason": "lease_end", "org_unit_id": "", "asset_field": "asset_id"}


def _intake_cases() -> list[dict]:
    with SessionLocal() as s:
        q = text("SELECT data FROM case_record WHERE data->'intake'->>'reason' = 'lease_end' ORDER BY id")
        return list(s.execute(q).scalars())


@pytest.fixture
def lease_import():
    made: list[str] = []
    yield made
    with SessionLocal() as s:
        for imp in made:
            manual.remove(s, imp)
        s.commit()
    starting.reset()


def test_import_opens_cases(lease_import):
    r = call("import.commit", {"ok": 2, "err": 0, "hash": "lease1", "rows": LEASE_ROWS, "open_cases": OPEN}, "developer")
    assert r["ok"], r
    lease_import.append(r["output"]["id"])
    assert (r["output"]["cases_opened"], r["output"]["cases_skipped"]) == (2, 0)
    cases = _intake_cases()
    assert [(c["assetId"], c["owner"], c["cls"], c["grade"], c["qty"], c["location"]) for c in cases] == [
        ("MTR-9811", "Customer A", "motor", "B", 1, "Warehouse 1"),
        ("PMP-9812", "Customer C", "pump", "C", 2, "Warehouse 2"),
    ]
    assert sorted(c["id"] for c in cases) == sorted(r["output"]["case_ids"])
    assert all(c["routes"] and c["intake"]["by"] for c in cases)
    # opening cases needs openCases as well: the Planner cannot import, the Approver cannot open
    body = {"ok": 2, "err": 0, "hash": "lease-x", "rows": LEASE_ROWS, "open_cases": OPEN}
    assert call("import.commit", body, "approver")["error"]["code"] == "out_of_scope"


def test_import_twice_opens_once(lease_import):
    first = call("import.commit", {"ok": 2, "err": 0, "hash": "lease2", "rows": LEASE_ROWS, "open_cases": OPEN}, "developer")
    assert first["ok"], first
    lease_import.append(first["output"]["id"])
    again = call("import.commit", {"ok": 2, "err": 0, "hash": "lease3", "rows": LEASE_ROWS, "open_cases": OPEN}, "developer")
    assert again["ok"], again  # the same rows in another file: loaded, but no case twice
    lease_import.append(again["output"]["id"])
    assert (again["output"]["cases_opened"], again["output"]["cases_skipped"]) == (0, 2)
    assert len(_intake_cases()) == 2


# ---------------------------------------------------------------- conflicts
def _conflict(key: str) -> str:
    with SessionLocal() as s:
        store.apply(s, "erp", [Fact("demand", key, "purchase_baseline", 12000.0)], 97)
        store.apply(s, "proc", [Fact("demand", key, "purchase_baseline", 15000.0)], 90)
        s.commit()
        cid = s.execute(text("SELECT id FROM conflict WHERE key = :k AND status = 'open'"), {"k": key}).scalar_one()
    return f"CF-{cid}"


def _row(cid: str) -> dict:
    rows = client.get("/api/screens/integration/conflicts", params={"status": "all", "limit": 5000}, headers=h("admin")).json()
    return next(c for c in rows["conflicts"] if c["id"] == cid) | {"_counts": rows["counts"]}


def test_escalate_keeps_it_open_then_resolve_still_works():
    cid = _conflict("FRT-1")
    open0 = _row(cid)["_counts"]["open"]
    r = call("conflict.escalate", {"id": cid}, "developer")
    assert r["ok"] and r["output"]["id"] == cid
    c = _row(cid)
    assert c["status"] == "open" and c["escalated"]["by"] and c["_counts"]["open"] == open0  # it stays open (demo)
    e = events()[0]
    assert e["type"] == "conflict.escalated" and e["dir"] == "out" and e["ack"] == "sent" and e["key"] == "esc-" + cid.lower()
    assert e["note"] == "Purchase baseline conflict on FRT-1 escalated" and e["dest"].endswith(" data owner")
    again = call("conflict.escalate", {"id": cid}, "developer")
    assert again["error"]["code"] == "duplicate"
    r = call("conflict.resolve", {"id": cid}, "developer")
    assert r["ok"] and r["output"]["kept"] == "erp" and r["output"]["kind"] == "Purchase baseline" and r["output"]["authority"]
    c = _row(cid)
    assert c["status"] == "resolved" and c["_counts"]["open"] == open0 - 1
    e = events()[0]
    assert (
        e["type"] == "conflict.resolved" and e["dir"] == "in" and e["ack"] == "acknowledged" and e["key"] == "conf-" + cid.lower()
    )
    assert e["note"] == f"Purchase baseline conflict on FRT-1 resolved by source authority {r['output']['authority']}"
    assert " vs " in e["dest"]
    dup = call("conflict.resolve", {"id": cid}, "developer")
    assert dup["error"] == {"code": "duplicate", "message": f"{cid} is already resolved"}
    assert call("conflict.escalate", {"id": cid}, "developer")["error"]["code"] == "conflict"
