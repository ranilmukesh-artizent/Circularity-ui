"""Cases and their stage log (migration 0005)."""

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

# --- 0005 cases -----------------------------------------------------------------------------------------------------

case_record = Table(
    "case_record",
    metadata,
    Column("id", Text, primary_key=True),
    Column("owner", Text, nullable=False),  # tenant
    Column("location", Text, nullable=False),
    Column("stage", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("data", JSONB, nullable=False),
    ts("created_at", now=True),
    ts("updated_at", now=True),
    Index("ix_case_record_owner", "owner"),
)


case_stage_log = Table(
    "case_stage_log",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("case_id", Text, ForeignKey("case_record.id", ondelete="CASCADE"), nullable=False),
    Column("from_stage", Text),  # null when the case was opened
    Column("to_stage", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("seq", BigInteger, ForeignKey("action_journal.seq")),  # the action behind it, if any
    ts("at", now=True),
    Index("ix_case_stage_log_case", "case_id", "id"),
)
