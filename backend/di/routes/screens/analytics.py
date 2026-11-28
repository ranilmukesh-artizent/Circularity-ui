"""The /api/screens/analytics endpoint. What it serves, and the facade map: di.services.screens.analytics (which also
registers the read action analytics.models)."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from di.core import clock
from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import analytics as svc

router = APIRouter(prefix="/api/screens/analytics", tags=["screens: analytics"])


@router.get("")
def analytics(
    p: CurrentPrincipal,
    session: DbSession,
    tenant: str = "",
    cls: str = "",
    route: str = "",
    from_: Annotated[int, Query(alias="from")] = 0,
    to: int = 11,
    model: str = "",
    tenant_filter: str = "All",
    org: str = "",
):
    p.require_page("analytics")
    return svc.page(p, session, tenant, cls, route, from_, to, model, tenant_filter, org)


@router.get("/renewals")
def renewals(p: CurrentPrincipal, session: DbSession, since: date | None = None, until: date | None = None):
    p.require_page("analytics")
    end = until or clock.now().date()
    return svc.renewals(session, p, since or end - timedelta(days=730), end)


@router.get("/pack")
def pack(p: CurrentPrincipal, session: DbSession, key: str = ""):
    p.require_page("analytics")
    try:
        return svc.pack_view(session, p, key)
    except KeyError:
        raise HTTPException(404, {"code": "not_found", "message": f"No pack {key}."}) from None


@router.get("/pack-headline")
def pack_headline(p: CurrentPrincipal, session: DbSession, days: Annotated[int, Query(ge=1, le=730)] = 90):
    p.require_page("analytics", "waterfall")  # the section that shows the tiles (and the rows behind them)
    return svc.pack_headlines(session, p, days)
