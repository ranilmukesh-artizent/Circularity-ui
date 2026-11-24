"""tenant_grant: an end and a revocation (plan 8 UI gaps, agent A).

A grant may end (`expires_at`, chosen by the person who approves the request; NULL: no end) and Admin, or the Approver
with the tenantAccess delegation, may revoke it (`revoked_at`, `revoked_by`, `revoke_note`). Only a live grant counts:
not revoked and not past its end (di.core.auth.load_context). Approving a new request for the same tenant makes the
row live again. Existing rows stay live without an end, so the seeded state is unchanged.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-24

Idempotent, as every migration from 0018 on (ADD COLUMN IF NOT EXISTS).
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE tenant_grant ADD COLUMN IF NOT EXISTS expires_at  timestamptz NULL;
ALTER TABLE tenant_grant ADD COLUMN IF NOT EXISTS revoked_at  timestamptz NULL;
ALTER TABLE tenant_grant ADD COLUMN IF NOT EXISTS revoked_by  text        NULL;
ALTER TABLE tenant_grant ADD COLUMN IF NOT EXISTS revoke_note text        NULL;
"""
    )


def downgrade() -> None:
    op.execute(
        """
ALTER TABLE tenant_grant DROP COLUMN IF EXISTS revoke_note;
ALTER TABLE tenant_grant DROP COLUMN IF EXISTS revoked_by;
ALTER TABLE tenant_grant DROP COLUMN IF EXISTS revoked_at;
ALTER TABLE tenant_grant DROP COLUMN IF EXISTS expires_at;
"""
    )
