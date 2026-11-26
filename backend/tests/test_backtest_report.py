"""P9-7.6 (story X-06; registry entry I-16): the back-test report page's data: the waterfall, the ten flips explained and the
fixed method note, all computed from the stored replay report by `di.services.replay.measures` (never re-typed by the page).

The text on the page is composed by code from the decision's own gate result and trace, or is the one fixed method note, so
there is no free-form model output to route (R16): every number and every sentence here is checked arithmetic or a constant.
"""

import pytest

from di.services.modeler.pack import load_pack
from di.services.replay import measures
from di.services.replay import run as R
from tests.flowkit import ok
from tests.helpers import call
from tests.test_replay_run import (  # the stub deciders and the action fixtures of the replay tests
    FV,
    PACK,
    batch,
    decision,
    drain,
    fresh,
    import_batch,
    item,
    own_flow,
    route,
    stub,
)

__all__ = ["fresh"]  # the database fixture, reused


def _report(n: int = 20) -> R.ReplayReport:
    """n items: every third agrees; the rest flip to a different route with a different net."""
    items, plan = [], {}
    for k in range(n):
        actual = ["redeploy", "refurb", "resell", "harvest"][k % 4]
        items.append(item(k, actual, realised=90.0 + k))
        chosen = actual if k % 3 == 0 else "redeploy" if actual != "redeploy" else "refurb"
        routes = [route("redeploy", 500 + 11 * k), route("refurb", 200 + 3 * k), route("resell", 80 + k), route("harvest", 20)]
        if k == 2:
            routes[2] = route("resell", 900, excluded=True, failReason="Recall check: quarantined")
        plan[f"T{k:03d}"] = decision(chosen, routes, rules_applied=["TF-C"] if k == 1 else [], trace=(f"step {k}", "second"))
    return R.replay(batch(n), items, FV, pack=load_pack(PACK), decide=stub(plan))


def test_x_06_report_waterfall_sums():
    rep = _report().model_dump(mode="json")
    steps = measures.waterfall(rep)
    assert steps[0]["step"] == "Actual net" and steps[1]["step"] == "Same-route repricing (bias)"
    assert steps[-2]["step"] == "Constraint losses" and steps[-1]["step"] == "Net uplift"
    assert any(s["step"].startswith("Route change to ") for s in steps)
    flow_total = rep["flow_net"]
    assert sum(s["amount"] for s in steps if s["kind"] != "result") == pytest.approx(flow_total, abs=0.01)
    assert steps[-1]["amount"] == pytest.approx(rep["flow_net"] - rep["actual_net"], abs=0.01)


def test_x_06_report_waterfall_sums_with_constraint_loss():
    rep = {"actual_net": 1000.0, "flow_net": 1180.0, "repricing": 5.5, "constraint_loss": 40.25,
           "route_changes": [{"route": "refurb", "amount": 120.0}, {"route": "redeploy", "amount": 94.75}]}  # fmt: skip
    steps = measures.waterfall(rep)
    assert [s["amount"] for s in steps] == [1000.0, 5.5, 120.0, 94.75, -40.25, 180.0]
    assert sum(s["amount"] for s in steps if s["kind"] != "result") == pytest.approx(1180.0, abs=0.01)
    assert measures.waterfall({"flips": []}) == []  # a report from before this task has no totals


def test_x_06_report_top_flips_explained():
    rep = _report().model_dump(mode="json")
    assert len(rep["flips"]) > 10
    top = measures.top_flips_explained(rep)
    assert len(top) == 10
    assert all(t["reason"] and t["from"] != t["to"] for t in top)
    deltas = [abs(t["delta"]) for t in top]
    assert deltas == sorted(deltas, reverse=True) and deltas[0] == max(abs(f["delta"]) for f in rep["flips"])
    excluded = next(t for t in measures.top_flips_explained(rep, n=50) if t["item_id"] == "T002")
    assert excluded["gate"] == "Recall check: quarantined" and excluded["trace"] == "step 2 · second"
    ruled = next(t for t in measures.top_flips_explained(rep, n=50) if t["item_id"] == "T001")
    assert ruled["gate"] == "TF-C"
    assert measures.method_note() == measures.METHOD_NOTE
    for word in ("As-of", "Yardstick", "Leakage", "Bias", "Sensitivity runs are not included"):
        assert word in measures.method_note()


def test_x_06_report_readable_by_executive(fresh):
    bid, fid = import_batch(), own_flow()
    run_id = ok(call("replay.run", {"batch_id": bid, "flow_id": fid}, "planner.a"))["run_id"]
    queued = ok(call("replay.report", {"run_id": run_id}, "exec"))
    assert (queued["waterfall"], queued["top_flips"]) == ([], []) and queued["method_note"] == measures.method_note()
    drain()
    out = ok(call("replay.report", {"run_id": run_id}, "exec"))  # 200
    assert out["status"] == "done" and out["method_note"] == measures.method_note()
    assert out["waterfall"][0]["step"] == "Actual net" and out["waterfall"][-1]["step"] == "Net uplift"
    flow_net = out["report"]["flow_net"]
    assert sum(s["amount"] for s in out["waterfall"] if s["kind"] != "result") == pytest.approx(flow_net, abs=0.01)
    assert len(out["top_flips"]) == min(10, len(out["report"]["flips"]))
    picker = ok(call("replay.runs", {}, "exec"))["runs"]  # the Analytics run picker: finished runs of the actor's orgs
    assert [r["run_id"] for r in picker] == [run_id] and picker[0]["flow_name"]
    r = call("replay.run", {"batch_id": bid, "flow_id": fid}, "exec")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    assert ok(call("replay.runs", {}, "planner.b"))["runs"] == []  # another tenant's runs are not listed
