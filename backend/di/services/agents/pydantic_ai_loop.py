"""The Pydantic AI adapter of the AgentLoop port (plan 9, P9-2.2; registry entry I-8).

    PydanticAILoop(model_factory).run(s, spec, prompt, ctx=ctx, resume=None) -> LoopResult

One function tool per action id of the spec, named as the catalogue names it (`case_evidence`), with the action's own
JSON Schema as its parameters. A tool call runs `pipeline.invoke` as the run's person, prepared by the run's agent, with
`idem_key = "<run_id>:<tool_call_id>"`, so a repeated call is answered "Already done" and the pipeline's gates (kill
switch, autonomy, run limits, org scope, the forbidden list) apply exactly as for any agent call.
    - the pipeline holds the call for a person (`{"held": pid}`) -> `CallDeferred` (external): the run ends with
      `DeferredToolRequests`, mapped to `LoopResult.deferred`; never `requires_approval` (the pipeline decides)
    - a refusal -> `ModelRetry` (two retries per tool, then the run raises); a `duplicate` -> "Already done"
    - a tool of `spec.untrusted_tools` returning -> `LoopResult.tainted` (P9-2.4 reads it)
    - `ask_person(question)` exists only when `spec.tools` lists it: `CallDeferred(kind="question")`
Each time the loop is about to send the next request (and at the end) the messages added since are appended to
`agent_run_message` and committed, so a crash repeats at most one model call. A resume loads them, passes
`message_history` and `deferred_tool_results`; a deferred tool is never invoked again.

No model (the factory returns None): `LoopResult(output=None, model=None)` and no request, so the caller takes its
deterministic path (R16). The model comes from the router (di.services.llm.router, P9-2.3: the default factory
`router_model_factory(s, run_id, role)`): budgets, cooldowns, a fallback on 429 or 5xx, and the model that answered
kept in `state.model_route`.
Never does: start OpenTelemetry,
or call an action outside the spec. Tests use `FunctionModel` or `TestModel`, never a live provider.
"""

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai import (
    Agent,
    CallDeferred,
    DeferredToolRequests,
    DeferredToolResults,
    ModelRetry,
    RunContext,
    Tool,
)
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.actions.pipeline import CallContext, invoke
from di.services.actions.registry import ACTIONS
from di.services.agents import catalog
from di.services.agents.loop import ASK_PERSON, Deferred, LoopResult, LoopSpec
from di.services.llm import router

ALREADY_DONE = "Already done; nothing was created twice."
TOOL_RETRIES = 2
ModelFactory = Callable[[Session, str, str], Model | None]  # (session, run id, role)


@dataclass
class _Deps:
    ctx: CallContext
    untrusted: frozenset[str]
    tainted: bool = False


def router_model_factory(s: Session, run_id: str, role: str) -> Model | None:
    """The router's model for the run (P9-2.3): its sticky model first, then the rest of the chain as fallbacks; None
    when every model is cooling, out of budget or without a key (so no request is ever made)."""
    first = router.pick_model(s, run_id, role)
    if first is None:
        return None
    rest = [r for r in router.chain_for(s, role, needs_tools=role == "agent") if r.id != first.id]
    return router.build_model(s, [first, *rest])


def _name(model: Model) -> str | None:
    """The model that answered (the router's), else the model's own name."""
    if isinstance(model, router.RouterModel) and model.answered is not None:
        return model.answered.model
    return getattr(model, "model_name", None)


def _action_tool(action_id: str) -> Tool[_Deps]:
    a = ACTIONS[action_id]

    async def call(rc: RunContext[_Deps], **args: Any) -> Any:
        d = rc.deps
        r = invoke(action_id, args, replace(d.ctx, idem_key=f"{d.ctx.run_id}:{rc.tool_call_id}"))
        if r["ok"]:
            out = r["output"]
            if isinstance(out, dict) and "held" in out:  # {held, reasons} (P9-2.4)
                raise CallDeferred(metadata={"kind": "external", "action": action_id, "proposal_id": out["held"]})
            if action_id in d.untrusted:
                d.tainted = d.ctx.taint = True  # the rest of the run's writes are held (P9-2.4)
            return out
        e = r["error"]
        if e["code"] == "duplicate":
            return ALREADY_DONE
        raise ModelRetry(e["message"])

    return Tool.from_schema(
        call, name=catalog.tool_name(action_id), description=a.desc or a.title,
        json_schema=catalog.input_schema(a), takes_ctx=True,
    )  # fmt: skip


