"""The action endpoint the frontend's invoke() calls (docs/BACKEND_STEPS.md, B8).

POST /api/actions/{id}        body: the action's input (JSON object)
    headers (optional): Idempotency-Key, X-Circularity-Preparer (agent id), X-Circularity-Confirmed: true,
                        X-Circularity-Run (agent run id)
    → 200 {ok: true, output, key, action, seq}  or  4xx {ok: false, error: {code, message}}
GET  /api/actions             the catalog, with what the signed-in account may call
GET  /api/journal             the action journal (Audit), newest first
POST /api/journal/undo        mark journal entries as undone (the person who acted, or Admin)
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.actions.pipeline import ERROR_STATUS, Actor, CallContext, invoke
from di.actions.registry import ACTIONS
from di.auth import Principal, optional_principal, principal
from di.db import get_session

router = APIRouter(prefix="/api", tags=["Actions"])


@router.post("/actions/{action_id}")
def call_action(
    action_id: str,
    body: Any = Body(default=None),
    p: Principal | None = Depends(optional_principal),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None),
    x_circularity_preparer: str | None = Header(default=None),
    x_circularity_confirmed: str | None = Header(default=None),
    x_circularity_run: str | None = Header(default=None),
):
    if body is not None and not isinstance(body, dict):
        return JSONResponse(
            {"ok": False, "error": {"code": "validation_error", "message": "The input must be a JSON object."}}, 400
        )
    actor = Actor(account=p.account, ctx=p.ctx) if p else Actor(account=None)
    ctx = CallContext(
        actor=actor,
        session=session,
        preparer=x_circularity_preparer,
        confirmed=(x_circularity_confirmed or "").lower() == "true",
        run_id=x_circularity_run,
        idem_key=idempotency_key,
    )
    result = invoke(action_id, body or {}, ctx)
    if result["ok"]:
        session.commit()
        return result
    session.rollback()
    code = result["error"]["code"]
    status = 401 if (p is None and code == "out_of_scope") else ERROR_STATUS.get(code, 400)
    return JSONResponse(result, status_code=status)


@router.get("/actions")
def catalog(p: Principal = Depends(principal)):
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


@router.get("/journal")
def journal(
    case_id: str | None = None, limit: int = 100, p: Principal = Depends(principal), session: Session = Depends(get_session)
):
    p.require_page("audit")
    rows = session.execute(
        text(
            "SELECT seq, action, input, actor, role, preparer, run_id, case_id, output_ref, undone, at FROM action_journal "
            "WHERE (CAST(:c AS text) IS NULL OR case_id = :c) ORDER BY seq DESC LIMIT :n"
        ),
        {"c": case_id, "n": max(1, min(limit, 500))},
    ).mappings()
    visible = []
    for r in rows:
        # a Planner sees their own tenants' cases only; journal entries without a case are visible to the auditor roles
        if r["case_id"]:
            from di.actions.scope import case_scope

            where = case_scope(r["case_id"])
            if where and not (p.tenant_ok(where[0]) and p.location_ok(where[1])):
                continue
        visible.append(dict(r))
    return visible


class Undo(BaseModel):
    seqs: list[int]


@router.post("/journal/undo")
def undo(body: Undo, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """Marks entries as undone. Reversing their effects is each handler's undo (added with the handlers, B10-B13)."""
    rows = session.execute(text("SELECT seq, actor FROM action_journal WHERE seq = ANY(:s)"), {"s": body.seqs}).all()
    if len(rows) != len(set(body.seqs)):
        raise HTTPException(404, {"code": "not_found", "message": "Some journal entries do not exist."})
    if not policy.policy(p.account).get("all") and any(r.actor != p.account.id for r in rows):
        raise HTTPException(403, {"code": "out_of_scope", "message": "You can only undo your own actions."})
    session.execute(text("UPDATE action_journal SET undone = true WHERE seq = ANY(:s)"), {"s": body.seqs})
    session.commit()
    return {"undone": sorted(body.seqs)}
