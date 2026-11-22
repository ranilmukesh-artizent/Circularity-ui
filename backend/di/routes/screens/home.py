"""The /api/screens/home endpoints (Home, My Tasks, Alerts, Reports). What they serve, and the facade map:
di.services.screens.home."""

from typing import Annotated

from fastapi import APIRouter, Query

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import home as svc

router = APIRouter(prefix="/api/screens/home", tags=["screens: home"])


@router.get("/briefing")
def get_briefing(p: CurrentPrincipal, session: DbSession) -> list[dict]:
    """The briefing lines for the signed-in role (the demo's afBriefing)."""
    return svc.briefing_page(p, session)


@router.get("/tasks")
def get_tasks(p: CurrentPrincipal, session: DbSession) -> list[dict]:
    """Everything whose next step is the signed-in account's (the demo's aomeItems), each with its My Tasks group."""
    return svc.tasks_page(p, session)


@router.get("/alerts")
def get_alerts(p: CurrentPrincipal, session: DbSession) -> list[dict]:
    """Notifications, escalations and integration issues the account sees (the demo's frAlerts)."""
    return svc.alerts_page(p, session)


@router.get("/kpis")
def get_kpis(p: CurrentPrincipal, session: DbSession) -> list[dict]:
    """Home's KPI tiles for the signed-in role (the demo's frKpis)."""
    return svc.kpis_page(p, session)


@router.get("/activity")
def get_activity(
    p: CurrentPrincipal, session: DbSession, win: Annotated[str, Query(pattern="^(live|today|week)$")] = "today"
) -> list[dict]:
    """Agent-prepared changes and hand-off events in the window (the demo's frActivity)."""
    return svc.activity_page(p, session, win)


@router.get("/middle")
def get_middle(p: CurrentPrincipal, session: DbSession) -> dict:
    """Home's middle panel for the signed-in role."""
    return svc.middle_page(p, session)


@router.get("/figures")
def get_figures(
    p: CurrentPrincipal, session: DbSession, per: Annotated[str, Query(pattern="^(30|90|365)$")] = "30"
) -> list[dict]:
    """Home's key figures for a period of 30, 90 or 365 days."""
    return svc.figures_page(p, session, per)


@router.get("/reports")
def get_reports(p: CurrentPrincipal, session: DbSession) -> list[dict]:
    """The reports the account may open."""
    return svc.reports_page(p, session)


@router.get("/reports/{report_id}")
def get_report_rows(
    report_id: str,
    p: CurrentPrincipal,
    session: DbSession,
    tenant: str = "All",
    period: Annotated[str, Query(pattern="^(30|90|365)$")] = "90",
) -> list[list]:
    """A report's rows (header first) for a tenant ('All' or one the account may see) and a period."""
    return svc.report_page(p, session, report_id, tenant, period)
