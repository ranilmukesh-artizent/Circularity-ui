"""live updates: one feed of everything that changes, filled by triggers (B15)

stream_event is the feed behind GET /api/stream. Triggers copy into it, as they happen:
- journal: every domain_event (actions, stage moves)
- event: every item added to the demo-shaped event stream (state collection `events`)
- notification: every notification (state collection `notes`)
- sync: a sync run starting or finishing
- step: an instruction step queued, sent, acknowledged or failed
Each row carries the case's tenant and location (from case_record) so the stream can filter by the account's scope
without another query, and each insert sends NOTIFY di_stream with the row id.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TRIGGERS = """
CREATE FUNCTION stream_put(k text, cid text, p jsonb) RETURNS void LANGUAGE plpgsql AS $$
DECLARE t text; l text;
BEGIN
  IF cid IS NOT NULL THEN SELECT owner, location INTO t, l FROM case_record WHERE id = cid; END IF;
  INSERT INTO stream_event (kind, case_id, tenant, location, payload) VALUES (k, cid, t, l, p);
END $$;

CREATE FUNCTION stream_notify() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_notify('di_stream', NEW.id::text); RETURN NEW; END $$;
CREATE TRIGGER stream_event_notify AFTER INSERT ON stream_event FOR EACH ROW EXECUTE FUNCTION stream_notify();

CREATE FUNCTION stream_from_domain_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM stream_put('journal', NEW.case_id, jsonb_build_object('type', NEW.type, 'seq', NEW.seq, 'data', NEW.payload));
  RETURN NEW;
END $$;
CREATE TRIGGER domain_event_stream AFTER INSERT ON domain_event FOR EACH ROW EXECUTE FUNCTION stream_from_domain_event();

CREATE FUNCTION stream_from_state_item() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.collection = 'events' THEN
    PERFORM stream_put('event', NEW.data->>'caseId', NEW.data);
  ELSIF NEW.collection = 'notes' THEN
    PERFORM stream_put('notification', NULLIF(NEW.data->'ids'->>0, ''), NEW.data);
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER state_item_stream AFTER INSERT ON state_item FOR EACH ROW EXECUTE FUNCTION stream_from_state_item();

CREATE FUNCTION stream_from_sync_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
    PERFORM stream_put('sync', NULL, jsonb_build_object('id', NEW.id, 'source_id', NEW.source_id, 'status', NEW.status,
      'records_read', NEW.records_read, 'records_failed', NEW.records_failed));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER sync_run_stream AFTER INSERT OR UPDATE ON sync_run FOR EACH ROW EXECUTE FUNCTION stream_from_sync_run();

CREATE FUNCTION stream_from_instruction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
    PERFORM stream_put('step', NEW.case_id, jsonb_build_object('id', NEW.id, 'step', NEW.step, 'kind', NEW.kind,
      'system', NEW.system, 'status', NEW.status, 'doc_ref', NEW.doc_ref, 'simulated', NEW.simulated));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER instruction_stream AFTER INSERT OR UPDATE ON instruction FOR EACH ROW EXECUTE FUNCTION stream_from_instruction();
"""

DROP = """
DROP TRIGGER IF EXISTS instruction_stream ON instruction; DROP FUNCTION IF EXISTS stream_from_instruction();
DROP TRIGGER IF EXISTS sync_run_stream ON sync_run; DROP FUNCTION IF EXISTS stream_from_sync_run();
DROP TRIGGER IF EXISTS state_item_stream ON state_item; DROP FUNCTION IF EXISTS stream_from_state_item();
DROP TRIGGER IF EXISTS domain_event_stream ON domain_event; DROP FUNCTION IF EXISTS stream_from_domain_event();
DROP TRIGGER IF EXISTS stream_event_notify ON stream_event; DROP FUNCTION IF EXISTS stream_notify();
DROP FUNCTION IF EXISTS stream_put(text, text, jsonb);
"""


def upgrade() -> None:
    op.create_table(
        "stream_event",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),  # journal, event, notification, sync, step
        sa.Column("case_id", sa.Text()),
        sa.Column("tenant", sa.Text()),  # the case's owner, for the tenant boundary
        sa.Column("location", sa.Text()),  # the case's location, for the warehouse lock
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(TRIGGERS)


def downgrade() -> None:
    op.execute(DROP)
    op.drop_table("stream_event")
