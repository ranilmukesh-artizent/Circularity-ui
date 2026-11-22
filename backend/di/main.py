import logging

from fastapi import FastAPI

import di.repositories.cases  # registers action handlers
import di.repositories.workspace  # registers action handlers
import di.services.actions.access  # registers action handlers
import di.services.actions.decisions  # registers action handlers
import di.services.actions.engine  # registers action handlers
import di.services.actions.execution  # registers action handlers
import di.services.actions.integration  # registers action handlers
import di.services.actions.workflow_builder  # registers action handlers (workflow.draft, workflow.plan)
import di.services.actions.workflow_drafts  # registers action handlers (workflow.draft.save, workflow.draft.discard, testRun)
import di.services.actions.workflows  # noqa: F401  (registers action handlers)
from di.core.errors import register as register_error_handlers
from di.core.logs import configure_logging
from di.mcp import server as mcp_server
from di.routes import actions, ask, auth, health, screens, sources, stream, webhooks
from di.services.cases import use_database_scope

configure_logging()  # one format and level for di and uvicorn; secrets masked in access lines (di/core/logs.py)
log = logging.getLogger("di.api")
app = FastAPI(title="Circularity DI API", version="0.2.0", lifespan=mcp_server.lifespan)
register_error_handlers(app)  # every error answers {ok: false, error: {code, message}} (di/core/errors.py, D1)
app.include_router(auth.router)
app.include_router(actions.router)
app.include_router(sources.router)
app.include_router(webhooks.router)
app.include_router(screens.router)
app.include_router(stream.router)
app.include_router(ask.router)  # POST /api/ask (B16b; di.services.ask)
mcp_server.mount(app)  # the MCP server at /mcp (B16; di.mcp)
use_database_scope()
app.include_router(health.router)  # GET /api/health/live, GET /api/health
