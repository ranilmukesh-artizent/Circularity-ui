"""AssetWise authentication for the mock (demo credentials, not secrets).

- Bentley IMS (OpenID Connect / OAuth 2.0, IdentityServer): POST /assetwise/ims/connect/token, form-encoded
  grant_type=client_credentials, client_id, client_secret, scope -> {"access_token", "token_type": "Bearer",
  "expires_in": 3600, "scope"}; then `Authorization: Bearer <token>` on the AssetWise OData service.
  Service app: client_id service-circularity-di, client_secret circularity-demo-ims-secret, scope assetwise-odata.
- Basic authentication with an AssetWise user (documented for the data warehouse OData endpoint):
  di.connector / Circularity-demo-aw-1.
Token errors follow IdentityServer: 400 {"error": "invalid_client" | "invalid_scope" | "unsupported_grant_type"};
the service answers 401 with an OData error body and `WWW-Authenticate: Bearer` without valid credentials.
"""

import base64
import binascii
import secrets
import time

from fastapi import Request

CLIENTS = {"service-circularity-di": ("circularity-demo-ims-secret", "di.connector", {"assetwise-odata"})}
USERS = {"di.connector": "Circularity-demo-aw-1", "eng.approver": "Circularity-demo-aw-approver"}
TOKEN_TTL = 3600
_tokens: dict[str, tuple[str, float]] = {}  # token -> (user, expires)


def issue(client_id: str, client_secret: str, scope: str) -> tuple[dict | None, str | None]:
    known = CLIENTS.get(client_id)
    if known is None or known[0] != client_secret:
        return None, "invalid_client"
    wanted = set(scope.split()) if scope else set(known[2])
    if not wanted <= known[2]:
        return None, "invalid_scope"
    tok = secrets.token_urlsafe(48)
    _tokens[tok] = (known[1], time.time() + TOKEN_TTL)
    return {"access_token": tok, "token_type": "Bearer", "expires_in": TOKEN_TTL, "scope": " ".join(sorted(wanted))}, None


def user_of(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        t = _tokens.get(h[7:].strip())
        return t[0] if t and t[1] > time.time() else None
    if h.lower().startswith("basic "):
        try:
            user, _, pw = base64.b64decode(h[6:], validate=True).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            return None
        return user if USERS.get(user) == pw else None
    return None
