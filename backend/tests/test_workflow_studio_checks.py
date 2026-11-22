"""Workflow Studio usability (plan 6 follow-up, G2).

- workflow.validate takes an unsaved draft graph (`graph`) and answers the server's full checks for it (live sources,
  field-aware settings), each with the step it belongs to (`node`) and its severity (`sev`), so the canvas' Checks
  panel, Validate and the inspector show the errors Test run and Publish would refuse on. Without `graph` it answers as
  the demo did (the saved graph, `node` null: the golden replays).
- A test run refused for errors names the first one.
- A published workflow whose saved version is newer than the one that runs can publish that version (Publish v{x}).
- A test run is a dry run: whoever may run it (manageWorkflows) may approve its simulated Human approval step; the
  answer says the approval was simulated. Real approvals stay with approvers.
"""

import copy

from tests import starting
from tests.helpers import call, client, h

BAD_KEY = "Order late events: Key fields opportunity_id is not a field the records carry."


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _detail(wid: str) -> dict:
    r = client.get(f"/api/screens/workflows/{wid}", headers=h("developer"))
    assert r.status_code == 200, r.text
    return r.json()


def _new(kind: str, sid: str) -> dict:
    r = call("workflow.create", {"type": kind, "src": sid}, "developer")
    assert r["ok"], r
    return _detail(r["output"]["id"])["workflow"]


def _with_bad_key(w: dict) -> dict:
    g = copy.deepcopy(w["graph"])
    conn = next(n for n in g["nodes"] if n["k"] == "conn")
    g["nodes"].append({"id": "late", "k": "xf", "ref": "x_late", "x": 400, "y": 400, "cfg": {"keys": ["opportunity_id"]}})
    g["edges"].append({"id": "eL", "a": conn["id"], "b": "late", "locked": False})
    return g


# ---------------------------------------------------------------- gap 1: the server's checks for the draft
def test_validate_a_posted_draft_gives_the_field_error_with_its_step():
    w = _new("ingest", "crm")
    try:
        g = _with_bad_key(w)
        o = call("workflow.validate", {"id": w["id"], "graph": g}, "developer")["output"]
        assert {"msg": BAD_KEY, "node": "late", "sev": "error"} in o["errors"], o
        assert all(x["node"] and x["sev"] in ("warn", "info") for x in o["warnings"]), o
        # the saved graph has no such step: validating it (the demo's call) does not see the draft's error
        saved = call("workflow.validate", {"id": w["id"]}, "developer")["output"]
        assert BAD_KEY not in [x["msg"] for x in saved["errors"]]
        assert all(x["node"] is None for x in saved["errors"] + saved["warnings"])
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_validate_refuses_a_malformed_draft():
    w = _new("ingest", "crm")
    try:
        r = call("workflow.validate", {"id": w["id"], "graph": {"nodes": "x"}}, "developer")
        assert not r["ok"] and r["error"]["code"] == "validation_error", r
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


def test_a_refused_test_run_names_the_first_error():
    w = _new("ingest", "crm")
    try:
        r = call("workflow.testRun", {"id": w["id"], "graph": _with_bad_key(w)}, "developer")
        assert not r["ok"] and r["error"]["code"] == "conflict", r
        assert r["error"]["message"] == f"Fix 1 error before running. The checks say what and why. First: {BAD_KEY}", r
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


# ---------------------------------------------------------------- gap 2: publishing a newer saved version
def test_a_newer_saved_version_of_a_published_workflow_can_be_published():
    w = _new("ingest", "erp")
    try:
        assert call("workflow.publish", {"id": w["id"]}, "developer")["ok"]
        d = _detail(w["id"])
        assert d["published_ver"] == d["workflow"]["ver"]
        g = copy.deepcopy(d["workflow"]["graph"])
        g["nodes"][0]["x"] += 40
        s = call("workflow.save", {"id": w["id"], "name": w["name"], "owner": w["owner"], "trig": w["trig"], "graph": g},
                 "developer")  # fmt: skip
        assert s["ok"], s
        d = _detail(w["id"])
        assert d["workflow"]["status"] == "published" and d["published_ver"] != d["workflow"]["ver"]
        r = call("workflow.publish", {"id": w["id"]}, "developer")
        assert r["ok"] and r["output"]["ver"] == s["output"]["ver"], r
        assert _detail(w["id"])["published_ver"] == s["output"]["ver"]
        # once the newest version runs, publishing again is a duplicate
        again = call("workflow.publish", {"id": w["id"]}, "developer")
        assert not again["ok"] and again["error"]["code"] == "duplicate", again
    finally:
        call("workflow.delete", {"id": w["id"]}, "developer")


# ---------------------------------------------------------------- gap 3: approving a dry run
def test_a_developer_approves_the_simulated_approval_of_a_dry_run():
    r = call("workflow.create", {"type": "out", "src": "erp"}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    try:
        held = call("workflow.testRun", {"id": wid}, "developer")["output"]
        assert held["status"] == "held" and held["simulated_approval"] is False, held
        o = call("workflow.testRun", {"id": wid, "approved": True}, "developer")["output"]
        assert o["approved"] is True and o["simulated_approval"] is True and o["dry"] is True, o
        assert o["status"] != "held"
    finally:
        call("workflow.delete", {"id": wid}, "developer")


def test_real_approval_rules_are_unchanged():
    """The dry-run approval is not a real one: a Developer still cannot approve a case, and the Approver (who can) still
    cannot run a workflow's test run."""
    cat = {a["id"]: a for a in client.get("/api/actions", headers=h("developer")).json()}
    assert not cat["decision.approve"]["allowed"] and cat["workflow.testRun"]["allowed"]
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": "Dry run approval is not real.", "reviewed": True},
             "developer")  # fmt: skip
    assert not r["ok"], r
    appr = {a["id"]: a for a in client.get("/api/actions", headers=h("approver")).json()}
    assert appr["decision.approve"]["allowed"] and not appr["workflow.testRun"]["allowed"]
