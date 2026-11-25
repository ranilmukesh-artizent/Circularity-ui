"""The exception assistant (plan 9, P9-2.10 and P9-2.19; uses registry entries I-8 AgentLoop, I-9 router, I-20 work items).

    draft_exception(exc, case, pack, *, writer, session=None, ctx=None) -> ExceptionDraft
    explain_exception(ctx, exc, case, pack) -> ExceptionDraft     the draft with the language model, when one is set
    check_words(words, base, exc, case, pack) -> [str]            pure: why the model's draft is refused
    pack_roles(pack) -> [str]                                     the roles an owner may be

An exception item of My work gets a draft: a cause, a recommended action and an owner role, each with the facts and
sources it rests on. It replaces the `case_planner` of the plan's decision D1: the assistant proposes text and a person
acts.
    - Deterministic and complete without a model or key (R16): the pack's exception type gives `owner_role` and
      `recommended_action`; `cause` is the type's label filled with the facts (`process.facts_of`).
    - Model first: the `exception_writer` playbook (`playbooks.exception_writer`, read-only tools) drafts `cause`,
      `recommended_action` and `owner_role` and names the facts it rests on; `by_model` is then true and `model` says which.
      Code checks it (`check_words`): the owner is a role of the pack (`pack_roles`), every source a fact of the case, every
      number one the case gives. A refusal goes back to the model once (`checked_output`), then the deterministic draft
      stands. When the owner differs from the exception type's, `pack_default` says what the pack would have chosen.
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

from di.core import policy
from di.core.db import SessionLocal
from di.services.actions.pipeline import CallContext
from di.services.agents import runtime
from di.services.agents.checked_output import checked_type, invented_numbers
from di.services.agents.loop import AgentLoop
from di.services.agents.playbooks import exception_writer
from di.services.agents.playbooks.exception_writer import ExceptionWords
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
    model: str | None = None
    pack_default: str | None = None
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


def pack_roles(pack: Pack) -> list[str]:
    """The roles an owner may be: the app's roles and the pack's own (exception owners, guardrail approvers, escalation)."""
    named = [t.owner_role for t in pack.runtime.exception_types] + [a for g in pack.guardrails for a in g.approvers]
    named += [pack.runtime.escalate_to] if pack.runtime.escalate_to else []
    return list(dict.fromkeys([*policy.roles(), *named]))


def _role(name: str, pack: Pack) -> str | None:
    return next((r for r in pack_roles(pack) if r.strip().lower() == name.strip().lower()), None)


def check_words(
    words: exception_writer.ExceptionWords, base: ExceptionDraft, exc: Mapping[str, Any], case: Mapping[str, Any], pack: Pack
) -> list[str]:
    """Why the model's draft is refused, one sentence each (pure): an empty field, an owner that is no role of the pack, a source
    that is not a fact of the case, a number no fact of the case gives."""
    errors: list[str] = []
    if not words.cause.strip() or not words.recommended_action.strip():
        errors.append("Write a cause and a recommended action.")
    if _role(words.owner_role, pack) is None:
        errors.append(f"{words.owner_role!r} is not a role of the pack. Roles: {', '.join(pack_roles(pack))}.")
    facts = {s.fact.strip().lower() for s in base.sources}
    if unknown := sorted({x for x in words.sources if x.strip().lower() not in facts}):
        errors.append(f"These sources are not facts of the case: {'; '.join(unknown)}. Copy facts from the list.")
    blobs = [json.dumps([s.fact for s in base.sources]), json.dumps(exc, default=str), json.dumps(case, default=str)]
    if invented := invented_numbers([words.cause, words.recommended_action], *blobs):
        errors.append(f"These numbers are not in the case: {', '.join(invented)}. Write no number you were not given.")
    return errors


def _prompt(exc: Mapping[str, Any], case: Mapping[str, Any], draft: ExceptionDraft, pack: Pack) -> str:
    facts = "\n".join(f"- {s.fact}" for s in draft.sources) or "- (none)"
    return (
        f"Exception {exc['id']} ({exc['type']}) on case {case.get('id') or exc.get('case_id')}.\n"
        f"Facts (data):\n{facts}\n"
        f"The pack's own draft: cause {draft.cause!r}; action {draft.recommended_action!r}; owner {draft.owner_role}.\n"
        f"Roles you may choose from: {', '.join(pack_roles(pack))}.\n"
        "Read the case with your tools if you need more, then draft the cause, the action and the owner."
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
    drafts the cause, the action and the owner, and the draft is the model's when it passes `check_words` (one retry), else
    the deterministic one."""
    draft = deterministic(exc, case, pack)
    if writer is None:
        return draft
    if session is None or ctx is None or ctx.run_id is None:
        raise ValueError("a writer needs the session and the context of an agent run")
    checked = checked_type(ExceptionWords, lambda w: check_words(w, draft, exc, case, pack))
    spec = replace(exception_writer.spec(), output_type=checked)
    try:
        res = writer.run(session, spec, _prompt(exc, case, draft, pack), ctx=ctx)
    except Exception as e:  # noqa: BLE001 - a provider error, a refused tool, a draft out of retries, the turn limit: the pack's draft stands
        log.warning("exception assistant: the model loop failed for item %s: %s", exc.get("id"), e)
        return draft
    words = res.output
    role = _role(words.owner_role, pack) if isinstance(words, ExceptionWords) else None
    if not isinstance(words, ExceptionWords) or role is None:
        return draft
    owner = process.role_of_owner(role)
    cited = {x.strip().lower() for x in words.sources}
    return draft.model_copy(
        update={
            "cause": _clean(words.cause), "recommended_action": _clean(words.recommended_action), "owner_role": owner,
            "by_model": True, "model": res.model, "pack_default": draft.owner_role if owner != draft.owner_role else None,
            "sources": [s for s in draft.sources if s.fact.strip().lower() in cited] or draft.sources,
        }
    )  # fmt: skip


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
