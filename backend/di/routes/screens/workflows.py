"""The /api/screens/workflows endpoints (Workflow Studio). What each returns, its access and the facade map:
di.services.screens.workflows."""

from fastapi import APIRouter, HTTPException

from di.core.auth import Principal
from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import workflows as svc

router = APIRouter(prefix="/api/screens/workflows", tags=["screens: workflows"])


def require_studio(p: Principal) -> None:
    p.require_page("integration", "studio")


def _not_found(e: svc.NotFound) -> HTTPException:
    return HTTPException(404, {"code": "not_found", "message": str(e)})


@router.get("")
def workflow_list(
    p: CurrentPrincipal,
    session: DbSession,
    cat: str | None = None,
    status: str | None = None,
    src: str | None = None,
    q: str | None = None,
):
    require_studio(p)
    return svc.workflow_list(session, cat, status, src, q)


@router.get("/blocks")
def workflow_blocks(p: CurrentPrincipal):
    require_studio(p)
    return svc.workflow_blocks()


@router.get("/schema")
def workflow_schema(p: CurrentPrincipal):
    require_studio(p)
    return svc.workflow_schema()


@router.get("/{workflow_id}")
def workflow_detail(workflow_id: str, p: CurrentPrincipal, session: DbSession):
    require_studio(p)
    try:
        return svc.workflow_detail(session, workflow_id, p.account.id)
    except svc.NotFound as e:
        raise _not_found(e) from None


@router.get("/{workflow_id}/compare")
def workflow_compare(workflow_id: str, a: str, p: CurrentPrincipal, session: DbSession, b: str | None = None):
    require_studio(p)
    try:
        return svc.workflow_compare(session, workflow_id, a, b)
    except svc.NotFound as e:
        raise _not_found(e) from None
