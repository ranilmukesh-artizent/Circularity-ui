# D. Tier 1 + 2 connection layer: open-source options (24 Nov 2026)

Scope: the Connection Fabric (adapters, formats, mappings, quality, CDC) and the Workflow Studio (engine, JSON
contract, canvas). Context and rules: [00-brief.md](00-brief.md). Licence findings in this report need review by
Kinective's Legal team before anyone relies on them.

## What changed in this revision and why (revision 2, 24 Nov 2026)

The target is now the team's Recover prototype ([01-recover-segments.md](01-recover-segments.md), "01"). Its adapter mapping, adapter registry and
identity-provider access (01 §2) ask for capabilities revision 1 did not cover. **01 is used for its concept only** (capabilities, data, rules, agents): its screens, menus, panels and step tabs are not UI requirements, and this report describes capabilities, not layout.

| Change | What | Why |
|---|---|---|
| **Added** §1.4 | The adapter registry: three connector sources, sign-in types, test → production environments, read-only vs write-back, the credential vault, **system-owner approval**, discovery that samples 500 records, mapping proposals with confidence and a reason, the five person choices, the test run | 01 §2 specifies each of these; revision 1 covered only adapter *generation* |
| **Added** §3.4 | Field-mapping suggestion: embedding-free and LLM-assisted options with licences, dependency weight and a recommended pipeline | 01 asks for a confidence score and a reason per field; revision 1 had only a sketch |
| **Added** §8b | Identity provider access: OIDC sign-in, SCIM 2.0 provisioning, directory groups → roles, sync, checking what a user gets; Python libraries with licences; fit with `core/policy.py` | 01 §2 "Access"; not in revision 1 |
| **Added** rows 23–33 in §9; build-order items 9–10; sources; unconfirmed items; legal list | New libraries and IdP servers | Follows from the three sections above |
| **Updated** §0 discovery row, §1.3 steps 5 and 9 | Discovery samples up to 500 records from the *test* environment (was: the newest 200 already landed); publish needs the system owner's approval as well as maker-checker | 01 §2 "samples 500 records", "the system owner approves the connection" |
| **Updated** §3.2, rank 8 | Valentine stays offline only: its current release pulls PuLP with CBC (`cbcbox`, EPL-2.0, a ~200 MB wheel) | Found in this revision's PyPI check |
| **Updated** Summary (items 6–8), §10 diagram | Registry, identity and mapping pieces | Same |
| **Deleted** | Nothing. Every revision-1 recommendation stands | The new target adds needs; it does not contradict the earlier choices |

**Decisions:** README decision **D3 is unchanged**. This revision proposes one addition to D3 (call it D3b): "OIDC sign-in
with Authlib, SCIM 2.0 provisioning on scim2-models, group → role mapping as data in `policy`, no IdP server in the
trial package". The README is not edited here.

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
6. **Adapter registry (new, §1.4):** one registry of versioned connector entries of three kinds (catalogue, generic
   REST, built once from an API spec), each connection with an environment (test, then production), an access mode
   (read-only or read + write-back), credentials in our vault (write-only), and a **system-owner approval** before it
   goes live or gains write-back. All of it is our own code on Postgres; no new library.
7. **Field mapping (new, §3.4):** in-house pipeline: RapidFuzz (MIT) name scores + value profiles from the 500-record
   sample + a synonym memory of accepted mappings, then an LLM rerank that may abstain. Confidence is calibrated on a
   gold set, and every proposal carries a reason. Valentine and bdi-kit (both Apache-2.0) stay offline: too heavy for
   the image.
8. **Identity (new, §8b):** OIDC sign-in with **Authlib** (BSD-3-Clause), SCIM 2.0 provisioning endpoints of our own
   built on **scim2-models** (Apache-2.0, pydantic), and **scim2-tester** in CI. The group → role mapping becomes data
   in `policy`. No IdP server ships: Keycloak (Apache-2.0) is only a dev/test stand-in; Zitadel is AGPL-3.0 since
   v3 (31 Mar 2025).

## 0. What we have today (grounding)

Read for this report (no code changed):

