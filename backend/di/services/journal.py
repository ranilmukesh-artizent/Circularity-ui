"""The action catalog and the action journal (Audit), behind di.routes.actions (docs/backend-steps.md, B8)."""

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal
from di.services.actions.registry import ACTIONS
from di.services.actions.scope import case_scope


def catalog(p: Principal) -> list[dict]:
    """Every action, with what the signed-in account may call."""
    out = []
    for a in ACTIONS.values():
        allowed = a.risk != "system" and (a.permission is None or policy.can(p.account, a.permission, p.ctx))
        out.append(
            {
                "id": a.id,
                "title": a.title,
                "desc": a.desc,
                "risk": a.risk,
                "perm": a.perm,
                "scope": a.scope,
                "input": a.input,
                "allowed": allowed,
                "available": a.handler is not None,
            }
        )
    return out


def entries(p: Principal, session: Session, case_id: str | None, limit: int) -> list[dict]:
    """The journal, newest first, without the entries of cases this account may not see."""
    # A Planner sees their own tenants' cases only; journal entries without a case are visible to the auditor roles.
    # The cases this account may not see are excluded in SQL, so LIMIT counts visible entries only.
    journaled = session.execute(text("SELECT DISTINCT case_id FROM action_journal WHERE case_id IS NOT NULL")).scalars()
    hidden = [c for c in journaled if not _may_see(p, c)]
    rows = session.execute(
        text(
            "SELECT seq, action, input, actor, role, preparer, run_id, case_id, output_ref, undone, at FROM action_journal "
            "WHERE (CAST(:c AS text) IS NULL OR case_id = :c) AND (case_id IS NULL OR case_id <> ALL(CAST(:hidden AS text[]))) "
            "ORDER BY seq DESC LIMIT :n"
        ),
        {"c": case_id, "hidden": hidden, "n": max(1, min(limit, 500))},
    ).mappings()
    return [dict(r) for r in rows]


def _may_see(p: Principal, case_id: str) -> bool:
    """The tenant boundary and warehouse lock for one journaled case; an unknown case is not restricted."""
    where = case_scope(case_id)
    return not where or (p.tenant_ok(where[0]) and p.location_ok(where[1]))


def undo(p: Principal, session: Session, seqs: list[int]) -> dict:
    """Marks entries as undone. Reversing their effects is each handler's undo (added with the handlers, B10-B13)."""
    rows = session.execute(text("SELECT seq, actor FROM action_journal WHERE seq = ANY(:s)"), {"s": seqs}).all()
    if len(rows) != len(set(seqs)):
        raise HTTPException(404, {"code": "not_found", "message": "Some journal entries do not exist."})
    if not policy.policy(p.account).get("all") and any(r.actor != p.account.id for r in rows):
        raise HTTPException(403, {"code": "out_of_scope", "message": "You can only undo your own actions."})
    session.execute(text("UPDATE action_journal SET undone = true WHERE seq = ANY(:s)"), {"s": seqs})
    session.commit()
    return {"undone": sorted(seqs)}
