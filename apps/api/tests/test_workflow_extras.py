"""Workflow Studio controls the demo kept in browser memory, now actions: save as template (frWfTpl) and create from a
template (frTplUse), the run settings Retries and Alert when (frWfSet), reprocess failed records (frReproc) and apply
the suggested fix (frFixApply).

The starting state is unchanged by all of this (test_screens_workflows compares it with the demo); each test starts
from the starting workflows and runs.
"""

import pytest
from sqlalchemy import text

import di.actions.workflows as wf
from di import state
from di.db import engine
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(wf, "STEP_SECONDS", 0)
    monkeypatch.setattr(wf, "QUICK_SECONDS", 0)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'workflow.run'"))
    state.reset(["workflows", "workflow_runs", "workflow_templates", "workflow_versions", "notes", "events"])


def run_queued() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, payload FROM job WHERE kind = 'workflow.run' AND status = 'queued' ORDER BY id")
        ).all()
    for job_id, payload in rows:
        wf.run_job(payload)
        with engine.begin() as conn:
            conn.execute(text("UPDATE job SET status = 'done' WHERE id = :i"), {"i": job_id})


def detail(wid: str) -> dict:
    r = client.get(f"/api/screens/workflows/{wid}", headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()


def listing() -> dict:
    return client.get("/api/screens/workflows", headers=h("developer")).json()


def notes() -> list[dict]:
    with engine.connect() as conn:
        return list(conn.execute(text("SELECT data FROM state_item WHERE collection = 'notes' ORDER BY seq")).scalars())


def save_body(wid: str, **extra) -> dict:
    d = detail(wid)
    w = d["workflow"]
    return {"id": wid, "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": w["graph"]} | extra


# ---------------------------------------------------------------- templates
def test_the_list_has_no_templates_at_the_start():
    assert listing()["templates"] == []


def test_save_as_template_then_create_from_it():
    r = call("workflow.saveTemplate", {"id": "WF-101"}, "developer")
    assert r["ok"], r
    assert r["output"]["id"] == "TPL-1" and r["output"]["name"].endswith(" template")
    # the demo keeps one template per workflow: saving again adds nothing
    assert call("workflow.saveTemplate", {"id": "WF-101"}, "developer")["output"]["id"] == "TPL-1"
    tpls = listing()["templates"]
    assert [t["id"] for t in tpls] == ["TPL-1"] and tpls[0]["from"] == "WF-101" and "tpl" not in tpls[0]

    src = detail("WF-101")["workflow"]
    c = call("workflow.create", {"type": "template", "tpl": "TPL-1"}, "developer")
    assert c["ok"], c
    new = detail(c["output"]["id"])
    w = new["workflow"]
    assert w["name"] == src["name"] + " (from template)" and c["output"]["name"] == w["name"]
    assert w["desc"] == f"Created from {src['name']} template."
    assert w["status"] == "draft" and w["ver"] == "0.1" and w["runsN"] == 0 and w["last"] is None
    assert (w["cat"], w["kind"], w["src"], w["owner"], w["trig"]) == (
        src["cat"],
        src["kind"],
        src["src"],
        src["owner"],
        src["trig"],
    )
    assert w["graph"] == src["graph"]
    # Reset to template gives the saved template's graph, not an empty one
    assert new["template"] == src["graph"]


def test_template_refusals():
    assert call("workflow.saveTemplate", {"id": "WF-999"}, "developer")["error"]["code"] == "not_found"
    assert call("workflow.create", {"type": "template", "tpl": "TPL-9"}, "developer")["error"] == {
        "code": "not_found",
        "message": "No template TPL-9.",
    }
    r = call("workflow.saveTemplate", {"id": "WF-101"}, "engineer")
    assert r["error"]["code"] == "out_of_scope"


# ---------------------------------------------------------------- run settings
def test_run_settings_are_saved_with_the_workflow():
    r = call("workflow.save", save_body("WF-101", retries=5, alert="Never"), "developer")
    assert r["ok"], r
    d = detail("WF-101")
    assert d["workflow"]["retries"] == 5 and d["workflow"]["alert"] == "Never"
    assert d["saved"]["retries"] == 5 and d["saved"]["alert"] == "Never"


def test_run_settings_are_checked():
    bad = call("workflow.save", save_body("WF-101", retries=2), "developer")
    assert bad["error"] == {"code": "validation_error", "message": "Retries must be 0, 1, 3 or 5."}
    bad = call("workflow.save", save_body("WF-101", alert="Sometimes"), "developer")
    assert bad["error"]["code"] == "validation_error"


def fail_step(wid: str, step: str, **extra) -> None:
    """Mark a step to fail (the canvas' failure toggle) and save, with the given run settings; a published workflow is
    published again, since runs use the published version (plan 6 C8)."""
    b = save_body(wid, **extra)
    for n in b["graph"]["nodes"]:
        if n["id"] == step:
            n["fail"] = True
    assert call("workflow.save", b, "developer")["ok"]
    if detail(wid)["workflow"]["status"] == "published":
        r = call("workflow.publish", {"id": wid}, "developer")
        assert r["ok"], r


def first_xf(wid: str) -> str:
    return next(n["id"] for n in detail(wid)["workflow"]["graph"]["nodes"] if n["k"] == "xf" and n["ref"] == "x_val")


def run(wid: str) -> dict:
    r = call("workflow.run", {"id": wid}, "developer")
    assert r["ok"], r
    run_queued()
    return detail(wid)["workflow"]


def test_a_failed_run_uses_the_retries_and_raises_the_alert():
    step = first_xf("WF-101")
    fail_step("WF-101", step, retries=1)
    w = run("WF-101")
    assert w["last"]["state"] == "failed" and w["lastRun"]["retries"] == 1
    n = [x for x in notes() if x.get("exId") == "wf:WF-101"]
    assert len(n) == 1 and n[0]["to"] == "developer" and n[0]["status"] == "open"
    assert n[0]["title"] == "Workflow alert · " + w["name"]
    assert n[0]["msg"].startswith(w["name"] + ": run " + w["lastRun"]["id"] + " failed.")


def test_alert_never_raises_nothing_and_two_in_a_row_waits_for_the_second():
    step = first_xf("WF-102")
    fail_step("WF-102", step, alert="Never")
    run("WF-102")
    assert not [x for x in notes() if x.get("exId") == "wf:WF-102"]

    fail_step("WF-103", first_xf("WF-103"), alert="Two runs fail in a row")
    run("WF-103")
    assert not [x for x in notes() if x.get("exId") == "wf:WF-103"]
    run("WF-103")
    n = [x for x in notes() if x.get("exId") == "wf:WF-103"]
    assert len(n) == 1 and "two runs failed in a row" in n[0]["msg"]


def test_a_successful_run_raises_no_alert():
    run("WF-104")
    assert not [x for x in notes() if x.get("exId") == "wf:WF-104"]


# ---------------------------------------------------------------- failed records and the suggested fix
def state_items(c: str) -> list[dict]:
    with engine.connect() as conn:
        return list(conn.execute(text("SELECT data FROM state_item WHERE collection = :c ORDER BY seq"), {"c": c}).scalars())


def held_rows(**where) -> list[dict]:
    """The workflow runs' failed_record rows that match every given column."""
    q = text("SELECT * FROM failed_record WHERE run_kind = 'workflow' ORDER BY id")
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(q).mappings()]
    return [r for r in rows if all(r[k] == v for k, v in where.items())]


