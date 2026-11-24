"""The /api/screens/orgs endpoints (Organisation). What each returns, its access and the facade map:
di.services.screens.orgs."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import orgs as svc

router = APIRouter(prefix="/api/screens/orgs", tags=["screens: orgs"])


@router.get("")
def org_units(p: CurrentPrincipal, session: DbSession):
    return svc.page(p, session)


@router.get("/{unit}/pilot")
def pilot_report(unit: str, p: CurrentPrincipal, session: DbSession):
    return svc.pilot(p, session, unit)
