"""Reserved for P9-13.9 (plan 9): Per-agent credentials with client credentials.

A client credential per agent (client id, scrypt hash of the secret, owner account): the agent's token acts as the
owner, narrowed by the agent's tools and org scope. Idempotent (IF NOT EXISTS): `scripts/dev/migrate-reapply.sh 0028`
applies it on a database that already ran it empty.

Revision ID: 0060
Revises: 0059
Create Date: 2026-11-25
"""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS agent_credential ("
        "client_id text PRIMARY KEY, "
        "agent_id text NOT NULL REFERENCES agent_identity(id) ON DELETE CASCADE, "
        "owner text NOT NULL, secret_hash text NOT NULL, "
        "created_at timestamptz DEFAULT now(), last_used_at timestamptz, revoked_at timestamptz)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_credential_agent ON agent_credential (agent_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_credential")
