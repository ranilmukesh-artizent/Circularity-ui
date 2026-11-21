"""dated currency rates for the Convert currency step (plan 6, task C4)

`fx_rate` holds one rate per date and currency: how many units of the currency one USD buys. The x_fx step converts
a record's amount at the newest rate dated on or before the record's date (or the run's). Seeded with the demo's
fixed rates (di.connectors.generic.to_usd: 83.5 INR/USD, 0.92 EUR/USD, dated 2026-10-06), so numbers do not change.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS fx_rate (
  date      date          NOT NULL,
  currency  text          NOT NULL,
  usd_rate  numeric(18,6) NOT NULL CONSTRAINT fx_rate_positive CHECK (usd_rate > 0),
  PRIMARY KEY (date, currency)
);
INSERT INTO fx_rate (date, currency, usd_rate) VALUES
  ('2026-10-06', 'USD', 1),
  ('2026-10-06', 'INR', 83.5),
  ('2026-10-06', 'EUR', 0.92)
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fx_rate")
