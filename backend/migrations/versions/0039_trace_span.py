"""trace_span: the spans of an agent run (plan 9, P9-2.6; registry entry I-12).

One row per span: a `run` (the run's bursts of steps), a `stage` of the chain, a `model` response, a `tool` call or an
`action` the pipeline ran for an agent. Written by `di.core.tracing`, read by `agent.runTrace`, deleted after
`trace_retention_days` by the `trace.prune` job. Idempotent: `scripts/dev/migrate-reapply.sh 0028` applies it again on a
database that already ran the empty reservation.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-25
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_span (
            span_id text PRIMARY KEY,
            trace_id text NOT NULL,
            parent_id text NULL,
            run_id text NULL,
            name text NOT NULL,
            kind text NOT NULL CHECK (kind IN ('run','stage','model','tool','action')),
            started_at timestamptz NOT NULL,
            ended_at timestamptz NOT NULL,
            status text NOT NULL CHECK (status IN ('ok','error')),
            attrs jsonb NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_span_run ON trace_span (run_id, started_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_span_started ON trace_span (started_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trace_span")
