"""POST /oauth/token (plan 9, P9-13.9): an agent's client credentials for a short-lived access token (RFC 6749 §4.4).

The client sends `grant_type=client_credentials` as a form (urlencoded), with its client id and secret in HTTP Basic
(client_secret_basic) or in the form (client_secret_post). The answer is `{access_token, token_type, expires_in}`; any
refusal is `invalid_client` (401) without saying why (revoked, stopped agent, owner gone, wrong secret look alike).
The secret is never logged. di.services.agent_credentials does the work; later grants (P9-13.10) join this route.
"""

import base64
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from di.core.deps import DbSession
from di.services import agent_credentials

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
    if form.get("grant_type") != "client_credentials":
        return _error(400, "unsupported_grant_type", "Only grant_type=client_credentials is supported here.")
    client_id, secret = _basic(request.headers.get("authorization")) or (form.get("client_id", ""), form.get("client_secret", ""))
    cred = agent_credentials.authenticate(session, client_id, secret) if client_id and secret else None
    if cred is None:
        return _error(401, "invalid_client", "Client authentication failed.")
    out = agent_credentials.mint(session, cred)
    session.commit()
    return JSONResponse(out, headers=_NO_STORE)
