"""replay_run (plan 9, P9-7.2; registry entry I-16; story X-06): one as-of replay of a history batch under a flow.

A run is queued by `replay.run`, taken by the worker job of the same name, and ends `done` with its report (JSON) or
`failed` with the error. `flow_ver` is `draft` or the published version replayed; `dver` is the draft's version when it was
a draft (the publish gate of P9-7.3 reads the newest done run of the draft).
Idempotent (IF NOT EXISTS), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-25
"""

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

RUN = """
CREATE TABLE IF NOT EXISTS replay_run (
  id          bigserial   PRIMARY KEY,
  batch_id    bigint      NOT NULL REFERENCES replay_batch(id),
  flow_id     bigint      NOT NULL REFERENCES decision_flow(id),
  flow_ver    text        NOT NULL,
  dver        integer,
  status      text        NOT NULL CONSTRAINT replay_run_status CHECK (status IN ('queued','running','done','failed')),
  report      jsonb,
  error       text,
  created_by  text        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
)
"""

INDEX = "CREATE INDEX IF NOT EXISTS ix_replay_run_flow ON replay_run (flow_id, dver, status)"


def upgrade() -> None:
    op.execute(RUN)
    op.execute(INDEX)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS replay_run")
