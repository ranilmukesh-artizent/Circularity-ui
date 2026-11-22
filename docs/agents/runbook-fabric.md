# Runbook: the Connection Fabric

For whoever operates the stack. What to look at and what to do when a source, a workflow run or a credential goes
wrong. All vendor systems are synthetic (source-sim); the procedures are the ones a real deployment would follow.

Shell commands assume the repo root and Docker Compose (on the lead's Windows machine, run them through WSL; see
CLAUDE.md). `psql` means `docker compose exec -T postgres psql -U circ -d di`.

## A source is failing

1. **Connection Fabric → Monitor** (per source) or the source's drawer **Sync & History**: the last runs, their
   error, records read and failed.
2. **Test connection** (drawer, Troubleshooting): DNS → TLS → Auth → Permissions → Sample read. It stops at the first
   failure and says why (unknown host, not encrypted, token rejected, which resource could not be read).
3. What the system does by itself:
   - each GET is retried on 429, 5xx and timeouts (4 tries, 0.5 s, 1 s, 2 s; a `Retry-After` up to 30 s is honoured);
   - a failed sync is retried after 2, 4, 8 … minutes (never later than the source's interval):
     `SELECT id, status, fail_streak, next_retry_at FROM source_system WHERE fail_streak > 0;`
   - `auth_expired`: the source answered 401, or its stored credential expired (the sync says "Credential expired on
     {date}"). **Rotate credentials** (Security tab) or **Re-authenticate**, then **Sync now**.
4. Only one sync per source runs at a time (advisory lock). A second one returns `skipped: running`; that is normal.

## Credentials

- Stored encrypted in `source_secret` (Fernet, key `DI_SECRET_KEY`); one active version per source and kind. Screens
  show only the version and the last 4 characters. Nothing logs, journals or streams the value.
- **Rotate a source's secret**: drawer → Security → Rotate secret. The old version is kept, inactive (revoked).
- **`DI_SECRET_KEY` is required outside `DI_ENV=dev`** and must be a Fernet key, or several separated by commas (the
  first encrypts, every one decrypts):
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- **Rotating `DI_SECRET_KEY`** (replacing the key alone would leave every stored secret unreadable: `SecretUnreadable`,
  and syncs of those sources fail):
  1. Make a new key and set `DI_SECRET_KEY="NEW,OLD"` (new first) in `.env` or the deployment's environment.
  2. Recreate api and worker so they read it: `docker compose up -d api worker` (`docker compose restart` keeps the
     old environment).
  3. `bash scripts/dev/reencrypt-secrets.sh`: rewrites every `source_secret` row (every version) with the new key and
     prints `N re-encrypted with the current key, M unreadable` (plus source, kind and version of each unreadable row;
     never a key or a secret). It exits 1 when a row opens with none of the keys; the readable ones are committed all
     the same. Rotate the credentials of the unreadable sources by hand (drawer → Security).
  4. Set `DI_SECRET_KEY="NEW"` alone and recreate api and worker again.

## Webhooks

- Per source: `POST /api/webhooks/{source_id}`, CloudEvent with `id` and `time`, HMAC in `X-Signature`, the source's
  webhook secret (else `DI_WEBHOOK_SECRET`). 401 bad signature, 400 `stale_event` (older than 300 s on the workspace
  clock), 200 `{"duplicate": true}` for an id already seen (`webhook_event`, pruned after 7 days).
- source-sim's shared route `/api/webhooks/source-sim` has no window and no dedupe on purpose (it redelivers for an
  hour); its handling is idempotent.

## A workflow run is stuck or failed

- Runs are worker jobs (`job.kind = 'workflow.run'`). One run per workflow at a time; a second Run now says it is
  already running.
- **Stuck "running"**: the worker's periodic step (every 30 s) closes a run whose worker died (no job queued or going,
  no run lock held): the run fails with "worker lost" and the workflow can run again. Run now and triggered starts do
  the same check.
