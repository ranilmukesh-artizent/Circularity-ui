"""live updates: workflow changes and run progress on the stream (B15 part 2)

The state_item trigger of 0008 fired on INSERT only and streamed the demo-shaped event log (`events`) and the
notifications (`notes`). It now also fires on UPDATE, and streams the Workflow Studio's two collections as kind
`workflow`:
- `workflow_runs`: a run record when it is added (a run queued) and every time it changes (the worker writes the run's
  progress after each step, then its result), with the whole record;
- `workflows`: a workflow added, or changed (saved, published, paused, running, its last run), without its graph and
  saved snapshot (GET /api/screens/workflows/{id} has those).
An update that leaves the data as it was sends nothing, and the starting items written when a collection is seeded
(before its state_seed row exists) send nothing either. Events and notifications keep the 0008 behaviour (inserts
only). Deleting a workflow shows on the stream as the journal event of workflow.delete.

Payload: {collection, op ("insert" | "update"), id (the item's key), data}. The stream shows kind `workflow` to accounts
that may open the Workflow Studio (di/stream.py).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE OR REPLACE FUNCTION stream_from_state_item() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' AND NEW.collection = 'events' THEN
    PERFORM stream_put('event', NEW.data->>'caseId', NEW.data);
  ELSIF TG_OP = 'INSERT' AND NEW.collection = 'notes' THEN
    PERFORM stream_put('notification', NULLIF(NEW.data->'ids'->>0, ''), NEW.data);
  ELSIF NEW.collection IN ('workflows', 'workflow_runs')
        AND (TG_OP = 'INSERT' OR NEW.data IS DISTINCT FROM OLD.data)
        AND EXISTS (SELECT 1 FROM state_seed WHERE collection = NEW.collection) THEN
    PERFORM stream_put('workflow', NULL, jsonb_build_object(
      'collection', NEW.collection, 'op', lower(TG_OP), 'id', NEW.id,
      'data', CASE WHEN NEW.collection = 'workflows' THEN NEW.data - 'graph' - 'saved' ELSE NEW.data END));
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS state_item_stream ON state_item;
CREATE TRIGGER state_item_stream AFTER INSERT OR UPDATE ON state_item FOR EACH ROW EXECUTE FUNCTION stream_from_state_item();
"""

DOWNGRADE = """
CREATE OR REPLACE FUNCTION stream_from_state_item() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.collection = 'events' THEN
    PERFORM stream_put('event', NEW.data->>'caseId', NEW.data);
  ELSIF NEW.collection = 'notes' THEN
    PERFORM stream_put('notification', NULLIF(NEW.data->'ids'->>0, ''), NEW.data);
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS state_item_stream ON state_item;
CREATE TRIGGER state_item_stream AFTER INSERT ON state_item FOR EACH ROW EXECUTE FUNCTION stream_from_state_item();
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
