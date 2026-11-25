"""The LLM router (plan 9, P9-2.3; registry entry I-9): which language model a caller may use now.

    chain_for(s, role, needs_tools=False) -> [ModelRef]   enabled models of the role, not cooling down, with budget left
                                                          in the minute and the day, by priority (table llm_model)
    pick_model(s, run_id, role="agent") -> ModelRef | None  the run's sticky model, else the first of the chain
    reserve(s, model_id, est_tokens) -> bool              one atomic statement per window; False leaves the model out
                                                          of the chain for the rest of that window
    cooldown(s, model_id, seconds)                        out of the chain until then (a 429's retry-after)
    build_model(s, refs, run_id=None) -> RouterModel      a Pydantic AI FallbackModel over the refs

Limits are per model, not per caller: Ask, the agents, the authoring helpers and the judges share them. A call reserves
its estimated tokens (prompt plus max_tokens) before it is sent; a 429 puts that model on cooldown and the request moves
on to the next model at once (SDK retries are 0, so one 429 costs one request). Nothing answers when every model is cooling
or out of budget: `pick_model` is None and the caller takes its deterministic path (R16).

Keys: a row holds `key_ref` ("env:<VAR>"), never a key. The key is read from the settings when a model is built, handed to
the provider SDK and never stored, logged or put in a span. Provider `test` is a `FunctionModel` that a test registers in
`TEST_MODELS` under the row's id; no other code puts anything there. Budget and cooldown writes use their own short
sessions, so a caller's open transaction (the run's row lock) is never waited for and the counts survive its rollback.

Never: calls a live provider in a test, or lets a caller write the tables (the actions `llm.setModel` and `llm.models`,
di.services.actions.llm, are the person's way in and are forbidden to agents).
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic_ai import ModelAPIError, ModelHTTPError, ModelRateLimitError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.config import get_settings

Role = Literal["ask", "agent", "author", "judge", "stage"]
ROLES: tuple[str, ...] = ("ask", "agent", "author", "judge", "stage")
# `stage` (the stage reasoners, P9-2.18) reads the case through tools; a model with the role `agent` serves it too, so a stack
# seeded before the role existed still reasons. Each model's budget is its own, whatever the role.
TOOL_ROLES = ("agent", "stage")
SEED_ID = "groq-default"  # the row of migration 0036; GROQ_MODEL still overrides its model at run time
DEFAULT_COOLDOWN = 60.0
DEFAULT_MAX_TOKENS = 1024
DAY_TOKEN_CAP = 2_000_000_000  # the day window limits requests only
TEST_MODELS: dict[str, Model] = {}  # provider `test`: row id -> the FunctionModel a test registered


@dataclass(frozen=True)
class ModelRef:
    id: str
    provider: Literal["groq", "test"]
    model: str
    key_ref: str | None
    request_timeout: float


def resolve_key(key_ref: str | None) -> str:
    """The key a `key_ref` names, or "" (never logged, never stored)."""
    if not key_ref or not key_ref.startswith("env:"):
        return ""
    var = key_ref[4:]
    if var == "GROQ_API_KEY":
        return get_settings().groq_api_key.get_secret_value().strip()
    import os

    return os.environ.get(var, "").strip()


_CHAIN_SQL = """
SELECT m.id, m.provider, m.model, m.key_ref, m.request_timeout FROM llm_model m
LEFT JOIN llm_budget bm ON bm.model_id = m.id AND bm."window" = 'minute' AND bm.window_start = date_trunc('minute', now())
LEFT JOIN llm_budget bd ON bd.model_id = m.id AND bd."window" = 'day' AND bd.window_start = date_trunc('day', now())
WHERE m.enabled AND (:role = ANY(m.roles) OR (:role = 'stage' AND 'agent' = ANY(m.roles))) AND (NOT :tools OR m.tools)
  AND (m.cooldown_until IS NULL OR m.cooldown_until <= now())
  AND coalesce(bm.used_requests, 0) < m.rpm AND coalesce(bm.used_tokens, 0) < m.tpm
  AND coalesce(bd.used_requests, 0) < m.rpd
