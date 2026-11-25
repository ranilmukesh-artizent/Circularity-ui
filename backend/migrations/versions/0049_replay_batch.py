"""replay_batch and replay_item (plan 9, P9-7.1; registry entry I-16; story X-06): imported history of past decisions.

A batch is one import (or the appends to it) for a pack and an org unit; each row is an item, `ok` or `held` with the one
reason it was held. Facts keep the time each was known, so a replay can use only what was known at the decision date.
Idempotent (IF NOT EXISTS), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-25
"""

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

BATCH = """
CREATE TABLE IF NOT EXISTS replay_batch (
  id          bigserial   PRIMARY KEY,
  pack        text        NOT NULL,
  org_unit_id text        NOT NULL REFERENCES org_unit(id),
  rows        integer     NOT NULL,
  held        integer     NOT NULL,
  period_from date,
  period_to   date,
  created_by  text        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
)
"""

ITEM = """
CREATE TABLE IF NOT EXISTS replay_item (
  batch_id       bigint      NOT NULL REFERENCES replay_batch(id) ON DELETE CASCADE,
  n              integer     NOT NULL,
  item_id        text        NOT NULL,
  decided_at     timestamptz,
  cls            text,
  market         text,
  actual_route   text,
  realised_value numeric,
  costs          jsonb       NOT NULL DEFAULT '{}',
  facts          jsonb       NOT NULL DEFAULT '{}',
  status         text        NOT NULL CONSTRAINT replay_item_status CHECK (status IN ('ok','held')),
  held_reason    text,
  PRIMARY KEY (batch_id, n)
)
"""

INDEX = "CREATE INDEX IF NOT EXISTS ix_replay_item_status ON replay_item (batch_id, status)"


def upgrade() -> None:
    op.execute(BATCH)
    op.execute(ITEM)
    op.execute(INDEX)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS replay_item")
    op.execute("DROP TABLE IF EXISTS replay_batch")
