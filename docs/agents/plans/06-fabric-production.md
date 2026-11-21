# Plan 6: Connection Fabric, production grade Implementation Plan

> **For agentic workers:** one task per iteration (`loop.md`), or inline by the lead. Steps use checkboxes.

## Status (21 Nov 2026)

**Done.** Run by the lead with 7+ parallel agents (tracks A, B, C/W, D) on one tree; plan commit `832b681`, work
`810d706` … `93e57e5`. What runs for real now: `docs/backend-steps.md` (plan 6 status block); what no longer replays
the demo, on purpose: decision-log *D-Fabric* and the rows below it; operating it: `docs/agents/runbook-fabric.md`.

| Task | Commit(s) |
|---|---|
| Migrations 0011–0017 reserved (empty, idempotent) | `f45a85d` |
| A1 encrypted credentials | `810d706` |
| A2 per-source connection settings, A3 configured adapter, A5 honest Test connection | `b9a9081` (one commit: shared files), `0511bbc` (restores A7's `webhook_event` model it dropped) |
| A4 the edited mapping runs | `e00df59` (module), `8ee1d29` (call sites) |
| A6 sync reliability | `7ce232b`, `86aaa12` (took back an unfinished A3 line) |
| A7 webhook intake | `90f51bf` |
| B1 schema checks, failed records | `0600f33` |
| B2 sticky conflicts | `7dcdaf0` |
| B3 Manual Import | `f25ea62` |
| B4 Event Streams and tiles | `9625f34` |
| B5 Source Tables discovered | `cf99202` (module), `8ee1d29` (call sites) |
| C1 block catalogue | `c23d6b3` |
| C2 settings on nodes | `d6200ec` |
| C3 settings in the inspector | `cf89309` |
| C4 step implementations | `5088b2d` |
| C5 engine, sync = ingest workflow; C7 retries, one run at a time | `f9bbbf2`, `8b0417c` (shared workflow files) |
| C6 triggers | `0d2296d`, `8b0417c` |
| C8 versions, reprocess, fix | `2cf2785`, `8b0417c` |
| C9 server drafts, dry test run | `b667dbd`, `e53c371` (drafts not journaled), `8b0417c` |
| C10 live checks, palette, import | `8579832`, `8b0417c` |
| T8 (added) catalogue mappings on the mocks' real fields | `df9cee3` |
| Type checks (mypy, ruff) | `fc9e7dc`, `93e57e5` |
| D1 Monitor per workflow and step | `4b9c095` |
| D2 `smoke-fabric.mjs`, D3 guides, runbook, these docs | `3932fbe` (decisions, runbook); the rest with the lead's closing commits |

Deviations worth knowing:
- **Plan 2 tasks 1–3 were not done first.** One run at a time is the run's advisory lock plus a query on `job`
  (`run_active` in `di/actions/workflows.py`), not `dedupe_key`; plan 6 has its own reaper (`di/worker.py
  reap_lost_runs`, `reap_lost_run`) instead of plan 2's.
- **Migrations 0010–0017**, not "numbered at the time": 0010 is A1's `source_secret`, 0011–0017 were reserved empty
  so tracks could fill them in parallel (`scripts/dev/migrate-reapply.sh`).
- **Demo sources keep their adapters' built-in credentials** until someone rotates one; nothing is seeded into
  `source_secret` (the plan said seed through `put_secret`).
- **Retries:** 3 retries = 4 tries per GET (`DI_SOURCE_RETRY_BASE_SECONDS`, 0.5 s doubled).
- **Canonical schema** is canonical.json plus a documented table of the fields the connectors write
  (`di/canonical/fields.py`); canonical.json alone would hold most demo data.
- **Block settings are stored only where they differ from the defaults** (`compact_cfg`), so the demo's graphs and the
  golden replay are unchanged.
- **Only workflows published in the app are bound** to a source's sync; a webhook runs the bound workflow through the
  sync only, never also through its Event trigger. File and case triggers are helpers nothing calls yet. Triggers are
  off in the api suite (`DI_WORKFLOW_TRIGGERS=false`, `tests/conftest.py`).
- **Versions, drafts and run stats live in state collections** (`workflow_versions`, `workflow_drafts`,
  `workflow_run_stats`), not new tables; draft autosaves are unjournaled (`ActionDef.journaled=False`).
- **Catalogue systems** map only where their mock holds circularity data, on keys of their own (`<system>:<key>`), so
  they never touch demo canonical data (T8, not in the original plan).
- **Shared files** (`di/actions/workflows.py`, `di/screens/workflows.py`, `fabric_sources.py`, `sync.py`,
  `apps/web/src/api/workflows.ts`, `Canvas.tsx`) were committed by the lead in `8ee1d29` and `8b0417c`; the
  "(part)" commits hold only their track's own files.

Gate per phase: the phase's tests below, then `scripts/dev/full-suite.sh`, `scripts/dev/web-check.sh`,
`node apps/web/scripts/smoke-pages.mjs` and `node apps/web/scripts/smoke-rt1048.mjs` (reset before and after).

**Goal:** everything under the Connection Fabric menu does real work: sources connect with stored, encrypted
credentials to the URL a person configured; the mapping a person edits is the mapping a sync applies; canonical data is
checked against its model; conflicts, imports and events are real; workflow blocks have settings and a workflow run
processes real records, on its trigger, with real retries, failed records and history.

**Architecture:** three layers, built bottom up. (1) *Connections*: a `source_connection` row and an encrypted
`source_secret` per source, a `ConfiguredAdapter` that reads any spec-shaped HTTP API from that configuration (the 21
Python adapters stay, now reading their URL and secret from the same rows), and a versioned `field_mapping` that the
sync applies. (2) *Data*: canonical schema checks, `failed_record` storage, conflicts that stay resolved, manual imports
through the same pipeline, Event Streams from real events. (3) *Workflows*: a block catalogue with settings
(`di/workflow/blocks.py`), node settings `cfg`, and an engine (`di/workflow/engine.py`) that runs a graph's steps over
record batches. A source's sync **is** the run of its ingest workflow (the default graph when none is published), so
there is one data path.

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, psycopg 3, `cryptography` (Fernet, already in the lock at 50.0.2),
httpx, React 18 + TS, Vitest, pytest, Node Playwright with Chrome.

**Spec:** this plan, from the audit of 21 Nov 2026 (two read-only audits of `apps/api/di/connectors`,
`di/actions/fabric_*.py`, `di/actions/workflows.py`, `di/reads/workflows.py`, `apps/web/src/pages/{integration,workflows}`),
summarised under *Where we start*. User request (21 Nov 2026): "all the things under the connector menu should be
production grade".

## Where we start (21 Nov 2026)

| Area | Today |
|---|---|
| Sync engine, cursors, raw records, provenance, canonical, conflict detection, sync schedule, Monitor metrics | **Real**, Postgres, against source-sim |
| Source URL and credentials | Hard-coded per adapter (`settings.source_sim_url + base_path`, literal secrets in `auth()`); rotate/re-auth throw the secret away |
| Catalogue and hand-made sources | No adapter: one synthetic first sync (hash row count, 4.2 s), then "No simulated system" |
| Data Mapping edits | Stored in `source_config.maps`, never used by a sync |
| Test connection | Real DNS/TCP/auth to source-sim; TLS text, IP and scopes invented; no-adapter sources always pass |
| Sync failures | Recorded, never retried before the next interval; no HTTP retry; no per-source lock |
| Webhooks | HMAC real (one global secret); no event dedupe or replay window |
| Canonical schema | Only the model name is checked |
| Conflict resolve | Flips status only; reopens on the next sync; escalation not persisted |
| Manual Import | Rows stored in a collection nobody reads |
| Event Streams, Home/Command fabric tiles | Seeded fixtures and hash-generated buckets |
| Workflow blocks | No settings: a node is `{id,k,ref,x,y}` |
| Workflow runs | Simulation (seeded draws, hash counts, invented failed rows and history); never read a record |
| Triggers, retries | Labels; only Run now starts a run; retries never happen |
| Versions | Only the latest graph kept; drafts live in browser memory |
| Inspector | **Done in 70b3584**: connections in/out with Remove, Next step / Add another connection, Testing apart |

## Global Constraints

- All vendor systems stay synthetic (AGENTS.md rule 14). "Real" means the engine works against any HTTP API shaped like
  a `sim.generic.spec.Spec`; in dev that API is source-sim. Never claim a named vendor is connected.
- Never store, log, return or journal a secret in plain text. Secrets live only as Fernet ciphertext in `source_secret`;
  the key is `DI_SECRET_KEY` (env, 32-byte urlsafe base64). Without it the api refuses to start when `DI_ENV=prod`; in dev
  it derives a key from a fixed dev seed and logs one warning. Responses show only `kind`, `issued_at`, `expires_at`,
  `version` and the last 4 characters.
- Every write goes through the action pipeline (`POST /api/actions/{id}`), with server-side permission checks
  (`manageIntegrations` for sources, `manageWorkflows` for workflows). New action ids are declared with
  `ACTIONS.setdefault`.
- **Parity changes on purpose** (golden rule 1): add one decision-log entry, *"D-Fabric: Connection Fabric runs for
  real"*, listing what no longer matches the demo (run states, counts, durations, failed rows, history, test-connection
  texts, Event Streams contents, catalogue first syncs). Golden files are never hand-edited: tests that replay a now-real
  behaviour assert the behaviour instead, and say so in their docstring.
