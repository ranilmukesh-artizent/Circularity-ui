"""plan 6 A7: webhook events already received, for dedupe

One row per event accepted by POST /api/webhooks/{source_id} (di/connectors/webhook.py): a second delivery of the same
event id for the same source is answered `{"duplicate": true}` and queues nothing. Rows older than a week are pruned
by the intake (events older than the 300 s replay window are refused anyway).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-21

Plan 6 runs in parallel: every plan-6 migration is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so they can be re-applied with alembic downgrade 0010 && alembic
upgrade head while the chain is being filled.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS webhook_event (
  source_id    text        NOT NULL,
  event_id     text        NOT NULL,
  event_type   text,
  event_time   timestamptz,
  received_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, event_id)
);
CREATE INDEX IF NOT EXISTS ix_webhook_event_received ON webhook_event (received_at);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_event")
