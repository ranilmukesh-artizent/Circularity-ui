"""Customer service tickets waiting for a case (plan 9, P9-4.1; table `service_ticket`, filled by the `sdesk` source).
Read only."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TicketRow:
    number: str
    account: str | None
    market: str | None
    site: str | None
    batch_id: str | None  # None for one tool
    lines: list[dict[str, Any]]  # {serial, model_class, age_months, fault_code, fault_text, cover_type, cover_until}
    requester_role: str | None
    loaner_promised: bool
    opened_at: datetime
    case_id: str | None


def pending(s: Session, org: str | None) -> list[TicketRow]:
    """Tickets of `org` (and the shared ones) that have no case yet, oldest first."""
    rows = s.execute(
        text(
            "SELECT number, account, market, site, batch_id, lines, requester_role, loaner_promised, opened_at, case_id "
            "FROM service_ticket WHERE case_id IS NULL AND (org_unit_id IS NULL OR org_unit_id = :org) "
            "ORDER BY opened_at, number"
        ),
        {"org": org},
    ).all()
    return [
        TicketRow(
            r.number,
            r.account,
            r.market,
            r.site,
            r.batch_id or None,
            r.lines or [],
            r.requester_role,
            r.loaner_promised,
            r.opened_at,
            r.case_id,
        )  # fmt: skip
        for r in rows
    ]
