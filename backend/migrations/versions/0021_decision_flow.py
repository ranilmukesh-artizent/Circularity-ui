"""decision_flow (plan 8, MVP-3.1): the Modeler's process flows and their published versions.

`decision_flow` holds one flow per template and org unit: the published graph, and while someone edits it the draft
with its lifecycle (draft, review, shadow, pub), maker and checker. `decision_flow_version` keeps every graph a
publish replaced, for rollback. Seeded with one published flow per template on the root `workspace`: the template's
default flow (di.services.modeler.flow.default_flow) at version 1. The industrial default has no rule nodes, so the
demo's cases evaluate exactly as before.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-23

Plans 2 and 8 run in parallel: every migration from 0018 on is idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF
NOT EXISTS, DROP ... IF EXISTS, inserts ON CONFLICT DO NOTHING) so the chain can be re-applied while it is being
filled: bash scripts/dev/migrate-reapply.sh 0017
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS decision_flow (
  id            bigserial   PRIMARY KEY,
  template_key  text        NOT NULL,
  org_unit_id   text        NOT NULL REFERENCES org_unit(id),
  name          text        NOT NULL,
  status        text        NOT NULL
                CONSTRAINT decision_flow_status CHECK (status IN ('draft','review','shadow','pub')),
  ver           integer     NOT NULL,
  dver          integer     NULL,
  maker         text        NULL,
  checker       text        NULL,
  draft         jsonb       NULL,
  published     jsonb       NOT NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_decision_flow_template_org UNIQUE (template_key, org_unit_id)
);
CREATE TABLE IF NOT EXISTS decision_flow_version (
  flow_id       bigint      NOT NULL REFERENCES decision_flow(id),
  ver           integer     NOT NULL,
  graph         jsonb       NOT NULL,
  published_by  text        NULL,
  published_at  timestamptz NULL,
  note          text        NULL,
  PRIMARY KEY (flow_id, ver)
);
"""
    )
    # the seed reads the template packs (pure; the PO goldens for tool_fleet and device)
    from di.services.modeler.flow import default_flow
    from di.services.modeler.templates import TEMPLATE_KEYS, load_template

    ins = sa.text(
        "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, published) "
        "VALUES (:k, 'workspace', :n, 'pub', 1, CAST(:g AS jsonb)) ON CONFLICT DO NOTHING"
    )
    for key in TEMPLATE_KEYS:
        t = load_template(key)
        op.get_bind().execute(ins, {"k": key, "n": t.name, "g": json.dumps(default_flow(t))})


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS decision_flow_version")
    op.execute("DROP TABLE IF EXISTS decision_flow")
