"""pack_version (plan 9, P9-1.6): a pack as a versioned, approvable object.

One row per pack key, version and org unit (a null org unit is a pack for every org): the pack document (`doc`), its
status (draft, review, pub, retired), who made and who approved it, the impact of publishing it on the open cases and
the sample queue (`impact`: changed, total, dv), and when it was published. The pack files stay the base: the newest
published version of a key, for the org or its nearest ancestor, else the shared one, else the file, is the pack in force.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as 0017 is: `scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran
it empty.
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS pack_version (
  id           bigserial   PRIMARY KEY,
  key          text        NOT NULL,
  version      text        NOT NULL,
  org_unit_id  text        REFERENCES org_unit(id),
  doc          jsonb       NOT NULL,
  status       text        NOT NULL CONSTRAINT pack_version_status CHECK (status IN ('draft','review','pub','retired')),
  maker        text,
  checker      text,
  note         text,
  impact       jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz
);
"""
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pack_version ON pack_version (key, version, coalesce(org_unit_id, ''))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_pack_version")
    op.execute("DROP TABLE IF EXISTS pack_version")
