"""P9-0.5: the model chain with rate-limit fallback (R16: fake clients, no network; the key below is a dummy)."""

import groq
import httpx
import pytest
from sqlalchemy import text

import di.main  # noqa: F401  (loads every action before Ask's tools check them)
from di.core.config import get_settings, model_chain
from di.core.db import SessionLocal
from di.services.actions import workflow_builder
from di.services.ask import complete, groq_model, modeler_read
from di.services.ask.chain import ChainModel
from di.services.ask.groq_model import GroqModel
from di.services.ask.model import AskRequest, Done, ModelUnavailable, TextDelta, get_model


def _resp(code: int) -> httpx.Response:
    return httpx.Response(code, request=httpx.Request("POST", "http://fake.invalid/"))


def _rate_limit() -> Exception:
    return groq.RateLimitError("slow down", response=_resp(429), body=None)


def _bad_request() -> Exception:
    return groq.BadRequestError("bad", response=_resp(400), body=None)


class FakeModel:
    name = "fake"

    def __init__(self, model: str, events=(), error: Exception | None = None, error_first=True):
        self.model, self.events, self.error, self.error_first, self.calls = model, list(events), error, error_first, 0

    def answer(self, request, tools):
        self.calls += 1
        if self.error and self.error_first:
            raise self.error
        yield from self.events
        if self.error:
            raise self.error


REQ = AskRequest(question="q", system="s")


def test_chain_moves_on_after_429():
    a = FakeModel("a", error=ModelUnavailable("rate_limited"))
    b = FakeModel("b", [Done("second")])
    out = list(ChainModel([a, b]).answer(REQ, None))
    assert out == [Done("second")]
    assert (a.calls, b.calls) == (1, 1)


def test_chain_does_not_repeat_after_stream_started():
    a = FakeModel("a", [TextDelta("hi")], ModelUnavailable("rate_limited"), error_first=False)
    b = FakeModel("b", [Done("x")])
    gen = ChainModel([a, b]).answer(REQ, None)
    got = [next(gen)]
    with pytest.raises(ModelUnavailable) as e:
        next(gen)
    assert e.value.reason == "rate_limited" and got == [TextDelta("hi")] and b.calls == 0


def test_chain_stops_on_model_error():
    a = FakeModel("a", error=ModelUnavailable("model_error"))
    b = FakeModel("b", [Done("x")])
    with pytest.raises(ModelUnavailable) as e:
        list(ChainModel([a, b]).answer(REQ, None))
    assert e.value.reason == "model_error" and b.calls == 0


def test_chain_raises_last_when_every_model_failed():
    a, b = FakeModel("a", error=ModelUnavailable("rate_limited")), FakeModel("b", error=ModelUnavailable("timeout"))
    with pytest.raises(ModelUnavailable) as e:
        list(ChainModel([a, b]).answer(REQ, None))
    assert e.value.reason == "timeout" and ChainModel([a, b]).model == "a"


class _Client:
    """A fake groq client: each call pops the next outcome (an exception is raised, a dict is the JSON answer)."""

    def __init__(self, outcomes):
        self.outcomes, self.models = list(outcomes), []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        import json
        from types import SimpleNamespace as NS

        self.models.append(kw["model"])
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return NS(choices=[NS(message=NS(content=json.dumps(o)))])


@pytest.fixture
def chain_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ASK_PROVIDER", "groq")
    monkeypatch.setenv("ASK_MODEL_CHAIN", "groq:m1,groq:m2")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_complete_json_falls_back_then_empty(chain_env, monkeypatch):
    c = _Client([_rate_limit(), _rate_limit()])
    monkeypatch.setattr(groq_model, "_client", lambda key, timeout: c)
    assert complete.complete_json("s", "u", max_tokens=10) == {}
    assert c.models == ["m1", "m2"]
    c = _Client([_rate_limit(), {"path": "resell"}])
    monkeypatch.setattr(groq_model, "_client", lambda key, timeout: c)
    assert complete.complete_json("s", "u", max_tokens=10) == {"path": "resell"}


def test_complete_json_is_off_without_a_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    monkeypatch.setattr(groq_model, "_client", lambda *a: pytest.fail("no key, no call"))
    assert complete.complete_json("s", "u", max_tokens=10) == {}
    get_settings.cache_clear()


def test_complete_json_used_by_modeler_read_and_workflow_plan(monkeypatch):
    calls = []
    monkeypatch.setattr(complete, "complete_json", lambda system, user, **kw: calls.append(kw) or {})
    monkeypatch.setattr(modeler_read, "_key", lambda: "test-key")
    from di.services.modeler.templates import load_template

    modeler_read.model_rule("some rule", load_template("tool_fleet"))
    assert [c["max_tokens"] for c in calls] == [200]
    workflow_builder.model_slots("make a workflow")
    assert [c["max_tokens"] for c in calls] == [200, 300]


def test_empty_chain_is_todays_single_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.delenv("ASK_MODEL_CHAIN", raising=False)
    get_settings.cache_clear()
    m = get_model()
    assert isinstance(m, GroqModel) and m.model == (get_settings().groq_model.strip() or "openai/gpt-oss-120b")
    get_settings.cache_clear()


def test_chain_of_two_gives_a_chain_model_and_other_providers_are_skipped(chain_env, monkeypatch):
    # plan 9 P9-2.3: Ask's models are the router's rows (llm_model), no longer ASK_MODEL_CHAIN
    with SessionLocal() as s:
        s.execute(text("UPDATE llm_model SET model = 'm1' WHERE id = 'groq-default'"))
        s.execute(
            text(
                "INSERT INTO llm_model (id, provider, model, key_ref, rpm, tpm, rpd, roles, priority) "
                "VALUES ('groq-second', 'groq', 'm2', 'env:GROQ_API_KEY', 30, 8000, 1000, ARRAY['ask'], 2)"
            )
        )
        s.commit()
    monkeypatch.setenv("GROQ_MODEL", "")
    try:
        m = get_model()
        assert isinstance(m, ChainModel) and m.model == "m1" and [x.model for x in m.models] == ["m1", "m2"]
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM llm_model WHERE id = 'groq-second'"))
            s.execute(text("UPDATE llm_model SET model = 'openai/gpt-oss-120b' WHERE id = 'groq-default'"))
            s.commit()
    monkeypatch.setenv("ASK_MODEL_CHAIN", "other:x, groq:m3")
    get_settings.cache_clear()
    assert model_chain(get_settings()) == [("groq", "m3")]
