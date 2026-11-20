"""SAP Gateway security, as a client meets it (docs/backend-steps.md, B3).

- Every call needs Basic auth (communication user) or an OAuth 2.0 bearer token from the client-credentials
  token endpoint. Otherwise: 401 with a Basic challenge.
- Changing calls (POST, PUT, PATCH, MERGE, DELETE) need a CSRF token: first send a GET with
  `x-csrf-token: Fetch`; the response carries the token and a session cookie. Send both with the change.
  A missing or wrong token: 403, `x-csrf-token: Required`, body "CSRF token validation failed".
Credentials are demo values from settings (SIM_S4_USERS, SIM_S4_CLIENTS); nothing real is protected here.
"""

import base64
import secrets
import time
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse

from sim.config import get_settings

SESSION_COOKIE = "SAP_SESSIONID_S4H_100"
REALM = 'Basic realm="SAP NetWeaver Application Server [S4H/100]"'
TOKEN_TTL = 3600


@dataclass
class _Token:
    client: str
    expires: float


_tokens: dict[str, _Token] = {}
_csrf: dict[str, str] = {}  # session id -> token


def _pairs(text: str) -> dict[str, str]:
    return dict(p.split(":", 1) for p in text.split(",") if ":" in p)


def users() -> dict[str, str]:
    return _pairs(get_settings().s4_users)


def clients() -> dict[str, str]:
    return _pairs(get_settings().s4_clients)


def _basic(header: str) -> tuple[str, str] | None:
    if not header.lower().startswith("basic "):
        return None
    try:
        user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
    except ValueError:
        return None
    return user, pw


def authenticate(request: Request) -> str | None:
    """The calling user or client, or None."""
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        t = _tokens.get(h[7:].strip())
        if t and t.expires > time.time():
            return t.client
        return None
    cred = _basic(h)
    if cred and users().get(cred[0]) == cred[1]:
        return cred[0]
    return None


def unauthorized() -> Response:
    return PlainTextResponse("Logon failed", status_code=401, headers={"WWW-Authenticate": REALM})


def issue_token(request_form: dict, header: str) -> dict | None:
    """OAuth 2.0 client credentials. The client authenticates with Basic auth or client_id/client_secret."""
    if request_form.get("grant_type") != "client_credentials":
        return None
    cred = _basic(header) or (request_form.get("client_id", ""), request_form.get("client_secret", ""))
    if clients().get(cred[0]) != cred[1]:
        return None
    token = secrets.token_urlsafe(32)
    _tokens[token] = _Token(cred[0], time.time() + TOKEN_TTL)
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL, "scope": "API_BUSINESS_PARTNER"}


def expire_all_tokens() -> int:
    """Fault injection (B6): every issued bearer token stops working."""
    n = len(_tokens)
    _tokens.clear()
    return n


def fetch_csrf(request: Request, response: Response) -> None:
    sid = request.cookies.get(SESSION_COOKIE) or secrets.token_urlsafe(24)
    token = _csrf.get(sid) or secrets.token_urlsafe(24)
    _csrf[sid] = token
    response.headers["x-csrf-token"] = token
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, path="/")


def csrf_ok(request: Request) -> bool:
    sid = request.cookies.get(SESSION_COOKIE)
    token = request.headers.get("x-csrf-token")
    return bool(sid and token and _csrf.get(sid) == token)


def csrf_required() -> Response:
    return PlainTextResponse("CSRF token validation failed", status_code=403, headers={"x-csrf-token": "Required"})
