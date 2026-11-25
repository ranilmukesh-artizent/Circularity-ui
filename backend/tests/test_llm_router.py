"""P9-2.3 (enabler, F §4): the LLM router with budgets and cooldowns (registry entry I-9).

Every model is a `FunctionModel` registered under a `test` provider row (R16): no test reaches a provider and none reads
a key. The seeded Groq row is switched off while a test runs and put back afterwards.
"""

import json
import logging

import pytest
from pydantic import BaseModel
from pydantic.types import SecretStr
from pydantic_ai import ModelHTTPError, ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.agents import runtime
from di.services.agents.forbidden import forbidden
from di.services.agents.loop import LoopSpec
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.llm import router
from tests import starting
from tests.helpers import call, client, h
from tests.test_agent_loop import PB, register, start

models.ALLOW_MODEL_REQUESTS = False
SEED = "groq-default"


class Out(BaseModel):
    summary: str


def _spec() -> LoopSpec:
    return LoopSpec(playbook=PB, version="1", instructions="Test playbook.", output_type=Out, tools=())


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run"))
        s.execute(text("DELETE FROM llm_model WHERE id <> :i"), {"i": SEED})  # the budgets cascade
        s.execute(text("DELETE FROM llm_budget"))
        s.execute(
            text(
                "UPDATE llm_model SET cooldown_until = NULL, enabled = true, priority = 1, model = 'openai/gpt-oss-120b' "
                "WHERE id = :i"
            ),
            {"i": SEED},
        )
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    with SessionLocal() as s:
        s.execute(text("UPDATE llm_model SET enabled = false WHERE id = :i"), {"i": SEED})
        s.commit()
    yield
    router.TEST_MODELS.clear()
    _clean()
    starting.reset()


def add(model_id: str, fn=None, priority: int = 1, tpm: int = 8000, rpm: int = 30, rpd: int = 1000, roles="agent") -> None:
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO llm_model (id, provider, model, rpm, tpm, rpd, roles, priority) "
                "VALUES (:i, 'test', :i, :rpm, :tpm, :rpd, :roles, :p)"
            ),
            {"i": model_id, "rpm": rpm, "tpm": tpm, "rpd": rpd, "roles": roles.split(","), "p": priority},
        )
        s.commit()
    if fn is not None:
        router.TEST_MODELS[model_id] = FunctionModel(fn)


class Counter:
    def __init__(self, status: int | None = None, retry_after: float | None = None) -> None:
        self.calls, self.status, self.retry_after = 0, status, retry_after

    def __call__(self, messages: list, info: AgentInfo) -> ModelResponse:
        self.calls += 1
        if self.status:
            raise ModelHTTPError(self.status, "m", {"error": "limit"}, retry_after=self.retry_after)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": "done"})])


def _ctx(run_id: str):
    with SessionLocal() as s:
        return runtime._context(s, runtime.get(s, run_id))