- **Must not change:** the canonical data the 21 demo sources produce (so every decision, number and RT-1048 stays
  identical), the 11 accounts' page smoke, RT-1048 end to end, and the access rules.
- Dependencies at least 2 weeks old; no new service (no Redis, no vault server: decision D6).
- Each task: failing test first, one commit, one line in `PROGRESS.md`. Migrations are numbered after the newest in
  `apps/api/migrations/versions/` at the time (plan 2 may have taken 0010).
- Prerequisite: plan 2 tasks 1–3 (job priorities, `dedupe_key`, dead letters, heartbeats). If plan 2 is not done when
  phase C starts, do those three tasks first.

## Review Focus

1. **The default ingest workflow changes canonical data.** After a full sync of all 21 sources through the engine, the
   `canonical` and `provenance` tables must equal those from today's `run_sync`. Test: `test_engine_parity_canonical`
   (Task C5).
2. **A secret leaks.** Rotate a credential, then search the action journal, the logs, `fetch_log`, the stream and every
   screen response for the plain value: none contains it. Test: `test_secret_never_leaves` (Task A1).
3. **A resolved conflict reopens.** Resolve, sync again with the same differing values: the conflict stays resolved;
   change one value: a new conflict opens. Test: `test_resolution_sticks_until_values_change` (Task B2).
