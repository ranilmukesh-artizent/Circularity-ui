"""The /api/screens/agent-activity endpoint (Agent activity). What it returns and its access:
di.services.screens.agent_activity."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import agent_activity as svc

router = APIRouter(prefix="/api/screens/agent-activity", tags=["screens: agent activity"])


@router.get("")
def agent_activity(p: CurrentPrincipal, session: DbSession):
    return svc.page(p, session)
