"""MVP-4.1: flow.simulate runs a candidate flow against the published one over the open queue the actor may see
(Domain spec D9)."""

import pytest

from di.core.db import SessionLocal
from di.services.cases import store
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call


@pytest.fixture(autouse=True)
def fresh_flows():
    flowkit.reset_flows()
    yield
    flowkit.reset_flows()


def _open_cases() -> list[dict]:
    with SessionLocal() as s:
        return [c for c in store.all_cases(s) if c["stage"] != "closed"]


def _industrial():
    return default_flow(load_template("industrial"))


def _flips_by_excluding(cases: list[dict], path: str) -> set[str]:
    """The cases recommending `path` that have another eligible route to go to."""
    return {
        c["id"]
        for c in cases
        if c.get("recommendation") and c["recommendation"]["id"] == path
        and any(not r["excluded"] and r["id"] != path for r in c["routes"])
    }  # fmt: skip


def test_simulate_no_change_is_zero():
    fid = flowkit.flow_id("industrial", "workspace")
    out = ok(call("flow.simulate", {"flow_id": fid}, "admin"))
    assert out["kind"] == "equip"
    assert out["n"] == len(_open_cases()) > 0
    assert (out["flips"], out["dv"]) == ([], 0)


def test_simulate_excluding_resale_flips_cases():
    fid = flowkit.flow_id("industrial", "workspace")
    g = with_rule(_industrial(), "IR-01", "exclude", "resale", {})
    out = ok(call("flow.simulate", {"flow_id": fid, "graph": g}, "admin"))
    want = _flips_by_excluding(_open_cases(), "resale")
    assert want, "the demo's queue has cases recommending resale"
    assert {f["case_id"] for f in out["flips"]} == want
    assert all(f["from"] == "resale" and f["to"] != "resale" and f["dv"] <= 0 for f in out["flips"])
    assert out["dv"] == pytest.approx(sum(f["dv"] for f in out["flips"]))
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft) == ("pub", None)  # a simulation saves nothing


def test_simulate_uses_the_draft_when_no_graph_is_given():
    fid = flowkit.flow_id("industrial", "workspace")
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": with_rule(_industrial(), "IR-01", "exclude", "resale", {})}, "admin"))
    out = ok(call("flow.simulate", {"flow_id": fid}, "admin"))
    assert {f["case_id"] for f in out["flips"]} == _flips_by_excluding(_open_cases(), "resale")


def test_simulate_respects_tenant():
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": "Customer A"}, "planner-a"))["flow_id"]
    g = with_rule(_industrial(), "IR-01", "exclude", "resale", {})
    out = ok(call("flow.simulate", {"flow_id": fid, "graph": g}, "planner-a"))
    mine = [c for c in _open_cases() if c["owner"] == "Customer A"]
    assert out["n"] == len(mine) > 0
    assert {f["case_id"] for f in out["flips"]} == _flips_by_excluding(mine, "resale")
    ws = flowkit.flow_id("industrial", "workspace")
    r = call("flow.simulate", {"flow_id": ws, "graph": g}, "planner-a")
    assert r["error"]["code"] == "tenant_boundary"
    others = ok(call("flow.simulate", {"flow_id": ws}, "admin"))
    assert others["n"] == len([c for c in _open_cases() if c["owner"] != "Customer A"])  # Customer A has its own flow


def test_simulate_needs_a_flow_permission():
    fid = flowkit.flow_id("industrial", "workspace")
    assert ok(call("flow.simulate", {"flow_id": fid}, "approver"))["kind"] == "equip"
    r = call("flow.simulate", {"flow_id": fid}, "warehouse1")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
