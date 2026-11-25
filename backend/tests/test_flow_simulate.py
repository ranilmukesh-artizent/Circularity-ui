"""MVP-4.1: flow.simulate runs a candidate flow against the published one over the open queue the actor may see
(Domain spec D9)."""

import pytest

from di.core import golden
from di.core.db import SessionLocal
from di.services.cases import store
from di.services.modeler.flow import default_flow, fe
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call, client, h


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


def test_simulate_per_node_counts():
    """P9-8.15: the answer's `per_node` says how many cases reach each node and leave it; an exclude rule on grade C
    removes exactly the grade-C cases of the sample queue."""
    from di.services.modeler.valuers import tool_fleet

    fid = flowkit.flow_id("tool_fleet", "workspace")
    g = with_rule(default_flow(load_template("tool_fleet")), "TF-C", "exclude", "resell", {"grade": ["C"]})
    out = ok(call("flow.simulate", {"flow_id": fid, "graph": g}, "admin"))
    node = out["per_node"]["r-TF-C"]
    sample_c = sum(1 for c in tool_fleet.sample_queue() if (c.get("grade") or c.get("estGrade")) == "C")
    assert node["in"] == out["n"] and node["in"] - node["out"] >= sample_c > 0
    assert 1 <= len(node["examples"]) <= 3


# ---------------------------------------------------------------- MVP-6.3: the template sample queues
def test_tool_fleet_simulation_equals_golden():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    flows = {c["name"]: {"nodes": c["flow"]["n"], "edges": c["flow"]["e"]} for c in golden.load("po/compile_cases")["cases"]}
    for row in golden.load("po/sim_cases")["equip"]:
        out = ok(call("flow.simulate", {"flow_id": fid, "graph": flows[row["name"]]}, "admin"))
        want = row["sim"]
        assert (out["kind"], out["n"]) == (want["kind"], want["n"]), row["name"]
        got = [(f["case_id"], f["from"], f["to"]) for f in out["flips"]]
        assert got == [(f["id"], f["from"], f["to"]) for f in want["flips"]], row["name"]
        assert out["dv"] == pytest.approx(want["dv"], abs=1e-6), row["name"]


def test_device_simulation_equals_golden():
    fid = flowkit.flow_id("device", "workspace")
    row = golden.load("po/sim_cases")["device"][0]
    g = default_flow(load_template("device"))
    rule = row["rule"]
    into = next(e for e in g["edges"] if e["b"] == "dec")
    g["nodes"].append(rule)
    g["edges"] = [e for e in g["edges"] if e is not into] + [fe(into["a"], rule["id"]), fe(rule["id"], "dec")]
    out = ok(call("flow.simulate", {"flow_id": fid, "graph": g}, "admin"))
    want = row["sim"]
    assert (out["kind"], out["n"]) == ("device", want["n"])
    assert [(f["case_id"], f["from"], f["to"]) for f in out["flips"]] == [(f["id"], f["from"], f["to"]) for f in want["flips"]]
    assert out["dv"] == pytest.approx(want["dv"], abs=1e-6)
    for k in ("u", "cash", "dd", "days", "dl"):
        assert out["extra"][k] == pytest.approx(want[k], abs=1e-6), k


def test_modeler_screen_lists_the_queue():
    out = client.get("/api/screens/modeler", params={"template": "tool_fleet"}, headers=h("admin")).json()
    assert len(out["queue"]) == 26 and set(out["queue"][0]) == {"id", "label", "best", "net"}
    out = client.get("/api/screens/modeler", params={"template": "industrial"}, headers=h("planner-a")).json()
    assert {q["id"] for q in out["queue"]} == {c["id"] for c in _open_cases() if c["owner"] == "Customer A"}
