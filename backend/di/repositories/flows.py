"""The Modeler's process flows as read from `decision_flow` and `decision_flow_version` (plan 8, MVP-3.1). Reads only;
the lifecycle actions (di.services.actions.modeler) write them.

A flow belongs to a template and an org unit. A case uses the flow of the nearest unit, from its owner up to the root
`workspace`, that has one (`flow_for`); the workspace holds the seeded defaults.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from di.core import orgs
from di.repositories.orgs import units

_COLS = "id, template_key, org_unit_id, name, status, ver, dver, maker, checker, draft, published, updated_at, returned"


@dataclass(frozen=True)
class FlowRow:
    id: int
    template_key: str
    org_unit_id: str
    name: str
    status: str  # draft, review, shadow, pub
    ver: int
    dver: int | None
    maker: str | None
    checker: str | None
    draft: dict[str, Any] | None
    published: dict[str, Any]
    updated_at: datetime
    returned: dict[str, Any] | None = None  # {reason, node_id, by, at} of the last return to the maker (0030)


@dataclass(frozen=True)
class VersionRow:
    flow_id: int
    ver: int
    graph: dict[str, Any]
    published_by: str | None
    published_at: datetime | None
    note: str | None


def _flow(r: Row[Any]) -> FlowRow:
    return FlowRow(*r)


def get_flow(s: Session, flow_id: int, for_update: bool = False) -> FlowRow | None:
    sql = f"SELECT {_COLS} FROM decision_flow WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed column list and suffix; values are bound
    r = s.execute(text(sql), {"i": flow_id}).first()
    return _flow(r) if r else None


def flow_for(s: Session, template_key: str, org_unit_id: str) -> FlowRow | None:
    """The flow of the nearest unit, from `org_unit_id` up to the root, that has one for the template."""
    chain = orgs.ancestors(units(s), org_unit_id)
    if not chain:
        return None
    rows = s.execute(
        text(f"SELECT {_COLS} FROM decision_flow WHERE template_key = :k AND org_unit_id = ANY(:o)"),  # noqa: S608 - fixed column list; values are bound
        {"k": template_key, "o": chain},
    ).all()
    by_org = {r.org_unit_id: r for r in rows}
    return next((_flow(by_org[u]) for u in chain if u in by_org), None)


def flows(s: Session, org_ids: set[str]) -> list[FlowRow]:
    """The flows bound to these units, by template and unit."""
    rows = s.execute(
        text(f"SELECT {_COLS} FROM decision_flow WHERE org_unit_id = ANY(:o) ORDER BY template_key, org_unit_id"),  # noqa: S608 - fixed column list; values are bound
        {"o": sorted(org_ids)},
    ).all()
    return [_flow(r) for r in rows]


def shadow_stats(s: Session, flow_id: int) -> dict[str, Any]:
    """The flow's shadow decisions (MVP-3.5): how many, how many chose the live route and how many another, and dv,
    the sum of (shadow net - live net)."""
    r = s.execute(
        text(
            "SELECT count(*) AS n, count(*) FILTER (WHERE live_route IS NOT DISTINCT FROM shadow_route) AS agree, "
            "coalesce(sum(coalesce(shadow_net, 0) - coalesce(live_net, 0)), 0) AS dv "
            "FROM shadow_decision WHERE flow_id = :i"
        ),
        {"i": flow_id},
    ).one()
    return {"n": r.n, "agree": r.agree, "disagree": r.n - r.agree, "dv": float(r.dv)}


def versions(s: Session, flow_id: int) -> list[VersionRow]:
    """The graphs earlier publishes replaced, newest first."""
    rows = s.execute(
        text(
            "SELECT flow_id, ver, graph, published_by, published_at, note FROM decision_flow_version "
            "WHERE flow_id = :i ORDER BY ver DESC"
        ),
        {"i": flow_id},
    ).all()
    return [VersionRow(*r) for r in rows]
