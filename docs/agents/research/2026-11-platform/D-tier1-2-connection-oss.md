# D. Tier 1 + 2 connection layer: open-source options (24 Nov 2026)

Scope: the Connection Fabric (adapters, formats, mappings, quality, CDC) and the Workflow Studio (engine, JSON
contract, canvas). Context and rules: [00-brief.md](00-brief.md). Licence findings in this report need review by
Kinective's Legal team before anyone relies on them.

## Summary

1. **Keep our workflow engine.** Every candidate brings a second runtime/state store; n8n (Sustainable Use), Windmill
   (AGPL) and Activepieces EE restrict redistribution. Learn from Kestra, n8n's node I/O panes, Windmill's OpenFlow.
2. **Adapters in hours:** `ConfiguredAdapter` is already a declarative format; extend it with dlt `rest_api` vocabulary
   (Apache-2.0), add an OpenAPI importer; agent drafts spec + mapping, probes a sandbox, dry-runs, a person publishes.
   Don't ship PyAirbyte (ELv2) or Singer taps (many AGPL-3.0); Airbyte manifests (CDK MIT) are a reference/importer.
3. **Workflow JSON:** keep ours, publish a versioned JSON Schema generated from `blocks.py`; structured output,
   validator chain, repair loop, auto-layout, dry run. Open Workflow Spec 1.1 and Arazzo 1.1: export/import only.
4. **Canvas:** `@xyflow/react` (MIT, v13) + `@dagrejs/dagre` (MIT) or `elkjs` (EPL-2.0/GPL-3.0, flag); per-node
   before/after samples from the existing dry run.
5. **Quality:** pydantic + our rule codes for hold-and-explain; pandera for back-test imports; avoid GX and Soda Core
   (now Elastic License 2.0). **CDC:** not needed now; Debezium Server only as an optional customer-run sidecar.

## 0. What we have today (grounding)

Read for this report (no code changed):

| Piece | File | What it already does | Gap relevant here |
|---|---|---|---|
| Block catalogue | `backend/di/workflow/blocks.py` | `BlockSpec` / `FieldSpec` per block (`conn`, `map`, `x_val`, `x_fx`, `x_utc`, `x_late`, `x_branch`, `x_wait`, `x_case` ...), typed settings, defaults, `cfg_errors` naming block + field | Not published as JSON Schema; no typed record ports (input/output shape per block) |
| Engine | `backend/di/workflow/engine.py` (779 lines) | Runs the graph over real records; states, retries with backoff, error branches, held records (`failed_record`), waits parked as jobs, dry runs with before/after samples (`SAMPLE_N = 3`), progress callback, sync lock; a sync *is* the source's ingest workflow | No expression language beyond `x_expr`; no per-node pinned test data; graph positions stored in the contract |
| Configured adapter | `backend/di/connectors/configured.py` | Declarative HTTP connector from the connection row: resources (path, id_field, delta_param, changed_field), paging (offset/page/cursor, items/next/total keys), auth (none, api_key, bearer, basic, oauth_cc) | No dependent (parent → child) resources, no link-header paging, no record selector paths beyond `items_key`, no rate-limit hints, no non-JSON bodies |
| Mapping | `backend/di/connectors/mapping.py` | Versioned `MapRow(src, model, field, rule, resource)`, rules copy/upper/number/date/utc/units/fx/code/prefix; missing field fails one record | No confidence or provenance per row (who/what proposed it) |
| Discovery / probe | `discover.py`, `probe.py` | Column inference from the newest 200 raw records, FK suggestions (≥ 90 % key overlap); probe dns → tcp → tls → auth → perms → read | Discovery needs records already landed; no OpenAPI-based discovery |
| MCP source | `mcp_client.py` | One MCP tool call → rows, mapped like a configured source (`mcp==2.3.0`) | No `tools/list`-driven discovery; single tool per resource |
| Build with AI | `services/actions/workflow_builder.py` | Keyword rules (`AF_WF_KW`, `read_prompt`) insert known blocks into the default ingest graph; validates | Not an LLM; cannot express a new topology |
| Canvas | `frontend/src/pages/workflows/Canvas.tsx` (532 lines), `modeler/FlowCanvas.tsx` | Hand-built: fixed world width, `transform: scale(z)`, scroll container, minimap, drag-connect | Scrollbars, no infinite pan, no auto-layout; frontend has no graph library (`package.json`: react, react-router, react-query only) |

Graph contract today: nodes `{id, k, ref, x, y, cfg?, ai?, fail?}`, edges `{id, a, b, locked}`.

Takeaway: the shape of a good answer already exists in-house. The work is to widen the declarative formats, give them
schemas an LLM can target, and wrap generation in the hold-for-a-person flow we already have for agents.

## 1. Adapter generation in hours

### 1.1 Options

