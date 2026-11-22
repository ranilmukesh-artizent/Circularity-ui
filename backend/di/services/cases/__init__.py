"""Cases: the store (case_record), the stage machine, and the case scope used by the action pipeline (B11)."""

from di.core.db import SessionLocal
from di.services.actions import scope


def _db_scope(case_id: str) -> tuple[str, str] | None:
    from di.services.cases import store

    with SessionLocal() as s:
        return store.scope(s, case_id)


def use_database_scope() -> None:
    """The tenant boundary and warehouse lock read a case's owner and location from the database."""
    scope.set_provider(_db_scope)
