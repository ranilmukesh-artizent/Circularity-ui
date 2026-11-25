"""customer_overlay (plan 9, P9-1.3): a customer's changes to a pack, with their own approval.

One row per pack and org unit: `published` holds the operations in force (`ver` counts the approvals), `draft` the
operations being worked on while `status` is `draft` or `review`, with the pack version each was made against
(`base_version`, `draft_base_version`). `conflicts` and `notes` come from a rebase onto a newer pack version. Maker and
checker are kept for display; who made a draft is read from the journal when it is approved.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as 0017 is: `scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran
it empty.
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS customer_overlay (
  id                 bigserial   PRIMARY KEY,
  pack_key           text        NOT NULL,
  org_unit_id        text        NOT NULL REFERENCES org_unit(id),
  base_version       text        NOT NULL,
  draft              jsonb,
  draft_base_version text,
  published          jsonb       NOT NULL DEFAULT '[]',
  status             text        NOT NULL CONSTRAINT customer_overlay_status CHECK (status IN ('draft','review','pub')),
  ver                integer     NOT NULL DEFAULT 0,
  maker              text,
  checker            text,
  conflicts          jsonb       NOT NULL DEFAULT '[]',
  notes              jsonb       NOT NULL DEFAULT '[]',
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_customer_overlay_pack_org UNIQUE (pack_key, org_unit_id)
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS customer_overlay")