| Option | Licence | Runtime | Embed in Python? | Latest release | Fit |
|---|---|---|---|---|---|
| Airbyte declarative manifest (low-code CDK, `airbyte-python-cdk`) | MIT (CDK repo) | Python | Yes, as a library (`airbyte_cdk` reads a manifest and emits Airbyte protocol messages); dependency weight not measured, **unconfirmed** | v7.49.0, 16 Nov 2026 | Richest declarative REST vocabulary (requesters, paginators, record selectors, transformations, incremental sync, parent streams); manifest validated against a JSON Schema shipped in the CDK |
| Airbyte Connector Builder UI + AI Assist | Platform is Elastic License 2.0; AI Assist documented as beta in 1.6 docs | Airbyte platform (server) | No | n/a | Learn from: "paste docs URL or OpenAPI → prefilled manifest → test streams → publish" |
| `airbyte-connector-builder-mcp` | Not stated on PyPI, **unconfirmed** | Python MCP server | Tooling for agents (validate manifest, test stream) | 0.7.2, 18 Mar 2026 | Learn from the tool split an agent needs |
| PyAirbyte | **Elastic License 2.0** | Python | Yes | 0.71.3 (date not read) | Avoid as a shipped dependency: ELv2 forbids offering it as a hosted/managed service; blocks a later SaaS |
| Airbyte connector catalogue | Per connector (repo root is ELv2; the licence FAQ says own connectors "remain open-source" but does not name the licence) | — | — | — | Use only as reference; check each connector's own licence field, **unconfirmed** |
| dlt `rest_api` source | Apache-2.0 | Python | Yes; resources are plain iterables, so they can be read without a dlt destination | dlt 1.32.0, 29 Oct 2026 | Compact dict config: `client` (base_url, auth, paginator), `resource_defaults`, `resources`; paginators json_link, header_link, header_cursor, offset, page_number, cursor, single_page, auto; auth bearer, http_basic, api_key, oauth2_client_credentials; incremental placeholders; dependent resources `resources.<parent>.<field>` |
| `dlt-init-openapi` | Apache-2.0 (dlt org, **unconfirmed** for this repo) | Python CLI | Generator, run at design time | Tracks dlt docs 1.32.0 | OpenAPI 3.x → `rest_api` config with heuristics for paging, primary keys, data selectors, parent/child; OAuth not native, OpenAPI 2.0 basic |
| Meltano Singer SDK | Apache-2.0 | Python | Taps are separate processes speaking Singer JSON lines | v0.54.9, 19 Oct 2026 | Python classes, not declarative; good stream/paging base classes |
| Singer taps (singer-io) | Many **AGPL-3.0** (e.g. tap-salesforce) | Python processes | — | — | Avoid shipping |
| `openapi-python-client` | MIT | Python codegen | Generates a typed client package | v0.30.0, 7 Nov 2026 | Generates code a person must review and we must ship; good for one-off typed write adapters, not for config-driven reads |
| MCP servers as sources | Protocol spec; servers vary | Any | Already: `mcp_client.py` | Current spec revision 2026-07-28 (handshake-free, `server/discover`); our SDK `mcp==2.3.0` | Fast path where a vendor ships an MCP server; tool descriptions are untrusted input |
| LLM-assisted generation from API docs | — | Our LLM port | Yes | — | Use to fill the spec + mapping; never to emit executable code |

### 1.2 Assessment

- **Our format vs. adopting one.** `ConfiguredAdapter` covers the 80 % case (paged JSON lists with an id and an updated
  timestamp). Adopting the Airbyte CDK as the runtime would add a large framework with its own message protocol,
  state format and concurrency model beside our engine's cursors (`sync_cursor`) and raw-record store. dlt `rest_api`
  is lighter and its config is close to ours, but dlt also brings pipeline state and schema evolution we would bypass.
  **Recommendation:** keep `ConfiguredAdapter` as the runtime and extend its spec with the missing concepts, copying
  dlt's names where they fit (they are short, documented, and LLMs have seen many examples):
  - paginators: add `header_link` (RFC 8288 `Link`), `json_link` (next URL in body), `header_cursor`, `single_page`;
  - `data_selector` (JSONPath into the body) instead of only `items_key`;
  - dependent resources: `path: "/orders/{resources.orders.id}/lines"` with `include_from_parent`;
  - incremental: `{cursor_path, initial_value, param}`; per-resource `rate_limit` and `retry_after` honouring;
  - response formats: JSON, NDJSON, CSV, XML (section 2), routed to the same `Record`.
  Effort: 6–9 days including tests against source-sim's generic mocks.
- **Importers, not runtimes.** Two design-time importers raise the hit rate of generation:
  1. *OpenAPI → spec*: walk `paths` for GET list operations, infer paging params (`limit/offset/page/cursor`), the
     array path in the 200 response schema, id field (`id`, `*_id`, `required` + unique), auth from
     `securitySchemes`. Same heuristics `dlt-init-openapi` documents; write our own (≈ 400 lines) or run
     `dlt-init-openapi` at design time only and translate its output (no runtime dependency). Effort: 4–6 days.
  2. *Airbyte manifest → spec* (later): many manifest-only connectors exist; a translator for the common subset
     (DeclarativeStream, HttpRequester, DpathExtractor, Default/Cursor paginators, DatetimeBasedCursor) gives reference
     specs for known SaaS systems. Check each connector's licence before importing its manifest. Effort: 5 days.
- **Code generation** (`openapi-python-client`): use only for write adapters (instructions out: sales order, transfer,
  work order) where typed request bodies matter, and treat generated code as code a person reviews in a PR. Not part of
  the agent's runtime path.
- **MCP as a source.** Extend `mcp_client.py` with discovery: `tools/list` (or `server/discover` on 2026-07-28
  servers), keep only tools a person allows, use the tool's `outputSchema` as the resource schema, map rows as today.
  Treat `readOnlyHint` annotations as hints, not guarantees; tool descriptions are data, not instructions (prompt
  injection). Effort: 3 days.
- **Singer/Meltano:** a process-per-tap model fits a data warehouse, not our per-record hold/explain path. Learn from
  the SDK's stream base classes; avoid the taps (licences vary, many AGPL).

### 1.3 Proposed agent flow: spec → manifest → probe → mapping draft → test run → a person publishes

Every step is an action through the pipeline (`POST /api/actions/{id}`), journalled with provenance (`agent`, model,
prompt hash, inputs). Nothing an agent produces is live until a person publishes it.

| Step | Who / what | Output | Safety rule |
|---|---|---|---|
| 1. Intake | Person names the system, gives docs URL / OpenAPI file / sample payloads / MCP endpoint | `adapter_draft` row (state `draft`) | URLs come from the person, never from fetched content |
| 2. Spec draft | Agent: OpenAPI importer first; LLM fills gaps from docs text with **structured output against the spec's JSON Schema** | Draft spec + rationale per field + confidence | LLM never sees credentials; output is data validated by schema, never code |
| 3. Static checks | Validator: schema, URL host = connection host, only GET/HEAD for reads, paging terminates, no secrets in spec | Errors back to the agent for repair (max 3 rounds) | Deterministic |
| 4. Probe | Existing `probe_connection` (dns, tcp, tls, auth, perms, read) on a **sandbox** connection; then read ≤ N pages per resource | Probe report; sample records in a quarantined raw store (`dry`) | Egress allow-list = the connection's host; read-only methods; rate limit + page cap + time budget; credentials stored by a person (encrypted, `secrets.py`) |
| 5. Discovery | `discover.py` on the sample (types, keys, FKs) | Source tables | — |
| 6. Mapping draft | Section 3: candidates + LLM choice + rule per field | `MapRow` set with `confidence`, `why`, `proposed_by` | Low-confidence rows marked "needs a person"; required canonical fields unmapped = blocking warning |
| 7. Test run | `workflow.testRun` dry run of the default ingest graph with the draft spec + mapping | Per-step counts, before/after samples, held records with reasons | Writes nothing (engine dry mode) |
| 8. Proposal | Agent files a proposal (existing proposals service) with diff, probe report, test run, open questions | Held for a person | `adapter.publish` / `source.publish` must be on `FORBIDDEN_ACTIONS` for agents |
| 9. Publish | Person (maker) submits, another (checker) approves for production connections | Versioned spec + mapping | Maker-checker as in the Modeler |
| 10. Watch | Health states, first-sync diff vs. test run; auto-pause on error spike | Alerts in "My work" | Rollback = previous spec version |

