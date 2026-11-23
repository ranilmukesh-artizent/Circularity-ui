"""MVP-2.6: guardrail checks on rules (ruleGuardE / ruleGuardD) and on plain-language text (textGuard), Domain spec D8."""

import pytest

from di.core import golden
from di.services.modeler.guard import rule_breaks, text_breaks
from di.services.modeler.templates import load_template

CASES = golden.load("po/textguard_cases")["cases"]
PO_KEY = {"equip": "tool_fleet", "device": "device"}


@pytest.mark.parametrize("case", CASES, ids=[c["text"] for c in CASES])
def test_textguard_matches_golden(case):
    for po, key in PO_KEY.items():
        assert text_breaks(load_template(key), case["text"]) == case[po], (key, case["text"])


def test_textguard_patterns():
    tf, dev, ind = (load_template(k) for k in ("tool_fleet", "device", "industrial"))
    assert text_breaks(tf, "Send refurbished tools to stock") == "GR-02"
    assert text_breaks(tf, "Change the holding cost") == "GR-04"
    assert text_breaks(tf, "Auto-approve resale under $500") == "GR-05"
    assert text_breaks(tf, "Never refurbish grade C") is None
    assert text_breaks(dev, "List without a wipe certificate") == "GR-D1"
    assert text_breaks(dev, "Lower the recovery floor") == "GR-D2"
    assert text_breaks(dev, "Raise the lot size for auction") == "GR-D4"
    assert text_breaks(dev, "Let Marketplace undercut Buy Now") == "GR-D5"
    assert text_breaks(ind, "Approve redeploys without approval") == "GR-I5"
    assert text_breaks(ind, "Never resell motors") is None


def test_release_grade_c_breaks_gr01():
    tf = load_template("tool_fleet")
    assert rule_breaks(tf, {"path": "release", "action": "prefer", "scope": {"grade": ["C"]}}) == "GR-01"
    assert rule_breaks(tf, {"path": "release", "action": "require", "scope": {"grade": ["A", "D"]}}) == "GR-01"
    assert rule_breaks(tf, {"path": "release", "action": "exclude", "scope": {"grade": ["C"]}}) is None
    assert rule_breaks(tf, {"path": "release", "action": "prefer", "scope": {"grade": ["A", "B"]}}) is None
    assert rule_breaks(tf, {"path": "release", "action": "prefer", "scope": {}}) is None
    assert rule_breaks(tf, {"path": "refurb", "action": "prefer", "scope": {"grade": ["C"]}}) is None
    dev = load_template("device")
    assert rule_breaks(dev, {"path": "market", "action": "require", "scope": {"grade": ["D"]}}) == "GR-D3"
    assert rule_breaks(dev, {"path": "auction", "action": "require", "scope": {"grade": ["D"]}}) is None