| Piece | File | What it already does | Gap relevant here |
|---|---|---|---|
| Block catalogue | `backend/di/workflow/blocks.py` | `BlockSpec` / `FieldSpec` per block (`conn`, `map`, `x_val`, `x_fx`, `x_utc`, `x_late`, `x_branch`, `x_wait`, `x_case` ...), typed settings, defaults, `cfg_errors` naming block + field | Not published as JSON Schema; no typed record ports (input/output shape per block) |
| Engine | `backend/di/workflow/engine.py` (779 lines) | Runs the graph over real records; states, retries with backoff, error branches, held records (`failed_record`), waits parked as jobs, dry runs with before/after samples (`SAMPLE_N = 3`), progress callback, sync lock; a sync *is* the source's ingest workflow | No expression language beyond `x_expr`; no per-node pinned test data; graph positions stored in the contract |
| Configured adapter | `backend/di/connectors/configured.py` | Declarative HTTP connector from the connection row: resources (path, id_field, delta_param, changed_field), paging (offset/page/cursor, items/next/total keys), auth (none, api_key, bearer, basic, oauth_cc) | No dependent (parent → child) resources, no link-header paging, no record selector paths beyond `items_key`, no rate-limit hints, no non-JSON bodies |
| Mapping | `backend/di/connectors/mapping.py` | Versioned `MapRow(src, model, field, rule, resource)`, rules copy/upper/number/date/utc/units/fx/code/prefix; missing field fails one record | No confidence or provenance per row (who/what proposed it) |
| Discovery / probe | `discover.py`, `probe.py` | Column inference from the newest 200 raw records, FK suggestions (≥ 90 % key overlap); probe dns → tcp → tls → auth → perms → read | Discovery needs records already landed; no OpenAPI-based discovery; Recover wants a 500-record sample from the test environment (§1.4, updated in revision 2) |
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
| 5. Discovery | `discover.py` on a sample of up to **500 records** per resource read from the *test* environment (§1.4) (types, keys, FKs, value profiles) | Source tables + profiles | Read-only, page cap; personal data masked before any LLM sees it |
| 6. Mapping draft | Section 3: candidates + LLM choice + rule per field | `MapRow` set with `confidence`, `why`, `proposed_by` | Low-confidence rows marked "needs a person"; required canonical fields unmapped = blocking warning |
| 7. Test run | `workflow.testRun` dry run of the default ingest graph with the draft spec + mapping | Per-step counts, before/after samples, held records with reasons | Writes nothing (engine dry mode) |
| 8. Proposal | Agent files a proposal (existing proposals service) with diff, probe report, test run, open questions | Held for a person | `adapter.publish` / `source.publish` must be on `FORBIDDEN_ACTIONS` for agents |
| 9. Publish | Person (maker) submits; the **system owner** approves the connection (§1.4); another person (checker) approves the flow for production | Versioned spec + mapping | Maker-checker as in the Modeler; system-owner approval again for production and for write-back |
| 10. Watch | Health states, first-sync diff vs. test run; auto-pause on error spike | Alerts in "My work" | Rollback = previous spec version |

Eval harness (makes "hours" measurable): the 21 source-sim mocks already have hand-written adapters and demo mappings.
Generate a spec + mapping for each from its OpenAPI (source-sim's FastAPI apps publish one, **unconfirmed** for every
vendor mock) and compare records and facts with the hand-written adapter's output. Metrics: share of resources read
correctly, mapping precision@1, records held, minutes of person time. Target for the pilot: ≥ 80 % of resources right
first time on the generic mocks; a person fixes the rest in < 2 hours.

### 1.4 The adapter registry and adapter mapping (added in revision 2)

What 01 §2 asks for, and how each part fits what we have. Everything here is our own code on Postgres; the only
libraries involved are the ones already chosen (dlt `rest_api` vocabulary, the OpenAPI importer) and RapidFuzz for
mapping (§3.4).

**Registry entries.** One table `adapter_registry` of versioned entries, separate from the customer's connections:

