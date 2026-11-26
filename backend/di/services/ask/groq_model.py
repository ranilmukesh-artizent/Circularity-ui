"""The Groq provider: Ask's AskModel on Groq's chat completions (the official `groq` SDK, OpenAI-style tool calling).

    answer(request, tools)
        messages   the system prompt, the conversation so far, the question
        loop       up to `max_rounds` requests, streamed: text deltas are passed on as they arrive; tool calls are
                   gathered from the stream, run with tools.call (the access policy applies there) and their results go
                   back as `tool` messages; the last round is sent without tools, so it must answer
        errors     any groq.APIError (429 over the limit, 5xx, a connection failure, a timeout, a stream error) is
                   raised as ModelUnavailable with its reason; Ask then answers with the rule-based fallback

Free tier: about 30 requests a minute, 1,000 a day and 8,000 tokens a minute per organisation for the default model
(openai/gpt-oss-120b, which supports tool calling on the free tier). Every request counts its prompt and its
`max_completion_tokens` against the minute's tokens, so prompts stay short, tool results are compacted
(di.services.ask.tools.as_text), completions are capped and the SDK does not retry (a 429 falls back at once instead of
spending more of the limit).

The key comes from the settings (GROQ_API_KEY) and is handed to the SDK only; it is never logged or returned.
"""

import json
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

import groq
import httpx
from opentelemetry.trace import SpanKind, StatusCode

from di import telemetry
from di.services.ask.model import AskRequest, Done, Event, ModelUnavailable, TextDelta, Toolbox, ToolUse
from di.services.ask.tools import as_text

MAX_COMPLETION_TOKENS = 700


@lru_cache(maxsize=4)
def _client(api_key: str, timeout: float) -> groq.Groq:
    return groq.Groq(api_key=api_key, timeout=httpx.Timeout(timeout, connect=5.0), max_retries=0)


def _reason(e: groq.APIError) -> str:
    if isinstance(e, groq.RateLimitError):
        return "rate_limited"
    if isinstance(e, groq.APITimeoutError):
        return "timeout"
    if isinstance(e, groq.APIConnectionError):
        return "unavailable"
    if isinstance(e, groq.APIStatusError):
        return "unavailable" if e.status_code >= 500 else "model_error"
    return "model_error"


class _Chat:
    """One model request as an OpenTelemetry GenAI inference span `chat {model}` (CLIENT, a child of the Ask span) and a
    sample of the histogram `gen_ai.client.inference.duration`. `end` is idempotent, so a stream that is closed half way
    (the client left) still ends its span. No prompt or answer is recorded unless DI_OTEL_CAPTURE_CONTENT is on.
    Nothing is created while telemetry is off."""

    def __init__(self, model: str, tools: Toolbox, messages: list[dict]):
        self.model, self.span, self.t0 = model, None, time.monotonic()
        self.finish: list[str] = []
        self.usage: tuple[int | None, int | None] = (None, None)
        self.response_model: str | None = None
        if not telemetry.enabled():
            return
        parent = getattr(tools, "trace_context", None)
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "groq",
            "gen_ai.request.model": model,
        }
        if conv := getattr(tools, "conversation_id", None):
            attrs["gen_ai.conversation.id"] = conv
        if telemetry.capture_content():
            attrs["gen_ai.input.messages"] = telemetry.clip(json.dumps(messages, default=str))
        self.span = telemetry.tracer.start_span(f"chat {model}", kind=SpanKind.CLIENT, context=parent, attributes=attrs)

    def chunk(self, chunk: Any) -> None:
        """Read what a streamed chunk says about the response: its model, finish reason and token usage (Groq sends the
        usage in `x_groq.usage` of the last chunk, other servers in `usage`)."""
        if self.span is None:
            return
        self.response_model = getattr(chunk, "model", None) or self.response_model
        usage = getattr(chunk, "usage", None) or getattr(getattr(chunk, "x_groq", None), "usage", None)
        if usage is not None:
            self.usage = (getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None))
        for choice in chunk.choices or []:
            if choice.finish_reason:
                self.finish = [choice.finish_reason]

    def end(self, error: str | None = None, output: dict | None = None) -> None:
        span, self.span = self.span, None
        if span is None:
            return
        attrs: dict[str, Any] = {  # the histogram's attributes
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "groq",
            "gen_ai.request.model": self.model,
        }
        if self.response_model:
            span.set_attribute("gen_ai.response.model", self.response_model)
        if self.finish:
            span.set_attribute("gen_ai.response.finish_reasons", self.finish)
        for key, n in zip(("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"), self.usage, strict=True):
            if n is not None:
                span.set_attribute(key, int(n))
        if error:
            span.set_attribute("error.type", error)
            span.set_status(StatusCode.ERROR)
            attrs["error.type"] = error
        if output is not None and telemetry.capture_content():
            span.set_attribute("gen_ai.output.messages", telemetry.clip(json.dumps([output], default=str)))
        span.end()
        telemetry.record_duration(
            "gen_ai.client.inference.duration", time.monotonic() - self.t0, attrs, "Duration of a GenAI inference request"
        )


