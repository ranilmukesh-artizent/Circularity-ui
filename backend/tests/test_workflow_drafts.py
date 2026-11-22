"""Plan 6, task C9: the canvas' working draft is kept on the server (per workflow and person), so a reload or a
sign-out keeps it; Discard drops it; deleting the workflow drops everyone's draft."""

import copy

from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _detail(wid: str, who: str = "developer") -> dict:
    r = client.get(f"/api/screens/workflows/{wid}", headers=h(who))
    assert r.status_code == 200, r.text
    return r.json()


def _new() -> dict:
    r = call("workflow.create", {"type": "ingest", "src": "erp"}, "developer")
    assert r["ok"], r
    return _detail(r["output"]["id"])["workflow"]


def _draft_body(w: dict, **more) -> dict:
    g = copy.deepcopy(w["graph"])
    g["nodes"][0]["x"] += 40  # a moved step
    return {"id": w["id"], "graph": g, "name": w["name"] + " (editing)", "owner": w["owner"], "trig": w["trig"],
            "retries": 1, "alert": "Never", "base": w["ver"] + "|" + str(w["updated"])} | more  # fmt: skip


def test_a_draft_survives_a_reload_and_is_per_person():
    w = _new()
    try:
        assert _detail(w["id"])["draft"] is None
        body = _draft_body(w)
        r = call("workflow.draft.save", body, "developer")
        assert r["ok"] and r["output"]["id"] == w["id"], r
        d = _detail(w["id"])["draft"]  # what the page reads when it opens again (a reload, or after signing in)
        assert {k: d[k] for k in ("graph", "name", "owner", "trig", "retries", "alert", "base")} == {
            k: body[k] for k in ("graph", "name", "owner", "trig", "retries", "alert", "base")
        }
        assert _detail(w["id"], "admin")["draft"] is None  # another person does not see it
        # the workflow itself is unchanged: a draft is not a version
        after = _detail(w["id"])["workflow"]
        assert (after["ver"], after["name"], after["graph"]) == (w["ver"], w["name"], w["graph"])
        # a later autosave replaces it
        body2 = _draft_body(w, name="Second try")
        assert call("workflow.draft.save", body2, "developer")["ok"]
        assert _detail(w["id"])["draft"]["name"] == "Second try"
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_autosaves_are_not_journaled():
    """An autosave every few seconds is the person's scratch copy: it is stored but writes no journal row and no domain
    event (they would fill the activity and audit views). The permission check still applies (a write)."""
    from sqlalchemy import text

    from di.core.db import engine

    w = _new()
    try:
        with engine.connect() as c:
            before = c.execute(text("SELECT count(*) FROM action_journal WHERE action LIKE 'workflow.draft.%'")).scalar_one()
        assert call("workflow.draft.save", _draft_body(w), "developer")["ok"]
        assert call("workflow.draft.discard", {"id": w["id"]}, "developer")["ok"]
        with engine.connect() as c:
            after = c.execute(text("SELECT count(*) FROM action_journal WHERE action LIKE 'workflow.draft.%'")).scalar_one()
            events = c.execute(text("SELECT count(*) FROM domain_event WHERE type LIKE 'action.workflow.draft.%'")).scalar_one()
        assert (after - before, events) == (0, 0)
        assert call("workflow.draft.save", _draft_body(w), "planner-a")["error"]["code"] == "out_of_scope"
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_discard_drops_the_draft():
    w = _new()
    try:
        assert call("workflow.draft.save", _draft_body(w), "developer")["ok"]
        r = call("workflow.draft.discard", {"id": w["id"]}, "developer")
        assert r["ok"] and r["output"]["discarded"] is True, r
        assert _detail(w["id"])["draft"] is None
        assert call("workflow.draft.discard", {"id": w["id"]}, "developer")["output"]["discarded"] is False
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_deleting_the_workflow_drops_its_drafts():
    w = _new()
    assert call("workflow.draft.save", _draft_body(w), "developer")["ok"]
    assert call("workflow.draft.save", _draft_body(w), "admin")["ok"]
    assert call("workflow.delete", {"id": w["id"]}, "developer")["ok"]
    again = _new()  # the id is reused
    try:
        assert again["id"] == w["id"]
        assert _detail(again["id"])["draft"] is None and _detail(again["id"], "admin")["draft"] is None
    finally:
        call("workflow.delete", {"id": again["id"]}, "developer")


