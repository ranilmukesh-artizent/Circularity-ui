"""B10: the decision engine gives the demo's answers (docs/backend-steps.md).

Parity: for all 128 cases, the engine recomputes the gates, nets, P10/P90 ranges, ranks and recommendation from
each case's inputs (facts and route terms) and must match fixtures/golden/cases.json exactly. What-if and the pool
optimiser must match fixtures/golden/engine.json.
"""

import copy
import itertools

import pytest

from di import golden
from di.engine import book
from di.engine.evaluate import build_routes, evaluate
from di.engine.jsmath import js_round
from di.engine.pool import solve_pool
from di.engine.predictor import Asset, FormulaPredictor
from di.engine.routes import fail, mk_route, rank_routes, term
from di.engine.scenario import what_if
from tests.helpers import client, h

CASES = golden.load("cases")
BY_ID = {c["id"]: c for c in CASES}
ENGINE = golden.load("engine")


# ---------------------------------------------------------------- the building blocks
def test_js_round_rounds_halves_up_like_javascript():
    assert [js_round(x) for x in (2.5, -2.5, 0.5, -0.5, 1.4999, -1.5001)] == [3, -2, 1, 0, 1, -2]


def test_mk_route_net_and_range_for_rt_1048_redeploy():
    r = mk_route({
        "id": "redeploy", "sigma": 0.1,
        "terms": [term("Avoided equivalent purchase", 12000, "purchase"), term("Preparation and transfer", -1800, "prep"),
                  term("Service exposure (30 months)", -900, "service"), term("Residual value adjustment", 300, "residual")],
    })  # fmt: skip
    assert (r["net"], r["p10"], r["p90"]) == (9600, 8371, 10608)
    assert r["gates"] == ["pass"] * 6 and not r["excluded"] and r["failGate"] == -1


def test_small_routes_have_a_minimum_spread():
    r = mk_route({"id": "exit", "sigma": 0.08, "terms": [term("Net exit cost", -60, "fees")]})
    assert (r["p10"], r["p90"]) == (-72, -50)  # spread floor $12, upside x 0.82


def test_fail_skips_later_passing_gates_only():
    r = mk_route({"id": "resale", "terms": [term("x", 10, "sale")]})
    fail(r, 0, "life")
    fail(r, 2, "erasure")  # a later rule on an excluded route moves the failing gate on
    assert r["gates"] == ["fail", "skip", "fail", "skip", "skip", "skip"] and r["failGate"] == 2


def test_ranking_is_by_net_with_ties_in_listed_order():
    a, b, c = (mk_route({"id": i, "terms": [term("x", n, "sale")]}) for i, n in (("a", 5), ("b", 9), ("c", 5)))
    excluded = fail(mk_route({"id": "d", "terms": [term("x", 99, "sale")]}), 3, "no demand")
    assert rank_routes([a, b, c, excluded]) is b
    assert [r["rank"] for r in (b, a, c, excluded)] == [1, 2, 3, None]
    assert rank_routes([a, b], blocked={"gate": 0}) is None


# ---------------------------------------------------------------- parity with the demo, all 128 cases
@pytest.mark.parametrize("cid", sorted(BY_ID))
def test_case_parity(cid):
    g = BY_ID[cid]
    c = book.evaluated(g)
    assert c["routes"] == g["routes"], f"{cid}: routes differ"
    assert c["recommendation"] == g.get("recommendation")
    if g.get("recommendation") is not None:
        assert c["recommendation"] is c["routes"][g["routes"].index(g["recommendation"])]


def test_parity_covers_every_kind_of_case():
    rules = [c for c in CASES if c["routes"] and not book.hand_modelled(c)]
    reasons = {r["failReason"] for c in rules for r in c["routes"] if r["excluded"]}
    assert len(CASES) == 128 and len(rules) > 70
    assert sum(1 for c in CASES if c.get("recommendation")) == 87 and sum(1 for c in CASES if c["blocked"]) == 41
    # every gate rule is exercised by the generated cases
    assert len(reasons) >= 6, reasons


def test_rules_find_the_exclusions_themselves():
    """Without any exclusion given, the rules alone reproduce every generated case's exclusions."""
    for c in (c for c in CASES if c["routes"] and not book.hand_modelled(c)):
        facts, drafts, rules = book.inputs_of(c)
        assert rules and not any("preset_fail" in d for d in drafts)
        routes, _ = evaluate(facts, drafts, rules)
        assert [(r["failGate"], r["failReason"]) for r in routes] == [(r["failGate"], r["failReason"]) for r in c["routes"]]


