"""P9-2.6 (story X-05): run tracing and the agent run view (registry entry I-12).

Spans are written by `di.core.tracing` (no OpenTelemetry). A chain run leaves a `run`, `stage` and `action` spans; an LLM
run (a `FunctionModel` under a `test` provider row, R16) leaves `model` and `tool` spans; `agent.runTrace` reads it all.
"""

from datetime import timedelta

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core import tracing
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.agents import chain, playbook_versions, runtime
from di.services.agents.loop import LoopSpec
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.llm import router
from tests import starting
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

models.ALLOW_MODEL_REQUESTS = False
CASE = "RT-1048"  # Customer A's hero case; planner.b is Customer B's
PB = "trace_test_playbook"
SEED = "groq-default"


class Out(BaseModel):
    summary: str


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM trace_span"))
        s.execute(text("DELETE FROM agent_run"))
        s.execute(text("DELETE FROM agent_proposal"))
        s.execute(text("DELETE FROM llm_model WHERE id <> :i"), {"i": SEED})
        s.execute(text("DELETE FROM llm_budget"))
        s.execute(text("UPDATE llm_model SET enabled = true, cooldown_until = NULL WHERE id = :i"), {"i": SEED})
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    with SessionLocal() as s:
        s.execute(text("UPDATE llm_model SET enabled = false WHERE id = :i"), {"i": SEED})
        s.commit()
    yield
    runtime.set_loop(None)
    router.TEST_MODELS.clear()
    playbook_versions.unregister(PB, "1")
    get_settings.cache_clear()
    _clean()
    starting.reset()


def _spans(run_id: str | None = None, kind: str | None = None) -> list[dict]:
    q = "SELECT * FROM trace_span WHERE (CAST(:r AS text) IS NULL OR run_id = :r) AND (CAST(:k AS text) IS NULL OR kind = :k)"
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(q + " ORDER BY started_at"), {"r": run_id, "k": kind}).mappings()]


def _emit(name: str, *, kind: str = "tool", run_id: str | None = None, attrs: dict | None = None, fail: bool = False) -> str:
    """Write one span in its own session; returns its id."""
    with SessionLocal() as s, tracing.span(s, name, kind=kind, run_id=run_id, attrs=attrs) as sp:
        if fail:
            raise ValueError("bad thing")
    return sp.span_id


def test_x_05_trace_spans_for_chain_run():
    with SessionLocal() as s:
        run = chain.run_chain(s, CASE, account="planner-a")
        s.commit()
        calls = s.execute(text("SELECT count(*) FROM agent_run_step WHERE run_id = :r"), {"r": run.run_id}).scalar_one()
    spans = _spans(run.run_id)
    kinds = [x["kind"] for x in spans]
    assert kinds.count("run") == 1
    assert kinds.count("stage") == len(run.stages) and len(run.stages) >= 5
    assert kinds.count("action") == calls >= 1
    assert all(x["attrs"]["di.run_id"] == run.run_id for x in spans)
    root = next(x for x in spans if x["kind"] == "run")
    assert root["parent_id"] is None and {x["trace_id"] for x in spans} == {root["trace_id"]}
    action = next(x for x in spans if x["kind"] == "action")
    stage_ids = {x["span_id"] for x in spans if x["kind"] == "stage"}
    assert action["parent_id"] in stage_ids and action["attrs"]["di.action"] and action["attrs"]["di.preparer"]


