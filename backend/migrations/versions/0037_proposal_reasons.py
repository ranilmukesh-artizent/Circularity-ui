"""agent_proposal.reasons (plan 9, P9-2.4; registry entry I-10): why the hold policy held a call for a person.

A JSON list of {reason, detail}, reason one of risk, value, confidence, taint, destructive, autonomy
(di.services.actions.hold). Proposals held before this step get an empty list; the Home inbox and the Agents page show
none for them.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

SQL = "ALTER TABLE agent_proposal ADD COLUMN IF NOT EXISTS reasons jsonb NOT NULL DEFAULT '[]'"


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("ALTER TABLE agent_proposal DROP COLUMN IF EXISTS reasons")
