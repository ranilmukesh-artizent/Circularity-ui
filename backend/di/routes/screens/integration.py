"""The /api/screens/integration endpoints (Connection Fabric). What each returns, its access and the facade map:
di.services.screens.integration."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from di.core import policy
from di.core.auth import Principal
from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import integration as svc

router = APIRouter(prefix="/api/screens/integration", tags=["screens: integration"])

SECTIONS_SOURCES = ("overview", "map", "tables", "models", "monitor")


def _require_any(p: Principal, *sections: str) -> None:
    if not any(policy.can_page(p.account, "integration", s) for s in sections):
        p.require_page("integration", sections[0])


@router.get("/sources")
def sources(
    p: CurrentPrincipal,
    session: DbSession,
    cat: str | None = None,
    status: str | None = None,
    method: str | None = None,
    q: str | None = None,
):
    _require_any(p, *SECTIONS_SOURCES)
    return svc.sources(session, p, cat, status, method, q)


@router.get("/sources/{source_id}")
def source_detail(source_id: str, p: CurrentPrincipal, session: DbSession, days: Annotated[int, Query(ge=1, le=180)] = 30):
    _require_any(p, *SECTIONS_SOURCES)
    out = svc.source_detail(session, p, source_id, days)
    if out is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No source {source_id}."})
    return out


@router.get("/overview")
def overview(p: CurrentPrincipal, session: DbSession):
    _require_any(p, "overview")
    return svc.overview(session, p)


@router.get("/map")
def source_map(p: CurrentPrincipal, session: DbSession, limit: Annotated[int, Query(ge=1, le=2000)] = 100):
    _require_any(p, "map")
    return svc.source_map(session, p, limit)


@router.get("/tables")
def tables(p: CurrentPrincipal, session: DbSession, source: str | None = None):
    _require_any(p, "tables")
    out = svc.tables(session, p, source)
    if out is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No table model for {source}."})
    return out


@router.get("/models")
def models(p: CurrentPrincipal, session: DbSession):
    _require_any(p, "models")
    return svc.models(session, p)


@router.get("/events")
def events(
    p: CurrentPrincipal,
    session: DbSession,
    dir: Annotated[str | None, Query(pattern="^(in|out)$")] = None,
    issues: bool = False,
    q: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
):
    _require_any(p, "events")
    return svc.events(session, p, dir, issues, q, limit)


@router.get("/conflicts")
def conflicts(
    p: CurrentPrincipal,
    session: DbSession,
    status: Annotated[Literal["open", "resolved", "all"], Query()] = "open",
    source: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
):
    _require_any(p, "conflicts")
    return svc.conflicts(session, p, status, source, limit)


@router.get("/monitor")
def monitor(p: CurrentPrincipal, session: DbSession):
    _require_any(p, "monitor")
    return svc.monitor(session, p)
