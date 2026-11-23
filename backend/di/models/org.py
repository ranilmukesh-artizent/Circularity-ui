"""Organisation units (migration 0019; plan 8 MVP-1.1): the tree a tenant check reads (di/core/orgs.py)."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Table,
    Text,
)

from di.models.base import metadata, ts

# --- 0019 org units (seeded: workspace, and Customer A/B/C under it) --------------------------------------------------

org_unit = Table(
    "org_unit",
    metadata,
    Column("id", Text, primary_key=True),
    Column("parent_id", Text, ForeignKey("org_unit.id")),
    Column("kind", Text, nullable=False),  # group, segment, company, site, customer
    Column("name", Text, nullable=False),
    ts("created_at", now=True),
    CheckConstraint("kind IN ('group','segment','company','site','customer')", name="org_unit_kind"),
    Index("ix_org_unit_parent", "parent_id"),
)
