"""decision_flow.returned: a sent-back flow change pinned to a step (plan 9, P9-0.12)

`returned` holds {reason, node_id, by, at} from the last flow.reject (node_id null for the whole flow); flow.submit
clears it. Idempotent (ADD COLUMN IF NOT EXISTS): plan 9's writers run in parallel and every migration from 0029 to
0061 exists, chained, from the start; `scripts/dev/migrate-reapply.sh 0028` applies it on a database that ran it empty.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-25
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE decision_flow ADD COLUMN IF NOT EXISTS returned jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE decision_flow DROP COLUMN IF EXISTS returned")
