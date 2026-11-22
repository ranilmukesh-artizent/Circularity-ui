"""The /api/screens/command endpoints (Command Center). What they serve, the filters, and the facade map:
di.services.screens.command."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import command as svc
from di.services.screens.command import Filters

router = APIRouter(prefix="/api/screens/command", tags=["screens: command"])
Mode = Annotated[str, Query(pattern="^(operational|senior)$")]


def scope_filters(
    tenant: str = "All", site: str = "", cls: str = "", route: str = "", months: Annotated[int, Query(ge=1, le=12)] = 12
) -> Filters:
    return Filters(tenant, site, cls, route, months)


def table_filters(
    f: Annotated[Filters, Depends(scope_filters)], stage: str = "", due: str = "", reason: str = "", q: str = ""
) -> Filters:
    f.stage, f.due, f.reason, f.q = stage, due, reason, q
    return f


ScopeFilters = Annotated[Filters, Depends(scope_filters)]
TableFilters = Annotated[Filters, Depends(table_filters)]


@router.get("/layout")
def get_layout(p: CurrentPrincipal, session: DbSession, mode: Mode = "operational") -> dict:
    """The role's Command Center layout, its key figures and the sections the account may open."""
    return svc.layout_page(p, session, mode)


@router.get("/kpis")
def get_kpis(f: ScopeFilters, p: CurrentPrincipal, session: DbSession, mode: Mode = "operational") -> dict:
    """Key figures: the layout's tiles, the "needs attention now" line, the totals and the health strip."""
    return svc.kpis_page(p, session, f, mode)


@router.get("/charts")
def get_charts(f: ScopeFilters, p: CurrentPrincipal, session: DbSession) -> dict:
    """The charts and panels: lifecycle stages, due windows, routes, value at risk, value realisation, signals and
    capacity."""
    return svc.charts_page(p, session, f)


@router.get("/actions")
def get_actions(f: TableFilters, p: CurrentPrincipal, session: DbSession) -> dict:
    """The ranked table of actions to prioritise, with the table's view, due, reason and search filters."""
    return svc.actions_page(p, session, f)


@router.get("/exceptions")
def get_exceptions(f: ScopeFilters, p: CurrentPrincipal, session: DbSession) -> dict:
    """Exceptions by warehouse, and the decisions awaiting approval (the senior view's read-only queue)."""
    return svc.exceptions_page(p, session, f)


@router.get("/aome")
def get_aome(p: CurrentPrincipal, session: DbSession, all: bool = False, tenant: str = "All") -> dict:
    """Actions on me, at the home site or (all=true) every location, in the tenant menu's tenant."""
    return svc.aome_page(p, session, all, tenant)


@router.get("/handed")
def get_handed(p: CurrentPrincipal, session: DbSession, all: bool = False, tenant: str = "All") -> dict:
    """Handed off and awaiting outcome, and waiting for approval, at the home site or (all=true) every location."""
    return svc.handed_page(p, session, all, tenant)


@router.get("/outcomes")
def get_outcomes(p: CurrentPrincipal, session: DbSession, tenant: str = "All") -> dict:
    """Outcomes reported by the enterprise systems and waiting for Finance."""
    return svc.outcomes_page(p, session, tenant)


@router.get("/inbox")
def get_inbox(p: CurrentPrincipal, session: DbSession, tenant: str = "All") -> dict:
    """The Approvals inbox: requests the account may decide, its delegated scope and the approval cards."""
    return svc.inbox_page(p, session, tenant)


@router.get("/health")
def get_health(p: CurrentPrincipal, session: DbSession) -> dict:
    """Integration health for the Developer and Admin views."""
    return svc.health_page(p, session)
