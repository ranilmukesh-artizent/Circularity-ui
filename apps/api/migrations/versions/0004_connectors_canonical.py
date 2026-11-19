"""connectors and the canonical store (B9)

source_system   the connected systems (seeded from the demo's SOURCES) and their state
sync_run        one row per sync of one source: counts, outcome, trigger
sync_cursor     delta position per source and resource
fetch_log       every HTTP call a connector made (Audit › Fetch log)
raw_record      what each source returned, as returned (the landing zone; provenance points here)
provenance      every value every source gave for every canonical field
canonical       the chosen value per field, per model and key
conflict        two sources disagree on a field; names the authority, holds dependent routes

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "source_system",
        sa.Column("id", sa.Text(), primary_key=True),  # erp, proc, crm …
        sa.Column("vendor", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),  # live, paused, disconnected, failing, auth_expired, unavailable, manual
        sa.Column(
            "interval_min", sa.Integer(), nullable=False, server_default="0"
        ),  # 0 = event-driven (webhooks) + hourly safety sync
        sa.Column("authority", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("owner", sa.Text()),
        sa.Column("last_sync_at", TS),
        sa.Column("last_success_at", TS),
        sa.Column("completeness", sa.Numeric(5, 2)),  # % of expected canonical fields this source filled
        sa.Column("confidence", sa.Numeric(5, 2)),
        sa.Column("note", sa.Text()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "sync_run",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.Text(), sa.ForeignKey("source_system.id"), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),  # schedule, manual, webhook, initial
        sa.Column("status", sa.Text(), nullable=False),  # running, ok, partial, failed
        sa.Column("started_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TS),
        sa.Column("records_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("facts_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_sync_run_source", "sync_run", ["source_id", "id"])
    op.create_table(
        "sync_cursor",
        sa.Column("source_id", sa.Text(), primary_key=True),
        sa.Column("resource", sa.Text(), primary_key=True),
        sa.Column("cursor", sa.Text(), nullable=False),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "fetch_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.BigInteger()),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer()),
        sa.Column("records", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fetch_log_source", "fetch_log", ["source_id", "id"])
    op.create_table(
        "raw_record",
        sa.Column("source_id", sa.Text(), primary_key=True),
        sa.Column("resource", sa.Text(), primary_key=True),
        sa.Column("ext_id", sa.Text(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("request", sa.Text()),
        sa.Column("fetch_id", sa.BigInteger()),
        sa.Column("fetched_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "provenance",
        sa.Column("model", sa.Text(), primary_key=True),  # asset, condition, demand, intervention, market, route, …
        sa.Column("key", sa.Text(), primary_key=True),  # MTR-2041, SO-48102 …
        sa.Column("field", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB()),
        sa.Column("source_field", sa.Text()),  # e.g. EKPO-NETPR
        sa.Column("source_value", postgresql.JSONB()),  # as the source had it, e.g. "1002000.00 INR"
        sa.Column("transform", sa.Text()),  # e.g. "Currency at 83.5 (rate dated 2026-10-06)"
        sa.Column("resource", sa.Text()),
        sa.Column("ext_id", sa.Text()),
        sa.Column("confidence", sa.Numeric(5, 2)),
        sa.Column("fetched_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_provenance_source", "provenance", ["source_id"])
    op.create_table(
        "canonical",
        sa.Column("model", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "conflict",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("values", postgresql.JSONB(), nullable=False),  # {source_id: value}
        sa.Column("authority", sa.Text()),  # the source whose value counts
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),  # open, resolved, escalated
        sa.Column("opened_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", TS),
        sa.Column("closed_by", sa.Text()),
        sa.Column("note", sa.Text()),
    )
    op.create_index(
        "ux_conflict_open", "conflict", ["model", "key", "field"], unique=True, postgresql_where=sa.text("status = 'open'")
    )


def downgrade() -> None:
    for t in ("conflict", "canonical", "provenance", "raw_record", "fetch_log", "sync_cursor", "sync_run", "source_system"):
        op.drop_table(t)
