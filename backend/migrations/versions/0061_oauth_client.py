"""P9-13.10 (plan 9): OAuth for outside MCP clients.

`oauth_client`: a pre-registered client (public, PKCE; exact redirect URIs; the agent it acts as; the scopes it may
ask for). `oauth_code`: an authorization code, stored as its SHA-256 (never the code), single use, 60 seconds.
Idempotent (IF NOT EXISTS): `scripts/dev/migrate-reapply.sh 0028` applies it on a database that ran it empty.

Revision ID: 0061
Revises: 0060
Create Date: 2026-11-25
"""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS oauth_client ("
        "client_id text PRIMARY KEY, name text NOT NULL, redirect_uris text[] NOT NULL, "
        "agent_id text NOT NULL REFERENCES agent_identity(id) ON DELETE CASCADE, scopes text[] NOT NULL, "
        "created_by text NOT NULL, created_at timestamptz DEFAULT now(), revoked_at timestamptz)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS oauth_code ("
        "code text PRIMARY KEY, client_id text NOT NULL REFERENCES oauth_client(client_id) ON DELETE CASCADE, "
        "account_id text NOT NULL, agent_id text NOT NULL, scopes text[] NOT NULL, resource text NOT NULL, "
        "challenge text NOT NULL, redirect_uri text NOT NULL, expires_at timestamptz NOT NULL, used_at timestamptz)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_oauth_code_client ON oauth_code (client_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_code")
    op.execute("DROP TABLE IF EXISTS oauth_client")
