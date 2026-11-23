"""agent_proposal (plan 8, MVP-11.4): a write an agent prepared that holds for a person.

An agent registered with autonomy `propose` that calls an action which changes state does not run it: the pipeline
stores the call here (`pending`) and answers `{held: id}`. A person with the action's own permission accepts it
(the action runs as that person, prepared by the agent) or rejects it.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS agent_proposal (
  id          bigserial   PRIMARY KEY,
  agent       text        NOT NULL,
  action      text        NOT NULL,
  input       jsonb       NOT NULL DEFAULT '{}',
  case_id     text        NULL,
  run_id      text        NULL,
  status      text        NOT NULL DEFAULT 'pending'
              CONSTRAINT agent_proposal_status CHECK (status IN ('pending','accepted','rejected','expired')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  decided_by  text        NULL,
  decided_at  timestamptz NULL,
  result      jsonb       NULL
);
CREATE INDEX IF NOT EXISTS ix_agent_proposal_status ON agent_proposal (status, created_at);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_proposal")
