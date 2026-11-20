"""MCP & Tools (#/mcp): the governed tool catalog, the agent registry, the permission matrix, the call log, the
enterprise MCP servers Circularity consumes, and MCP server proposals (B14).

    GET /api/screens/mcp/tools                 the ten tools (with input schema and approval rule) and the hard rules
    GET /api/screens/mcp/agents                the agents, their scopes, tools, limits and call counts
    GET /api/screens/mcp/matrix?tenant=        what each agent may do with each tool on behalf of a tenant (permCell)
    GET /api/screens/mcp/calls?filter=all|issues&limit=
                                               the call log, newest first, each call with whether this account may
                                               open its case; the calls held for approval
    GET /api/screens/mcp/client                the enterprise MCP servers Circularity consumes as a client
    GET /api/screens/mcp/proposals             MCP server proposals (access requests of kind "mcp"), each with
                                               whether this account may decide it

Each needs its section of the MCP page (catalog, agents, perms, calls, client, proposals: Admin, Developer, Approver,
Engineer); other accounts get 403 `out_of_scope`.

All of it is the demo's configuration and state, at parity with the demo (fixtures/golden/screens/mcp.json):
- tools, agents and hard rules: fixtures/golden/tools.json (TOOLS, AGENTS, HARD_RULES);
- the servers: the workspace collection "mcp_servers" (di.actions.access; an approved proposal joins it);
- the call log: the demo's CALLS, generated at load, as the workspace collection "mcp_calls" registered here and
  seeded from the golden file. Nothing writes it yet: the playground's calls (runPlaygroundTool) stay in the browser
  until the MCP server (B16) logs every call here;
- proposals: the workspace collection "requests" (di.reads.common).

Facade (apps/web/src/api/mcp.ts) → here:

| export | where |
|---|---|
| tools, toolById, hardRules | GET /tools |
| mcpAgents | GET /agents |
| permCell (per agent, tool and tenant) | GET /matrix?tenant= |
| toolCalls, caseOpenable | GET /calls (`openable` on each call) |
| clientServers | GET /client |
| mcpProposals (access.ts) | GET /proposals |
| tenantList, journeyStep, PERM_CHIP, registryTools (the actions catalog and RISK_LABEL) | reference |
| toolSchema, exampleInput, autoAgent, jsonHtml | frontend-only (pure functions of a tool and the agents) |
| runPlaygroundTool | the playground's simulated call (not an action); B16 serves real tool calls |
| benchCases, runBench, runBenchAll, benchBadgeHtml | the agent test bench runs the in-browser agent layer; B16b |
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from di import policy, state
from di.deps import CurrentPrincipal, DbSession
from di.reads import mcp_calls  # noqa: F401 - registers the "mcp_calls" collection this page reads
from di.reads.access import request_rows
from di.reads.constants import AGENTS, HARD_RULES, TOOLS
from di.reads.context import case_openable

router = APIRouter(prefix="/api/screens/mcp", tags=["screens: mcp"])


# ---------------------------------------------------------------- the demo's permCell
def perm_cell(a: dict, t: dict, tenant: str) -> dict:
    """What an agent may do with a tool on behalf of a tenant."""
    if t["id"] not in a["tools"]:
        return {"k": "deny", "l": "—", "tip": f"{a['name']} has no scope for {t['id']}"}
    if t["approval"] == "human approval required":
        return {"k": "gate", "l": "Human", "tip": "Allowed to propose; a person must approve before anything is committed"}
    if t["rw"] == "write":
        return {"k": "scope", "l": "Write", "tip": "Write within the agent scope and authority limit"}
    if tenant == "Customer B" and t["id"] in ("optimize_pool", "find_demand"):
        return {"k": "own", "l": "Own only", "tip": "Cross-client demand needs consent; Customer B has none on file"}
    return {"k": "read", "l": "Read", "tip": "Read within the tenant boundary"}


# ---------------------------------------------------------------- endpoints
@router.get("/tools")
def tools(p: CurrentPrincipal):
    p.require_page("mcp", "catalog")
    return {"tools": TOOLS, "hard_rules": HARD_RULES}


@router.get("/agents")
def agents(p: CurrentPrincipal):
    p.require_page("mcp", "agents")
    return {"agents": AGENTS}


@router.get("/matrix")
def matrix(p: CurrentPrincipal, tenant: str | None = None):
    p.require_page("mcp", "perms")
    tenants = policy.tenants()
    ten = tenant or tenants[0]
    if ten not in tenants:
        raise HTTPException(404, {"code": "not_found", "message": f"Unknown tenant {ten}."})
    rows = [{"agent": a["id"], "cells": [{"tool": t["id"]} | perm_cell(a, t, ten) for t in TOOLS]} for a in AGENTS]
    return {"tenant": ten, "tenants": tenants, "tools": [t["id"] for t in TOOLS], "rows": rows}


@router.get("/calls")
def calls(
    p: CurrentPrincipal,
    session: DbSession,
    filter: Annotated[str, Query(pattern="^(all|issues)$")] = "all",
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
):
    p.require_page("mcp", "calls")
    log = state.items(session, "mcp_calls", newest_first=True)
    ok = case_openable(session, p, {c["caseId"] for c in log})
    rows = [c | {"openable": ok.get(c["caseId"], False)} for c in log]
    shown = [c for c in rows if filter == "all" or c["outcome"] != "ok"]
    return {
        "calls": shown[:limit] if limit else shown,
        "held": [c for c in rows if c["outcome"] == "held for approval"][:4],
        "counts": {
            "total": len(rows),
            "issues": sum(1 for c in rows if c["outcome"] != "ok"),
            "held": sum(1 for c in rows if c["outcome"] == "held for approval"),
            "denied": sum(1 for c in rows if c["outcome"].startswith("denied")),
        },
    }


@router.get("/client")
def client_servers(p: CurrentPrincipal, session: DbSession):
    p.require_page("mcp", "client")
    return {"servers": state.items(session, "mcp_servers")}


@router.get("/proposals")
def proposals(p: CurrentPrincipal, session: DbSession):
    p.require_page("mcp", "proposals")
    return {"proposals": request_rows(session, p, kind="mcp")}
