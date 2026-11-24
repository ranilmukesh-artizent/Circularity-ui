"""agent_proposal.requested_by (audit F3a, docs/agents/audits/2026-11-24-plan-08): the person an agent acted for.

An agent acts as the signed-in person (MCP: the bearer token's account; an agent run: the account that started it).
That person does not accept the proposal their own agent call created; another person with the held action's
permission does (maker-checker). NULL for the proposals stored before this column.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-24
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_proposal ADD COLUMN IF NOT EXISTS requested_by text NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_proposal DROP COLUMN IF EXISTS requested_by")
