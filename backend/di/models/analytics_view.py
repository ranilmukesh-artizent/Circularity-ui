"""Saved analytics views (migration 0065; plan 9 P9-9.19, story UC-20): one worked question saved with its parameters by its
owner, shared with roles, with at most one measure alert. Plain table, read and written by `di.services.analytics_views`."""

from sqlalchemy import BigInteger, Boolean, Column, Index, Table, Text
from sqlalchemy.dialects.postgresql import JSONB

from di.models.base import metadata, ts

analytics_view = Table(
    "analytics_view",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("org_unit_id", Text, nullable=False),
    Column("owner", Text, nullable=False),  # the account id
    Column("owner_role", Text, nullable=False),  # the owner's role when saved: who the alert reaches with the owner
    Column("pack", Text, nullable=False),
    Column("question_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("params", JSONB, nullable=False, server_default="{}"),
    Column("shared_with_roles", JSONB, nullable=False, server_default="[]"),
    Column("alert", JSONB),  # {measure, op, threshold} or null
    Column("alert_active", Boolean, nullable=False, server_default="false"),  # crossed now: its items are open
    Column("alert_items", JSONB, nullable=False, server_default="[]"),  # the work item ids of the crossing
    ts("created_at", now=True),
    ts("updated_at", now=True),
    Index("ix_analytics_view_owner", "owner"),
)
