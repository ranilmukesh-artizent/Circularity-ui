"""Refurbished units released to service and not yet held (plan 9, P9-4.1; table `refurb_unit`, filled by the `rephist`
source). A covered swap draws on this stock: `reserve` holds one unit for a case."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def available(s: Session, org: str | None, model_class: str) -> int:
    """Released units of the class that no case holds, of `org` and the shared ones."""
    return s.execute(
        text(
            "SELECT count(*) FROM refurb_unit WHERE model_class = :c AND reserved_case IS NULL "
            "AND (org_unit_id IS NULL OR org_unit_id = :org)"
        ),
        {"c": model_class, "org": org},
    ).scalar_one()


def reserve(s: Session, serial: str, case_id: str) -> bool:
    """Hold the unit for the case. False when the unit does not exist or a case already holds it. No commit."""
    got = s.execute(
        text("UPDATE refurb_unit SET reserved_case = :k WHERE serial = :s AND reserved_case IS NULL RETURNING serial"),
        {"k": case_id, "s": serial},
    ).first()
    return got is not None
