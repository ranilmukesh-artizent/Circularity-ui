"""A published default flow on `workspace` for every pack beyond the demo's three (plan 9, writer 8).

Migration 0021 seeded `industrial`, `tool_fleet` and `device`. Every pack file is a Modeler template now
(`di.services.modeler.templates.template_keys`), so each other pack gets its default flow too. Idempotent (ON CONFLICT DO
NOTHING); the worker repeats it at start for packs added later (`di.repositories.flows.ensure_pack_flows`).
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from di.services.modeler.flow import default_flow
    from di.services.modeler.templates import load_template, template_keys

    ins = sa.text(
        "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, published) "
        "VALUES (:k, 'workspace', :n, 'pub', 1, CAST(:g AS jsonb)) ON CONFLICT DO NOTHING"
    )
    for key in template_keys()[3:]:
        t = load_template(key)
        op.get_bind().execute(ins, {"k": key, "n": t.name, "g": json.dumps(default_flow(t))})


def downgrade() -> None:
    op.execute(
        "DELETE FROM decision_flow WHERE org_unit_id = 'workspace' AND ver = 1 AND status = 'pub' "
        "AND template_key NOT IN ('industrial', 'tool_fleet', 'device')"
    )
