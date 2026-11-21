"""Plan 6, task C10: the workflow checks read the sources as they are now, field-aware settings checks, and
workflow.import.

- Pausing a source shows "Paused upstream" on its workflows from the server (the list's `upstream`), and the checks
  warn; resuming clears both. The seeded workspace still gives the demo's checks (the golden replays in
  test_writes_workflows.py cover that).
- A dedupe key the source's records do not carry is an error naming the block and the field.
- workflow.import takes the JSON the export writes and creates the workflow as a draft; an unknown block or source is
  refused with its name.
"""

import copy

import pytest

from di.workflow import live
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _list() -> dict:
    r = client.get("/api/screens/workflows", headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()


def _ingest_of(sid: str) -> dict:
    return next(w for w in _list()["workflows"] if w["src"] == sid and w["cat"] == "Ingest")


def _detail(wid: str) -> dict:
    r = client.get(f"/api/screens/workflows/{wid}", headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()


def _checks(wid: str) -> tuple[list[str], list[str]]:
    o = call("workflow.validate", {"id": wid}, "developer")["output"]
    return [x["msg"] for x in o["errors"]], [x["msg"] for x in o["warnings"]]


# ---------------------------------------------------------------- live source state
def test_effective_status_rules():
    ref = {"status": "stale"}
    assert live._effective(ref, "live", None) == ("stale", False)  # the demo's status stands while the connector is fine
    assert live._effective(ref, "paused", "live") == ("stale", True)
    assert live._effective({"status": "live"}, "failing", None) == ("stale", False)
    assert live._effective({"status": "live"}, "auth_expired", None) == ("stale", False)
    assert live._effective({"status": "live"}, "disconnected", None) == ("unavailable", False)
    assert live._effective({"status": "unavailable"}, "live", None) == ("live", False)  # connected since
    assert live._effective(None, "live", None) == ("live", False)


def test_pausing_a_source_shows_paused_upstream_from_the_server():
    w = _ingest_of("erp")
    assert "upstream" not in w and not _list()["live"]["erp"].get("paused")
    assert not [m for m in _checks(w["id"])[1] if "paused" in m]
    assert call("source.pause", {"source_id": "erp"}, "developer")["ok"]
    try:
        got = _ingest_of("erp")
        assert got["upstream"] == "paused"
        assert _list()["live"]["erp"]["paused"] is True
        assert _detail(w["id"])["workflow"]["upstream"] == "paused"
        others = [x for x in _list()["workflows"] if x["src"] != "erp"]
        assert all("upstream" not in x for x in others)
        _, warns = _checks(w["id"])
        assert f"{_name('erp')} is paused. Runs read nothing from it until it is resumed." in warns
    finally:
        assert call("source.resume", {"source_id": "erp"}, "developer")["ok"]
    assert "upstream" not in _ingest_of("erp")


def _name(sid: str) -> str:
    from di.reads.common import SOURCES

    return SOURCES[sid]["name"]


def test_the_seeded_sources_keep_the_demos_statuses_for_the_checks():
    lv = _list()["live"]
    assert lv["mkt"]["status"] == "stale" and lv["mkt"]["fresh"] == "19 h"
    assert lv["rcy"]["status"] == "manual"
    assert lv["iot"]["status"] == "unavailable"


def test_the_seeded_workspace_gives_the_demos_checks():
    """Every starting workflow gets the checks the demo's source reference gives (the golden replays' validate results),
    except where a connector itself reports trouble now (failing, auth_expired: real state the demo never had)."""
    from sqlalchemy import text

    from di import golden
    from di.actions import workflows as wf
    from di.db import SessionLocal

    with SessionLocal() as s:
        trouble = set(s.execute(text("SELECT id FROM source_system WHERE status IN ('failing', 'auth_expired')")).scalars())
        for w in golden.load("screens/workflows")["starting"]:
            g = w.get("graph") or wf.build(w["tpl"])
            if {n["ref"] for n in g["nodes"] if n["k"] in ("conn", "wconn")} & trouble:
                continue
            assert wf.validate(g, w["kind"], s) == wf.validate(g, w["kind"]), w["id"]


# ---------------------------------------------------------------- field-aware settings checks
def _new(sid: str) -> dict:
    r = call("workflow.create", {"type": "ingest", "src": sid}, "developer")
    assert r["ok"], r
    return _detail(r["output"]["id"])["workflow"]


def _save(w: dict, g: dict) -> None:
    r = call("workflow.save", {"id": w["id"], "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": g}, "developer")
    assert r["ok"], r


def test_a_dedupe_key_the_records_lack_is_an_error_naming_the_block_and_field():
    w = _new("crm")
    try:
        g = copy.deepcopy(w["graph"])
        r = next(n for n in g["nodes"] if n["k"] == "conn")
        g["nodes"].append({"id": "late", "k": "xf", "ref": "x_late", "x": 400, "y": 400, "cfg": {"keys": ["opportunity_id"]}})
        g["edges"].append({"id": "eL", "a": r["id"], "b": "late", "locked": False})
        _save(w, g)
        errs, _ = _checks(w["id"])
        assert "Order late events: Key fields opportunity_id is not a field the records carry." in errs
        next(n for n in g["nodes"] if n["id"] == "late")["cfg"] = {"keys": ["Id"]}  # Salesforce's record id
        _save(w, g)
        errs, _ = _checks(w["id"])
        assert not [m for m in errs if "is not a field the records carry" in m]
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_fields_come_from_records_and_the_mapping():
    from di.db import SessionLocal

    with SessionLocal() as s:
        f = live.fields(s, "erp")
        assert f is not None and {"EKPO-MENGE", "MENGE", "demand.qty", "qty"} <= f
        assert live.fields(s, "no-such-source") is None


# ---------------------------------------------------------------- workflow.import
def _export(wid: str) -> dict:
    """The JSON the browser's Export JSON writes (apps/web/src/api/workflows.ts exportJson)."""
    d = _detail(wid)
    w, g = d["workflow"], d["workflow"]["graph"]
    from di.actions import workflows as wf

    return {
        "id": w["id"], "name": w["name"], "version": w["ver"], "type": w["cat"], "status": w["status"], "owner": w["owner"],
        "trigger": w["trig"], "source": wf.SOURCES[w["src"]]["vendor"] if w.get("src") else None, "source_id": w.get("src"),
        "description": w["desc"],
        "steps": [{"id": n["id"], "kind": n["k"], "ref": n["ref"], "label": wf.label(n), "x": n["x"], "y": n["y"],
                   **({"cfg": n["cfg"]} if n.get("cfg") else {})} for n in g["nodes"]],
        "links": [{"from": e["a"], "to": e["b"], "fixed": bool(e.get("locked"))} for e in g["edges"]],
        "exported_by": "Developer", "exported_at": "2026-11-20T09:00:00.000Z",
    }  # fmt: skip


def test_import_of_an_export_recreates_the_workflow_as_a_draft():
    src = _ingest_of("erp")
    exp = _export(src["id"])
    r = call("workflow.import", {"data": exp}, "developer")
    assert r["ok"], r
    nid = r["output"]["id"]
    try:
        assert nid != src["id"] and r["output"]["name"] == exp["name"]
        got = _detail(nid)["workflow"]
        orig = _detail(src["id"])["workflow"]
        assert got["status"] == "draft" and got["ver"] == "0.1"
        keys = ("cat", "kind", "src", "owner", "trig")
        assert [got[k] for k in keys] == [orig[k] for k in keys]
        strip = lambda g: ([{k: n[k] for k in ("id", "k", "ref", "x", "y")} for n in g["nodes"]],  # noqa: E731
                           [(e["a"], e["b"], e["locked"]) for e in g["edges"]])  # fmt: skip
        assert strip(got["graph"]) == strip(orig["graph"])
        assert _checks(nid) == _checks(src["id"])
    finally:
        call("workflow.delete", {"id": nid}, "developer")


def test_import_keeps_block_settings():
    w = _new("erp")
    g = copy.deepcopy(w["graph"])
    next(n for n in g["nodes"] if n["ref"] == "x_val")["cfg"] = {"on_failure": "reject"}
    _save(w, g)
    r = call("workflow.import", {"data": _export(w["id"])}, "developer")
    try:
        assert r["ok"], r
        got = _detail(r["output"]["id"])["workflow"]["graph"]
        assert next(n for n in got["nodes"] if n["ref"] == "x_val")["cfg"] == {"on_failure": "reject"}
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")
        if r.get("ok"):
            call("workflow.delete", {"id": r["output"]["id"]}, "developer")


@pytest.mark.parametrize(
    ("change", "code", "msg"),
    [
        (lambda e: e["steps"].append({"id": "zz", "kind": "xf", "ref": "x_teleport", "x": 0, "y": 0}), "validation_error",
         "Unknown block x_teleport in step zz."),
        (lambda e: e["steps"].append({"id": "zz", "kind": "gadget", "ref": "x_val", "x": 0, "y": 0}), "validation_error",
         "Unknown block gadget in step zz."),
        (lambda e: e.update(source_id="nope", source="Nope Corp"), "not_found", "Unknown source nope."),
        (lambda e: e["steps"].append({"id": "zz", "kind": "conn", "ref": "nope", "x": 0, "y": 0}), "not_found",
         "Unknown source nope in step zz."),
        (lambda e: e["links"].append({"from": "r", "to": "ghost", "fixed": False}), "validation_error",
         "Link r → ghost names a step the workflow does not have."),
        (lambda e: e.pop("steps"), "validation_error", "This is not a workflow export: it has no steps."),
    ],
)  # fmt: skip
def test_import_refusals(change, code, msg):
    exp = _export(_ingest_of("erp")["id"])
    change(exp)
    n = len(_list()["workflows"])
    r = call("workflow.import", {"data": exp}, "developer")
    assert not r["ok"] and r["error"]["code"] == code and r["error"]["message"] == msg, r
    assert len(_list()["workflows"]) == n


def test_import_needs_manage_workflows():
    r = call("workflow.import", {"data": _export(_ingest_of("erp")["id"])}, "planner-a")
    assert not r["ok"] and r["error"]["code"] == "out_of_scope", r
