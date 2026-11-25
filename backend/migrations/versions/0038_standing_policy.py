"""standing_policy and standing_policy_version (plan 9, P9-2.5; registry entry I-11; story X-05).

A standing policy is a person-owned, maker-checked approval below thresholds: a decision under its limits is approved by
the policy (`decision.approveByPolicy`), the journal reading "approved by policy P vN, owner X". One row per policy;
at most one is active per pack and org unit (`ux_standing_policy_active`). Each approval writes the rules it approved
into `standing_policy_version`. No seed: no policy exists at the start, so the demo is unchanged.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

TABLES = """
CREATE TABLE IF NOT EXISTS standing_policy (
  id          text        PRIMARY KEY,
  pack        text        NOT NULL,
  org_unit_id text        NOT NULL REFERENCES org_unit(id),
  name        text        NOT NULL,
  ver         integer     NOT NULL DEFAULT 0,
  status      text        NOT NULL CONSTRAINT standing_policy_status CHECK (status IN ('draft','review','active','retired')),
  rules       jsonb       NOT NULL,
  owner       text        NOT NULL,
  maker       text        NOT NULL,
  checker     text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz
)
"""
ACTIVE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_standing_policy_active ON standing_policy (pack, org_unit_id) WHERE status = 'active'"
)
VERSIONS = """
CREATE TABLE IF NOT EXISTS standing_policy_version (
  policy_id   text        NOT NULL REFERENCES standing_policy(id),
  ver         integer     NOT NULL,
  rules       jsonb       NOT NULL,
  owner       text        NOT NULL,
  approved_by text        NOT NULL,
  approved_at timestamptz NOT NULL,
  PRIMARY KEY (policy_id, ver)
)
"""


def upgrade() -> None:
    op.execute(TABLES)
    op.execute(ACTIVE)
    op.execute(VERSIONS)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS standing_policy_version")
    op.execute("DROP TABLE IF EXISTS standing_policy")
