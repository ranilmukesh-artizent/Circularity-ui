"""agent_run (plan 8, MVP-11.5): an agent's run of a playbook, and the calls it made.

`agent_run` is the run (status running, waiting, done, failed or stopped; `step` the playbook's next step; `state`
what the steps learnt, the account it acts as, and what it waits for). `agent_run_step` keeps each call, numbered
from 1 per run, with its input and the pipeline's answer.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS agent_run (
  id          text        PRIMARY KEY,
  agent       text        NOT NULL,
  playbook    text        NOT NULL,
  case_id     text        NULL,
  status      text        NOT NULL DEFAULT 'running'
              CONSTRAINT agent_run_status CHECK (status IN ('running','waiting','done','failed','stopped')),
  step        integer     NOT NULL DEFAULT 0,
  state       jsonb       NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_run_case ON agent_run (case_id, status);
CREATE TABLE IF NOT EXISTS agent_run_step (
  run_id      text        NOT NULL REFERENCES agent_run(id) ON DELETE CASCADE,
  n           integer     NOT NULL,
  tool        text        NOT NULL,
  input       jsonb       NOT NULL DEFAULT '{}',
  output      jsonb       NULL,
  at          timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, n)
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_run_step")
    op.execute("DROP TABLE IF EXISTS agent_run")
