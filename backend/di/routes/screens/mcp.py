"""The /api/screens/mcp endpoints (MCP & Tools). What each returns, its access and the facade map:
di.services.screens.mcp."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import mcp as svc

router = APIRouter(prefix="/api/screens/mcp", tags=["screens: mcp"])


@router.get("/tools")
def tools(p: CurrentPrincipal):
    p.require_page("mcp", "catalog")
    return svc.tools()


@router.get("/agents")
def agents(p: CurrentPrincipal):
    p.require_page("mcp", "agents")
    return svc.agents()


@router.get("/generated")
def generated(p: CurrentPrincipal, session: DbSession):
    p.require_page("mcp", "agents")
    return svc.generated(session)


@router.get("/matrix")
def matrix(p: CurrentPrincipal, tenant: str | None = None):
    p.require_page("mcp", "perms")
    out = svc.matrix(tenant)
    if out is None:
        raise HTTPException(404, {"code": "not_found", "message": f"Unknown tenant {tenant}."})
    return out


@router.get("/calls")
def calls(
    p: CurrentPrincipal,
    session: DbSession,
    filter: Annotated[str, Query(pattern="^(all|issues)$")] = "all",
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
):
    p.require_page("mcp", "calls")
    return svc.calls(session, p, filter, limit)


@router.get("/client")
def client_servers(p: CurrentPrincipal, session: DbSession):
    p.require_page("mcp", "client")
    return svc.client_servers(session)


@router.get("/proposals")
def proposals(p: CurrentPrincipal, session: DbSession):
    p.require_page("mcp", "proposals")
    return svc.proposals(session, p)
