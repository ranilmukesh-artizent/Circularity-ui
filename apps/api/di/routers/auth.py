"""Sign-in, the signed-in account, the live stream's ticket (F3), and the Approver delegations (B7)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from di import policy
from di.auth import STREAM_TICKET_SECONDS, issue_stream_ticket, issue_token, load_context
from di.deps import CurrentPrincipal, DbSession

router = APIRouter(prefix="/api", tags=["Access"])


class Login(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: Login, session: DbSession):
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
def me(p: CurrentPrincipal):
    return policy.summary(p.account, p.ctx)


@router.post("/auth/stream-ticket")
def stream_ticket(p: CurrentPrincipal):
    """A short-lived ticket for GET /api/stream?ticket= (EventSource cannot send the bearer token as a header)."""
    return {"ticket": issue_stream_ticket(p.account), "expires_in": STREAM_TICKET_SECONDS}


class DelegationIn(BaseModel):
    enabled: bool


@router.get("/access/delegations")
def delegations(p: CurrentPrincipal):
    p.require_page("access")
    return p.ctx.delegations


@router.put("/access/delegations/{scope}")
def set_delegation(scope: str, body: DelegationIn, p: CurrentPrincipal, session: DbSession):
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
