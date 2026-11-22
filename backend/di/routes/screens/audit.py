"""The /api/screens/audit endpoints. What they serve, and the facade map: di.services.screens.audit."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import audit as svc

router = APIRouter(prefix="/api/screens/audit", tags=["screens: audit"])


@router.get("")
def audit(p: CurrentPrincipal, session: DbSession, tenant_filter: str = "All"):
    p.require_page("audit")
    return svc.page(p, session, tenant_filter)


@router.get("/provenance")
def provenance_of(case_id: str, key: str, p: CurrentPrincipal, session: DbSession):
    p.require_page("audit")
    return svc.provenance_of(p, session, case_id, key)


@router.get("/comments")
def comments(key: str, p: CurrentPrincipal, session: DbSession):  # noqa: ARG001 - the dependency authenticates the caller
    """Comments under one record key (an audit entry "au:<id>", a source "src:<id>" ...): everyone signed in reads."""
    return svc.comments(session, key)
