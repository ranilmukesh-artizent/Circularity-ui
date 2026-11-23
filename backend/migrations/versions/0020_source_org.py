"""source_org (plan 8, MVP-1.4): reserved, filled by that task.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
