"""config_change_set (plan 9, P9-2.7): what the configuration agent drafted from a description.

One row per draft: the reading log (`reading`), the one clarifying question and the answer, the typed overlay
operations (`ops`: tighten, add_approver, add_step, shortcut, set_param only), which of them were assumed, what was
blocked (with the guardrail named), the systems and KPIs the pack lists, and the proposal that holds the overlay draft
for a person. Also seeds `agent_identity` row `recover-config` (internal, autonomy `propose`): the agent behind
`di.services.agents.config_agent`; it only drafts, and a person approves through the overlay maker-checker.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS, ON CONFLICT DO NOTHING): `scripts/dev/migrate-reapply.sh 0028` applies it on a database
that already ran it empty.
"""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS config_change_set (
  id           bigserial   PRIMARY KEY,
  org_unit_id  text        NOT NULL REFERENCES org_unit(id),
  pack         text        NOT NULL,
  base_version text        NOT NULL,
  reading      jsonb       NOT NULL,
  question     jsonb,
  answer       text,
  ops          jsonb       NOT NULL,
  assumed      jsonb       NOT NULL DEFAULT '[]',
  blocked      jsonb       NOT NULL DEFAULT '[]',
  systems      jsonb       NOT NULL DEFAULT '[]',
  kpis         jsonb       NOT NULL DEFAULT '[]',
  proposal_id  bigint,
  created_by   text        NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES
  ('recover-config', 'Configuration agent', 'internal', '{config.read,config.draft,overlay.save}', 'propose')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM agent_identity WHERE id = 'recover-config'")
    op.execute("DROP TABLE IF EXISTS config_change_set")