| Field | Meaning |
|---|---|
| `id`, `version`, `system_type` (ERP, fleet contract, telematics, …), `vendor_family` | What the entry connects to |
| `kind` | `catalogue` (we build and maintain it, Python or ConfiguredAdapter), `generic_rest` (ConfiguredAdapter with no preset), `spec_built` (built once from an API spec through §1.3, then reused by every customer of that system) |
| `auth_methods` | `oauth2_client_credentials`, `oauth2_auth_code` (a person consents once), `service_account` (user + secret or key file), `api_key` |
| `resources`, `canonical_entities` | What it reads and which canonical entities it feeds (tool, return event, condition grade, remaining life, demand signal, market price, cost rate; 01 §4.1) |
| `write_actions` | Instructions it can carry back (sales order, transfer, work order, credit memo); empty = read-only by design |
| `mapping_templates` | Default mappings per pack, with the confidence each earned in past use |
| `contract_tests`, `status` (`draft`, `tested`, `released`, `deprecated`), `maintainer`, `source_licence` | Quality and provenance. `source_licence` records the licence of any imported manifest (Airbyte connectors vary, §1.1) |

"A connector built once from an API specification" is a `spec_built` entry: the agent flow of §1.3 produces it for
the first customer, a person releases it, and the next customer starts from the released entry instead of from the
spec. The legacy depot repair log in the tool-fleet pack (01 §4.1, "needs a connector") is the first candidate; for a
system with no API, the entry is a file-drop adapter (§2.3).

**Connections** (`source` rows today) gain three fields:

- `environment`: `test` or `production`. A new connection always starts in `test`. "Promote to production" copies
  the released spec and the accepted mapping, asks for new production credentials, and needs the system owner's
  approval. The test connection stays for later test runs.
- `access_mode`: `read` (default) or `read_write`. The execution step that sends instructions refuses a connection
  in `read` mode (a pipeline check, not a UI hint, golden rule 9). Turning on write-back is a separate approval by the
  system owner.
- `system_owner`: a person from the directory (§8b), named when the connection is created; they cannot be the maker.

**Credential vault.** Keep today's encrypted store (`secrets.py`, Fernet, plan 6): the secret field is write-only; no
API, log, span or agent ever reads it back ("never shown again"). Rotation replaces it. The key comes from the
environment or, at a customer, from their KMS. An external vault is optional and the customer's choice; if one is
asked for, note that HashiCorp Vault has been BSL 1.1 since August 2023 and OpenBao is its MPL-2.0 fork (general
knowledge, **not re-read this session**). Agents never handle credentials (§1.3, step 2).

**System-owner approval.** New actions `connection.requestApproval` and `connection.approve` / `connection.decline`.
The approval is per (connection, environment, access mode): "Fleet contract system, production, read-only" is one
approval; adding write-back later is another. Approvals and declines are person-only: they sit under the `source.`
prefix family that `FORBIDDEN_ACTIONS` already refuses to agents, or get their own entry there. The approval card
shows the scopes requested, the resources read, the write actions (if any), the sample counts and who asked.

**Discovery samples 500 records.** Today `discover.py` profiles the newest 200 records already landed. When a new connection is authored,
discovery reads up to 500 records per resource from the *test* connection into the quarantined raw store (`dry`), with
the egress allow-list, page cap and time budget of §1.3. To avoid only seeing this week's records, take half from the
newest pages and half spread over the time window when the API allows offsets or date filters (otherwise the newest
500, and say so). The profile per field: type, null rate, distinct count, top values, patterns, ranges, code-set
overlap. Personal data is masked in the profile before any LLM sees it (organisation rule; §3.1).

