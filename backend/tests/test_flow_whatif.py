"""P9-0.15: flow.simulate takes what-if levers (market, labour, lease, repair slots) on the tool-fleet template. A what-if
is a read: nothing is saved and no number changes (G section 6 item 16; G section 7.7 T3)."""

import pytest

from di.core import golden
from di.core.db import SessionLocal
from di.services.cases import store
from di.services.modeler.valuers import tool_fleet
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call


@pytest.fixture(autouse=True)
def fresh_flows():
    flowkit.reset_flows()
    yield
    flowkit.reset_flows()


def _expected(params: dict) -> list[tuple[str, str, str, float]]:
    """The sample queue decided at BASEP and at BASEP | params under the published rules, from the valuer directly."""
    out = []
    for c in tool_fleet.sample_queue():
        b = tool_fleet.decide(c, tool_fleet.BASEP, tool_fleet.LIVE_RULES)["best"]
        s = tool_fleet.decide(c, tool_fleet.BASEP | params, tool_fleet.LIVE_RULES)["best"]
        if b["k"] != s["k"]:
            out.append((c["id"], b["k"], s["k"], s["net"] - b["net"]))
    return out


def _sample_flips(out: dict) -> list[tuple[str, str, str, float]]:
    sample = {c["id"] for c in tool_fleet.sample_queue()}
    return [(f["case_id"], f["from"], f["to"], f["dv"]) for f in out["flips"] if f["case_id"] in sample]


def test_whatif_market_flips():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    out = ok(call("flow.simulate", {"flow_id": fid, "params": {"market": 0.6}}, "admin"))
    want = _expected({"market": 0.6})
    assert want and out["flips"]
    got = _sample_flips(out)
    assert [g[:3] for g in got] == [w[:3] for w in want]
    assert [g[3] for g in got] == pytest.approx([w[3] for w in want], abs=1e-6)
    assert out["params"] == {"market": 0.6}


def test_whatif_zero_slots_no_refurb():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    out = ok(call("flow.simulate", {"flow_id": fid, "params": {"slots": 0}}, "admin"))
    assert all(f["to"] != "refurb" for f in out["flips"])
    base_refurb = {
        c["id"]
        for c in tool_fleet.sample_queue()
        if tool_fleet.decide(c, tool_fleet.BASEP, tool_fleet.LIVE_RULES)["best"]["k"] == "refurb"
    }
    assert base_refurb, "the sample queue refurbishes some returns at the base slots"
    assert base_refurb <= {f["case_id"] for f in out["flips"]}


def test_whatif_device_refused():
    fid = flowkit.flow_id("device", "workspace")
    r = call("flow.simulate", {"flow_id": fid, "params": {"market": 0.6}}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == "What-if levers apply to the tool-fleet template."


@pytest.mark.parametrize(
    ("params", "msg"),
    [
        ({"market": 0.4}, "market must be between 0.5 and 1.5."),
        ({"labor": 1.6}, "labor must be between 0.5 and 1.5."),
        ({"lease": 0}, "lease must be between 0.5 and 1.5."),
        ({"slots": 21}, "slots must be between 0 and 20."),
        ({"slots": 2.5}, "slots must be between 0 and 20."),
    ],
)
def test_whatif_out_of_range_refused(params, msg):
    fid = flowkit.flow_id("tool_fleet", "workspace")
    r = call("flow.simulate", {"flow_id": fid, "params": params}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == msg


def test_whatif_saves_nothing():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    with SessionLocal() as s:
        before = store.all_cases(s)
    ok(call("flow.simulate", {"flow_id": fid, "params": {"market": 0.6, "slots": 2}}, "admin"))
    f, _ = flowkit.get(fid)
    assert (f.status, f.draft) == ("pub", None)
    with SessionLocal() as s:
        assert store.all_cases(s) == before


def test_simulate_without_params_unchanged():
    fid = flowkit.flow_id("tool_fleet", "workspace")
    flows = {c["name"]: {"nodes": c["flow"]["n"], "edges": c["flow"]["e"]} for c in golden.load("po/compile_cases")["cases"]}
    for row in golden.load("po/sim_cases")["equip"]:
        out = ok(call("flow.simulate", {"flow_id": fid, "graph": flows[row["name"]]}, "admin"))
        got = [(f["case_id"], f["from"], f["to"]) for f in out["flips"]]
        assert got == [(f["id"], f["from"], f["to"]) for f in row["sim"]["flips"]]
        assert out["dv"] == pytest.approx(row["sim"]["dv"], abs=1e-6)
        assert out["params"] is None
