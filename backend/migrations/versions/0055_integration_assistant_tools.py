"""P9-8.7 (plan 9): the Integration Assistant's tools for drafting an adapter spec held for a person.

Data only. The seeded agent `integrator` (migration 0023) gets the tools of the adapter author playbook:
`registry.importSpec`, `registry.draftFromSpec`, `connection.discover`, `mapping.suggest`, `mapping.decide`, `workflow.testRun`.
Its old tools `workflow.draft` and `workflow.validate` give way to them; none of the new ones answers 501 (P9-0.4's hygiene),
and the agent stays at autonomy `act`: its one write that matters, `registry.saveEntry`, is held for a person
(`HELD_FOR_PERSON`), and `mapping.decide` too. Idempotent: running it again sets the same list.

Revision ID: 0055
Revises: 0054
Create Date: 2026-11-25
"""

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

TOOLS = (
    "registry.importSpec",
    "registry.draftFromSpec",
    "connection.discover",
    "mapping.suggest",
    "mapping.decide",
    "workflow.testRun",
)


def upgrade() -> None:
    tools = ",".join(TOOLS)
    op.execute(f"UPDATE agent_identity SET tools = '{{{tools}}}' WHERE id = 'integrator'")  # noqa: S608 - fixed ids above


def downgrade() -> None:
    op.execute("UPDATE agent_identity SET tools = '{workflow.draft,workflow.validate}' WHERE id = 'integrator'")
