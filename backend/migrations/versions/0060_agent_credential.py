"""Reserved for P9-13.9 (plan 9): Per-agent credentials with client credentials.

Empty until that task fills it. Plan 9's writers run in parallel and merge in any order, so every migration from
0029 to 0061 exists, chained, from the start; a filled one is idempotent (IF NOT EXISTS), and
`scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran it empty.

Revision ID: 0060
Revises: 0059
Create Date: 2026-11-25
"""

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
