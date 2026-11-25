"""The AgentLoop port (plan 9, P9-2.2; registry entry I-8): one language-model loop over action tools.

Owns the value types a loop takes and gives back, and the `AgentLoop` Protocol the runtime calls. The one adapter is
`pydantic_ai_loop.PydanticAILoop`; a test or a later adapter may stand in for it.

    LoopSpec    what to run: playbook name and version, instructions, the output type, the action ids that become tools
                (each must pass `catalog.agent_allowed`; checked when the spec is built), which of them return untrusted
                text, the turn limit, the router role. The special tool id `ask_person` (a question to a person) is
                allowed only when the spec lists it.
    Deferred    a tool call that did not run now: an action held as a proposal for a person (`external`) or a
                question to a person (`question`)
    LoopResult  the output (None when no model is configured, or the run ended deferred), the deferred calls, token
                usage, the model name, and `tainted` (an untrusted tool returned during the run)

Never does: call a provider by itself, decide a hold (the action pipeline does, step 9b), or run an action no agent may
run (`catalog.agent_allowed` refuses it at spec build and the pipeline refuses it again).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS
from di.services.agents import catalog

ASK_PERSON = "ask_person"  # the question tool's id in LoopSpec.tools (not an action)


@dataclass(frozen=True)
class LoopSpec:
    playbook: str
    version: str
    instructions: str
    output_type: type[BaseModel]
    tools: tuple[str, ...]
    untrusted_tools: frozenset[str] = frozenset()
    max_turns: int = 6
    role: str = "agent"

    def __post_init__(self) -> None:
        for t in self.tools:
            if t == ASK_PERSON:
                continue
            a = ACTIONS.get(t)
            if a is None or not catalog.agent_allowed(a):
                raise ValueError(f"{t!r} is not a tool an agent may call")
        if extra := self.untrusted_tools - set(self.tools):
            raise ValueError(f"untrusted tools that are not tools of the spec: {sorted(extra)}")


@dataclass(frozen=True)
class Deferred:
    tool_call_id: str
    action: str
    proposal_id: int | None
    kind: Literal["external", "question"]
    question: str | None = None


@dataclass
class LoopResult:
    output: BaseModel | None
    deferred: list[Deferred] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0})
    model: str | None = None
    tainted: bool = False


class AgentLoop(Protocol):
    def run(
        self, s: Session, spec: LoopSpec, prompt: str, *, ctx: CallContext, resume: Mapping[str, Any] | None = None
    ) -> LoopResult:
        """Run the loop for `ctx.run_id`. `resume` is None for a fresh run; otherwise the run's stored messages are
        loaded and `resume` maps tool_call_id to the value that call now has (an accepted proposal's output, or the
        person's answer); an empty mapping continues a run that stopped between turns."""
        ...