**Mapping proposals with confidence and a reason** (§3.4 for the method). Each proposed `MapRow` carries
`confidence` (0–1, calibrated), `why` (one line a person can check, for example "coded 0/1; meaning taken from the
registry documentation"), `proposed_by` (rule, memory, model) and the normalised sample values.

**The five person choices** become a `decision` on each row, journaled with who and when:

| Choice (01 §2) | Stored as | Effect |
|---|---|---|
| Accept as suggested | `accepted` | Row goes into the draft mapping; becomes a memory example |
| Choose a different field | `replaced` (+ `src`) | The corrected row is a strong memory example (a negative for the old one) |
| Accept with a conversion | `accepted_with_rule` (+ `rule`: `units`, `fx`, `code`, `date`, `utc` …) | The rule is applied to the sample at once, so the person sees the converted values |
| Not needed | `not_needed` | Excluded; a required canonical field marked not needed is a blocking warning |
| Ask the system owner | `asked_owner` | A task in the system owner's "My work" with the field, the sample values and the reason; their answer sets one of the four choices above |

**Test run** ("puts past items through the draft flow and shows where cases stopped"): `workflow.testRun` on the
sample (ingest, writes nothing), then the Modeler's replay (E §11.6) over the canonical records it produced. The
report counts, per stage, how many items stopped and why (missing field, held record code, guardrail). Effort for
§1.4 without §3.4 and §8b: about 3 weeks (registry table and actions, environment and access-mode checks, approvals,
sampling, row decisions).

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

- Valentine: adopt as an offline baseline and feature source (Apache-2.0); don't put it in the request path.
  Revision 2 checked its weight: 1.1.1 (12 Nov 2026, Python ≥ 3.12) requires `PuLP[cbc]`, which pulls `cbcbox`
  (EPL-2.0, the manylinux x86_64 wheel is ~200 MB), plus POT, NLTK and NetworkX. Keep it on the eval machine only.
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
- Effort: 6–8 days (retrieval, prompt, schema, mapping actions, eval script).

### 3.4 Field-mapping suggestion: libraries and the pipeline (added in revision 2)

Recover's adapter mapping gives each field a confidence score and, when unsure, a reason (01 §2; the telecom pack's
"export class inferred from the part number at low confidence", 01 §7). Options checked on PyPI on 24 Nov 2026:

| Option | Kind | Licence | Latest | Weight | Verdict |
|---|---|---|---|---|---|
| **RapidFuzz** | Embedding-free string similarity (Levenshtein, Jaro-Winkler, token-set ratios), C++ core | MIT | 3.14.6, 30 Aug 2026 | ~3 MB wheel, no dependencies | **Adopt** for name and description scores |
| Valentine | Classic schema matchers (COMA-style, Cupid, Similarity Flooding, distribution-based, Jaccard) | Apache-2.0 | 1.1.1, 12 Nov 2026 | PuLP + CBC (EPL-2.0, ~200 MB), POT, NLTK | **Offline only** (eval baseline, §3.2) |
| bdi-kit (VIDA-NYU) | Toolkit for schema and value matching for biomedical data integration; also an MCP server extra | Apache-2.0 (README badge, PyPI) | 0.11.0, 29 May 2026 | torch, transformers, sentence-transformers, flair, gensim, Valentine 0.5.0 | **Learn from**, avoid in the image. Which matchers it ships (for example the Magneto two-stage method, small model to retrieve and LLM to rerank) is **unconfirmed**: the README does not name them |
| Embedding model via our LLM port | Semantic similarity of names and descriptions | Per model | — | A provider call, or a local model for air-gapped customers | **Optional**, not needed for v1 |
| LLM rerank with abstain | Pick one of the top-k candidates or "none", name the conversion rule, give a one-line reason | Our port | — | One structured call per source table (batched fields) | **Adopt** (§3.1, approach 3) |

**Pipeline (all in-house, ≈ 700 lines):**

1. **Candidates (no LLM, no embeddings).** For each source field and each canonical field of the pack's entities:
   RapidFuzz scores on names, after splitting vendor codes and expanding abbreviations from a synonym list
   (`NETPR` → net price, `SERNR` → serial); value-profile features from the 500-record sample (type, pattern, range,
   distinct ratio, overlap with known code tables such as grades or ISO currency); **memory**: the same field of the same
   vendor family accepted before (§3.1 approach 4). A small logistic model, trained on the gold set (§3.3), turns these
   features into a score; the top 5 per field are kept.
2. **LLM rerank (optional; skipped with no key).** Inputs: field names, types, masked sample values, the candidates and
   their scores, and the vendor docs as *data*. Structured output per field: `{canonical | none, rule, why}`. The model
   may abstain.
