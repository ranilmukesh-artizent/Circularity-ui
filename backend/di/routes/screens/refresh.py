"""The /api/screens/refresh endpoint (the contract refresh case panel). What it returns, its access and the facade map:
di.services.screens.refresh."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import refresh as svc

router = APIRouter(prefix="/api/screens/refresh", tags=["screens: refresh"])


@router.get("/{case_id}")
def refresh_view(case_id: str, p: CurrentPrincipal, session: DbSession):
    return svc.view(session, p, case_id)
