"""OAuth 2.0 for the Salesforce mock: the JWT bearer flow and client credentials, and bearer-token checks.

Demo credentials (nothing real is protected here):
    connected app consumer key (client_id)   CLIENT_ID
    consumer secret (client_secret)          CLIENT_SECRET
    users (JWT `sub`)                        USERS: integration@northfield.example, sales.ops@northfield.example
The JWT bearer flow takes `assertion`, a JWT whose claims carry iss = CLIENT_ID, sub = a known username,
aud = https://login.salesforce.com (or test.salesforce.com) and an exp in the future. The signature is not checked.
Client credentials run as the integration user.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Request

from sim.vendors.salesforce.schema import make_id

CLIENT_ID = "3MVG9circularity.demo.northfield.crm.connector"
CLIENT_SECRET = "circularity-demo-salesforce-secret"
ORG_ID = make_id("00D", 4711)
AUDIENCES = ("https://login.salesforce.com", "https://test.salesforce.com")
INTEGRATION_USER = "integration@northfield.example"
# username -> (user number for its id, first name, last name, title)
USERS = {
    INTEGRATION_USER: (1, "Integration", "User", "Circularity DI connector"),
    "sales.ops@northfield.example": (2, "Sales", "Operations", "Sales Operations"),
}
TOKEN_TTL = 7200


def user_id(username: str) -> str:
    return make_id("005", USERS[username][0])


@dataclass
class Session:
    user_id: str
    expires: float


_sessions: dict[str, Session] = {}


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error, self.description, self.status = error, description, status


def _b64json(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def _jwt_user(assertion: str) -> str:
    parts = (assertion or "").split(".")
    if len(parts) != 3:
        raise OAuthError("invalid_grant", "invalid assertion")
    try:
        header, claims = _b64json(parts[0]), _b64json(parts[1])
    except (ValueError, binascii.Error):
        raise OAuthError("invalid_grant", "invalid assertion") from None
    if not isinstance(header, dict) or not isinstance(claims, dict) or "alg" not in header:
        raise OAuthError("invalid_grant", "invalid assertion")
    if claims.get("iss") != CLIENT_ID:
        raise OAuthError("invalid_client_id", "client identifier invalid")
    if claims.get("aud") not in AUDIENCES:
        raise OAuthError("invalid_grant", "audience is invalid")
    exp = claims.get("exp")
    if not isinstance(exp, int | float) or exp < time.time():
        raise OAuthError("invalid_grant", "expired authorization code")
    if claims.get("sub") not in USERS:
        raise OAuthError("invalid_grant", "user hasn't approved this consumer")
    return claims["sub"]


def _client_credentials(form: dict, header: str) -> str:
    cid, secret = form.get("client_id", ""), form.get("client_secret", "")
    if header.lower().startswith("basic "):
        try:
            cid, _, secret = base64.b64decode(header[6:]).decode().partition(":")
        except (ValueError, binascii.Error):
            pass
    if cid != CLIENT_ID:
        raise OAuthError("invalid_client_id", "client identifier invalid")
    if not hmac.compare_digest(secret, CLIENT_SECRET):
        raise OAuthError("invalid_client", "invalid client credentials")
    return INTEGRATION_USER


def issue(form: dict, header: str, instance_url: str) -> dict:
    grant = form.get("grant_type")
    if grant == "urn:ietf:params:oauth:grant-type:jwt-bearer":
        username = _jwt_user(form.get("assertion", ""))
    elif grant == "client_credentials":
        username = _client_credentials(form, header)
    else:
        raise OAuthError("unsupported_grant_type", "grant type not supported")
    uid = user_id(username)
    token = f"{ORG_ID[:15]}!{secrets.token_urlsafe(48)}"
    _sessions[token] = Session(uid, time.time() + TOKEN_TTL)
    issued_at = str(int(time.time() * 1000))
    identity = f"https://login.salesforce.com/id/{ORG_ID}/{uid}"
    sig = base64.b64encode(hmac.new(CLIENT_SECRET.encode(), (identity + issued_at).encode(), hashlib.sha256).digest()).decode()
    return {
        "access_token": token,
        "scope": "api",
        "instance_url": instance_url,
        "id": identity,
        "token_type": "Bearer",
        "issued_at": issued_at,
        "signature": sig,
    }


def session_user(request: Request) -> str | None:
    """The calling user's id, or None when the session is missing, invalid or expired."""
    h = request.headers.get("authorization", "")
    scheme, _, token = h.partition(" ")
    if scheme.lower() not in ("bearer", "oauth"):
        return None
    s = _sessions.get(token.strip())
    return s.user_id if s and s.expires > time.time() else None


def expire_all_tokens() -> int:
    """Fault injection (B6): every issued session stops working."""
    n = len(_sessions)
    _sessions.clear()
    return n
