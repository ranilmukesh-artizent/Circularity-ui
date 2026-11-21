"""Connection Fabric records: Source Tables (tables.update), Manual Import (import.commit) and the Conflict Queue
(conflict.resolve, conflict.escalate), with the demo's rules and texts (index.html, defAction('tables.update' ...),
ACT.tgAddOk ..., defAction('import.commit' ...), defAction('conflict.resolve' ...))."""

from sqlalchemy import text

from di import state
from di.canonical import store
from di.canonical.store import Fact
from di.db import SessionLocal, engine
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM conflict WHERE key LIKE 'FRT-%'"))
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
