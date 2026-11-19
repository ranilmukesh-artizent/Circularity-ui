"""access state: Approver delegations and tenant grants (B7)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delegation",
        sa.Column("scope", sa.Text(), primary_key=True),  # decisions, mcp, tenantAccess
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope IN ('decisions','mcp','tenantAccess')", name="ck_delegation_scope"),
    )
    op.execute("INSERT INTO delegation (scope, enabled) VALUES ('decisions', true), ('mcp', true), ('tenantAccess', true)")
    op.create_table(
        "tenant_grant",
        sa.Column("account_id", sa.Text(), primary_key=True),
        sa.Column("tenant", sa.Text(), primary_key=True),
        sa.Column("granted_by", sa.Text()),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("tenant_grant")
    op.drop_table("delegation")