def test_draft_refusals():
    r = call("workflow.draft.save", {"id": "WF-999", "graph": {"nodes": [], "edges": []}, "name": "x"}, "developer")
    assert not r["ok"] and r["error"]["code"] == "not_found", r
    r = call("workflow.draft.save", {"id": "WF-101", "graph": {"nodes": "x"}, "name": "x"}, "developer")
    assert not r["ok"] and r["error"]["code"] == "validation_error", r
    r = call("workflow.draft.save", {"id": "WF-101", "graph": {"nodes": [], "edges": []}, "name": "x"}, "planner-a")
    assert not r["ok"] and r["error"]["code"] == "out_of_scope", r


# ---------------------------------------------------------------- the honest test run (workflow.testRun)
def _fingerprint() -> tuple:
    from sqlalchemy import text

    from di.core.db import engine

    with engine.connect() as c:
        return tuple(
            c.execute(text(f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {t} t")).one()  # noqa: S608
            for t in ("canonical", "provenance", "raw_record", "sync_cursor", "failed_record", "action_journal")
        )


def test_a_test_run_is_a_dry_run_of_the_draft_with_real_counts_and_samples():
    w = _new()
    try:
        g = copy.deepcopy(w["graph"])
        g["nodes"][0]["x"] += 10  # an unsaved draft: the test run uses the graph it is sent
        runs_before = len(client.get("/api/screens/workflows", headers=h("developer")).json()["runs"])
        before = _fingerprint()
        r = call("workflow.testRun", {"id": w["id"], "graph": g, "sample": 10}, "developer")
        assert r["ok"], r
        o = r["output"]
        assert _fingerprint() == before  # nothing written: no records, facts, cursors, held records, journal entry
        assert len(client.get("/api/screens/workflows", headers=h("developer")).json()["runs"]) == runs_before
        assert o["status"] in ("success", "failed") and o["dry"] is True
        assert o["order"] and set(o["order"]) == {n["id"] for n in g["nodes"]}
        conn = next(n["id"] for n in g["nodes"] if n["k"] == "conn")
        mp = next(n["id"] for n in g["nodes"] if n["k"] == "map")
        assert o["states"][conn] == "success", o
        assert 0 < o["counts"][conn]["out"] <= 10 and o["rows"] == o["counts"][conn]["out"]
        assert o["counts"][mp]["in"] == sum(o["counts"][p]["out"] for p in [e["a"] for e in g["edges"] if e["b"] == mp])
        assert o["samples"][mp]["before"] and o["samples"][mp]["after"] and "facts" in o["samples"][mp]["after"][0]
        assert all(isinstance(o["dur"][x], int | float) for x in o["order"])
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_a_test_run_stops_at_human_approval_until_approved():
    r = call("workflow.create", {"type": "out", "src": "erp"}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    try:
        g = _detail(wid)["workflow"]["graph"]
        appr = next(n["id"] for n in g["nodes"] if n["k"] == "fixed" and n["ref"] == "appr")
        after = {e["b"] for e in g["edges"] if e["a"] == appr}
        o = call("workflow.testRun", {"id": wid}, "developer")["output"]
        assert o["status"] == "held" and o["states"][appr] == "held", o
        assert after and all(o["states"][x] == "waiting" for x in after)
        o2 = call("workflow.testRun", {"id": wid, "approved": True}, "developer")["output"]
        assert o2["states"][appr] == "success" and o2["status"] != "held", o2
    finally:
        call("workflow.delete", {"id": wid}, "developer")


def test_a_test_run_refuses_a_draft_with_errors_and_needs_manage_workflows():
    w = _new()
    try:
        g = copy.deepcopy(w["graph"])
        g["edges"] = []  # nothing wired: raw values would not reach the model, the checks have errors
        g["nodes"].append({"id": "fx", "k": "xf", "ref": "x_fx", "x": 0, "y": 400, "cfg": {"currency": "XYZ"}})
        r = call("workflow.testRun", {"id": w["id"], "graph": g}, "developer")
        assert not r["ok"] and r["error"]["code"] == "conflict" and r["error"]["message"].startswith("Fix "), r
        r = call("workflow.testRun", {"id": w["id"]}, "planner-a")
        assert not r["ok"] and r["error"]["code"] == "out_of_scope", r
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")