3. **Confidence.** Not the model's own number: calibrate a score from (step 1 score, agreement between the step-1 top
   candidate and the LLM pick, memory hit) with isotonic regression on the gold set (scikit-learn, BSD-3, which
   arrives with the ML stack of E §6). The score is "the share of past proposals like this that a person accepted".
4. **Reason.** A template per signal, filled from the evidence: "name match 0.92 with `serial_number`", "values look
   like ISO 4217 codes", "coded 0/1; meaning taken from the registry documentation" (the docs snippet is quoted), "used
   for this vendor family by 3 customers before".
5. **Thresholds.** Pre-tick at confidence ≥ the value that gave ≥ 95 % precision on the gold set; between that and a
   lower bound, show "check"; below it, show "no proposal" with the candidates. Nothing is auto-accepted.

Without a model key the pipeline still proposes (steps 1, 3, 4), which keeps the trial package useful offline.

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

## 8b. Identity provider access (Recover "Access") (added in revision 2)

01 §2 (concept): roles and scopes come from the identity provider; directory groups map to roles; it must be possible
to say what each role can do and to check what a given user would get; members get access on the next sync.

### 8b.1 What we have

- `di/core/policy.py` already models the directory as the demo did: `IDP_GROUPS` (a hard-coded account → group map),
  the `idp_users` state collection, `idp_roles()` (every role except Admin; Admin is never assigned through a group),
  `map_identity()` and the role source setting (`approles` or groups, `_idp_start`).
- Actions in `services/actions/access.py`: `access.syncDirectory` (today it only stamps `lastSync` and counts users),
  `access.mapIdentity`, `access.removeUser`, `access.setRoleSource`, out-of-office delegation. All `access.*` actions
  are forbidden to agents.
- `di/core/auth.py` signs our own HS256 JWT after the demo sign-in; its docstring already plans "real single sign-on
  (OIDC, Keycloak as the stand-in)" with the token and dependencies unchanged. `PyJWT==2.10.1` is pinned (latest is
  2.15.1, 28 Sep 2026).

So the policy side exists; what is missing is a real protocol on both ends: sign-in (OIDC) and provisioning (SCIM 2.0
push, or a pull sync through an adapter).

### 8b.2 Libraries (PyPI, read 24 Nov 2026)

