"""replay_demand (plan 9, P9-7.5; registry entry I-16; story X-06): the demand windows a replay plans against.

One row per line of a demand file ("Demand at the time", A section 3.1): a renewal, requisition, bid or repair slot window
(`route`, `opens_at` to `closes_at`, `value`, `capacity` units), ok or held with its reason, like `replay_item`. A replay of
a pack with a queue planner offers a day the rows open on it (opens_at <= day < closes_at) that no earlier day filled.
Idempotent (IF NOT EXISTS), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028

Revision ID: 0052
Revises: 0051
Create Date: 2026-11-25
"""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

DEMAND = """
CREATE TABLE IF NOT EXISTS replay_demand (
  batch_id    bigint  NOT NULL REFERENCES replay_batch(id) ON DELETE CASCADE,
  n           integer NOT NULL,
  demand_id   text    NOT NULL,
  route       text,
  opens_at    date,
  closes_at   date,
  value       numeric,
  capacity    integer,
  status      text    NOT NULL CONSTRAINT replay_demand_status CHECK (status IN ('ok','held')),
  held_reason text,
  PRIMARY KEY (batch_id, n)
)
"""

INDEX = "CREATE INDEX IF NOT EXISTS ix_replay_demand_status ON replay_demand (batch_id, status)"


def upgrade() -> None:
    op.execute(DEMAND)
    op.execute(INDEX)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS replay_demand")
