"""Service desk data (plan 9, P9-4.1): closed repairs, upgrade offers, refurbished stock, service tickets.

The tables the extra sources `rephist` (Oracle Depot Repair's repair history) and `sdesk` (ServiceNow customer service
cases and upgrade offers) fill, and two dated currency rates for the markets that do not trade in USD or EUR. Idempotent
(IF NOT EXISTS, ON CONFLICT DO NOTHING), as 0017 is: `scripts/dev/migrate-reapply.sh 0028` applies it on a database that
already ran it empty.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-25
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS repair_history (
  id              text          PRIMARY KEY,
  org_unit_id     text,
  serial          text,
  model_class     text,
  age_months      integer,
  fault_code      text,
  market          text,
  parts           jsonb         NOT NULL DEFAULT '[]'::jsonb,
  labour_hours    numeric(8,2),
  test_fee        boolean,
  turnaround_days integer,
  actual_cost     numeric(12,2),
  currency        text,
  closed_on       date          NOT NULL,
  source          text
);
CREATE INDEX IF NOT EXISTS ix_repair_history_key ON repair_history (model_class, fault_code, closed_on);

CREATE TABLE IF NOT EXISTS upgrade_offer (
  id            text          PRIMARY KEY,
  org_unit_id   text,
  account       text,
  market        text,
  model_class   text,
  offered_on    date          NOT NULL,
  credit_pct    numeric(5,4),
  credit_amount numeric(12,2),
  currency      text,
  accepted      boolean,
  source        text
);
CREATE INDEX IF NOT EXISTS ix_upgrade_offer_account ON upgrade_offer (account, offered_on);

CREATE TABLE IF NOT EXISTS refurb_unit (
  serial        text          PRIMARY KEY,
  org_unit_id   text,
  model_class   text,
  grade         text,
  market        text,
  released_on   date,
  reserved_case text
);

CREATE TABLE IF NOT EXISTS service_ticket (
  number          text          PRIMARY KEY,
  org_unit_id     text,
  account         text,
  market          text,
  site            text,
  batch_id        text,
  lines           jsonb         NOT NULL DEFAULT '[]'::jsonb,
  requester_role  text,
  loaner_promised boolean       NOT NULL DEFAULT false,
  opened_at       timestamptz   NOT NULL,
  case_id         text,
  source          text
);

INSERT INTO fx_rate (date, currency, usd_rate) VALUES
  ('2026-10-06', 'GBP', 0.79),
  ('2026-10-06', 'AUD', 1.52)
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute(
        """
DELETE FROM fx_rate WHERE date = '2026-10-06' AND currency IN ('GBP', 'AUD');
DROP TABLE IF EXISTS service_ticket;
DROP TABLE IF EXISTS refurb_unit;
DROP TABLE IF EXISTS upgrade_offer;
DROP TABLE IF EXISTS repair_history;
"""
    )
