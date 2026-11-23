"""Can a rule suggestion (MVP-12.3) be fed to build_proposal (MVP-5.2) by its text? Only if the parser reads every
suggestion's text back to the suggested rule. It does for industrial and device; it does not for tool_fleet, whose
parser (parseEquip) reads "tool pool" as the return channel Tool pool (PO golden README note 4), so a suggestion to
the tool pool would come back with another scope. flow.suggestions therefore keeps placing the rule itself."""

import pytest

from di.services.modeler.parse import ParsedRule, parse_rule
from di.services.modeler.templates import load_template
from di.services.modeler.text import rule_text


def _suggestion_rules(key: str):
    """Every rule suggest() can make: prefer one path for one value of one set dimension."""
    t = load_template(key)
    for d in (d for d in t.dims if d.kind == "set"):
        for v in d.values:
            for p in t.path_ids():
                yield t, {"action": "prefer", "path": p, "scope": {d.key: [v]}}


@pytest.mark.parametrize("key", ["industrial", "device"])
def test_suggestion_text_reads_back_to_the_rule(key):
    for t, rule in _suggestion_rules(key):
        text = rule_text(t, rule)
        assert parse_rule(t, text) == ParsedRule(rule["path"], rule["action"], rule["scope"]), text


def test_tool_fleet_suggestions_do_not_read_back():
    t = load_template("tool_fleet")
    rule = {"action": "prefer", "path": "redeploy", "scope": {"cls": ["CMH"]}}
    assert rule_text(t, rule) == "combihammers: prefer tool pool"
    assert parse_rule(t, rule_text(t, rule)) == ParsedRule(None, "prefer", {"cls": ["CMH"], "ft": ["Tool pool"]})
