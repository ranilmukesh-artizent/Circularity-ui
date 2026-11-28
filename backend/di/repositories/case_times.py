"""When cases opened and when they closed (the Analytics pack headline; plan 11, D1).

Owns: `times(s, ids)`. A case opened when its row was created (`case_record.created_at`) and closed at the last stage-log
move to `closed`. Never writes a row.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CaseTimes:
    opened: datetime
    closed: datetime | None  # None: the case has not closed


def times(s: Session, ids: Sequence[str]) -> dict[str, CaseTimes]:
    """Opened and closed time of each of the cases (an id that does not exist is absent)."""
    if not ids:
        return {}
    rows = s.execute(
        text(
            "SELECT c.id, c.created_at AS opened, "
            "(SELECT max(l.at) FROM case_stage_log l WHERE l.case_id = c.id AND l.to_stage = 'closed') AS closed "
            "FROM case_record c WHERE c.id = ANY(:ids)"
        ),
        {"ids": list(ids)},
    ).mappings()
    return {r["id"]: CaseTimes(r["opened"], r["closed"]) for r in rows}
