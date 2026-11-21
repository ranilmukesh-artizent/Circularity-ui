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
- **`DI_SECRET_KEY` is required outside `DI_ENV=dev`** and must be a Fernet key:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- **Changing `DI_SECRET_KEY`**: stored secrets no longer open (`SecretUnreadable`; syncs of those sources fail). There
  is no re-encryption tool yet: before changing the key, list the sources with a stored secret
  (`SELECT DISTINCT source_id FROM source_secret WHERE active;`), change the key, restart api and worker, and rotate
  each of those sources' credentials again.

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
- Triggers: schedules, source events and approvals start published workflows; a workflow whose source is paused or
  unavailable is skipped. `DI_WORKFLOW_TRIGGERS=false` turns triggers off (the test suite does).

## Held records

- A record a workflow step rejects (validation rule, unknown currency, dedupe) or whose facts do not fit the canonical
  schema is held in `failed_record` with its reason, not dropped:
  `SELECT run_kind, step, rule, reason, count(*) FROM failed_record WHERE status = 'held' GROUP BY 1, 2, 3, 4;`
- **View failed records** (workflow → Investigate) lists them; **Reprocess** sends them back through the step that
  rejected them: fixed ones become `reprocessed`, the rest stay held. Fix the rule or the source first.
- Manual Import rejects are held with `run_kind = 'import'`.

## Conflicts

- A conflict opens when two sources disagree on a canonical field; the source with authority wins until a person
  decides. A person's decision sticks until a source changes its value; then a new conflict opens.
- Escalated conflicts stay in the queue (status `escalated`) and their routes stay held.

## Resetting the demo

`bash scripts/dev/reset.sh` returns the demo: sources made in the app are removed, demo sources go back to their
starting status (including ones a sync left failing or auth_expired), stored credentials, edited mappings, manual
imports, workflow versions and drafts made in the app are cleared.
