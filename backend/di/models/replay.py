"""replay_batch and replay_item (migration 0049; plan 9 P9-7.1, registry entry I-16): imported history of past decisions,
each item ok or held with its reason."""

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, ForeignKey, Index, Integer, Numeric, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

replay_batch = Table(
    "replay_batch",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("pack", Text, nullable=False),
    Column("org_unit_id", Text, ForeignKey("org_unit.id"), nullable=False),
    Column("rows", Integer, nullable=False),
    Column("held", Integer, nullable=False),
    Column("period_from", Date),
    Column("period_to", Date),
    Column("created_by", Text, nullable=False),
    ts("created_at", now=True),
)

replay_item = Table(
    "replay_item",
    metadata,
    Column("batch_id", BigInteger, ForeignKey("replay_batch.id", ondelete="CASCADE"), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("item_id", Text, nullable=False),
    ts("decided_at"),
    Column("cls", Text),
    Column("market", Text),
    Column("actual_route", Text),
    Column("realised_value", Numeric),
    Column("costs", JSONB, nullable=False, server_default=text("'{}'")),
    Column("facts", JSONB, nullable=False, server_default=text("'{}'")),
    Column("status", Text, nullable=False),
    Column("held_reason", Text),
    CheckConstraint("status IN ('ok','held')", name="replay_item_status"),
    Index("ix_replay_item_status", "batch_id", "status"),
)

replay_run = Table(
    "replay_run",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("batch_id", BigInteger, ForeignKey("replay_batch.id"), nullable=False),
    Column("flow_id", BigInteger, ForeignKey("decision_flow.id"), nullable=False),
    Column("flow_ver", Text, nullable=False),
    Column("dver", Integer),
    Column("status", Text, nullable=False),
    Column("report", JSONB),
    Column("error", Text),
    Column("created_by", Text, nullable=False),
    ts("created_at", now=True),
    ts("finished_at"),
    CheckConstraint("status IN ('queued','running','done','failed')", name="replay_run_status"),
    Index("ix_replay_run_flow", "flow_id", "dver", "status"),
)
