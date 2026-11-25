"""market_table (migration 0044; plan 9 P9-4.2, registry entry I-15): versions of per-market rate cards and decision tables,
each a draft, submitted, approved (by a different person) or rejected, with the dates it is in force."""

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, Index, Integer, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

market_table = Table(
    "market_table",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("org_unit_id", Text),  # None: shared by every org unit
    Column("pack", Text, nullable=False),
    Column("flow", Text, nullable=False),
    Column("market", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("status", Text, nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    Column("currency", Text),
    Column("body", JSONB, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("submitted_by", Text),
    Column("approved_by", Text),
    Column("reason", Text),
    ts("created_at", now=True),
    CheckConstraint("kind IN ('rate_card','decision_table')", name="market_table_kind"),
    CheckConstraint("status IN ('draft','submitted','approved','rejected','retired')", name="market_table_status"),
    UniqueConstraint("org_unit_id", "pack", "flow", "market", "name", "version", name="market_table_version"),
    Index("ix_market_table_lookup", "pack", "flow", "market", "name", "status", "valid_from"),
    Index(
        "ux_market_table_shared", "pack", "flow", "market", "name", "version", unique=True,
        postgresql_where=text("org_unit_id IS NULL"),
    ),
)  # fmt: skip