def _held_workflow() -> tuple[str, str]:
    """A workflow (connector -> validation -> audit log, with an error handler) whose run RUN-HELD1 held two records
    at its validation step: A2 (qty 0) and A5 (qty 3, held under an older rule)."""
    from di.canonical.failed import hold

    wid = new_ingest()
    rules = [{"field": "qty", "check": "range", "arg": ">0"}]
    nodes = [
        {"id": "r", "k": "conn", "ref": "erp", "x": 24, "y": 170},
        {"id": "v", "k": "xf", "ref": "x_val", "x": 230, "y": 170, "cfg": {"rules": rules}},
        {"id": "aud", "k": "xf", "ref": "x_audit", "x": 436, "y": 170},
        {"id": "err", "k": "xf", "ref": "x_err", "x": 230, "y": 340},
    ]
    edges = [{"id": "e0", "a": "r", "b": "v", "locked": False}, {"id": "e1", "a": "v", "b": "aud", "locked": False},
             {"id": "e2", "a": "v", "b": "err", "locked": False}]  # fmt: skip
    b = save_body(wid) | {"graph": {"nodes": nodes, "edges": edges}}
    assert call("workflow.save", b, "developer")["ok"]
    from di.db import SessionLocal

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM failed_record WHERE run_id LIKE 'RUN-HELD1%' OR run_id LIKE 'REPROC-%'"))
    with SessionLocal() as s:
        for ext, qty in (("A2", 0), ("A5", 3)):
            hold(
                s, run_kind="workflow", run_id="RUN-HELD1", source_id="erp", step="err", resource="items", ext_id=ext,
                field="qty", rule="range", value=qty, reason=f"qty {qty} is not > 0", payload={"id": ext, "qty": qty},
            )  # fmt: skip
        rec = {"id": "RUN-HELD1", "wf": wid, "name": "x", "ts": 1, "trig": "Manual", "dur": 1, "rows": 2, "state": "warning"}
        state.add(s, "workflow_runs", "RUN-HELD1", rec | {"note": "2 records held"})
        s.commit()
    return wid, "RUN-HELD1"