4. **Two runs of one workflow at once** (schedule tick plus Run now): one runs, the other is refused with
   `already_running` or queued once; `running` never stays true after a crash. Test: `test_one_run_at_a_time` (Task C7).
5. **A block setting the step cannot use** (unknown currency, a dedupe key the records lack, an empty filter): Save
   keeps it but the checks show an error naming the block and the field; Publish is refused. Test:
   `test_bad_settings_block_publish` (Task C2).

---

## Phase A: connections that are real

### Task A1: encrypted credentials
**Files:** Create `apps/api/di/connectors/secrets.py`, migration `00NN_source_secret.py`; Modify `di/config.py`
(`secret_key`, `env`), `di/actions/fabric_sources.py` (`credentials.rotate`, re-auth, `source.update` new/catalog).
Test: Create `tests/test_secrets.py`.
**Interfaces:** Produces `put_secret(s, source_id: str, kind: str, value: str, days: int, by: str) -> SecretMeta`
(new active version, old one inactive), `active_secret(s, source_id: str, kind: str = "auth") -> str | None`,
`secret_meta(s, source_id) -> SecretMeta | None`; `SecretMeta(kind, version, issued_at, expires_at, last4)`.
Table `source_secret(source_id, version, kind, ciphertext bytea, issued_at, expires_at, active, created_by)`, PK
`(source_id, kind, version)`.
- [x] Tests: round trip; rotate makes a new version and `active_secret` returns it; `secret_meta` has `last4` only;
  `test_secret_never_leaves` (Review Focus 2); a wrong `DI_SECRET_KEY` raises `SecretUnreadable`, not garbage.
- [x] Implement; the drawer's Security tab reads `secret_meta` (issued, expiry, version, ••••last4). Remove the
  web texts that call this a "vault" (`IntegrationPage.tsx:291`, `SourceDrawer.tsx:600`, `ConnectFlow.tsx:102`) and
  say *"Encrypted and stored by Circularity; never shown again."* Commit.

