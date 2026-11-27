"""ai-tasks I10: flow.propose is MODEL-FIRST. The guardrail wall (code) comes first, then a model reads the sentence into a typed
`FlowReading` (playbook `flow_reader`), code checks it (`flow_reader.problems`), and only when no model answers does the pattern
parser answer (`read_by: "rules"`). The model here is always a `FunctionModel` behind a fake loop, never a live provider."""
# ruff: noqa: E501 - long lines in the readings

from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel

from di.services.agents import runtime
from di.services.agents.playbooks import flow_reader
from di.services.agents.playbooks.flow_reader import FlowReading, RuleRead, StepRead
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler.flow import default_flow
from di.services.modeler.parse import parse_rule
from di.services.modeler.propose import build_proposal
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok
from tests.helpers import call

models.ALLOW_MODEL_REQUESTS = False
SENTENCE = "Never recycle construction lasers"  # the parser reads a path and a scope from it (golden BR-03)
UNCLEAR = "Prefer tool pool for grade A or B from Repair center"  # the parser finds no path (PO golden, README 4)
T = load_template("tool_fleet")


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    flowkit.reset_flows()
    monkeypatch.setattr(flow_reader, "_model_ready", lambda: True)  # a model is configured for the role
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model unless a test installs one
    yield
    runtime.set_loop(None)
    flowkit.reset_flows()


def scripted(outputs: list[dict[str, Any]], seen: list[str] | None = None) -> list[int]:
    """Install a model that answers with `outputs` in turn (the last repeats); returns the list of its calls."""
    calls: list[int] = []

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(str(messages))
        out = outputs[min(len(calls), len(outputs) - 1)]
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn)))
    return calls


def _propose(text: str, flow: str = "tool_fleet") -> dict:
    return ok(call("flow.propose", {"flow_id": flowkit.flow_id(flow, "workspace"), "text": text}, "admin"))


def _node(out: dict) -> dict:
    return next(n for n in out["graph"]["nodes"] if n["id"] == out["node_id"])


def _unsaved() -> None:
    f, _ = flowkit.get(flowkit.flow_id("tool_fleet", "workspace"))
    assert (f.status, f.draft) == ("pub", None)


def _rule(path: str, action: str = "exclude", **scope: Any) -> dict[str, Any]:
    return {"path": path, "action": action, "scope": scope}


PARSED = parse_rule(T, SENTENCE)


def test_one_rule_reading_becomes_a_rule_proposal():
    calls = scripted([{"kind": "rules", "rules": [_rule("harvest", cls=["LSR"])]}])
    out = _propose(SENTENCE)
    assert calls == [1]
    assert (out["kind"], out["read_by"], out["rid"]) == ("rule", "model", "BR-03")
    assert out["sim"]["kind"] == "equip" and out["sim"]["n"] >= 26  # simulated on the open queue
    assert out["note"] == "Proposed by the assistant: " + SENTENCE
    node = _node(out)
    assert (node["path"], node["action"], node["scope"]["cls"]) == ("harvest", "exclude", ["LSR"])
    _unsaved()


def test_two_rule_reading_is_one_proposal_naming_both():
    scripted([{"kind": "rules", "rules": [_rule("harvest", cls=["LSR"]), _rule("redeploy", "prefer", grade=["A"])]}])
    out = _propose("Never recycle lasers, and prefer redeploying grade A")
    assert (out["kind"], out["read_by"], out["rid"]) == ("rule", "model", "BR-03, BR-04")
    assert out["label"].count("BR-0") == 2 and "; " in out["label"]
    assert out["label"].startswith("BR-03: ") and "BR-04: " in out["label"]
    rids = [n.get("rid") for n in out["graph"]["nodes"]]
    assert "BR-03" in rids and "BR-04" in rids
    _unsaved()


