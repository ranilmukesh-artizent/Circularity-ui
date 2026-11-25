"""The case process layer's items (migration 0033; plan 9 P9-1.7): exceptions, questions and steps with an owner role,
an optional due time and an escalation mark."""

from sqlalchemy import BigInteger, CheckConstraint, Column, Index, Integer, Table, Text

from di.models.base import metadata, ts

work_item = Table(
    "work_item",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("kind", Text, nullable=False),  # exception, needs_info, step
    Column("case_id", Text),
    Column("org_unit_id", Text),
    Column("type", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("cause", Text),
    Column("action", Text),
    Column("owner_role", Text, nullable=False),
    Column("owner_account", Text),
    Column("priority", Integer, nullable=False, server_default="100"),
    Column("status", Text, nullable=False, server_default="open"),  # open, done, cancelled
    ts("due_at"),
    ts("escalated_at"),
    Column("outcome", Text),
    Column("created_by", Text),
    ts("created_at", now=True),
    Column("closed_by", Text),
    ts("closed_at"),
    CheckConstraint("kind IN ('exception','needs_info','step')", name="work_item_kind"),
    CheckConstraint("status IN ('open','done','cancelled')", name="work_item_status"),
    Index("ix_work_item_status_owner", "status", "owner_role"),
    Index("ix_work_item_case", "case_id"),
)
