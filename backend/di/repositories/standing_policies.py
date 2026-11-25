"""Standing policies as read from `standing_policy` (plan 9, P9-2.5, registry entry I-11). Reads only; the actions
(di.services.actions.standing_policy) write them.

A policy belongs to a pack and an org unit. The one in force for an org is the active policy of the nearest unit, from the org up
to the root `workspace`, that has one for the pack (`effective`), found the way `flows.flow_for` finds a flow.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from di.core import orgs
from di.repositories.orgs import units

_COLS = "id, pack, org_unit_id, name, ver, status, rules, owner, maker, checker, created_at, updated_at, approved_at"


@dataclass(frozen=True)
class PolicyRow:
    id: str
    pack: str
    org_unit_id: str
    name: str
    ver: int  # the version in force while active; 0 until the first approval
    status: str  # draft, review, active, retired
    rules: dict[str, Any]
    owner: str
    maker: str
    checker: str | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None


def _row(r: Row[Any]) -> PolicyRow:
    return PolicyRow(*r)


def get(s: Session, policy_id: str, for_update: bool = False) -> PolicyRow | None:
    sql = f"SELECT {_COLS} FROM standing_policy WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed column list and suffix; values are bound
    r = s.execute(text(sql), {"i": policy_id}).first()
    return _row(r) if r else None


def listed(s: Session, pack: str, org_unit_id: str) -> list[PolicyRow]:
    """The policies of the pack at this org unit, newest first."""
    rows = s.execute(
        text(f"SELECT {_COLS} FROM standing_policy WHERE pack = :p AND org_unit_id = :o ORDER BY created_at DESC, id DESC"),  # noqa: S608 - fixed column list; values are bound
        {"p": pack, "o": org_unit_id},
    ).all()
    return [_row(r) for r in rows]


def effective(s: Session, pack: str, org_unit_id: str) -> PolicyRow | None:
    """The active policy in force for the org: the nearest unit, up to the root, with an active one for the pack."""
    chain = orgs.ancestors(units(s), org_unit_id)
    if not chain:
        return None
    rows = s.execute(
        text(f"SELECT {_COLS} FROM standing_policy WHERE pack = :p AND status = 'active' AND org_unit_id = ANY(:o)"),  # noqa: S608 - fixed column list; values are bound
        {"p": pack, "o": chain},
    ).all()
    by_org = {r.org_unit_id: r for r in rows}
    return next((_row(by_org[u]) for u in chain if u in by_org), None)