| Library | Role | Licence | Latest | Notes | Verdict |
|---|---|---|---|---|---|
| **Authlib** | OAuth 2.0 / OIDC client (and server) with Starlette/FastAPI integration, discovery, PKCE, nonce, JWKS | BSD-3-Clause | 1.9.10, 20 Nov 2026 | Depends on `cryptography` and `joserfc`; Python ≥ 3.10 | **Adopt** for the OIDC authorization-code + PKCE flow |
| joserfc | JWS/JWE/JWK/JWT (Authlib's JOSE layer) | BSD-3-Clause | 1.8.0, 3 Nov 2026 | Same author as Authlib | Comes with Authlib |
| PyJWT | JWT encode/decode, `PyJWKClient` | MIT | 2.15.1, 28 Sep 2026 (we pin 2.10.1) | Already ours | **Keep** for our own session tokens |
| **scim2-models** | SCIM 2.0 resources (User, Group, EnterpriseUser, PatchOp, ListResponse, errors) as **pydantic v2** models, filter parsing (lark) | Apache-2.0 | 0.12.4, 29 Oct 2026 | Python ≥ 3.11 (we run 3.12); python-scim project, developed by Yaal Coop | **Adopt** to parse and validate SCIM requests in our own FastAPI routes |
| scim2-server | Framework-agnostic SCIM server core (WSGI/ASGI apps, in-memory storage, RFC 7643/7644 validation) | Apache-2.0 | 0.8.8, 24 Nov 2026 | 15 GitHub stars: a small community | **Learn from**; don't depend on it for the routes (bus factor; we need our pipeline and journal on every write) |
| **scim2-tester** | Checks a SCIM server against the RFCs | Apache-2.0 | 0.6.5, 17 Nov 2026 | Uses scim2-client | **Adopt in CI** (dev dependency) |
| scim2-filter-parser | SCIM filter → SQL/Django query | MIT | 0.7.0, 20 Jul 2024 | Older; Django-oriented extra | Avoid (scim2-models parses filters) |
| django-scim2 | SCIM server for Django | MIT | 0.24.0, 9 Nov 2026 | Django only | Avoid |
| python3-saml | SAML 2.0 service provider | MIT | 1.16.0, 9 Oct 2023 | Needs `xmlsec` native library; no release for 3 years | Avoid for now: ask SAML-only customers to use their IdP's OIDC endpoint |
| python-keycloak | Keycloak admin/OIDC client | MIT | 7.1.1, 15 Feb 2026 | Vendor-specific | Not needed (Authlib is IdP-neutral) |

IdP *servers* (never in the trial package; customers bring theirs): **Keycloak** (Apache-2.0, JVM) is the dev and
test stand-in our `auth.py` already names, run as an optional Compose profile for our own tests only. **Zitadel moved
from Apache-2.0 to AGPL-3.0 with v3 (31 Mar 2025)** per its own announcement and FAQ, so avoid shipping it. Dex
(Apache-2.0, Go) is a lighter stand-in (licence from general knowledge, **unconfirmed** this session).

### 8b.3 Design and fit with `core/policy.py`

1. **Group → role mapping becomes data.** A table `idp_group_map` (external group id or app role → role, tenant or org
   unit, site/warehouse, valid from/to) replaces the hard-coded `IDP_GROUPS`; the demo's map is its seed, so parity
   holds. `idp_roles()` keeps refusing Admin through a group. Changes are `access.*` actions: person-only, journaled,
   and maker-checker for production (a mapping change is an access change).
2. **Sign-in (OIDC).** Authlib runs the authorization-code flow with PKCE against the customer's IdP (discovery URL,
   client id; the client secret in the vault of §1.4). On callback we validate the ID token (issuer, audience, nonce,
   signature from JWKS), read the `groups` or `roles` claim (the role source setting chooses which), resolve the
   account through the same mapping, and issue **our own** JWT exactly as today, so `Principal`, `policy.can()`,
   tenant and warehouse checks stay unchanged. The demo sign-in stays for the trial and for tests.
3. **Provisioning (SCIM 2.0 push).** New routes `/scim/v2/Users`, `/Groups`, `/ServiceProviderConfig`, `/Schemas`,
   `/ResourceTypes`, authenticated by a per-IdP bearer token from the vault. Requests are parsed with scim2-models
   and each write becomes an action through `pipeline.invoke` (golden rule 8) under a system principal "directory
   sync", journaled. `active: false` or a delete removes the user from `idp_users`, ends their sessions (short token
   TTL plus a revocation check on the account), ends their tenant grants, and moves their open approvals to their
   delegate.
