"""Plan 9 P9-0.4: catalogue hygiene. Remove from every agent's tools the actions that have no handler.

The demo's seeded agents (migration 0023) list six tools whose actions answer 501 on the server: analytics.query,
audit.search, sources.health, mapping.suggest, tables.suggestLinks and import.clean. They never worked, so they go
from agent_identity.tools; the register dialog hides unbuilt actions too. Idempotent: running it again removes nothing.
The downgrade is a no-op: the removed tools never worked, so there is nothing to give back.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-25
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

UNBUILT = ("analytics.query", "audit.search", "sources.health", "mapping.suggest", "tables.suggestLinks", "import.clean")


_NAMES = ", ".join(f"'{t}'" for t in UNBUILT)
SQL = (
    "UPDATE agent_identity SET tools = ARRAY(SELECT t FROM unnest(tools) t WHERE t <> ALL (ARRAY[" + _NAMES + "])) "  # noqa: S608 - fixed ids above, no input
    "WHERE tools && ARRAY[" + _NAMES + "]::text[]"
)


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    pass
