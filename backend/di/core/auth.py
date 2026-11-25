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

from di.core import orgs, policy, state
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
# A tenant grant counts while it is not revoked and not past its end (migration 0027). The end is wall-clock time (the
# database's now()), not the simulated workspace clock: access must not lapse faster when the simulation runs fast.
LIVE_GRANT = "revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())"


def grant_end(at: datetime | None) -> str | None:
    """A grant's end as the API sends it: ISO 8601 in UTC, or None for no end."""
    return at.astimezone(UTC).isoformat() if at else None


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
    if _revoked(session, a.id, claims.get("iat")):
        raise HTTPException(401, _ENDED, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    return Principal(a, ctx)


def _revoked(session: Session, account_id: str, issued_at: object) -> bool:
    """A token issued at or before the account's `revoked_after` is refused (P9-8.11: a leaver's sessions end at once).
    `revoked_after` is wall-clock ISO time in the collection "account_revoked"; `iat` has whole seconds, so a token
    issued in the same second as the revocation counts as issued before it."""
    rec = state.get(session, "account_revoked", account_id)
    if rec is None or not rec.get("revoked_after"):
        return False
    after = datetime.fromisoformat(rec["revoked_after"]).timestamp()
    return not isinstance(issued_at, int | float) or issued_at <= int(after)


GROUP_RULES = text(
    "SELECT group_id, role, org_unit_id, site, warehouse FROM idp_group_map WHERE status = 'approved' "
    "AND (valid_from IS NULL OR valid_from <= current_date) AND (valid_to IS NULL OR valid_to >= current_date) ORDER BY id"
)


def load_group_map(session: Session) -> dict[str, policy.GroupRule]:
    """The directory group rules in force: approved rows within their dates (a later row for a group wins)."""
    return {
        r.group_id: policy.GroupRule(r.group_id, r.role, r.org_unit_id, r.site, r.warehouse) for r in session.execute(GROUP_RULES)
    }


def load_context(session: Session) -> policy.Context:
    deleg = {r.scope: r.enabled for r in session.execute(text("SELECT scope, enabled FROM delegation"))}
    grants: dict[str, list[str]] = {}
    ends: dict[str, dict[str, str | None]] = {}
    live = text(f"SELECT account_id, tenant, expires_at FROM tenant_grant WHERE {LIVE_GRANT} ORDER BY tenant")  # noqa: S608 - a constant
    for r in session.execute(live):
        grants.setdefault(r.account_id, []).append(r.tenant)
        ends.setdefault(r.account_id, {})[r.tenant] = grant_end(r.expires_at)
    approval = state.get(session, "access_settings", "approval") or {}
    units = session.execute(text("SELECT id, parent_id, kind, name FROM org_unit ORDER BY created_at, id"))
    return policy.Context(
        group_map=load_group_map(session),
        delegations={k: deleg.get(k, True) for k in policy.DELEGATION_SCOPES},
        grants=grants,
        grant_ends=ends,
        # the accounts as the identity mapping has them now (access.mapIdentity)
        accounts={d["id"]: policy.Account(**d) for d in state.items(session, "accounts")},
        limits=approval.get("limits", dict(policy.STARTING_LIMITS)),
        self_approval=bool(approval.get("self")),
        org_units={r.id: orgs.OrgUnit(r.id, r.parent_id, r.kind, r.name) for r in units},  # plan 8 MVP-1.2
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
