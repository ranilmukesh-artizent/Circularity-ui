"""Proposals that hold for a person (plan 8, MVP-11.4; edge case 26): table agent_proposal (migration 0024).

    holds(s, agent_id) -> bool          the agent is registered with autonomy "propose": its writes are held
    hold(ctx, action, input, case_id) -> id   store the call (the pipeline does this instead of running it)
    get(s, id, for_update) -> dict | None
    decide(s, id, status, by, at, result)    accepted or rejected, by whom and when, with the result
    pending_for(s, account, pctx) -> [dict]  the pending proposals a person may decide: the held action's own
                                             permission, and the case in their tenants (Home's proposals); a case
                                             the server cannot place is nobody's (fail closed). Each with `why`.
Holding a proposal adds a domain_event `proposal.held` ({id, action, agent}, with the case), so the live stream
refreshes the inboxes.

proposal.accept and proposal.reject (di.services.actions.agents) are the person's side. The input is stored as the
pipeline journals it (anything that looks like a secret is dropped).
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.services.actions.registry import ACTIONS
from di.services.actions.scope import case_scope
from di.services.agents import registry

if TYPE_CHECKING:
    from di.services.actions.pipeline import CallContext

_COLS = "id, agent, action, input, case_id, run_id, status, created_at, decided_by, decided_at, result"


def holds(s: Session, agent_id: str) -> bool:
    a = registry.get(s, agent_id)
    return a is not None and a.autonomy == "propose"


def hold(ctx: "CallContext", action: str, i: dict[str, Any], case_id: str | None) -> int:
    pid: int = ctx.session.execute(
        text(
            "INSERT INTO agent_proposal (agent, action, input, case_id, run_id, status, created_at) "
            "VALUES (:a, :act, CAST(:i AS jsonb), :c, :r, 'pending', :at) RETURNING id"
        ),
        {"a": ctx.preparer, "act": action, "i": json.dumps(i, default=str), "c": case_id, "r": ctx.run_id, "at": ctx.now},
    ).scalar_one()
    # a journal event, so the live stream (filtered by the case's tenant) refreshes the inboxes; never the input
    ctx.session.execute(
        text("INSERT INTO domain_event (type, case_id, payload, at) VALUES ('proposal.held', :c, CAST(:p AS jsonb), :at)"),
        {"c": case_id, "p": json.dumps({"id": pid, "action": action, "agent": ctx.preparer}), "at": ctx.now},
    )
    return pid


def get(s: Session, pid: int, for_update: bool = False) -> dict | None:
    lock = " FOR UPDATE" if for_update else ""
    row = s.execute(text(f"SELECT {_COLS} FROM agent_proposal WHERE id = :i{lock}"), {"i": pid}).mappings().first()  # noqa: S608 - fixed columns
    return dict(row) if row else None


def decide(s: Session, pid: int, status: str, by: str, at: datetime, result: dict[str, Any]) -> None:
    s.execute(
        text(
            "UPDATE agent_proposal SET status = :st, decided_by = :by, decided_at = :at, result = CAST(:r AS jsonb) "
            "WHERE id = :i"
        ),
        {"st": status, "by": by, "at": at, "r": json.dumps(result, default=str), "i": pid},
    )


def may_decide(p: dict, account: policy.Account, pctx: policy.Context) -> bool:
    """The person holds the held action's permission and, for a case, may see its tenant."""
    a = ACTIONS.get(p["action"])
    if a is None or (a.permission and not policy.can(account, a.permission, pctx)):
        return False
    if not p["case_id"]:
        return True
    where = case_scope(p["case_id"])
    if where is None:  # a case the server cannot place: nobody decides it (fail closed)
        return False
    return policy.tenant_ok(account, where[0], pctx) and policy.location_ok(account, where[1])


_WHY_KEYS = ("reason", "rationale", "note", "message", "comment")


def why(p: dict) -> str:
    """Why the agent proposes it: the reason it gave in the input, else what the held action is for."""
    i = p["input"] if isinstance(p["input"], dict) else {}
    for k in _WHY_KEYS:
        if isinstance(i.get(k), str) and i[k].strip():
            return str(i[k]).strip()
    a = ACTIONS.get(p["action"])
    return a.desc if a and a.desc else ""


def pending_for(s: Session, account: policy.Account, pctx: policy.Context) -> list[dict]:
    rows = s.execute(text(f"SELECT {_COLS} FROM agent_proposal WHERE status = 'pending' ORDER BY id")).mappings()  # noqa: S608 - fixed columns
    names = {a.id: a.name for a in registry.all_agents(s)}
    out = []
    for r in map(dict, rows):
        if may_decide(r, account, pctx):
            a = ACTIONS[r["action"]]
            out.append(
                {
                    "id": r["id"], "agent": r["agent"], "agentName": names.get(r["agent"], r["agent"]), "action": r["action"],
                    "title": a.title, "why": why(r), "input": r["input"], "case_id": r["case_id"], "run_id": r["run_id"],
                    "at": r["created_at"].isoformat(),
                }
            )  # fmt: skip
    return out
