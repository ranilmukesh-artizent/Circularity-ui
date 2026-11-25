"""OIDC sign-in beside the demo sign-in (plan 9 P9-8.9, story X-10), behind the routes in di.routes.auth.

Flow (authorization code with PKCE S256 and a nonce, authlib 1.9 + joserfc):
    start()    -> the provider's authorize URL; keeps state, nonce and PKCE verifier in `oidc_login` (valid 10 minutes)
    callback() -> spends the state, swaps the code for tokens at the provider (server to server), validates the ID token
                  (signature from the JWKS, iss, aud, nonce, exp), resolves the account, keeps a one-time code (60 s)
                  and returns the SPA URL `/#/signin?sso=<code>`
    exchange() -> the one-time code for OUR token and the policy summary: the same body as `di.services.auth.login`

Owns: the flow, the ID-token checks and the account resolution (`resolve_directory_user`).
Never does: keep, return or log the provider's tokens or the client secret; give Admin through a group; sign in
anyone whose ID token fails a check (401, the session-ended text, nothing created); read the demo sign-in.
Provisioning a joiner is the system-only action `access.provisionUser` (di.services.actions.access), never a direct write.
Everything is off unless `oidc_issuer`, `oidc_client_id` and `oidc_redirect_uri` are set (`enabled()`).
"""

from typing import Any
from urllib.parse import quote

import httpx2
from authlib.common.errors import AuthlibBaseError  # type: ignore[import-untyped]
from authlib.common.security import generate_token  # type: ignore[import-untyped]
from authlib.integrations.httpx_client import OAuth2Client  # type: ignore[import-untyped]
from fastapi import HTTPException
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy, state
from di.core.auth import issue_token, load_context
from di.core.config import get_settings
from di.services.actions.pipeline import SYSTEM, CallContext, invoke

# tests set this to an httpx transport that stands in for the provider (no network)
HTTP_TRANSPORT: httpx2.BaseTransport | None = None

SCOPE = "openid email profile"
LABEL = "Sign in with your organisation"
NOT_MAPPED = "Your organisation account is not mapped to a Circularity role. Ask your administrator."
STATE_MINUTES = 10  # a state older than this is invalid
CODE_SECONDS = 60  # the one-time code the SPA exchanges
_ENDED = {"code": "unauthenticated", "message": "Your session has ended. Sign in again."}
_UNAVAILABLE = {
    "code": "idp_unavailable",
    "message": "Sign-in with your organisation is not available. Try again, or use your password.",
}


def enabled() -> bool:
    s = get_settings()
    return bool(s.oidc_issuer and s.oidc_client_id and s.oidc_redirect_uri)


def _ended() -> HTTPException:
    return HTTPException(401, _ENDED, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})


def _internal(url: str) -> str:
    """The address the api calls: the issuer's origin is replaced by `oidc_internal_url` (the browser sees another one)."""
    s = get_settings()
    issuer, internal = s.oidc_issuer.rstrip("/"), s.oidc_internal_url.rstrip("/")
    return internal + url[len(issuer) :] if internal and url.startswith(issuer) else url


def _discovery() -> dict[str, Any]:
    issuer = get_settings().oidc_issuer.rstrip("/")
    try:
        with httpx2.Client(transport=HTTP_TRANSPORT, timeout=10) as c:
            r = c.get(_internal(issuer) + "/.well-known/openid-configuration")
            r.raise_for_status()
            doc: dict[str, Any] = r.json()
    except (httpx2.HTTPError, ValueError) as e:
        raise HTTPException(502, _UNAVAILABLE) from e
    if str(doc.get("issuer", "")).rstrip("/") != issuer:
        raise HTTPException(502, _UNAVAILABLE)
    return doc


def _client(secret: bool) -> OAuth2Client:
    s = get_settings()
    return OAuth2Client(
        client_id=s.oidc_client_id,
        client_secret=s.oidc_client_secret.get_secret_value() if secret else None,
        token_endpoint_auth_method="client_secret_basic",  # noqa: S106 - a method name, not a secret
        scope=SCOPE,
        redirect_uri=s.oidc_redirect_uri,
        code_challenge_method="S256",
        transport=HTTP_TRANSPORT,
        timeout=10,
    )


def start(session: Session) -> str:
    """The provider's authorize URL for a new attempt (state, nonce and PKCE verifier are kept for the callback)."""
    doc = _discovery()
    state_, nonce, verifier = generate_token(32), generate_token(32), generate_token(64)
    session.execute(text("DELETE FROM oidc_login WHERE created_at < now() - interval '1 day'"))
    session.execute(
        text("INSERT INTO oidc_login (state, nonce, verifier) VALUES (:s, :n, :v)"),
        {"s": state_, "n": nonce, "v": verifier},
    )
    session.commit()
    with _client(secret=False) as c:
        url, _ = c.create_authorization_url(doc["authorization_endpoint"], state=state_, code_verifier=verifier, nonce=nonce)
    return str(url)


