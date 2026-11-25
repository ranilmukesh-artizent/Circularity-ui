"""agent_stage_record (plan 9, P9-2.1; registry entry I-7): the typed record a stage of the chain leaves on a run.

One row per (run, stage): the stage's agent, kind and autonomy, its status (done, skipped, held, waiting, exception), its
output, its confidence against the stage's threshold, the sources the output rests on and the reasons a hold gave (P9-2.4).
Also seeds the chain's agents (kind internal, autonomy act): `recover-chain`, which owns a `stage_chain` run, and one per
stage, each with the actions its stage module may call as its tools.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS, ON CONFLICT DO NOTHING), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS agent_stage_record (
  run_id     text         NOT NULL REFERENCES agent_run(id) ON DELETE CASCADE,
  stage      text         NOT NULL,
  case_id    text         NOT NULL,
  agent      text         NOT NULL,
  kind       text         NOT NULL CONSTRAINT agent_stage_record_kind CHECK (kind IN ('deterministic','llm','queue')),
  autonomy   text         NOT NULL CONSTRAINT agent_stage_record_autonomy CHECK (autonomy IN ('recommend','limits','alone')),
  status     text         NOT NULL
             CONSTRAINT agent_stage_record_status CHECK (status IN ('done','skipped','held','waiting','exception')),
  output     jsonb        NOT NULL DEFAULT '{}',
  confidence numeric(4,3),
  threshold  numeric(4,3) NOT NULL,
  sources    jsonb        NOT NULL DEFAULT '[]',
  reasons    jsonb        NOT NULL DEFAULT '[]',
  at         timestamptz  NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, stage)
);
CREATE INDEX IF NOT EXISTS ix_agent_stage_record_case ON agent_stage_record (case_id, at);
INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES
  ('recover-chain', 'Recover chain', 'internal',
   '{case.evidence,evidence.request,case.reevaluate,case.routes,decision.submit,instruction.resend}', 'act'),
  ('stage-intake', 'Intake agent', 'internal', '{case.evidence,evidence.request}', 'act'),
  ('stage-condition', 'Condition agent', 'internal', '{}', 'act'),
  ('stage-demand', 'Demand agent', 'internal', '{}', 'act'),
  ('stage-fit', 'Fit-for-use agent', 'internal', '{}', 'act'),
  ('stage-valuation', 'Valuation agent', 'internal', '{case.reevaluate,case.routes}', 'act'),
  ('stage-disposition', 'Disposition agent', 'internal', '{decision.submit}', 'act'),
  ('stage-follow', 'Follow-through agent', 'internal', '{instruction.resend}', 'act'),
  ('stage-analytics', 'Analytics agent', 'internal', '{}', 'act')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_stage_record")
    op.execute(
        "DELETE FROM agent_identity WHERE id IN ('recover-chain', 'stage-intake', 'stage-condition', 'stage-demand', "
        "'stage-fit', 'stage-valuation', 'stage-disposition', 'stage-follow', 'stage-analytics')"
    )
