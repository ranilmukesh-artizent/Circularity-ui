"""Spans of an agent run, written to our own table (plan 9, P9-2.6; registry entry I-12).

    with span(s, "name", kind="tool", run_id=run_id, attrs={...}) as sp:   writes one `trace_span` row when the block ends
        sp.attrs["di.proposal_id"] = 7                                    attributes may be added inside the block
    current_span_id()                                                     the enclosing span (a context variable)
    prune(s, days) -> int                                                 deletes the spans older than `days`

Kinds: `run` (the bursts of steps of one run: one row per run, its end moves on with every burst), `stage` (one row per
stage of the chain and run, likewise), `model` (one model response), `tool` (one tool call of the loop) and `action` (one
call an agent prepared, run by the pipeline). The parent is the enclosing span; a span with a run id and no parent starts
the trace named by that run id. A `run` or `stage` span passes its own deterministic `span_id` so that a later burst of the
same run updates the row instead of adding one (the start is kept, the end moves, attributes merge).

Attributes pass through `di.core.redact.clean` first (no key that looks like a secret is ever stored). Keys that start with
`content.` (prompts, tool inputs and outputs) are kept only when the setting `trace_content` is true (default false).
A key, a prompt or a provider header is never put in an attribute by this module or its callers.

Rows are written in their own short session on the caller's database (as the router writes its budgets): a rollback of the
caller's transaction, such as a failed model loop, keeps the spans that explain it. A failing write is logged, never raised:
tracing never changes what a run does. No OpenTelemetry: Global Constraints list no such dependency.
"""

import json
import logging
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.config import get_settings
from di.core.redact import clean

log = logging.getLogger(__name__)
Kind = Literal["run", "stage", "model", "tool", "action"]
CONTENT_PREFIX = "content."
USAGE_PREFIX = "gen_ai.usage."  # input_tokens and output_tokens: counts that redact.clean would drop for the word "token"
MESSAGE_LIMIT = 300


@dataclass
class Span:
    span_id: str
    trace_id: str
    parent_id: str | None
    run_id: str | None
    name: str
    kind: Kind
    started_at: datetime
    attrs: dict[str, Any] = field(default_factory=dict)
    status: Literal["ok", "error"] = "ok"


_current: ContextVar[Span | None] = ContextVar("di_current_span", default=None)

UPSERT = text(
    "INSERT INTO trace_span (span_id, trace_id, parent_id, run_id, name, kind, started_at, ended_at, status, attrs) "
    "VALUES (:id, :trace, :parent, :run, :name, :kind, :start, :end, :status, CAST(:attrs AS jsonb)) "
    "ON CONFLICT (span_id) DO UPDATE SET started_at = least(trace_span.started_at, EXCLUDED.started_at), "
    "ended_at = greatest(trace_span.ended_at, EXCLUDED.ended_at), status = EXCLUDED.status, "
    "attrs = trace_span.attrs || EXCLUDED.attrs"
)


def current_span_id() -> str | None:
    """The id of the enclosing span, or None outside any."""
    cur = _current.get()
    return cur.span_id if cur is not None else None


def _attrs(sp: Span) -> dict[str, Any]:
    keep = get_settings().trace_content
    raw = {k: v for k, v in sp.attrs.items() if keep or not str(k).startswith(CONTENT_PREFIX)}
    counts = {
        k: v for k, v in raw.items() if str(k).startswith(USAGE_PREFIX)
    }  # token counts, not secrets: "token" is a secret word
    out: dict[str, Any] = clean({k: v for k, v in raw.items() if k not in counts}) | counts
    if sp.run_id is not None:
        out.setdefault("di.run_id", sp.run_id)
    return out


def _write(s: Session, sp: Span) -> None:
    try:
        with Session(s.get_bind()) as ts:
            ts.execute(
                UPSERT,
                {
                    "id": sp.span_id, "trace": sp.trace_id, "parent": sp.parent_id, "run": sp.run_id, "name": sp.name,
                    "kind": sp.kind, "start": sp.started_at, "end": datetime.now(UTC), "status": sp.status,
                    "attrs": json.dumps(_attrs(sp), default=str),
                },
            )  # fmt: skip
            ts.commit()
    except Exception:  # noqa: BLE001 - tracing never changes what a run does
        log.warning("trace span %s was not written", sp.name, exc_info=True)


class SpanScope:
    """The context manager behind `span`; a class so that code that cannot use `with` (the loop's iteration) can call
    `__enter__` and `__exit__` itself."""

    def __init__(self, s: Session, sp: Span) -> None:
        self._s, self.span = s, sp
        self._token: Token[Span | None] | None = None

    def __enter__(self) -> Span:
        self._token = _current.set(self.span)
        return self.span

    def __exit__(self, et: type[BaseException] | None, ev: BaseException | None, tb: Any) -> None:
        if self._token is not None:
            try:
                _current.reset(self._token)
            except ValueError:  # reset in another context: put the parent back instead
                _current.set(None)
        if et is not None:
            self.span.status = "error"
            self.span.attrs["error.type"] = et.__name__
            self.span.attrs["error.message"] = str(ev)[:MESSAGE_LIMIT]
        _write(self._s, self.span)


def span(
    s: Session, name: str, *, kind: Kind, run_id: str | None, attrs: dict[str, Any] | None = None, span_id: str | None = None
) -> SpanScope:
    """Open a span; it is written when the block ends (status `error` with the exception's class and message when the
    block raised, which still propagates). `span_id` (optional) names the row: a second span with the same id updates it."""
    parent = _current.get()
    trace_id = run_id if run_id and parent is None else (parent.trace_id if parent else uuid.uuid4().hex)
    sp = Span(
        span_id=span_id or uuid.uuid4().hex[:16], trace_id=trace_id, parent_id=parent.span_id if parent else None,
        run_id=run_id, name=name, kind=kind, started_at=datetime.now(UTC), attrs=dict(attrs or {}),
    )  # fmt: skip
    return SpanScope(s, sp)


def record(
    s: Session, name: str, *, kind: Kind, trace_id: str, parent_id: str | None, started_at: datetime,
    attrs: dict[str, Any] | None = None, status: Literal["ok", "error"] = "ok", span_id: str | None = None,
) -> str:  # fmt: skip
    """Write one finished span with its trace and parent given (ai-tasks T0: an assistant turn runs across a generator and
    a worker thread, where the context variable of `span` does not carry). `run_id` is the trace id: the turn's id. Returns
    the span id. Same redaction and content rule as `span`; never raises."""
    sp = Span(
        span_id=span_id or uuid.uuid4().hex[:16], trace_id=trace_id, parent_id=parent_id, run_id=trace_id, name=name,
        kind=kind, started_at=started_at, attrs=dict(attrs or {}), status=status,
    )  # fmt: skip
    _write(s, sp)
    return sp.span_id


def prune(s: Session, days: int) -> int:
    """Delete the spans that started more than `days` days ago; returns how many."""
    r = s.execute(text("DELETE FROM trace_span WHERE started_at < now() - make_interval(days => :d)"), {"d": int(days)})
    return int(getattr(r, "rowcount", 0) or 0)
