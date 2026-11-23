"""decision_flow (plan 8, MVP-3.1): reserved, filled by that task.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
