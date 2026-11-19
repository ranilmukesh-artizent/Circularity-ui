"""workspace state: the demo's in-memory lists as ordered collections (B12)

The demo keeps its event stream, notifications, requests, comments, saved scenarios, directory users and similar
lists in browser memory. Each becomes a collection of JSON items in the demo's shape, in insertion order, seeded once
from the demo's starting values (state_seed records which collections are seeded, so an emptied one stays empty).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "state_item",
        sa.Column("collection", sa.Text(), primary_key=True),
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),  # insertion order
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_state_item_order", "state_item", ["collection", "seq"])
    op.create_table(
        "state_seed",
        sa.Column("collection", sa.Text(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("state_seed")
    op.drop_table("state_item")
