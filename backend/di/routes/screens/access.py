"""The /api/screens/access endpoint. What it serves, and the facade map: di.services.screens.access."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import access as svc

router = APIRouter(prefix="/api/screens/access", tags=["screens: access"])


@router.get("")
def access_page(p: CurrentPrincipal, session: DbSession):
    p.require_page("access")
    return svc.page(p, session)
