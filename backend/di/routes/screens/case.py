"""The /api/screens/case endpoints (the case pages). What each returns, its access and the facade map:
di.services.screens.case."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import case as svc

router = APIRouter(prefix="/api/screens/case", tags=["screens: case"])


@router.get("/{case_id}")
def case_page(case_id: str, p: CurrentPrincipal, session: DbSession):
    """Everything the stage bar, the stage pages, the Overview and the approval card read, for one case (load_case
    refuses as the case actions do)."""
    return svc.case_page(session, p, case_id)


@router.get("/{case_id}/analysis")
def case_analysis(case_id: str, p: CurrentPrincipal, session: DbSession, tenant: str = "All"):
    """The data behind the stage pages' detail tabs and Full analysis (`tenant`: the top-bar filter, for the repair
    centre's load)."""
    return svc.case_analysis(session, p, case_id, tenant)
