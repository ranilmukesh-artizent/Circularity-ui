"""P9-13.8 (plan 9): the model registry fields: kind, pack, training time and window, quality, drift, cadence.

Idempotent: `kind` exists since 0042, and every other column is added with IF NOT EXISTS. `pack` is backfilled from `template`.

Revision ID: 0059
Revises: 0058
Create Date: 2026-11-26
"""

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

BACKFILL = "UPDATE model_version SET pack = template WHERE pack IS NULL"


def upgrade() -> None:
    op.execute("ALTER TABLE model_version ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'calibration'")
    for col in (
        "pack text",
        "trained_at timestamptz",
        "data_window jsonb",
        "quality jsonb",
        "drift jsonb",
        "drift_status text",
        "cadence text",
        "next_due timestamptz",
    ):
        op.execute(f"ALTER TABLE model_version ADD COLUMN IF NOT EXISTS {col}")
    op.execute("ALTER TABLE model_version DROP CONSTRAINT IF EXISTS model_version_drift_status")
    op.execute(
        "ALTER TABLE model_version ADD CONSTRAINT model_version_drift_status "
        "CHECK (drift_status IS NULL OR drift_status IN ('ok','watch','alert'))"
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute("ALTER TABLE model_version DROP CONSTRAINT IF EXISTS model_version_drift_status")
    for col in ("next_due", "cadence", "drift_status", "drift", "quality", "data_window", "trained_at", "pack"):
        op.execute(f"ALTER TABLE model_version DROP COLUMN IF EXISTS {col}")
