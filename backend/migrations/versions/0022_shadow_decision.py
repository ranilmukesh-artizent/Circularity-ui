"""shadow_decision (plan 8, MVP-3.5): what a flow approved into shadow would have decided, beside the live decision.

While a case's flow is in `shadow` (approved, not yet published), every re-evaluation of the case also evaluates its
routes with the draft's compiled rules, on a copy, and records both recommendations here. The live decision is never
changed by it. di.repositories.flows.shadow_stats sums them for the flow.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS shadow_decision (
  id            bigserial   PRIMARY KEY,
  flow_id       bigint      NOT NULL REFERENCES decision_flow(id) ON DELETE CASCADE,
  dver          integer     NOT NULL,
  case_id       text        NOT NULL,
  live_route    text        NULL,
  shadow_route  text        NULL,
  live_net      numeric     NULL,
  shadow_net    numeric     NULL,
  at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_shadow_decision_flow ON shadow_decision (flow_id, dver);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shadow_decision")