def test_reprocess_sends_held_records_back_through_the_steps_from_the_one_that_rejected_them():
    wid, rid = _held_workflow()
    r = call("workflow.reprocess", {"id": wid}, "developer")
    assert r["ok"], r
    assert (r["output"]["n"], r["output"]["reprocessed"], r["output"]["held"]) == (2, 1, 1)
    rows = {x["ext_id"]: x for x in held_rows(run_id=rid)}
    assert rows["A5"]["status"] == "reprocessed" and rows["A2"]["status"] == "held"
    # a record that is still held stays as one row (no copy from the reprocess)
    assert len(held_rows(status="held", source_id="erp", ext_id="A2")) == 1
    assert not held_rows(status="held", source_id="erp", ext_id="A5")
    w = detail(wid)["workflow"]
    assert w["frReproc"].startswith("2 records at ") and "1 reprocessed, 1 still held" in w["frReproc"]
    ev = [e for e in state_items("events") if e.get("type") == "workflow.reprocessed"]
    want = f"{wid} · 2 held records sent back through Validation & enrichment: 1 reprocessed, 1 still held"
    assert ev and ev[-1]["note"] == want
    # fixed rule: the last one goes through too; then nothing is left to reprocess
    b = save_body(wid)
    next(n for n in b["graph"]["nodes"] if n["id"] == "v")["cfg"] = {"rules": [{"field": "qty", "check": "range", "arg": ">=0"}]}
    assert call("workflow.save", b, "developer")["ok"]
    r = call("workflow.reprocess", {"id": wid}, "developer")
    assert r["ok"] and r["output"]["reprocessed"] == 1, r
    assert call("workflow.reprocess", {"id": wid}, "developer")["error"] == {
        "code": "conflict",
        "message": "No held records to reprocess.",
    }
    assert call("workflow.reprocess", {"id": wid}, "engineer")["error"]["code"] == "out_of_scope"


def test_apply_fix_restores_the_failed_blocks_settings_from_the_last_good_version():
    step = first_xf("WF-105")
    before = detail("WF-105")["workflow"]
    fail_step("WF-105", step, alert="Never")  # a new version with the step's failure toggle on, published
    assert run("WF-105")["last"]["state"] == "failed"
    r = call("workflow.applyFix", {"id": "WF-105"}, "developer")
    assert r["ok"], r
    fix = r["output"]["fix"]
    assert fix == f"Validation & enrichment is back to its settings from v{before['ver']}: failure toggle off."
    d = detail("WF-105")
    w = d["workflow"]
    assert not next(n for n in w["graph"]["nodes"] if n["id"] == step).get("fail")
    assert w["frFix"] == fix and w["hist"][0]["note"] == "Fix applied" and r["output"]["ver"] == w["ver"]
    assert d["versions"][0]["ver"] == w["ver"] and d["published_ver"] == w["ver"]  # runs use the fixed version
    assert call("workflow.applyFix", {"id": "WF-105"}, "developer")["error"]["code"] == "duplicate"
    w = run("WF-105")
    assert w["last"]["state"] != "failed"
    assert "frFix" not in w and "frReproc" not in w


def test_apply_fix_refusals():
    # a workflow whose last run did not fail has nothing to fix
    assert call("workflow.applyFix", {"id": "WF-101"}, "developer")["error"]["code"] == "conflict"
    # WF-116's last run failed, but there is no earlier version to take settings from
    r = call("workflow.applyFix", {"id": "WF-116"}, "developer")
    assert r["error"]["code"] == "conflict" and "no earlier version" in r["error"]["message"], r


# ---------------------------------------------------------------- versions (plan 6 C8)
def new_ingest() -> str:
    r = call("workflow.create", {"type": "ingest", "src": "erp"}, "developer")
    assert r["ok"], r
    return r["output"]["id"]


def save_graph(wid: str, change, **extra) -> dict:
    """Save the workflow with its graph changed by `change(graph)`; returns the graph saved."""
    b = save_body(wid, **extra)
    change(b["graph"])
    r = call("workflow.save", b, "developer")
    assert r["ok"], r
    return detail(wid)["workflow"]["graph"]


