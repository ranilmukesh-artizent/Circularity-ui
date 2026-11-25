"""composition and composition_version (plan 9, P9-8.17): one approvable object made of the description's change set, the
mapping rows and the stage-agent settings, with maker-checker, versioned by snapshots.

`composition.status`: draft, submitted, sent_back, approved, published, discarded. `steps` holds, per step (describe,
mapping, agents, approve, publish), its state and the note a checker pinned to it. `composition_version` keeps one snapshot
per status change.

Revision ID: 0058
Revises: 0057
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS): `scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran it empty.
"""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS composition (
  id           bigserial   PRIMARY KEY,
  org_unit_id  text        NOT NULL,
  pack_key     text        NOT NULL,
  base_version text        NOT NULL,
  text         text        NOT NULL,
  reading      jsonb       NOT NULL DEFAULT '{}',
  change_set   jsonb       NOT NULL,
  steps        jsonb       NOT NULL DEFAULT '{}',
  status       text        NOT NULL,
  version      int         NOT NULL DEFAULT 1,
  created_by   text        NOT NULL,
  editors      text[]      NOT NULL DEFAULT '{}',
  submitted_by text,
  approved_by  text,
  published_by text,
  created_at   timestamptz DEFAULT now(),
  updated_at   timestamptz DEFAULT now(),
  CONSTRAINT composition_status CHECK (status IN ('draft','submitted','sent_back','approved','published','discarded'))
);
CREATE INDEX IF NOT EXISTS ix_composition_org_pack ON composition (org_unit_id, pack_key);
CREATE TABLE IF NOT EXISTS composition_version (
  composition_id bigint      NOT NULL,
  version        int         NOT NULL,
  snapshot       jsonb       NOT NULL,
  status         text        NOT NULL,
  "by"           text        NOT NULL,
  "at"           timestamptz DEFAULT now(),
  PRIMARY KEY (composition_id, version)
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS composition_version")
    op.execute("DROP TABLE IF EXISTS composition")
