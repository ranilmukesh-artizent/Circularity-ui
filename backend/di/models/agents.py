"""Agents (plan 8, phase 11): registry (0023), proposals (0024), runs (0025); plan 9: stage records (0034), messages (0035)."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Table,
    Text,
    func,
)
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
    Column("reasons", JSONB, nullable=False, server_default="[]"),  # 0037: [{reason, detail}] the hold policy gave (P9-2.4)
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

# --- 0034 stage records: what each stage of the chain said about a case in a run (plan 9, P9-2.1) ---------------------------

agent_stage_record = Table(
    "agent_stage_record",
    metadata,
    Column("run_id", Text, ForeignKey("agent_run.id", ondelete="CASCADE"), primary_key=True),
    Column("stage", Text, primary_key=True),
    Column("case_id", Text, nullable=False),
    Column("agent", Text, nullable=False),
    Column("kind", Text, nullable=False),  # deterministic, llm, queue
    Column("autonomy", Text, nullable=False),  # recommend, limits, alone
    Column("status", Text, nullable=False),  # done, skipped, held, waiting, exception
    Column("output", JSONB, nullable=False, server_default="{}"),
    Column("confidence", Numeric(4, 3)),
    Column("threshold", Numeric(4, 3), nullable=False),
    Column("sources", JSONB, nullable=False, server_default="[]"),
    Column("reasons", JSONB, nullable=False, server_default="[]"),
    ts("at", now=True),
    CheckConstraint("kind IN ('deterministic','llm','queue')", name="agent_stage_record_kind"),
    CheckConstraint("autonomy IN ('recommend','limits','alone')", name="agent_stage_record_autonomy"),
    CheckConstraint("status IN ('done','skipped','held','waiting','exception')", name="agent_stage_record_status"),
    Index("ix_agent_stage_record_case", "case_id", "at"),
)

# --- 0035 model messages of an LLM run, one row per turn (plan 9, P9-2.2) -------------------------------------------------------

agent_run_message = Table(
    "agent_run_message",
    metadata,
    Column("run_id", Text, ForeignKey("agent_run.id", ondelete="CASCADE"), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("messages", JSONB, nullable=False),
    Column("model", Text),
    ts("at", now=True),
)

# --- 0039 trace spans of an agent run (plan 9, P9-2.6, I-12) -------------------------------------------------------------

trace_span = Table(
    "trace_span",
    metadata,
    Column("span_id", Text, primary_key=True),
    Column("trace_id", Text, nullable=False),
    Column("parent_id", Text),
    Column("run_id", Text),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),  # run, stage, model, tool, action
    ts("started_at", nullable=False),
    ts("ended_at", nullable=False),
    Column("status", Text, nullable=False),  # ok, error
    Column("attrs", JSONB, nullable=False, server_default="{}"),
    CheckConstraint("kind IN ('run','stage','model','tool','action')", name="trace_span_kind"),
    CheckConstraint("status IN ('ok','error')", name="trace_span_status"),
    Index("ix_trace_span_run", "run_id", "started_at"),
    Index("ix_trace_span_started", "started_at"),
)

# --- 0060 client credentials of an agent (plan 9, P9-13.9): only a scrypt hash of the secret is stored ----------------------

agent_credential = Table(
    "agent_credential",
    metadata,
    Column("client_id", Text, primary_key=True),
    Column("agent_id", Text, ForeignKey("agent_identity.id", ondelete="CASCADE"), nullable=False),
    Column("owner", Text, nullable=False),  # the account the agent's token acts as
    Column("secret_hash", Text, nullable=False),  # scrypt$<salt>$<hash>
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    ts("last_used_at"),
    ts("revoked_at"),
    Index("ix_agent_credential_agent", "agent_id"),
)
