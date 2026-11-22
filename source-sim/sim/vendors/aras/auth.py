"""Aras Innovator authentication for the mock (demo credentials, not secrets).

The Innovator OAuth server (IdentityServer) issues tokens with the resource-owner password grant:
POST /aras/InnovatorServer/oauthserver/connect/token, form fields grant_type=password, scope=Innovator,
client_id=IOMApp, username, password (the MD5 hash of the password, hex, as Innovator stores it), database.
-> {"access_token", "expires_in": 3600, "token_type": "Bearer"}; then `Authorization: Bearer <token>`.

    database InnovatorDB
    username di-connector   password Circularity-demo-aras-1   (send md5 hex: see PASSWORD_MD5)
    username admin          password innovator                 (Innovator's default administrator)
"""

import hashlib
import secrets
import time

from fastapi import Request

DATABASE = "InnovatorDB"
CLIENTS = {"IOMApp": {"Innovator", "openid", "offline_access"}}  # the client registry in OAuth.config
USERS = {"di-connector": "Circularity-demo-aras-1", "admin": "innovator"}
PASSWORD_MD5 = {u: hashlib.md5(p.encode()).hexdigest() for u, p in USERS.items()}
TOKEN_TTL = 3600
_tokens: dict[str, tuple[str, float]] = {}


def issue(form: dict) -> tuple[dict | None, str | None, str | None]:
    """(token body, error, error_description)"""
    if form.get("grant_type") != "password":
        return None, "unsupported_grant_type", None
    scopes = set((form.get("scope") or "").split())
    allowed = CLIENTS.get(form.get("client_id") or "")
    if allowed is None:
        return None, "invalid_client", None
    if not scopes or not scopes <= allowed or "Innovator" not in scopes:
        return None, "invalid_scope", None
    user, pw, db = form.get("username") or "", (form.get("password") or "").lower(), form.get("database") or ""
    if db != DATABASE:
        return None, "invalid_grant", f"Database '{db}' is not available"
    if PASSWORD_MD5.get(user) != pw:
        return None, "invalid_grant", "invalid_username_or_password"
    tok = secrets.token_urlsafe(48)
    _tokens[tok] = (user, time.time() + TOKEN_TTL)
    return {"access_token": tok, "expires_in": TOKEN_TTL, "token_type": "Bearer", "scope": " ".join(sorted(scopes))}, None, None


def user_of(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        return None
    t = _tokens.get(h[7:].strip())
    return t[0] if t and t[1] > time.time() else None
