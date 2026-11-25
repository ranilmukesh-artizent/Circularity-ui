"""agent_run_message (plan 9, P9-2.2; registry entry I-8): the model messages of an LLM agent run, one row per turn.

`n` numbers the turns of a run from 1; `messages` holds the Pydantic AI messages that turn added (JSON mode), so
concatenating the rows in `n` order gives the run's whole message history. A crash repeats at most one model call.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS agent_run_message (
  run_id   text         NOT NULL REFERENCES agent_run(id) ON DELETE CASCADE,
  n        integer      NOT NULL,
  messages jsonb        NOT NULL,
  model    text         NULL,
  at       timestamptz  NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, n)
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_run_message")
