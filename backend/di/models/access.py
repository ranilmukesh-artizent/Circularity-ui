"""Access state: Approver delegations and tenant grants (migration 0002)."""

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
)