ORDER BY m.priority, m.id
"""


def _ref(row: Any) -> ModelRef:
    model = str(row.model)
    if row.id == SEED_ID and (override := get_settings().groq_model.strip()):
        model = override
    return ModelRef(str(row.id), row.provider, model, row.key_ref, float(row.request_timeout))


def _usable(ref: ModelRef) -> bool:
    return ref.provider == "test" or bool(resolve_key(ref.key_ref))


def chain_for(s: Session, role: Role | str, *, needs_tools: bool = False) -> list[ModelRef]:
    rows = s.execute(text(_CHAIN_SQL), {"role": role, "tools": needs_tools or role in TOOL_ROLES}).all()
    return [r for r in map(_ref, rows) if _usable(r)]


def _take(s: Session, model_id: str, window: str, est: int, tokens: int, requests: int) -> bool:
    """The one atomic statement of a window: count the request unless it would pass a limit."""
    got = s.execute(
        text(
            'INSERT INTO llm_budget (model_id, "window", window_start, used_requests, used_tokens) '
            "VALUES (:m, :w, date_trunc(:w, now()), 1, :est) "
            'ON CONFLICT (model_id, "window", window_start) DO UPDATE SET '
            "used_tokens = llm_budget.used_tokens + :est, used_requests = llm_budget.used_requests + 1 "
            "WHERE llm_budget.used_tokens + :est <= :limit AND llm_budget.used_requests + 1 <= :rlimit RETURNING 1"
        ),
        {"m": model_id, "w": window, "est": est, "limit": tokens, "rlimit": requests},
    ).first()
    return got is not None


def reserve(s: Session, model_id: str, est_tokens: int) -> bool:
    """Count one request of `est_tokens` against the minute and the day, atomically; False when either window is full
    (nothing is counted then, and the model leaves the chain until that window ends)."""
    row = s.execute(text("SELECT rpm, tpm, rpd FROM llm_model WHERE id = :i"), {"i": model_id}).first()
    if row is None:
        return False
    limits = {"minute": (row.tpm, row.rpm), "day": (DAY_TOKEN_CAP, row.rpd)}
    if est_tokens > row.tpm:
        return False  # it would never fit: no window to wait for
    failed: str | None = None
    nested = s.begin_nested()  # a window that is full undoes the other window's count too
    for window, (tokens, requests) in limits.items():
        if not _take(s, model_id, window, est_tokens, tokens, requests):
            failed = window
            break
    if failed is None:
        nested.commit()
        return True
    nested.rollback()
    unit = "1 minute" if failed == "minute" else "1 day"
    s.execute(
        text(
            "UPDATE llm_model SET cooldown_until = greatest(coalesce(cooldown_until, '-infinity'), "
            "date_trunc(:w, now()) + CAST(:u AS interval)) WHERE id = :i"
        ),
        {"w": failed, "u": unit, "i": model_id},
    )
    return False


def cooldown(s: Session, model_id: str, seconds: float | None) -> None:
    s.execute(
        text("UPDATE llm_model SET cooldown_until = now() + make_interval(secs => :n) WHERE id = :i"),
        {"n": float(seconds) if seconds else DEFAULT_COOLDOWN, "i": model_id},
    )


def pick_model(s: Session, run_id: str, role: Role | str = "agent") -> ModelRef | None:
    """The run's sticky model if it is still in the chain, else the first of the chain (written to state.model_route).

    A run's state may have lost `model_route` when the runtime saved it; its `model` (what the loop answered with) then
    names the sticky model too."""
    chain = chain_for(s, role, needs_tools=role in TOOL_ROLES)
    if not chain:
        return None
    st = s.execute(text("SELECT state FROM agent_run WHERE id = :i"), {"i": run_id}).scalar_one_or_none() or {}
    for ref in chain:
        if ref.id == st.get("model_route") or (not st.get("model_route") and ref.model == st.get("model")):
            return ref
    record_route(s, run_id, chain[0].id)
    return chain[0]


def record_route(s: Session, run_id: str, model_id: str) -> None:
    s.execute(
        text("UPDATE agent_run SET state = state || jsonb_build_object('model_route', CAST(:m AS text)) WHERE id = :i"),
        {"m": model_id, "i": run_id},
    )


def _estimate(messages: list[ModelMessage], settings: ModelSettings | None) -> int:
    return len(str(messages)) // 4 + int((settings or {}).get("max_tokens") or DEFAULT_MAX_TOKENS)


class RouterModel(FallbackModel):
    """A FallbackModel that remembers which model answered last (`answered`: the ref)."""

    answered: ModelRef | None = None


class _Metered(WrapperModel):
    """One model of the chain: reserves its budget before the request (no budget: a local 429, no request is sent),
    and puts the model on cooldown when the provider answers 429."""

    def __init__(self, wrapped: Model, ref: ModelRef, bind: Any, on_answer: Callable[[ModelRef], None]) -> None:
        super().__init__(wrapped)
        self.ref, self._bind, self._on_answer = ref, bind, on_answer

    def _before(self, messages: list[ModelMessage], settings: ModelSettings | None) -> None:
        with Session(self._bind) as ls:
            ok = reserve(ls, self.ref.id, _estimate(messages, settings))
            ls.commit()
        if not ok:
            raise ModelHTTPError(429, self.ref.model, {"error": "the model's budget is used up"})

    def _limited(self, e: ModelAPIError) -> None:
        if isinstance(e, ModelRateLimitError) or (isinstance(e, ModelHTTPError) and e.status_code == 429):
            with Session(self._bind) as ls:
                cooldown(ls, self.ref.id, e.retry_after)
                ls.commit()

    async def request(
        self, messages: list[ModelMessage], model_settings: ModelSettings | None, model_request_parameters: ModelRequestParameters
    ) -> ModelResponse:
        self._before(messages, model_settings)
        try:
            out = await self.wrapped.request(messages, model_settings, model_request_parameters)
        except ModelAPIError as e:
            self._limited(e)
            raise
        self._on_answer(self.ref)
        return out

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any = None,
    ) -> AsyncIterator[StreamedResponse]:
        self._before(messages, model_settings)
        try:
            async with self.wrapped.request_stream(messages, model_settings, model_request_parameters, run_context) as r:
                self._on_answer(self.ref)
                yield r
        except ModelAPIError as e:
            self._limited(e)
            raise


def _provider_model(ref: ModelRef) -> Model | None:
    if ref.provider == "test":
        return TEST_MODELS.get(ref.id)
    key = resolve_key(ref.key_ref)
    if not key:
        return None
    from groq import AsyncGroq
    from pydantic_ai.models.groq import GroqModel
    from pydantic_ai.providers.groq import GroqProvider

    client = AsyncGroq(api_key=key, timeout=httpx.Timeout(ref.request_timeout, connect=5.0), max_retries=0)
    return GroqModel(ref.model, provider=GroqProvider(groq_client=client))


def build_model(s: Session, refs: list[ModelRef]) -> RouterModel | None:
    """A FallbackModel over the refs in order, or None when none can be built (no key, no registered test model)."""
    built = [(r, m) for r in refs if (m := _provider_model(r)) is not None]
    if not built:
        return None
    bind = s.get_bind()

    def answered(ref: ModelRef) -> None:
        router.answered = ref

    router = RouterModel(*[_Metered(m, r, bind, answered) for r, m in built])
    return router