def _state(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT state FROM agent_run WHERE id = :i"), {"i": run_id}).scalar_one())


def _cooldown(model_id: str):
    with SessionLocal() as s:
        return s.execute(text("SELECT cooldown_until FROM llm_model WHERE id = :i"), {"i": model_id}).scalar_one()


def test_router_429_moves_without_second_request():
    a, b = Counter(429, retry_after=30), Counter()
    add("t-a", a, priority=1)
    add("t-b", b, priority=2)
    register("act")
    run_id = start()
    ctx = _ctx(run_id)
    with SessionLocal() as s:
        r = PydanticAILoop().run(s, _spec(), "Go.", ctx=ctx)
    assert r.output == Out(summary="done") and r.model == "t-b"
    assert (a.calls, b.calls) == (1, 1)
    assert _cooldown("t-a") is not None and _cooldown("t-b") is None
    assert _state(run_id)["model_route"] == "t-b"


def test_router_sticky_per_run():
    add("t-a", Counter(), priority=1)
    add("t-b", Counter(), priority=2)
    register("act")
    r1, r2 = start(), start("RT-1049")
    with SessionLocal() as s:
        first = router.pick_model(s, r1)
        assert first is not None and first.id == "t-a"
        s.commit()
        s.execute(text("UPDATE llm_model SET priority = 0 WHERE id = 't-b'"))
        s.commit()
        again, other = router.pick_model(s, r1), router.pick_model(s, r2)
        assert again is not None and again.id == "t-a"  # sticky
        assert other is not None and other.id == "t-b"  # a different run may start elsewhere
        s.commit()
    assert _state(r1)["model_route"] == "t-a" and _state(r2)["model_route"] == "t-b"


def test_router_budget_atomic():
    add("t-a", Counter(), tpm=1000)
    with SessionLocal() as s:
        assert [m.id for m in router.chain_for(s, "agent")] == ["t-a"]
        assert router.reserve(s, "t-a", 600) is True
        assert router.reserve(s, "t-a", 600) is False
        s.commit()
        assert router.chain_for(s, "agent") == []
        used = s.execute(
            text("SELECT \"window\", used_requests, used_tokens FROM llm_budget WHERE model_id = 't-a' ORDER BY 1")
        ).all()
    assert [tuple(u) for u in used] == [("day", 1, 600), ("minute", 1, 600)]  # the refused call changed nothing


def test_router_no_model_means_deterministic_path():
    add("t-a", Counter())
    register("act")
    run_id = start()
    with SessionLocal() as s:
        router.cooldown(s, "t-a", 3600)
        s.commit()
        assert router.pick_model(s, run_id) is None
        r = PydanticAILoop().run(s, _spec(), "Go.", ctx=_ctx(run_id))
    assert r.output is None and r.model is None
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM agent_run_message WHERE run_id = :r"), {"r": run_id}).scalar_one() == 0


def test_router_key_never_stored_or_logged(monkeypatch, caplog):
    secret = "gsk_" + "abcdefghijklmnopqrstuvwx"
    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr(secret))
    with SessionLocal() as s:
        s.execute(text("UPDATE llm_model SET enabled = true WHERE id = :i"), {"i": SEED})
        s.commit()
        cols = [
            r[0] for r in s.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'llm_model'"))
        ]
        assert [c for c in cols if "key" in c or "secret" in c] == ["key_ref"]
        assert s.execute(text("SELECT key_ref FROM llm_model WHERE id = :i"), {"i": SEED}).scalar_one() == "env:GROQ_API_KEY"
        with caplog.at_level(logging.DEBUG):
            refs = router.chain_for(s, "agent")
            assert router.build_model(s, refs) is not None  # a Groq model is built; no request is made
        assert secret not in repr(refs) and secret not in caplog.text
    out = call("llm.models", {}, "admin")
    assert out["ok"] is True and "gsk_" not in json.dumps(out)
    assert out["output"]["models"][0]["id"] == SEED


def test_llm_set_model_agent_refused():
    assert forbidden("llm.setModel") and forbidden("llm.models")
    for extra in ({}, {"X-Circularity-Confirmed": "true"}):
        hdr = h("admin") | {"X-Circularity-Preparer": "coordinator"} | extra
        r = client.post("/api/actions/llm.setModel", json={"id": SEED, "enabled": True}, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", r.json()
    with SessionLocal() as s:
        assert s.execute(text("SELECT enabled FROM llm_model WHERE id = :i"), {"i": SEED}).scalar_one() is False


def test_llm_set_model_rules():
    add("t-a", Counter())
    ok = call("llm.setModel", {"id": "t-a", "priority": 7, "roles": ["ask"], "rpm": 5, "enabled": False}, "admin")
    assert ok["ok"] is True
    with SessionLocal() as s:
        row = s.execute(text("SELECT priority, roles, rpm, enabled FROM llm_model WHERE id = 't-a'")).one()
    assert tuple(row) == (7, ["ask"], 5, False)
    for bad in ({"rpm": 0}, {"tpm": 0}, {"rpd": -1}, {"roles": ["nope"]}):
        r = call("llm.setModel", {"id": "t-a", **bad}, "admin")
        assert r["ok"] is False and r["error"]["code"] == "validation_error", (bad, r)
    assert call("llm.setModel", {"id": "zzz"}, "admin")["error"]["code"] == "not_found"
    assert call("llm.setModel", {"id": "t-a"}, "planner-a")["ok"] is False  # manageAgents is Admin's


def test_ask_uses_router_chain(monkeypatch):
    from di.services.ask.groq_model import GroqModel
    from di.services.ask.model import NoModel, get_model

    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr("test-key-not-real"))
    monkeypatch.setattr(get_settings(), "groq_model", "")
    with SessionLocal() as s:
        s.execute(text("UPDATE llm_model SET enabled = true, model = 'router-model-1' WHERE id = :i"), {"i": SEED})
        s.commit()
    m = get_model()
    assert isinstance(m, GroqModel) and m.model == "router-model-1"
    with SessionLocal() as s:
        router.cooldown(s, SEED, 3600)
        s.commit()
    assert isinstance(get_model(), NoModel)  # the router is empty: Ask answers by rules, as without a key
