"""model_version (plan 8, MVP-12.2): the calibration models fitted on the confirmed outcomes.

One row per fitted model of a template: its calibration factors (`[{route, cls, factor}]`, di.services.engine.
calibration.fit), its status (a `candidate` until a different person promotes it; then `active`, and the active one
it replaces `retired`), who fitted and who promoted it, and its metrics (the mean absolute error of the active model
vs the candidate on the outcome rows). An active model calibrates the predictor of new intake cases only.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS model_version (
  id           text        PRIMARY KEY,
  template     text        NOT NULL,
  factors      jsonb       NOT NULL,
  status       text        NOT NULL
               CONSTRAINT model_version_status CHECK (status IN ('candidate','active','retired')),
  created_by   text        NOT NULL,
  approved_by  text        NULL,
  metrics      jsonb       NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_version")
