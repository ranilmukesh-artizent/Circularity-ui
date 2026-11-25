"""The refresh window of a fleet contract (plan 9, P9-5.1, stories CR-01 and CR-08; part of the case process layer, I-20).

Pure: no session, no I/O, no model. Dates and counts are computed.

    window_opens(end, notice, days=90)   the day the window opens: `days` before the notice date when the contract has
                                         one, else before its end date
    basis(contract)                      "notice" or "end": what the window counts back from
    due(contracts, today, days)          the ids of the contracts whose window has opened and whose term has not ended
    add_working_days(d, n)               `d` plus `n` Monday-to-Friday days (the proposal's due date)

A contract is `{contract_id, status, end_date, notice_date?}` as the canonical store holds it (dates as ISO text or
`date`). Only `active` and `evergreen` contracts are renewed. Owns: nothing stored. Never does: open a case
(di.services.cases.refresh_intake does).
"""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any, Literal

RENEWABLE = ("active", "evergreen")
DEFAULT_DAYS = 90


def as_date(v: Any) -> date | None:
    """A date from `date` or ISO text (a time part is dropped); None for anything else."""
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def window_opens(end: date, notice: date | None, days: int = DEFAULT_DAYS) -> date:
    """`notice - days` when a notice date exists, else `end - days`."""
    return (notice or end) - timedelta(days=days)


def basis(contract: Mapping[str, Any]) -> Literal["end", "notice"]:
    """What the contract's window counts back from: its notice date when it has one, else its end date."""
    return "notice" if as_date(contract.get("notice_date")) else "end"


def due(contracts: Sequence[Mapping[str, Any]], today: date, days: int = DEFAULT_DAYS) -> list[str]:
    """The ids of the contracts (in the order given) with status `active` or `evergreen` whose window has opened by
    `today` and whose term has not ended (its end date is today or later)."""
    out = []
    for c in contracts:
        end = as_date(c.get("end_date"))
        if c.get("status") not in RENEWABLE or end is None or not c.get("contract_id"):
            continue
        if window_opens(end, as_date(c.get("notice_date")), days) <= today <= end:
            out.append(str(c["contract_id"]))
    return out


def add_working_days(d: date, n: int) -> date:
    """`d` plus `n` working days (Monday to Friday; holidays are not known here)."""
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d
