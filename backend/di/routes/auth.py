"""Sign-in, the signed-in account, the live stream's ticket (F3), and the Approver delegations (B7)."""

from fastapi import APIRouter

from di.core import policy
from di.core.auth import STREAM_TICKET_SECONDS, issue_stream_ticket
from di.core.deps import CurrentPrincipal, DbSession
from di.schemas.auth import DelegationIn, Login
from di.services import auth

router = APIRouter(prefix="/api", tags=["Access"])


@router.post("/auth/login")
def login(body: Login, session: DbSession):
    return auth.login(session, body.username, body.password)


@router.get("/auth/me")
def me(p: CurrentPrincipal):
    return policy.summary(p.account, p.ctx)


@router.post("/auth/stream-ticket")
def stream_ticket(p: CurrentPrincipal):
    """A short-lived ticket for GET /api/stream?ticket= (EventSource cannot send the bearer token as a header)."""
    return {"ticket": issue_stream_ticket(p.account), "expires_in": STREAM_TICKET_SECONDS}


@router.get("/access/delegations")
def delegations(p: CurrentPrincipal):
    p.require_page("access")
    return p.ctx.delegations


@router.put("/access/delegations/{scope}")
def set_delegation(scope: str, body: DelegationIn, p: CurrentPrincipal, session: DbSession):
    """What the Approver may decide (the demo's access.setDelegation; the full action arrives in B8/B12)."""
    p.require("manageAccess")
    return auth.set_delegation(session, scope, body.enabled, p.account.id)
