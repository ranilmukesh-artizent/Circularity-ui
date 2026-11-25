"""standing_policy and standing_policy_version (migration 0038; plan 9 P9-2.5, registry entry I-11): a person-owned approval
policy below thresholds, with its own maker-checker, and the rules each approval put in force."""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

standing_policy = Table(
    "standing_policy",
    metadata,
    Column("id", Text, primary_key=True),
    Column("pack", Text, nullable=False),
    Column("org_unit_id", Text, ForeignKey("org_unit.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("ver", Integer, nullable=False, server_default="0"),
    Column("status", Text, nullable=False),  # draft, review, active, retired
    Column("rules", JSONB, nullable=False),
    Column("owner", Text, nullable=False),
    Column("maker", Text, nullable=False),
    Column("checker", Text),
    ts("created_at", now=True),
    ts("updated_at", now=True),
    ts("approved_at"),
    CheckConstraint("status IN ('draft','review','active','retired')", name="standing_policy_status"),
    Index("ux_standing_policy_active", "pack", "org_unit_id", unique=True, postgresql_where=text("status = 'active'")),
)

standing_policy_version = Table(
    "standing_policy_version",
    metadata,
    Column("policy_id", Text, ForeignKey("standing_policy.id"), primary_key=True),
    Column("ver", Integer, primary_key=True),
    Column("rules", JSONB, nullable=False),
    Column("owner", Text, nullable=False),
    Column("approved_by", Text, nullable=False),
    ts("approved_at", nullable=False),
)
