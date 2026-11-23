"""MVP-6.1: the tool-fleet valuer is a port of the PO prototype's `value`/`decide1`/`decide`/`planQueue` and its case
generator (docs/reference/po-modeler/recover-app-prototype.html, lines 791-1153). It must reproduce the goldens that
frontend/scripts/dump-po-golden.mjs wrote from the prototype (fixtures/golden/po)."""

import pytest

from di.core.golden import load
from di.services.modeler.valuers import tool_fleet
from di.services.modeler.valuers.rng import mulberry32

NET_TOL = 1e-6  # the goldens round numbers to 1e-6


def test_rng_matches_js():
    # The first five draws of the prototype's rng(26110) (line 791), printed by Node from that line verbatim. The
    # golden dump does not hold them; they are hard-coded here instead (see the commit message).
    r = mulberry32(26110)
    assert [r() for _ in range(5)] == [
        0.19966196687892079,
        0.536108766682446,
        0.46672616107389331,
        0.86469918908551335,
        0.91461838944815099,
    ]
    assert mulberry32(4242)() == 0.5467061335220933


def test_sample_cases_match_golden():
    golden = load("po/equip_cases")
    assert tool_fleet.sample_cases() == golden["cases"]


def test_sample_queue_is_the_golden_open_cases():
    golden = load("po/equip_cases")
    queue = tool_fleet.sample_queue()
    assert [c["id"] for c in queue] == golden["open_ids"]
    by_id = {c["id"]: c for c in golden["cases"]}
    assert all(c == by_id[c["id"]] for c in queue)


def test_live_rules_match_golden():
    assert load("po/equip_decisions")["rules"] == tool_fleet.LIVE_RULES


def test_decisions_match_golden():
    golden = load("po/equip_decisions")
    cases = {c["id"]: c for c in tool_fleet.sample_queue()}
    assert [d["id"] for d in golden["decisions"]] == list(cases)
    for want in golden["decisions"]:
        got = tool_fleet.decide(cases[want["id"]], tool_fleet.BASEP, golden["rules"])
        assert got["best"]["k"] == want["best"]["k"], want["id"]
        assert got["best"]["net"] == pytest.approx(want["best"]["net"], abs=NET_TOL), want["id"]
        assert got["rules"] == want["rules"], want["id"]
        for v, w in zip(got["all"], want["paths"], strict=True):
            assert (v["k"], v["ok"], v["why"]) == (w["k"], w["ok"], w["why"]), want["id"]
            assert v["net"] == pytest.approx(w["net"], abs=NET_TOL), (want["id"], w["k"])


def test_apply_rules_matches_golden():
    golden = load("po/apply_cases")
    cases = {c["id"]: c for c in tool_fleet.sample_queue()}
    for want in golden["cases"]:
        values = [tool_fleet.value(cases[want["id"]], k, tool_fleet.BASEP) for k in tool_fleet.PK]
        result = tool_fleet.apply_rules(cases[want["id"]], values, golden["rule_sets"][want["rule_set"]])
        assert [{"k": v["k"], "ok": v["ok"], "why": v["why"]} for v in values] == want["paths"], want
        assert result == want["result"], want


def _compiled(name: str) -> list[dict]:
    return next(c["rules"] for c in load("po/compile_cases")["cases"] if c["name"] == name)


def test_sim_matches_golden():
    base = _compiled("default")
    for row in load("po/sim_cases")["equip"]:
        got = tool_fleet.simulate(base, _compiled(row["name"]))
        want = row["sim"]
        assert (got["kind"], got["n"]) == (want["kind"], want["n"]), row["name"]
        assert got["dv"] == pytest.approx(want["dv"], abs=NET_TOL), row["name"]
        assert [(f["id"], f["from"], f["to"]) for f in got["flips"]] == [(f["id"], f["from"], f["to"]) for f in want["flips"]]
        for f, w in zip(got["flips"], want["flips"], strict=True):
            assert f["from_net"] == pytest.approx(w["from_net"], abs=NET_TOL)
            assert f["to_net"] == pytest.approx(w["to_net"], abs=NET_TOL)


def test_value_lines_add_up():
    case = tool_fleet.sample_queue()[0]
    for k in tool_fleet.PK:
        v = tool_fleet.value(case, k)
        gross = sum(x["amt"] for x in v["lines"] if x["type"] == "v")
        cost = sum(x["amt"] for x in v["lines"] if x["type"] == "c")
        assert v["net"] == pytest.approx(gross - cost - v["hold"])


def test_decide_does_not_mutate_the_sample():
    case = tool_fleet.sample_queue()[0]
    d = tool_fleet.decide(case)
    d["best"]["net"] = 0
    d["all"].clear()
    assert tool_fleet.decide(case)["best"]["net"] != 0
    assert tool_fleet.sample_queue()[0] == case
