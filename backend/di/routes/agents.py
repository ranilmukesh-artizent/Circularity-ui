"""Agents (plan 8, phase 11).

GET /api/agents/tools    the tool catalogue (di.services.agents.catalog), filtered to the actions the signed-in
                         account may call; each entry says whether an agent may call it (agent_allowed)
"""

from fastapi import APIRouter

from di.core import policy
from di.core.deps import CurrentPrincipal
from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import catalog

router = APIRouter(prefix="/api/agents", tags=["Agents"])


@router.get("/tools")
def tools(p: CurrentPrincipal) -> list[dict]:
    def mine(action_id: str) -> bool:
        perm = ACTIONS[action_id].permission
        return perm is None or policy.can(p.account, perm, p.ctx)

    return [t for t in catalog() if mine(t["action"])]
