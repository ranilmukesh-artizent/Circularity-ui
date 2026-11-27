"""The assistant's one loop: a Pydantic AI agent over the router's model chain (ai-tasks T4, §4B D1, D3, D4).

    EngineModel(refs, bind)            an AskModel (di.services.ask.model): `answer(request, tools)` yields ToolUse events
                                       as the tools run, then the text (one TextDelta) and Done
    pick_tools(page, question, turns)  the few tools this question is given (code routes, the model does not choose
                                       from every tool)

Why this replaced the raw-SDK loop (di.services.ask.groq_model), measured on the main stack on 27 Nov 2026:
- every request carried all 20 tool definitions: about 2,400 to 3,500 prompt tokens against 8,000 tokens a minute per model,
  so one question with a tool call used a model's whole minute;
- the first model's 200,000 tokens a day were used up, and the old chain moved to the next model only before the first
  event: a limit met after a tool call ended the answer in the rules.
Here every model request goes through `di.services.llm.router.build_model`: a FallbackModel whose members reserve their
budget first and go on cooldown for the provider's retry-after on a 429, so the next model answers THAT request with the
same messages, at any round. The run ends on the model's final text, not on a round count (`MAX_REQUESTS` is the safety
net). Tools are the Toolbox's (di.services.ask.tools: reads and the three draft-making tools, each through the action
pipeline as the signed-in person); this module adds no way to reach an action.

Never: reads or logs a key, keeps a model between requests, or writes (the Toolbox does, through the pipeline).
"""

import asyncio
import logging
import queue
import re
import threading
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

from pydantic_ai import Agent, Tool
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    ModelRateLimitError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits
from sqlalchemy.orm import Session

from di.core import tracing
from di.services.ask.model import AskRequest, Done, Event, ModelUnavailable, TextDelta, Toolbox, ToolUse
from di.services.ask.tools import as_text
from di.services.llm import router

log = logging.getLogger("di.services.ask.engine")
MAX_REQUESTS = 8  # the safety net: a question is answered in 1 to 4 requests
MAX_TOKENS = 500  # counted against the minute's tokens with the prompt: answers are at most ~120 words
WAITS = 2  # times one answer waits for a model to come back from a limit
MAX_WAIT = 60.0  # seconds, each time: a minute window always turns within it

# ---- which tools a question gets (D4: a handful, chosen in code from the page and the words)
ALWAYS = ("get_inbox", "list_cases", "list_workflows")
GROUPS: dict[str, tuple[tuple[str, ...], re.Pattern[str], tuple[str, ...]]] = {
    # name: (tools, the words that ask for it, the pages that are about it)
    "case": (
        ("get_case", "get_case_run", "get_case_evidence", "list_eligible_routes", "predict_outcomes", "what_if"),
        re.compile(r"\bRT-\d|\bcases?\b|\bassets?\b|evidence|approv|\broutes?\b|what if|recommend|\bstage\b", re.I),
        ("product", "queue", "mywork", "approvals"),
    ),
    "workflow": (
        ("get_workflow", "get_workflow_run", "create_workflow"),
        re.compile(
            r"\bWF-\d|\bRUN-|workflows?|\bsyncs?\b|ingest|pipeline|\bsources?\b|\bruns?\b|stuck|fail|integrat|connect", re.I
        ),
        ("integration", "fabric", "records"),
    ),
    "flow": (
        ("get_decision_flow", "change_decision_flow", "describe_business"),
        re.compile(
            r"\bflows?\b|\brules?\b|guardrail|\bsteps?\b|\bnever\b|\balways\b|polic|modeler|\bpacks?\b|compos|template|"
            r"\bwe (?:take|buy|sell|rent|lease|refurbish|recycle|repair|collect)\b|our business|set ?up",
            re.I,
        ),
        ("modeler",),
    ),
    "figures": (
        ("explain_kpi", "get_model_validation", "device_question", "find_demand", "optimize_pool"),
        re.compile(
            r"kpi|recover|\bvalue\b|co2|carbon|\brisk\b|varian|demand|\bpools?\b|\bmodels?\b|price|dispute|how much|how many|%",
            re.I,
        ),
        ("analytics", "home", "overview"),
    ),
}


GROUP_OF_KIND = {
    "case": "case",
    "workflow": "workflow",
    "run": "workflow",
    "flow": "flow",
    "composition": "flow",
    "kpi": "figures",
}