4. **Sync (pull).** For IdPs without SCIM push, a directory adapter (an entry in the adapter registry, §1.4, for the
   IdP's users and groups API) runs on a schedule; `access.syncDirectory` then does what its name says. "Members get
   access on the next sync" holds for both: push is near real time, pull is at the next run.
5. **What each role can do** is a read action over `policy.roles()` plus `EXTRA_PERMS`, `EXTRA_PAGES` and
   `EXTRA_SECTIONS`; no new logic.
6. **Check a user**: a read action `access.testUser(email)` that resolves the user through the directory and the
   mapping without signing in, and returns `policy.summary()` (role, tenant, pages, permissions, approval limit,
   delegations) plus *which group* gave the role. Read-only, so agents may call it.
7. **Agents are not directory users.** Per-agent credentials stay a separate plan (F §7).

Effort (first-pass): OIDC sign-in 1 week; mapping as data plus the role and user checks 1 week; SCIM endpoints with
scim2-tester in CI 1.5 weeks; deprovisioning and session revocation 0.5 week.

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
| 23 | Adapter registry, environments, access modes, system-owner approval (§1.4) | **Build (ours)** | Policy on connections; Postgres only (added in revision 2) |
| 24 | RapidFuzz | **Adopt** | MIT, no dependencies; embedding-free name scores for mapping (§3.4) |
| 25 | Authlib (+ joserfc) | **Adopt** | BSD-3-Clause; OIDC sign-in with PKCE (§8b) |
| 26 | scim2-models | **Adopt** | Apache-2.0, pydantic v2; SCIM 2.0 parsing in our own routes (§8b) |
| 27 | scim2-tester | **Adopt (CI only)** | Apache-2.0; RFC compliance checks |
| 28 | scim2-server | **Learn from** | Apache-2.0 but a very small community |
| 29 | bdi-kit | **Learn from** | Apache-2.0; torch and transformers too heavy for the image |
| 30 | Keycloak, Dex | **Dev/test stand-in only**, never shipped | Apache-2.0, own servers |
| 31 | Zitadel | **Avoid** shipping | **AGPL-3.0 since v3 (31 Mar 2025)** |
| 32 | python3-saml, scim2-filter-parser, django-scim2 | **Avoid** | Stale (2023, 2024) or Django-only |
| 33 | HashiCorp Vault (if a customer asks for an external vault) | **Customer's choice**, not shipped | BSL 1.1 since Aug 2023; OpenBao is the MPL-2.0 fork (**not re-read**) |

## 10. Recommended Tier 1 + 2 target architecture

```
              person / agent (MCP, Ask, playbook)          docs URL · OpenAPI · Arazzo · samples · MCP endpoint
                          │  every write: POST /api/actions/{id} (pipeline, forbidden list, journal)
                          ▼
┌────────────── Connection Studio (FastAPI, Postgres only) ──────────────────────────────────────────────┐
│ Adapter registry (rev. 2): catalogue │ generic REST │ spec-built-once entries, versioned, released     │
│   connections: environment test→production, access read | read+write-back, vault (write-only),         │
│   system-owner approval; discovery samples 500 records; mapping rows with confidence + why + choice    │
│ Identity (rev. 2): OIDC sign-in (Authlib) → our JWT; SCIM 2.0 routes (scim2-models) → access actions;  │
│   idp_group_map (data) → policy.py roles; user check; role capabilities                               │
│ Adapter generator: importers (OpenAPI, Arazzo, Airbyte-manifest later) + LLM fill (structured output)  │
│   → spec JSON Schema validator → sandbox probe (read-only, egress allow-list) → discovery → mapping    │
│   draft (retrieval + LLM + eval-calibrated confidence) → dry run → PROPOSAL held for a person          │
│                                                                                                        │
│ Runtime adapters: Python adapters (21) │ ConfiguredAdapter v2 (dlt-style paging, selectors, parents,   │
│   formats JSON/NDJSON/CSV/XML) │ file adapters (sniffed CSV, X12 tokenizer, pydifact) │ MCP source     │
│   (discovery via tools/list) │ SQL query-delta source │ webhook intake (also Debezium Server, optional)│
│                                                                                                        │
│ Workflow engine (ours): typed block ports, expression subset, pinned data, replay-from-node,           │
│   held records with DQ codes + owner, dry runs with samples; sync = ingest workflow                    │
│ Contract: workflow JSON + published JSON Schema (from blocks.py), layout separate; OWS export later    │
│ Canonical store + checks (pydantic-generated JSON Schemas = data contracts); conflict queue            │
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
9. Adapter registry, environments, access modes, system-owner approval, 500-record discovery, the five mapping choices
   and the §3.4 pipeline (3 weeks + the 1.5 weeks of item 4; added in revision 2).
10. Identity: OIDC sign-in, group mapping as data, user check, SCIM 2.0 endpoints with scim2-tester (4 weeks; added in
    revision 2).

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
- Revision 2: which matchers bdi-kit 0.11.0 ships (Magneto or others) and whether its LLM matchers call an outside
  API; `cbcbox`'s wheel size was read as the largest manylinux x86_64 file on PyPI (it may bundle several solvers);
  Authlib's Starlette client needing a session middleware; scim2-server's release history (GitHub shows no releases;
  PyPI shows 0.8.8 on 24 Nov 2026); Dex's licence; HashiCorp Vault BSL 1.1 date and OpenBao MPL-2.0 (general
  knowledge, not re-read); whether every target IdP sends groups in the ID token (some send only an overage link);
  that a 50/50 newest/spread sample is possible depends on each API's filters.

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

Revision 2 (read 24 Nov 2026; PyPI JSON `https://pypi.org/pypi/<name>/json` for version, upload date, licence field and
dependencies)
- Target: [01-recover-segments.md](01-recover-segments.md) §2, §4.1, §7, §9
- Repo (read, not changed): `backend/di/core/policy.py` (IDP_GROUPS, idp_users, map_identity), `backend/di/core/auth.py`,
  `backend/di/services/actions/access.py` (syncDirectory, mapIdentity), `backend/requirements.in`, `backend/Dockerfile`
  (Python 3.12)