Eval harness (makes "hours" measurable): the 21 source-sim mocks already have hand-written adapters and demo mappings.
Generate a spec + mapping for each from its OpenAPI (source-sim's FastAPI apps publish one, **unconfirmed** for every
vendor mock) and compare records and facts with the hand-written adapter's output. Metrics: share of resources read
correctly, mapping precision@1, records held, minutes of person time. Target for the pilot: ≥ 80 % of resources right
first time on the generic mocks; a person fixes the rest in < 2 hours.

## 2. Formats

### 2.1 EDI

Reverse-logistics EDI that matters: X12 **180** (return merchandise authorization and notification), 850/855 (orders),
856 (ship notice), 810 (invoice), 940/945 (warehouse shipping order/advice), 997/999 (acknowledgements); EDIFACT
RETANN / RETINS (return announcement / instruction), DESADV, INVOIC, ORDERS. Message names are from general knowledge,
**unconfirmed** in this session against the standards bodies' current releases.

| Library | Licence | Latest | Scope | Verdict |
|---|---|---|---|---|
| `pydifact` | MIT | 0.2.3, 10 Apr 2026 (repo pushed 23 Nov 2026) | EDIFACT parse/serialise, segments and service string advice; no message-level directories | **Adopt** for EDIFACT tokenising |
| `pyx12` | BSD (PyPI classifier; GitHub licence shown as "Other") | 4.1.0, 6 Nov 2026 | X12 parser + validator with maps, focused on HIPAA healthcare transactions | Learn from; its maps do not cover supply-chain sets |
| LinuxForHealth `x12` | Apache-2.0 | repo pushed 19 Sep 2026 | Pydantic models for healthcare 005010 sets | Avoid for our sets (healthcare only) |
| `badx12` | MIT | 0.2.2, 7 Dec 2018 | X12 → dict/JSON | Avoid: unmaintained |
| Bots (`bots-ediint`) | **GPL-3.0** | 3.3.1 on PyPI, Jul 2019 (development on GitLab, newer status **unconfirmed**) | Full EDI translator server (X12, EDIFACT, XML, CSV, AS2-ish channels) | Avoid embedding (GPL, server, Python 2 heritage); learn from its grammar files |

**Recommendation.** X12 has a simple envelope: the ISA segment fixes the element, sub-element and segment separators
at fixed positions. A thin in-house tokenizer (ISA/GS/ST envelopes → segments → elements, ≈ 200 lines + tests)
producing `{"ST": ..., "BGN": [...], "loops": [...]}` dicts lets our existing `MapRow` dotted paths do the mapping, with
per-transaction "loop maps" as data files (180, 856 first). Use `pydifact` for EDIFACT. Generate 997/999 and CONTRL
acknowledgements as an outbound instruction. AS2 transport is out of scope (customers' EDI VANs drop files to SFTP,
which we already read). Effort: X12 tokenizer + 180/856 maps 5–7 days; EDIFACT via pydifact 3 days.

### 2.2 XML

- `lxml` (BSD) with `defusedxml` (PSF licence) rules: no external entities, no DTD fetch, size limits (XXE and
  billion-laughs). Licences from general knowledge, **unconfirmed** this session.
- `xmlschema` (MIT, **unconfirmed**) to validate against a vendor XSD and to convert XML → dict deterministically.
- `xsdata` (MIT, **unconfirmed**) to generate dataclasses from an XSD at design time, if a write adapter needs typed XML.
- Map with `MapRow` paths after conversion to dict; add an `xml` response format to `ConfiguredAdapter` and an XPath
  option for `data_selector`. Effort: 3 days.

### 2.3 Messy CSV and schema inference

Problems seen in file drops: encodings (cp1252, UTF-16 with BOM), delimiter guessing, header row not first, merged
header rows, thousands separators and decimal commas, dates in mixed formats, trailing totals rows.

| Tool | Licence | Use |
|---|---|---|
| `charset-normalizer` | MIT (**unconfirmed**) | Encoding detection (already a transitive dependency of many HTTP libs) |
| `clevercsv` | MIT (**unconfirmed**) | Dialect detection, better than `csv.Sniffer` on messy files |
| DuckDB `read_csv` sniffer | MIT (**unconfirmed**) | Strong sniffer + type inference, in-process; adds a second query engine, so use only at design time if at all |
| `genson` | MIT (**unconfirmed**) | JSON Schema from sample records, to store the inferred schema next to `discover.py`'s table model |
| `frictionless` | MIT (**unconfirmed**) | Table Schema inference + validation; heavier than we need |

**Recommendation.** A `x_file` pre-step "sniff" that records encoding, dialect, header row, locale (decimal, date
order) as settings a person can confirm, then parses with the stdlib `csv` module; emit a JSON Schema of the result
via `genson` so discovery works before any record lands. The LLM may propose the sniff settings from the first 50
lines, validated by parsing. Effort: 4 days.

## 3. AI-assisted schema mapping to the canonical model

### 3.1 Approaches

1. **Lexical / embedding similarity** of field names + descriptions (source field ↔ canonical field). Cheap, weak on
   vendor codes (`EKPO-NETPR`).
2. **Instance-based matching**: compare value profiles (type, length, pattern, range, distinct count, overlap with
   known code tables). Valentine (Apache-2.0, Python, repo pushed 21 Nov 2026) packages classic matchers (COMA-style,
   Cupid, Similarity Flooding, distribution-based, Jaccard) as an experiment suite; matcher list from general knowledge,
   **unconfirmed** for the current release.
