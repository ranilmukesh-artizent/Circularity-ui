"""Wholesale lots of received devices (plan 9, P9-6.11): `device_lot` and `device_lot_member`.

A lot groups the devices routed to the wholesale channel by model and grade, within the lot cap; it is posted to the device
market, collects bids, and is proposed to its best approved bid and approved by a person or the standing policy. `status` is
draft (not posted yet), bidding, proposed, approved, rejected or sold. Plan 9's writers run in parallel and merge in any order,
so every migration from 0029 to 0061 exists, chained, from the start; this one is idempotent (IF NOT EXISTS), and
`scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran it empty.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-25
"""

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS device_lot (
  id          text          PRIMARY KEY,
  org_unit_id text,
  lot_ref     text          NOT NULL UNIQUE,
  model       text          NOT NULL,
  grade       text          NOT NULL,
  units       integer       NOT NULL,
  status      text          NOT NULL,
  best_bid_id text,
  value_usd   numeric(12,2),
  created_by  text          NOT NULL,
  proposed_by text,
  approved_by text,
  reason      text,
  created_at  timestamptz   NOT NULL DEFAULT now(),
  CONSTRAINT device_lot_status CHECK (status IN ('draft','bidding','proposed','approved','rejected','sold'))
);
CREATE INDEX IF NOT EXISTS ix_device_lot_org_status ON device_lot (org_unit_id, status);

CREATE TABLE IF NOT EXISTS device_lot_member (
  lot_id  text NOT NULL,
  case_id text NOT NULL,
  PRIMARY KEY (lot_id, case_id)
);
CREATE INDEX IF NOT EXISTS ix_device_lot_member_case ON device_lot_member (case_id);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS device_lot_member")
    op.execute("DROP TABLE IF EXISTS device_lot")
