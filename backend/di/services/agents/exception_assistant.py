"""The exception assistant (plan 9, P9-2.10; uses registry entries I-8 AgentLoop, I-9 router, I-20 work items).

    draft_exception(exc, case, pack, *, writer, session=None, ctx=None) -> ExceptionDraft
    explain_exception(ctx, exc, case, pack) -> ExceptionDraft     the draft with the language model, when one is set

An exception item of My work gets a draft: a cause, a recommended action and an owner role, each with the facts and
sources it rests on. It replaces the `case_planner` of the plan's decision D1: the assistant proposes text and a person
acts.
    - Deterministic and complete without a model or key (R16): the pack's exception type gives `owner_role` and
      `recommended_action`; `cause` is the type's label filled with the facts (`process.facts_of`).
    - With a model: the `exception_writer` playbook (`playbooks.exception_writer`, read-only tools) rewrites `cause` only.
      `owner_role` and `recommended_action` always come from the pack, whatever the model says; `by_model` is then true.
      Any failure of the loop leaves the deterministic draft.
Never does: resolve, assign, escalate, approve or write anything about the case (golden rule 10). The only rows it adds are
its own agent run (`agent_run`, agent `recover-exceptions`), kept so the call shows in the Agents page; a run that no
model took part in is removed again.
"""

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.db import SessionLocal
from di.services.actions.pipeline import CallContext
from di.services.agents import runtime
from di.services.agents.loop import AgentLoop
from di.services.agents.playbooks import exception_writer
from di.services.cases import process
from di.services.modeler.pack import Pack

log = logging.getLogger(__name__)
MAX_CAUSE = 500


class Source(BaseModel):
    fact: str
    source: str
    at: str


class ExceptionDraft(BaseModel):
    cause: str
    recommended_action: str
    owner_role: str
    by_model: bool = False
    sources: list[Source] = Field(default_factory=list)


def _clean(s: str) -> str:
    return " ".join(s.split())[:MAX_CAUSE]


def deterministic(exc: Mapping[str, Any], case: Mapping[str, Any], pack: Pack) -> ExceptionDraft:
    """The pack's words filled with the case's facts. A type the pack does not know keeps what the item itself says."""
    kind = next((t for t in pack.runtime.exception_types if t.id == exc["type"]), None)
    facts = process.facts_of(exc, case)
    label = kind.label if kind else str(exc.get("title") or exc["type"])
    body = "; ".join(f["fact"].rstrip(".") for f in facts)
    return ExceptionDraft(
        cause=_clean(f"{label}: {body}" if body else label),
        recommended_action=kind.action if kind else str(exc.get("action") or ""),
        owner_role=process.role_of_owner(kind.owner_role if kind else str(exc["owner_role"])),
        sources=[Source(**f) for f in facts],
    )


def _prompt(exc: Mapping[str, Any], case: Mapping[str, Any], draft: ExceptionDraft) -> str:
    return (
        f"Exception {exc['id']} ({exc['type']}) on case {case.get('id') or exc.get('case_id')}. "
        f"Draft cause: {draft.cause} Read the case with your tools if you need more, then word the cause."
    )


def draft_exception(
    exc: Mapping[str, Any],
    case: Mapping[str, Any],
    pack: Pack,
    *,
    writer: AgentLoop | None,
    session: Session | None = None,
    ctx: CallContext | None = None,
) -> ExceptionDraft:
    """The deterministic draft; with a `writer` (and the `session` and `ctx` of an agent run, which the loop needs) the model
    rewrites the cause. The owner and the action are never the model's."""
    draft = deterministic(exc, case, pack)
    if writer is None:
        return draft
    if session is None or ctx is None or ctx.run_id is None:
        raise ValueError("a writer needs the session and the context of an agent run")
    try:
        res = writer.run(session, exception_writer.spec(), _prompt(exc, case, draft), ctx=ctx)
    except Exception as e:  # noqa: BLE001 - a provider error, a refused tool, the turn limit: the deterministic draft stands
        log.warning("exception assistant: the model loop failed for item %s: %s", exc.get("id"), e)
        return draft
    words = getattr(res.output, "cause", None)
    if not isinstance(words, str) or not words.strip():
        return draft
    return draft.model_copy(update={"cause": _clean(words), "by_model": True})


def explain_exception(ctx: CallContext, exc: Mapping[str, Any], case: Mapping[str, Any], pack: Pack) -> ExceptionDraft:
    """The draft for a person, worded by the router's model when one is available (R16: complete without one). The loop
    runs as the agent `recover-exceptions` in an `agent_run` of its own on the person's authority, in a session of its own
    (the loop commits after each model turn, which the caller's transaction must not see); the row stays only when a model
    answered. `s` is only read."""
    loop = runtime.loop_runner()
    run_id = "AR-" + uuid.uuid4().hex[:12]
    acct = ctx.actor.account.id if ctx.actor.account else None
    state = {"account": acct, "playbook_version": exception_writer.VERSION, "work_item": exc["id"]}
    with SessionLocal() as ms:
        ms.execute(
            text(
                "INSERT INTO agent_run (id, agent, playbook, case_id, status, step, state) "
                "VALUES (:i, :a, :p, :c, 'running', 0, CAST(:st AS jsonb))"
            ),
            {"i": run_id, "a": exception_writer.AGENT_ID, "p": exception_writer.NAME, "c": exc.get("case_id"),
             "st": json.dumps(state)},
        )  # fmt: skip
        ms.commit()
        run_ctx = replace(ctx, session=ms, preparer=exception_writer.AGENT_ID, run_id=run_id, idem_key=None)
        draft = draft_exception(exc, case, pack, writer=loop, session=ms, ctx=run_ctx)
        ms.rollback()  # leave a failed loop's half-done transaction; the committed turns stay
        if draft.by_model:
            ms.execute(text("UPDATE agent_run SET status = 'done', step = 1, updated_at = now() WHERE id = :i"), {"i": run_id})
        else:
            ms.execute(text("DELETE FROM agent_run WHERE id = :i"), {"i": run_id})
        ms.commit()
    return draft
