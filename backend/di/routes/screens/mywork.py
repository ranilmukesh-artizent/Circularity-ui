"""The /api/screens/mywork endpoint (My work). What it returns and the facade map: di.services.screens.mywork."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import mywork as svc

router = APIRouter(prefix="/api/screens/mywork", tags=["screens: mywork"])


@router.get("")
def mywork(p: CurrentPrincipal, session: DbSession) -> dict:
    """Everything that waits for the signed-in person: exceptions, approvals, questions, proposals, conflicts and tasks."""
    return svc.page(p, session)
