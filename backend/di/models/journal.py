"""The action journal, domain events and the live-update stream table (migrations 0003, 0008)."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Table,
    Text,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

# --- 0003 action journal and domain events --------------------------------------------------------------------------

action_journal = Table(
    "action_journal",
    metadata,
    Column("seq", BigInteger, primary_key=True),
    Column("action", Text, nullable=False),
    Column("input", JSONB, nullable=False),
    Column("actor", Text, nullable=False),  # account id, or "system"
    Column("role", Text, nullable=False),
    Column("preparer", Text),  # the agent that prepared it, if any
    Column("run_id", Text),
    Column("case_id", Text),
    Column("idem_key", Text),
    Column("output_ref", JSONB),
    Column("undone", Boolean, nullable=False, server_default=false()),
    ts("at", now=True),
    Index("ix_action_journal_case", "case_id", "seq"),
    # one live entry per idempotency key; an undone entry frees its key, so the action can be taken again
    Index("ux_action_journal_idem", "idem_key", unique=True, postgresql_where=text("NOT undone AND idem_key IS NOT NULL")),
)


domain_event = Table(
    "domain_event",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("type", Text, nullable=False),  # action.<id>, or a type the action emits
    Column("seq", BigInteger, ForeignKey("action_journal.seq")),
    Column("case_id", Text),
    Column("payload", JSONB, nullable=False),
    ts("at", now=True),
    Index("ix_domain_event_id_case", "case_id", "id"),
)


# --- 0008 live updates (the triggers that fill it are in the migration) ---------------------------------------------

stream_event = Table(
    "stream_event",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("kind", Text, nullable=False),  # journal, event, notification, sync, step, workflow
    Column("case_id", Text),
    Column("tenant", Text),  # the case's owner, for the tenant boundary
    Column("location", Text),  # the case's location, for the warehouse lock
    Column("payload", JSONB, nullable=False),
    ts("at", now=True),
)
