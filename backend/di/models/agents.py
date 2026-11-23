"""Agents (plan 8, phase 11): the registry (migration 0023)."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, Index, Table, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from di.models.base import metadata, ts

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

# --- 0024 proposals: an agent's write held for a person ----------------------------------------------------------------

agent_proposal = Table(
    "agent_proposal",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("agent", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("input", JSONB, nullable=False, server_default="{}"),
    Column("case_id", Text),
    Column("run_id", Text),
    Column("status", Text, nullable=False, server_default="pending"),  # pending, accepted, rejected, expired
    ts("created_at", now=True),
    Column("decided_by", Text),
    ts("decided_at"),
    Column("result", JSONB),
    CheckConstraint("status IN ('pending','accepted','rejected','expired')", name="agent_proposal_status"),
    Index("ix_agent_proposal_status", "status", "created_at"),
)
