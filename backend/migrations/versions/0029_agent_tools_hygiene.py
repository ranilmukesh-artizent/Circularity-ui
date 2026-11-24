"""Reserved for P9-0.4 (plan 9): Catalogue hygiene and credentials rotation forbidden.

Empty until that task fills it. Plan 9's writers run in parallel and merge in any order, so every migration from
0029 to 0061 exists, chained, from the start; a filled one is idempotent (IF NOT EXISTS), and
`scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran it empty.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-25
"""

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
