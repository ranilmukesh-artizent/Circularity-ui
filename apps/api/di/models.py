"""The database schema, declared once on Base.metadata (finding F16).

The migrations (migrations/versions/0001-0010) create these tables; this module declares the same tables so that
`alembic check` (tests/test_models_migrations.py) can prove the two agree, and so that autogenerate starts from the
real schema. The database and the migrations are the source of truth: a change goes into a new migration first and
is mirrored here.

`Job` is a mapped class (di/jobs.py uses the ORM); every other table is a Core `Table`, read and written with SQL.

Not metadata (they live in the migrations only, and `alembic check` does not see them):
- the live-update functions and triggers of 0008/0009: stream_put(text, text, jsonb), stream_notify(),
  stream_from_domain_event(), stream_from_state_item(), stream_from_sync_run(), stream_from_instruction(), and the
  triggers stream_event_notify, domain_event_stream, state_item_stream, sync_run_stream, instruction_stream;
- the starting rows of `delegation` (0002).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from di.db import Base

metadata = Base.metadata


def _ts(name: str, *, nullable: bool = True, now: bool = False) -> Column:
    """A timestamp with time zone; `now` = NOT NULL DEFAULT now()."""
    if now:
        return Column(name, DateTime(timezone=True), nullable=False, server_default=func.now())
    return Column(name, DateTime(timezone=True), nullable=nullable)


# --- 0001 job queue -------------------------------------------------------------------------------------------------


class Job(Base):
    """Background work for di-worker (sync, outbound instructions, webhooks).

    Claimed with FOR UPDATE SKIP LOCKED, so any number of workers can share the table.
    """

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")  # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_job_queue", "status", "run_after"),
        CheckConstraint("status IN ('queued','running','done','failed')", name="ck_job_status"),
    )


# --- 0002 access state ----------------------------------------------------------------------------------------------

delegation = Table(
    "delegation",
    metadata,
    Column("scope", Text, primary_key=True),  # decisions, mcp, tenantAccess
    Column("enabled", Boolean, nullable=False),
    Column("updated_by", Text),
    _ts("updated_at", now=True),
    CheckConstraint("scope IN ('decisions','mcp','tenantAccess')", name="ck_delegation_scope"),
)

tenant_grant = Table(
    "tenant_grant",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("tenant", Text, primary_key=True),
    Column("granted_by", Text),
    _ts("granted_at", now=True),
)

# --- 0003 action journal and domain events --------------------------------------------------------------------------

action_journal = Table(
    "action_journal",
    metadata,
    Column("seq", BigInteger, primary_key=True),
    Column("action", Text, nullable=False),
    Column("input", JSONB, nullable=False),
    Column("actor", Text, nullable=False),  # account id, or "system"
    Column("role", Text, nullable=False),
    Column("preparer", Text),  # the agent that prepared it, if any
    Column("run_id", Text),
    Column("case_id", Text),
    Column("idem_key", Text),
    Column("output_ref", JSONB),
    Column("undone", Boolean, nullable=False, server_default=false()),
    _ts("at", now=True),
    Index("ix_action_journal_case", "case_id", "seq"),
    # one live entry per idempotency key; an undone entry frees its key, so the action can be taken again
    Index("ux_action_journal_idem", "idem_key", unique=True, postgresql_where=text("NOT undone AND idem_key IS NOT NULL")),
)

domain_event = Table(
    "domain_event",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("type", Text, nullable=False),  # action.<id>, or a type the action emits
    Column("seq", BigInteger, ForeignKey("action_journal.seq")),
    Column("case_id", Text),
    Column("payload", JSONB, nullable=False),
    _ts("at", now=True),
    Index("ix_domain_event_id_case", "case_id", "id"),
)

# --- 0004 connectors and the canonical store ------------------------------------------------------------------------

source_system = Table(
    "source_system",
    metadata,
    Column("id", Text, primary_key=True),
    Column("vendor", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("status", Text, nullable=False),  # live, paused, disconnected, failing, auth_expired, unavailable, manual
    Column("interval_min", Integer, nullable=False, server_default="0"),  # 0 = event-driven + hourly safety sync
    Column("authority", ARRAY(Text), nullable=False, server_default="{}"),
    Column("owner", Text),
    _ts("last_sync_at"),
    _ts("last_success_at"),
    Column("completeness", Numeric(5, 2)),
    Column("confidence", Numeric(5, 2)),
    Column("note", Text),
    _ts("updated_at", now=True),
    # 0012 (plan 6 A6): failed syncs in a row, and when the next try is due (min(2**streak minutes, interval))
    Column("fail_streak", Integer, nullable=False, server_default="0"),
    _ts("next_retry_at"),
)

sync_run = Table(
    "sync_run",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("source_id", Text, ForeignKey("source_system.id"), nullable=False),
    Column("trigger", Text, nullable=False),  # schedule, manual, webhook, initial
    Column("status", Text, nullable=False),  # running, ok, partial, failed
    _ts("started_at", now=True),
    _ts("finished_at"),
    Column("records_read", Integer, nullable=False, server_default="0"),
    Column("facts_written", Integer, nullable=False, server_default="0"),
    Column("records_failed", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Index("ix_sync_run_source", "source_id", "id"),
)

sync_cursor = Table(
    "sync_cursor",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("resource", Text, primary_key=True),
    Column("cursor", Text, nullable=False),
    _ts("updated_at", now=True),
)

fetch_log = Table(
    "fetch_log",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("run_id", BigInteger),
    Column("source_id", Text, nullable=False),
    Column("method", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("status", Integer),
    Column("records", Integer),
    Column("duration_ms", Integer),
    Column("error", Text),
    _ts("at", now=True),
    Index("ix_fetch_log_source", "source_id", "id"),
)

raw_record = Table(
    "raw_record",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("resource", Text, primary_key=True),
    Column("ext_id", Text, primary_key=True),
    Column("payload", JSONB, nullable=False),
    Column("request", Text),
    Column("fetch_id", BigInteger),
    _ts("fetched_at", now=True),
)

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
    _ts("fetched_at", now=True),
    Index("ix_provenance_source", "source_id"),
)

canonical = Table(
    "canonical",
    metadata,
    Column("model", Text, primary_key=True),
    Column("key", Text, primary_key=True),
    Column("data", JSONB, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    _ts("updated_at", now=True),
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
    _ts("opened_at", now=True),
    _ts("closed_at"),
    Column("closed_by", Text),
    Column("note", Text),
    Index("ux_conflict_open", "model", "key", "field", unique=True, postgresql_where=text("status = 'open'")),
)

# --- 0005 cases -----------------------------------------------------------------------------------------------------

case_record = Table(
    "case_record",
    metadata,
    Column("id", Text, primary_key=True),
    Column("owner", Text, nullable=False),  # tenant
    Column("location", Text, nullable=False),
    Column("stage", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("data", JSONB, nullable=False),
    _ts("created_at", now=True),
    _ts("updated_at", now=True),
    Index("ix_case_record_owner", "owner"),
)

case_stage_log = Table(
    "case_stage_log",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("case_id", Text, ForeignKey("case_record.id", ondelete="CASCADE"), nullable=False),
    Column("from_stage", Text),  # null when the case was opened
    Column("to_stage", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("seq", BigInteger, ForeignKey("action_journal.seq")),  # the action behind it, if any
    _ts("at", now=True),
    Index("ix_case_stage_log_case", "case_id", "id"),
)

# --- 0006 workspace state -------------------------------------------------------------------------------------------

state_item = Table(
    "state_item",
    metadata,
    Column("collection", Text, primary_key=True),
    Column("id", Text, primary_key=True),
    Column("seq", BigInteger, Identity(), nullable=False),  # insertion order
    Column("data", JSONB, nullable=False),
    _ts("updated_at", now=True),
    Index("ix_state_item_order", "collection", "seq"),
)

state_seed = Table(
    "state_seed",
    metadata,
    Column("collection", Text, primary_key=True),
    _ts("at", now=True),
)

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
    _ts("due_at"),  # simulated acknowledgement time (simulated clock)
    _ts("queued_at"),  # these three on the workspace clock (di/clock.py)
    _ts("sent_at"),
    _ts("acknowledged_at"),
    _ts("created_at", now=True),
    _ts("updated_at", now=True),
    UniqueConstraint("approval_ref", "step", name="uq_instruction_step"),
    Index("ix_instruction_case", "case_id", "step"),
    Index("ix_instruction_status", "status"),
    Index("ix_instruction_refs", "match_refs", postgresql_using="gin"),
)

# --- 0008 live updates (the triggers that fill it are in the migration) ---------------------------------------------

stream_event = Table(
    "stream_event",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("kind", Text, nullable=False),  # journal, event, notification, sync, step, workflow
    Column("case_id", Text),
    Column("tenant", Text),  # the case's owner, for the tenant boundary
    Column("location", Text),  # the case's location, for the warehouse lock
    Column("payload", JSONB, nullable=False),
    _ts("at", now=True),
)

# --- 0010 source credentials, encrypted (plan 6 A1; di/connectors/secrets.py) ---------------------------------------

source_secret = Table(
    "source_secret",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("kind", Text, primary_key=True, server_default="auth"),  # auth, webhook
    Column("version", Integer, primary_key=True),
    Column("ciphertext", LargeBinary, nullable=False),  # Fernet, key DI_SECRET_KEY
    Column("last4", Text, nullable=False),
    _ts("issued_at", now=True),
    _ts("expires_at"),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_by", Text, nullable=False),
    CheckConstraint("kind IN ('auth', 'webhook')", name="source_secret_kind_check"),
    Index("source_secret_one_active", "source_id", "kind", unique=True, postgresql_where=text("active")),
)

# --- 0011 per-source connection settings (plan 6 A2; di/connectors/connection.py) ----------------------------------

source_connection = Table(
    "source_connection",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("base_url", Text, nullable=False),
    Column("protocol", Text, nullable=False, server_default="rest"),
    Column("auth_kind", Text, nullable=False, server_default="builtin"),  # builtin, none, api_key, bearer, basic, oauth_cc
    Column("auth_params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),  # never the secret
    Column("paging", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("resources", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("updated_by", Text),  # NULL: the seeded default of a demo source
    _ts("updated_at", now=True),
)

# --- 0017 dated currency rates (plan 6 C4; di/workflow/steps/transform.py x_fx) --------------------------------------

fx_rate = Table(
    "fx_rate",
    metadata,
    Column("date", Date, primary_key=True),
    Column("currency", Text, primary_key=True),
    Column("usd_rate", Numeric(18, 6), nullable=False),  # units of the currency per USD
    CheckConstraint("usd_rate > 0", name="fx_rate_positive"),
)

# --- 0013 webhook events received, for dedupe (plan 6 A7; di/connectors/webhook.py) ---------------------------------

webhook_event = Table(
    "webhook_event",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("event_id", Text, primary_key=True),
    Column("event_type", Text),
    _ts("event_time"),
    _ts("received_at", now=True),
    Index("ix_webhook_event_received", "received_at"),
)

# --- 0015 failed records (plan 6 B1; di/canonical/failed.py) --------------------------------------------------------

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
    _ts("created_at", now=True),
    CheckConstraint("run_kind IN ('sync', 'workflow', 'import')", name="failed_record_run_kind_check"),
    CheckConstraint("status IN ('held', 'reprocessed', 'dropped')", name="failed_record_status_check"),
    Index("ix_failed_record_run", "run_kind", "run_id"),
    Index("ix_failed_record_source", "source_id", "status"),
)
