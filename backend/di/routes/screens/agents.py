"""The /api/screens/agents endpoint (the Agents page). What it returns, its access and the facade map:
di.services.screens.agents."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import agents as svc

router = APIRouter(prefix="/api/screens/agents", tags=["screens: agents"])


@router.get("")
def agents(p: CurrentPrincipal, session: DbSession):
    return svc.page(p, session)


@router.get("/models")
def models(p: CurrentPrincipal, session: DbSession):
    return svc.models(p, session)