def test_step_reading_adds_a_step():
    scripted([{"kind": "step", "step": {"name": "Photo check", "after": "harvest"}}])
    out = _propose("We should photograph tools before they go to parts")
    assert (out["kind"], out["read_by"]) == ("step", "model")
    assert "Photo check" in out["label"]
    assert any(n.get("label") == "Photo check" for n in out["graph"]["nodes"])
    _unsaved()


def test_guardrail_reading_is_blocked_with_its_id_and_no_graph():
    scripted([{"kind": "guardrail", "guardrail": "GR-01", "message": "It would waive refurbishment."}])
    out = _propose("Issue grade C tools to the fleet as they are")
    assert (out["kind"], out["guard"], out["graph"], out["sim"], out["read_by"]) == ("blocked", "GR-01", None, None, "model")
    assert "GR-01" in out["msg"]
    _unsaved()


def test_unclear_reading_returns_the_models_question():
    scripted([{"kind": "unclear", "message": "Which path should it prefer: refurbish or redeploy?"}])
    out = _propose(UNCLEAR)
    assert (out["kind"], out["read_by"], out["graph"]) == ("unclear", "model", None)
    assert out["msg"] == "Which path should it prefer: refurbish or redeploy?"
    _unsaved()


def test_bad_reading_is_retried_once_with_the_errors_then_the_parser_answers():
    seen: list[str] = []
    calls = scripted([{"kind": "rules", "rules": [_rule("nonsuch", cls=["LSR"])]}], seen)  # the same bad reading twice
    out = _propose(SENTENCE)
    assert calls == [1, 1]  # first reading and one repair, no third
    assert "is not a path id" in seen[1] and "is not a path id" not in seen[0]  # the retry names the error
    assert out["read_by"] == "rules"
    p = build_proposal(T, default_flow(T), SENTENCE, "Fleet desk", None)
    assert (
        (out["kind"], out["rid"], out["label"])
        == (p.kind, p.rid, p.label)
        == ("rule", "BR-03", "BR-03: construction lasers: never recycle")
    )
    _unsaved()


def test_bad_then_good_reading_is_used():
    calls = scripted(
        [{"kind": "rules", "rules": [_rule("nonsuch")]}, {"kind": "rules", "rules": [_rule("harvest", cls=["LSR"])]}]
    )
    out = _propose(SENTENCE)
    assert calls == [1, 1]
    assert (out["kind"], out["read_by"]) == ("rule", "model")


def test_no_model_output_gives_the_parser_answer():
    out = _propose(SENTENCE)  # the fake loop has no model
    assert (out["kind"], out["read_by"], out["rid"]) == ("rule", "rules", "BR-03")
    assert out["label"] == "BR-03: construction lasers: never recycle"
    out = _propose(UNCLEAR)
    assert (out["kind"], out["read_by"]) == ("unclear", "rules")
    assert out["msg"].startswith("I couldn't tell which path this is about.")
    _unsaved()


def test_a_failing_model_gives_the_parser_answer():
    def boom(messages: list, info: AgentInfo) -> ModelResponse:
        raise RuntimeError("provider down")

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(boom)))
    out = _propose(SENTENCE)
    assert (out["kind"], out["read_by"], out["rid"]) == ("rule", "rules", "BR-03")


def test_no_model_ready_never_runs_the_loop(monkeypatch):
    monkeypatch.setattr(flow_reader, "_model_ready", lambda: False)
    calls = scripted([{"kind": "unclear", "message": "?"}])
    out = _propose(SENTENCE)
    assert calls == [] and out["read_by"] == "rules"


@pytest.mark.parametrize("text", ["Skip approval for grade A", "Lower the threshold for refurb to stock"])
def test_a_guardrail_weakening_text_never_asks_the_model(text):
    calls = scripted([{"kind": "rules", "rules": [_rule("harvest")]}])
    out = _propose(text)
    assert calls == []
    assert (out["kind"], out["read_by"], out["graph"], out["sim"]) == ("blocked", "guard", None, None)
    assert out["guard"] in {"GR-05", "GR-03"}
    _unsaved()


