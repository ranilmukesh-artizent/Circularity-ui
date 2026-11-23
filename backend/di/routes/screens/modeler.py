"""The /api/screens/modeler endpoint (the Modeler page). What it returns, its access and the facade map:
di.services.screens.modeler."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import modeler as svc

router = APIRouter(prefix="/api/screens/modeler", tags=["screens: modeler"])


@router.get("")
def modeler(p: CurrentPrincipal, session: DbSession, template: str | None = None, org: str | None = None):
    return svc.page(p, session, template, org)
