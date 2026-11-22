"""The /api/checks endpoint (Home › Data checks). What it serves, and the checks: di.services.screens.checks."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import checks as svc

router = APIRouter(tags=["screens: checks"])


@router.get("/api/checks")
def checks(p: CurrentPrincipal, session: DbSession):
    return svc.page(p, session)
