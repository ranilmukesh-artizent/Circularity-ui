"""Sign-in, the signed-in account, the live stream's ticket (F3), and the Approver delegations (B7)."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from di.core import policy
from di.core.auth import STREAM_TICKET_SECONDS, issue_stream_ticket
from di.core.deps import CurrentPrincipal, DbSession, PersonPrincipal
from di.schemas.auth import DelegationIn, Login
from di.services import auth, oidc

router = APIRouter(prefix="/api", tags=["Access"])


class OidcExchange(BaseModel):
    code: str


def _oidc_on() -> None:
    if not oidc.enabled():
        raise HTTPException(404, {"code": "not_found", "message": "Single sign-on is not set up."})


@router.post("/auth/login")
def login(body: Login, session: DbSession):
    return auth.login(session, body.username, body.password)


@router.get("/auth/me")
def me(p: CurrentPrincipal):
    return policy.summary(p.account, p.ctx)


@router.post("/auth/stream-ticket")
def stream_ticket(p: PersonPrincipal):
    """A short-lived ticket for GET /api/stream?ticket= (EventSource cannot send the bearer token as a header)."""
    return {"ticket": issue_stream_ticket(p.account), "expires_in": STREAM_TICKET_SECONDS}


@router.get("/access/delegations")
def delegations(p: CurrentPrincipal):
    p.require_page("access")
    return p.ctx.delegations


@router.put("/access/delegations/{scope}")
def set_delegation(scope: str, body: DelegationIn, p: PersonPrincipal, session: DbSession):
    """What the Approver may decide (the demo's access.setDelegation; the full action arrives in B8/B12)."""
    p.require("manageAccess")
    return auth.set_delegation(session, scope, body.enabled, p.account.id)


# --- OIDC sign-in beside the demo sign-in (P9-8.9): all four answer 404 (config: enabled false) while it is not set up
@router.get("/auth/oidc/config")
def oidc_config():
    return {"enabled": True, "label": oidc.LABEL} if oidc.enabled() else {"enabled": False}


@router.get("/auth/oidc/start")
def oidc_start(session: DbSession):
    _oidc_on()
    return RedirectResponse(oidc.start(session), status_code=302)


@router.get("/auth/oidc/callback")
def oidc_callback(session: DbSession, state: str = "", code: str = "", error: str = ""):
    _oidc_on()
    if error:  # the person refused at the provider
        return RedirectResponse("/#/signin?sso_error=Sign-in%20with%20your%20organisation%20was%20cancelled.", status_code=302)
    return RedirectResponse(oidc.callback(session, state, code), status_code=302)


@router.post("/auth/oidc/exchange")
def oidc_exchange(body: OidcExchange, session: DbSession):
    _oidc_on()
    return oidc.exchange(session, body.code)
