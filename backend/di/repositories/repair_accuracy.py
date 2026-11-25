"""Held-out accuracy rows of the repair estimate (plan 9, P9-4.5; table `repair_accuracy`, migration 0045).

One row per organisation unit (None: shared rows only), tool class and day. `window` reads the closed repairs a replay needs,
`replace_day` writes a day's rows again, `latest` and `latest_all` read the newest row of a family. Reads and the one
day-replacing write only; no row names a person.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories.repair_history import RepairRow

COLUMNS = "org_unit_id, as_of, model_class, n, mae, mae_share, coverage, auto_share, instant"


@dataclass(frozen=True)
class AccuracyRow:
    org_unit_id: str | None
    as_of: date
    model_class: str
    n: int
    mae: Decimal
    mae_share: Decimal
    coverage: Decimal
    auto_share: Decimal
    instant: bool


def _row(r: Any) -> AccuracyRow:
    return AccuracyRow(r.org_unit_id, r.as_of, r.model_class, r.n, r.mae, r.mae_share, r.coverage, r.auto_share, r.instant)


def window(s: Session, since: date, until: date) -> list[tuple[str | None, RepairRow]]:
    """Every closed repair with a class, closed in [since, until), with its org unit, oldest first."""
    rows = s.execute(
        text(
            "SELECT id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, labour_hours, test_fee, "
            "turnaround_days, actual_cost, currency, closed_on FROM repair_history "
            "WHERE model_class IS NOT NULL AND closed_on >= :since AND closed_on < :until ORDER BY closed_on, id"
        ),
        {"since": since, "until": until},
    ).all()
    num = lambda v: None if v is None else float(v)  # noqa: E731
    return [
        (
            r.org_unit_id,
            RepairRow(
                r.id, r.serial, r.model_class, r.age_months, r.fault_code, r.market, r.parts or [], num(r.labour_hours),
                r.test_fee, r.turnaround_days, num(r.actual_cost), r.currency, r.closed_on,
            ),
        )
        for r in rows
    ]  # fmt: skip


def replace_day(s: Session, as_of: date, rows: list[AccuracyRow]) -> None:
    """Keep exactly `rows` for the day `as_of` (a second computation on the same day replaces the first)."""
    s.execute(text("DELETE FROM repair_accuracy WHERE as_of = :d"), {"d": as_of})
    for r in rows:
        s.execute(
            text(
                f"INSERT INTO repair_accuracy ({COLUMNS}) VALUES (:o, :d, :c, :n, :mae, :ms, :cov, :au, :i)"  # noqa: S608 - constant
            ),
            {"o": r.org_unit_id, "d": as_of, "c": r.model_class, "n": r.n, "mae": r.mae, "ms": r.mae_share, "cov": r.coverage,
             "au": r.auto_share, "i": r.instant},
        )  # fmt: skip


def computed_on(s: Session, as_of: date) -> bool:
    return s.execute(text("SELECT 1 FROM repair_accuracy WHERE as_of = :d LIMIT 1"), {"d": as_of}).first() is not None


def latest(s: Session, org: str | None, model_class: str) -> AccuracyRow | None:
    """The newest row of the class for the org unit, else the newest of the shared rows (org unit None)."""
    r = s.execute(
        text(
            f"SELECT {COLUMNS} FROM repair_accuracy WHERE model_class = :c AND (org_unit_id IS NOT DISTINCT FROM :o OR "  # noqa: S608
            "org_unit_id IS NULL) ORDER BY (org_unit_id IS NULL), as_of DESC, id DESC LIMIT 1"
        ),
        {"c": model_class, "o": org},
    ).first()
    return None if r is None else _row(r)


def latest_all(s: Session) -> list[AccuracyRow]:
    """The newest row of every (org unit, class), ordered by org unit then class."""
    rows = s.execute(
        text(
            f"SELECT DISTINCT ON (org_unit_id, model_class) {COLUMNS} FROM repair_accuracy "  # noqa: S608 - constant
            "ORDER BY org_unit_id NULLS FIRST, model_class, as_of DESC, id DESC"
        )
    ).all()
    return [_row(r) for r in rows]
