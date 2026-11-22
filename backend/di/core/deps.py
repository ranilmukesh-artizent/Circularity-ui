"""FastAPI dependency aliases for endpoint signatures (docs/agents/plans/01b-refactor.md, step C3).

    def page(case_id: str, p: CurrentPrincipal, session: DbSession) -> dict: ...

FastAPI resolves each dependency once per request, so `principal` and the endpoint share the same session.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from di.core.auth import Principal, optional_principal, principal
from di.core.db import get_session

CurrentPrincipal = Annotated[Principal, Depends(principal)]
"""The signed-in account (401 without a valid access token)."""

OptionalPrincipal = Annotated[Principal | None, Depends(optional_principal)]
"""The signed-in account, or None for an anonymous caller."""

DbSession = Annotated[Session, Depends(get_session)]
"""The request's database session."""
