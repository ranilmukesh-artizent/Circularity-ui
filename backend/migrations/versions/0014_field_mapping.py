"""plan 6 A4 versioned field mappings (di/connectors/mapping.py)

One row per saved version of a source's field mapping. `rows` is the mapping a sync applies: a list of
{src, model, field, rule, resource?} (di.connectors.mapping.MapRow) plus the row as the Data Mapping tab shows it
(`show`: source field, sample, canonical field, normalised, rule text). A source without a row runs its adapter's
own mapping unchanged; Revert writes a new version equal to an older one, so versions only grow.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS field_mapping (
  source_id   text        NOT NULL,
  version     integer     NOT NULL,
  rows        jsonb       NOT NULL DEFAULT '[]'::jsonb,
  note        text,
  created_by  text        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, version)
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS field_mapping")