class GroqModel:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 20.0, max_rounds: int = 4):
        self.model, self.timeout, self.max_rounds = model, timeout, max(1, max_rounds)
        self._key = api_key
        # reasoning models (gpt-oss) think briefly and keep their reasoning out of the stream; others get neither field
        self._reasoning = {"reasoning_effort": "low", "include_reasoning": False} if model.startswith("openai/gpt-oss") else {}

    def answer(self, request: AskRequest, tools: Toolbox) -> Iterator[Event]:
        client = _client(self._key, self.timeout)
        specs = [{"type": "function", "function": s} for s in tools.specs]
        messages: list[dict] = [
            {"role": "system", "content": request.system},
            *request.conversation,
            {"role": "user", "content": request.question},
        ]
        said: list[str] = []
        for n in range(self.max_rounds):
            last = n == self.max_rounds - 1
            text: list[str] = []
            calls: dict[int, dict[str, Any]] = {}
            chat = _Chat(self.model, tools, messages)
            try:
                stream = client.chat.completions.create(  # type: ignore[call-overload]  # messages and tools are the API's JSON dicts
                    model=self.model,
                    messages=messages,
                    tools=specs,
                    tool_choice="none" if last else "auto",
                    stream=True,
                    temperature=0.2,
                    max_completion_tokens=MAX_COMPLETION_TOKENS,
                    **self._reasoning,
                )
                for chunk in stream:
                    chat.chunk(chunk)
                    if not chunk.choices:
                        continue
                    d = chunk.choices[0].delta
                    if d.content:
                        text.append(d.content)
                        yield TextDelta(d.content)
                    for tc in d.tool_calls or []:
                        c = calls.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
                        if tc.id:
                            c["id"] = tc.id
                        if tc.function and tc.function.name:
                            c["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            c["arguments"] += tc.function.arguments
                said_now = {"role": "assistant", "content": "".join(text), "tool_calls": [c["name"] for c in calls.values()]}
                chat.end(output=said_now)
            except groq.APIError as e:
                chat.end(error=type(e).__name__)
                raise ModelUnavailable(_reason(e), type(e).__name__) from None
            finally:
                chat.end()  # a stream closed half way (the client left) still ends its span
            said.append("".join(text))
            if not calls:
                # the answer is the last turn's text: text written before a further tool call was a draft, and joining it
                # repeated the answer (seen live, 25 Nov); an empty last turn keeps what was said before
                yield Done(said[-1] if said[-1].strip() else "".join(said))
                return
            ordered = [calls[k] for k in sorted(calls)]
            for i, c in enumerate(ordered):
                c["id"] = c["id"] or f"call_{n}_{i}"
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(text) or None,
                    "tool_calls": [
                        {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                        for c in ordered
                    ],
                }
            )
            for c in ordered:
                run = getattr(tools, "call_with_id", None)  # the provider's call id goes on the tool span (plan 5)
                args_json = c["arguments"] or "{}"
                result = run(c["name"], args_json, c["id"]) if run else tools.call(c["name"], args_json)
                yield ToolUse(c["name"], _args(c["arguments"]), result)
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": as_text(result)})
        yield Done("".join(said))


def _args(s: str) -> object:
    try:
        return json.loads(s or "{}")
    except json.JSONDecodeError:
        return s