def pick_tools(page: dict | None, question: str, earlier: str = "") -> tuple[str, ...]:
    """The tools for this question: the three list tools, the groups its words or the page ask for (the page's own group
    first), and every group when nothing says which (the answer is then slower, never blind). `earlier` is the last
    question of the conversation: a follow-up ("make it every 15 minutes") keeps its subject's tools."""
    p = page or {}
    kind = (p.get("object") or {}).get("kind")
    on = {g for g, (_t, _rx, pages) in GROUPS.items() if p.get("page") in pages}
    on |= {GROUP_OF_KIND.get(str(kind), "")}
    said = {g for g, (_t, rx, _p) in GROUPS.items() if rx.search(question)}
    groups = (said | on) - {""}
    if not said and earlier:
        groups |= {g for g, (_t, rx, _p) in GROUPS.items() if rx.search(earlier)}
    if not groups:
        groups = set(GROUPS)
    out = list(ALWAYS)
    for g in GROUPS:
        if g in groups:
            out += [t for t in GROUPS[g][0] if t not in out]
    return tuple(out)


def _reason(e: BaseException) -> str:
    """ModelUnavailable's reason for what the run raised. A group (the chain's FallbackExceptionGroup, or the task group
    Pydantic AI's graph raises around a failing node) is read through to its members: a limit wins, else the last."""
    if isinstance(e, BaseExceptionGroup):
        reasons = [_reason(x) for x in e.exceptions]
        return "rate_limited" if "rate_limited" in reasons else (reasons[-1] if reasons else "unavailable")
    if isinstance(e, UsageLimitExceeded | UnexpectedModelBehavior):
        return "model_error"
    if isinstance(e, ModelRateLimitError) or (isinstance(e, ModelHTTPError) and e.status_code == 429):
        return "rate_limited"
    if isinstance(e, ModelHTTPError):
        return "unavailable" if e.status_code >= 500 else "model_error"
    if isinstance(e, ModelAPIError):
        return "timeout" if "timeout" in type(e).__name__.lower() else "unavailable"
    return "model_error"


def _leaves(e: BaseException) -> str:
    """The classes (and HTTP status) of what was raised, for the log: never a message body, a header or a key."""
    if isinstance(e, BaseExceptionGroup):
        return ", ".join(_leaves(x) for x in e.exceptions)
    return f"{type(e).__name__}{' ' + str(e.status_code) if isinstance(e, ModelHTTPError) else ''}"


def _history(conversation: list[dict]) -> list[ModelMessage]:
    out: list[ModelMessage] = []
    for m in conversation:
        text = str(m.get("content") or "")
        if m.get("role") == "assistant":
            out.append(ModelResponse(parts=[TextPart(content=text)]))
        else:
            out.append(ModelRequest(parts=[UserPromptPart(content=text)]))
    return out


