"""Reads of the device trade-ins the device lab landed (plan 9 P9-6.2; table device_tradein, migration 0047).

Owns: `TradeInRow`, `pending` (the trade-ins that have no case yet) and `by_imei`. Never writes: the lab adapter lands the
rows (di.connectors.adapters.device_lab) and a later task stamps `case_id` when it opens the case. Synthetic data: an IMEI
identifies a device, no person is stored.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TradeInRow:
    trade_in_id: str
    org_unit_id: str | None
    imei: str
    sku: dict[str, Any]
    quote: dict[str, Any]
    partner: str
    batch_id: str | None
    bulk: bool
    received_at: datetime
    payout: dict[str, Any] | None
    case_id: str | None
    source: str


_COLUMNS = "trade_in_id, org_unit_id, imei, sku, quote, partner, batch_id, bulk, received_at, payout, case_id, source"


def pending(s: Session, org: str | None = None) -> list[TradeInRow]:
    """The trade-ins with no case yet, oldest first: those of `org` and the shared ones (no org unit)."""
    rows = s.execute(
        text(
            f"SELECT {_COLUMNS} FROM device_tradein WHERE case_id IS NULL "  # noqa: S608 - fixed column list
            "AND (org_unit_id IS NULL OR org_unit_id = :org) ORDER BY received_at, trade_in_id"
        ),
        {"org": org},
    )
    return [TradeInRow(*r) for r in rows]


def by_imei(s: Session, imei: str) -> TradeInRow | None:
    """The newest trade-in of a device, or None."""
    r = s.execute(
        text(f"SELECT {_COLUMNS} FROM device_tradein WHERE imei = :i ORDER BY received_at DESC, trade_in_id DESC LIMIT 1"),  # noqa: S608
        {"i": imei},
    ).first()
    return TradeInRow(*r) if r else None
