"""Plan 9 P9-2.10: the exception assistant's agent identity.

Seeds `agent_identity` row `recover-exceptions` (internal, autonomy `read`): the agent behind
`di.services.agents.exception_assistant`. It drafts the cause, action and owner of an exception item for a person and
changes nothing; its tools are the reads `case.get`, `case.evidence`, `case.trace` and `exception.explain`.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-25

Idempotent (ON CONFLICT DO NOTHING): `scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran
it empty.
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES
  ('recover-exceptions', 'Exception assistant', 'internal',
   '{case.get,case.evidence,case.trace,exception.explain}', 'read')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM agent_identity WHERE id = 'recover-exceptions'")
