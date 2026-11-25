"""HTTP surface of the directory mock, under /directory (see __init__.py for the standards followed).

    GET  /directory/.well-known/openid-configuration   provider metadata
    GET  /directory/authorize    code + PKCE S256 required; `login_hint` = a user id or email redirects at once,
                                 otherwise an HTML page with one button per user
    POST /directory/token        authorization_code grant, client_secret_basic; RS256 ID token
    GET  /directory/jwks, GET /directory/userinfo (Bearer access token)
    GET  /directory/api/users?offset&limit, GET /directory/api/groups    -> {"data": [...], "next": int | null}
    POST /directory/_admin/users {email, name?, groups?}, DELETE /directory/_admin/users/{id}, POST /_admin/reset

Owns: the routes. Never does: log a code, token or secret; store anything but `STATE`. Errors on the token call are
RFC 6749 bodies `{"error", "error_description"}`.
"""

import base64
import binascii
import hmac
import html
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from sim.vendors.directory.keys import jwks, pkce_s256, sign_jwt
from sim.vendors.directory.models import CODE_TTL, STATE, TOKEN_TTL, AuthCode, User
from sim.vendors.directory.seed import load

router = APIRouter(prefix="/directory")
CLIENT_ID = "circularity"
CLIENT_SECRET = "circularity-demo-secret"  # noqa: S105  (demo credential, not a secret)


def issuer() -> str:
    return os.environ.get("DIRECTORY_ISSUER", "http://localhost:8100/directory").rstrip("/")


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status)


def _claims(u: User) -> dict[str, Any]:
    return {"sub": u.id, "email": u.email, "email_verified": True, "name": u.name, "groups": list(u.groups)}


@router.get("/.well-known/openid-configuration")
def discovery() -> dict[str, Any]:
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "jwks_uri": f"{base}/jwks",
        "userinfo_endpoint": f"{base}/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "email", "profile"],
        "claims_supported": ["iss", "sub", "aud", "exp", "iat", "nonce", "email", "name", "groups"],
    }


@router.get("/jwks")
def jwks_document() -> dict[str, Any]:
    return jwks()


def _back(redirect_uri: str, state: str | None, **params: str) -> RedirectResponse:
    q = {**params, **({"state": state} if state else {})}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(q)}", status_code=302)


def _find(hint: str) -> User | None:
    return next((u for u in STATE.users.values() if hint in (u.id, u.email)), None)


@router.get("/authorize", response_model=None)
def authorize(request: Request) -> Response:
    q = request.query_params
    redirect_uri, state = q.get("redirect_uri", ""), q.get("state")
    if q.get("client_id") != CLIENT_ID or not redirect_uri:
        return HTMLResponse("Unknown client or missing redirect_uri.", status_code=400)
    if q.get("response_type") != "code":
        return _back(redirect_uri, state, error="unsupported_response_type")
    if not q.get("code_challenge") or q.get("code_challenge_method") != "S256":
        return _back(redirect_uri, state, error="invalid_request", error_description="PKCE S256 is required")
    hint = q.get("login_hint")
    if hint is None:
        return HTMLResponse(_page(dict(q)))
    user = _find(hint)
    if user is None:
        return HTMLResponse("Unknown login_hint.", status_code=400)
    code = secrets.token_urlsafe(24)
    STATE.codes[code] = AuthCode(user.id, CLIENT_ID, redirect_uri, q["code_challenge"], q.get("nonce"), time.time() + CODE_TTL)
    return _back(redirect_uri, state, code=code)


def _page(params: dict[str, str]) -> str:
    rows = "".join(
        f'<li><a href="/directory/authorize?{html.escape(urlencode({**params, "login_hint": u.id}))}">'
        f"<button>{html.escape(u.email)}</button></a> {html.escape(u.name)}</li>"
        for u in STATE.users.values()
    )
    return f"<!doctype html><title>Sign in</title><h1>Sign in (synthetic directory)</h1><ul>{rows}</ul>"


def _client_ok(request: Request) -> bool | None:
    """None: no Basic header; False: wrong client or secret; True: ok."""
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("basic "):
        return None
    try:
        who, _, secret = base64.b64decode(h[6:], validate=True).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return False
    return who == CLIENT_ID and hmac.compare_digest(secret, CLIENT_SECRET)


