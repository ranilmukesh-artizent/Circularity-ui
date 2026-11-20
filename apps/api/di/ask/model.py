"""The AskModel interface, its events, and the provider switch.

    class AskModel:   name ("groq"), model (the provider's model id)
        answer(request, tools) -> Iterator[TextDelta | ToolUse | Done]
            given the question, the page context, the conversation so far and the tools, stream the answer: text as it
            arrives, each tool call (the model decides; the provider runs it with tools.call, which applies the access
            policy, and hands the result back to the model), and the final text. A provider that cannot answer raises
            ModelUnavailable (no key, over the limit, failing, too slow), at any point; Ask then answers with the
            rule-based fallback.

The provider is chosen by configuration (di.config): ASK_PROVIDER=groq with GROQ_API_KEY (and GROQ_MODEL) gives
di.ask.groq_model.GroqModel; ASK_PROVIDER=none, or no key, gives NoModel, which always raises ModelUnavailable. Another
provider (Claude, a local Ollama model) is one more class with the same `answer` and one more line in `get_model`;
the endpoint, the stream the frontend reads and the tools stay as they are.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from di.config import DEFAULT_GROQ_MODEL, get_settings


@dataclass
class AskRequest:
    question: str
    system: str  # the system prompt (di.ask.prompt): rules, the signed-in user, the page
    conversation: list[dict] = field(default_factory=list)  # earlier turns: [{role: user|assistant, content}]


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolUse:
    name: str
    arguments: Any
    result: dict  # what the model was given back ({ok, data} or {ok: false, error})


@dataclass
class Done:
    text: str


Event = TextDelta | ToolUse | Done


class ModelUnavailable(Exception):
    """The model cannot answer; `reason` says why (no_key, disabled, rate_limited, timeout, unavailable, model_error)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason, self.detail = reason, detail


class Toolbox(Protocol):
    @property
    def specs(self) -> list[dict]: ...

    def call(self, name: str, arguments: Any) -> dict: ...


class AskModel(Protocol):
    name: str
    model: str

    def answer(self, request: AskRequest, tools: Toolbox) -> Iterator[Event]: ...


class NoModel:
    """No model configured: every answer is the fallback's."""

    name, model = "none", ""

    def __init__(self, reason: str):
        self.reason = reason

    def answer(self, request: AskRequest, tools: Toolbox) -> Iterator[Event]:  # noqa: ARG002 - the provider interface
        raise ModelUnavailable(self.reason)
        yield  # pragma: no cover  (a generator, like every provider's answer)


def get_model() -> AskModel:
    """The configured provider (a FastAPI dependency of POST /api/ask; tests override it with a fake model)."""
    s = get_settings()
    provider = (s.ask_provider or "groq").strip().lower()
    if provider in ("none", "off", "fallback", ""):
        return NoModel("disabled")
    if provider == "groq":
        key = s.groq_api_key.get_secret_value().strip()
        if not key:
            return NoModel("no_key")
        from di.ask.groq_model import GroqModel

        return GroqModel(
            api_key=key,
            model=s.groq_model.strip() or DEFAULT_GROQ_MODEL,
            timeout=s.ask_timeout_seconds,
            max_rounds=s.ask_max_rounds,
        )
    return NoModel("unknown_provider")
