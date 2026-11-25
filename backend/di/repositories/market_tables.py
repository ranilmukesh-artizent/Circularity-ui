"""Market tables as read from `market_table` (plan 9, P9-4.2, registry entry I-15). Reads, and the seeding of the pack's
starting tables; the actions (di.services.actions.market_tables) write every other change.

A table is a rate card or a decision table of a pack, a flow and a market. An org unit may have its own versions; the rest use
the shared ones (`org_unit_id` null). `effective` is the approved version valid on a date: a priced line cites it, so a later
change never rewrites an earlier price.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from di.services.modeler.pack import load_pack
from di.services.modeler.tables import market_spec

_COLS = (
    "id, org_unit_id, pack, flow, market, name, kind, version, status, valid_from, valid_to, currency, body, created_by, "
    "submitted_by, approved_by, reason, created_at"
)


@dataclass(frozen=True)
class TableRow:
    id: int
    org_unit_id: str | None
    pack: str
    flow: str
    market: str
    name: str
    kind: str
    version: int
    status: str  # draft, submitted, approved, rejected, retired
    valid_from: date
    valid_to: date | None
    currency: str | None
    body: dict[str, Any]
    created_by: str
    submitted_by: str | None
    approved_by: str | None
    reason: str | None
    created_at: datetime


def _row(r: Row[Any]) -> TableRow:
    return TableRow(*r)


def get(s: Session, table_id: int, for_update: bool = False) -> TableRow | None:
    sql = f"SELECT {_COLS} FROM market_table WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed column list and suffix; values are bound
    r = s.execute(text(sql), {"i": table_id}).first()
    return _row(r) if r else None


def listed(
    s: Session, pack: str, flow: str | None, market: str | None, org: str | None, *, name: str | None = None,
    visible: Sequence[str] | None = None,
) -> list[TableRow]:  # fmt: skip
    """Every version of the pack's tables the org (or the `visible` org units) and everyone (shared) can use, by name and newest
    version first. `flow`, `market` and `name` narrow it when given."""
    orgs = list(visible) if visible is not None else ([org] if org else [])
    rows = s.execute(
        text(
            f"SELECT {_COLS} FROM market_table WHERE pack = :p AND (org_unit_id IS NULL OR org_unit_id = ANY(:o)) "  # noqa: S608 - fixed column list; values are bound
            "AND (CAST(:f AS text) IS NULL OR flow = :f) AND (CAST(:m AS text) IS NULL OR market = :m) "
            "AND (CAST(:n AS text) IS NULL OR name = :n) "
            "ORDER BY name, market, version DESC, org_unit_id NULLS FIRST"
        ),
        {"p": pack, "o": orgs, "f": flow, "m": market, "n": name},
    ).all()
    return [_row(r) for r in rows]


def effective(s: Session, org: str | None, pack: str, flow: str, market: str, name: str, as_of: date) -> TableRow | None:
    """The approved version valid on `as_of`: the org's own first, else the shared one; None when there is none."""
    rows = s.execute(
        text(
            f"SELECT {_COLS} FROM market_table WHERE pack = :p AND flow = :f AND market = :m AND name = :n "  # noqa: S608 - fixed column list; values are bound
            "AND status = 'approved' AND valid_from <= :d AND (valid_to IS NULL OR valid_to >= :d) "
            "AND (org_unit_id IS NULL OR org_unit_id = :o) "
            "ORDER BY (org_unit_id IS NULL), valid_from DESC, version DESC"
        ),
        {"p": pack, "f": flow, "m": market, "n": name, "d": as_of, "o": org},
    ).all()
    return _row(rows[0]) if rows else None


def ensure_seeded(s: Session, pack_key: str) -> None:
    """Insert the pack file's starting tables as shared approved versions, once (a table version already there is left alone)."""
    spec = market_spec(pack_key)
    if spec is None:
        return
    by = f"pack {pack_key} v{load_pack(pack_key).version}"
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext('market_table.seed'))"))
    for t in spec.tables:
        starts: list[tuple[int, date, date | None, Mapping[str, Any]]]
        if t.kind == "rate_card":
            starts = [(n, v.valid_from, v.valid_to, v.values) for n, v in enumerate(t.versions, 1)]
        else:
            starts = [(1, spec.valid_from, None, {m: t.body or {} for m in spec.markets})]
        for version, valid_from, valid_to, by_market in starts:
            for market, content in by_market.items():
                body = {"values": content} if t.kind == "rate_card" else content
                s.execute(
                    text(
                        "INSERT INTO market_table (org_unit_id, pack, flow, market, name, kind, version, status, valid_from, "
                        "valid_to, currency, body, created_by, approved_by) "
                        "SELECT NULL, :p, :f, :m, :n, :k, :v, 'approved', :vf, :vt, :c, CAST(:b AS jsonb), :by, :by "
                        "WHERE NOT EXISTS (SELECT 1 FROM market_table WHERE org_unit_id IS NULL AND pack = :p AND flow = :f "
                        "AND market = :m AND name = :n AND version = :v)"
                    ),
                    {
                        "p": pack_key, "f": spec.flow, "m": market, "n": t.name, "k": t.kind, "v": version, "vf": valid_from,
                        "vt": valid_to, "c": spec.markets[market], "b": json.dumps(body), "by": by,
                    },
                )  # fmt: skip
