"""cases and their stage log (B11)

A case is stored as one JSON document in the demo's shape (facts, evidence, routes, approval, exec, outcome) with the
fields the queries need as columns. Every change of stage is logged with who changed it and the action behind it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_record",
        sa.Column("id", sa.Text(), primary_key=True),  # RT-1048
        sa.Column("owner", sa.Text(), nullable=False),  # tenant
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_case_record_owner", "case_record", ["owner"])
    op.create_table(
        "case_stage_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("case_id", sa.Text(), sa.ForeignKey("case_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_stage", sa.Text()),  # null when the case was opened
        sa.Column("to_stage", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.ForeignKey("action_journal.seq")),  # the action behind it, if any
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_case_stage_log_case", "case_stage_log", ["case_id", "id"])


def downgrade() -> None:
    op.drop_table("case_stage_log")
    op.drop_table("case_record")
