import logging

import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

import di.actions.access  # registers action handlers
import di.actions.decisions  # registers action handlers
import di.actions.engine  # registers action handlers
import di.actions.execution  # registers action handlers
import di.actions.integration  # registers action handlers
import di.actions.workflows  # registers action handlers
import di.reads.cases  # registers action handlers
import di.reads.workspace  # noqa: F401  (registers action handlers)
from di.ask import service as ask_service
from di.cases import use_database_scope
from di.config import get_settings
from di.connectors import webhook
from di.db import get_session
from di.errors import register as register_error_handlers
from di.logs import configure_logging
from di.mcp import server as mcp_server
from di.routers import actions as action_routes
from di.routers import auth as auth_routes
from di.routers import sources as source_routes
from di.screens import router as screen_routes
from di.stream import router as stream_routes

configure_logging()  # one format and level for di and uvicorn; secrets masked in access lines (di/logs.py)
log = logging.getLogger("di.api")
app = FastAPI(title="Circularity DI API", version="0.2.0", lifespan=mcp_server.lifespan)
register_error_handlers(app)  # every error answers {ok: false, error: {code, message}} (di/errors.py, D1)
app.include_router(auth_routes.router)
app.include_router(action_routes.router)
app.include_router(source_routes.router)
app.include_router(webhook.router)
app.include_router(screen_routes)
app.include_router(stream_routes)
app.include_router(ask_service.router)  # POST /api/ask (B16b; di.ask)
mcp_server.mount(app)  # the MCP server at /mcp (B16; di.mcp)
use_database_scope()


@app.get("/api/health/live")
def live() -> dict:
    """Process is up (used by the container healthcheck)."""
    return {"status": "ok"}


@app.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict:
    """Process, database and source-sim reachability, for the web status page."""
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
