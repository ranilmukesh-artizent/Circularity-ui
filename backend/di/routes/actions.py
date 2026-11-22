"""The action endpoint the frontend's invoke() calls (docs/backend-steps.md, B8).

POST /api/actions/{id}        body: the action's input (JSON object)
    headers (optional): Idempotency-Key, X-Circularity-Preparer (agent id), X-Circularity-Confirmed: true,
                        X-Circularity-Run (agent run id)
    → 200 {ok: true, output, key, action, seq}  or  4xx {ok: false, error: {code, message}}
GET  /api/actions             the catalog, with what the signed-in account may call
GET  /api/journal             the action journal (Audit), newest first
POST /api/journal/undo        mark journal entries as undone (the person who acted, or Admin)
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from di.core.deps import CurrentPrincipal, DbSession, OptionalPrincipal
from di.schemas.actions import Undo
from di.services import journal as journal_service
from di.services.actions.pipeline import ERROR_STATUS, Actor, CallContext, invoke

router = APIRouter(prefix="/api", tags=["Actions"])


@router.post("/actions/{action_id}")
def call_action(
    action_id: str,
    p: OptionalPrincipal,
    session: DbSession,
    body: Annotated[Any, Body()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
    x_circularity_preparer: Annotated[str | None, Header()] = None,
    x_circularity_confirmed: Annotated[str | None, Header()] = None,
    x_circularity_run: Annotated[str | None, Header()] = None,
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
def catalog(p: CurrentPrincipal):
    return journal_service.catalog(p)


@router.get("/journal")
def journal(p: CurrentPrincipal, session: DbSession, case_id: str | None = None, limit: int = 100):
    p.require_page("audit")
    return journal_service.entries(p, session, case_id, limit)


@router.post("/journal/undo")
def undo(body: Undo, p: CurrentPrincipal, session: DbSession):
    """Marks entries as undone. Reversing their effects is each handler's undo (added with the handlers, B10-B13)."""
    return journal_service.undo(p, session, body.seqs)
