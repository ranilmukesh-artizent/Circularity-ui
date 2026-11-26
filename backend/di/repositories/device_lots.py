"""Wholesale lots as read from `device_lot` and `device_lot_member` (plan 9, P9-6.11, story DV-07; migration 0048). Reads only;
the actions (di.services.actions.device_lots) write them.

Owns: the lot row, the lots an org (or a set of orgs) may see, a lot's members, the cases already in a lot, and the reads the
choice of a bid needs: the approved buyers (the market table `approved_buyers` of the device pack, I-15, version in force for the
lot's org on a date), the bids on a lot as of a date (`device_market.open_bids`) and their ranking. Never writes and never picks a
bid with a language model: `di.services.modeler.valuers.device_lots` ranks by net.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import device_market
from di.repositories import market_tables as tables_repo
from di.services.modeler import tables
from di.services.modeler.valuers.device_lots import Bid, Ranking, rank_bids

PACK, TABLE, MARKET = "device", "approved_buyers", "US"
_COLS = (
    "id, org_unit_id, lot_ref, model, grade, units, status, best_bid_id, value_usd, created_by, proposed_by, approved_by, "
    "reason, created_at"
)


@dataclass(frozen=True)
class LotRow:
    id: str
    org_unit_id: str | None
    lot_ref: str
    model: str
    grade: str
    units: int
    status: str  # draft, bidding, proposed, approved, rejected, sold
    best_bid_id: str | None
    value_usd: float | None
    created_by: str
    proposed_by: str | None
    approved_by: str | None
    reason: str | None
    created_at: datetime


def _row(r: Any) -> LotRow:
    return LotRow(
        r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], None if r[8] is None else float(r[8]), r[9], r[10], r[11], r[12], r[13]
    )


def get(s: Session, lot_id: str, for_update: bool = False) -> LotRow | None:
    sql = f"SELECT {_COLS} FROM device_lot WHERE id = :i" + (" FOR UPDATE" if for_update else "")  # noqa: S608 - fixed column list and suffix; values are bound
    r = s.execute(text(sql), {"i": lot_id}).first()
    return _row(r) if r else None


def listed(s: Session, orgs: Sequence[str]) -> list[LotRow]:
    """The lots of these org units, newest first."""
    rows = s.execute(
        text(f"SELECT {_COLS} FROM device_lot WHERE org_unit_id = ANY(:o) ORDER BY created_at DESC, id DESC"),  # noqa: S608 - fixed column list; values are bound
        {"o": list(orgs)},
    )
    return [_row(r) for r in rows]


def drafts(s: Session, org: str) -> list[LotRow]:
    """The org's lots that were built but not posted to the market yet, oldest first."""
    rows = s.execute(
        text(f"SELECT {_COLS} FROM device_lot WHERE org_unit_id = :o AND status = 'draft' ORDER BY created_at, id"),  # noqa: S608 - fixed column list; values are bound
        {"o": org},
    )
    return [_row(r) for r in rows]


def members(s: Session, lot_id: str) -> list[str]:
    """The case ids in the lot, by id."""
    return list(
        s.execute(text("SELECT case_id FROM device_lot_member WHERE lot_id = :l ORDER BY case_id"), {"l": lot_id}).scalars()
    )


def cases_in_lots(s: Session) -> set[str]:
    """The cases that are in a lot that was not rejected: they are not offered to a new lot."""
    rows = s.execute(
        text("SELECT m.case_id FROM device_lot_member m JOIN device_lot l ON l.id = m.lot_id WHERE l.status <> 'rejected'")
    )
    return set(rows.scalars())


def approved_buyers(s: Session, org: str | None, as_of: date) -> set[str]:
    """The buyers the org may sell a wholesale lot to on `as_of`: those with a rate above 0 in the approved version of the
    `approved_buyers` table (the org's own, else the shared one). No table in force: nobody is approved."""
    spec = tables.market_spec(PACK)
    if spec is None:
        return set()
    tables_repo.ensure_seeded(s, PACK)
    row = tables_repo.effective(s, org, PACK, spec.flow, MARKET, TABLE, as_of)
    return set() if row is None else {k for k, v in tables.rate_card(row).values.items() if v > 0}


def bids(s: Session, lot_ref: str, as_of: date) -> list[Bid]:
    """The bids on the lot received on or before `as_of`, oldest first."""
    return [Bid(b.bid_id, b.buyer_code, b.amount, b.fees, b.logistics) for b in device_market.open_bids(s, lot_ref, as_of)]


def ranking(s: Session, lot: LotRow, as_of: date) -> Ranking:
    """The lot's bids ranked by net a unit among the approved buyers of its org, and the bids dropped with their reasons."""
    return rank_bids(bids(s, lot.lot_ref, as_of), approved_buyers(s, lot.org_unit_id, as_of))


def best_net_per_unit(s: Session, model: str, grade: str, as_of: date) -> float | None:
    """The best approved net a unit among the lots of this model and grade that are collecting bids (the valuer's
    `inputs.bid_per_unit` of a received device of that model and grade), or None when no such lot has an approved bid."""
    rows = s.execute(
        text("SELECT org_unit_id, lot_ref FROM device_lot WHERE status = 'bidding' AND model = :m AND grade = :g ORDER BY id"),
        {"m": model, "g": grade},
    ).all()
    nets = []
    for org, ref in rows:
        best = rank_bids(bids(s, ref, as_of), approved_buyers(s, org, as_of)).best
        if best is not None:
            nets.append(best.net)
    return max(nets) if nets else None
