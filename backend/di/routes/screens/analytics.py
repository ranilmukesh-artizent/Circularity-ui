"""The /api/screens/analytics endpoint. What it serves, and the facade map: di.services.screens.analytics (which also
registers the read action analytics.models)."""

from typing import Annotated

from fastapi import APIRouter, Query

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
):
    p.require_page("analytics")
    return svc.page(p, session, tenant, cls, route, from_, to, model, tenant_filter)
