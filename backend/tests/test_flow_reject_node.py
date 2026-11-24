"""P9-0.12 (G section 6 item 10): a sent-back flow change is pinned to one step. flow.reject takes an optional
node_id and stores {reason, node_id, by, at} in decision_flow.returned; flow.saveDraft keeps it, flow.submit clears it."""

import pytest
from sqlalchemy import text

from di.core.db import engine
from di.mcp.policy import FORBIDDEN_ACTIONS
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h

REASON = "Scope this to grade D as well."
SCOPE = {"grade": ["C"], "owner": ["Customer A"]}


@pytest.fixture(autouse=True)
def fresh_flows():
    def reset() -> None:
        flowkit.reset_flows()
        with engine.begin() as conn:
            conn.execute(text("UPDATE decision_flow SET returned = NULL"))

    reset()
    yield
    reset()


def _in_review() -> int:
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(default_flow(load_template("industrial")), "IR-01", "exclude", "material", SCOPE)
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    return fid


def _returned():
    r = client.get("/api/screens/modeler", params={"template": "industrial", "org": "Customer A"}, headers=h("planner-a"))
    return r.json()["flow"]["returned"]


def test_reject_pinned_to_node():
    fid = _in_review()
    out = ok(call("flow.reject", {"flow_id": fid, "reason": REASON, "node_id": "p-resale"}, "approver"))
    assert out["node_id"] == "p-resale" and out["status"] == "draft"
    r = _returned()
    assert r["node_id"] == "p-resale" and r["reason"] == REASON and r["by"] == "approver" and r["at"]
    f, _ = flowkit.get(fid)
    assert f.returned["node_id"] == "p-resale"
    # saving the draft keeps it, so the maker sees it while fixing
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": f.draft}, "planner-a"))
    assert _returned()["node_id"] == "p-resale"


def test_reject_unknown_node_refused():
    fid = _in_review()
    r = call("flow.reject", {"flow_id": fid, "reason": REASON, "node_id": "nope"}, "approver")
    assert r["error"] == {"code": "validation_error", "message": "No step nope in this draft."}
    f, _ = flowkit.get(fid)
    assert f.status == "review" and f.returned is None


def test_submit_clears_returned():
    fid = _in_review()
    ok(call("flow.reject", {"flow_id": fid, "reason": REASON, "node_id": "p-resale"}, "approver"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    f, _ = flowkit.get(fid)
    assert f.status == "review" and f.returned is None


def test_reject_without_node_unchanged():
    fid = _in_review()
    out = ok(call("flow.reject", {"flow_id": fid, "reason": REASON}, "approver"))
    assert out["status"] == "draft" and out["reason"] == REASON and out["log"].startswith("Returned ")
    assert out.get("node_id") is None
    r = _returned()
    assert r["node_id"] is None and r["reason"] == REASON


def test_agent_still_cannot_reject():
    assert "flow.reject".startswith(FORBIDDEN_ACTIONS)
    fid = _in_review()
    hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post("/api/actions/flow.reject", json={"flow_id": fid, "reason": REASON, "node_id": "p-resale"}, headers=hdr)
    assert r.status_code == 403, r.json()
    f, _ = flowkit.get(fid)
    assert f.status == "review"
