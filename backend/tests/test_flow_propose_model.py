"""MVP-5.3: an optional model reading for flow.propose. The parser's answer is complete without a key; the model only
fills what the parser left empty, with values the template allows."""

import pytest

from di.services.ask import modeler_read
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call

UNCLEAR = "Prefer tool pool for grade A or B from Repair center"  # the parser finds no path (PO golden, README 4)


@pytest.fixture(autouse=True)
def fresh_flows():
    flowkit.reset_flows()
    yield
    flowkit.reset_flows()


def _propose(text: str) -> dict:
    return ok(call("flow.propose", {"flow_id": flowkit.flow_id("tool_fleet", "workspace"), "text": text}, "admin"))


def test_model_fills_the_path(monkeypatch):
    calls = []

    def stub(key, system, text):
        calls.append(text)
        return {"path": "redeploy", "action": "require", "scope": {"grade": ["B", "Z"], "site": ["Houston"], "x": [1]}}

    monkeypatch.setattr(modeler_read, "_key", lambda: "test-key")
    monkeypatch.setattr(modeler_read, "_ask", stub)
    out = _propose(UNCLEAR)
    assert calls == [UNCLEAR]
    assert (out["kind"], out["read_by"], out["rid"]) == ("rule", "rules+model", "BR-03")
    node = next(n for n in out["graph"]["nodes"] if n["id"] == out["node_id"])
    # the path from the model; the action and the scope keys the parser read stay; only an empty scope key is filled
    assert (node["path"], node["action"]) == ("redeploy", "prefer")
    assert node["scope"] == {"ft": ["Repair center", "Tool pool"], "grade": ["A", "B"], "site": ["Houston"]}


def test_model_failure_keeps_the_parser_answer(monkeypatch):
    def boom(key, system, text):
        raise RuntimeError("down")

    monkeypatch.setattr(modeler_read, "_key", lambda: "test-key")
    monkeypatch.setattr(modeler_read, "_ask", boom)
    out = _propose(UNCLEAR)
    assert (out["kind"], out["read_by"]) == ("unclear", "rules")
    assert out["msg"].startswith("I couldn't tell which path this is about.")


def test_no_key_never_calls_the_model(monkeypatch):
    def never(key, system, text):
        raise AssertionError("the model was called")

    monkeypatch.setattr(modeler_read, "_key", lambda: "")
    monkeypatch.setattr(modeler_read, "_ask", never)
    assert _propose(UNCLEAR)["read_by"] == "rules"
    assert modeler_read.model_rule(UNCLEAR, load_template("tool_fleet")) == {}


def test_a_clear_sentence_never_asks_the_model(monkeypatch):
    def never(key, system, text):
        raise AssertionError("the model was called")

    monkeypatch.setattr(modeler_read, "_key", lambda: "test-key")
    monkeypatch.setattr(modeler_read, "_ask", never)
    assert _propose("Never recycle construction lasers")["read_by"] == "rules"


def test_checked_drops_what_the_template_does_not_allow():
    t = load_template("device")
    raw = {"path": "ebay", "action": "maybe", "scope": {"brand": ["Apple"], "dohMin": 30, "qtyMin": "lots", "band": []}}
    assert modeler_read.checked(raw, t) == {"scope": {"brand": ["Apple"], "dohMin": 30}}
