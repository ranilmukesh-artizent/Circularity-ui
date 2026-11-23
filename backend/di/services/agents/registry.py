"""The agent registry at runtime (plan 8, MVP-11.3): table agent_identity (migration 0023).

    get(s, agent_id) -> Agent | None     a registered agent
    all_agents(s) -> [Agent]             every one, seeded first, then by id
    in_scope(agent, owner, units) -> bool   the case owner (an org unit) is in the agent's org scope (empty: all)

The demo's nine agents are seeded (kind internal, autonomy act). Admin registers and edits others with agent.register
and agent.update (di.services.actions.agents); agent.setEnabled is the kill switch.
"""

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import orgs


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    kind: str
    autonomy: str
    enabled: bool
    org_scope: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    created_by: str | None = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


_COLS = "id, name, kind, org_scope, tools, autonomy, enabled, created_by"


def _agent(row: dict) -> Agent:
    return Agent(
        id=row["id"],
        name=row["name"] or row["id"],
        kind=row["kind"],
        autonomy=row["autonomy"],
        enabled=row["enabled"],
        org_scope=list(row["org_scope"] or []),
        tools=list(row["tools"] or []),
        created_by=row["created_by"],
    )


def get(s: Session, agent_id: str) -> Agent | None:
    row = s.execute(text(f"SELECT {_COLS} FROM agent_identity WHERE id = :i"), {"i": agent_id}).mappings().first()  # noqa: S608 - fixed column list
    return _agent(dict(row)) if row else None


def all_agents(s: Session) -> list[Agent]:
    rows = s.execute(text(f"SELECT {_COLS} FROM agent_identity ORDER BY created_at, id")).mappings()  # noqa: S608 - fixed column list
    return [_agent(dict(r)) for r in rows]


def in_scope(agent: Agent, owner: str, units: dict[str, orgs.OrgUnit]) -> bool:
    """An empty scope covers every org; otherwise the owner is in the subtree of one of the scope's units."""
    return not agent.org_scope or any(owner in orgs.subtree(units, u) for u in agent.org_scope)
