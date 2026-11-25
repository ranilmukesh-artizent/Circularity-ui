"""P9-2.2 (story X-05): the AgentLoop port and its Pydantic AI adapter (registry entry I-8).

Every model here is a `FunctionModel` (R16): no test reaches a provider. The tests play the worker
(runtime.run_until_blocked) for runs, and call `PydanticAILoop.run` directly for the loop's own behaviour. The starting
state is restored before and after each test.
"""

import json
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelResponse, ToolCallPart, ToolReturnPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import playbook_versions, runtime
from di.services.agents.loop import LoopResult, LoopSpec
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from tests import starting
from tests.helpers import call

models.ALLOW_MODEL_REQUESTS = False  # a test that built a real model would fail, not call a provider

AGENT = {"id": "ext-autopilot", "name": "Autopilot", "tools": [], "autonomy": "propose"}
CASE = "RT-1048"
BLOCKED = "RT-1051"  # evidence is missing: evidence.request has something to ask
PB = "loop_test_playbook"


class Out(BaseModel):
    summary: str


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run"))  # the messages and steps cascade
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    runtime.set_loop(None)
    for v in ("1", "2"):
        playbook_versions.unregister(PB, v)
    starting.reset()
    _clean()


def spec(tools: tuple[str, ...] = (), version: str = "1", **kw: Any) -> LoopSpec:
    return LoopSpec(playbook=PB, version=version, instructions="Test playbook.", output_type=Out, tools=tools, **kw)


def register(autonomy: str = "propose") -> None:
    assert call("agent.register", {**AGENT, "autonomy": autonomy}, "admin")["ok"] is True


def start(case: str = CASE, account: str = "admin") -> str:
    if not playbook_versions.known(PB):
        playbook_versions.register(PB, "1", spec)
    with SessionLocal() as s:
        run_id = runtime.start(s, "ext-autopilot", PB, case, account=account)
        s.commit()
    return run_id


def final(info: AgentInfo, summary: str = "done") -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": summary})])


class Script:
    """A scripted model: `turns` is a list of functions (messages, info) -> ModelResponse, one per model request."""

    def __init__(self, *turns: Any) -> None:
        self.turns, self.seen = list(turns), []

    def __call__(self, messages: list, info: AgentInfo) -> ModelResponse:
        self.seen.append(messages)
        return self.turns[len(self.seen) - 1](info) if len(self.seen) <= len(self.turns) else final(info)

    def model(self) -> FunctionModel:
        return FunctionModel(self)


def tool_call(name: str, args: dict, call_id: str):
    return lambda _info: ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=call_id)])


def drive(run_id: str) -> dict:
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
        return run(run_id)


def run(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def messages_rows(run_id: str) -> int:
    with SessionLocal() as s:
        return int(s.execute(text("SELECT count(*) FROM agent_run_message WHERE run_id = :r"), {"r": run_id}).scalar_one())


def loop_run(script: Script, run_id: str, tools: tuple[str, ...], resume: dict | None = None, **kw: Any) -> LoopResult:
    """The loop alone, on an existing run."""
    with SessionLocal() as s:
        ctx = runtime._context(s, runtime.get(s, run_id))
        return PydanticAILoop(lambda _s, _run, _role: script.model()).run(s, spec(tools, **kw), "Go.", ctx=ctx, resume=resume)


def tool_returns(messages: list) -> list[ToolReturnPart]:
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def test_x_05_accept_resumes_with_person_result_no_rerun():
    register("propose")
    playbook_versions.register(PB, "1", lambda: spec(("evidence.request",)))
    script = Script(tool_call("evidence_request", {"case_id": BLOCKED}, "tc1"))
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: script.model()))
    run_id = start(BLOCKED, "planner-a")
    r = drive(run_id)
    assert r["status"] == "waiting" and r["state"]["waiting"] == "proposal"
    ((call_id, pid),) = r["state"]["deferred"].items()
    assert call_id == "tc1" and len(script.seen) == 1
    # a person other than the one the run acts for accepts: the held action runs as them
    assert call("proposal.accept", {"id": pid}, "admin")["ok"] is True
    assert run(run_id)["status"] == "running"
    r = drive(run_id)
    assert r["status"] == "done" and r["state"]["output"] == {"summary": "done"}
    with SessionLocal() as s:
        accepted = s.execute(text("SELECT result FROM agent_proposal WHERE id = :i"), {"i": pid}).scalar_one()["output"]
        rows = s.execute(text("SELECT actor, preparer FROM action_journal WHERE action = 'evidence.request'")).all()
    assert [tuple(x) for x in rows] == [("admin", "ext-autopilot")]  # once: the tool was not invoked again
    (ret,) = tool_returns(script.seen[1])
    assert ret.tool_call_id == "tc1" and ret.content == accepted and len(script.seen) == 2


def test_x_05_rejected_deferred_call_stops_the_run():
    register("propose")
    playbook_versions.register(PB, "1", lambda: spec(("evidence.request",)))
    runtime.set_loop(
        PydanticAILoop(lambda _s, _run, _role: Script(tool_call("evidence_request", {"case_id": BLOCKED}, "tc1")).model())
    )
    run_id = start(BLOCKED, "planner-a")
    pid = next(iter(drive(run_id)["state"]["deferred"].values()))
    assert call("proposal.reject", {"id": pid, "reason": "Not this one, thanks."}, "admin")["ok"] is True
    r = run(run_id)
    assert r["status"] == "stopped" and r["state"]["reason"] == "A person rejected the proposal."


