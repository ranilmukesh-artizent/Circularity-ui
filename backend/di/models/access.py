"""Access state: Approver delegations and tenant grants (migrations 0002 and 0027)."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
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
