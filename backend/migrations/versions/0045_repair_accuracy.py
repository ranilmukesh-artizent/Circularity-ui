"""repair_accuracy (plan 9, P9-4.5, story SD-08): held-out accuracy of the repair estimate, per org unit, tool class and day.

Written by `serviceDesk.computeAccuracy` (once a simulated day from the worker's periodic step); the estimate reads the
newest row of a family to decide whether it may be priced without a technician. Idempotent (IF NOT EXISTS), as every plan 9
migration is: bash scripts/dev/migrate-reapply.sh 0028

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-25
"""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS repair_accuracy (
  id           bigserial     PRIMARY KEY,
  org_unit_id  text,
  as_of        date          NOT NULL,
  model_class  text          NOT NULL,
  n            integer       NOT NULL,
  mae          numeric(12,2) NOT NULL,
  mae_share    numeric(6,4)  NOT NULL,
  coverage     numeric(6,4)  NOT NULL,
  auto_share   numeric(6,4)  NOT NULL,
  instant      boolean       NOT NULL,
  computed_at  timestamptz   NOT NULL DEFAULT now()
)
"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_repair_accuracy_class ON repair_accuracy (model_class, as_of DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS repair_accuracy")
