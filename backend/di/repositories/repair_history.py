"""Closed repairs for the repair estimate (plan 9, P9-4.1; table `repair_history`, filled by the `rephist` source).

`similar` answers with one indexed SELECT, read only: the rows of an organisation (and the shared rows) for a tool class
and fault code, closed in a date window. It never writes and never names a person: rows hold serials and part numbers.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

BANDS: dict[str, tuple[int, int | None]] = {"0-12": (0, 12), "13-24": (13, 24), "25-36": (25, 36), "37+": (37, None)}


@dataclass(frozen=True)
class RepairRow:
    repair_number: str
    serial: str | None
    model_class: str
    age_months: int | None
    fault_code: str | None
    market: str | None
    parts: list[dict[str, Any]]  # [{PART_NUMBER, QUANTITY}]
    labour_hours: float | None
    test_fee: bool | None
    turnaround_days: int | None
    actual_cost: float | None
    currency: str | None
    closed_on: date


def similar(
    s: Session, org: str | None, model_class: str, fault_code: str, age_band: str | None, since: date, until: date
) -> list[RepairRow]:
    """Rows of `org` (and the shared rows) for the class and fault, closed in [since, until). `age_band` (0-12, 13-24,
    25-36, 37+) narrows to that age; None widens the key to class + fault."""
    where = "model_class = :c AND fault_code = :f AND closed_on >= :since AND closed_on < :until"
    where += " AND (org_unit_id IS NULL OR org_unit_id = :org)"
    args: dict[str, Any] = {"c": model_class, "f": fault_code, "since": since, "until": until, "org": org}
    if age_band is not None:
        lo, hi = BANDS[age_band]
        where += " AND age_months >= :lo" + (" AND age_months <= :hi" if hi is not None else "")
        args |= {"lo": lo, "hi": hi}
    rows = s.execute(
        text(
            "SELECT id, serial, model_class, age_months, fault_code, market, parts, labour_hours, test_fee, "  # noqa: S608
            f"turnaround_days, actual_cost, currency, closed_on FROM repair_history WHERE {where} ORDER BY closed_on, id"
        ),
        args,
    ).all()
    return [
        RepairRow(
            r.id,
            r.serial,
            r.model_class,
            r.age_months,
            r.fault_code,
            r.market,
            r.parts or [],
            _num(r.labour_hours),
            r.test_fee,
            r.turnaround_days,
            _num(r.actual_cost),
            r.currency,
            r.closed_on,
        )  # fmt: skip
        for r in rows
    ]


def _num(v: Any) -> float | None:
    return None if v is None else float(v)
