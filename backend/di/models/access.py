"""Access state: Approver delegations and tenant grants (migrations 0002 and 0027), OIDC sign-in attempts (0056) and the
directory group to role map (0057)."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Table,
    Text,
)

from di.models.base import metadata, ts

# --- 0002 access state ----------------------------------------------------------------------------------------------

delegation = Table(
    "delegation",
    metadata,
    Column("scope", Text, primary_key=True),  # decisions, mcp, tenantAccess
    Column("enabled", Boolean, nullable=False),
    Column("updated_by", Text),
    ts("updated_at", now=True),
    CheckConstraint("scope IN ('decisions','mcp','tenantAccess')", name="ck_delegation_scope"),
)


# 0056 (P9-8.9): one OIDC sign-in attempt: state, nonce and PKCE verifier (valid 10 minutes), then a one-time code (60 s)
oidc_login = Table(
    "oidc_login",
    metadata,
    Column("state", Text, primary_key=True),
    Column("nonce", Text, nullable=False),
    Column("verifier", Text, nullable=False),
    ts("created_at", now=True),
    ts("used_at"),
    Column("code", Text, unique=True),
    Column("account_id", Text),
    ts("code_expires_at"),
)

# 0057 (P9-8.10): which role and scope a directory group gives; a draft until another person approves it
idp_group_map = Table(
    "idp_group_map",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("group_id", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("org_unit_id", Text),
    Column("site", Text),
    Column("warehouse", Text),
    Column("valid_from", Date),
    Column("valid_to", Date),
    Column("status", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("approved_by", Text),
    ts("created_at", now=True),
    ts("approved_at"),
    CheckConstraint("status IN ('draft','approved','retired')", name="ck_idp_group_map_status"),
)

tenant_grant = Table(
    "tenant_grant",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("tenant", Text, primary_key=True),
    Column("granted_by", Text),
    ts("granted_at", now=True),
    # 0027: an end the approver chose (NULL: none) and a revocation; only a live grant counts (di.core.auth)
    ts("expires_at"),
    ts("revoked_at"),
    Column("revoked_by", Text),
    Column("revoke_note", Text),
)
