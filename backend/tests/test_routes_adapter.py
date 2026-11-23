"""MVP-6.4: a template case's valuer output as the engine's routes, so `rank_routes` gives the recommendation (used by
intake, MVP-8.1, for the tool-fleet and device templates).

Term kinds of the tool-fleet value lines (first match wins; the label is matched by its start):

| path              | line          | label starts with                      | kind     |
|-------------------|---------------|----------------------------------------|----------|
| release, refurb   | value         | "Fleet renewal", "New fleet order"     | lease    |
| release, refurb   | value         | "Value when the contract ends"         | sale     |
| refurb            | value         | "Sales order"                          | sale     |
| redeploy          | value         | "New pool unit avoided"                | purchase |
| resell            | value         | "Bid", "Outlet sale"                   | sale     |
| harvest           | value         | "Residual material"                    | material |
| harvest           | value         | any other (a certified part)           | parts    |
| exit              | value         | "Material credit"                      | material |
| any               | cost          | "Ship to", "Inbound", "Channel fees",  | fees     |
|                   |               | "Listing", "Recycling"                 |          |
| any               | cost          | "Repairs covered"                      | risk     |
| any               | cost          | any other (clean, refurbish, teardown) | prep     |
| any               | holding       | "Holding until done"                   | fees     |

Costs and holding are negative amounts, so the route's net is the valuer's net. A device channel has two terms: the
expected cash a unit (`sale`) and the score's penalty for days past the service level (`risk`), so the net is the
channel's score, which is what `device.decide` ranks by.
"""

import pytest

from di.core.golden import load
from di.services.engine.routes import POLICY, rank_routes
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import device, tool_fleet
from di.services.modeler.valuers.routes_adapter import to_routes

TF = load_template("tool_fleet")
DEV = load_template("device")
FIVE = ["RC-26121", "RC-26141", "RC-26135", "RC-26142", "RC-26118"]  # release, refurb, redeploy, harvest, resell


def _tf_decision(case_id: str) -> tool_fleet.Decision:
    cases = {c["id"]: c for c in tool_fleet.sample_queue()}
    return tool_fleet.decide(cases[case_id], tool_fleet.BASEP, load("po/equip_decisions")["rules"])


@pytest.mark.parametrize("case_id", FIVE)
def test_adapter_keeps_best_path(case_id):
    d = _tf_decision(case_id)
    routes = to_routes(TF, d["all"])
    best = rank_routes(routes)
    assert best is not None
    assert best["id"] == d["best"]["k"]
    assert best["net"] == pytest.approx(d["best"]["net"], abs=1e-6)
    assert [r["id"] for r in routes] == list(tool_fleet.PK)
    assert all(r["net"] == pytest.approx(v["net"], abs=1e-6) for r, v in zip(routes, d["all"], strict=True))


def test_adapter_keeps_best_channel():
    for lot in device.sample_lots()[:5]:
        d = device.decide(lot)
        best = rank_routes(to_routes(DEV, d["all"]))
        assert d["best"] is not None and best is not None
        assert best["id"] == d["best"]["k"], lot["id"]
        assert best["net"] == pytest.approx(d["best"]["score"], abs=1e-6)


def test_adapter_excluded_reason():
    d = _tf_decision("RC-26141")  # BR-01: core drill rigs are never recycled
    routes = {r["id"]: r for r in to_routes(TF, d["all"])}
    exit_ = routes["exit"]
    why = next(v["why"] for v in d["all"] if v["k"] == "exit")
    assert why.startswith("Excluded by business rule BR-01: ")
    assert (exit_["excluded"], exit_["failGate"], exit_["failReason"]) == (True, POLICY, why)
    assert exit_["gates"][POLICY] == "fail"
    ok = routes["refurb"]
    assert (ok["excluded"], ok["failGate"], ok["failReason"]) == (False, -1, "")
    assert ok["plan"] == "Refurbish → place"
    assert ok["why"] == next(v["why"] for v in d["all"] if v["k"] == "refurb")


def test_adapter_device_reason_and_names():
    lot = next(x for x in device.sample_lots() if x["grade"] == "D")
    routes = {r["id"]: r for r in to_routes(DEV, device.decide(lot)["all"])}
    assert routes["market"]["plan"] == "Marketplace"
    assert routes["market"]["excluded"] and routes["market"]["failGate"] == POLICY
    assert routes["market"]["failReason"] == "Marketplace cannot take this lot"


def test_adapter_term_kinds():
    cases = {c["id"]: c for c in tool_fleet.sample_queue()}
    kinds = {}
    for c in cases.values():
        for v, r in zip(tool_fleet.decide(c)["all"], to_routes(TF, tool_fleet.decide(c)["all"]), strict=True):
            for line, t in zip(v["lines"], r["terms"], strict=True):
                assert t["label"] == line["label"]
                assert t["amt"] == (line["amt"] if line["type"] == "v" else -line["amt"])
                kinds[(v["k"], line["type"], line["label"].split(" ")[0])] = t["kind"]
    assert kinds[("release", "v", "Fleet")] == "lease"
    assert kinds[("refurb", "v", "Value")] == "sale"
    assert kinds[("redeploy", "v", "New")] == "purchase"
    assert kinds[("resell", "v", "Bid")] == "sale"
    assert kinds[("harvest", "v", "Residual")] == "material"
    assert kinds[("harvest", "v", "Gearbox")] == "parts"
    assert kinds[("exit", "v", "Material")] == "material"
    assert kinds[("resell", "c", "Channel")] == "fees"
    assert kinds[("refurb", "c", "Inbound")] == "fees"
    assert kinds[("exit", "c", "Recycling")] == "fees"
    assert kinds[("release", "c", "Repairs")] == "risk"
    assert kinds[("harvest", "c", "Teardown")] == "prep"
    assert kinds[("redeploy", "h", "Holding")] == "fees"
    allowed = {"sale", "prep", "fees", "risk", "purchase", "lease", "parts", "material"}
    assert set(kinds.values()) <= allowed
