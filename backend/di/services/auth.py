"""Sign-in and the Approver delegations (B7), behind di.routes.auth. Tokens and principals: di.core.auth."""

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import issue_token, load_context


def login(session: Session, username: str, password: str) -> dict:
    """The access token for a known account and a non-empty password (any password: the accounts are the demo's)."""
    if not username.strip():
        raise HTTPException(400, {"code": "validation_error", "message": "Enter your work email or user ID."})
    a = policy.resolve_sign_in(username)
    if a is None:
        raise HTTPException(
            401, {"code": "unknown_account", "message": "We could not find that account. Check the email or user ID."}
        )
    if not password:
        raise HTTPException(400, {"code": "validation_error", "message": "Enter your password."})
    token, exp = issue_token(a)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": exp.isoformat(),
        **policy.summary(a, load_context(session)),
    }


def set_delegation(session: Session, scope: str, enabled: bool, by: str) -> dict:
    """What the Approver may decide (the demo's access.setDelegation)."""
    if scope not in policy.DELEGATION_SCOPES:
        raise HTTPException(404, {"code": "not_found", "message": f"No delegation scope {scope}."})
    session.execute(
        text("UPDATE delegation SET enabled = :e, updated_by = :by, updated_at = now() WHERE scope = :s"),
        {"e": enabled, "by": by, "s": scope},
    )
    session.commit()
    return {"scope": scope, "enabled": enabled}
