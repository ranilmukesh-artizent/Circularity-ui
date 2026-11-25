"""Device data tables (plan 9, P9-6.2): the trade-ins, price feed, launches, listings, bids, sales, disputes and
replacement demand of the device-recommerce flow.

`dvlab` lands device_tradein and device_dispute (P9-6.2); `dvmkt` lands the other six (P9-6.3). The registry's and the
lab's other facts go to the canonical store, not here. Synthetic data: an IMEI is a device identifier, no person is stored.

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as 0017 is: `scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran
it empty.
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

TABLES = (
    "device_tradein", "device_price_point", "device_launch", "device_listing", "device_bid", "device_sale",
    "device_dispute", "device_replacement_demand",
)  # fmt: skip


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS device_tradein (
  trade_in_id text        PRIMARY KEY,
  org_unit_id text,
  imei        text        NOT NULL,
  sku         jsonb       NOT NULL,
  quote       jsonb       NOT NULL,
  partner     text        NOT NULL,
  batch_id    text,
  bulk        boolean     NOT NULL,
  received_at timestamptz NOT NULL,
  payout      jsonb,
  case_id     text,
  source      text        NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_device_tradein_imei ON device_tradein (imei);
CREATE INDEX IF NOT EXISTS ix_device_tradein_batch ON device_tradein (batch_id);

CREATE TABLE IF NOT EXISTS device_price_point (
  sku_key  text          NOT NULL,
  grade    text          NOT NULL,
  week     date          NOT NULL,
  price    numeric(12,2) NOT NULL,
  currency text          NOT NULL,
  source   text          NOT NULL,
  PRIMARY KEY (sku_key, grade, week)
);

CREATE TABLE IF NOT EXISTS device_launch (
  model       text NOT NULL,
  successor   text NOT NULL,
  launched_on date NOT NULL,
  PRIMARY KEY (model, launched_on)
);

CREATE TABLE IF NOT EXISTS device_listing (
  listing_id  text          PRIMARY KEY,
  org_unit_id text,
  imei        text          NOT NULL,
  case_id     text,
  channel     text          NOT NULL,
  price       numeric(12,2) NOT NULL,
  listed_at   timestamptz   NOT NULL,
  offers      integer       NOT NULL,
  status      text          NOT NULL,
  updated_at  timestamptz   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_device_listing_channel_status ON device_listing (channel, status);

CREATE TABLE IF NOT EXISTS device_bid (
  bid_id      text          PRIMARY KEY,
  lot_ref     text          NOT NULL,
  buyer_code  text          NOT NULL,
  amount      numeric(12,2) NOT NULL,
  fees        numeric(12,2) NOT NULL,
  logistics   numeric(12,2) NOT NULL,
  received_at timestamptz   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_device_bid_lot ON device_bid (lot_ref);

CREATE TABLE IF NOT EXISTS device_sale (
  sale_id       text          PRIMARY KEY,
  listing_id    text,
  lot_ref       text,
  imeis         jsonb         NOT NULL,
  price         numeric(12,2) NOT NULL,
  fees          numeric(12,2) NOT NULL,
  buyer_returns numeric(12,2) NOT NULL,
  settled_at    timestamptz   NOT NULL,
  case_ids      jsonb         NOT NULL
);

CREATE TABLE IF NOT EXISTS device_dispute (
  id        text        PRIMARY KEY,
  imei      text        NOT NULL,
  partner   text        NOT NULL,
  reason    text        NOT NULL,
  opened_at timestamptz NOT NULL,
  outcome   text        NOT NULL
);

CREATE TABLE IF NOT EXISTS device_replacement_demand (
  id        text          PRIMARY KEY,
  sku_key   text          NOT NULL,
  grade_min text          NOT NULL,
  qty       integer       NOT NULL,
  unit_cost numeric(12,2) NOT NULL,
  needed_by date,
  reserved  jsonb         NOT NULL DEFAULT '[]'
);
"""
    )


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t}")
