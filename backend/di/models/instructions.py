"""Outbound instructions to the enterprise systems (migration 0007)."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Identity,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

# --- 0007 instructions ----------------------------------------------------------------------------------------------

instruction = Table(
    "instruction",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("case_id", Text, nullable=False),
    Column("approval_ref", Text, nullable=False),
    Column("step", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("system", Text, nullable=False),  # a source id (oms, repair, tms, wms, erp) or the step's system label
    Column("idem_key", Text, nullable=False, unique=True),
    Column("match_refs", JSONB, nullable=False, server_default="[]"),  # the values the system's events carry back
    Column("request", JSONB),  # what was sent, call by call
    Column("detail", JSONB, nullable=False, server_default="{}"),  # what later steps need from it
    Column("doc_ref", Text),  # the system's own document reference
    Column("status", Text, nullable=False, server_default="queued"),  # queued | sent | acknowledged | failed
    Column("simulated", Boolean, nullable=False, server_default=false()),
    Column("waiting_for", Text),  # set while a step cannot be sent yet
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text),
    ts("due_at"),  # simulated acknowledgement time (simulated clock)
    ts("queued_at"),  # these three on the workspace clock (di/core/clock.py)
    ts("sent_at"),
    ts("acknowledged_at"),
    ts("created_at", now=True),
    ts("updated_at", now=True),
    UniqueConstraint("approval_ref", "step", name="uq_instruction_step"),
    Index("ix_instruction_case", "case_id", "step"),
    Index("ix_instruction_status", "status"),
    Index("ix_instruction_refs", "match_refs", postgresql_using="gin"),
)
