"""per-source connection settings (plan 6, task A2)

One row per source: the URL its connector calls, the protocol, how it signs in (`auth_kind`, with the non-secret
`auth_params` such as the header name or the client id; the secret itself is in source_secret), and, for a source read
by the configured adapter (di.connectors.configured), its paging and resources. `updated_by` is NULL while the row is
the seeded default of a demo source (di.connectors.connection.seed_demo keeps those in step with DI_SOURCE_SIM_URL).

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, DROP ... IF EXISTS) so the
chain can be re-applied with alembic downgrade 0010 && alembic upgrade head while it is being filled.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS source_connection (
  source_id    text        PRIMARY KEY,
  base_url     text        NOT NULL,
  protocol     text        NOT NULL DEFAULT 'rest',
  auth_kind    text        NOT NULL DEFAULT 'builtin',
  auth_params  jsonb       NOT NULL DEFAULT '{}'::jsonb,
  paging       jsonb       NOT NULL DEFAULT '{}'::jsonb,
  resources    jsonb       NOT NULL DEFAULT '[]'::jsonb,
  updated_by   text,
  updated_at   timestamptz NOT NULL DEFAULT now()
);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_connection")
