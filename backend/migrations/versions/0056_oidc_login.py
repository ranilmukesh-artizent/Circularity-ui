"""P9-8.9 (plan 9): OIDC sign-in with authlib beside the demo sign-in: the table `oidc_login`.

One row per sign-in attempt: the state, nonce and PKCE verifier kept between start and callback (valid 10 minutes),
and the one-time code the SPA exchanges for our own token (valid 60 s).

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-25

Idempotent (CREATE TABLE IF NOT EXISTS), so `scripts/dev/migrate-reapply.sh 0028` applies it again on a database that
ran the empty placeholder.
"""

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oidc_login (
            state text PRIMARY KEY,
            nonce text NOT NULL,
            verifier text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            used_at timestamptz,
            code text UNIQUE,
            account_id text,
            code_expires_at timestamptz
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oidc_login")