### Task A2: per-source connection settings
**Files:** Create migration `00NN_source_connection.py`, `di/connectors/connection.py`; Modify `di/connectors/http.py`
(`SourceClient`), `base.py`, `sync.py:299`, `probe.py`, `adapters/*.py` (`auth()`), `actions/fabric_sources.py`.
Test: Create `tests/test_connection_settings.py`.
**Interfaces:** Table `source_connection(source_id pk, base_url, protocol, auth_kind, auth_params jsonb, paging jsonb,
resources jsonb, updated_at)`. `connection_for(s, source_id) -> Connection | None`. `Adapter.auth(conn: Connection,
secret: str | None) -> Auth`. Seeded for the 21 demo sources with `base_url = settings.source_sim_url + base_path`
and their demo secret written through `put_secret` (so behaviour is unchanged).
- [x] Tests: editing a demo source's base URL to a wrong host makes the next sync fail at connect with the host in the
  error; restoring it syncs again; rotating to a wrong secret gives `auth_expired` after the 401.
- [x] Implement; `source.update` writes `source_connection` (URL, protocol, auth kind and non-secret params) and the
  secret through `put_secret`. Commit.

### Task A3: a configured adapter for any spec-shaped API
**Files:** Create `di/connectors/configured.py`; Modify `registry.py`, `sync.py:284`, `actions/integration.py:27-33`,
`actions/fabric_sources.py` (catalogue connect, hand-made create: no more synthetic run). Source-sim: Create
`apps/source-sim/sim/generic/specs/catalog_*.py`, one spec per catalogue system (15; resources and fields that read
like that product's API, seeded deterministically), and `sim/generic/specs/sandbox.py` (`/sandbox/{name}/records`,
offset paging) for hand-made sources. Test: Create `tests/test_configured_adapter.py`,
`apps/source-sim/tests/test_catalog_specs.py`.
**Interfaces:** `ConfiguredAdapter(conn: Connection)` implements the `base.Adapter` contract: `resources()` from
`conn.resources` (`{name, path, id_field, delta_param?}`), paging from `conn.paging` (offset, page, cursor; the same
keys as `sim.generic.spec.Paging`), auth `api_key | bearer | basic | oauth_cc`. `map()` comes from Task A4.
`registry.adapter_for(s, source_id) -> Adapter | None`: the Python adapter if one exists, else `ConfiguredAdapter`
when a connection row exists.
- [x] Tests: connect *Workday HCM* from the catalogue → the first sync reads the spec's records (`records_read` equals
  the seeded count), Sync now works later; a hand-made source pointing at `http://source-sim:8100/sandbox/demo`
  syncs; one pointing at an unknown host fails Test connection at DNS.
- [x] Delete `record_synthetic_run` and the hash row counts. Commit.

### Task A4: the mapping a person edits is the one that runs
**Files:** Create migration `00NN_field_mapping.py`, `di/connectors/mapping.py`; Modify `sync.py:326-330`,
`actions/fabric_sources.py` (`source.update` maps), `lifecycle.py:72-77`, `screens/integration.py:232`. Test: Create
`tests/test_mapping_runs.py`.
**Interfaces:** Table `field_mapping(source_id, version, rows jsonb, created_by, created_at)`. `MapRow(src: str
(dotted path), model: str, field: str, rule: str)`; rules `copy | upper | lower | number | int | date | utc |
units:<from>><to> | fx:<currency> | code:<table>`. `active_rows(s, source_id) -> list[MapRow]`;
`apply_rows(rows, rec) -> list[Fact]`; `overlay(facts, rec, rows, builtin: set[tuple[model, field]]) -> list[Fact]`.
Configured sources: `map()` = `apply_rows`. Python adapters: their code mapping stays the default; an edited row
replaces the fact for its `(model, field)`, an added row adds one, a removed row drops it (`overlay`).
- [x] Tests: on SafetyCulture, change one row's rule to `upper` → after Sync now the canonical value is upper-cased and
  provenance shows the new transform; Revert (a new version equal to v1) restores it; a row whose `src` path is missing
  in a record fails that record with reason *"missing field {src}"* (counted, not fatal).
- [x] Data Mapping tab: version shown, *Preview on a sample record* (action `mapping.preview`, read). Commit.