def test_scope_the_model_left_out_is_put_back():
    assert PARSED.scope  # the parser finds the qualifier the model leaves out
    scripted([{"kind": "rules", "rules": [_rule(PARSED.path or "harvest")]}])  # no scope at all
    out = _propose(SENTENCE)
    assert out["read_by"] == "model"
    node = _node(out)
    assert node["scope"] == PARSED.scope


def test_scope_the_model_gave_wins_over_the_parser():
    scripted([{"kind": "rules", "rules": [_rule("harvest", cls=["BRK"])]}])
    out = _propose(SENTENCE)
    node = _node(out)
    assert node["scope"].get("cls") == ["BRK"]  # setdefault: only keys the model left out come back


def test_the_agent_run_of_a_failed_reading_is_not_kept():
    from sqlalchemy import text

    from di.core.db import SessionLocal

    with SessionLocal() as s:
        before = s.execute(text("SELECT count(*) FROM agent_run WHERE playbook = 'flow_reader'")).scalar_one()
    _propose(SENTENCE)  # no model output
    with SessionLocal() as s:
        after = s.execute(text("SELECT count(*) FROM agent_run WHERE playbook = 'flow_reader'")).scalar_one()
    assert after == before


# ---------------------------------------------------------------- flow_reader.problems (pure)
DRAFT = default_flow(T)


def _bad(r: FlowReading) -> list[str]:
    return flow_reader.problems(r, T, DRAFT)


def test_problems_accepts_a_good_reading():
    r = FlowReading(kind="rules", rules=[RuleRead(path="harvest", action="exclude", scope={"cls": ["LSR"], "rulMax": 20})])
    assert _bad(r) == []
    assert _bad(FlowReading(kind="step", step=StepRead(name="Photo check", after="harvest"))) == []
    assert _bad(FlowReading(kind="guardrail", guardrail="GR-01")) == []
    assert _bad(FlowReading(kind="guardrail")) == []
    assert _bad(FlowReading(kind="unclear", message="Which path?")) == []


def test_problems_rules():
    assert any("at least one rule" in p for p in _bad(FlowReading(kind="rules")))
    assert any("not a path id" in p for p in _bad(FlowReading(kind="rules", rules=[RuleRead(path="nope", action="require")])))
    r = FlowReading(kind="rules", rules=[RuleRead(path="harvest", action="require", scope={"colour": ["red"]})])
    assert any("not a dimension" in p for p in _bad(r))
    for v in (["Z"], "A", [], ["A", "Z"]):  # a value outside the set, not a list, empty, a partly wrong list
        r = FlowReading(kind="rules", rules=[RuleRead(path="harvest", action="require", scope={"grade": v})])
        assert any("scope.grade must be a list" in p for p in _bad(r)), v
    for v in ("lots", True, ["20"]):  # a number dimension takes a number
        r = FlowReading(kind="rules", rules=[RuleRead(path="harvest", action="require", scope={"rulMax": v})])
        assert any("scope.rulMax must be a number" in p for p in _bad(r)), v


def test_problems_step_guardrail_unclear():
    r = FlowReading(kind="step", step=StepRead(name="Photo check", after="nowhere"))
    assert any("not a path of this flow" in p for p in _bad(r))
    assert any("needs step.name" in p for p in _bad(FlowReading(kind="step")))
    assert any("needs step.name" in p for p in _bad(FlowReading(kind="step", step=StepRead(name="  ", after="harvest"))))
    assert any("not a guardrail id" in p for p in _bad(FlowReading(kind="guardrail", guardrail="GR-99")))
    assert any("needs the one question" in p for p in _bad(FlowReading(kind="unclear")))
    assert any("needs the one question" in p for p in _bad(FlowReading(kind="unclear", message="  ")))
