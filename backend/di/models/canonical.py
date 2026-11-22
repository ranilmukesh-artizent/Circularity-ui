"""The canonical store: provenance, canonical values, conflicts and failed records (migrations 0004, 0015)."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Index,
    Integer,
    Numeric,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

provenance = Table(
    "provenance",
    metadata,
    Column("model", Text, primary_key=True),
    Column("key", Text, primary_key=True),
    Column("field", Text, primary_key=True),
    Column("source_id", Text, primary_key=True),
    Column("value", JSONB),
    Column("source_field", Text),
    Column("source_value", JSONB),
    Column("transform", Text),
    Column("resource", Text),
    Column("ext_id", Text),
    Column("confidence", Numeric(5, 2)),
    ts("fetched_at", now=True),
    Index("ix_provenance_source", "source_id"),
)


canonical = Table(
    "canonical",
    metadata,
    Column("model", Text, primary_key=True),
    Column("key", Text, primary_key=True),
    Column("data", JSONB, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    ts("updated_at", now=True),
)


conflict = Table(
    "conflict",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("model", Text, nullable=False),
    Column("key", Text, nullable=False),
    Column("field", Text, nullable=False),
    Column("values", JSONB, nullable=False),  # {source_id: value}
    Column("authority", Text),  # the source whose value counts
    Column("status", Text, nullable=False, server_default="open"),  # open, resolved, escalated
    ts("opened_at", now=True),
    ts("closed_at"),
    Column("closed_by", Text),
    Column("note", Text),
    Column("values_hash", Text),  # 0016 (plan 6 B2): the differing values it was opened or resolved on
    Index(
        "ux_conflict_open", "model", "key", "field", unique=True, postgresql_where=text("status IN ('open', 'escalated')")
    ),  # 0016: one active (open or escalated) conflict per field
)


# --- 0015 failed records (plan 6 B1; di/services/canonical/failed.py) --------------------------------------------------------

failed_record = Table(
    "failed_record",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("run_kind", Text, nullable=False),  # sync, workflow, import
    Column("run_id", Text),  # sync_run.id, the workflow run's id or the import's IMP-n
    Column("source_id", Text),
    Column("step", Text),  # where it was held: canonical (the schema check), a workflow node, import
    Column("resource", Text),
    Column("ext_id", Text),
    Column("field", Text),  # model.field
    Column("rule", Text),  # schema, a validation rule ...
    Column("value", JSONB),
    Column("reason", Text, nullable=False),
    Column("payload", JSONB),  # the record it came from, for reprocessing
    Column("status", Text, nullable=False, server_default="held"),  # held, reprocessed, dropped
    ts("created_at", now=True),
    CheckConstraint("run_kind IN ('sync', 'workflow', 'import')", name="failed_record_run_kind_check"),
    CheckConstraint("status IN ('held', 'reprocessed', 'dropped')", name="failed_record_status_check"),
    Index("ix_failed_record_run", "run_kind", "run_id"),
    Index("ix_failed_record_source", "source_id", "status"),
)
