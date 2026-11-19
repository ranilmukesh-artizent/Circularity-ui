"""Sign-in and request authentication (docs/BACKEND_STEPS.md, B7).

POST /api/auth/login takes the demo's sign-in IDs (exec, ops, planner.b@northfield.example …) and, as in the demo,
any non-empty password. It returns a JWT. Real single sign-on (OIDC, Keycloak as the stand-in) replaces the
password check later; the token and the dependencies below stay the same.

Endpoints depend on `Principal` (signed-in account + its run-time access state) and use the policy through it:
    def handler(p: Principal = Depends(principal)): p.require("approve.decisions"); p.require_tenant(case.owner)
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.config import get_settings
from di.db import get_session

_bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def issue_token(a: policy.Account) -> tuple[str, datetime]:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.jwt_ttl_minutes)
    token = jwt.encode(
        {"sub": a.id, "role": a.role, "tenant": a.tenant, "exp": exp, "iat": datetime.now(UTC)}, s.jwt_secret, ALGORITHM
    )
    return token, exp


def load_context(session: Session) -> policy.Context:
    deleg = {r.scope: r.enabled for r in session.execute(text("SELECT scope, enabled FROM delegation"))}
    grants: dict[str, list[str]] = {}
    for r in session.execute(text("SELECT account_id, tenant FROM tenant_grant ORDER BY tenant")):
        grants.setdefault(r.account_id, []).append(r.tenant)
    return policy.Context(delegations={k: deleg.get(k, True) for k in policy.DELEGATION_SCOPES}, grants=grants)


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
        if not policy.can_page(self.account, page, section):
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
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), session: Session = Depends(get_session)
) -> Principal:
    if creds is None:
        raise HTTPException(401, {"code": "unauthenticated", "message": "Sign in first."}, headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as e:
        raise HTTPException(
            401,
            {"code": "unauthenticated", "message": "Your session has ended. Sign in again."},
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from e
    a = policy.account(claims.get("sub", ""))
    if a is None:
        raise HTTPException(401, {"code": "unauthenticated", "message": "Unknown account."})
    return Principal(a, load_context(session))


def optional_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), session: Session = Depends(get_session)
) -> Principal | None:
    """The signed-in account, or None (for endpoints that answer anonymous callers themselves, like /api/actions)."""
    if creds is None:
        return None
    try:
        return principal(creds, session)
    except HTTPException:
        return None
