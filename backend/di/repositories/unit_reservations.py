"""Reservations of refurbished units for contract refresh swaps (plan 9, P9-5.3, story CR-03; table `unit_reservation`).

    held(s, org_unit_id) -> frozenset[str]                       the unit ids held now in the org
    hold(s, unit_id, case_id, need_id, by, org_unit_id=None)     hold a unit once; ActionError conflict when it is held
    release(s, case_id) / consume(s, case_id)                   free the case's held units / mark them given to the customer
    stock(s) -> [{id, cls, rul, grade}]                          graded refurbished stock at the repair centre, available

A unit is held once: a partial unique index on `unit_id` where the status is held, so two contracts that want one unit cannot
both hold it even when they race. `hold` is called when a person approves a refresh (P9-5.5); matching only proposes.
`stock` reads the canonical `stock_unit` records whose status is `available` and that carry a grade and a remaining life
(GR-C3: a like-life unit is certified).

Never does: approve anything, or decide who gets a unit (di.services.engine.like_life).
"""

from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from di.services.actions.registry import ActionError


def held(s: Session, org_unit_id: str) -> frozenset[str]:
    rows = s.execute(
        text("SELECT unit_id FROM unit_reservation WHERE org_unit_id = :o AND status = 'held'"), {"o": org_unit_id}
    ).scalars()
    return frozenset(rows)


def hold(s: Session, unit_id: str, case_id: str, need_id: str, by: str, org_unit_id: str | None = None) -> None:
    org = org_unit_id or s.execute(text("SELECT owner FROM case_record WHERE id = :c"), {"c": case_id}).scalar()
    if not org:
        raise ActionError("not_found", f"{case_id} is not a case.")
    try:
        with s.begin_nested():
            s.execute(
                text(
                    "INSERT INTO unit_reservation (unit_id, org_unit_id, case_id, need_id, status, created_by) "
                    "VALUES (:u, :o, :c, :n, 'held', :b)"
                ),
                {"u": unit_id, "o": org, "c": case_id, "n": need_id, "b": by},
            )
    except IntegrityError:
        other = s.execute(
            text("SELECT case_id FROM unit_reservation WHERE unit_id = :u AND status = 'held'"), {"u": unit_id}
        ).scalar()
        raise ActionError("conflict", f"{unit_id} is already reserved for {other}") from None


def stock(s: Session) -> list[dict[str, Any]]:
    """The available, graded refurbished units (module docstring), by unit id."""
    rows = s.execute(text("SELECT key, data FROM canonical WHERE model = 'stock_unit' ORDER BY key")).all()
    return [
        {"id": str(r.key), "cls": str(r.data.get("tool_class")), "rul": round(float(r.data["rul_pct"])), "grade": r.data["grade"]}
        for r in rows
        if r.data.get("status") == "available" and r.data.get("grade") and r.data.get("rul_pct") is not None
        and r.data.get("tool_class")
    ]  # fmt: skip


def release(s: Session, case_id: str) -> int:
    """Free every unit the case holds (status `released`): the case was declined, re-evaluated, sent back, lapsed or its
    reservation step failed. The number of rows freed. In the caller's transaction."""
    r = s.execute(text("UPDATE unit_reservation SET status = 'released' WHERE case_id = :c AND status = 'held'"), {"c": case_id})
    return int(cast(CursorResult[Any], r).rowcount or 0)


def consume(s: Session, case_id: str) -> int:
    """The case's held units went to the customer (the contract renewed): status `consumed`, never offered again."""
    r = s.execute(text("UPDATE unit_reservation SET status = 'consumed' WHERE case_id = :c AND status = 'held'"), {"c": case_id})
    return int(cast(CursorResult[Any], r).rowcount or 0)
