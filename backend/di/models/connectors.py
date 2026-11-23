"""Source systems, sync runs and cursors, the fetch log, raw records, encrypted credentials, versioned field mappings,
connection settings and received webhooks (migrations 0004, 0010, 0011, 0013, 0014)."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from di.models.base import metadata, ts

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
    ts("last_sync_at"),
    ts("last_success_at"),
    Column("completeness", Numeric(5, 2)),
    Column("confidence", Numeric(5, 2)),
    Column("note", Text),
    ts("updated_at", now=True),
    # 0012 (plan 6 A6): failed syncs in a row, and when the next try is due (min(2**streak minutes, interval))
    Column("fail_streak", Integer, nullable=False, server_default="0"),
    ts("next_retry_at"),
    # 0020 (plan 8 MVP-1.4): the org unit the source belongs to; null = shared by every org (every demo source)
    Column("org_unit_id", Text, ForeignKey("org_unit.id")),
)


sync_run = Table(
    "sync_run",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("source_id", Text, ForeignKey("source_system.id"), nullable=False),
    Column("trigger", Text, nullable=False),  # schedule, manual, webhook, initial
    Column("status", Text, nullable=False),  # running, ok, partial, failed
    ts("started_at", now=True),
    ts("finished_at"),
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
    ts("updated_at", now=True),
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
    ts("at", now=True),
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
    ts("fetched_at", now=True),
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
    ts("issued_at", now=True),
    ts("expires_at"),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_by", Text, nullable=False),
    CheckConstraint("kind IN ('auth', 'webhook')", name="source_secret_kind_check"),
    Index("source_secret_one_active", "source_id", "kind", unique=True, postgresql_where=text("active")),
)


# --- 0014 versioned field mappings (plan 6 A4; di/connectors/mapping.py) --------------------------------------------

field_mapping = Table(
    "field_mapping",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("rows", JSONB, nullable=False, server_default=text("'[]'::jsonb")),  # MapRow dicts plus the row as shown
    Column("note", Text),
    Column("created_by", Text, nullable=False),
    ts("created_at", now=True),
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
    ts("updated_at", now=True),
)


# --- 0013 webhook events received, for dedupe (plan 6 A7; di/connectors/webhook.py) ---------------------------------

webhook_event = Table(
    "webhook_event",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("event_id", Text, primary_key=True),
    Column("event_type", Text),
    ts("event_time"),
    ts("received_at", now=True),
    Index("ix_webhook_event_received", "received_at"),
)