def _llm_run(tools: tuple[str, ...], fn) -> str:
    assert call("agent.register", {"id": "ext-autopilot", "name": "A", "tools": [], "autonomy": "act"}, "admin")["ok"]
    playbook_versions.register(
        PB, "1", lambda: LoopSpec(playbook=PB, version="1", instructions="x", output_type=Out, tools=tools)
    )
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO llm_model (id, provider, model, rpm, tpm, rpd, roles, priority) "
                "VALUES ('t-a', 'test', 't-a', 30, 8000, 1000, '{agent}', 1)"
            )
        )
        s.commit()
    router.TEST_MODELS["t-a"] = FunctionModel(fn)
    runtime.set_loop(PydanticAILoop())
    with SessionLocal() as s:
        run_id = runtime.start(s, "ext-autopilot", PB, CASE, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
    return run_id


def test_trace_model_span_attrs():
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": "done"})])

    run_id = _llm_run((), fn)
    (m,) = _spans(run_id, "model")
    assert m["attrs"]["gen_ai.usage.input_tokens"] > 0 and m["attrs"]["gen_ai.usage.output_tokens"] > 0
    assert m["attrs"]["di.model_route"] == "t-a" and m["status"] == "ok"


def test_trace_tool_span_under_model_span():
    n = {"i": 0}

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        n["i"] += 1
        if n["i"] == 1:
            return ModelResponse(parts=[ToolCallPart("case_evidence", {"case_id": CASE}, tool_call_id="c1")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": "done"})])

    run_id = _llm_run(("case.evidence",), fn)
    models_ = _spans(run_id, "model")
    (tool,) = _spans(run_id, "tool")
    assert len(models_) == 2 and tool["parent_id"] == models_[0]["span_id"]
    (action,) = _spans(run_id, "action")
    assert action["parent_id"] == tool["span_id"]


def test_trace_redacts_secrets():
    _emit("x", attrs={"api_key": "sk-1", "ok": 1, "nested": {"password": "p", "a": 2}})
    (row,) = _spans()
    assert "api_key" not in row["attrs"] and row["attrs"]["ok"] == 1
    assert row["attrs"]["nested"] == {"a": 2}


def test_trace_content_only_when_enabled(monkeypatch):
    def put() -> dict:
        sid = _emit("t", attrs={"content.input": {"q": 1}, "n": 1})
        return next(x for x in _spans() if x["span_id"] == sid)["attrs"]

    assert "content.input" not in put()
    monkeypatch.setattr(get_settings(), "trace_content", True)
    assert put()["content.input"] == {"q": 1}


def test_trace_error_status():
    with pytest.raises(ValueError, match="bad thing"):
        _emit("boom", fail=True)
    (row,) = _spans()
    assert (
        row["status"] == "error" and row["attrs"]["error.type"] == "ValueError" and "bad thing" in row["attrs"]["error.message"]
    )


def test_trace_prune_retention():
    with SessionLocal() as s:
        for name, days in (("old", 15), ("new", 13)):
            s.execute(
                text(
                    "INSERT INTO trace_span (span_id, trace_id, name, kind, started_at, ended_at, status) "
                    "VALUES (:n, :n, :n, 'tool', now() - make_interval(days => :d), now() - make_interval(days => :d), 'ok')"
                ),
                {"n": name, "d": days},
            )
        s.commit()
        assert tracing.prune(s, get_settings().trace_retention_days) == 1
        s.commit()
    assert [x["span_id"] for x in _spans()] == ["new"]


def test_run_trace_tenant_boundary():
    r = call("agent.runTrace", {"case_id": CASE}, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"


def test_run_trace_read_shape_and_permissions():
    with SessionLocal() as s:
        run = chain.run_chain(s, CASE, account="planner-a")
        s.commit()
    out = call("agent.runTrace", {"case_id": CASE}, "planner.a")
    assert out["ok"] is True
    o = out["output"]
    assert o["run"]["id"] == run.run_id and next(x["stage"] for x in o["stages"]) == "intake"
    assert o["calls"] and o["journal"] and o["spans"][0]["kind"] == "run" and o["spans"][0]["children"]
    by_run = call("agent.runTrace", {"run_id": run.run_id}, "admin")["output"]
    assert by_run["run"]["id"] == run.run_id
    assert call("agent.runTrace", {}, "admin")["error"]["code"] == "validation_error"
    assert call("agent.runTrace", {"run_id": "AR-nope"}, "admin")["error"]["code"] == "not_found"


def test_run_trace_case_without_run_is_empty():
    assert call("agent.runTrace", {"case_id": CASE}, "planner.a")["output"]["run"] is None


def test_pause_agent_shown_in_run_view():
    assert call("agent.register", {"id": "ext-autopilot", "name": "A", "tools": [], "autonomy": "act"}, "admin")["ok"]
    with SessionLocal() as s:
        run_id = runtime.start(s, "ext-autopilot", "case_autopilot", CASE, account="planner-a")
        s.commit()
    assert call("agent.setEnabled", {"id": "ext-autopilot", "on": False}, "admin")["ok"]
    with SessionLocal() as s:
        assert runtime.run_until_blocked(s, run_id) == "stopped"
    o = call("agent.runTrace", {"run_id": run_id}, "admin")["output"]
    assert o["run"]["status"] == "stopped"
    assert [(p["by"], p["on"]) for p in o["pauses"]] == [("admin", False)] and o["pauses"][0]["at"]


def test_trace_span_is_inserted_with_timestamps():
    _emit("t", kind="stage", run_id="AR-x")
    (row,) = _spans("AR-x")
    assert row["ended_at"] - row["started_at"] < timedelta(seconds=5) and row["trace_id"] == "AR-x"
