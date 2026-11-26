"""OAuth endpoints (plan 9): POST /oauth/token for an agent's client credentials (P9-13.9, RFC 6749 §4.4) and, for an
outside MCP client, GET /oauth/authorize, GET and POST /api/oauth/consent and the authorization_code grant (P9-13.10;
di.services.oauth: PKCE S256 only, exact redirect URI, single-use code, audience-bound token). A consent is a signed-in
person's: an agent's token is refused (an agent never approves).

POST /oauth/token (P9-13.9): an agent's client credentials for a short-lived access token (RFC 6749 §4.4).

The client sends `grant_type=client_credentials` as a form (urlencoded), with its client id and secret in HTTP Basic
(client_secret_basic) or in the form (client_secret_post). The answer is `{access_token, token_type, expires_in}`; any
refusal is `invalid_client` (401) without saying why (revoked, stopped agent, owner gone, wrong secret look alike).
The secret is never logged. di.services.agent_credentials does the work; later grants (P9-13.10) join this route.
"""

import base64
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from di.core.deps import CurrentPrincipal, DbSession
from di.services import agent_credentials, oauth

router = APIRouter(tags=["OAuth"])
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _error(status: int, code: str, description: str) -> JSONResponse:
    headers = _NO_STORE | ({"WWW-Authenticate": 'Basic realm="di"'} if status == 401 else {})
    return JSONResponse({"error": code, "error_description": description}, status_code=status, headers=headers)


def _basic(header: str | None) -> tuple[str, str] | None:
    scheme, _, value = (header or "").partition(" ")
    if scheme.lower() != "basic":
        return None
    try:
        user, _, secret = base64.b64decode(value.strip()).decode().partition(":")
    except ValueError:
        return None
    return user, secret


@router.post("/oauth/token")
async def token(request: Request, session: DbSession):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode(errors="replace")).items()}
    if form.get("grant_type") == "authorization_code":
        try:
            out = oauth.exchange(session, form)
        except oauth.OAuthError as e:
            session.commit()  # a refused exchange of a used code still leaves the row marked
            return _error(e.status, e.code, e.description)
        session.commit()
        return JSONResponse(out, headers=_NO_STORE)
    if form.get("grant_type") != "client_credentials":
        return _error(400, "unsupported_grant_type", "Only authorization_code and client_credentials are supported.")
    client_id, secret = _basic(request.headers.get("authorization")) or (form.get("client_id", ""), form.get("client_secret", ""))
    cred = agent_credentials.authenticate(session, client_id, secret) if client_id and secret else None
    if cred is None:
        return _error(401, "invalid_client", "Client authentication failed.")
    out = agent_credentials.mint(session, cred)
    session.commit()
    return JSONResponse(out, headers=_NO_STORE)


@router.get("/oauth/authorize")
def authorize(request: Request, session: DbSession):
    """An outside client's authorization request: checked, then the browser goes to the consent page."""
    try:
        req = oauth.authorize(session, dict(request.query_params))
    except oauth.OAuthError as e:
        return _error(e.status, e.code, e.description)
    return RedirectResponse(f"/#/oauth/consent?req={req}", status_code=302, headers=_NO_STORE)


class ConsentIn(BaseModel):
    req: str
    approve: bool


def _person(p: CurrentPrincipal) -> None:
    if p.agent_id:
        raise HTTPException(403, {"code": "out_of_scope", "message": "An agent cannot give consent: a person does."})


@router.get("/api/oauth/consent")
def consent_request(req: str, p: CurrentPrincipal, session: DbSession) -> dict:
    """What the consent page shows: the client, the agent it acts as and the scopes asked for."""
    _person(p)
    try:
        return oauth.describe(session, req)
    except oauth.OAuthError as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.description}) from e


@router.post("/api/oauth/consent")
def consent(body: ConsentIn, p: CurrentPrincipal, session: DbSession) -> dict:
    """The signed-in person's answer: the URL to send the browser back to, with `code` and `state` (or `error`)."""
    _person(p)
    try:
        url = oauth.consent(session, p.account, body.req, body.approve)
    except oauth.OAuthError as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.description}) from e
    session.commit()
    return {"redirect": url}
