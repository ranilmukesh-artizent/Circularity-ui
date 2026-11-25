"""work_item (plan 9, P9-1.7): the case process layer's items, one table for exceptions, questions and steps.

A row is one thing a person or a role has to do for a case: an exception to resolve, a question to answer (`needs_info`)
or a step. `due_at` starts a timer: a `work.sla` job runs at that time and escalates the item if it is still open
(di.services.cases.process). Approvals, tasks, proposals and conflicts are not copied here; My work reads them where they
live (`process.items_for`).

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-25

Idempotent (IF NOT EXISTS), as 0017 is: `scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran
it empty.
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS work_item (
  id            bigserial   PRIMARY KEY,
  kind          text        NOT NULL CONSTRAINT work_item_kind CHECK (kind IN ('exception','needs_info','step')),
  case_id       text,
  org_unit_id   text,
  type          text        NOT NULL,
  title         text        NOT NULL,
  cause         text,
  action        text,
  owner_role    text        NOT NULL,
  owner_account text,
  priority      integer     NOT NULL DEFAULT 100,
  status        text        NOT NULL DEFAULT 'open' CONSTRAINT work_item_status CHECK (status IN ('open','done','cancelled')),
  due_at        timestamptz,
  escalated_at  timestamptz,
  outcome       text,
  created_by    text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  closed_by     text,
  closed_at     timestamptz
);
CREATE INDEX IF NOT EXISTS ix_work_item_status_owner ON work_item (status, owner_role);
CREATE INDEX IF NOT EXISTS ix_work_item_case ON work_item (case_id);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS work_item")
