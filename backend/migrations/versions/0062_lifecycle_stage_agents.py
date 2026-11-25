"""The lifecycle stage agents (plan 9, P9-2.20 and P9-2.21; registry entry I-7): stages 1 to 3, 9 and 10 of the returned-asset
journey.

Data only: five `agent_identity` rows (kind internal, autonomy act, because each writes: `evidence.request` or the transit
delay item), each with the actions its stage module may call as its tools. `stage-lease` and `stage-return` ask for a missing
record; `stage-transit` opens the "Transit delayed" item (`transit.flagDelay`). `stage-outcome` and `stage-reconcile`
(P9-2.21) call no action: they read the case, and
`outcome.confirm` stays a person's. No agent here deletes or approves (R16).

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-25

Idempotent (ON CONFLICT DO NOTHING), as every plan 9 migration is: bash scripts/dev/migrate-reapply.sh 0028
"""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES
  ('stage-lease', 'Lease-end agent', 'internal', '{case.get,case.evidence,evidence.request}', 'act'),
  ('stage-return', 'Return-authorisation agent', 'internal', '{case.get,case.evidence,evidence.request}', 'act'),
  ('stage-transit', 'Transit agent', 'internal', '{case.get,case.evidence,transit.flagDelay}', 'act'),
  ('stage-outcome', 'Outcome agent', 'internal', '{case.get,case.evidence}', 'act'),
  ('stage-reconcile', 'Reconciliation agent', 'internal', '{case.get,case.evidence}', 'act')
ON CONFLICT DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM agent_identity WHERE id IN ("
        "'stage-lease', 'stage-return', 'stage-transit', 'stage-outcome', 'stage-reconcile')"
    )
