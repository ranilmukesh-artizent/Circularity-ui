"""Sign-in and request authentication (docs/backend-steps.md, B7).

POST /api/auth/login takes the demo's sign-in IDs (exec, ops, planner.b@northfield.example …) and, as in the demo,
any non-empty password. It returns a JWT. Real single sign-on (OIDC, Keycloak as the stand-in) replaces the
password check later; the token and the dependencies below stay the same.

POST /api/auth/stream-ticket trades a valid access token for a 60-second stream ticket (aud "stream"), which only
GET /api/stream accepts, as `?ticket=` (F3: the access token stays out of URLs and access logs).

Endpoints depend on `Principal` (signed-in account + its run-time access state; the `CurrentPrincipal` alias in di.core.deps)
and use the policy through it:
    def handler(p: CurrentPrincipal): p.require("approve.decisions"); p.require_tenant(case.owner)
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy, state
from di.core.config import get_settings
from di.core.db import get_session

_bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"
ISSUER, AUDIENCE = "di-api", "di"  # D2: every token names who issued it and for whom; both are checked
REQUIRED_CLAIMS = ["exp", "sub", "iat", "iss", "aud"]
# F3: the live stream's EventSource cannot send headers, so the browser puts a ticket in the URL instead of its access
# token. A ticket is good for one thing (aud "stream": GET /api/stream only, never as a bearer token) and briefly.
STREAM_AUDIENCE = "stream"
STREAM_TICKET_SECONDS = 60
_ENDED = {"code": "unauthenticated", "message": "Your session has ended. Sign in again."}


def _sign(a: policy.Account, audience: str, lifetime: timedelta) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    exp = now + lifetime
    claims = {"sub": a.id, "role": a.role, "tenant": a.tenant, "exp": exp, "iat": now, "iss": ISSUER, "aud": audience}
    return jwt.encode(claims, get_settings().jwt_secret.get_secret_value(), ALGORITHM), exp


def issue_token(a: policy.Account) -> tuple[str, datetime]:
    return _sign(a, AUDIENCE, timedelta(minutes=get_settings().jwt_ttl_minutes))


def issue_stream_ticket(a: policy.Account) -> str:
    return _sign(a, STREAM_AUDIENCE, timedelta(seconds=STREAM_TICKET_SECONDS))[0]


def _resolve(token: str, audience: str, session: Session) -> "Principal":
    """The account behind a token for this audience, as mapped now; 401 for anything else (the token is not logged)."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=audience,
            issuer=ISSUER,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, _ENDED, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}) from e
    # The account is looked up by id on every request, as mapped now: a token issued before an identity mapping
    # changed the account's role or warehouse carries the old role claim, which is informational only.
    ctx = load_context(session)
    a = policy.account(claims.get("sub", ""), ctx)
    if a is None:
        raise HTTPException(401, {"code": "unauthenticated", "message": "Unknown account."})
    return Principal(a, ctx)


def load_context(session: Session) -> policy.Context:
    deleg = {r.scope: r.enabled for r in session.execute(text("SELECT scope, enabled FROM delegation"))}
    grants: dict[str, list[str]] = {}
    for r in session.execute(text("SELECT account_id, tenant FROM tenant_grant ORDER BY tenant")):
        grants.setdefault(r.account_id, []).append(r.tenant)
    approval = state.get(session, "access_settings", "approval") or {}
    return policy.Context(
        delegations={k: deleg.get(k, True) for k in policy.DELEGATION_SCOPES},
        grants=grants,
        # the accounts as the identity mapping has them now (access.mapIdentity)
        accounts={d["id"]: policy.Account(**d) for d in state.items(session, "accounts")},
        limits=approval.get("limits", dict(policy.STARTING_LIMITS)),
        self_approval=bool(approval.get("self")),
    )


@dataclass
class Principal:
    account: policy.Account
    ctx: policy.Context

    def can(self, perm: str) -> bool:
        return policy.can(self.account, perm, self.ctx)

    def require(self, perm: str) -> None:
        if not self.can(perm):
            raise HTTPException(
                403, {"code": "out_of_scope", "message": f"The {self.account.role} view cannot do this ({perm})."}
            )

    def require_page(self, page: str, section: str | None = None) -> None:
        self.require_any_page((page, section))

    def require_any_page(self, *pages: tuple[str, str | None]) -> None:
        """Refused unless the account sees at least one of these (page, section) pairs (section None: the page)."""
        if not any(policy.can_page(self.account, page, section) for page, section in pages):
            raise HTTPException(403, {"code": "out_of_scope", "message": f"Not available for the {self.account.role} view."})

    def tenant_ok(self, tenant: str) -> bool:
        return policy.tenant_ok(self.account, tenant, self.ctx)

    def location_ok(self, location: str) -> bool:
        return policy.location_ok(self.account, location)

    def require_record(self, record_id: str, tenant: str, location: str) -> None:
        """The demo's tenant boundary and warehouse lock for one record (a case or an asset)."""
        if not self.tenant_ok(tenant):
            raise HTTPException(
                403,
                {
                    "code": "tenant_boundary",
                    "message": f"{record_id} belongs to {tenant}, a tenant you cannot see. Request tenant access first.",
                },
            )
        if not self.location_ok(location):
            raise HTTPException(
                403, {"code": "tenant_boundary", "message": f"{record_id} is at {location}, outside your warehouse."}
            )


def principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)], session: Annotated[Session, Depends(get_session)]
) -> Principal:
    if creds is None:
        raise HTTPException(401, {"code": "unauthenticated", "message": "Sign in first."}, headers={"WWW-Authenticate": "Bearer"})
    return _resolve(creds.credentials, AUDIENCE, session)


def stream_principal(ticket: str, session: Session) -> Principal:
    """The account behind a stream ticket (aud "stream"); an access token is refused here, as a ticket is elsewhere."""
    return _resolve(ticket, STREAM_AUDIENCE, session)


def optional_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)], session: Annotated[Session, Depends(get_session)]
) -> Principal | None:
    """The signed-in account, or None (for endpoints that answer anonymous callers themselves, like /api/actions)."""
    if creds is None:
        return None
    try:
        return principal(creds, session)
    except HTTPException:
        return None
