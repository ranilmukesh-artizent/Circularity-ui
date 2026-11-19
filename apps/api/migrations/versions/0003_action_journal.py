"""action journal and domain events (B8)

The journal is the demo's AF.journal: every action that changes state, with who did it, who prepared it (an agent),
the idempotency key and a reference to what it produced. It doubles as the audit trail of actions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_journal",
        sa.Column("seq", sa.BigInteger(), primary_key=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),  # account id, or "system"
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("preparer", sa.Text()),  # the agent that prepared it, if any
        sa.Column("run_id", sa.Text()),
        sa.Column("case_id", sa.Text()),
        sa.Column("idem_key", sa.Text()),
        sa.Column("output_ref", postgresql.JSONB()),
        sa.Column("undone", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_action_journal_case", "action_journal", ["case_id", "seq"])
    # one live entry per idempotency key; an undone entry frees its key, so the action can be taken again
    op.create_index(
        "ux_action_journal_idem",
        "action_journal",
        ["idem_key"],
        unique=True,
        postgresql_where=sa.text("NOT undone AND idem_key IS NOT NULL"),
    )
    op.create_table(
        "domain_event",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),  # action.<id>, or a type the action emits
        sa.Column("seq", sa.BigInteger(), sa.ForeignKey("action_journal.seq")),
        sa.Column("case_id", sa.Text()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_domain_event_id_case", "domain_event", ["case_id", "id"])


def downgrade() -> None:
    op.drop_table("domain_event")
    op.drop_table("action_journal")
