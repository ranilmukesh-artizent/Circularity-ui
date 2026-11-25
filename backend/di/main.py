import logging

from fastapi import FastAPI

import di.repositories.cases  # registers action handlers
import di.repositories.workspace  # registers action handlers
import di.services.actions.access  # registers action handlers
import di.services.actions.agents  # registers action handlers (agent.register, agent.update; plan 8)
import di.services.actions.cases_intake  # registers action handlers (case.open; plan 8)
import di.services.actions.compose  # registers action handlers (compose.*: the composition object; plan 9 P9-8.17)
import di.services.actions.config_agent  # registers action handlers (config.read, config.draft: the configuration agent; plan 9)
import di.services.actions.connections  # registers action handlers (registry.*, connection.*: the adapter registry; plan 9)
import di.services.actions.decisions  # registers action handlers
import di.services.actions.engine  # registers action handlers
import di.services.actions.exceptions  # registers action handlers (exception.explain: the exception assistant; plan 9)
import di.services.actions.execution  # registers action handlers
import di.services.actions.fraud  # registers action handlers (fraud.hold, release, reject, simulate; plan 9)
import di.services.actions.integration  # registers action handlers
import di.services.actions.lifecycle  # registers transit.flagDelay (plan 9 P9-2.20)
import di.services.actions.llm  # registers action handlers (llm.models, llm.setModel; plan 9)
import di.services.actions.market_tables  # registers action handlers (marketTable.*: per-market tables; plan 9)
import di.services.actions.modeler  # registers action handlers (flow.*: the decision flow lifecycle; plan 8)
import di.services.actions.modeler_suggest  # registers action handlers (flow.suggestions; plan 8)
import di.services.actions.models  # registers action handlers (model.fit, model.promote; plan 8)
import di.services.actions.org_pack  # registers action handlers (org.exportPack, org.importPack; plan 8)
import di.services.actions.org_pilot  # registers action handlers (org.setPilot, org.pilotReport; plan 8)
import di.services.actions.orgs  # registers action handlers (org.create, org.update, org.move, org.tree; plan 8)
import di.services.actions.overlays  # registers action handlers (overlay.*: the customer overlay of a pack; plan 9)
import di.services.actions.packs  # registers action handlers (pack.*: pack versions with maker-checker; plan 9)
import di.services.actions.proposals  # registers action handlers (proposal.accept, proposal.reject; plan 8)
import di.services.actions.standing_policy  # registers action handlers (standingPolicy.*, policy approval; plan 9)
import di.services.actions.tools  # registers action handlers (tools.find: the tool search; plan 9)
import di.services.actions.work  # registers action handlers (case.needInfo, work.resolve, work.assign; plan 9)
import di.services.actions.workflow_author  # registers action handlers (workflow.author: a draft from a sentence, P9-8.12)
import di.services.actions.workflow_builder  # registers action handlers (workflow.draft, workflow.plan)
import di.services.actions.workflow_drafts  # registers action handlers (workflow.draft.save, workflow.draft.discard, testRun)
import di.services.actions.workflow_read  # registers action handlers (workflow.list, get, runs, runGet: reads for Ask; P9-2.23)
import di.services.actions.workflows  # noqa: F401  (registers action handlers)
from di.core.errors import register as register_error_handlers
from di.core.logs import configure_logging
from di.mcp import server as mcp_server
from di.routes import actions, agents, ask, auth, health, screens, sources, stream, tasks, webhooks, wellknown
from di.services.actions.registry import ACTIONS
from di.services.agents.forbidden import check_person_only
from di.services.cases import use_database_scope

configure_logging()  # one format and level for di and uvicorn; secrets masked in access lines (di/core/logs.py)
log = logging.getLogger("di.api")
check_person_only(ACTIONS)  # every action module is imported above: agents never delete or approve

app = FastAPI(title="Circularity DI API", version="0.2.0", lifespan=mcp_server.lifespan)
register_error_handlers(app)  # every error answers {ok: false, error: {code, message}} (di/core/errors.py, D1)
app.include_router(auth.router)
app.include_router(actions.router)
app.include_router(sources.router)
app.include_router(webhooks.router)
app.include_router(screens.router)
app.include_router(stream.router)
app.include_router(ask.router)  # POST /api/ask (B16b; di.services.ask)
app.include_router(agents.router)  # /api/agents (plan 8 phase 11; di.services.agents)
app.include_router(wellknown.router)  # /.well-known/oauth-protected-resource (P9-2.14; di.mcp.oauth)
mcp_server.mount(app)  # the MCP server at /mcp (B16; di.mcp)
use_database_scope()
app.include_router(health.router)  # GET /api/health/live, GET /api/health
app.include_router(tasks.router)  # /api/v1/tasks: CRUD over the job queue (plan 2; di.services.tasks)
