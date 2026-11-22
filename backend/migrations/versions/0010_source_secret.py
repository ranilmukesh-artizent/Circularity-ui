"""source credentials, encrypted (plan 6, task A1)

One row per version of a source's secret (kind "auth" for signing in, "webhook" for verifying its events). The value is
Fernet ciphertext (di.connectors.secrets, key DI_SECRET_KEY); `last4` is what the screens show. One active version per
source and kind; rotating adds a version and revokes the previous one.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE source_secret (
  source_id   text        NOT NULL,
  kind        text        NOT NULL DEFAULT 'auth' CHECK (kind IN ('auth', 'webhook')),
  version     integer     NOT NULL,
  ciphertext  bytea       NOT NULL,
  last4       text        NOT NULL,
  issued_at   timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz,
  active      boolean     NOT NULL DEFAULT true,
  created_by  text        NOT NULL,
  PRIMARY KEY (source_id, kind, version)
);
CREATE UNIQUE INDEX source_secret_one_active ON source_secret (source_id, kind) WHERE active;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE source_secret")
