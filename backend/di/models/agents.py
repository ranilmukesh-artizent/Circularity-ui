"""Agents (plan 8, phase 11): the registry (0023), proposals (0024) and runs (0025)."""

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Table, Text, func
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
    Column("requested_by", Text),  # 0028: the person the agent acted for (audit F3a)
    CheckConstraint("status IN ('pending','accepted','rejected','expired')", name="agent_proposal_status"),
    Index("ix_agent_proposal_status", "status", "created_at"),
)

# --- 0025 runs: an agent's run of a playbook, and each call it made -----------------------------------------------------

agent_run = Table(
    "agent_run",
    metadata,
    Column("id", Text, primary_key=True),
    Column("agent", Text, nullable=False),
    Column("playbook", Text, nullable=False),
    Column("case_id", Text),
    Column("status", Text, nullable=False, server_default="running"),  # running, waiting, done, failed, stopped
    Column("step", Integer, nullable=False, server_default="0"),
    Column("state", JSONB, nullable=False, server_default="{}"),
    ts("created_at", now=True),
    ts("updated_at", now=True),
    CheckConstraint("status IN ('running','waiting','done','failed','stopped')", name="agent_run_status"),
    Index("ix_agent_run_case", "case_id", "status"),
)

agent_run_step = Table(
    "agent_run_step",
    metadata,
    Column("run_id", Text, ForeignKey("agent_run.id", ondelete="CASCADE"), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("tool", Text, nullable=False),
    Column("input", JSONB, nullable=False, server_default="{}"),
    Column("output", JSONB),
    ts("at", now=True),
)