def set_cfg(nid_ref: str, cfg: dict):
    def change(g: dict) -> None:
        n = next(x for x in g["nodes"] if x["ref"] == nid_ref)
        n["cfg"] = cfg

    return change


def add_node(nid: str, ref: str):
    def change(g: dict) -> None:
        g["nodes"].append({"id": nid, "k": "xf", "ref": ref, "x": 900, "y": 420})

    return change


def test_every_version_is_kept_and_v02_and_v03_are_both_restorable():
    wid = new_ingest()
    g1 = detail(wid)["workflow"]["graph"]
    g2 = save_graph(wid, set_cfg("x_val", {"on_failure": "reject"}), note="Reject bad rows")  # 0.2
    g3 = save_graph(wid, add_node("fx", "x_fx"), retries=5)  # 0.3
    save_graph(wid, add_node("lk", "x_lookup"))  # 0.4
    d = detail(wid)
    assert d["workflow"]["ver"] == "0.4"
    vs = d["versions"]
    assert [v["ver"] for v in vs] == ["0.4", "0.3", "0.2", "0.1"]
    assert vs[2]["note"] == "Reject bad rows" and vs[2]["by"] and vs[2]["at"]
    assert vs[0]["current"] and not any(v["current"] for v in vs[1:])

    r = call("workflow.restore", {"id": wid, "ver": "0.2"}, "developer")
    assert r["ok"], r
    assert r["output"]["ver"] == "0.5"
    w = detail(wid)["workflow"]
    assert w["ver"] == "0.5" and w["graph"] == g2 and w["hist"][0]["note"] == "Restored v0.2"
    assert w.get("retries") is None  # 0.2 had no run settings saved

    r = call("workflow.restore", {"id": wid, "ver": "0.3"}, "developer")
    assert r["ok"], r
    w = detail(wid)["workflow"]
    assert w["ver"] == "0.6" and w["graph"] == g3 and w["retries"] == 5
    # the very first version too, and the saved snapshot follows the restored graph
    assert call("workflow.restore", {"id": wid, "ver": "0.1"}, "developer")["ok"]
    d = detail(wid)
    assert d["workflow"]["graph"] == g1 and d["saved"]["graph"] == g1
    assert [v["ver"] for v in d["versions"]][:3] == ["0.7", "0.6", "0.5"]


def test_restore_refusals():
    wid = new_ingest()
    save_graph(wid, add_node("fx", "x_fx"))
    assert call("workflow.restore", {"id": wid, "ver": "9.9"}, "developer")["error"]["code"] == "not_found"
    assert call("workflow.restore", {"id": wid, "ver": "0.2"}, "developer")["error"] == {
        "code": "conflict",
        "message": "v0.2 is the current version.",
    }
    assert call("workflow.restore", {"id": "WF-999", "ver": "0.1"}, "developer")["error"]["code"] == "not_found"
    assert call("workflow.restore", {"id": wid, "ver": "0.1"}, "engineer")["error"]["code"] == "out_of_scope"


def test_a_run_uses_the_published_version_even_with_a_saved_draft():
    wid = new_ingest()
    g1 = detail(wid)["workflow"]["graph"]
    assert call("workflow.publish", {"id": wid}, "developer")["ok"]
    g2 = save_graph(wid, add_node("fx", "x_fx"))  # a draft change, saved but not published
    w = state_get(wid)
    assert wf.graph_for_run(w) == g1 and g2 != g1
    d = detail(wid)
    assert d["published_ver"] == "0.1" and "pub" not in d["workflow"]
    assert [v["published"] for v in d["versions"]] == [False, True]
    # publishing the saved draft makes it the version that runs
    assert call("workflow.publish", {"id": wid}, "developer")["ok"]
    assert wf.graph_for_run(state_get(wid)) == g2
    assert detail(wid)["published_ver"] == "0.2"
    # unpublished: a manual run tries the saved graph
    save_graph(wid, add_node("lk", "x_lookup"))
    assert call("workflow.setStatus", {"id": wid, "status": "draft"}, "developer")["ok"]
    assert wf.graph_for_run(state_get(wid)) == state_get(wid)["graph"]
    assert detail(wid)["published_ver"] is None


