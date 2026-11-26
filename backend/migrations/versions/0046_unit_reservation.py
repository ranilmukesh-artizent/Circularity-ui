"""unit_reservation: a refurbished unit held for one contract refresh swap (plan 9, P9-5.3, story CR-03)

A unit is held once: the partial unique index on (unit_id) where status is 'held'. The row is written when a person approves
the refresh (P9-5.5); matching only proposes. Idempotent (CREATE ... IF NOT EXISTS), as the other plan 9 migrations.

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-25
"""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS unit_reservation (
  unit_id     text NOT NULL,
  org_unit_id text NOT NULL REFERENCES org_unit(id),
  case_id     text NOT NULL,
  need_id     text NOT NULL,
  status      text NOT NULL CONSTRAINT unit_reservation_status CHECK (status IN ('held','released','consumed')),
  created_by  text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_unit_reservation_held ON unit_reservation (unit_id) WHERE status = 'held';
CREATE INDEX IF NOT EXISTS ix_unit_reservation_case ON unit_reservation (case_id);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS unit_reservation")
