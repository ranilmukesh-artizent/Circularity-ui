"""MCP & Tools (#/mcp): the governed tool catalog, the agent registry, the permission matrix, the call log, the
enterprise MCP servers Circularity consumes, and MCP server proposals (B14).

    GET /api/screens/mcp/tools                 the ten tools (with input schema and approval rule) and the hard rules
    GET /api/screens/mcp/agents                the agents, their scopes, tools, limits and call counts
    GET /api/screens/mcp/generated             per registered agent, the tools generated from the action catalogue with
                                               their hints (plan 9 P9-2.13; section "agents")
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
- the servers: the workspace collection "mcp_servers" (di.services.actions.access; an approved proposal joins it);
- the call log: the demo's CALLS, generated at load, as the workspace collection "mcp_calls" registered here and
  seeded from the golden file. Nothing writes it yet: the playground's calls (runPlaygroundTool) stay in the browser
  until the MCP server (B16) logs every call here;
- proposals: the workspace collection "requests" (di.repositories.common).

Facade (frontend/src/api/mcp.ts) → here:

| export | where |
|---|---|
| tools, toolById, hardRules | GET /tools |
| mcpAgents | GET /agents |
| generated (useMcp) | GET /generated |
| permCell (per agent, tool and tenant) | GET /matrix?tenant= |
| toolCalls, caseOpenable | GET /calls (`openable` on each call) |
| clientServers | GET /client |
| mcpProposals (access.ts) | GET /proposals |
| tenantList, journeyStep, PERM_CHIP, registryTools (the actions catalog and RISK_LABEL) | reference |
| toolSchema, exampleInput, autoAgent, jsonHtml | frontend-only (pure functions of a tool and the agents) |
| runPlaygroundTool | the playground's simulated call (not an action); B16 serves real tool calls |
| benchCases, runBench, runBenchAll, benchBadgeHtml | the agent test bench runs the in-browser agent layer; B16b |

The endpoints are in di.routes.screens.mcp (parameters and access); this module builds what each returns.
"""

from sqlalchemy.orm import Session

from di.core import policy, state
from di.core.auth import Principal
from di.repositories import mcp_calls  # noqa: F401 - registers the "mcp_calls" collection this page reads
from di.repositories.access import request_rows
from di.repositories.constants import AGENTS, HARD_RULES, TOOLS
from di.repositories.context import case_openable
from di.services.agents import registry as agent_registry


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


# ---------------------------------------------------------------- what each endpoint returns
def tools() -> dict:
    """GET /tools."""
    return {"tools": TOOLS, "hard_rules": HARD_RULES}


def agents() -> dict:
    """GET /agents."""
    return {"agents": AGENTS}


def generated(session: Session) -> dict:
    """GET /generated: each registered agent's tools generated from the action catalogue, with the hints (P9-2.13)."""
    from di.mcp.catalog_tools import tools_for  # late: di.mcp imports the action modules this page need not load

    rows = []
    for a in agent_registry.all_agents(session):
        tools = [
            {
                "tool": t.name, "action": (t.meta or {}).get("action"), "read_only": t.annotations.read_only_hint,
                "destructive": t.annotations.destructive_hint, "needs_person": (t.meta or {}).get("requiresHumanApproval"),
            }
            for t in tools_for(a)
            if t.annotations is not None
        ]  # fmt: skip
        rows.append({"agent": a.id, "name": a.name, "tools": tools})
    return {"agents": rows}


def matrix(tenant: str | None) -> dict | None:
    """GET /matrix: permCell for every agent and tool on behalf of the tenant (the first one by default); None for an
    unknown tenant."""
    tenants = policy.tenants()
    ten = tenant or tenants[0]
    if ten not in tenants:
        return None
    rows = [{"agent": a["id"], "cells": [{"tool": t["id"]} | perm_cell(a, t, ten) for t in TOOLS]} for a in AGENTS]
    return {"tenant": ten, "tenants": tenants, "tools": [t["id"] for t in TOOLS], "rows": rows}


def calls(session: Session, p: Principal, filter: str, limit: int | None) -> dict:
    """GET /calls: the call log, newest first, with whether this account may open each call's case."""
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


def client_servers(session: Session) -> dict:
    """GET /client."""
    return {"servers": state.items(session, "mcp_servers")}


def proposals(session: Session, p: Principal) -> dict:
    """GET /proposals."""
    return {"proposals": request_rows(session, p, kind="mcp")}