def test_loop_idem_key_is_run_and_tool_call():
    register("act")
    playbook_versions.register(PB, "1", lambda: spec(("comment.add",)))
    run_id = start()
    args = {"key": CASE, "text": "Reviewed by the agent."}
    first = Script(tool_call("comment_add", args, "tc1"))
    loop_run(first, run_id, ("comment.add",))
    with SessionLocal() as s:
        keys = list(s.execute(text("SELECT idem_key FROM action_journal WHERE action = 'comment.add'")).scalars())
    assert len(keys) == 1 and keys[0].endswith(f"{run_id}:tc1")
    again = Script(tool_call("comment_add", args, "tc1"))
    loop_run(again, run_id, ("comment.add",))
    assert str(tool_returns(again.seen[1])[0].content).startswith("Already done")
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM action_journal WHERE action = 'comment.add'")).scalar_one() == 1


def test_loop_persists_each_turn():
    register("act")
    playbook_versions.register(PB, "1", lambda: spec(("comment.add",)))
    run_id = start()
    args = {"key": CASE, "text": "Reviewed by the agent."}
    loop_run(Script(tool_call("comment_add", args, "tc1")), run_id, ("comment.add",))
    assert messages_rows(run_id) == 2


def test_loop_crash_after_turn_one_repeats_one_model_call():
    register("act")
    playbook_versions.register(PB, "1", lambda: spec(("comment.add",)))
    run_id = start()
    args = {"key": CASE, "text": "Reviewed by the agent."}

    def killed(_info: AgentInfo) -> ModelResponse:
        raise KeyboardInterrupt("the worker was killed")

    with pytest.raises(KeyboardInterrupt):
        loop_run(Script(tool_call("comment_add", args, "tc1"), killed), run_id, ("comment.add",))
    assert messages_rows(run_id) == 1
    again = Script()  # answers with the final output at once
    out = loop_run(again, run_id, ("comment.add",), resume={})
    assert len(again.seen) == 1 and out.output == Out(summary="done")  # one more model request, not two
    assert messages_rows(run_id) == 2
    assert "tc1" in [p.tool_call_id for p in tool_returns(again.seen[0])]


def test_loop_pinned_playbook_version():
    register("act")
    playbook_versions.register(PB, "1", lambda: spec(version="1"))
    run_id, second = start(), start()  # both start on v1
    playbook_versions.register(PB, "2", lambda: spec(version="2"))
    seen: list[str] = []

    class Fake:
        def run(self, s, sp, prompt, *, ctx, resume=None):
            seen.append(sp.version)
            return LoopResult(output=Out(summary="ok"), model="fake")

    runtime.set_loop(Fake())
    assert drive(run_id)["status"] == "done" and seen == ["1"]  # v1 although v2 is the latest
    playbook_versions.unregister(PB, "1")
    r = drive(second)
    assert r["status"] == "stopped"
    assert r["state"]["reason"] == "The playbook changed since this run started (v1, now v2)."
    assert seen == ["1"]


def test_loop_untrusted_tool_taints():
    register("act")
    run_id = start()
    args = {"key": CASE, "text": "Reviewed by the agent."}
    assert loop_run(Script(tool_call("comment_add", args, "tc1")), run_id, ("comment.add",)).tainted is False
    other = start()
    r = loop_run(
        Script(tool_call("comment_add", args, "tc2")), other, ("comment.add",), untrusted_tools=frozenset({"comment.add"})
    )
    assert r.tainted is True


def test_loop_spec_refuses_forbidden_tool():
    with pytest.raises(ValueError, match="decision.approve"):
        spec(("decision.approve",))
    with pytest.raises(ValueError, match="no.such.action"):
        spec(("no.such.action",))


def test_loop_ask_person_defers_a_question():
    register("act")
    run_id = start()
    script = Script(tool_call("ask_person", {"question": "Which site?"}, "q1"))
    r = loop_run(script, run_id, ("ask_person",))
    assert r.output is None and [(d.kind, d.question, d.proposal_id) for d in r.deferred] == [("question", "Which site?", None)]
    plain = Script()
    loop_run(plain, run_id, ())  # without it the model is offered no such tool
    assert json.dumps(plain.seen[0], default=str).find("ask_person") == -1


def test_loop_no_model_returns_none():
    register("act")
    run_id = start()
    with SessionLocal() as s:
        ctx = runtime._context(s, runtime.get(s, run_id))
        r = PydanticAILoop(lambda _s, _run, _role: None).run(s, spec(), "Go.", ctx=ctx)
    assert r.output is None and r.model is None and r.deferred == []
    assert messages_rows(run_id) == 0


def test_loop_refusal_retries_then_fails_the_run():
    register("act")
    playbook_versions.register(PB, "1", lambda: spec(("evidence.request",)))
    # RT-1048 has no missing evidence: evidence.request refuses every time
    bad = tool_call("evidence_request", {"case_id": CASE}, "tc1")
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: Script(bad, bad, bad, bad).model()))
    r = drive(start())
    assert r["status"] == "failed" and "The model loop failed" in r["state"]["reason"]
