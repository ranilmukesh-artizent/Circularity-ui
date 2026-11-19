"""ServiceNow authentication, as a REST client meets it on an instance.

- Basic auth with an integration user, or
- OAuth 2.0: POST /servicenow/oauth_token.do (form) with grant_type=client_credentials (client_id, client_secret),
  grant_type=password (plus username, password) or grant_type=refresh_token; then `Authorization: Bearer <token>`.
Failures: 401 {"error":{"message":"User Not Authenticated","detail":"Required to provide Auth information"},
"status":"failure"}; a bad token request: 401 {"error":"server_error","error_description":"access_denied"}.
"""

import base64
import secrets
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

# Demo credentials (nothing real is protected here)
USERS = {"di.integration": "Circularity-demo-sn-1", "admin": "Circularity-demo-sn-admin"}
CLIENTS = {"circularity-di": "circularity-demo-sn-secret"}  # OAuth application registry: client_id -> secret
CLIENT_CREDENTIALS_USER = "di.integration"  # the OAuth application's run-as user
TOKEN_TTL = 1799
REFRESH_TTL = 8640000


@dataclass
class _Token:
    user: str
    client: str
    expires: float


_access: dict[str, _Token] = {}
_refresh: dict[str, _Token] = {}


def unauthorized(detail: str = "Required to provide Auth information") -> JSONResponse:
    return JSONResponse(
        {"error": {"message": "User Not Authenticated", "detail": detail}, "status": "failure"},
        status_code=401,
        headers={"WWW-Authenticate": 'BASIC realm="Service-now"'},
    )


def authenticate(request: Request) -> str | None:
    """The calling user name, or None."""
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        t = _access.get(h[7:].strip())
        return t.user if t and t.expires > time.time() else None
    if h.lower().startswith("basic "):
        try:
            user, _, pw = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            return None
        return user if USERS.get(user) == pw else None
    return None


def _issue(user: str, client: str) -> dict:
    access, refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    _access[access] = _Token(user, client, time.time() + TOKEN_TTL)
    _refresh[refresh] = _Token(user, client, time.time() + REFRESH_TTL)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "scope": "useraccount",
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL,
    }


def token(form: dict, header: str) -> dict | None:
    """The token response, or None when the request is refused."""
    client, secret = form.get("client_id", ""), form.get("client_secret", "")
    if header.lower().startswith("basic ") and not client:
        try:
            client, _, secret = base64.b64decode(header[6:]).decode().partition(":")
        except ValueError:
            return None
    if not client or CLIENTS.get(client) != secret:
        return None
    grant = form.get("grant_type")
    if grant == "client_credentials":
        return _issue(CLIENT_CREDENTIALS_USER, client)
    if grant == "password":
        user = form.get("username", "")
        return _issue(user, client) if user and USERS.get(user) == form.get("password") else None
    if grant == "refresh_token":
        t = _refresh.get(form.get("refresh_token", ""))
        return _issue(t.user, client) if t and t.client == client and t.expires > time.time() else None
    return None


def token_refused() -> JSONResponse:
    return JSONResponse({"error_description": "access_denied", "error": "server_error"}, status_code=401)


def expire_all_tokens() -> int:
    """Fault injection (B6): every issued access token stops working."""
    n = len(_access)
    _access.clear()
    return n
