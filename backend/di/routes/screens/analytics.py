"""The /api/screens/analytics endpoint. What it serves, and the facade map: di.services.screens.analytics (which also
registers the read action analytics.models)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/pack")
def pack(p: CurrentPrincipal, session: DbSession, key: str = ""):
    p.require_page("analytics")
    try:
        return svc.pack_view(session, p, key)
    except KeyError:
        raise HTTPException(404, {"code": "not_found", "message": f"No pack {key}."}) from None
