"""The /api/screens/toolfleet endpoint (the tool fleet case panel). What it returns, its access and the facade map:
di.services.screens.toolfleet."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import toolfleet as svc

router = APIRouter(prefix="/api/screens/toolfleet", tags=["screens: toolfleet"])


@router.get("/{case_id}")
def toolfleet_view(case_id: str, p: CurrentPrincipal, session: DbSession):
    return svc.view(session, p, case_id)
