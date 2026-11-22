"""instructions: one row per execution step sent to an enterprise system (B13b)

An approved decision's steps go out one at a time: approval queues the first, each acknowledgement the next. A row
keeps what was sent and to which system, the idempotency key it went with, the references the system's events carry
back (to match an event to its instruction), the system's own document reference, and the send attempts.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruction",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("approval_ref", sa.Text(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),  # a source id (oms, repair, tms, wms, erp) or the step's system label
        sa.Column("idem_key", sa.Text(), nullable=False, unique=True),
        # the values the system's events carry that identify this instruction (our key, our document number ...)
        sa.Column("match_refs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("request", postgresql.JSONB()),  # what was sent, call by call
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),  # what later steps need from it
        sa.Column("doc_ref", sa.Text()),  # the system's own document reference
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),  # queued | sent | acknowledged | failed
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("waiting_for", sa.Text()),  # set while a step cannot be sent yet (e.g. delivery waits for the POD)
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("due_at", sa.DateTime(timezone=True)),  # simulated acknowledgement time (simulated clock)
        sa.Column("queued_at", sa.DateTime(timezone=True)),  # these three on the workspace clock (di/core/clock.py)
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("approval_ref", "step", name="uq_instruction_step"),
    )
    op.create_index("ix_instruction_case", "instruction", ["case_id", "step"])
    op.create_index("ix_instruction_status", "instruction", ["status"])
    op.create_index("ix_instruction_refs", "instruction", ["match_refs"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_table("instruction")
