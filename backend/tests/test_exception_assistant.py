"""P9-2.10 (enabler: decision D1, the exception assistant replaces `case_planner`; registry I-8, I-9, I-20).

An exception item of My work gets a draft (cause, recommended action, owner role) with the facts and sources behind it.
Without a model it is complete from the pack (R16); with one the model only words the cause. It reads and proposes: nothing
here resolves or hands on an item (golden rule 10). Every model is a `FunctionModel` (no test reaches a provider). Every test
ends with the starting state."""

from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import exception_assistant, runtime
from di.services.agents.playbooks import exception_writer
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.cases import process
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, client, h

models.ALLOW_MODEL_REQUESTS = False

A_CASE = "RT-1051"  # Customer A
CONTRACT = "no_active_contract"  # a tool fleet pack exception type: owner Planner, "Find the contract or hold the return"
SERIAL_FACT = "Serial PMP-0470 has no active contract in the contract system"


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item"))
        s.execute(text("DELETE FROM agent_run"))  # the messages cascade
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)
    _clean()
    starting.reset()


def _template(case_id: str, template: str) -> None:
    with SessionLocal() as s:
        s.execute(
            text("UPDATE case_record SET data = jsonb_set(data, '{template}', CAST(:t AS jsonb)) WHERE id = :c"),
            {"t": f'"{template}"', "c": case_id},
        )
        s.commit()


def _open(type_: str = CONTRACT, cause: str | None = SERIAL_FACT, case_id: str = A_CASE, org: str = "Customer A") -> int:
    with SessionLocal() as s:
        item = process.open_item(
            s, kind="exception", case_id=case_id, org_unit_id=org, type=type_, title="Exception", cause=cause,
            action="x", owner_role="Planner", due_hours=None, by="system",
        )  # fmt: skip
        s.commit()
    return item


def _model(*turns: Any) -> PydanticAILoop:
    seen: list = []

    def fn(_messages: list, info: AgentInfo) -> ModelResponse:
        seen.append(1)
        return turns[min(len(seen), len(turns)) - 1](info)

    return PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn))


def _final(cause: str, **extra: Any):
    return lambda info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"cause": cause, **extra})])


def _tool(name: str, args: dict[str, Any]):
    return lambda _info: ModelResponse(parts=[ToolCallPart(name, args)])


def _runs() -> list[dict[str, Any]]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("SELECT * FROM agent_run ORDER BY created_at")).mappings()]


def test_exception_assistant_deterministic_draft():
    """No model and no key: the owner and action are the pack's, and the cause names the serial's facts and sources."""
    _template(A_CASE, "tool_fleet")
    item = _open()
    r = call("exception.explain", {"exception_id": item}, "planner.a")
    assert r["ok"] is True, r
    d = r["output"]
    assert (d["owner_role"], d["recommended_action"], d["by_model"]) == ("Planner", "Find the contract or hold the return", False)
    assert d["cause"].startswith("No active contract for the serial: ")
    assert "PMP-0470" in d["cause"] and "no active contract in the contract system" in d["cause"]
    by_source = {s["source"]: s["fact"] for s in d["sources"]}
    assert by_source["case record"].endswith("PMP-0470") and by_source[f"work item {item}"] == SERIAL_FACT
    assert all(s["at"] for s in d["sources"])
    assert _runs() == []  # no model took part: no run is kept


def test_exception_assistant_unknown_type_keeps_the_item_words():
    item = _open(type_="not_in_the_pack")  # the industrial pack has no exception types
    d = call("exception.explain", {"exception_id": item}, "planner.a")["output"]
    assert d["owner_role"] == "Planner" and d["recommended_action"] == "x" and d["by_model"] is False


