"""MVP-5.1: plain-language rules read per template (Domain spec D10; the prototype's parseEquip and parseDevice)."""

import pytest

from di.core import golden
from di.services.modeler.parse import ParsedRule, parse_rule
from di.services.modeler.templates import load_template

CASES = golden.load("po/parse_cases")["cases"]
KEYS = {"equip": "tool_fleet", "device": "device"}


@pytest.mark.parametrize("kind", ["equip", "device"])
@pytest.mark.parametrize("i", range(len(CASES)))
def test_parse_matches_golden(i, kind):
    c = CASES[i]
    want = c[kind]
    got = parse_rule(load_template(KEYS[kind]), c["text"])
    assert got == ParsedRule(want["path"], want["action"], want["scope"]), c["text"]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Never send grade C industrial motors to material recovery",
         ParsedRule("material", "exclude", {"cls": ["motor"], "grade": ["C"]})),
        ("Only re-lease hydraulic pumps at Pune Works for Customer A",
         ParsedRule("relase", "require", {"cls": ["pump"], "site": ["Site 1"], "owner": ["Customer A"]})),
        ("Prefer selling parts of control units from Site 3",
         ParsedRule("extparts", "prefer", {"cls": ["control"], "site": ["Site 3"]})),
        ("Do not scrap power tools of grade A or B; use the parts internally",
         ParsedRule("material", "exclude", {"cls": ["drill"], "grade": ["A", "B"]})),
    ],
)  # fmt: skip
def test_industrial_parse_examples(text, want):
    assert parse_rule(load_template("industrial"), text) == want


def test_industrial_parts_and_no_path():
    t = load_template("industrial")
    assert parse_rule(t, "Prefer recovered parts for IT electronics").path == "intparts"
    assert parse_rule(t, "Prefer recovered parts for IT electronics").scope == {"cls": ["it"]}
    assert parse_rule(t, "Keep it simple for grade D") == ParsedRule(None, "prefer", {"grade": ["D"]})


def test_industrial_reads_other_dims_by_their_phrase():
    """A dim added to the pack (the telemetry alarm, MVP-7.1) is read by its rule-text phrase."""
    t = load_template("industrial")
    assert parse_rule(t, "Industrial motors with a telemetry alarm: never whole-asset resale").scope == {
        "cls": ["motor"], "alarm": ["yes"],
    }  # fmt: skip
    assert parse_rule(t, "Pumps without a telemetry alarm: prefer redeploy").scope == {"cls": ["pump"], "alarm": ["no"]}