async def _ask_person(rc: RunContext[_Deps], question: str) -> str:  # noqa: ARG001 - the tool's signature
    raise CallDeferred(metadata={"kind": "question", "action": ASK_PERSON, "question": question}, kind="question")


def _tools(spec: LoopSpec) -> list[Tool[_Deps]]:
    out = [_action_tool(t) for t in spec.tools if t != ASK_PERSON]
    if ASK_PERSON in spec.tools:
        out.append(Tool(_ask_person, name=ASK_PERSON, description="Ask a person a question and wait for the answer."))
    return out


def load_messages(s: Session, run_id: str) -> list[ModelMessage]:
    rows = s.execute(text("SELECT messages FROM agent_run_message WHERE run_id = :r ORDER BY n"), {"r": run_id}).scalars()
    flat: list[Any] = [m for turn in rows for m in turn]
    return ModelMessagesTypeAdapter.validate_python(flat)


def _save_turn(s: Session, run_id: str, new: list[ModelMessage], model: str | None) -> None:
    """Append what the model added since the last save, then commit it (a crash then repeats at most one model call)."""
    dumped = ModelMessagesTypeAdapter.dump_python(new, mode="json")
    s.execute(
        text(
            "INSERT INTO agent_run_message (run_id, n, messages, model) VALUES "
            "(:r, (SELECT coalesce(max(n), 0) + 1 FROM agent_run_message WHERE run_id = :r), CAST(:m AS jsonb), :mo)"
        ),
        {"r": run_id, "m": json.dumps(dumped), "mo": model},
    )
    s.commit()


class PydanticAILoop:
    def __init__(self, model_factory: ModelFactory = router_model_factory) -> None:
        self._factory = model_factory

    def run(
        self, s: Session, spec: LoopSpec, prompt: str, *, ctx: CallContext, resume: Mapping[str, Any] | None = None
    ) -> LoopResult:
        if ctx.run_id is None:
            raise ValueError("an agent loop runs inside an agent run (ctx.run_id)")
        model = self._factory(s, str(ctx.run_id), spec.role)
        if model is None:
            return LoopResult(output=None, model=None)
        return asyncio.run(self._run(s, spec, prompt, ctx, resume, model))

    async def _run(
        self, s: Session, spec: LoopSpec, prompt: str, ctx: CallContext, resume: Mapping[str, Any] | None, model: Model
    ) -> LoopResult:
        run_id = str(ctx.run_id)
        agent: Agent[_Deps, Any] = Agent(
            model,
            output_type=[spec.output_type, DeferredToolRequests],
            instructions=spec.instructions,
            deps_type=_Deps,
            tools=_tools(spec),
            retries=TOOL_RETRIES,
        )
        history = load_messages(s, run_id) if resume is not None else []
        deps = _Deps(ctx=ctx, untrusted=spec.untrusted_tools)
        answers = DeferredToolResults(calls=dict(resume)) if resume else None
        saved = len(history)
        name = _name(model)
        async with agent.iter(
            None if resume is not None else prompt,
            message_history=history or None,
            deferred_tool_results=answers,
            deps=deps,
            usage_limits=UsageLimits(request_limit=spec.max_turns),
        ) as ar:
            async for node in ar:
                # a request node is next (the tools of the last response have run) or the run ended: save the new messages
                if type(node).__name__ in ("ModelRequestNode", "End") and len(ar.all_messages()) > saved:
                    name = _name(model)
                    if isinstance(model, router.RouterModel) and model.answered is not None:
                        router.record_route(s, run_id, model.answered.id)
                    _save_turn(s, run_id, ar.all_messages()[saved:], name)
                    saved = len(ar.all_messages())
        result = ar.result
        out = result.output if result is not None else None
        u = ar.usage
        usage = {"requests": u.requests, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens}
        deferred: list[Deferred] = []
        if isinstance(out, DeferredToolRequests):
            for c in out.calls:
                meta = out.metadata.get(c.tool_call_id, {})
                if meta.get("kind") == "question":
                    deferred.append(Deferred(c.tool_call_id, ASK_PERSON, None, "question", meta.get("question")))
                else:
                    deferred.append(
                        Deferred(c.tool_call_id, str(meta.get("action", c.tool_name)), meta.get("proposal_id"), "external")
                    )
            out = None
        return LoopResult(output=out, deferred=deferred, usage=usage, model=name, tainted=deps.tainted)
