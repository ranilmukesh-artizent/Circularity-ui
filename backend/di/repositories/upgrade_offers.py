"""Past upgrade offers and whether the customer took them (plan 9, P9-4.1; table `upgrade_offer`, filled by the `sdesk`
source): the data the take-up curve is learned from. Read only; rows carry account codes, no names."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class OfferRow:
    id: str
    account: str | None
    market: str | None
    model_class: str | None
    offered_on: date
    credit_pct: float | None  # a share, 0.15 = 15%
    credit_amount: float | None
    currency: str | None
    accepted: bool


def offers(s: Session, org: str | None, account: str | None, market: str, since: date, until: date) -> list[OfferRow]:
    """Offers of `org` (and the shared ones) in a market, offered in [since, until); `account` narrows to one account."""
    where = "market = :m AND offered_on >= :since AND offered_on < :until AND (org_unit_id IS NULL OR org_unit_id = :org)"
    args: dict[str, Any] = {"m": market, "since": since, "until": until, "org": org}
    if account is not None:
        where += " AND account = :a"
        args["a"] = account
    rows = s.execute(
        text(
            "SELECT id, account, market, model_class, offered_on, credit_pct, credit_amount, currency, accepted "  # noqa: S608
            f"FROM upgrade_offer WHERE {where} ORDER BY offered_on, id"
        ),
        args,
    ).all()
    return [
        OfferRow(
            r.id,
            r.account,
            r.market,
            r.model_class,
            r.offered_on,
            None if r.credit_pct is None else float(r.credit_pct),
            None if r.credit_amount is None else float(r.credit_amount),
            r.currency,
            bool(r.accepted),
        )  # fmt: skip
        for r in rows
    ]
