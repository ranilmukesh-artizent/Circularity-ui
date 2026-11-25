"""What the configuration agent drafted (migration 0040; plan 9 P9-2.7): one row per change set, with the reading log, the
question and answer, the typed overlay operations, and the proposal that holds the overlay draft for a person."""

from sqlalchemy import BigInteger, Column, ForeignKey, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

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