### Task A5: honest Test connection and expiry
**Files:** Modify `di/connectors/probe.py`, `actions/fabric_sources.py:503-619`, `screens/integration.py:165-169`,
`sync.py` (expiry check). Test: extend `tests/test_fabric_sources.py`.
- [x] Tests: the TLS step reports the real result (an `http://` URL says *"Not encrypted: http"* as a warning; an
  `https://` URL does a handshake and reports the protocol and certificate expiry); the IP step shows the resolved
  address; *Permissions* reads one record from each configured read resource and names the first that is refused;
  a source whose credential expired is not synced (`sync_run.status = 'failed'`, error *"Credential expired on
  {date}"*, status `auth_expired`).
- [x] Implement; remove the invented `_ip` and fixed texts. Commit.

### Task A6: sync reliability
**Files:** Modify `di/connectors/http.py`, `sync.py` (`run_sync`, `enqueue_due`), migration `00NN_sync_retry.py`
(`source_system.fail_streak int default 0`, `next_retry_at timestamptz`). Test: Create `tests/test_sync_reliability.py`.
**Interfaces:** `SourceClient` retries GETs on 429, 5xx, connect and read timeouts: 3 tries, backoff 0.5 s, 1 s, 2 s,
honouring `Retry-After` up to 30 s. `run_sync` takes `pg_try_advisory_xact_lock(hashtext('sync:'||source_id))`;
already locked → `{"status": "skipped", "reason": "running"}`. A failed run sets `fail_streak += 1` and
`next_retry_at = now + min(2**fail_streak minutes, interval)`; success resets both; `enqueue_due` honours
`next_retry_at`.
- [x] Tests (source-sim faults): a 503 burst of 2 then OK → one sync, `ok`, 3 fetch_log rows; a failing source retries
  after 2, 4, 8 min (clock pinned), not after a full interval; two concurrent `run_sync` → one skipped. Commit.

### Task A7: webhook intake
**Files:** Modify `di/connectors/webhook.py`, migration `00NN_webhook_event.py`; route
`POST /api/webhooks/{source_id}` beside the source-sim one. Test: extend `tests/test_webhooks.py` (or create).
**Interfaces:** Table `webhook_event(event_id text pk, source_id, received_at)`. Per-source secret
`active_secret(s, sid, "webhook")`, falling back to the global one for the demo sources. Reject a `time` older than
300 s (`stale_event`) or a seen `id` (`duplicate`, 200 with `{"duplicate": true}`).
- [x] Tests: replayed event → one sync; event 10 min old → 400 `stale_event`; wrong signature → 401. Commit.

**Phase A gate.** Plus: in Chrome, connect Workday HCM from the catalogue, see real records in Sync & History, rotate its
secret, Sync now still works; edit a mapping rule and see the canonical value change.

## Phase B: data that is real

### Task B1: canonical schema checks and failed records
**Files:** Modify `di/canonical/schema.py`, `store.py:41-66`; Create migration `00NN_failed_record.py`,
`di/canonical/failed.py`. Test: Create `tests/test_canonical_schema.py`.
**Interfaces:** `MODEL_FIELDS: dict[str, dict[str, FieldSpec]]` built once from `fixtures/golden/canonical.json`
(`FieldSpec(type: "text"|"number"|"date"|"bool"|"ref", required: bool)`). `check_fact(f: Fact) -> str | None`.
Table `failed_record(id, run_kind 'sync'|'workflow'|'import', run_id, source_id, step, resource, ext_id, field, rule,
value, reason, payload jsonb, status 'held'|'reprocessed'|'dropped', created_at)`; `hold(s, ...) -> int`.
- [x] Tests: a fact with an unknown field or a wrong type is held with a reason and counted in `records_failed`; the
  21 demo sources produce **zero** held records on a full sync (proves the schema matches the demo data). Commit.

### Task B2: conflicts that stay resolved
**Files:** Modify `actions/fabric_records.py:310-349`, `di/canonical/store.py:102-152`, migration
`00NN_conflict_resolution.py`. Test: extend `tests/test_conflicts.py` (or create).
**Interfaces:** `conflict.resolve` input `{id, choose: "authority"|"other"|"value", value?: str, reason: str}`.
`store.override(s, model, key, field, value, by) -> None` writes canonical and a provenance row from source
`manual`. Column `conflict.values_hash`; `_settle` does not reopen while the hash of the differing values is unchanged.
`conflict.escalate` sets `status = 'escalated'` in the table.
- [x] Tests: `test_resolution_sticks_until_values_change` (Review Focus 3); choosing *other* changes the canonical value
  and the routes that were held are released; escalated shows in the queue with its owner. Commit.

### Task B3: Manual Import through the pipeline
**Files:** Modify `actions/fabric_records.py:210-273`; Create `di/connectors/manual.py`. Test: extend
`tests/test_fabric_records.py`.
- [x] Tests: loaded rows land in `raw_record` (source `manual`, resource `import`), map to facts with confidence
  `manual` and freshness none, appear on the asset pages, never trigger instructions; rejected rows are held in
  `failed_record` with `run_kind='import'`; loading twice is still refused. Commit.

### Task B4: Event Streams and fabric tiles from real data
**Files:** Modify `screens/integration.py:707-739`, `di/reads/fabric.py`, `screens/home.py:79`, `screens/command.py:90`.
Test: extend `tests/test_screens_integration.py`, `test_screens_home.py`, `test_screens_command.py`.
- [x] Tests: Event Streams lists the seeded decision messages **plus** real ones (sync runs, webhook deliveries,
  instruction acks from `domain_event` / `stream_event`), newest first; Home and Command Center tiles equal the
  Monitor's numbers for the same moment (no hash buckets). Commit.

### Task B5: Source Tables from what the source really sends
**Files:** Modify `screens/integration.py:122` (`table_models`), `actions/fabric_records.py:132-206`; Create
`di/connectors/discover.py`. Test: extend `tests/test_fabric_records.py`.
**Interfaces:** `discover(s, source_id) -> list[TableModel]`: one table per resource in `raw_record`, columns from the
union of payload keys with an inferred type, the `id_field` first; foreign keys suggested where a column's values match
another table's key (≥ 90 % of a sample of 200).
- [x] Tests: a configured source shows its real tables after its first sync; tables a person added or edited are kept
  and marked *manual*; the demo systems' seeded models stay as they are. Commit.

**Phase B gate.**

## Phase C: workflows that run

### Task C1: block catalogue with settings
**Files:** Create `apps/api/di/workflow/__init__.py`, `di/workflow/blocks.py`; route
`GET /api/screens/workflows/blocks`; Modify `apps/web/src/api/workflows.ts` (`blockSpecs()`). Test: Create
`tests/test_blocks.py`.
**Interfaces:** `FieldSpec(key, label, type: "text"|"number"|"select"|"multi"|"bool"|"fields"|"rules"|"mapping",
default, required: bool, choices: list | None, help: str)`; `BlockSpec(ref, fields: tuple[FieldSpec, ...])`;
`BLOCKS: dict[str, BlockSpec]`; `default_cfg(ref) -> dict`; `cfg_errors(node, ctx) -> list[str]`.
Settings per block (defaults reproduce today's behaviour):

| ref | settings |
|---|---|
| conn | resources (multi, from the connection), mode `delta`/`full`, lookback days |
| x_gw / x_evt / x_file | rate limit per min; timeout s / ordering key, replay window min / path, checksum required |
| x_val | required fields (fields), rules (rules: field, check `present|type|regex|range|in`, arg), on failure `reject`/`hold` |
| x_late | key fields (fields), newest wins by (field), late window min |
| x_fx | target currency (select ISO 4217), rate date `record`/`run`, rate table (select) |
| x_utc / x_units / x_lookup | fields and source zone / field → unit pairs / field → code table |
| x_filter / x_expr / x_agg | condition (rules) / target field and expression / group by and totals |
| x_enrich / x_join / x_ident | lookup model and key / second input and key / identity keys within the tenant |
| map | mapping version (select; latest by default) |
| x_branch / x_wait / x_call / x_loop | condition / duration or until / workflow id / items path |
| x_err / x_audit / x_pub | hold or drop / level / topic |
| x_sched / x_evtrig | interval min / event type |
| act / wconn | timeout s, retries / target operation |
| fixed, tool | none (read only) |

- [x] Tests: every palette ref has a spec; every default passes `cfg_errors`; the endpoint is readable by Admin and
  Developer only. Commit.

### Task C2: settings on nodes, checked on the server
**Files:** Modify `di/actions/workflows.py` (`_n` gains `cfg`, `workflow.save` and `workflow.publish` validate),
`validate()` (adds `cfg_errors`), `apps/web/src/api/workflowGraph.ts` (same rule in the browser),
`di/actions/workflow_builder.py` (fills `cfg` from the description: e.g. *"to EUR"* → `x_fx.currency = "EUR"`). Test:
extend `tests/test_writes_workflows.py`, `test_workflow_builder.py`, `workflowGraph.test.ts`.
- [x] Tests: `test_bad_settings_block_publish` (Review Focus 5); a graph saved without `cfg` gets defaults (old
  workflows still open); the builder sets the currency. Commit.

### Task C3: settings in the inspector
**Files:** Create `apps/web/src/pages/workflows/BlockSettings.tsx`; Modify `Canvas.tsx` (Inspector: a *Settings*
section between About and Connections), `draftStore.ts` (`setCfg(nodeId, key, value)`, undoable). Test: Create
`BlockSettings.test.tsx`.
- [x] Tests: renders each field type from a spec; a required empty field shows its error in place; editing marks the
  draft unsaved and undo restores it; fixed blocks show their settings read only.
- [x] Chrome: on the CRM workflow set Convert currency to EUR, Order late events key `opportunity_id`, Save, reload:
  the values are kept. Commit.

### Task C4: the step implementations
**Files:** Create `di/workflow/steps/{__init__,ingest,quality,transform,flow,branch}.py`. Test: Create
`tests/test_steps.py`.
**Interfaces:** `Rec(ext_id, resource, data: dict, facts: list[Fact] | None, meta: dict)`;
`Reject(rec, field, rule, value, reason)`; `StepCtx(s, run_id, wf, node, source_id, now, dry: bool, log)`;
`StepResult(out: list[Rec], rejected: list[Reject], side: dict)`;
`STEPS: dict[str, Callable[[list[Rec], dict, StepCtx], StepResult]]`. Rate table for `x_fx`: `fx_rate` table (date,
currency, usd_rate) seeded with today's fixed rates from `generic.to_usd`, so numbers do not change.
- [x] Tests (pure, no DB except `fx_rate`): x_val rejects per rule with the rule name; x_late keeps the newest per key
  and drops the rest; x_fx converts at the dated rate and records it in `meta.fx`; x_filter keeps matches; x_utc,
  x_units, x_lookup, x_expr, x_agg, x_join, x_ident, x_enrich one case each; x_branch splits by condition. Commit.

### Task C5: the engine, and sync = the ingest workflow
**Files:** Create `di/workflow/engine.py`; Modify `di/connectors/sync.py` (`run_sync` runs the source's bound
workflow, or `minimal_graph({"k": "min", "type": "ingest", "src": sid})` when none), `di/actions/workflows.py`
(`run_job` calls the engine; delete `sim_outcome`, `draws`, `step_dur`, the hash counts), `di/reads/workflows.py`
(`run_counts`, `failed_rows` read the run record and `failed_record`). Test: Create `tests/test_workflow_engine.py`.
**Interfaces:** `run_graph(s, wf: dict, graph: dict, *, trigger: str, dry: bool = False, sample: int | None = None)
-> RunResult(states: dict, counts: dict[str, Counts], dur_ms: dict, rows: int, failed: int, error: str | None)`.
Steps run in `studio._order`; a node gets the union of its predecessors' `out`; `x_err` gets their `rejected`; a
failing step marks later ones `upstream_failed`. Progress is written to the run record after each step (the live
canvas keeps working). Binding: `source_config.workflow` = the newest published ingest workflow whose connector is the
source; set on publish, cleared on unpublish or delete.
- [x] Tests: `test_engine_parity_canonical` (Review Focus 1); a workflow with x_val rule `qty > 0` holds the bad rows
  and the Failed records view lists them (real values); a dry run writes nothing (`canonical` unchanged) and returns
  before/after samples per step; run counts equal the records that really passed each step.
- [x] Re-assert the parity tests that replayed simulated runs (`test_writes_workflows.py`, `test_screens_workflows.py`)
  as behaviour tests; decision-log entry D-Fabric. Commit.

### Task C6: triggers
**Files:** Create `di/workflow/triggers.py`; Modify `di/worker.py` (`periodic()`), `di/connectors/webhook.py`,
`di/instructions/queue.py` (approval hook). Test: Create `tests/test_triggers.py`.
**Interfaces:** `due(s, now) -> list[tuple[str, str]]` (workflow id, trigger label) for published, not paused
workflows: schedule (`lastAt + min`), event (a webhook for the bound source), file (a file landed for an `x_trig`),
approval (an instruction queued for the outbound workflow's target), case (a case request). Enqueues `workflow.run`
with `dedupe_key = "wf:" + id`.
- [x] Tests: a 30-min schedule runs at +30 min (pinned clock), not before; paused does not run; a webhook runs the
  bound workflow with trigger *Event*; the UI text *"It runs on its trigger"* is now true. Commit.

### Task C7: retries, one run at a time, alerts
**Files:** Modify `di/workflow/engine.py`, `di/actions/workflows.py` (`run`, `run_job`, `_alert`), `Canvas.tsx:454`
(Try column from the record). Test: extend `tests/test_workflow_engine.py`, `tests/test_workflow_extras.py`.
- [x] Tests: `test_one_run_at_a_time` (Review Focus 4); a step that raises is retried `w.retries` times with backoff
  1 s, 2 s, 4 s and the run shows the real attempts; the alert rules fire on real failures; a crashed job clears
  `running` (the reaper from plan 2 marks the run `failed: worker lost`). Commit.

### Task C8: versions, real history and reprocess
**Files:** Modify `di/actions/workflows.py` (save/publish store every version; `workflow.restore`; runs use the
**published** version), `di/screens/workflows.py:127-176` (history from stored runs only), `workflow.reprocess` and
`applyFix`. Web: History tab lists versions with *Compare* and *Restore*. Test: extend `tests/test_workflow_extras.py`.
- [x] Tests: v0.2 and v0.3 both restorable; a run uses the published version even with an unsaved or saved draft;
  history shows only runs that happened; Reprocess sends held records through the steps after the one that rejected
  them and marks them `reprocessed` or keeps them held; *Apply fix* restores the last good version's settings of the
  failed block (no canned text). Commit.

### Task C9: drafts on the server and an honest test run
**Files:** Modify `apps/web/src/pages/workflows/draftStore.ts` (autosave to `workflow.draft.save` every 2 s of quiet),
`WorkflowPage.tsx:93-130` (Test run calls `workflow.testRun`, a dry run of the draft); Create those two actions.
Test: extend `draftStore.test.ts`, `tests/test_workflow_engine.py`.
- [x] Tests: a reload keeps the draft; Test run shows real per-step counts and before/after samples and writes nothing;
  the browser `setTimeout` simulation is deleted. Commit.

### Task C10: live source state in the checks, palette gaps, import
**Files:** `di/actions/workflows.py:174-184` (checks read `source_system`, not golden `SOURCES`),
`Canvas.tsx:139-158` (add x_env, x_flag), `workflow.import` (JSON, the export's shape, validated). Test: extend
`tests/test_writes_workflows.py`.
- [x] Tests: pausing a source shows *Paused upstream* on its workflows from the server; importing an export recreates
  the workflow as a draft; an import with an unknown block is refused with its name. Commit.

**Phase C gate.** Plus, in Chrome as Developer: build the CRM workflow by hand (currency EUR, dedupe on
`opportunity_id`), Test run (real samples), Publish, wait for its schedule, see a real run with real counts; break a
validation rule, see held records, fix, Reprocess.

## Phase D: operate it

### Task D1: Monitor per step and per run
**Files:** `screens/integration.py` (Monitor: per-workflow success, p95 duration per step, held records by rule).
- [x] Tests on seeded runs. Commit.

### Task D2: browser suite for the Fabric
**Files:** Create `apps/web/scripts/smoke-fabric.mjs` (connect a catalogue system, rotate, edit mapping, resolve a
conflict, import, build/publish/run a workflow, reprocess), referenced from `docs/agents/testing.md`.
- [ ] Runs green twice in a row on a reset stack. Commit.

### Task D3: docs and runbook
**Files:** `docs/guides/connection-fabric.md`, `docs/guides/workflow-tutorial.md` (settings, real runs; remove "all
simulated" caveats that no longer apply, keep the synthetic-vendor statement), `docs/agents/runbook-fabric.md` (key
rotation, a stuck run, a failing source, replaying held records), `docs/backend-steps.md` B17b.
- [ ] Commit.

**Phase D gate** = the plan's done line in `00-overview.md`.

## Order and size

A (7 tasks) → B (5) → C (10) → D (3). Rough size: A 4–5 days, B 2–3, C 6–8, D 2. Phase A first because the engine
in C reads through A's connections and mapping; B before C because the engine holds failed records in B1's table.