3. **LLM with retrieval (recommended)**: for each source field, retrieve top-k canonical candidates using 1 + 2, then
   ask the LLM to choose one or abstain, and to name the rule (`units:kg>t`, `fx:INR`, `code:grade`, `utc`), with a
   one-line reason. Output is structured (JSON Schema of `MapRow` + `confidence` + `why`), validated, then applied to
   the sample records so a person sees the normalised value before accepting.
4. **Learning from accepted mappings**: every mapping a person accepts or corrects becomes a few-shot example and a
   synonym entry (per vendor family: "NETPR" → amount). This is where the moat grows.

Guardrails: the LLM gets field names, types and at most a few **masked** sample values (no personal data; the
organisation's rule on personal information applies to customer end-customer data); the vendor's free-text docs are
data, not instructions.

### 3.2 Libraries

- Valentine: adopt as an offline baseline and feature source (Apache-2.0); don't put it in the request path until its
  dependency weight is checked (**unconfirmed**).
- Embeddings: through our LLM port (provider-neutral); a local small embedding model is an option for air-gapped
  customers (licence per model).
- Everything else in-house (≈ 600 lines): candidate retrieval, prompt, validation, apply-to-sample.

### 3.3 Evaluation method

- Gold set: the demo's mappings for the 21 sources (`fixtures/golden/`, the Data Mapping rows) plus the canonical
  fields per template pack (industrial, tool fleet, device). Hold out by vendor family.
- Metrics: precision@1 and recall@3 of canonical field; rule accuracy; abstention rate and precision of
  non-abstained answers; share of records that pass canonical checks after mapping; person minutes to finish.
- Gate: auto-accept nothing in production; pre-tick suggestions with confidence ≥ a threshold calibrated on the gold
  set so that precision ≥ 95 %; everything else "needs a person". Re-run the eval on every prompt or model change
  (fits the "LLM resilience" fallback: each fallback model must pass the same eval).
- Effort: 6–8 days (retrieval, prompt, schema, UI hooks in the Data Mapping tab, eval script).

## 4. Data quality: hold the record and explain

| Tool | Licence | Latest | Model | Fit for per-record hold + reason |
|---|---|---|---|---|
| pydantic v2 | MIT (**unconfirmed** this session; long-standing) | — | Record-level models, error list with location + message | **High**: already in the stack; errors map to "field X: reason" |
| pandera | MIT | v0.36.0, 10 Nov 2026 ("ParsedColumns/Fields and Decisions API") | DataFrame schemas (pandas, polars, others), row-level failure cases | Medium: good for batch files and back-test imports; brings pandas/polars |
| Great Expectations (GX Core) | Apache-2.0 | 1.25.0, 12 Nov 2026 | Expectation suites, checkpoints, data docs, its own context/stores | Low: dataset-level, heavy, second config/store |
| Soda Core | **Elastic License 2.0** (repo LICENSE file read 24 Nov 2026; repo describes itself as a "Data Contracts engine"); earlier v3 releases were Apache-2.0 per general knowledge, change date **unconfirmed** | v4.31.0, 17 Nov 2026 | YAML data contracts, SQL-pushdown checks, telemetry | Avoid: licence change + warehouse-oriented |

**How they fit.** Our checks are per record and must say *why* a record is held and *who* can release it
(`failed_record`, `x_val` rules present/type/regex/range/in, canonical checks in `services/canonical/schema.py`). That is
a row-level, explanation-first need. Dataset tools (GX, Soda) answer "is this table healthy?" and produce reports,
not per-record holds.

**Recommendation.**
- Keep the `x_val` rule vocabulary and canonical checks as the source of truth; give every check a stable code
  (`DQ.RANGE`, `DQ.MISSING`, `DQ.CODE_UNKNOWN`), a message template and an owner role, so the hold reason and the
  release path are data.
- Generate a JSON Schema per canonical model from pydantic models, so the same checks are published to agents and to
  the adapter generator (section 1) and to customers as "data contracts".
- Add batch-level checks (volume drop, null-rate jump, duplicate keys, freshness) as a small set of our own monitors
  computed per sync run (counts we already keep), raising source health warnings. Use pandera only in the back-test
  import path (CSV of a quarter's returns), where dataframes are natural. Effort: 4–5 days.

## 5. CDC

| Option | Licence | Runtime | Latest | Note |
|---|---|---|---|---|
| Debezium (embedded / Kafka Connect) | Apache-2.0 | JVM; Kafka for Connect | 3.7.0.Final GA end of Sep 2026 (per debezium.io tag page), 3.7.1.Final maintenance, 3.8.0.Alpha2 tag | Most connectors (Postgres, MySQL, SQL Server, Oracle, Db2 ...); needs JVM |
| Debezium Server | Apache-2.0 | JVM process, no Kafka | Same series | Sinks include HTTP; could post change events to our webhook endpoint |
| Postgres logical decoding (pgoutput, wal2json, test_decoding) | PostgreSQL licence | In the database | — | psycopg 3 has **no** replication-protocol support (listed as planned; issue #71); options: psycopg2 `ReplicationCursor`, asyncpg, or polling `pg_logical_slot_get_changes()` over plain SQL |
| pgstream | Apache-2.0 | Go | repo pushed 20 Nov 2026 | Postgres → targets incl. webhooks, DDL-aware |
| Sequin | MIT | Elixir | repo last pushed 23 Feb 2026 (activity slowing, **unconfirmed** status) | Postgres CDC to queues/HTTP |
| PeerDB, Estuary | ELv2 / BSL family (**unconfirmed**) | Go / Rust | — | Avoid for redistribution |

**Do we need it?** Not for the pilot.
- Our sources are enterprise *applications* (ERP, WMS, EAM ...). Customers rarely grant log-level access to an ERP
  database, and reading vendor tables bypasses the vendor's business logic. APIs, webhooks, event exports and file
  drops are the supported paths, and we have them (delta cursors, webhooks, SFTP).
- For a customer-owned database (a home-grown returns DB), add a **SQL query connector** with an `updated_at`/rowversion
  cursor (query-based CDC): no deletes, but no new runtime. Effort: 4 days.
- For our own outbound events, keep the transactional outbox + `LISTEN/NOTIFY` pattern of the job queue; no WAL reading.
- If a customer insists on log CDC: document **Debezium Server as an optional sidecar** they run, posting to our
  webhook endpoint (signed, idempotent by LSN/offset). We do not ship a JVM in the trial package.

## 6. iPaaS / workflow OSS: embed, learn from, or avoid

| Project | Licence | Runtime | Latest | Embed? | Verdict |
|---|---|---|---|---|---|
| n8n | **Sustainable Use License 1.0** + n8n Enterprise License for `.ee.` files | Node/TS server | n8n@2.49.5, 23 Nov 2026 | No | **Avoid embedding/shipping**: use limited to internal business purposes or non-commercial; distribution only free of charge and non-commercial. **Learn from** its node input/output panes, pinned data, expression editor |
| Activepieces | MIT core; `packages/ee` under a commercial licence (production use needs an enterprise agreement) | Node/TS server | 0.93.0, 8 Nov 2026 | No | Learn from the "pieces" framework (typed actions/triggers, auth as data); avoid as a runtime |
| Windmill | **AGPLv3** default + proprietary EE code; client libraries and OpenAPI/**OpenFlow spec Apache-2.0** | Rust + Postgres | v1.883.0, 24 Nov 2026 | No | Avoid embedding (AGPL network clause in a shipped product); **learn from OpenFlow** JSON (Apache-2.0) and its Postgres-only queue design |
| Kestra | Apache-2.0 (Enterprise Edition separate) | Java server; Postgres backend possible | v2.0.11, 17 Nov 2026 | No | **Learn from**: declarative YAML flows validated by a published JSON Schema, plugin-typed tasks, AI flow generation over that schema. Avoid the JVM in our stack |
| Node-RED | Apache-2.0 | Node.js | 5.0.10, 17 Nov 2026 | No | Learn from flow JSON export/import and debug sidebar; avoid |
| Apache Hop | Apache-2.0 | Java | 2.20.0-rc1, 27 Oct 2026 (latest final **unconfirmed**) | No | Avoid (desktop-first ETL, JVM) |
| Apache NiFi | Apache-2.0 | Java | tag rel/nifi-2.12.0 (date **unconfirmed**) | No | Learn from data provenance per flowfile and back-pressure; avoid |
| Apache Camel | Apache-2.0 | Java | tag camel-4.23.0 (date **unconfirmed**) | No | Learn from Enterprise Integration Patterns vocabulary and YAML DSL schema; avoid |
| DBOS Transact (Python) | MIT (**unconfirmed** this session) | Python library on Postgres | 3.6.0, 17 Nov 2026 | Possible | Learn from: durable steps checkpointed in Postgres; not needed while our job queue + waits cover resumption |

### Should we replace our own workflow engine? **No.**

1. **It is the data path.** A sync *is* the run of the source's ingest workflow (`sync.py` → `run_graph`), with parity
   tests on canonical output, held records, cursors, the sync lock and dry runs. Replacing it means re-proving every
   number against the demo.
2. **Every candidate adds a second control plane.** Each brings its own state store, API server, auth, scheduler and
   (mostly) a JVM or Node runtime. The agent-foundation decision says: no second state store, approval store,
   workflow engine or API server.
3. **Licences.** The most capable embeddable-looking options restrict what matters to us: n8n (Sustainable Use),
   Windmill (AGPL + proprietary), Activepieces EE (commercial). The permissive ones (Kestra, NiFi, Camel, Hop) are JVM.
4. **Our differentiator is policy on records**, not breadth of SaaS nodes: tenant boundary, warehouse lock, hold and
   explain, action pipeline, journal, agent forbidden list. These would have to be rebuilt as plugins inside someone
   else's engine.

**Close these gaps instead** (≈ 15–20 days in total):
- typed ports: each `BlockSpec` declares input/output record schema (JSON Schema), so the validator and the canvas can
  check edges and the LLM knows what flows where;
- a small, safe expression language for `x_expr`, `x_branch`, `x_wait.until` (JSONata or a CEL subset; pick one with
  a Python implementation, licence check needed) instead of ad-hoc strings;
- per-node pinned test data and replay from a node (n8n-style), built on the existing dry run and `resume` machinery;
- engine version + block catalogue version stamped on every workflow version, for safe upgrades;
- concurrency limits per source and back-pressure (NiFi lesson) via the job queue's priorities.

Revisit only if a customer needs hundreds of SaaS connectors we will never build: then integrate *beside* us (the
customer's own iPaaS posts to our webhook / calls our MCP or API), never inside.

## 7. Declarative workflow JSON as the contract agents generate

### 7.1 Standards considered

| Standard | Status (dates) | What it models | Fit for our ingest/ETL graphs |
|---|---|---|---|
| Serverless Workflow, renamed **Open Workflow Specification** in v1.1.0 | v1.1.0 released 12 Nov 2026; DSL reference + `schema/workflow.yaml`; Python SDK repo last pushed 4 Nov 2025 | Task-oriented orchestration: call (http, openapi, asyncapi, grpc), do, for, fork, switch, try/catch, wait, emit/listen, set; jq expressions | Medium-low: good for service orchestration, weak for record-level ETL (units, FX, dedupe, hold); Python SDK stale |
| OpenAPI **Arazzo** | 1.0.0 25 Sep 2024; 1.0.1 20 Jan 2025; **1.1.0 18 May 2026** (AsyncAPI v3, JSONPath/XPath, `$self`) | Sequences of API calls across OpenAPI/AsyncAPI descriptions with success criteria | High **for adapters** (multi-call reads: auth → list → detail), low for workflows |
| BPMN 2.0 XML | Stable OMG standard (no change found) | Business processes, human tasks, gateways, events | Low for ETL; possible export for Tier 3 business flows; verbose XML, poor LLM target |
| Windmill OpenFlow | Apache-2.0 spec in the Windmill repo | Steps of scripts with input transforms | Learn from |
| Kestra flow YAML | Apache-2.0 | Typed tasks + JSON Schema | Learn from |

**Recommendation.** Keep our own JSON and make it a real contract:
- `schemaVersion`, `$id`-addressed **JSON Schema published at `/api/schemas/workflow/{version}`**, generated from
  `blocks.py` (one source of truth): a discriminated union on `k` (and on `ref` for `xf`), `cfg` per block from its
  `FieldSpec`s (enums from `choices`, min/max, required), edges with optional `port` (`else`, `error`).
- Split **logic from layout**: `x, y` become optional; a separate `layout` object; graphs without positions are
  auto-laid out. Keeps diffs and LLM output small.
- Keep **connection workflows separate from decision flows** (team ask 12): two schemas, two catalogues.
- Interop: an exporter to Open Workflow Spec for orchestration-only workflows and an **Arazzo importer** for adapter
  call sequences (section 1). BPMN export only for the Modeler, if a customer asks. Effort: schema generation + endpoint
  3 days; layout split 3 days (migration of stored graphs, canvas reads both); exporters later.

### 7.2 Making LLM generation reliable

1. **Two-stage output.** Stage A: a compact plan (list of blocks with intent, sources by id, edges) as structured
   output against a *reduced* schema (no positions, no defaults). Stage B: fill `cfg` per block against that block's
   `FieldSpec` schema, given the source's discovered fields. Small schemas fit providers' strict structured-output
   limits better (exact limits per provider/model **unconfirmed**).
2. **Structured output where the provider supports it**, else tool-call with the schema as parameters, else JSON mode +
   parse. Via Pydantic AI output types (already the chosen agent library), behind our provider port, with model
   fallback (team ask 9).
3. **Validator chain**: JSON Schema → `cfg_errors(node, ctx)` with the source's real fields/resources → graph rules
   (`validate`: one trigger, reachable nodes, no cycles except allowed loops, `canLink`) → permission check
   (`readable`/`writable` sources for the caller). Errors return to the model as a list (`node`, `field`, `message`);
   at most 3 repair rounds; then hand to a person with the errors shown.
4. **Grounding**: the prompt carries the block catalogue (labels, one-line help), the caller's readable/writable
   sources and their fields; never free-text from source data as instructions.
5. **Auto-layout** server-side (deterministic layered layout in Python, or `elkjs` on the client) so generated JSON never
   needs coordinates.
6. **Dry run before showing "ready"**: `workflow.testRun` on a sample; show counts and held records.
7. **Diff + person saves.** The draft lands in `workflow_drafts`; nodes keep `ai: 1`; Publish is a person's action.
8. **Eval set**: 50–100 prompts → expected graphs, seeded from the current keyword builder's cases
   (`workflow_builder.read_prompt`) and the demo's workflows. Metrics: schema-valid rate (target 100 % after repair),
   semantically valid rate, topology match, cfg field accuracy, dry-run success. The rule-based builder stays as the
   no-key fallback. Effort: 8–10 days.

## 8. Canvas UI

| Library | Licence | Latest | Notes |
|---|---|---|---|
| `@xyflow/react` (React Flow) | MIT ("open-source MIT-licensed software, and it will be forever", reactflow.dev/pro) | 13.0.3; 13.0.0 announced ~16 Nov 2026 | Infinite pan/zoom viewport, minimap, controls, custom React nodes, handles, sub-flows, node toolbar; v13 needs React ≥ 18 (we have 18.3.1), split stores, React Compiler; Pro = examples + support, no gated library features per the Pro page |
| Rete.js | MIT | repo pushed 22 Nov 2026 | Framework-agnostic visual programming with a dataflow engine; smaller ecosystem |
| JointJS (core) | **MPL-2.0** (file-level copyleft); JointJS+ commercial | repo pushed 24 Nov 2026 | SVG diagramming, strong for BPMN-like diagrams; less React-native |
| `elkjs` | **EPL-2.0 OR GPL-3.0-or-later** (flag) | 0.12.1, 28 Oct 2026 | Best layered layout with ports and orthogonal edges; runs in a web worker; use unmodified |
| `@dagrejs/dagre` | MIT | 3.1.3 | Simple layered layout, fast, weaker on ports |

**Recommendation.** Adopt `@xyflow/react` for both the Workflow Studio and the Modeler canvas; `@dagrejs/dagre` first
(MIT, simple), `elkjs` if port-aware layout is needed and Legal accepts EPL-2.0. Reasons: React-native custom nodes
(our `NodeMark`, `StateChip` port over), the largest ecosystem and examples, and an infinite viewport without
scrollbars out of the box (pan by drag/trackpad, zoom by wheel/pinch, `fitView`), replacing our fixed-width world +
`scale()` + scroll container.

**Live input/output previews per node.** The engine already returns each step's first 3 records before and after
(`samples`) in a dry run, and `on_step` progress during real runs. Show them:
- on the node: a small badge (records in → out, held), the run state chip;
- in the inspector: tabs *Input* / *Output* / *Held* with a table/JSON toggle (n8n pattern);
- **pin data**: a person or agent can pin a sample as a node's input for repeated test runs (stored in the draft);
- run "from this node" using the `resume` path the Wait step already uses.

**Parity note.** The demo's canvas look is part of parity (golden rule 1). A library swap must keep the demo's node
visuals and texts, or a decision-log entry must accept the change. Effort: Workflow Studio canvas 8–10 days, Modeler
canvas 3–4 days, previews 4–5 days, browser smokes updated 2 days.

## 9. Ranked: adopt / learn from / avoid

| Rank | Item | Verdict | Why |
|---|---|---|---|
| 1 | Own workflow engine + own JSON (published JSON Schema from `blocks.py`) | **Adopt (keep)** | Data path, parity, policy; no second control plane |
| 2 | `@xyflow/react` | **Adopt** | MIT, infinite canvas, custom nodes, previews |
| 3 | `@dagrejs/dagre` (then `elkjs` after Legal review) | **Adopt** | Auto-layout for generated graphs |
| 4 | dlt `rest_api` config vocabulary + `dlt-init-openapi` heuristics | **Adopt the vocabulary / learn from**; optional design-time tool | Apache-2.0, close to our spec |
| 5 | `pydifact` | **Adopt** | MIT, maintained, EDIFACT |
| 6 | pydantic (+ our rule codes) for hold-and-explain | **Adopt (keep)** | Row-level explanations |
| 7 | pandera | **Adopt narrowly** (back-test imports) | MIT, batch checks |
| 8 | Valentine | **Adopt offline** (baseline in mapping eval) | Apache-2.0 |
| 9 | Airbyte declarative manifest (CDK MIT) | **Learn from**; later importer | Richest declarative vocabulary; heavy runtime |
| 10 | Kestra | **Learn from** | Schema-first YAML flows, AI generation over a schema |
| 11 | n8n | **Learn from** (UX only) | Node I/O panes, pinned data; licence blocks shipping |
| 12 | Windmill OpenFlow spec | **Learn from** | Apache-2.0 spec inside an AGPL product |
| 13 | Arazzo 1.1 | **Learn from / import** | Multi-call adapter sequences |
| 14 | Open Workflow Spec 1.1 | **Learn from / export later** | Orchestration semantics; stale Python SDK |
| 15 | Debezium Server | **Optional sidecar, customer-run** | Apache-2.0 but JVM |
| 16 | pyx12 | **Learn from** | Healthcare maps |
| 17 | `openapi-python-client` | **Use for typed write adapters only** | MIT, generated code under review |
| 18 | Activepieces, Node-RED, Camel, NiFi, Hop | **Avoid as runtime**; learn patterns | Second runtime (Node/JVM); Activepieces EE commercial |
| 19 | PyAirbyte, Soda Core | **Avoid** | Elastic License 2.0 |
| 20 | Windmill runtime, n8n runtime, Bots, Singer taps | **Avoid** | AGPL / Sustainable Use / GPL / AGPL |
| 21 | Great Expectations | **Avoid** | Heavy, dataset-level, own stores |
| 22 | `badx12`, LinuxForHealth `x12` | **Avoid** | Unmaintained / healthcare-only |

## 10. Recommended Tier 1 + 2 target architecture

```
              person / agent (MCP, Ask, playbook)          docs URL · OpenAPI · Arazzo · samples · MCP endpoint
                          │  every write: POST /api/actions/{id} (pipeline, forbidden list, journal)
                          ▼
┌────────────── Connection Studio (FastAPI, Postgres only) ──────────────────────────────────────────────┐
│ Adapter generator: importers (OpenAPI, Arazzo, Airbyte-manifest later) + LLM fill (structured output)  │
│   → spec JSON Schema validator → sandbox probe (read-only, egress allow-list) → discovery → mapping     │
│   draft (retrieval + LLM + eval-calibrated confidence) → dry run → PROPOSAL held for a person          │
│                                                                                                        │
│ Runtime adapters: Python adapters (21) │ ConfiguredAdapter v2 (dlt-style paging, selectors, parents,   │
│   formats JSON/NDJSON/CSV/XML) │ file adapters (sniffed CSV, X12 tokenizer, pydifact) │ MCP source     │
│   (discovery via tools/list) │ SQL query-delta source │ webhook intake (also Debezium Server, optional)│
│                                                                                                        │
│ Workflow engine (ours): typed block ports, expression subset, pinned data, replay-from-node,           │
│   held records with DQ codes + owner, dry runs with samples; sync = ingest workflow                    │
│ Contract: workflow JSON + published JSON Schema (from blocks.py), layout separate; OWS export later    │
│ Canonical store + checks (pydantic-generated JSON Schemas = data contracts); conflict queue           │
│ Job queue (Postgres, LISTEN/NOTIFY), outbox for events                                                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                          ▲
   React canvas: @xyflow/react + dagre/elkjs auto-layout, node badges, Input/Output/Held inspector tabs
```

Build order (Tier 1 + 2, ≈ 10–12 weeks for 2 engineers, estimates **unvalidated**):
1. Workflow JSON Schema from `blocks.py` + layout split + validator chain (1.5 weeks).
2. Canvas on React Flow with auto-layout and per-node previews (3 weeks, parity-checked).
3. ConfiguredAdapter v2 + OpenAPI importer + MCP discovery (2.5 weeks).
4. Mapping suggestions with eval harness (1.5 weeks).
5. Agent adapter-generation flow with proposals and `adapter.publish` forbidden for agents (1.5 weeks).
6. Formats: CSV sniffing, X12 180/856, EDIFACT, XML (2 weeks, in parallel).
7. LLM workflow generation (two-stage, repair loop, eval set) (2 weeks).
8. DQ codes + batch monitors; SQL query-delta source (1 week).

## Unconfirmed

- Dependency weight of `airbyte-python-cdk` when embedded; whether manifest-only connectors run with the CDK alone.
- The licence of individual Airbyte connectors (the licence FAQ says "open-source" without naming it) and of
  `airbyte-connector-builder-mcp` (no licence on PyPI).
- Whether every source-sim mock publishes an OpenAPI document usable by the eval harness.
- Exact X12 / EDIFACT message names and versions for returns (180, RETANN, RETINS) against current standards releases.
- Licences of `defusedxml`, `xmlschema`, `xsdata`, `charset-normalizer`, `clevercsv`, DuckDB, `genson`, `frictionless`,
  pydantic and DBOS Transact were not re-checked in this session (stated from general knowledge).
- The date Soda Core moved from Apache-2.0 to Elastic License 2.0; that v3 was Apache-2.0 is from memory.
- Debezium 3.7.0.Final and 3.7.1.Final exact dates (the GitHub releases API returned none; the tag list and a
  debezium.io tag page were used); NiFi 2.12.0 and Camel 4.23.0 release dates; Apache Hop's latest final release.
- PeerDB and Estuary licences; Sequin's maintenance status.
- Valentine's current matcher list and dependencies.
- Structured-output (strict JSON Schema) support and schema-size limits of our hosted inference provider's models.
- React Flow 13.0.0 date inferred from the "What's new" permalink (16 Nov 2026).
- All effort estimates are first-pass and not validated against the team's velocity.

## Sources (all read 24 Nov 2026 unless stated)

Repo (read, not changed): `docs/agents/research/2026-11-platform/00-brief.md`; `backend/di/workflow/blocks.py`,
`engine.py`; `backend/di/connectors/configured.py`, `mapping.py`, `sync.py`, `generic.py`, `discover.py`, `probe.py`,
`mcp_client.py`; `backend/di/services/actions/workflow_builder.py`, `workflow_drafts.py`; `backend/requirements.in`;
`frontend/package.json`; `frontend/src/pages/workflows/Canvas.tsx`.

Adapter generation
- airbyte-python-cdk: GitHub API repo (MIT) and latest release v7.49.0 (published 2026-11-16).
  https://github.com/airbytehq/airbyte-python-cdk
- Airbyte Connector Builder and AI Assist docs: https://docs.airbyte.com/platform/connector-development/connector-builder-ui/overview,
  https://docs.airbyte.com/platform/connector-development/connector-builder-ui/ai-assist (1.6 docs mark it beta)
- Airbyte licence FAQ: https://docs.airbyte.com/platform/developer-guides/licenses/license-faq; Airbyte repo root
  LICENSE (ELv2 text): https://github.com/airbytehq/airbyte/blob/master/LICENSE
- PyAirbyte LICENSE.md (Elastic License 2.0): https://github.com/airbytehq/PyAirbyte; PyPI `airbyte` 0.71.3
- `airbyte-connector-builder-mcp` 0.7.2 (uploaded 2026-03-18): https://pypi.org/project/airbyte-connector-builder-mcp/
- dlt: release 1.32.0 (2026-10-29), Apache-2.0: https://github.com/dlt-hub/dlt; rest_api docs:
  https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic; OpenAPI generator:
  https://dlthub.com/docs/dlt-ecosystem/verified-sources/openapi-generator
- Meltano SDK v0.54.9 (2026-10-19), Apache-2.0: https://github.com/meltano/sdk
- singer-io tap-salesforce, AGPL-3.0 (pushed 2026-11-23): https://github.com/singer-io/tap-salesforce
- openapi-python-client v0.30.0 (2026-11-07), MIT: https://github.com/openapi-generators/openapi-python-client
- MCP versioning, current revision 2026-07-28: https://modelcontextprotocol.io/specification/versioning

Formats
- pydifact (MIT, pushed 2026-11-23; PyPI 0.2.3 2026-04-10): https://github.com/nerdocs/pydifact
- pyx12 (PyPI 4.1.0, 2026-11-06, BSD classifier): https://github.com/azoner/pyx12, https://pypi.org/project/pyx12/
- badx12 (PyPI 0.2.2, 2018-12-07, MIT): https://pypi.org/project/badx12/
- bots-ediint (PyPI 3.3.1, 2019-07-19, GPL-3.0): https://pypi.org/project/bots-ediint/, https://gitlab.com/bots-ediint/bots
- LinuxForHealth x12 (Apache-2.0, pushed 2026-09-19): https://github.com/LinuxForHealth/x12

Mapping and quality
- Valentine (Apache-2.0, pushed 2026-11-21): https://github.com/delftdata/valentine
- pandera v0.36.0 (2026-11-10), MIT: https://github.com/unionai-oss/pandera
- Great Expectations 1.25.0 (2026-11-12), Apache-2.0: https://github.com/great-expectations/great_expectations
- Soda Core v4.31.0 (2026-11-17); LICENSE = Elastic License 2.0: https://github.com/sodadata/soda-core/blob/main/LICENSE

CDC
- Debezium tags (v3.8.0.Alpha2, v3.7.1.Final, v3.7.0.Final): https://github.com/debezium/debezium/tags; 3.7 GA noted on
  debezium.io tag pages, e.g. https://debezium.io/tag/mariadb
- psycopg 3 replication not implemented: https://github.com/psycopg/psycopg/issues/71, https://psycopg.org/features
- PostgreSQL logical replication protocol: https://www.postgresql.org/docs/17/protocol-logical-replication.html
- pgstream (Apache-2.0, pushed 2026-11-20): https://github.com/xataio/pgstream
- Sequin (MIT, pushed 2026-02-23): https://github.com/sequinstream/sequin

Workflow OSS
- n8n LICENSE.md (Sustainable Use License 1.0 + Enterprise files), release n8n@2.49.5 (2026-11-23):
  https://github.com/n8n-io/n8n
- Activepieces LICENSE (MIT outside `packages/ee`) and `packages/ee/LICENSE` (commercial), release 0.93.0 (2026-11-08):
  https://github.com/activepieces/activepieces
- Windmill LICENSE (AGPLv3 default, proprietary EE, Apache-2.0 clients and OpenFlow spec), v1.883.0 (2026-11-24):
  https://github.com/windmill-labs/windmill
- Kestra (Apache-2.0, Java), v2.0.11 (2026-11-17): https://github.com/kestra-io/kestra
- Node-RED (Apache-2.0), 5.0.10 (2026-11-17): https://github.com/node-red/node-red
- Apache Hop 2.20.0-rc1 (2026-10-27): https://github.com/apache/hop; Apache NiFi tags (rel/nifi-2.12.0):
  https://github.com/apache/nifi; Apache Camel tags (camel-4.23.0): https://github.com/apache/camel
- DBOS Transact Python 3.6.0 (2026-11-17): https://github.com/dbos-inc/dbos-transact-py

Workflow JSON standards
- Serverless Workflow / Open Workflow Specification v1.1.0 (2026-11-12):
  https://github.com/serverlessworkflow/specification/releases/tag/v1.1.0; Python SDK (Apache-2.0, pushed 2025-11-04):
  https://github.com/serverlessworkflow/sdk-python
- Arazzo releases 1.0.0 (2024-09-25), 1.0.1 (2025-01-20), 1.1.0 (2026-05-18):
  https://github.com/OAI/Arazzo-Specification/releases

Canvas
- `@xyflow/react` 13.0.3, MIT (npm registry); React Flow 13 notes: https://reactflow.dev/whats-new; Pro:
  https://reactflow.dev/pro
- Rete.js (MIT, pushed 2026-11-22): https://github.com/retejs/rete
- JointJS (MPL-2.0, pushed 2026-11-24): https://github.com/clientIO/joint
- elkjs 0.12.1 (2026-10-28), EPL-2.0 OR GPL-3.0-or-later: https://github.com/kieler/elkjs, npm registry
- @dagrejs/dagre 3.1.3, MIT: npm registry, https://github.com/dagrejs/dagre

## Legal review note

Every licence statement above (MIT, Apache-2.0, BSD, MPL-2.0, EPL-2.0, GPL-3.0, AGPL-3.0, Elastic License 2.0,
Sustainable Use License, Activepieces' and n8n's enterprise licences) is a reading of public licence files and
package metadata on 24 Nov 2026 for engineering triage only. It is not legal advice. Because the trial package is
redistributed to customers, these findings must be reviewed by Kinective's Legal team before anyone relies on or
acts on them, in particular: ELv2 (PyAirbyte, Soda Core), Sustainable Use (n8n), AGPL (Windmill, Singer taps), GPL
(Bots), EPL-2.0 OR GPL-3.0 (elkjs), MPL-2.0 (JointJS) and the Activepieces `ee` terms.