def _spend_state(session: Session, state_: str) -> tuple[str, str]:
    """(nonce, verifier) of a state that is unused and under 10 minutes old; the state is spent either way."""
    row = session.execute(
        text(
            "UPDATE oidc_login SET used_at = now() WHERE state = :s AND used_at IS NULL "
            "AND created_at > now() - make_interval(mins => :m) RETURNING nonce, verifier"
        ),
        {"s": state_, "m": STATE_MINUTES},
    ).first()
    session.commit()
    if row is None:
        raise _ended()
    return row.nonce, row.verifier


def _id_token_claims(doc: dict[str, Any], id_token: str, nonce: str) -> dict[str, Any]:
    """The ID token's claims once signature (RS256, the provider's JWKS), iss, aud, nonce and exp are all right."""
    s = get_settings()
    try:
        with httpx2.Client(transport=HTTP_TRANSPORT, timeout=10) as c:
            r = c.get(_internal(doc["jwks_uri"]))
            r.raise_for_status()
            keys = KeySet.import_key_set(r.json())
        token = jwt.decode(id_token, keys, algorithms=["RS256"])
        JWTClaimsRegistry(
            iss={"essential": True, "value": s.oidc_issuer.rstrip("/")},
            aud={"essential": True, "value": s.oidc_client_id},
            nonce={"essential": True, "value": nonce},
            exp={"essential": True},
            sub={"essential": True},
        ).validate(token.claims)
    except (httpx2.HTTPError, JoseError, ValueError, KeyError) as e:
        raise _ended() from e
    return dict(token.claims)


def _groups(claims: dict[str, Any]) -> list[str]:
    raw = claims.get(get_settings().oidc_groups_claim)
    if isinstance(raw, str):
        return [raw]
    return [g for g in raw if isinstance(g, str)] if isinstance(raw, list) else []


def callback(session: Session, state_: str, code: str) -> str:
    """Finish the attempt: the SPA URL carrying a one-time code, or one carrying the reason there is no account."""
    nonce, verifier = _spend_state(session, state_)
    doc = _discovery()
    try:
        with _client(secret=True) as c:
            tokens = c.fetch_token(
                _internal(doc["token_endpoint"]), code=code, code_verifier=verifier, grant_type="authorization_code"
            )
    except (AuthlibBaseError, httpx2.HTTPError, ValueError) as e:
        raise _ended() from e
    id_token = tokens.get("id_token")
    if not isinstance(id_token, str):
        raise _ended()
    claims = _id_token_claims(doc, id_token, nonce)  # the tokens are dropped here: nothing of them is stored or returned
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise _ended()
    name = claims.get("name")
    account = resolve_directory_user(session, email, _groups(claims), name if isinstance(name, str) else None)
    if account is None:
        return "/#/signin?sso_error=" + quote(NOT_MAPPED)
    one_time = generate_token(32)
    session.execute(
        text(
            "UPDATE oidc_login SET code = :c, account_id = :a, "
            "code_expires_at = now() + make_interval(secs => :t) WHERE state = :s"
        ),
        {"c": one_time, "a": account.id, "s": state_, "t": CODE_SECONDS},
    )
    session.commit()
    return "/#/signin?sso=" + one_time


def exchange(session: Session, code: str) -> dict[str, Any]:
    """The one-time code for our own token and the policy summary (the shape of POST /api/auth/login)."""
    row = session.execute(
        text("UPDATE oidc_login SET code = NULL WHERE code = :c AND code_expires_at > now() RETURNING account_id"), {"c": code}
    ).first()
    session.commit()
    account = policy.account(row.account_id, load_context(session)) if row else None
    if account is None:
        raise _ended()
    token, exp = issue_token(account)
    body = {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat()}
    return {**body, **policy.summary(account, load_context(session))}


def resolve_directory_user(session: Session, email: str, groups: list[str], name: str | None = None) -> policy.Account | None:
    """The account for a directory user: the one linked to that email (as mapped now), else one provisioned from the
    user's first group that maps to a role other than Admin; None when no group maps (the map is the table idp_group_map)."""
    ctx = load_context(session)
    wanted = email.strip().lower()
    for u in state.items(session, "idp_users"):
        if str(u["email"]).lower() == wanted and u.get("acct"):
            return policy.account(u["acct"], ctx)
    for group in groups:
        rule = policy.group_role(group, ctx)  # the approved, in-date mapping of the group (table idp_group_map)
        if rule is None or rule.role not in policy.idp_roles():  # never Admin from a group
            continue
        out = invoke(
            "access.provisionUser",
            {"email": wanted, "name": name or wanted.split("@")[0], "role": rule.role, "tenant": rule.org_unit_id,
             "site": rule.site, "warehouse": rule.warehouse, "via_group": group},
            CallContext(actor=SYSTEM, session=session),
        )  # fmt: skip
        if not out["ok"]:
            return None
        session.commit()
        return policy.account(out["output"]["account_id"], load_context(session))
    return None
