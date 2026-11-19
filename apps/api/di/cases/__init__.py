"""Cases: the store (case_record), the stage machine, and the case scope used by the action pipeline (B11)."""

from di.actions import scope
from di.db import SessionLocal


def _db_scope(case_id: str) -> tuple[str, str] | None:
    from di.cases import store

    with SessionLocal() as s:
        return store.scope(s, case_id)


def use_database_scope() -> None:
    """The tenant boundary and warehouse lock read a case's owner and location from the database."""
    scope.set_provider(_db_scope)
