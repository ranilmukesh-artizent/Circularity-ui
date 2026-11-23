"""MVP-2.4: business rules apply after the gate rules (Domain spec D4; the prototype's inScope and applyRules).

Exclusions fail the route at gate 2 (Policy & certification) with the prototype's texts; a rule set that would leave
no route eligible is waived (Review Focus 1). Without business rules the engine's output is unchanged (parity).
"""

import copy

import pytest

from di.core import golden
from di.services.engine import book
from di.services.engine.evaluate import build_routes, evaluate
from di.services.engine.predictor import FormulaPredictor
from di.services.engine.routes import POLICY, fail, mk_route, rank_routes, term
from di.services.modeler.apply import RuleOutcome, apply_rules
from di.services.modeler.compile import CompiledRule
from di.services.modeler.scope import in_scope
from di.services.modeler.templates import load_template

TF = load_template("tool_fleet")
IND = load_template("industrial")
APPLY = golden.load("po/apply_cases")
EQUIP = {c["id"]: c for c in golden.load("po/equip_cases")["cases"]}
CASES = golden.load("cases")


def _rules(rows: list[dict]) -> list[CompiledRule]:
    return [CompiledRule(r["id"], r["scope"], r["action"], r["path"], r["text"]) for r in rows]


def _stubs(paths: list[dict]) -> list[dict]:
    """Golden prototype paths as engine routes: an ineligible path is failed at gate 0 with its reason."""
    out = []
    for p in paths:
        r = mk_route({"id": p["k"], "why": p["why"], "terms": [term("x", 1, "sale")]})
        if not p["ok"]:
            fail(r, 0, p["why"])
        out.append(r)
    return out


def _as_paths(routes: list[dict]) -> list[dict]:
    return [{"k": r["id"], "ok": not r["excluded"], "why": r["failReason"] if r["excluded"] else r["why"]} for r in routes]


def _before() -> dict[str, list[dict]]:
    """Each case's paths before any rule: the waived set restores them exactly."""
    return {c["id"]: c["paths"] for c in APPLY["cases"] if c["rule_set"] == "exclude_every_path"}


@pytest.mark.parametrize("i", range(len(APPLY["cases"])))
def test_apply_matches_golden(i):
    g = APPLY["cases"][i]
    routes = _stubs(_before()[g["id"]])
    out = apply_rules(EQUIP[g["id"]], routes, _rules(APPLY["rule_sets"][g["rule_set"]]), TF)
    assert out == RuleOutcome(g["result"]["ids"], g["result"]["pref"], bool(g["result"].get("waived")))
    assert _as_paths(routes) == g["paths"]


def test_exclude_reason_text():
    routes = _stubs([{"k": k, "ok": True, "why": "fine"} for k in TF.path_ids()])
    rule = CompiledRule("BR-07", {}, "exclude", "exit", "every return: never recycle")
    flow = CompiledRule("FLOW", {}, "exclude", "harvest", "removed from flow")
    out = apply_rules({"grade": "A"}, routes, [rule, flow], TF)
    by = {r["id"]: r for r in routes}
    assert by["exit"]["failReason"] == "Excluded by business rule BR-07: every return: never recycle"
    assert by["harvest"]["failReason"] == "Path removed from the published process flow"
    assert by["exit"]["failGate"] == POLICY == 2 and by["exit"]["gates"][2] == "fail"
    assert out == RuleOutcome(["BR-07"], None, False)


def test_exclude_covers_every_offer_of_the_path():
    """A hand-modelled case may offer one path twice (RT-1049 has two resale offers): an exclusion fails both."""
    routes = _stubs([{"k": k, "ok": True, "why": "fine"} for k in ("resale", "resale", "redeploy")])
    out = apply_rules({}, routes, [CompiledRule("IR-01", {}, "exclude", "resale", "every return: never resale")], IND)
    assert [r["excluded"] for r in routes] == [True, True, False]
    assert out == RuleOutcome(["IR-01"], None, False)


def test_require_excludes_others():
    routes = _stubs([{"k": k, "ok": k != "resell", "why": "x"} for k in TF.path_ids()])
    out = apply_rules({}, routes, [CompiledRule("BR-04", {}, "require", "refurb", "every return: only refurbish")], TF)
    assert out.ids == ["BR-04"]
    assert [r["id"] for r in routes if not r["excluded"]] == ["refurb"]
    by = {r["id"]: r for r in routes}
    assert by["release"]["failReason"] == "Business rule BR-04 sends this return to refurbish → place"
    assert by["resell"]["failReason"] == "x"  # already ineligible: untouched