- **Failed**: Workflow Studio → the workflow → Investigate (`?run=last`): which step, after how many tries (the
  workflow's Retries setting, backoff 1 s, 2 s, 4 s), and its error. **Apply the suggested fix** restores the failed
  block's settings from the last version where they were different; **History** lists every version with Compare and
  Restore. Runs use the **published** version: publish after a fix.
- Triggers (`di/workflow/triggers.py`) start workflows published in the app (`pub`; the seeded demo workflows never fire): schedules (worker, every 30 s), source webhooks
  (filtered by the Event trigger block's event type, `fnmatch` patterns), approvals (an instruction queued for the
  target), file arrival (after a `sync.source` job of a file-drop source read new records: `file_arrived`), case
  requests (a case moving to `reeval`, in a savepoint of that move) and Call workflow steps (label *Workflow*). A
  Scheduler or Event trigger block in the graph that runs overrides the Settings tab's trigger (`trigger_of`). A
  workflow whose source is paused or unavailable is skipped; a trigger never fails its caller.
  `DI_WORKFLOW_TRIGGERS=false` turns triggers off (the test suite does), Call workflow included.
- **Records waiting at a Wait step** are parked in the state collection `workflow_waits` (one item per Wait step and
  run) with a `workflow.resume` job due at the resume time on the wall clock:
  `SELECT id, status, run_after FROM job WHERE kind = 'workflow.resume' ORDER BY run_after;`
  `SELECT id, data->>'wf', data->>'node', data->>'at' FROM state_item WHERE collection = 'workflow_waits';`
  The job runs the workflow from the Wait step (run labelled *Resume*). A running or paused workflow puts it back 1
  minute; a deleted workflow drops the item; a Wait step no longer in the graph holds its records (`failed_record`,
  rule `wait`). A record still waiting after 7 days is held with rule `wait`. The worker must be running for any of
  this.
- **Binding**: a source's sync runs its bound published ingest workflow for the resources that workflow's connector
  reads, and the default graph for the rest (`binding.unread`, `binding.rest_graph`), in one `sync_run`. Only
  workflows published in the app bind; Unpublish, Pause or Delete unbinds.
- **Outbound settings**: the instructions to a target use the changed Timeout, Retries and Target operation of the
  newest outbound workflow to that target **published in the app** (`di/services/instructions/outbound.py`); with none, sends
  are as in the demo. Retries never exceed the job queue's `job_max_attempts`.

## Held records

- A record a workflow step rejects (validation rule, unknown currency, dedupe) or whose facts do not fit the canonical
  schema is held in `failed_record` with its reason, not dropped:
  `SELECT run_kind, step, rule, reason, count(*) FROM failed_record WHERE status = 'held' GROUP BY 1, 2, 3, 4;`
- **View failed records** (workflow → Investigate) lists them; **Reprocess** sends them back through the step that
  rejected them: fixed ones become `reprocessed`, the rest stay held. Fix the rule or the source first.
- The run views count the same rows, one per record (`resource/ext_id`), by `run_id`: the Runs table's **Held**,
  Data quality (the latest real run, `lastRun.key`), the Investigation's **Held records** by step, field and rule,
  and View failed records (`di/repositories/workflows.py` `run_figures`, `run_quality`). A seeded demo run has none and keeps
  the demo's estimate:
  `SELECT run_id, count(DISTINCT coalesce(resource,'') || '/' || coalesce(ext_id,'row:' || id::text)) FROM failed_record WHERE run_kind = 'workflow' AND status = 'held' GROUP BY 1;`
- Manual Import rejects are held with `run_kind = 'import'`.

## Conflicts

- A conflict opens when two sources disagree on a canonical field; the source with authority wins until a person
  decides. A person's decision sticks until a source changes its value; then a new conflict opens.
- Escalated conflicts stay in the queue (status `escalated`) and their routes stay held.
- Home shows them as one alert, *"N open source conflicts"* with *"M hold up a decision"* (the menu badge's rule,
  `di.services.screens.nav.held_conflicts`); the Developer's briefing says the same. Home's source alerts are one per source
  the Source Map shows stale or not connected (`source_system` status stale, failing, auth_expired, unavailable or
  disconnected), so they clear when the source is live again.

## Resetting the demo

`bash scripts/dev/reset.sh` returns the demo: sources made in the app are removed, demo sources go back to their
starting status (including ones a sync left failing or auth_expired), stored credentials, edited mappings, manual
imports, workflow versions and drafts made in the app are cleared.
