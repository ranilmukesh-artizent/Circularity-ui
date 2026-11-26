"""Authorization code flow with PKCE for outside MCP clients (plan 9, P9-13.10; MCP authorization 2026-07-28, OAuth 2.1
draft-ietf-oauth-v2-1, RFC 7636 PKCE, RFC 8707 resource indicators, RFC 8414 / RFC 9728 metadata).

Owns: pre-registered clients (`oauth_client`), the signed authorization request the consent page carries, consent, the
single-use code (stored as its SHA-256, 60 seconds) and the audience-bound access token (`aud` the MCP resource, `sub`
the person, `act.sub` "agent:<id>", `scope`, `client_id`, 15 minutes, no refresh token).
Never: accepts a `plain` challenge, a redirect URI that is not an exact match, a scope the client was not registered
for, or a resource other than this server's MCP; logs or stores a code or token; forwards a token; approves, overrides,
declines or changes access (the token acts as the person, prepared by the agent: the action pipeline and
FORBIDDEN_ACTIONS still decide every call). Dynamic registration and client ID metadata documents are not offered.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import jwt
from authlib.oauth2.rfc7636 import create_s256_code_challenge  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import auth, policy, state
from di.core.config import get_settings
from di.mcp import oauth as resource
from di.services import agent_credentials
from di.services.agents import registry

CODE_SECONDS = 60
TOKEN_SECONDS = 900
REQUEST_SECONDS = 600
REQ_AUDIENCE = "oauth-request"
SCOPES = resource.SCOPES


class OAuthError(Exception):
    def __init__(self, code: str, description: str, status: int = 400):
        super().__init__(description)
        self.code, self.description, self.status = code, description, status


def _key() -> str:
    return get_settings().jwt_secret.get_secret_value()


def issuer() -> str:
    u = urlsplit(get_settings().mcp_resource_url)
    return f"{u.scheme}://{u.netloc}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def metadata() -> dict[str, Any]:
    """RFC 8414 authorization server metadata."""
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_basic", "client_secret_post"],
        "scopes_supported": SCOPES,
    }


# --- clients ---------------------------------------------------------------------------------------------------------


def register_client(s: Session, name: str, redirect_uris: list[str], agent_id: str, scopes: list[str], created_by: str) -> str:
    client_id = "ocl_" + secrets.token_hex(8)
    s.execute(
        text(
            "INSERT INTO oauth_client (client_id, name, redirect_uris, agent_id, scopes, created_by) "
            "VALUES (:c, :n, :r, :a, :s, :b)"
        ),
        {"c": client_id, "n": name, "r": redirect_uris, "a": agent_id, "s": scopes, "b": created_by},
    )
    return client_id


def revoke_client(s: Session, client_id: str) -> bool:
    r = s.execute(
        text("UPDATE oauth_client SET revoked_at = now() WHERE client_id = :c AND revoked_at IS NULL"), {"c": client_id}
    )
    return bool(r.rowcount)  # type: ignore[attr-defined]


def clients(s: Session) -> list[dict[str, Any]]:
    rows = s.execute(
        text(
            "SELECT c.client_id, c.name, c.redirect_uris, c.agent_id, c.scopes, c.created_by, c.created_at, c.revoked_at, "
            "a.name AS agent_name FROM oauth_client c LEFT JOIN agent_identity a ON a.id = c.agent_id "
            "ORDER BY c.created_at, c.client_id"
        )
    ).mappings()
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} for r in rows]


def _client(s: Session, client_id: str) -> dict[str, Any] | None:
    row = (
        s.execute(
            text(
                "SELECT client_id, name, redirect_uris, agent_id, scopes FROM oauth_client "
                "WHERE client_id = :c AND revoked_at IS NULL"
            ),
            {"c": client_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def agent_usable(s: Session, agent_id: str) -> bool:
    agent = registry.get(s, agent_id)
    off = state.get(s, "access_settings", "agents_off") or {}
    return agent is not None and agent.enabled and not off.get(agent_id)


# --- authorize and consent -------------------------------------------------------------------------------------------


def authorize(s: Session, q: dict[str, str]) -> str:
    """Check an authorization request and answer the signed request id the consent page carries."""
    client = _client(s, q.get("client_id", ""))
    if client is None:
        raise OAuthError("invalid_request", "Unknown client.")
    if q.get("redirect_uri") not in client["redirect_uris"]:  # exact string match (OAuth 2.1)
        raise OAuthError("invalid_request", "The redirect URI is not registered for this client.")
    if q.get("response_type") != "code":
        raise OAuthError("unsupported_response_type", "Only response_type=code is supported.")
    if q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
        raise OAuthError("invalid_request", "PKCE with code_challenge_method=S256 is required.")
    if q.get("resource") != get_settings().mcp_resource_url:
        raise OAuthError("invalid_target", "The resource must be this server's MCP endpoint.")
    asked = q.get("scope", "").split() or list(client["scopes"])
    if not set(asked) <= set(client["scopes"]) or not set(asked) <= set(SCOPES):
        raise OAuthError("invalid_scope", "A scope is outside what this client may ask for.")
    now = datetime.now(UTC)
    claims = {
        "aud": REQ_AUDIENCE, "iss": auth.ISSUER, "iat": now, "exp": now + timedelta(seconds=REQUEST_SECONDS),
        "cid": client["client_id"], "ru": q["redirect_uri"], "ch": q["code_challenge"], "sc": asked, "st": q.get("state", ""),
        "res": q["resource"], "jti": secrets.token_hex(8),
    }  # fmt: skip
    return jwt.encode(claims, _key(), "HS256")


def _request(req: str) -> dict[str, Any]:
    try:
        return jwt.decode(req, _key(), algorithms=["HS256"], audience=REQ_AUDIENCE, issuer=auth.ISSUER)
    except jwt.PyJWTError as e:
        raise OAuthError("invalid_request", "This authorization request is not valid or has expired.") from e


def describe(s: Session, req: str) -> dict[str, Any]:
    """What the consent page tells the person: the client, the agent and the scopes."""
    r = _request(req)
    client = _client(s, r["cid"])
    if client is None:
        raise OAuthError("invalid_request", "Unknown client.")
    agent = registry.get(s, client["agent_id"])
    name = agent.name if agent else client["agent_id"]
    return {"client_name": client["name"], "agent_id": client["agent_id"], "agent_name": name, "scopes": r["sc"]}


def _redirect(uri: str, **params: str) -> str:
    sep = "&" if urlsplit(uri).query else "?"
    return uri + sep + urlencode({k: v for k, v in params.items() if v})


def consent(s: Session, person: policy.Account, req: str, approve: bool) -> str:
    """The person's answer: the redirect URL, with a single-use code and the state, or `access_denied`."""
    r = _request(req)
    client = _client(s, r["cid"])
    if client is None or r["ru"] not in client["redirect_uris"]:
        raise OAuthError("invalid_request", "Unknown client.")
    if not approve:
        return _redirect(r["ru"], error="access_denied", state=r["st"])
    if not agent_usable(s, client["agent_id"]):
        raise OAuthError("access_denied", "The agent this client acts as is stopped.", 403)
    scopes = [x for x in r["sc"] if x in client["scopes"]]  # never more than the client was registered for
    code = secrets.token_urlsafe(32)
    s.execute(
        text(
            "INSERT INTO oauth_code (code, client_id, account_id, agent_id, scopes, resource, challenge, redirect_uri, "
            "expires_at) "
            "VALUES (:h, :c, :p, :a, :s, :res, :ch, :ru, now() + make_interval(secs => :t))"
        ),
        {"h": _hash(code), "c": client["client_id"], "p": person.id, "a": client["agent_id"], "s": scopes, "res": r["res"],
         "ch": r["ch"], "ru": r["ru"], "t": CODE_SECONDS},
    )  # fmt: skip
    return _redirect(r["ru"], code=code, state=r["st"])


