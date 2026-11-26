"""Publish in steps (plan 9, P9-7.3, registry I-17): the rollout of a flow's candidate version by region and share, and
which arm each case was assigned to (sticky from then on). `subject_kind 'table'` is used by P9-7.7.

Idempotent (IF NOT EXISTS); `scripts/dev/migrate-reapply.sh 0028` applies it on a database that ran it empty.

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-26
"""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rollout (
            id bigserial PRIMARY KEY,
            subject_kind text NOT NULL CHECK (subject_kind IN ('flow', 'table')),
            subject_id text NOT NULL,
            candidate_ver integer NULL,
            base_ver integer NULL,
            stage text NOT NULL CHECK (stage IN ('replay', 'shadow', 'canary', 'full', 'paused', 'rolled_back')),
            region_key text NOT NULL DEFAULT 'market',
            region text NULL,
            share integer NOT NULL DEFAULT 0 CHECK (share BETWEEN 0 AND 100),
            salt text NOT NULL,
            stop_rules jsonb NOT NULL DEFAULT '{}',
            replay_run_id bigint NULL REFERENCES replay_run(id),
            set_by text NOT NULL,
            set_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_rollout_subject ON rollout (subject_kind, subject_id, stage)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rollout_assignment (
            rollout_id bigint NOT NULL REFERENCES rollout(id) ON DELETE CASCADE,
            case_id text NOT NULL,
            arm text NOT NULL CHECK (arm IN ('canary', 'control')),
            ver text NOT NULL,
            at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (rollout_id, case_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_rollout_assignment_case ON rollout_assignment (case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rollout_assignment")
    op.execute("DROP TABLE IF EXISTS rollout")
