"""Directory groups to roles as data (P9-8.10, story X-10): table idp_group_map, seeded from policy.IDP_GROUPS.

One row maps a directory group to a role and a scope (organisation unit, site, warehouse) for a date range. A row is a
draft until a person other than its maker approves it; approving retires the group's previous approved row. The ten
seeded rows are the demo's groups, approved, role and tenant as the demo accounts have them, so parity holds.
Idempotent: the table is created if missing and a seed row is added only when the group has none.

Revision ID: 0057
Revises: 0056
Create Date: 2026-11-25
"""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


SEED = [  # group, role, org unit, site, warehouse (the demo accounts' own, see policy.IDP_GROUPS)
    ("circ-planners-customer-a", "Planner", "Customer A", "Warehouse 1", None),
    ("circ-planners-customer-b", "Planner", "Customer B", "Warehouse 2", None),
    ("circ-planners-customer-c", "Planner", "Customer C", "Warehouse 1", None),
    ("circ-approvers", "Approver", None, None, None),
    ("circ-engineering", "Engineer", None, "Repair centre", None),
    ("circ-finance", "Finance", None, None, None),
    ("circ-integration-devs", "Developer", None, None, None),
    ("circ-executives", "Executive", None, None, None),
    ("circ-warehouse-1", "Warehouse Manager", None, None, "Warehouse 1"),
    ("circ-warehouse-2", "Warehouse Manager", None, None, "Warehouse 2"),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS idp_group_map (
            id bigserial PRIMARY KEY,
            group_id text NOT NULL,
            role text NOT NULL,
            org_unit_id text,
            site text,
            warehouse text,
            valid_from date,
            valid_to date,
            status text NOT NULL CHECK (status IN ('draft','approved','retired')),
            created_by text NOT NULL,
            approved_by text,
            created_at timestamptz NOT NULL DEFAULT now(),
            approved_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_idp_group_map_group ON idp_group_map (group_id, status)")
    for group, role, org, site, warehouse in SEED:
        op.get_bind().exec_driver_sql(
            "INSERT INTO idp_group_map (group_id, role, org_unit_id, site, warehouse, status, created_by) "
            "SELECT %s::text, %s::text, %s::text, %s::text, %s::text, 'approved', 'seed' "
            "WHERE NOT EXISTS (SELECT 1 FROM idp_group_map WHERE group_id = %s::text)",
            (group, role, org, site, warehouse, group),
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idp_group_map")
