"""plan 6 B1 failed records (di/canonical/failed.py)

One row per piece of data that could not be stored: a fact that does not fit its canonical model (sync), a row a
workflow step rejected (workflow) or an import row that failed its checks (import). It keeps the value, the reason
and the record it came from, so a person can fix and reprocess it, or drop it.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS failed_record (
  id          bigserial   PRIMARY KEY,
  run_kind    text        NOT NULL,
  run_id      text,
  source_id   text,
  step        text,
  resource    text,
  ext_id      text,
  field       text,
  rule        text,
  value       jsonb,
  reason      text        NOT NULL,
  payload     jsonb,
  status      text        NOT NULL DEFAULT 'held',
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT failed_record_run_kind_check CHECK (run_kind IN ('sync', 'workflow', 'import')),
  CONSTRAINT failed_record_status_check CHECK (status IN ('held', 'reprocessed', 'dropped'))
);
CREATE INDEX IF NOT EXISTS ix_failed_record_run ON failed_record (run_kind, run_id);
CREATE INDEX IF NOT EXISTS ix_failed_record_source ON failed_record (source_id, status);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS failed_record")
