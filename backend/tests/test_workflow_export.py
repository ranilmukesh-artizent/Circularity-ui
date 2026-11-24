"""P9-0.8: workflow.export, the one server-side workflow export (G section 6 item 5, "three shapes for two canvases").

- The shape is what the web app's exportJson wrote: the keys in order, a step's `cfg` only where it differs from the
  block's defaults, `exported_by` the account label.
- It round-trips through workflow.import, validates against the P9-0.7 schema, refuses an unknown id, and is for
  accounts that can open the Workflow Studio.
"""

from jsonschema import Draft202012Validator

from di.core.db import SessionLocal
from di.repositories.workflows import all_workflows
from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import agent_allowed
from di.workflow.schema import workflow_schema
from tests import starting
from tests.helpers import call

KEYS = ["id", "name", "version", "type", "status", "owner", "trigger", "source", "source_id", "description", "steps",
        "links", "exported_by", "exported_at"]  # fmt: skip


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _export(wid: str, user: str = "developer") -> dict:
    return call("workflow.export", {"workflow_id": wid}, user)


def _all_ids() -> list[str]:
    with SessionLocal() as s:
        return [w["id"] for w in all_workflows(s)]


def _first_id() -> str:
    with SessionLocal() as s:
        return next(w["id"] for w in all_workflows(s) if w.get("kind") == "pipe" and w.get("src"))


def test_export_matches_browser_shape():
    wid = _first_id()
    r = _export(wid)
    assert r["ok"], r
    out = r["output"]
    assert list(out) == KEYS
    assert out["id"] == wid and out["exported_by"] == "Developer" and out["exported_at"].endswith(("Z", "+00:00"))
    assert out["steps"] and all(list(s)[:6] == ["id", "kind", "ref", "label", "x", "y"] for s in out["steps"])
    assert all(list(link) == ["from", "to", "fixed"] for link in out["links"])
    assert all("cfg" not in s for s in out["steps"])  # a graph on its defaults carries no settings


def test_export_cfg_omits_default_settings():
    wid = _first_id()
    out = _export(wid)["output"]
    conn = next(s for s in out["steps"] if s["kind"] == "conn")
    graph = {
        "nodes": [
            {"id": s["id"], "k": s["kind"], "ref": s["ref"], "x": s["x"], "y": s["y"]}
            | ({"cfg": {"mode": "full", "lookback_days": 30}} if s["id"] == conn["id"] else {})
            for s in out["steps"]
        ],
        "edges": [{"id": f"e{i}", "a": k["from"], "b": k["to"], "locked": k["fixed"]} for i, k in enumerate(out["links"])],
    }
    saved = call("workflow.save", {"id": wid, "name": out["name"], "graph": graph}, "developer")
    assert saved["ok"], saved
    again = _export(wid)["output"]
    step = next(s for s in again["steps"] if s["id"] == conn["id"])
    assert set(step.get("cfg", {})) <= {"mode", "lookback_days"}
    assert all("cfg" not in s for s in again["steps"] if s["id"] != conn["id"])


def test_export_round_trips_through_import():
    wid = _first_id()
    out = _export(wid)["output"]
    r = call("workflow.import", {"data": out}, "developer")
    assert r["ok"], r
    try:
        back = _export(r["output"]["id"])["output"]
        assert [(s["id"], s["kind"], s["ref"], s.get("cfg")) for s in back["steps"]] == [
            (s["id"], s["kind"], s["ref"], s.get("cfg")) for s in out["steps"]
        ]
        assert back["links"] == out["links"]
        assert back["status"] == "draft"
    finally:
        call("workflow.delete", {"id": r["output"]["id"]}, "developer")


def test_export_validates_against_schema():
    v = Draft202012Validator(workflow_schema())
    for wid in _all_ids():
        out = _export(wid)["output"]
        assert list(v.iter_errors(out)) == [], wid


def test_export_unknown_workflow_not_found():
    r = _export("WF-NOPE")
    assert not r["ok"] and r["error"] == {"code": "not_found", "message": "No workflow WF-NOPE."}


def test_export_is_for_studio_accounts_only():
    r = _export(_first_id(), "planner.a")
    assert not r["ok"] and r["error"]["code"] == "out_of_scope"


def test_export_is_a_read_an_agent_may_call():
    a = ACTIONS["workflow.export"]
    assert a.risk == "read" and a.permission is None and agent_allowed(a)