@router.post("/token", response_model=None)
async def token(request: Request) -> Response:
    ok = _client_ok(request)
    if ok is None:
        return JSONResponse(
            {"error": "invalid_client", "error_description": "client_secret_basic required"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="directory"'},
        )
    if not ok:
        return _oauth_error("invalid_client", "wrong client or secret", 401)
    form = await request.form()
    if form.get("grant_type") != "authorization_code":
        return _oauth_error("unsupported_grant_type", "only authorization_code")
    # a code is spent by the first attempt, right or wrong (RFC 6749 4.1.2: a code is used once)
    entry = STATE.codes.pop(str(form.get("code", "")), None)
    verifier = str(form.get("code_verifier", ""))
    if (
        entry is None
        or entry.expires < time.time()
        or entry.client_id != CLIENT_ID
        or str(form.get("redirect_uri", "")) != entry.redirect_uri
        or not hmac.compare_digest(pkce_s256(verifier), entry.challenge)
    ):
        return _oauth_error("invalid_grant", "code unknown, used, expired or the verifier does not match")
    user = STATE.users.get(entry.user_id)
    if user is None:
        return _oauth_error("invalid_grant", "user no longer active")
    now = int(time.time())
    claims = {"iss": issuer(), "aud": CLIENT_ID, "iat": now, "exp": now + TOKEN_TTL, **_claims(user)}
    if entry.nonce:
        claims["nonce"] = entry.nonce
    access = secrets.token_urlsafe(24)
    STATE.tokens[access] = (user.id, time.time() + TOKEN_TTL)
    return JSONResponse(
        {"access_token": access, "token_type": "Bearer", "expires_in": TOKEN_TTL, "id_token": sign_jwt(claims)},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/userinfo", response_model=None)
def userinfo(request: Request) -> Response:
    h = request.headers.get("authorization", "")
    entry = STATE.tokens.get(h[7:]) if h.lower().startswith("bearer ") else None
    user = STATE.users.get(entry[0]) if entry and entry[1] > time.time() else None
    if user is None:
        return JSONResponse({"error": "invalid_token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return JSONResponse(_claims(user))


def _page_of(items: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    end = offset + limit
    return {"data": items[offset:end], "next": end if end < len(items) else None}


@router.get("/api/users")
def users(offset: int = 0, limit: int = 25) -> dict[str, Any]:
    items = [{"id": u.id, "email": u.email, "name": u.name, "groups": list(u.groups)} for u in STATE.users.values()]
    return _page_of(items, max(offset, 0), min(max(limit, 1), 100))


@router.get("/api/groups")
def groups(offset: int = 0, limit: int = 25) -> dict[str, Any]:
    members: dict[str, list[str]] = {}
    for u in STATE.users.values():
        for g in u.groups:
            members.setdefault(g, []).append(u.id)
    items = [{"id": g, "name": g, "members": m} for g, m in sorted(members.items())]
    return _page_of(items, max(offset, 0), min(max(limit, 1), 100))


class NewUser(BaseModel):
    email: str = Field(min_length=3)
    name: str | None = None
    groups: list[str] = []


@router.post("/_admin/users", status_code=201)
def add_user(body: NewUser) -> dict[str, Any]:
    """Add a joiner. A pending joiner (the seed's joiner.one) keeps its id and name; anyone else is new."""
    same = next((u for u in STATE.users.values() if u.email == body.email), None)
    if same is not None:  # idempotent for a smoke that retries
        return {"id": same.id, "email": same.email, "name": same.name, "groups": same.groups}
    base = STATE.pending.pop(body.email, None)
    uid = base.id if base else "u-" + body.email.split("@")[0].replace(".", "-")
    user = User(uid, body.email, body.name or (base.name if base else body.email), list(body.groups))
    STATE.users[uid] = user
    return {"id": uid, "email": user.email, "name": user.name, "groups": user.groups}


@router.delete("/_admin/users/{user_id}", status_code=204, response_model=None)
def remove_user(user_id: str) -> Response:
    if STATE.users.pop(user_id, None) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return Response(status_code=204)


@router.post("/_admin/reset")
def reset_directory() -> dict[str, int]:
    return {"users": load()}
