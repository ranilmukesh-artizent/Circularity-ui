"""Customer overlays as read from `customer_overlay` (plan 9, P9-1.3; migration 0031). Reads only; the actions
(di.services.actions.overlays) write them.

An overlay belongs to a pack key and an org unit. The one in force for an org is the published one of the nearest unit,
from the org up to the root `workspace`, that has one (`nearest_published`); overlays are not added up across units.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from di.core import orgs
from di.repositories.orgs import units

_COLS = (
    "id, pack_key, org_unit_id, base_version, draft, draft_base_version, published, status, ver, maker, checker, "
    "conflicts, notes, updated_at"
)


@dataclass(frozen=True)
class OverlayRow:
    id: int
    pack_key: str
    org_unit_id: str
    base_version: str  # the pack version `published` was made against
    draft: list[dict[str, Any]] | None
    draft_base_version: str | None
    published: list[dict[str, Any]]
    status: str  # draft, review, pub
    ver: int
    maker: str | None
    checker: str | None
    conflicts: list[dict[str, Any]]
    notes: list[str]
    updated_at: datetime


def _row(r: Row[Any]) -> OverlayRow:
    return OverlayRow(*r)


def get(s: Session, pack_key: str, org_unit_id: str, for_update: bool = False) -> OverlayRow | None:
    sql = f"SELECT {_COLS} FROM customer_overlay WHERE pack_key = :p AND org_unit_id = :o" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed column list and suffix; values are bound
    r = s.execute(text(sql), {"p": pack_key, "o": org_unit_id}).first()
    return _row(r) if r else None


def nearest_published(s: Session, pack_key: str, org_unit_id: str) -> OverlayRow | None:
    """The overlay in force for the org: the nearest unit, up to the root, with a published one (`ver` > 0)."""
    chain = orgs.ancestors(units(s), org_unit_id)
    if not chain:
        return None
    rows = s.execute(
        text(f"SELECT {_COLS} FROM customer_overlay WHERE pack_key = :p AND ver > 0 AND org_unit_id = ANY(:o)"),  # noqa: S608 - fixed column list; values are bound
        {"p": pack_key, "o": chain},
    ).all()
    by_org = {r.org_unit_id: r for r in rows}
    return next((_row(by_org[u]) for u in chain if u in by_org), None)
