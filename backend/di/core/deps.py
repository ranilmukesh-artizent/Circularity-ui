"""FastAPI dependency aliases for endpoint signatures (docs/agents/plans/01b-refactor.md, step C3).

    def page(case_id: str, p: CurrentPrincipal, session: DbSession) -> dict: ...

FastAPI resolves each dependency once per request, so `principal` and the endpoint share the same session.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from di.core.auth import Principal, optional_principal, principal
from di.core.db import get_session
from di.core.errors import ApiError

AGENT_REFUSED = "Agents cannot call this route."


def person_principal(p: Annotated[Principal, Depends(principal)]) -> Principal:
    """The signed-in account when a person called; 403 for an agent's own token (`Principal.agent_id`, P9-13.9).

    Rule 10 (review 13 F1): an agent reads, or prepares an action that holds for a person. A write route outside
    `POST /api/actions/{id}` (and the generic `/api/v1/{name}` CRUD, which prepare as the agent) has no preparer and no
    confirmation step, so every such route takes this instead of `CurrentPrincipal`."""
    if p.agent_id:
        raise ApiError("out_of_scope", AGENT_REFUSED, 403)
    return p


CurrentPrincipal = Annotated[Principal, Depends(principal)]
"""The signed-in account (401 without a valid access token)."""

PersonPrincipal = Annotated[Principal, Depends(person_principal)]
"""The signed-in person: 401 without a valid access token, 403 for an agent's own token. Every non-GET route outside the
action pipeline and /mcp takes it."""

OptionalPrincipal = Annotated[Principal | None, Depends(optional_principal)]
"""The signed-in account, or None for an anonymous caller."""

DbSession = Annotated[Session, Depends(get_session)]
"""The request's database session."""
