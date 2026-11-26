"""Saved analytics views (plan 9, P9-9.19, story UC-20): a worked question saved with its parameters, shared with roles and
carrying one measure alert. Idempotent (IF NOT EXISTS).

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-27
"""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS analytics_view ("
        "id bigserial PRIMARY KEY, org_unit_id text NOT NULL, owner text NOT NULL, owner_role text NOT NULL, "
        "pack text NOT NULL, question_id text NOT NULL, name text NOT NULL, "
        "params jsonb NOT NULL DEFAULT '{}'::jsonb, shared_with_roles jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "alert jsonb, alert_active boolean NOT NULL DEFAULT false, alert_items jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_view_owner ON analytics_view (owner)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics_view")
