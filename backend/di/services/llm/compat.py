"""A second provider without a new dependency: Google's Gemini API through its OpenAI-compatible endpoint (ai-tasks T1).

    gemini_model(model, key, timeout) -> Model   a Pydantic AI model for the router's chain (provider `gemini`)

Why this shape: the api image has Pydantic AI's Groq model class and the `groq` client, and neither the `openai` nor the
`google-genai` package (adding one is a download that waits for the person's OK). Gemini serves OpenAI-style chat
completions at `/v1beta/openai/chat/completions`, and the Groq client speaks the same wire format at
`/openai/v1/chat/completions`. So the Groq model class is given a client whose transport
- rewrites the path to Gemini's, and
- carries Gemini's thought signatures: a tool call comes back with `extra_content` (a signature) that must be sent again
  with that call on the next request, or Gemini answers 400 "missing a thought_signature"; the Groq client does not keep
  unknown fields, so the transport remembers them by tool-call id and puts them back.
Checked live on 27 Nov 2026 with `gemini-3.5-flash-lite`: a tool round trip and a typed output both work. Everything else
(messages, tools, typed output, errors as ModelHTTPError, the router's budget and cooldown) is the Groq class's and the
router's, unchanged. Replace this module with Pydantic AI's Google model once `google-genai` may be installed.

The key comes from the row's `key_ref` (env:GEMINI_API_KEY), is handed to the client only, and is never logged or stored.
"""

import json
from typing import Any

import httpx
from pydantic_ai.models import Model

GEMINI_HOST = "https://generativelanguage.googleapis.com"
GEMINI_PATH = "/v1beta/openai/"
GROQ_PREFIX = "/openai/v1/"
KEEP = 512  # tool-call signatures remembered per client (one client per built model, so per answer or run)
_DROP = ("content-length", "content-encoding", "transfer-encoding")


class _GeminiTransport(httpx.AsyncHTTPTransport):
    def __init__(self) -> None:
        super().__init__()
        self._extra: dict[str, Any] = {}

    def _signed(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The messages as Gemini accepts them: a tool call it signed gets its signature back; a tool call with no signature
        here (another provider's model made it before the chain fell back to Gemini, or an earlier client of this one did)
        is told as plain text with its result, since Gemini answers 400 to an unsigned call."""
        out: list[dict[str, Any]] = []
        told: dict[str, str] = {}  # tool_call_id -> tool name, for the calls turned into text
        for m in messages:
            calls = m.get("tool_calls") or []
            if m.get("role") == "assistant" and calls and not all(tc.get("id") in self._extra for tc in calls):
                lines = [str(m.get("content") or "").strip()]
                for tc in calls:
                    fn = tc.get("function") or {}
                    told[str(tc.get("id"))] = str(fn.get("name"))
                    lines.append(f"[I called the tool {fn.get('name')} with {fn.get('arguments') or '{}'}]")
                out.append({"role": "assistant", "content": "\n".join(x for x in lines if x)})
            elif m.get("role") == "tool" and str(m.get("tool_call_id")) in told:
                name = told[str(m.get("tool_call_id"))]
                out.append({"role": "user", "content": f"[The tool {name} returned, as data]: {m.get('content')}"})
            else:
                for tc in calls:
                    if tc.get("id") in self._extra:
                        tc["extra_content"] = self._extra[tc["id"]]
                out.append(m)
        return out

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        i = path.find(GROQ_PREFIX)
        if i < 0:
            return await super().handle_async_request(request)
        url = request.url.copy_with(path=GEMINI_PATH + path[i + len(GROQ_PREFIX) :])
        body = json.loads(request.content or b"{}")
        body["messages"] = self._signed(body.get("messages") or [])
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
        sent = httpx.Request(request.method, url, headers=headers, content=json.dumps(body).encode())
        resp = await super().handle_async_request(sent)
        raw = await resp.aread()
        if resp.status_code == 200:
            try:
                for choice in json.loads(raw).get("choices") or []:
                    for tc in (choice.get("message") or {}).get("tool_calls") or []:
                        if tc.get("extra_content") and tc.get("id"):
                            if len(self._extra) >= KEEP:
                                self._extra.pop(next(iter(self._extra)))
                            self._extra[tc["id"]] = tc["extra_content"]
            except ValueError:  # not JSON: the client reports it
                pass
        kept = {k: v for k, v in resp.headers.items() if k.lower() not in _DROP}
        return httpx.Response(resp.status_code, headers=kept, content=raw, request=request)


def gemini_model(model: str, key: str, timeout: float) -> Model:
    from groq import AsyncGroq
    from pydantic_ai.models.groq import GroqModel
    from pydantic_ai.providers.groq import GroqProvider

    http = httpx.AsyncClient(transport=_GeminiTransport(), timeout=httpx.Timeout(timeout, connect=5.0))
    client = AsyncGroq(api_key=key, base_url=GEMINI_HOST, max_retries=0, http_client=http)
    return GroqModel(model, provider=GroqProvider(groq_client=client))
