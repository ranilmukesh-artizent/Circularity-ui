"""market_table (plan 9, P9-4.2; registry entry I-15; story SD-03): per-market rate cards and decision tables.

One row per version of a table: a rate card (values per rate) or a decision table (a JDM graph), for a pack, a flow and a
market, owned by an org unit or shared (`org_unit_id` null). A version is a draft, then submitted, then approved by a
different person (maker-checker) or rejected; an approved version is in force from `valid_from` to `valid_to`. The pack's
starting tables are inserted as approved version 1 by `market_tables.ensure_seeded`, not here. Idempotent (IF NOT EXISTS),
as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-25
"""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

TABLE = """
CREATE TABLE IF NOT EXISTS market_table (
  id           bigserial   PRIMARY KEY,
  org_unit_id  text,
  pack         text        NOT NULL,
  flow         text        NOT NULL,
  market       text        NOT NULL,
  name         text        NOT NULL,
  kind         text        NOT NULL CONSTRAINT market_table_kind CHECK (kind IN ('rate_card','decision_table')),
  version      integer     NOT NULL,
  status       text        NOT NULL
               CONSTRAINT market_table_status CHECK (status IN ('draft','submitted','approved','rejected','retired')),
  valid_from   date        NOT NULL,
  valid_to     date,
  currency     text,
  body         jsonb       NOT NULL,
  created_by   text        NOT NULL,
  submitted_by text,
  approved_by  text,
  reason       text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT market_table_version UNIQUE (org_unit_id, pack, flow, market, name, version)
)
"""
INDEX = "CREATE INDEX IF NOT EXISTS ix_market_table_lookup ON market_table (pack, flow, market, name, status, valid_from)"
SHARED = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_market_table_shared ON market_table (pack, flow, market, name, version) "
    "WHERE org_unit_id IS NULL"
)  # NULLs are distinct in a unique constraint: this keeps the shared versions unique too


def upgrade() -> None:
    op.execute(TABLE)
    op.execute(INDEX)
    op.execute(SHARED)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS market_table")
