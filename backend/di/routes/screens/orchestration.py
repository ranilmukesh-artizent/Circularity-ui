"""The /api/screens/orchestration endpoints (Process orchestration). What each returns, its access and the facade map:
di.services.screens.orchestration."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import orchestration as svc

router = APIRouter(prefix="/api/screens/orchestration", tags=["screens: orchestration"])


@router.get("/cases")
def cases(p: CurrentPrincipal, session: DbSession, tenant: str = "All"):
    """The demo's orCases and orCase."""
    p.require_page("orchestration")
    return svc.cases(session, p, tenant)


@router.get("/run/{case_id}")
def case_run(case_id: str, p: CurrentPrincipal, session: DbSession, fail: str = ""):
    """One case's run, as the live board, the run details and the trace read it (load_case refuses as the case actions
    do)."""
    return svc.case_run(session, p, case_id, fail)