- RapidFuzz 3.14.6 (30 Aug 2026), MIT: https://pypi.org/project/RapidFuzz/
- Valentine 1.1.1 (12 Nov 2026), Apache-2.0, requires `PuLP[cbc]`, POT, NLTK: https://pypi.org/project/valentine/ ;
  PuLP 4.3.1 (19 Nov 2026), MIT, `cbc` extra = `cbcbox`: https://pypi.org/project/PuLP/ ; cbcbox 2.937 (9 Nov 2026),
  EPL-2.0: https://pypi.org/project/cbcbox/
- bdi-kit 0.11.0 (29 May 2026), Apache-2.0, dependencies incl. torch, transformers, flair, gensim:
  https://pypi.org/project/bdi-kit/ ; README: https://github.com/VIDA-NYU/bdi-kit
- Authlib 1.9.10 (20 Nov 2026), BSD-3-Clause: https://pypi.org/project/Authlib/ ; joserfc 1.8.0 (3 Nov 2026),
  BSD-3-Clause: https://pypi.org/project/joserfc/ ; PyJWT 2.15.1 (28 Sep 2026), MIT: https://pypi.org/project/PyJWT/
- scim2-models 0.12.4 (29 Oct 2026), scim2-client 0.14.1 (29 Oct 2026), scim2-server 0.8.8 (24 Nov 2026), scim2-tester
  0.6.5 (17 Nov 2026), all Apache-2.0: https://pypi.org/project/scim2-models/ and siblings; scim2-server README (python-scim,
  Yaal Coop, WSGI/ASGI, 15 stars): https://github.com/python-scim/scim2-server
- scim2-filter-parser 0.7.0 (20 Jul 2024), MIT; django-scim2 0.24.0 (9 Nov 2026), MIT; python3-saml 1.16.0 (9 Oct 2023),
  MIT; python-keycloak 7.1.1 (15 Feb 2026), MIT: PyPI pages of each
- Zitadel licence change to AGPL-3.0 with v3 (scheduled 31 Mar 2025): https://zitadel.com/blog/apache-to-agpl ,
  https://zitadel.com/license-faq
- SCIM 2.0: RFC 7643 (core schema) and RFC 7644 (protocol), IETF, Sep 2015 (standards, not re-read)

## Legal review note

Every licence statement above (MIT, Apache-2.0, BSD, MPL-2.0, EPL-2.0, GPL-3.0, AGPL-3.0, Elastic License 2.0,
Sustainable Use License, Activepieces' and n8n's enterprise licences) is a reading of public licence files and
package metadata on 24 Nov 2026 for engineering triage only. It is not legal advice. Because the trial package is
redistributed to customers, these findings must be reviewed by Kinective's Legal team before anyone relies on or
acts on them, in particular: ELv2 (PyAirbyte, Soda Core), Sustainable Use (n8n), AGPL (Windmill, Singer taps), GPL
(Bots), EPL-2.0 OR GPL-3.0 (elkjs), MPL-2.0 (JointJS) and the Activepieces `ee` terms. Revision 2 adds: AGPL-3.0
(Zitadel since v3), EPL-2.0 (CBC through Valentine's PuLP extra, kept off the image), BSL 1.1 (HashiCorp Vault, if a
customer brings it) and the permissive licences of Authlib, joserfc, scim2-* and RapidFuzz.
