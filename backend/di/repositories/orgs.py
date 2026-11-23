"""Org units as read from the table `org_unit` (plan 8, MVP-1.3): the units by id, and the tree the Access page's
Organisation section and the read action org.tree show."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.orgs import OrgUnit


def units(s: Session) -> dict[str, OrgUnit]:
    """Every unit by id, oldest first (the seeded ones in their order)."""
    rows = s.execute(text("SELECT id, parent_id, kind, name FROM org_unit ORDER BY created_at, id"))
    return {r.id: OrgUnit(r.id, r.parent_id, r.kind, r.name) for r in rows}


def tree(s: Session) -> list[dict[str, Any]]:
    """The roots (the workspace), each {id, parent_id, kind, name, children: [...]}, children oldest first."""
    nodes = {uid: {**u.__dict__, "children": []} for uid, u in units(s).items()}
    roots: list[dict[str, Any]] = []
    for n in nodes.values():
        parent = nodes.get(n["parent_id"]) if n["parent_id"] else None
        (parent["children"] if parent else roots).append(n)
    return roots
