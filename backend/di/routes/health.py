"""GET /api/health/live and GET /api/health (di.services.health)."""

from fastapi import APIRouter

from di.core.deps import DbSession
from di.services import health as health_service

router = APIRouter()


@router.get("/api/health/live")
def live() -> dict:
    """Process is up (used by the container healthcheck)."""
    return {"status": "ok"}


@router.get("/api/health")
def health(session: DbSession) -> dict:
    """Process, database and source-sim reachability, for the web status page."""
    return health_service.check(session)