def test_exception_assistant_model_words_only():
    """A model that also tries to set another owner and action: both stay the pack's; only the cause is replaced."""
    _template(A_CASE, "tool_fleet")
    item = _open()
    runtime.set_loop(_model(_tool("case_get", {"case_id": A_CASE}), _final("The serial has no contract.", owner_role="Admin",
                                                                          recommended_action="Close the case")))  # fmt: skip
    r = call("exception.explain", {"exception_id": item}, "planner.a")
    assert r["ok"] is True, r
    d = r["output"]
    assert d["cause"] == "The serial has no contract." and d["by_model"] is True
    assert (d["owner_role"], d["recommended_action"]) == ("Planner", "Find the contract or hold the return")
    runs = _runs()
    assert [(x["agent"], x["playbook"], x["status"]) for x in runs] == [("recover-exceptions", "exception_writer", "done")]


def test_exception_assistant_tools_read_only():
    """The toolset holds only reads: a write is refused when the spec is built, and a model that calls one anyway gets no
    tool, so the deterministic draft stands and nothing is decided."""
    spec = exception_writer.spec()
    assert spec.tools == ("case.get", "case.evidence", "case.trace") and spec.output_type is exception_writer.ExceptionWords
    from di.services.actions.registry import ACTIONS

    assert all(ACTIONS[t].risk == "read" for t in spec.tools)
    for bad in ("decision.submit", "work.resolve", "work.assign", "decision.approve"):
        with pytest.raises(ValueError, match="read-only"):
            exception_writer.build_spec(("case.get", bad))
    _template(A_CASE, "tool_fleet")
    item = _open()
    runtime.set_loop(_model(_tool("decision_submit", {"case_id": A_CASE, "route": "resell"})))
    d = call("exception.explain", {"exception_id": item}, "planner.a")["output"]
    assert d["by_model"] is False and d["owner_role"] == "Planner"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM action_journal WHERE action LIKE 'decision.%'")).scalar_one() == 0
        assert s.execute(text("SELECT status FROM work_item WHERE id = :i"), {"i": item}).scalar_one() == "open"
    assert _runs() == []


def test_exception_assistant_writer_needs_a_run():
    pack = load_pack("tool_fleet")
    exc = {"id": 1, "type": CONTRACT, "title": "t", "cause": None, "owner_role": "Planner", "case_id": None}
    plain = exception_assistant.draft_exception(exc, {}, pack, writer=None)
    assert plain.owner_role == "Planner" and plain.cause == "No active contract for the serial"
    with pytest.raises(ValueError, match="agent run"):
        exception_assistant.draft_exception(exc, {}, pack, writer=PydanticAILoop(lambda *_: None))


def test_exception_explain_tenant_boundary():
    item = _open()
    r = call("exception.explain", {"exception_id": item}, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert call("exception.explain", {"exception_id": item}, "planner.a")["ok"] is True


def test_exception_explain_needs_an_exception():
    assert call("exception.explain", {"exception_id": 999999}, "planner.a")["error"]["code"] == "not_found"
    with SessionLocal() as s:
        step = process.open_item(
            s, kind="needs_info", case_id=A_CASE, org_unit_id="Customer A", type="needs_info", title="Q", cause="why",
            action=None, owner_role="Planner", due_hours=None, by="system",
        )  # fmt: skip
        s.commit()
    assert call("exception.explain", {"exception_id": step}, "planner.a")["error"]["code"] == "not_found"


def test_exception_assistant_agent_reads_and_never_resolves():
    """The agent may call the read; resolving and handing on stay a person's, whoever prepares the call (rule 10)."""
    item = _open()
    head = h("admin") | {"X-Circularity-Preparer": "recover-exceptions"}
    r = client.post("/api/actions/exception.explain", json={"exception_id": item}, headers=head).json()
    assert r["ok"] is True, r
    for action, body in (
        ("work.resolve", {"item_id": item, "outcome": "done"}),
        ("work.assign", {"item_id": item, "account": "planner.a"}),
    ):
        out = client.post(f"/api/actions/{action}", json=body, headers=head).json()
        assert out["ok"] is False, action
    with SessionLocal() as s:
        row = s.execute(text("SELECT status, owner_account FROM work_item WHERE id = :i"), {"i": item}).one()
    assert tuple(row) == ("open", None)
