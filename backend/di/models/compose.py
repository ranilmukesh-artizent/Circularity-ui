"""What the configuration agent drafted (migration 0040; plan 9 P9-2.7): one row per change set, with the reading log, the
question and answer, the typed overlay operations, and the proposal that holds the overlay draft for a person.

Also the composition (migration 0058; P9-8.17): one approvable object per business description (change set, mapping rows, stage
settings) and its snapshots, one per status change."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from di.models.base import metadata, ts

config_change_set = Table(
    "config_change_set",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("org_unit_id", Text, ForeignKey("org_unit.id"), nullable=False),
    Column("pack", Text, nullable=False),
    Column("base_version", Text, nullable=False),
    Column("reading", JSONB, nullable=False),
    Column("question", JSONB),
    Column("answer", Text),
    Column("ops", JSONB, nullable=False),
    Column("assumed", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("blocked", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("systems", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("kpis", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("proposal_id", BigInteger),
    Column("created_by", Text, nullable=False),
    ts("created_at", now=True),
)

composition = Table(
    "composition",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("org_unit_id", Text, nullable=False),
    Column("pack_key", Text, nullable=False),
    Column("base_version", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("reading", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("change_set", JSONB, nullable=False),
    Column("steps", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("status", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("created_by", Text, nullable=False),
    Column("editors", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("submitted_by", Text),
    Column("approved_by", Text),
    Column("published_by", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    CheckConstraint("status IN ('draft','submitted','sent_back','approved','published','discarded')", name="composition_status"),
    Index("ix_composition_org_pack", "org_unit_id", "pack_key"),
)

composition_version = Table(
    "composition_version",
    metadata,
    Column("composition_id", BigInteger, nullable=False),
    Column("version", Integer, nullable=False),
    Column("snapshot", JSONB, nullable=False),
    Column("status", Text, nullable=False),
    Column("by", Text, nullable=False),
    Column("at", DateTime(timezone=True), server_default=func.now()),
    PrimaryKeyConstraint("composition_id", "version"),
)
