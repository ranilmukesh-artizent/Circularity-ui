"""Model kind (plan 9, P9-3.10): `model_version.kind` says what a model predicts.

`calibration` is every model before this one (price calibration, stage calibration); `rated_life` is the remaining-life
Weibull model fitted on teardown verdicts. The other values are reserved for the price, repair cost, demand and take-up
models of later tasks. Idempotent: it runs on a database that already ran this file empty.

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-25
"""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE model_version ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'calibration'")
    op.execute("ALTER TABLE model_version DROP CONSTRAINT IF EXISTS model_version_kind")
    op.execute(
        "ALTER TABLE model_version ADD CONSTRAINT model_version_kind "
        "CHECK (kind IN ('calibration','rated_life','price','repair_cost','demand','take_up'))"
    )
    op.execute("CREATE INDEX IF NOT EXISTS model_version_template_kind_status ON model_version (template, kind, status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS model_version_template_kind_status")
    op.execute("ALTER TABLE model_version DROP CONSTRAINT IF EXISTS model_version_kind")
    op.execute("ALTER TABLE model_version DROP COLUMN IF EXISTS kind")
