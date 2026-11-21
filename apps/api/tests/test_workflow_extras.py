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
from di.reads.common import STARTING_MAPPINGS
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
    state.reset(["workflows", "workflow_runs", "workflow_templates", "notes", "events"])


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
    """Mark a step to fail (the canvas' failure toggle) and save, with the given run settings."""
    b = save_body(wid, **extra)
    for n in b["graph"]["nodes"]:
        if n["id"] == step:
            n["fail"] = True
    assert call("workflow.save", b, "developer")["ok"]


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
def test_reprocess_failed_records():
    rows = detail("WF-101")["failed_rows"]
    assert rows
    r = call("workflow.reprocess", {"id": "WF-101"}, "developer")
    assert r["ok"], r
    assert r["output"]["n"] == len(rows)
    w = detail("WF-101")["workflow"]
    assert w["frReproc"].startswith(f"{len(rows)} records at ")
    again = call("workflow.reprocess", {"id": "WF-101"}, "developer")
    assert again["error"]["code"] == "duplicate"
    # WF-116's last run failed at validation, so it held no records
    assert call("workflow.reprocess", {"id": "WF-116"}, "developer")["error"]["code"] == "conflict"
    ev = [e for e in state_items("events") if e.get("type") == "workflow.reprocessed"]
    assert ev and ev[-1]["note"] == f"WF-101 · {len(rows)} held records sent back through validation"


def state_items(c: str) -> list[dict]:
    with engine.connect() as conn:
        return list(conn.execute(text("SELECT data FROM state_item WHERE collection = :c ORDER BY seq"), {"c": c}).scalars())


def test_apply_the_suggested_fix():
    before = detail("WF-116")["workflow"]
    r = call("workflow.applyFix", {"id": "WF-116"}, "developer")
    assert r["ok"], r
    f = STARTING_MAPPINGS["repair"][0]
    want = f"The renamed source field now maps to {f[2]} again (mapping kept as a new version)."
    w = detail("WF-116")["workflow"]
    assert w["frFix"] == want and r["output"]["fix"] == want
    assert w["ver"] != before["ver"] and w["hist"][0]["note"] == "Fix applied"
    assert call("workflow.applyFix", {"id": "WF-116"}, "developer")["error"]["code"] == "duplicate"
    # a workflow whose last run did not fail has nothing to fix
    assert call("workflow.applyFix", {"id": "WF-101"}, "developer")["error"]["code"] == "conflict"


def test_the_fix_clears_the_failing_step_and_the_next_run_clears_the_flags():
    step = first_xf("WF-105")
    fail_step("WF-105", step, alert="Never")
    assert run("WF-105")["last"]["state"] == "failed"
    assert call("workflow.applyFix", {"id": "WF-105"}, "developer")["ok"]
    g = detail("WF-105")["workflow"]["graph"]
    assert not next(n for n in g["nodes"] if n["id"] == step).get("fail")
    w = run("WF-105")
    assert w["last"]["state"] != "failed"
    assert "frFix" not in w and "frReproc" not in w
