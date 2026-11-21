"""plan 6 C4 dated currency rates (reserved; filled by that task)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op  # noqa: F401 - used once the task fills this migration

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
