"""plan 6 A6: a failing source is retried sooner than its interval

`fail_streak` counts the source's failed syncs in a row; `next_retry_at` is when the next try is due
(last sync + min(2**fail_streak minutes, the interval)). A successful sync resets both (di/connectors/sync.py).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE source_system ADD COLUMN IF NOT EXISTS fail_streak integer NOT NULL DEFAULT 0;
ALTER TABLE source_system ADD COLUMN IF NOT EXISTS next_retry_at timestamptz;
"""
    )


def downgrade() -> None:
    op.execute(
        """
ALTER TABLE source_system DROP COLUMN IF EXISTS next_retry_at;
ALTER TABLE source_system DROP COLUMN IF EXISTS fail_streak;
"""
    )
