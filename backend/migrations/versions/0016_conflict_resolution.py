"""plan 6 B2 conflicts that stay resolved (di/services/canonical/store.py, di/services/actions/fabric_records.py)

- conflict.values_hash: the fingerprint of the differing values ({source: value}) a conflict was opened or resolved
  on. The canonical store does not reopen a conflict a person resolved while the sources keep sending those values.
- An escalated conflict is now stored as status 'escalated' (it was kept 'open' with the escalation beside it). It is
  still active: the one-active-conflict-per-field index covers 'open' and 'escalated', so a sync updates it instead of
  opening a second one.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE conflict ADD COLUMN IF NOT EXISTS values_hash text;
DROP INDEX IF EXISTS ux_conflict_open;
CREATE UNIQUE INDEX IF NOT EXISTS ux_conflict_open ON conflict (model, key, field) WHERE status IN ('open', 'escalated');
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP INDEX IF EXISTS ux_conflict_open;
UPDATE conflict SET status = 'open' WHERE status = 'escalated';
CREATE UNIQUE INDEX IF NOT EXISTS ux_conflict_open ON conflict (model, key, field) WHERE status = 'open';
ALTER TABLE conflict DROP COLUMN IF EXISTS values_hash;
"""
    )
