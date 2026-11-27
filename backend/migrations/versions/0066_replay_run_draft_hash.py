"""replay_run.draft_hash (review P9-7.9 F1): the hash of the draft graph a replay of the draft ran on, so a canary starts only
on the exact draft that was replayed (saveDraft reuses the draft's version number). Idempotent (IF NOT EXISTS).

Revision ID: 0066
Revises: 0065
Create Date: 2026-11-28
"""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE replay_run ADD COLUMN IF NOT EXISTS draft_hash text")


def downgrade() -> None:
    op.execute("ALTER TABLE replay_run DROP COLUMN IF EXISTS draft_hash")
