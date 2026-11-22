"""Process, database and source-sim reachability (GET /api/health, di.routes.health)."""

import logging

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.config import get_settings

log = logging.getLogger("di.api")


def check(session: Session) -> dict:
    checks: dict[str, dict] = {}
    try:
        rev = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks["database"] = {"ok": True, "migration": rev}
    except Exception:  # the detail goes to the log only (it can name hosts and users)
        log.exception("health: database check failed")
        checks["database"] = {"ok": False, "error": "unreachable"}
    try:
        r = httpx.get(f"{get_settings().source_sim_url}/health", timeout=2)
        r.raise_for_status()
        checks["source_sim"] = {"ok": True, **r.json()}
    except Exception:
        log.exception("health: source-sim check failed")
        checks["source_sim"] = {"ok": False, "error": "unreachable"}
    return {"status": "ok" if all(c["ok"] for c in checks.values()) else "degraded", "checks": checks}
