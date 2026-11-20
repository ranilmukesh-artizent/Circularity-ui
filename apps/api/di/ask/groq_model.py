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
(di.ask.tools.as_text), completions are capped and the SDK does not retry (a 429 falls back at once instead of
spending more of the limit).

The key comes from the settings (GROQ_API_KEY) and is handed to the SDK only; it is never logged or returned.
"""

import json
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

import groq
import httpx

from di.ask.model import AskRequest, Done, Event, ModelUnavailable, TextDelta, Toolbox, ToolUse
from di.ask.tools import as_text

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
            except groq.APIError as e:
                raise ModelUnavailable(_reason(e), type(e).__name__) from None
            said.append("".join(text))
            if not calls:
                yield Done("".join(said))
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
                result = tools.call(c["name"], c["arguments"] or "{}")
                yield ToolUse(c["name"], _args(c["arguments"]), result)
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": as_text(result)})
        yield Done("".join(said))


def _args(s: str) -> object:
    try:
        return json.loads(s or "{}")
    except json.JSONDecodeError:
        return s
