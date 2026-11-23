"""job_queue (plan 2, task 1): priorities, delayed runs, dead letters, stale-lock recovery, instant wake-up.

The `job` table (0001) gains:
- `priority` (lower runs first, default 100), `max_attempts` (default 5; then `dead`, kept for a retry),
  `heartbeat_at` (a running job's last sign of life; the reaper requeues one that went quiet), `dedupe_key` (one
  queued or running job per key: partial unique index `ux_job_dedupe`) and `history` (the errors of past attempts);
- statuses `dead` (out of attempts) and `cancelled`;
- index `ix_job_claim` (status, priority, run_after, id) in the order the worker claims;
- trigger `job_notify`: a job that is queued (inserted, or set back to queued) sends `NOTIFY di_jobs, '<kind>'`, so a
  waiting worker wakes at once (polling stays the fallback).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE job ADD COLUMN IF NOT EXISTS priority integer NOT NULL DEFAULT 100;
ALTER TABLE job ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 5;
ALTER TABLE job ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
ALTER TABLE job ADD COLUMN IF NOT EXISTS dedupe_key text;
ALTER TABLE job ADD COLUMN IF NOT EXISTS history jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE job DROP CONSTRAINT IF EXISTS ck_job_status;
ALTER TABLE job ADD CONSTRAINT ck_job_status
  CHECK (status IN ('queued','running','done','failed','dead','cancelled'));
CREATE UNIQUE INDEX IF NOT EXISTS ux_job_dedupe ON job (dedupe_key) WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS ix_job_claim ON job (status, priority, run_after, id);
CREATE OR REPLACE FUNCTION job_notify() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('di_jobs', NEW.kind);
  RETURN NULL;
END
$$;
DROP TRIGGER IF EXISTS job_notify ON job;
CREATE TRIGGER job_notify AFTER INSERT OR UPDATE OF status ON job
  FOR EACH ROW WHEN (NEW.status = 'queued') EXECUTE FUNCTION job_notify();
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TRIGGER IF EXISTS job_notify ON job;
DROP FUNCTION IF EXISTS job_notify();
DROP INDEX IF EXISTS ix_job_claim;
DROP INDEX IF EXISTS ux_job_dedupe;
ALTER TABLE job DROP CONSTRAINT IF EXISTS ck_job_status;
UPDATE job SET status = 'failed' WHERE status IN ('dead','cancelled');
ALTER TABLE job ADD CONSTRAINT ck_job_status CHECK (status IN ('queued','running','done','failed'));
ALTER TABLE job DROP COLUMN IF EXISTS history;
ALTER TABLE job DROP COLUMN IF EXISTS dedupe_key;
ALTER TABLE job DROP COLUMN IF EXISTS heartbeat_at;
ALTER TABLE job DROP COLUMN IF EXISTS max_attempts;
ALTER TABLE job DROP COLUMN IF EXISTS priority;
"""
    )
