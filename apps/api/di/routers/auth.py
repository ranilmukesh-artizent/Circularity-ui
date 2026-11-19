"""Sign-in, the signed-in account, and the Approver delegations (B7)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.auth import Principal, issue_token, load_context, principal
from di.db import get_session

router = APIRouter(prefix="/api", tags=["Access"])


class Login(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: Login, session: Session = Depends(get_session)):
    if not body.username.strip():
        raise HTTPException(400, {"code": "validation_error", "message": "Enter your work email or user ID."})
    a = policy.resolve_sign_in(body.username)
    if a is None:
        raise HTTPException(
            401, {"code": "unknown_account", "message": "We could not find that account. Check the email or user ID."}
        )
    if not body.password:
        raise HTTPException(400, {"code": "validation_error", "message": "Enter your password."})
    token, exp = issue_token(a)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": exp.isoformat(),
        **policy.summary(a, load_context(session)),
    }


@router.get("/auth/me")
def me(p: Principal = Depends(principal)):
    return policy.summary(p.account, p.ctx)


class DelegationIn(BaseModel):
    enabled: bool


@router.get("/access/delegations")
def delegations(p: Principal = Depends(principal)):
    p.require_page("access")
    return p.ctx.delegations


@router.put("/access/delegations/{scope}")
def set_delegation(scope: str, body: DelegationIn, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    """What the Approver may decide (the demo's access.setDelegation; the full action arrives in B8/B12)."""
    p.require("manageAccess")
    if scope not in policy.DELEGATION_SCOPES:
        raise HTTPException(404, {"code": "not_found", "message": f"No delegation scope {scope}."})
    session.execute(
        text("UPDATE delegation SET enabled = :e, updated_by = :by, updated_at = now() WHERE scope = :s"),
        {"e": body.enabled, "by": p.account.id, "s": scope},
    )
    session.commit()
    return {"scope": scope, "enabled": body.enabled}
