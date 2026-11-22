"""The /api/screens/product endpoints (Returned assets, Expected returns, the journey strip, Asset intelligence, the
pools). What each returns, its access and the facade map: di.services.screens.product."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import product as svc

router = APIRouter(prefix="/api/screens/product", tags=["screens: product"])


@router.get("/returned")
def returned(p: CurrentPrincipal, session: DbSession, tenant: str = "All"):
    """Returned assets: the queue, the KPI strip, the Expected toggle's count and the account's open notifications."""
    p.require_page("product", "received")
    return svc.returned(session, p, tenant)


@router.get("/expected")
def expected(p: CurrentPrincipal, session: DbSession, tenant: str = "All"):  # noqa: ARG001 - unused dependency left in place (C1 changes no behaviour)
    """Expected returns: the account's (tenant, warehouse, top-bar filter), the toggle's count and the source."""
    p.require_page("product", "expected")
    return svc.expected(p, tenant)


@router.get("/journey/{case_id}")
def journey(case_id: str, p: CurrentPrincipal, session: DbSession):
    """The journey strip and guide on Returned assets (step 0) and Asset intelligence (step 1)."""
    return svc.journey(session, p, case_id)


@router.get("/asset")
def asset_default(p: CurrentPrincipal, session: DbSession):
    """Asset intelligence for the default asset (the frontend passes the remembered one to /asset/{id})."""
    return svc.asset(session, p, svc.default_asset(p, session))


@router.get("/asset/{case_id}")
def asset(case_id: str, p: CurrentPrincipal, session: DbSession):
    """Asset intelligence for one case (load_case refuses as the case actions do)."""
    return svc.asset(session, p, case_id)


@router.get("/pools")
def pools(p: CurrentPrincipal, session: DbSession):
    """The pool optimiser: hidden while pools are off (the demo's FEAT.pools), as canPage('product', 'pools') hides it."""
    p.require_page("product", "pools")
    return svc.pools(session, p)
