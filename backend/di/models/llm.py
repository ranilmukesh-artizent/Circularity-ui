"""The LLM router's tables (migration 0036; plan 9 P9-2.3, registry entry I-9): each model with its limits, roles and
cooldown (`key_ref` names a setting, a key is never stored), and the requests and tokens used per model and window."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, Table, Text, text
from sqlalchemy.dialects.postgresql import ARRAY

from di.models.base import metadata, ts

llm_model = Table(
    "llm_model",
    metadata,
    Column("id", Text, primary_key=True),
    Column("provider", Text, nullable=False),  # groq, gemini (migration 0066), test
    Column("model", Text, nullable=False),
    Column("key_ref", Text),  # "env:<VAR>": the setting that holds the key
    Column("rpm", Integer, nullable=False),
    Column("tpm", Integer, nullable=False),
    Column("rpd", Integer, nullable=False),
    Column("ctx_tokens", Integer, nullable=False, server_default="8192"),
    Column("tools", Boolean, nullable=False, server_default=text("true")),
    Column("structured", Boolean, nullable=False, server_default=text("true")),
    Column("roles", ARRAY(Text), nullable=False),  # ask, agent, author, judge
    Column("priority", Integer, nullable=False, server_default="100"),
    Column("enabled", Boolean, nullable=False, server_default=text("true")),
    Column("request_timeout", Numeric, nullable=False, server_default="20"),
    ts("cooldown_until"),
    Column("eval_score", Numeric),
    Column("eval_prev", Numeric),
    ts("eval_at"),
    CheckConstraint("provider IN ('groq','gemini','test')", name="llm_model_provider"),
)

llm_budget = Table(
    "llm_budget",
    metadata,
    Column("model_id", Text, ForeignKey("llm_model.id", ondelete="CASCADE"), primary_key=True),
    Column("window", Text, primary_key=True),  # minute, day
    Column("window_start", DateTime(timezone=True), primary_key=True),
    Column("used_requests", Integer, nullable=False, server_default="0"),
    Column("used_tokens", Integer, nullable=False, server_default="0"),
    CheckConstraint("\"window\" IN ('minute','day')", name="llm_budget_window"),
)
