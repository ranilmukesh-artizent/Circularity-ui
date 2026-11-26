"""The close of a telecom unit: what the reuse saved (plan 9, P9-10.17; stories TN-21, TN-22; reads registry entry I-7).

    close_case(s, case_id) -> CloseResult   keeps on the case, as `close.telecom`, the new spend avoided, the days to redeploy
                                            and whether the unit was reused

For a telecom case with an approved route:
    reused            the route is `redeploy` or `spare` (the unit fills a need instead of a new purchase)
    purchase_price    the catalogue price of the unit's model (`market.new_price`, the spares planning catalogue)
    new_spend_avoided the purchase price when the unit was reused, else 0
    days_to_redeploy  whole days from the unit's removal (`asset.removed_at`, the decommission tracker) to the network
                      inventory's confirmation of the transfer (the acknowledged `site_transfer` or `spares_transfer`
                      instruction); a reuse route waits (`waiting_for_install`) until that confirmation arrives
A route that is not a reuse route closes at once with 0 spend avoided and no days.
Never does: confirm an outcome (a person's, `outcome.confirm`), close the case's stage, post to Finance, read a clock or call a
model: it reads the case, the canonical store and the instructions. A case that is not telecom's or was not approved is left
alone (`CloseResult.status`). Calibration learns only from confirmed outcomes; this record is what the reconcile stage reads.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.cases import store as case_store
from di.services.cases import telecom_facts

TEMPLATE = "telecom_network"
REUSE = ("redeploy", "spare")
CONFIRMING = ("site_transfer", "spares_transfer")
CENT = Decimal("0.01")

Status = Literal["closed", "not_applicable", "not_approved", "waiting_for_install"]


@dataclass(frozen=True)
class CloseResult:
    status: Status
    reason: str = ""
    new_spend_avoided: float = 0.0
    days_to_redeploy: int | None = None
    reused: bool = False


def _money(v: Any) -> float:
    return float(Decimal(str(v)).quantize(CENT, ROUND_HALF_UP))


def _removed_on(s: Session, asset_key: str) -> date | None:
    rec = canonical.get(s, "asset", asset_key)
    raw = ((rec or {}).get("data") or {}).get("removed_at")
    try:
        return datetime.fromisoformat(str(raw)).date() if raw else None
    except ValueError:
        return None


def _installed_at(s: Session, case_id: str) -> datetime | None:
    return s.execute(
        text("SELECT min(acknowledged_at) FROM instruction WHERE case_id = :c AND kind = ANY(:k) AND status = 'acknowledged'"),
        {"c": case_id, "k": list(CONFIRMING)},
    ).scalar()


def close_case(s: Session, case_id: str) -> CloseResult:
    """Record the close of a telecom unit on its case (module docstring)."""
    c = case_store.get(s, case_id, for_update=True)
    if c is None or c.get("template") != TEMPLATE:
        return CloseResult("not_applicable", "Not a telecom network case.")
    route = c.get("chosen")
    if not c.get("exec") or not route:
        return CloseResult("not_approved", "No decision has been approved for the unit yet.")
    reused = str(route.get("id")) in REUSE
    price = _money((telecom_facts.gather(s, c).get("market") or {}).get("new_price") or 0)
    days: int | None = None
    if reused:
        installed, removed = _installed_at(s, case_id), _removed_on(s, str(c["assetId"]))
        if installed is None:
            return CloseResult("waiting_for_install", "The network inventory has not confirmed the transfer yet.")
        days = max(0, (installed.date() - removed).days) if removed else None
    spend = price if reused else 0.0
    c["close"] = {
        **(c.get("close") or {}),
        "telecom": {"new_spend_avoided": spend, "purchase_price": price, "days_to_redeploy": days, "reused": reused,
                    "route": route.get("id")},
    }  # fmt: skip
    case_store.save(s, c)
    return CloseResult("closed", "The unit's close is recorded.", spend, days, reused)