# --- the token --------------------------------------------------------------------------------------------------------


def exchange(s: Session, f: dict[str, str]) -> dict[str, Any]:
    """grant_type=authorization_code: the code (single use), the verifier (S256), the redirect URI and the client."""
    bad = OAuthError("invalid_grant", "The code is invalid, used, expired or does not match.")
    verifier = f.get("code_verifier", "")
    if not f.get("code") or not 43 <= len(verifier) <= 128:
        raise bad
    row = (
        s.execute(
            text(
                "UPDATE oauth_code SET used_at = now() WHERE code = :h AND used_at IS NULL AND expires_at > now() "
                "RETURNING client_id, account_id, agent_id, scopes, resource, challenge, redirect_uri"
            ),
            {"h": _hash(f["code"])},
        )
        .mappings()
        .first()
    )  # one statement: a second exchange of the same code finds no row
    if row is None:
        raise bad
    ok = (
        _client(s, row["client_id"]) is not None
        and f.get("client_id") == row["client_id"]
        and f.get("redirect_uri") == row["redirect_uri"]
        and secrets.compare_digest(create_s256_code_challenge(verifier), row["challenge"])
        and (not f.get("resource") or f["resource"] == row["resource"])
    )
    if not ok or not agent_usable(s, row["agent_id"]) or not agent_credentials.owner_active(s, row["account_id"]):
        raise bad
    now = datetime.now(UTC)
    claims = {
        "iss": auth.ISSUER,
        "aud": row["resource"],
        "sub": row["account_id"],
        "act": {"sub": agent_credentials.PREFIX + row["agent_id"]},
        "scope": " ".join(row["scopes"]),
        "client_id": row["client_id"],
        "iat": now,
        "exp": now + timedelta(seconds=TOKEN_SECONDS),
    }
    token = jwt.encode(claims, _key(), "HS256")
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_SECONDS, "scope": claims["scope"]}
