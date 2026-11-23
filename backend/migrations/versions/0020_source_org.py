"""source_org (plan 8, MVP-1.4): a source system may belong to one org unit.

`source_system.org_unit_id` references org_unit(id); null means the source is shared by every org, which every demo
source is. A second source of a type (erp_2) may belong to another org than the first.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE source_system ADD COLUMN IF NOT EXISTS org_unit_id text NULL;
ALTER TABLE source_system DROP CONSTRAINT IF EXISTS source_system_org_unit_id_fkey;
ALTER TABLE source_system ADD CONSTRAINT source_system_org_unit_id_fkey
  FOREIGN KEY (org_unit_id) REFERENCES org_unit(id);
"""
    )


def downgrade() -> None:
    op.execute("ALTER TABLE source_system DROP COLUMN IF EXISTS org_unit_id")