class EngineModel:
    """The router's chain as one AskModel. `model` is the model that answered last (the first of the chain before)."""

    def __init__(self, refs: list[router.ModelRef], bind: Any):
        self._refs, self._bind = refs, bind
        self.name: str = refs[0].provider if len({r.provider for r in refs}) == 1 else "chain"
        self.model = refs[0].model

    def answer(self, request: AskRequest, tools: Toolbox) -> Iterator[Event]:
        """The run is ONE asyncio task in its own thread (Pydantic AI keeps context variables per task: stepping an async
        generator from a synchronous one enters and leaves the run in different tasks and fails). Events cross a queue.
        The Toolbox's session is used by the run's thread only while this generator waits on the queue."""
        q: queue.Queue[Event | BaseException | None] = queue.Queue()

        async def main() -> None:
            async for ev in self._events(request, tools):
                q.put(ev)

        def work() -> None:
            try:
                asyncio.run(main())
                q.put(None)
            except BaseException as e:  # noqa: BLE001 - handed to the caller's thread, raised there
                q.put(e)

        t = threading.Thread(target=work, name="ask-engine", daemon=True)
        t.start()
        try:
            while True:
                ev = q.get()
                if ev is None:
                    return
                if isinstance(ev, BaseException):
                    raise ev
                yield ev
        finally:
            t.join(timeout=60)

    async def _events(self, request: AskRequest, tools: Toolbox) -> AsyncIterator[Event]:
        pending: list[ToolUse] = []
        one_tool = asyncio.Lock()

        def make(spec: dict) -> Tool[None]:
            name = spec["name"]

            async def call(**args: Any) -> str:
                # in a worker thread: a build tool runs a model loop of its own (workflow.author's drafter, the flow
                # reader) with asyncio.run, which refuses to start on a thread whose event loop is running (27 Nov 2026:
                # those inner models had silently never answered from the assistant). One tool at a time: the session.
                run = getattr(tools, "call_with_id", None)
                async with one_tool:
                    result = (
                        await asyncio.to_thread(run, name, args, None) if run else await asyncio.to_thread(tools.call, name, args)
                    )
                pending.append(ToolUse(name, args, result))
                return as_text(result)  # {ok, data} or {ok: false, error}: an error is data the model reads, never a retry

            return Tool.from_schema(call, name=name, description=spec["description"], json_schema=spec["parameters"])

        toolset = [make(sp) for sp in tools.specs]
        history: list[ModelMessage] = _history(request.conversation)
        prompt: str | None = request.question
        text, requests = "", 0
        for attempt in range(WAITS + 1):
            with Session(self._bind) as s:
                refs = [r for r in router.chain_for(s, "ask", needs_tools=True) if r.provider != "test"]
                chain = router.build_model(s, refs) if refs else None
            if chain is None:
                if attempt == WAITS or not await self._wait():
                    raise ModelUnavailable("rate_limited", "every model is cooling down or out of budget")
                continue
            agent: Agent[None, str] = Agent(
                chain,
                instructions=request.system,
                tools=toolset,
                retries=1,
                model_settings={"temperature": 0.2, "max_tokens": MAX_TOKENS},
            )
            seen: list[ModelMessage] = []
            t_req = datetime.now(UTC)
            try:
                async with agent.iter(
                    prompt,
                    message_history=history or None,
                    usage_limits=UsageLimits(request_limit=max(1, MAX_REQUESTS - requests)),
                ) as run:
                    async for node in run:
                        seen = list(run.all_messages())
                        if Agent.is_model_request_node(node) and not any(m is node.request for m in seen):
                            seen.append(node.request)  # the request about to be sent: the question, or the tools' results
                        if chain.answered is not None:
                            self.model = chain.answered.model
                        if Agent.is_call_tools_node(node):  # one model response: a `model` span with its tokens
                            self._model_span(tools, node.model_response, t_req)
                            t_req = datetime.now(UTC)
                        while pending:
                            yield pending.pop(0)
                    u = run.usage
                    requests += u.requests
                    total = getattr(tools, "usage", None)
                    if isinstance(total, dict):
                        used = {"requests": u.requests, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens}
                        for k, v in used.items():
                            total[k] = int(total.get(k) or 0) + int(v or 0)
                    result = run.result
                    text = str(result.output) if result is not None and result.output is not None else ""
                break
            except (ModelAPIError, UsageLimitExceeded, UnexpectedModelBehavior, ExceptionGroup) as e:
                # every model refused THIS request (a limit, an outage, a tool call the provider rejected). What was done
                # so far is kept: the run goes on from the same messages, so no tool runs twice and no draft is made twice.
                # A limit waits for the first model back; a provider's rejection is tried once more at once.
                why = _reason(e)
                log.warning("Ask engine: a model request failed (%s): %s", why, _leaves(e))
                again = (why == "rate_limited" and await self._wait()) or (why == "model_error" and attempt == 0)
                if attempt == WAITS or not again or isinstance(e, UsageLimitExceeded):
                    raise ModelUnavailable(why, type(e).__name__) from None
                if seen and isinstance(seen[-1], ModelRequest):
                    history, prompt = seen, None
        while pending:
            yield pending.pop(0)
        if text.strip():
            yield TextDelta(text)
        yield Done(text)

    def _model_span(self, tools: Toolbox, resp: ModelResponse, started: datetime) -> None:
        trace, session = getattr(tools, "trace", None), getattr(tools, "session", None)
        if not trace or session is None:  # a toolbox without a trace (a test's): nothing to write
            return
        u = resp.usage
        tracing.record(
            session, f"chat {self.model}", kind="model", trace_id=trace[0], parent_id=trace[1], started_at=started,
            attrs={"di.agent": "ask", "gen_ai.request.model": self.model, "gen_ai.response.model": resp.model_name,
                   "gen_ai.usage.input_tokens": u.input_tokens, "gen_ai.usage.output_tokens": u.output_tokens,
                   "di.tool_calls": [p.tool_name for p in resp.parts if hasattr(p, "tool_name")]},
        )  # fmt: skip

    async def _wait(self) -> bool:
        """Wait for the first model to come back (its cooldown, or the minute's budget); False when that is further away
        than MAX_WAIT seconds (a day's limit), so the caller answers by rules now."""
        with Session(self._bind) as s:
            wait = router.soonest(s, "ask")
        if wait is None or wait > MAX_WAIT:
            return False
        await asyncio.sleep(wait + 0.5)
        return True
