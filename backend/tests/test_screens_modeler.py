"""MVP-4.2: the Modeler page's endpoint (GET /api/screens/modeler) and its menu entry."""

import pytest
from sqlalchemy import text

from di.core.db import engine
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import TEMPLATE_KEYS, load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h

URL = "/api/screens/modeler"


@pytest.fixture(autouse=True)
def fresh_flows():
    def reset() -> None:
        flowkit.reset_flows()
        with engine.begin() as conn:  # the log is the journal of the flow actions
            conn.execute(text("DELETE FROM domain_event WHERE type LIKE 'action.flow.%'"))
            conn.execute(text("DELETE FROM action_journal WHERE action LIKE 'flow.%'"))

    reset()
    yield
    reset()


def _get(acct: str, **params):
    return client.get(URL, params=params, headers=h(acct))


def test_modeler_screen_for_planner():
    out = _get("planner-a").json()
    assert [t["key"] for t in out["templates"]] == list(TEMPLATE_KEYS)
    assert out["org"] == "Customer A" and "Customer A" in out["orgs"]
    assert not {"workspace", "Customer B", "Customer C"} & set(out["orgs"])
    f = out["flow"]
    assert (f["org_unit_id"], f["status"], f["ver"], f["name"]) == ("workspace", "pub", 1, "Industrial returns")
    assert f["graph"] == f["published"] == default_flow(load_template("industrial"))
    assert out["can"] == {"edit": False, "approve": False, "fork": True}  # inherited: fork it first
    assert len(out["template"]["paths"]) == 7 and out["template"]["pre"] == "IR"
    assert (out["compiled"], out["versions"], out["shadow"], out["log"]) == ([], [], None, [])
    assert {c["level"] for c in out["checks"]} == {"ok"}

    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(f["graph"], "IR-01", "exclude", "resale", {"grade": ["C"]})
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": g}, "planner-a"))
    out = _get("planner-a", template="industrial", org="Customer A").json()
    assert (out["flow"]["id"], out["flow"]["status"], out["flow"]["dver"]) == (fid, "draft", 2)
    assert out["flow"]["graph"] == g and out["flow"]["published"] == f["published"]
    assert out["can"] == {"edit": True, "approve": False, "fork": False}
    assert [r["id"] for r in out["compiled"]] == ["IR-01"]
    assert [(x["action"], x["role"]) for x in out["log"]] == [("flow.saveDraft", "Planner"), ("flow.fork", "Planner")]


def test_shadow_and_versions():
    fid = flowkit.fork_and_publish("Customer A", [("IR-01", "exclude", "material", {})])
    out = _get("approver", org="Customer A").json()
    assert [v["ver"] for v in out["versions"]] == [1]
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": default_flow(load_template("industrial"))}, "planner-a"))
    ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    ok(call("flow.approve", {"flow_id": fid}, "approver"))
    out = _get("approver", org="Customer A").json()
    assert out["flow"]["status"] == "shadow" and set(out["shadow"]) == {"n", "agree", "disagree", "dv"}
    assert out["can"]["approve"] is True


def test_executive_read_only():
    r = _get("executive", template="tool_fleet")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["flow"]["name"] == "Tool fleet returns" and out["org"] == "workspace"
    assert out["band"][4] == "Core prediction and agents · fixed"
    assert out["can"] == {"edit": False, "approve": False, "fork": False}


def test_other_org_is_refused():
    r = _get("planner-a", org="Customer B")
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_boundary"
    assert _get("admin", template="nope").status_code == 404


@pytest.mark.parametrize("acct", ["admin", "planner-a", "approver", "executive", "developer", "wm-1"])
def test_nav_shows_modeler_for_allowed_roles(acct):
    groups = client.get("/api/screens/nav", headers=h(acct)).json()["groups"]
    got = [g for g in groups if g["id"] == "modeler"]
    if acct in ("developer", "wm-1"):
        assert got == []
        return
    assert got == [{"id": "modeler", "label": "Modeler", "sub": "Decision process and business rules", "icon": "branch",
                    "section": "Integration", "leaf": True, "href": "#/modeler", "kids": []}]  # fmt: skip
    ids = [g["id"] for g in groups]
    assert ids[ids.index("modeler") + 1] in ("mcp", "orchestration")  # the first group of the More section


def test_warehouse_manager_no_access():
    r = _get("wm-1")
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
