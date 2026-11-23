"""Agents (plan 8, phase 11): the registry (migration 0023)."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Table, Text, func
from sqlalchemy.dialects.postgresql import ARRAY

from di.models.base import metadata

# --- 0023 agent registry (seeded: the demo's nine agents, internal) --------------------------------------------------

agent_identity = Table(
    "agent_identity",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text),
    Column("kind", Text, nullable=False),  # internal, external
    Column("org_scope", ARRAY(Text), nullable=False, server_default="{}"),  # org unit ids; empty: every org
    Column("tools", ARRAY(Text), nullable=False, server_default="{}"),  # MCP tool ids (or action ids)
    Column("autonomy", Text, nullable=False, server_default="propose"),  # read, propose, act
    Column("enabled", Boolean, nullable=False, server_default="true"),
    Column("created_by", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    CheckConstraint("kind IN ('internal','external')", name="agent_identity_kind"),
    CheckConstraint("autonomy IN ('read','propose','act')", name="agent_identity_autonomy"),
)
