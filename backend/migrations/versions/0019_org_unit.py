"""org_unit (plan 8, MVP-1.1): the organisation tree (group, segment, company, site, customer).

The seeded ids equal the demo's tenant strings (fixtures/golden/world.json `tenants`) under one root `workspace`, so
`case_record.owner` and `tenant_grant.tenant` keep holding org unit ids and every tenant check reads the same values.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS org_unit (
  id          text        PRIMARY KEY,
  parent_id   text        NULL REFERENCES org_unit(id),
  kind        text        NOT NULL
              CONSTRAINT org_unit_kind CHECK (kind IN ('group','segment','company','site','customer')),
  name        text        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_org_unit_parent ON org_unit (parent_id);
INSERT INTO org_unit (id, parent_id, kind, name) VALUES ('workspace', NULL, 'group', 'Workspace')
ON CONFLICT DO NOTHING;
INSERT INTO org_unit (id, parent_id, kind, name) VALUES
  ('Customer A', 'workspace', 'customer', 'Customer A'),
  ('Customer B', 'workspace', 'customer', 'Customer B'),
  ('Customer C', 'workspace', 'customer', 'Customer C')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_unit")
