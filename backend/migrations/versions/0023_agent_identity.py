"""agent_identity (plan 8, MVP-11.3): the agents that may call Circularity, registered at runtime.

Seeded with the demo's nine agents (fixtures/golden/tools.json `agents`), kind `internal`, each with its own tools,
and Ask Circularity (`ask`, the preparer of Ask's read tools, di.services.ask), autonomy `read`: it never changes
anything (AGENTS.md rule 10). The nine are seeded with autonomy `act`, so they keep behaving as before the registry
(their writes run as the person through the action pipeline, whose agent gate still stops every commit); an agent
registered later starts at `propose` (its writes are held for a person, MVP-11.4).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS agent_identity (
  id          text        PRIMARY KEY,
  name        text,
  kind        text        NOT NULL CONSTRAINT agent_identity_kind CHECK (kind IN ('internal','external')),
  org_scope   text[]      NOT NULL DEFAULT '{}',
  tools       text[]      NOT NULL DEFAULT '{}',
  autonomy    text        NOT NULL DEFAULT 'propose'
              CONSTRAINT agent_identity_autonomy CHECK (autonomy IN ('read','propose','act')),
  enabled     boolean     NOT NULL DEFAULT true,
  created_by  text,
  created_at  timestamptz DEFAULT now()
);
INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES
  ('assembler', 'Evidence Assembler', 'internal',
   '{get_case_evidence,list_eligible_routes,get_model_validation}', 'act'),
  ('finder', 'Opportunity Finder', 'internal',
   '{find_demand,predict_outcomes,optimize_pool,list_eligible_routes,get_case_evidence}', 'act'),
  ('gap', 'Gap Requester', 'internal', '{get_case_evidence,request_missing_evidence}', 'act'),
  ('coordinator', 'Handoff Coordinator', 'internal', '{get_case_evidence,request_approval,send_instruction}', 'act'),
  ('reconciler', 'Reconciler', 'internal', '{get_case_evidence,reconcile_outcome,get_model_validation}', 'act'),
  ('briefer', 'Briefing Agent', 'internal', '{inbox.get,cases.list,analytics.query}', 'act'),
  ('analyst', 'Analytics Explainer', 'internal', '{analytics.query,kpi.explain,analytics.models}', 'act'),
  ('integrator', 'Integration Assistant', 'internal',
   '{sources.health,mapping.suggest,tables.suggestLinks,workflow.draft,workflow.validate,import.clean}', 'act'),
  ('auditor', 'Audit Assistant', 'internal', '{audit.search,case.trace}', 'act'),
  ('ask', 'Ask Circularity', 'internal', '{}', 'read')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_identity")