# ---------------------------------------------------------------- what-if and the pool optimiser
WHAT_IF = [(cid, k) for cid, runs in sorted(ENGINE["what_if"].items()) for k in range(len(runs))]


def test_what_if_parity_all():
    runs = ENGINE["what_if"]
    bad = [(cid, k) for cid, k in WHAT_IF if what_if(book.get(cid), runs[cid][k]["input"]) != runs[cid][k]["output"]]
    assert not bad and len(WHAT_IF) == 88 * len(ENGINE["scenarios"])


def test_what_if_rt_1048_without_confirmed_demand():
    o = what_if(book.get("RT-1048"), {"demandOff": True})
    assert o["sim"] == {"plan": "Sell + buy for Site 3", "net": 4800} and o["change"] == -4800 and o["rank_changed"]
    assert o["rows"][0]["why"] == "Confirmed demand cancelled in this scenario" and o["decision_unchanged"]


@pytest.mark.parametrize(("cid", "partner"), [("RT-1048", "RT-1062"), ("RT-1052", "RT-1044")])
def test_pool_parity(cid, partner):
    p = solve_pool(copy.deepcopy(BY_ID[cid]["pool"]))
    want = BY_ID[partner]["poolResult"]  # the demo keeps the solved pool on the partner case
    assert {k: p[k] for k in ("greedy", "optimal", "uplift")} == {k: want[k] for k in ("greedy", "optimal", "uplift")}
    out = ENGINE["pools"][cid]
    got = (p["greedy"]["total"], p["optimal"]["total"], p["uplift"], p["optimal"]["alloc"])
    assert got == (out["greedy"], out["optimal"], out["uplift"], out["allocation"])


def test_pool_rt_1048_beats_greedy():
    p = solve_pool(BY_ID["RT-1048"]["pool"])
    assert (p["greedy"]["total"], p["optimal"]["total"], p["uplift"]) == (16000, 18200, 2200)
    assert p["greedy"]["alloc"] == {"RT-1062": {"Site 3": 1}, "RT-1048": {"Site 5": 1}}
    assert p["optimal"]["alloc"] == {"RT-1062": {"Site 5": 1}, "RT-1048": {"Site 3": 1}}


# ---------------------------------------------------------------- the formulas behind the Predictor
def test_formula_predictor_with_pinned_draws():
    p = FormulaPredictor(rnd=itertools.repeat(0.5).__next__)
    a = Asset("motor", "B", 6.4)
    assert p.avoided_purchase(a) == 10384  # 11,800 x (0.78 + 0.5 x 0.2)
    assert p.residual(a) == 236
    assert p.lease_income(a) == 2334  # 11,800 x (0.16 + 0.5 x 0.14) x 0.86 (grade B)
    # 0.03 + 0.5 x 0.025 is 0.042499999... in floating point, as in the demo, so 11,800 x it rounds down to 501
    assert p.material(a) == (501, js_round(501 * 0.4 + 10))


@pytest.mark.parametrize("cid", sorted(c["id"] for c in CASES if c["routes"] and not book.hand_modelled(c)))
def test_build_routes_has_the_demo_structure(cid):
    """A generated case rebuilt by the formulas (with different draws) has the demo's routes, terms and the
    exclusions that do not depend on value."""
    g = BY_ID[cid]
    facts, _, _ = book.inputs_of(g)
    built = build_routes(facts, FormulaPredictor())
    assert [r["id"] for r in built] == [r["id"] for r in g["routes"]]
    for b, r in zip(built[1:], g["routes"][1:], strict=True):  # [0] is resale as-is or refurbished, by value
        assert [(t["label"], t["kind"]) for t in b["terms"]] == [(t["label"], t["kind"]) for t in r["terms"]]
        assert (b["plan"], b["demandLabel"], b["demandStatus"]) == (r["plan"], r["demandLabel"], r["demandStatus"])
        if r["failGate"] in (0, 2, 3, 5):
            assert b["failGate"] == r["failGate"]


# ---------------------------------------------------------------- the actions


def _post(action, body, user="ops"):
    return client.post(f"/api/actions/{action}", json=body, headers=h(user))


def test_case_what_if_action():
    r = _post("case.whatIf", {"case_id": "RT-1048", "purchase": 0.8})
    assert r.status_code == 200, r.text
    assert r.json()["output"] == ENGINE["what_if"]["RT-1048"][0]["output"]


def test_pool_optimize_action():
    r = _post("pool.optimize", {"case_id": "RT-1062"})
    assert r.status_code == 200, r.text
    assert r.json()["output"]["uplift"] == 2200
    r = _post("pool.optimize", {"case_id": "RT-1049"})
    assert r.status_code == 404 and r.json()["error"]["message"] == "RT-1049 is not in a pool."
