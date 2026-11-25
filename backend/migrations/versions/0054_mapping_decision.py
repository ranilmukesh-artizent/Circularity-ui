"""mapping_decision (plan 9, P9-8.4): the person's choice for each suggested field mapping.

One row per choice (accepted, replaced, accepted_with_rule, not_needed, asked_owner); a newer choice for the same source
field sets `superseded` on the older one. Idempotent (IF NOT EXISTS); `scripts/dev/migrate-reapply.sh 0028` applies it on
a database that ran the empty placeholder.

Revision ID: 0054
Revises: 0053
Create Date: 2026-11-25
"""

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS mapping_decision (
  id          bigserial   PRIMARY KEY,
  source_id   text        NOT NULL,
  resource    text,
  src         text        NOT NULL,
  decision    text        NOT NULL CONSTRAINT mapping_decision_decision
              CHECK (decision IN ('accepted','replaced','accepted_with_rule','not_needed','asked_owner')),
  target      text,
  rule        text,
  confidence  real,
  reason      text,
  proposed_by text,
  owner       text,
  answer      jsonb,
  decided_by  text        NOT NULL,
  decided_at  timestamptz DEFAULT now(),
  superseded  boolean     NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_mapping_decision_source_src ON mapping_decision (source_id, src);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mapping_decision")