def test_a_starting_published_workflow_keeps_running_its_published_graph():
    before = detail("WF-101")["workflow"]
    g = save_graph("WF-101", add_node("fx", "x_fx"))
    w = state_get("WF-101")
    assert wf.graph_for_run(w) == before["graph"] != g
    d = detail("WF-101")
    assert d["published_ver"] == before["ver"]
    assert [v["ver"] for v in d["versions"]] == [w["ver"], before["ver"]]
    assert "pub" not in listing()["workflows"][0]


def state_get(wid: str) -> dict:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT data FROM state_item WHERE collection = 'workflows' AND id = :i"), {"i": wid}
        ).scalar_one()


def compare(wid: str, a: str, b: str | None = None):
    params = {"a": a} | ({"b": b} if b else {})
    return client.get(f"/api/screens/workflows/{wid}/compare", params=params, headers=h("developer"))


def test_compare_two_versions():
    wid = new_ingest()
    save_graph(wid, set_cfg("x_val", {"on_failure": "reject"}))  # 0.2

    def change(g: dict) -> None:
        g["nodes"] = [n for n in g["nodes"] if n["ref"] != "x_audit"]
        ids = {n["id"] for n in g["nodes"]}
        g["edges"] = [e for e in g["edges"] if e["a"] in ids and e["b"] in ids]
        g["nodes"].append({"id": "fx", "k": "xf", "ref": "x_fx", "x": 900, "y": 420, "cfg": {"currency": "EUR"}})
        g["edges"].append({"id": "efx", "a": "v", "b": "fx", "locked": False})

    had_audit = any(n["ref"] == "x_audit" for n in detail(wid)["workflow"]["graph"]["nodes"])
    save_graph(wid, change, retries=1, owner="Data team")  # 0.3
    r = compare(wid, "0.1", "0.3")
    assert r.status_code == 200, r.text
    c = r.json()
    assert (c["a"], c["b"]) == ("0.1", "0.3")
    assert c["blocks"]["added"] == [{"id": "fx", "label": "Convert currency"}]
    if had_audit:
        assert [x["label"] for x in c["blocks"]["removed"]] == ["Audit log"]
    v = next(n for n in detail(wid)["workflow"]["graph"]["nodes"] if n["ref"] == "x_val")
    ch = next(x for x in c["blocks"]["changed"] if x["id"] == v["id"])
    assert {"field": "on_failure", "from": wf.blocks.default_cfg("x_val")["on_failure"], "to": "reject"} in ch["fields"]
    assert {"a": "v", "b": "fx"} in c["links"]["added"]
    keys = {s["key"]: s for s in c["settings"]}
    assert keys["retries"]["to"] == 1 and keys["owner"]["to"] == "Data team"
    # b defaults to the current version; an unknown version is 404
    assert compare(wid, "0.2").json()["b"] == "0.3"
    assert compare(wid, "7.7").status_code == 404
    assert client.get(f"/api/screens/workflows/{wid}/compare", params={"a": "0.1"}, headers=h("planner-a")).status_code == 403


def test_delete_forgets_the_versions_and_a_copy_starts_its_own():
    wid = new_ingest()
    assert call("workflow.publish", {"id": wid}, "developer")["ok"]
    save_graph(wid, add_node("fx", "x_fx"))
    c = call("workflow.duplicate", {"id": wid}, "developer")["output"]["id"]
    d = detail(c)
    assert d["published_ver"] is None and [v["ver"] for v in d["versions"]] == ["0.1"]
    assert call("workflow.delete", {"id": wid}, "developer")["ok"]
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM state_item WHERE collection = 'workflow_versions' AND data->>'wf' = :w"), {"w": wid}
        ).scalar_one()
    assert n == 0


# ---------------------------------------------------------------- history: only runs that happened (plan 6 C8)
def test_history_lists_only_the_runs_that_happened():
    """The demo derived up to 30 earlier runs from a workflow's counts (frWfHistory); those never happened, so the
    history now lists the run records, or the workflow's recorded last run when it has no record."""
    runs = listing()["runs"]
    for wid in ("WF-101", "WF-102", "WF-116"):
        w = detail(wid)
        mine = [r for r in runs if r["wf"] == wid]
        hist = w["history"]
        if mine:
            assert [x["id"] for x in hist] == [r["id"] for r in mine]
        else:
            last = w["workflow"]["last"]
            assert len(hist) == 1 and hist[0]["ts"] == last["ts"] and hist[0]["state"] == last["state"]
    n0 = len([r for r in runs if r["wf"] == "WF-104"])
    run("WF-104")
    h1 = detail("WF-104")["history"]
    assert len(h1) == n0 + 1
    assert h1[0]["real"] and h1[0]["id"] == detail("WF-104")["workflow"]["lastRun"]["id"]
