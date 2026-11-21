# Connection Fabric: user guide

The Connection Fabric is the **Integration → Connection Fabric** menu. It is where you connect the enterprise systems
Circularity reads evidence from and writes approved instructions back to, map their fields to the canonical models,
build the workflows that move the data, and watch that all of it stays healthy.

> **Everything here is simulated.** All data is synthetic (Northfield Industrial Leasing). Each "system" (SAP S/4HANA,
> Salesforce, Oracle Transportation Management, AWS IoT Core …) is a local mock in the `source-sim` service that
> imitates that product's API style. No real vendor product is connected, and connecting one from the catalogue
> creates a simulated connection only.

## Contents

1. [Who can do what](#1-who-can-do-what)
2. [The page frame](#2-the-page-frame)
3. [Overview](#3-overview): the catalogue, recommendations, all integrations
4. [Connecting a system](#4-connecting-a-system): from the catalogue, or by hand
5. [The source drawer](#5-the-source-drawer): settings, mapping, sync, security, comments
6. [Keeping a source running](#6-keeping-a-source-running): sync, test, pause, disconnect, credentials, delete
7. [Workflow Studio](#7-workflow-studio)
8. [Source Map](#8-source-map)
9. [Source Tables](#9-source-tables)
10. [Canonical Models](#10-canonical-models)
11. [Event Streams](#11-event-streams)
12. [Conflict Queue](#12-conflict-queue)
13. [Manual Import](#13-manual-import)
14. [Monitor](#14-monitor)
15. [Messages you may see](#15-messages-you-may-see)
16. [Limits and good to know](#16-limits-and-good-to-know)

---

## 1. Who can do what

Sign in with any account ID and any password (for example `admin`, `developer`, `engineer`).

| Role | Sections it sees | Can change connections, tables, conflicts, workflows | Can comment on a source |
|---|---|---|---|
| Admin | all nine | yes | yes |
| Developer | all nine | yes | yes |
| Engineer | Overview, Source Map, Source Tables, Canonical Models, Monitor | no | no |
| Finance | Overview, Source Map, Monitor | no | yes |
| Approver | Event Streams, Conflict Queue (view only) | no | no |
| Planner, Executive, Warehouse Manager | the menu is not shown | no | no |

- The server enforces these rules. A role without the right sees **Read-only view. Only the Developer or Admin changes
  connections, tables, conflicts and workflows.**, gets **View** instead of the ⋯ menu, and has every field disabled.
- A refused change shows *"The {Role} view cannot {verb}."* or *"Only the Developer or Admin changes integrations."*
- Workflow Studio is visible to Admin and Developer only.

## 2. The page frame

- **Tabs** (only the ones your role may open): Overview · Workflow Studio · Source Map · Source Tables · Canonical
  Models · Event Streams · Conflict Queue (n) · Manual Import · Monitor. The number on Conflict Queue counts open
  conflicts.
- **Integration guide** (every tab) opens a short guide: Connect → Map → Run → Monitor, and the *How data flows*
  diagram (sources → integration layer → Circularity → enterprise systems, with the return loop).
- **New integration** (Overview, managers) and **+ Add source** (Source Map, managers) start a new connection.

## 3. Overview

`#/integration/overview`

**Tiles**
- **Connected**: systems sending data.
- **Needs attention**: stale, failing, expiring (credential expires within 14 days) or not connected.
- **Available**: catalogue systems not connected yet.

**Search**: matches vendor, name, category and owner. Typing a request such as `connect our HR system` and pressing
Enter opens the Connect dialog for the matching catalogue system (the text must start with connect, add, set up,
integrate, hook up or link).

**Category filter**: dropdown, pills and the left list all set the same filter (CRM, ERP, OMS, MRO, EAM, WMS, TMS,
Databases, Collaboration, Storage, Analytics, Security, Custom). Search, category and sort are remembered while you
stay signed in.

**Recommended for you**: up to four cards, ranked from open gaps:
1. a stale feed → **Manage** (opens the source);
2. a failing ingest workflow → **Investigate** (opens the workflow's last run);
3. a source that is not connected → **Connect**;
4. a catalogue system that would fill a gap → **Connect**.

*Why recommended* explains the card; nothing changes until you press Connect or Manage.

**All integrations**: sortable by Integration, Type (shows the category), Status and Last sync.
- Status values: Connected, Needs attention, Not connected, Available, Paused, Disconnected, Manual import, Syncing.
- Click a connected source's name to open its drawer, or a catalogue item's name to connect it.
- Actions: the ⋯ menu (managers) or **View**; **Connect** on catalogue rows (managers).

## 4. Connecting a system

### 4.1 From the catalogue

Use this for the 15 catalogue systems (Workday HCM, Atlassian Jira and Confluence, PostgreSQL, MySQL, Microsoft SQL
Server, Amazon S3, Azure Blob Storage, Microsoft Excel and SharePoint, Microsoft Dynamics 365, Oracle E-Business
Suite, Oracle NetSuite, Microsoft Teams, Google Drive, Snowflake).

Open it from **New integration → pick a tile**, a catalogue row's **Connect**, a recommendation's **Connect**, or the
search shortcut. The dialog has five steps:

1. **Authentication**: how Circularity signs in. Credentials go to the platform secret store and are never shown again.
   - **OAuth 2.0**: press **Allow** on the consent box (Deny closes the dialog).
   - **API key**: paste the key (at least 6 characters).
   - **Service principal**: enter its ID, e.g. `svc-circularity-read` (at least 6 characters).
   - **SFTP** (file storage systems only): the drop path; each file must arrive with a signed manifest.
   **Continue** unlocks once the step is complete.
2. **Scopes**: *Read records* is always on. Turn on *Write approved instructions* (writes run only after a person
   approves) and *Receive events* (webhook or queue delivery) only if you need them.
3. **Test connection**: runs DNS, TLS, Auth, Permissions and Sample read. Continue unlocks when it passes.
4. **Field mapping**: **Suggest mappings** proposes source field → canonical field rows with a confidence
   (High ≥ 85 %, Medium ≥ 70 %, else Low). Tick rows, or **Accept all high**. Accept at least one row.
5. **First sync**: the first sync reads a full extract; afterwards events arrive as they happen or on a schedule.
   Press **Done** when it finishes.

The system is then a real (simulated) source: it appears as **Connected** on Overview, on the Source Map and in the
Monitor, with the authentication, scopes and accepted mappings you chose. Catalogue systems have no simulated system
behind them, so their first sync is a synthetic run (its note says so) and **Sync now** later says that no simulated
system is behind the connection.

### 4.2 By hand (any other system)

**New integration → Another system**, or **+ Add source** on the Source Map, opens the **Add source** drawer:

- **Connection**: display name (max 60), system type, vendor product, version, environment (Production / Staging /
  Sandbox), owner team, and the **connection method** with its fields:
  - API extractor: base URL (`https://…`), REST or OData, poll interval (0 = real time, up to 1440 min);
  - Native connector, JDBC extractor (host, port 1–65535, database), Event / Ingestion API, Delta Sharing (sharing
    endpoint, share name), Flat file upload (SFTP path, max 1 GB per file);
  - **Authentication**: OAuth 2.0 client credentials, JWT bearer, mTLS, API key (optionally with an IP allow-list),
    service principal, basic auth over TLS, SFTP drop with a signed manifest, database user and password (vault), or a
    Delta Sharing bearer token.
- **Operations**: at least one read operation; each starts with a verb (`GET /assets`, `SELECT * FROM table`). Add
  write operations if Circularity should send instructions back.
- **Field mapping**: source field → canonical field rows; no row may be empty or repeated.

**Test connection** checks the settings first. **Create connection** validates the form (errors are marked in place,
with a summary such as *"Fix 2 items before saving."*), creates the source and records its first sync:
*"{name} ({vendor}) connected. Initial sync started."*

## 5. The source drawer

Open a source from any list, tile or graph node. Tabs: **Overview, Configuration, Data Mapping (n), Sync & History,
Security, Comments (n)**.

- **Overview**: the health card (healthy, stale, ingest workflow failing, not connected, disconnected, paused, manual
  import) with last and next sync; connection details; usage and performance (7D / 30D / 90D); *Permissions and
  access*, *Key features* and *Troubleshooting* (opens by itself when something is wrong, and holds **Test connection**).
- **Configuration**: the same fields as *Add source*, plus live facts (status, freshness, completeness, confidence,
  records, what the source has authority for) and the read and write operation lists. The system type cannot change.
- **Data Mapping**: the field mapping (source field, sample value, canonical field, normalised value, rule). Edit
  cells, remove rows (✕) or **+ Add field mapping**. Units, currency, timestamps and status codes are normalised;
  source values and provenance are kept.
- **Sync & History**: sync runs (run, time, trigger, records, duration, result) and the change history (version,
  when, by, change).
- **Security**: method, credential issued and expiry (an *Expiring* pill within 14 days), where it is stored, scopes
  and audit. **Rotate secret**; **Re-authenticate** for a stale source.
- **Comments**: Finance, Developer and Admin can post (max 500 characters; do not enter personal data).

**Saving**: on Configuration and Data Mapping, **Save changes** (enabled once something changed) and **Revert**. A
save raises the configuration version: *"{name} saved. Configuration is now v{x}."* Saving with no change says *"No
changes to save."*

## 6. Keeping a source running

All of these are in the ⋯ menu and the drawer footer (managers).

| Action | What it does | You see |
|---|---|---|
| **Sync now** | Queues a sync with the worker; the row shows *Syncing* until it ends. A sync already queued is not queued twice. | *"{name} synced: N records updated."* or *"{name}: sync failed, see Sync & History for the reason."* |
| **Sync all** (Source Map list) | Starts a sync of every live source, staggered. | *"Sync started for N live sources."* |
| **Test connection** | Probes the system for real: DNS, TLS, Auth, Permissions, Sample read (the sample read shows the real time, e.g. *1 record in 99 ms*). Stops at the first failure. | *"Connection test passed"* / *"failed"*. A not-connected system fails at DNS (*No route to host: the system is not provisioned*); an expired token fails at Auth (*Token rejected: expired*). |
| **Pause** / **Resume** | Stops scheduled syncs (queued ones are dropped) and marks dependent workflows *Paused upstream*; Resume restarts them. A paused source cannot be synced. | *"{vendor} paused. Scheduled syncs stop; n workflows now show Paused upstream."* / *"{vendor} resumed. Scheduled syncs restart."* |
| **Disconnect** | Circularity stops reading; the system itself is not changed and the settings are kept. Type the vendor name to confirm. | *"{vendor} disconnected."* with a **Reconnect** button. |
| **Connect** / **Reconnect** | Brings a not-connected or disconnected source live again and queues a sync. | *"{name} is live again. Predictions no longer carry a stale-feed warning."* |
| **Refresh token and re-sync** (stale source) | Renews the expired token and re-reads the feed. | same as Reconnect |
| **Re-authenticate** (Security, stale source) | Authentication → Test connection → Finish; renews the credential. | *"{vendor} re-authenticated. The credential is renewed for 180 days."* |
| **Rotate credentials** | New secret (at least 8 characters) and expiry (90, 180 or 365 days). Updates the issued and expiry dates. | *"Credentials updated for {name}."* |
| **Delete** | Type the source name to confirm. Mappings go, workflows that use it will fail validation, write-back stops. | *"{name} ({vendor}) deleted."* with **Undo** for 8 seconds, which restores the source with its settings and mappings. |

## 7. Workflow Studio

`#/integration/studio` (Admin and Developer)

### 7.1 The list

- Tiles: Total workflows, Published, Failing (published and the last run failed), Draft or paused.
- Search (name, id, owner, system), filters (type, system, status), sort (last run, name, 24 h success, status),
  20 per page. Filters stay while you are signed in.
- Row: **Investigate** (failing) or **Open**, and the ⋯ menu: Edit, Run now, Publish / Pause / Resume, Duplicate,
  Export JSON, Delete.
- Select rows for the bulk bar: **Run** (drafts are skipped), **Pause**, **Export** (one JSON per workflow).
- Side panel: items that need attention (failing workflows, expired credentials, high failure rates) with
  **Investigate** and **Diagnose** (asks Ask Circularity), workflow health, recent activity.

### 7.2 Creating a workflow

Press **+ New workflow** (or **New workflow** in Home's quick actions):

| Type | You choose | Draft it creates |
|---|---|---|
| Ingest pipeline | a source system | connector → ingestion channel (or the file steps) → validation & enrichment → a transform for the source type → field mapping → canonical model → evidence snapshot, plus error handler, audit log and event-stream branches |
| Outbound instruction | a target system and a delivery method (API call, event, interface file, process orchestration) | decision → human approval → instruction envelope → delivery → write connector → outcome |
| Decision workflow | — | evidence → six eligibility gates → routes → predictions → approval request → human approval → decision → send instruction → outcome → reconcile |
| Blank pipeline | — | an empty canvas |

Name is optional (max 80). **Your templates** lists the templates you saved (see 7.5); pick one to create a draft
from it: *"Created from the template as a draft."*

A complete, verified walk-through (template → extra blocks → settings → publish → run) is in
[workflow-tutorial.md](workflow-tutorial.md).

### 7.2a Build with AI

**Build with AI** (next to *+ New workflow*, Admin and Developer) builds a workflow from a description and asks for
whatever it still needs:

1. Describe it, e.g. *"Ingest from Salesforce with currency conversion and de-duplication, every 30 minutes"*, or pick
   an example, then **Plan it**.
2. The *Understood* row shows what it took from your words (type, system, trigger, steps); **Change** reopens any of
   them. It then asks only what is missing or unclear, each question with a sensible default:
   - the workflow type; the source system, or the target system and a delivery method it accepts;
   - how records arrive, the trigger and interval;
   - extra steps (pre-ticked from your words), and whether to keep the standard ones;
   - error handling and logging, retries, the alert rule, name and owner.
   **Use defaults for the rest** skips the remaining questions; **Back** goes one round back.
3. If you name a system that is not connected (e.g. *Workday*), or one it reads but cannot write to, it says so and
   offers the closest real systems.
4. The plan shows a tailored name and description, every step in run order with why it is there, a small graph,
   **what differs from the standard template** (added, left out, changed), and the checks (always 0 errors; if a
   choice would break a rule it says so instead).
5. Nothing exists until you press **Create workflow**: it creates the draft as you, with the settings you chose, and
   opens it. Then Save, Publish and Run now as usual.

Without a Groq key (`GROQ_API_KEY` in `.env`) the builder reads your words with rules over the real system names and
step keywords; with a key, the model only helps resolve wording the rules could not. It never invents a step you did
not ask for. In **Ask Circularity**, *"Build an ingest for Dealer network with currency conversion"* shows the drafted
steps with **Refine in Workflow Studio**, which opens the builder with that request.

### 7.3 Editing on the canvas

- **Add a step**: drag it from the palette, or click it / press Enter. Palette groups: source connectors by category,
  transform steps (mapping, enrichment, filter, aggregation, expression, code-table lookup, join, validation,
  timestamps to UTC, currency, units, identity, late events), orchestration steps (scheduler, event trigger, branch,
  loop, call workflow, wait), branches (error handler, audit log, event stream) and *More* (integration layer, file
  exchange, delivery methods, write connectors, all field mappings). Decision workflows show the agent tools instead.
- **Connect** steps by dragging from a step's right dot to another step, or with *Connect output to* in the inspector.
- **Remove a link**: click the line close to its arrowhead (near a step's output dot, branch lines overlap) and press
  **Remove connection**.
- **Move** by dragging (8 px grid) or with the arrow keys (Shift = 40 px). **Delete** with Delete/Backspace or
  *Remove from workflow*.
- **Fixed steps** (canonical models, evidence snapshot, decision, send instruction) and **locked links** belong to
  Circularity: they cannot be moved, re-wired or removed.
- Toolbar: zoom (50–140 %), fit, undo/redo (40 steps), auto layout, minimap, Overview / Details / Data flow views,
  expand canvas. On a phone the canvas is read-only.
- The **Checks** panel lists errors and warnings (for example a write that bypasses human approval, a mapping fed by
  the wrong connector, a connector with no connected feed). **Validate** runs them on demand.

### 7.4 Save, publish, run

- Edits stay in a draft (*Unsaved changes*) until **More actions → Save** (*"{name} saved as v{x}."*). **Discard
  changes** returns to the last saved version; leaving with unsaved changes warns you once.
- **Publish** saves first if needed and refuses while there are check errors; the workflow then runs on its trigger.
  **Unpublish** returns it to draft. Pause and Resume are in the list's ⋯ menu.
- **Test run** runs the *draft* in the browser, step by step, and stops at Human approval: **Approve and continue**
  needs approval rights (Admin; a Developer is told to switch to Approver). Nothing is sent to any system.
- **Run now** runs the *saved* version on the server and records the run (History tab, Recent runs, Task instances).
- **Fail this step in the next run** (inspector) makes a run fail at that step, to rehearse the failure path.

### 7.5 Settings, history, templates

- **Settings tab**: trigger (schedule with an interval, event, approval, file arrival, case request, manual), owner,
  **Retries** (0, 1, 3 or 5; default 3) and **Alert when** (a run fails, two runs fail in a row, success rate drops
  below 95 %, never). They are saved with the workflow (*"Saved with the workflow."*) and apply once you save or
  publish: a failed run reports *failed after N retries*, and when the alert rule matches, a *Workflow alert* appears
  on the Alerts page for Developer and Admin.
- **History tab**: every run, latest first, with **View** (steps, timings, failed records).
- **Documentation tab**: generated from the graph; **Explain this workflow** asks Ask Circularity.
- **Save as template** (More actions or Quick actions): *"Saved as a template. It appears under New workflow."*
  **Reset to template** puts the template's graph back in the draft.
- **Duplicate** creates *"{name} (copy)"* as a draft. **Export JSON** downloads the saved version. **Delete** asks for
  confirmation and warns when the workflow is published.

### 7.6 When a run fails

- **Investigate** (or `?run=last`) shows which step failed after how many retries, the error log and any schema
  drift. **Diagnose** and **Fix** ask Ask Circularity.
- **Apply the suggested fix** applies it to the workflow (the renamed source field maps again, or the step returns
  to its last good configuration) and raises the version: *"Fix applied. Run now to confirm it turns green."*
- **View failed records** lists the rows that broke a validation rule (held by the error handler, not dropped).
  **Export CSV** downloads them; **Reprocess** sends them back through validation: *"N records sent back through
  validation. Rows that still break a rule stay held."*

## 8. Source Map

`#/integration/map`: how every system, its tables and fields reach the canonical models and the decisions.

- Tiles: connected sources, tables modelled, field mappings, active workflows, integration health (24 h).
- Toolbar: search (system, vendor, owner), system picker, category, status, *Show field links*, and the view switch:
  - **Graph**: systems → canonical models → models and decisions. Edge badges show mapped fields; select a node to
    highlight its paths. Zoom 50–140 %.
  - **List**: tiles per category with freshness, completeness and confidence meters, the journey steps each source
    feeds, and **Edit** / **Sync** / **Delete**; **Sync all** and **+ Add source** at the top; sync activity, health,
    mapping exceptions and recent events below.
  - **Matrix**: mapped fields per system and model; red cells mark a stale or missing feed, or a target with no
    mapping.
- Detail panel: Overview, Tables, Fields (with **Suggest mappings**, which opens the Data Mapping tab), Sync,
  Settings, and **Test connection**.

## 9. Source Tables

`#/integration/tables`: the tables each system exposes and how they link (systems with a table model: CRM, EAM, ERP,
FSM, PLM, WMS).

- Pick a system; switch **Graph** / **List**. Hover a table, field or link to see what it is and why it is used.
- **Graph**: drag a table by its header, **Auto Align** by cluster, zoom 30–140 %. Positions are saved.
- Managers:
  - **Add Tables**: name (letters, numbers, underscores), cluster, description (max 220), columns one per line, key
    first. *"{name} added. Use New Foreign Key to link it to other tables."*
  - **Edit** (⋮ on a card or Edit in the list): description, cluster, columns; **Delete table** removes it and its
    links (with **Undo**).
  - **New Foreign Key**: from table and column, to table and column, and why the link matters (max 120). Delete a
    link from the list.
- Changes are saved on the server and show in the tiles and on the Source Map.

## 10. Canonical Models

`#/integration/models`: the seven versioned models every adapter maps into (Asset & component, Condition &
eligibility, Demand opportunity, Intervention, Route candidate, Decision, Outcome), each with its purpose, fields,
the systems that feed it and an example from RT-1048. Read only.

## 11. Event Streams

`#/integration/events`: every decision and instruction message in and out, with its acknowledgement.

- Tiles and panels: events, inbound, outbound, errors/duplicates/escalations; first-time acknowledgement rate,
  duplicates caught, late or out-of-order events reconciled.
- Filters: All / Outbound / Inbound, *Only retries, duplicates, late and conflicts*, and a search by case, decision,
  destination or event type. The 70 newest matching events are shown.
- Select a row for the full message (decision, approval reference, version, destination, acknowledgement,
  idempotency key, retries) and **Open {case}**.
- Conflict decisions (`conflict.resolved`, `conflict.escalated`) and manual imports (`import.evaluated`) are logged
  here too.

## 12. Conflict Queue

`#/integration/conflicts`: where two systems disagree on a canonical field.

- A conflict opens when a sync finds different values for the same field (text compared case-insensitively, numbers
  within 0.5 %). The value used is the one from the **source with authority** (for example the lease system for the
  owner tenant, WMS for location). It closes by itself when the sources agree again.
- Each card shows the field, the record, both values, the authority and the impact (routes using the field are held).
- Managers:
  - **Accept {authority}**: resolves the conflict in favour of the source with authority: *"{id} resolved: {authority}
    is authoritative for {kind}."*
  - **Escalate to owner**: notifies the data owner; the conflict stays open and dependent routes stay held. You can
    still accept it afterwards.
- Approvers see the cards without buttons.

## 13. Manual Import

`#/integration/import`: a controlled CSV import for partners without a supported API. Imported rows support
evaluation, not live automation: they are tagged manual, carry no live freshness and cannot trigger instructions.

1. **Provide a file**: choose a `.csv` (max 200 KB) or paste rows, or **Load sample file**.
   Required columns: `asset_id, qty, condition_grade, location, owner, received` (header case does not matter, extra
   columns are ignored).
2. **Validate**: each row is checked:
   - asset_id matches a known class (`MTR`, `PMP`, `CTL`, `DRL`, `BAT`, `ITE` + 4 digits);
   - qty is a positive whole number;
   - grade A–D (`B+` becomes `B`);
   - location is Warehouse 1, Warehouse 2 or Repair centre;
   - owner is Customer A, B or C;
   - received is `YYYY-MM-DD` (`YYYY/MM/DD` is fixed).
   The preview marks rows **Ready**, **Normalised** or **Rejected** (with the reason). Rejected rows are never loaded.
3. **Load N rows for evaluation**: the server checks the rows again and loads them: *"{n} rows loaded for
   evaluation. They are tagged manual and will not trigger any instruction."* Loading the same rows twice is
   refused: *"These rows were already loaded. Nothing was created twice."*

Values are split on plain commas: quoted values and values containing commas are not supported.

## 14. Monitor

`#/integration/monitor`: integration health over time.

- Tiles: sync success (24 h; runs with warnings do not count as successes), average latency, failed records (7 days,
  held for reprocessing), fresh within SLA, failing workflows. SLA = twice the poll interval; 15 min for event
  sources; 2 days for manual import; otherwise 60 min.
- **Sync runs, last 24 hours**: one stacked bar per hour (successful, warnings, failures). Select a dip for an
  explanation.
- **Per source** (freshness, SLA, success, failed records, latency) and **Per workflow** (lowest success first).

## 15. Messages you may see

| Message | Meaning |
|---|---|
| Only the Developer or Admin changes integrations. | Your role is read-only here. |
| {name} is paused. Resume it to sync. | Resume the source first. |
| {id} is disconnected/unavailable. Resume or reconnect it first. | The source is not connected. |
| No simulated system is behind {id}… | A catalogue or hand-made source has no mock to read from. |
| Fix the highlighted connection settings first. | The connection fields have errors (shown in place). |
| Enter a full URL starting with https:// | Base URLs must be HTTPS. |
| Add at least one read operation. | A source must read something. |
| A source with this name and vendor already exists. | Pick another display name. |
| Cannot publish: N error(s) in the checks. Fix them first. | Open the Checks panel. |
| {name} is a draft with errors: … | Run now refuses a draft whose run would fail. |
| These rows were already loaded. Nothing was created twice. | The same import was loaded before. |
| Conflict CF-n is already resolved. | Someone resolved it already. |

## 16. Limits and good to know

- All systems are simulated (see the top of this guide); catalogue and hand-made sources have no mock behind them,
  so they cannot sync after their first (synthetic) run. The AI builder offers only the demo's 21 systems.
- In the dev stack no source starts stale: the simulator's *expired token* fault on Ritchie Bros. Market Data is off by
  default. To show *Needs attention*, *Refresh token and re-sync* and *Re-authenticate*, switch it on with
  `curl -X POST http://localhost:8100/_sim/faults/demo` and press **Sync now** on Ritchie Bros. (or start source-sim
  with `SIM_DEMO_FAULTS=true`).
- The demo reset (`bash scripts/dev/reset.sh`) removes sources connected in the app and returns paused or
  disconnected demo sources to their starting state.
- Drafts of workflows and unsaved drawer edits belong to your browser session; signing out drops them.
- *Run now* and *Export JSON* use the saved workflow; *Test run* and *Validate* use the draft.
- Event Streams shows the 70 newest matching events; the Conflict Queue shows 60 cards at a time (*Show more*).
- The CloudEvents the simulated systems send to Circularity (`POST /api/webhooks/source-sim`, HMAC-signed) trigger
  syncs; they are not listed in Event Streams, which shows decision and instruction messages.
