"""MVP-2.3: a flow compiles into business rules (Domain spec D5; the prototype's compileEquip and ruleTextE)."""

from dataclasses import asdict

import pytest

from di.core import golden
from di.services.modeler.compile import CompiledRule, compile_flow, rule_text
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import load_template

CASES = golden.load("po/compile_cases")["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_compile_matches_golden(case):
    flow = {"nodes": case["flow"]["n"], "edges": case["flow"]["e"]}
    assert [asdict(r) for r in compile_flow(load_template("tool_fleet"), flow)] == case["rules"]


def test_compile_covers_the_five_flows():
    assert [c["name"] for c in CASES] == [
        "default", "r1_disconnected", "harvest_removed", "release_grade_c", "rule_without_path"
    ]  # fmt: skip


def test_industrial_default_compiles_to_nothing():
    t = load_template("industrial")
    assert compile_flow(t, default_flow(t)) == []


def test_device_default_compiles_its_rule():
    t = load_template("device")
    assert compile_flow(t, default_flow(t)) == [
        CompiledRule("DR-01", {"dohMin": 45}, "exclude", "buynow", "45+ days on hand: never Buy Now")
    ]


def test_rule_text_over_the_dims():
    tf, dev, ind = (load_template(k) for k in ("tool_fleet", "device", "industrial"))
    assert rule_text(tf, {"action": "require", "path": "refurb", "scope": {"cls": ["AGR"], "rulMax": 40}}) == (
        "angle grinders, under 40% life: only refurbish"
    )
    assert rule_text(tf, {"action": "prefer", "path": "resell", "scope": {"site": ["Denver"], "rulMin": 60.0}}) == (
        "at Denver, 60%+ life: prefer pre-owned sale"
    )
    assert rule_text(tf, {"action": "exclude", "path": "nowhere", "scope": {}}) == "every return: never ?"
    assert rule_text(dev, {"action": "require", "path": "auction", "scope": {"brand": ["Apple"], "band": ["49m+"]}}) == (
        "Apple, 49m+ age: only Auction"
    )
    assert rule_text(ind, {"action": "exclude", "path": "exit", "scope": {"cls": ["motor"], "owner": ["Customer A"]}}) == (
        "industrial motors, for Customer A: never responsible exit"
    )