def test_prefer_changes_recommendation_only_if_eligible():
    a, b, c = (
        mk_route({"id": k, "terms": [term("x", n, "sale")]}) for k, n in (("resale", 900), ("redeploy", 500), ("exit", 100))
    )
    routes = [a, b, c]
    out = apply_rules({}, routes, [CompiledRule("IR-01", {}, "prefer", "redeploy", "every return: prefer redeploy")], IND)
    assert out == RuleOutcome(["IR-01"], "redeploy", False)
    assert rank_routes(routes, prefer=out.preferred) is b
    assert [r["rank"] for r in routes] == [2, 1, 3]
    # a preferred route that is not eligible changes nothing
    fail(b, 3, "no demand")
    out = apply_rules({}, routes, [CompiledRule("IR-01", {}, "prefer", "redeploy", "x")], IND)
    assert out == RuleOutcome([], None, False)
    assert rank_routes(routes, prefer="redeploy") is a and [r["rank"] for r in routes] == [1, None, 2]


def test_all_excluded_is_waived():
    routes = _stubs([{"k": k, "ok": k in ("refurb", "exit"), "why": "gate"} for k in TF.path_ids()])
    before = copy.deepcopy(routes)
    rules = [CompiledRule("BR-01", {}, "exclude", "exit", "a"), CompiledRule("BR-02", {}, "exclude", "refurb", "b")]
    assert apply_rules({}, routes, rules, TF) == RuleOutcome([], None, True)
    assert routes == before


def test_in_scope_dimensions():
    dims = TF.dims
    c = {"cls": "CMH", "grade": None, "estGrade": "B", "ft": "Tool pool", "site": "Denver", "rul": 40}
    assert in_scope(c, {}, dims)
    assert in_scope(c, {"grade": ["B"], "cls": [], "site": ["Denver", "Houston"]}, dims)
    assert not in_scope(c, {"grade": ["A"]}, dims)
    assert not in_scope(c, {"rulMax": 40}, dims) and in_scope(c, {"rulMax": "41"}, dims)
    assert in_scope(c, {"rulMin": 40}, dims) and not in_scope(c, {"rulMin": 41}, dims)
    assert in_scope(c, {"rulMin": "", "rulMax": None}, dims)
    ind = {"cls": "motor", "grade": "C", "demand": {"site": "Site 2"}, "owner": "Customer A"}
    assert in_scope(ind, {"site": ["Site 2"], "owner": ["Customer A"]}, IND.dims)
    assert not in_scope(ind, {"owner": ["Customer B"]}, IND.dims)


@pytest.mark.parametrize("business", [None, []], ids=["none", "empty"])
def test_none_rules_keeps_engine_output(business):
    """Parity: the 128 book cases evaluate exactly as the golden with no business rules."""
    for g in CASES:
        facts, drafts, rules = book.inputs_of(g)
        routes, rec = evaluate(facts, drafts, rules, business=business, template=IND)
        assert routes == g["routes"], g["id"]
        assert rec == g.get("recommendation"), g["id"]
        assert ("rulesApplied" in facts) == (business is not None)
        if business is not None:
            assert facts["rulesApplied"] == [] and facts["preferred"] is None


def test_build_routes_applies_business_rules_after_the_gates():
    g = next(c for c in CASES if c["routes"] and not book.hand_modelled(c) and not c["blocked"])
    facts, _, _ = book.inputs_of(g)
    plain = build_routes(copy.deepcopy(facts), FormulaPredictor())
    assert "rulesApplied" not in facts
    target = next(r["id"] for r in plain if not r["excluded"])
    rule = CompiledRule("IR-01", {}, "exclude", target, "every return: never x")
    case = copy.deepcopy(facts)
    routes = build_routes(case, FormulaPredictor(), rules=[rule], template=IND)
    hit = next(r for r in routes if r["id"] == target)
    others = [r for r in routes if r["id"] != target]
    if any(not r["excluded"] for r in others):
        assert hit["excluded"] and hit["failGate"] == POLICY
        assert hit["failReason"] == "Excluded by business rule IR-01: every return: never x"
        assert case["rulesApplied"] == ["IR-01"] and case["rulesWaived"] is False
    else:
        assert case["rulesWaived"] is True
    assert others == [r for r in plain if r["id"] != target]
