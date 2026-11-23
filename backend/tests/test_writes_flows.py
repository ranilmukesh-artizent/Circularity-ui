"""MVP-3.2: the flow lifecycle actions (di.services.actions.modeler) with maker-checker (Domain spec D7; Review Focus
2 and 3)."""

import pytest

from di.mcp.policy import FORBIDDEN_ACTIONS
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h

MAKER_CHECKER = "Maker-checker: you made these changes, so you cannot approve them."
SCOPE_A_C = {"grade": ["C"], "owner": ["Customer A"]}


@pytest.fixture(autouse=True)
def fresh_flows():
    flowkit.reset_flows()
    yield
    flowkit.reset_flows()


def _industrial():
    return default_flow(load_template("industrial"))


def test_full_lifecycle():
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    f, _ = flowkit.get(fid)
    assert (f.org_unit_id, f.status, f.ver, f.published) == ("Customer A", "pub", 1, _industrial())

    g = with_rule(_industrial(), "IR-01", "exclude", "material", SCOPE_A_C)
    out = ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    assert not [c for c in out["checks"] if c["level"] == "fail"]
    f, _ = flowkit.get(fid)
    assert (f.status, f.maker, f.dver, f.draft) == ("draft", "planner-a", 2, g)

    out = ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    assert out["log"] == "Submitted Industrial returns v2 for approval"
    out = ok(call("flow.approve", {"flow_id": fid}, "approver"))
    assert out["log"] == "Approved Industrial returns v2 (maker Planner · Customer A); shadow run started"
    f, _ = flowkit.get(fid)
    assert (f.status, f.checker) == ("shadow", "approver")

    out = ok(call("flow.publish", {"flow_id": fid}, "approver"))
    assert out["log"] == "Published Industrial returns v2"
    f, versions = flowkit.get(fid)
    assert (f.status, f.ver, f.dver, f.draft, f.maker, f.checker, f.published) == ("pub", 2, None, None, None, None, g)
    assert [(v.ver, v.graph, v.published_by) for v in versions] == [(1, _industrial(), "approver")]

    got = ok(call("flow.get", {"flow_id": fid}, "planner-a"))
    assert got["flow"]["ver"] == 2 and got["template"]["key"] == "industrial"
    assert [r["id"] for r in got["compiled"]] == ["IR-01"]


def test_maker_cannot_approve():
    fid = flowkit.flow_id("industrial", "workspace")
    g = with_rule(_industrial(), "IR-01", "prefer", "resale", {})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "admin"))
    ok(call("flow.submit", {"flow_id": fid}, "admin"))
    r = call("flow.approve", {"flow_id": fid}, "admin")
    assert r == {"ok": False, "error": {"code": "conflict", "message": MAKER_CHECKER}}
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    r = call("flow.publish", {"flow_id": fid}, "admin")
    assert r["error"] == {"code": "conflict", "message": MAKER_CHECKER}


def test_planner_cannot_touch_other_org_flow():
    r = call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer B"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert r["error"]["message"] == "Customer B is a tenant you cannot see. Request tenant access first."
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer B"}, "admin"))["flow_id"]
    for action, body in (("flow.saveDraft", {"flow_id": fid, "graph": _industrial()}), ("flow.get", {"flow_id": fid}),
                         ("flow.submit", {"flow_id": fid})):  # fmt: skip
        r = call(action, body, "planner-a")
        assert r["error"]["code"] == "tenant_boundary", (action, r)
    ws = flowkit.flow_id("industrial", "workspace")
    assert call("flow.saveDraft", {"flow_id": ws, "graph": _industrial()}, "planner-a")["error"]["code"] == "tenant_boundary"


def test_fork_twice_conflicts():
    ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))
    r = call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a")
    assert r["error"]["code"] == "conflict"


def test_submit_refused_with_blocking_checks():
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(_industrial(), "IR-01", "exclude", None, {})
    out = ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    assert ["fail", "IR-01 has no path. Pick one in the inspector.", "r-IR-01"] in [
        [c["level"], c["msg"], c["node_id"]] for c in out["checks"]
    ]
    r = call("flow.submit", {"flow_id": fid}, "planner-a")
    assert r["error"] == {"code": "conflict", "message": "Fix the blocking checks before submitting."}


def test_reject_and_discard():
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(_industrial(), "IR-01", "exclude", "material", SCOPE_A_C)
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    assert call("flow.reject", {"flow_id": fid, "reason": "too short"}, "approver")["error"]["code"] == "validation_error"
    ok(call("flow.reject", {"flow_id": fid, "reason": "Scope this to grade D as well."}, "approver"))
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft) == ("draft", g)
    ok(call("flow.discard", {"flow_id": fid}, "planner-a"))
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft, f.maker, f.dver, f.ver, f.published) == ("pub", None, None, None, 1, _industrial())


def test_rollback():
    fid = flowkit.fork_and_publish("Customer A", [("IR-01", "exclude", "material", SCOPE_A_C)])
    out = ok(call("flow.rollback", {"flow_id": fid}, "approver"))
    assert out["log"] == "Rolled back Industrial returns from v2 to v1"
    f, versions = flowkit.get(fid)
    assert (f.status, f.ver, f.published, versions) == ("pub", 1, _industrial(), [])
    r = call("flow.rollback", {"flow_id": fid}, "approver")
    assert r["error"] == {"code": "conflict", "message": "No earlier version to roll back to."}


def test_permissions():
    fid = flowkit.flow_id("industrial", "workspace")
    assert call("flow.saveDraft", {"flow_id": fid, "graph": _industrial()}, "approver")["error"]["code"] == "out_of_scope"
    assert call("flow.approve", {"flow_id": fid}, "planner-a")["error"]["code"] == "out_of_scope"


def test_agent_cannot_publish():
    for a in ("flow.approve", "flow.publish", "flow.reject", "flow.rollback"):
        assert a.startswith(FORBIDDEN_ACTIONS), a
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(_industrial(), "IR-01", "exclude", "material", SCOPE_A_C)
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    for extra in ({}, {"X-Circularity-Confirmed": "true"}):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
        r = client.post("/api/actions/flow.publish", json={"flow_id": fid}, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] in ("approval_required", "out_of_scope"), r.json()
    f, _ = flowkit.get(fid)
    assert f.status == "shadow"
