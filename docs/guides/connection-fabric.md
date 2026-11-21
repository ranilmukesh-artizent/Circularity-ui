# Connection Fabric: user guide

The Connection Fabric is the **Integration → Connection Fabric** menu. It is where you connect the enterprise systems
Circularity reads evidence from and writes approved instructions back to, map their fields to the canonical models,
build the workflows that move the data, and watch that all of it stays healthy.

> **Everything here is simulated.** All data is synthetic (Northfield Industrial Leasing). Each "system" (SAP S/4HANA,
> Salesforce, Oracle Transportation Management, AWS IoT Core …) is a local mock in the `source-sim` service that
> imitates that product's API style. No real vendor product is connected, and connecting one from the catalogue
> connects to that system's mock in source-sim. What Circularity does with the data is real: syncs, mappings,
> credential storage, checks, conflicts and workflow runs all work as they would against a real system.

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

1. **Authentication**: how Circularity signs in. Credentials are encrypted and stored by Circularity, and never shown
   again.
   - **OAuth 2.0**: press **Allow** on the consent box (Deny closes the dialog).
   - **API key**: the field starts with the simulated system's sandbox key, and says *"This is the sandbox key of the
     simulated system."* The key in the field is the one Test connection signs in with and the one stored when you
     connect. Type another and the note says *"The simulated system accepts only its sandbox key; another key fails
     the test at Auth."*
   - **Service principal**: enter its ID, e.g. `svc-circularity-read` (at least 6 characters).
   - **SFTP** (file storage systems only): the drop path; each file must arrive with a signed manifest.
   **Continue** unlocks once the step is complete.
2. **Scopes**: *Read records* is always on. Turn on *Write approved instructions* (writes run only after a person
   approves) and *Receive events* (webhook or queue delivery) only if you need them.
3. **Test connection**: runs DNS, TLS, Auth, Permissions and Sample read. Continue unlocks when it passes.
4. **Field mapping**: **Suggest mappings** reads a sample record from the system and proposes source field →
   canonical field rows with a confidence (High ≥ 85 %, Medium ≥ 70 %, else Low); it never proposes a field the
   system does not send. Tick rows, or **Accept all high**. Systems that hold no asset, condition, demand, market or
   vendor data (Workday, Jira, Confluence, Teams, Google Drive, S3, Azure Blob, NetSuite) have nothing to map: their
   records are kept as source records (Sync & History, Source Tables) and add no canonical data.
5. **First sync**: the first sync is queued; it reads a full extract, later syncs read changes on the schedule.
   Press **Done**.

The system is then a connected source: it appears as **Connected** on Overview, on the Source Map and in the Monitor,
with the authentication, scopes and accepted mappings you chose, and **Sync now** reads it again. Its canonical data is
kept under keys of its own (for example `postgres:MTR-2041`), so connecting a catalogue system never changes the demo's
data or opens conflicts. Until its record reaches the list, its row in **All integrations** shows *Connecting…* and
opens nothing. Like the demo's sources, it can have its own ingest workflow in Workflow Studio (and an outbound one
when it has write operations).

Connecting a catalogue system you deleted earlier **starts clean**: the deleted source's sync runs, landed records,
cursors, held records, webhook events, mapping versions, connection and credentials are removed when you connect it
again. Until then, **Undo** of the delete brings it back with everything it had.

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
with a summary such as *"Fix 2 items before saving."*), creates the source and queues its first sync:
*"{name} ({vendor}) connected. Initial sync started."* The source is read from the base URL you entered; each `GET
/path` operation is a resource it reads. In the dev stack, `http://source-sim:8100/sandbox/<any-name>` is a test API
with 25 records you can point a hand-made source at.

## 5. The source drawer

Open a source from any list, tile or graph node. Tabs: **Overview, Configuration, Data Mapping (n), Sync & History,
Security, Comments (n)**.

- **Overview**: the health card (healthy, stale, ingest workflow failing, not connected, disconnected, paused, manual
  import) with last and next sync; connection details; usage and performance (7D / 30D / 90D); *Permissions and
  access*, *Key features* and *Troubleshooting* (opens by itself when something is wrong, and holds **Test connection**).
- **Configuration**: the same fields as *Add source*, plus live facts (status, freshness, completeness, confidence,
  records, what the source has authority for) and the read and write operation lists. The system type cannot change.
- **Data Mapping**: the field mapping (source field, sample value, canonical field, normalised value, rule). Edit
  cells, remove rows (✕) or **+ Add field mapping**. The mapping you save is the one the next sync applies: each save
  is a new version (the bar above the table shows the version that runs); **Preview on a sample record** shows what
  the mapping writes for a real record before you save; **Revert to …** brings back an older version as a new one.
  Rules a sync applies: copy, upper, lower, number, integer, date, timestamp to UTC, units, currency and code tables.
  A record that lacks a mapped field fails alone ("missing field …"); the rest of the sync goes on.
- **Sync & History**: sync runs (run, time, trigger, records, duration, result) and the change history (version,
  when, by, change).
- **Security**: method, credential issued and expiry (an *Expiring* pill within 14 days), how it is stored
  (*Encrypted by Circularity · version n · ends in ••••xxxx* once a secret was entered), scopes and audit. **Rotate
  secret**; **Re-authenticate** for a stale source. An expired credential is not used: syncs stop with *"Credential
  expired on {date}"* until you rotate it.
- **Comments**: Finance, Developer and Admin can post (max 500 characters; do not enter personal data).

**Saving**: on Configuration and Data Mapping, **Save changes** (enabled once something changed) and **Revert**. A
save raises the configuration version: *"{name} saved. Configuration is now v{x}."* Saving with no change says *"No
changes to save."*

## 6. Keeping a source running

All of these are in the ⋯ menu and the drawer footer (managers).

| Action | What it does | You see |
|---|---|---|
| **Sync now** | Queues a sync with the worker; the row shows *Syncing* until it ends. A sync already queued is not queued twice, and only one sync of a source runs at a time. A system that answers busy or slow (429, 5xx, timeout) is asked again up to 3 times; a failed sync is retried after 2, 4, 8 … minutes. | *"{name} synced: N records updated."* or *"{name}: sync failed, see Sync & History for the reason."* |
| **Sync all** (Source Map list) | Starts a sync of every live source, staggered. | *"Sync started for N live sources."* |
| **Test connection** | Probes the configured endpoint for real: DNS (the resolved address), TLS (the protocol and certificate expiry; *Not encrypted: http* is a warning), Auth, Permissions (reads one record from each read resource and names the first that fails) and Sample read (the real time, e.g. *1 record in 99 ms*). Stops at the first failure. | *"Connection test passed"* / *"failed"*. A not-connected system fails at DNS (*No route to host: the system is not provisioned*); a refused credential fails at Auth (*Token rejected (HTTP 401): the credential is expired or revoked*). |
| **Pause** / **Resume** | Stops scheduled syncs (queued ones are dropped) and marks dependent workflows *Paused upstream*; Resume restarts them. A paused source cannot be synced. | *"{vendor} paused. Scheduled syncs stop; n workflows now show Paused upstream."* / *"{vendor} resumed. Scheduled syncs restart."* |
| **Disconnect** | Circularity stops reading; the system itself is not changed and the settings are kept. Type the vendor name to confirm. | *"{vendor} disconnected."* with a **Reconnect** button. |
| **Connect** / **Reconnect** | Brings a not-connected or disconnected source live again and queues a sync. | *"{name} is live again. Predictions no longer carry a stale-feed warning."* |
| **Refresh token and re-sync** (stale source) | Renews the expired token and re-reads the feed. | same as Reconnect |
| **Re-authenticate** (Security, stale source) | Authentication → Test connection → Finish; renews the credential. | *"{vendor} re-authenticated. The credential is renewed for 180 days."* |
| **Rotate credentials** | New secret (at least 8 characters) and expiry (90, 180 or 365 days). The secret is stored encrypted as a new version and used from the next sync; the previous one is revoked. | *"Credentials updated for {name}."* |
| **Delete** | Type the source name to confirm. Mappings go, workflows that use it will fail validation, write-back stops. | *"{name} ({vendor}) deleted."* with **Undo** for 8 seconds, which restores the source with its settings and mappings. |

## 7. Workflow Studio

`#/integration/studio` (Admin and Developer)

Every block has settings, and a run processes real records from the source. The full reference for the Studio is
[workflow-studio.md](workflow-studio.md) (detailed reference); a step-by-step build is in
[workflow-tutorial.md](workflow-tutorial.md).

### 7.1 The list

- Tiles: Total workflows, Published, Failing (published and the last run failed), Draft or paused.
- Search (name, id, owner, system), filters (type, system, status), sort (last run, name, 24 h success, status),
  20 per page. Filters stay while you are signed in.
- Row: **Investigate** (failing) or **Open**, and the ⋯ menu: Edit, Run now, Publish / Pause / Resume, Duplicate,
  Export JSON, Delete. The status shows **Paused upstream** when the workflow's source is paused in the Connection
  Fabric (the server reports it).
- **Import** (next to *Build with AI*, managers): choose a JSON file that **Export JSON** wrote. It becomes a new draft
  with its blocks, links and block settings: *"{name} imported as a draft ({id})."* The server checks it first and
  names what it does not know: *"Unknown block {ref} in step {id}."*, *"Unknown source {ref} in step {id}."* A file
  that is not JSON: *"{file} is not a JSON file. Choose a file that Export JSON wrote."*
- Select rows for the bulk bar: **Run** (drafts are skipped), **Pause**, **Export** (one JSON per workflow).
- Side panel: items that need attention (failing workflows, expired credentials, high failure rates) with
  **Investigate** and **Diagnose** (asks Ask Circularity), workflow health, recent activity.

### 7.2 Creating a workflow

Press **+ New workflow** (or **New workflow** in Home's quick actions):

A new workflow holds **only the blocks it needs to run**; you mix and match everything else from the palette.

| Type | You choose | Blocks it starts with |
|---|---|---|
| Ingest pipeline | a source system | connector → one ingestion channel (API gateway, or event ingestion for an event source; the file steps for a file-only source) → validation & enrichment → field mapping → canonical model → evidence snapshot |
| Outbound instruction | a target system and a delivery method (API call, event, interface file, process orchestration) | decision → human approval → instruction envelope → delivery method (plus a manifest for a file) → write connector → outcome |
| Decision workflow | — | evidence → six eligibility gates → routes → predictions → approval request → human approval → decision → send instruction → outcome → reconcile |
| Blank pipeline | — | an empty canvas |

Optional blocks (a transform such as Convert currency or Timestamps to UTC, the error handler, audit log, event
stream, a second ingestion channel, the import-log steps) are never added for you. **Reset to template** returns to
the starting blocks.

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
   - how records arrive (one channel unless you want both), the trigger and interval;
   - extra blocks (ticked only if you mentioned them; the source type's usual transform is marked but not added);
   - error handling and logging (optional, unticked), retries, the alert rule, name and owner.
   **Use defaults for the rest** skips the remaining questions; **Back** goes one round back.
3. If you name a system that is not connected (e.g. *Workday*), or one it reads but cannot write to, it says so and
   offers the closest real systems.
4. The plan does not start from a template: it holds the blocks **required to run** plus exactly the ones **you
   asked for**, and shows both lists, every block in run order with why it is there, a small graph, the settings you
   changed, and the checks (always 0 errors; if a choice would break a rule it says so instead).
5. Nothing exists until you press **Create workflow**: it creates the draft as you, with the settings you chose, and
   opens it. Then Save, Publish and Run now as usual.

Block settings your words state are filled in: *"to EUR"* (or *in*, *into*; USD, EUR or INR) sets Convert currency's
**Target currency**, and *"de-duplicate by opportunity_id"* (also *ordered by …*) sets Order late events' **Key
fields**. Everything else keeps its default; change it in the inspector afterwards.

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
- **The inspector** (click a block) shows its name and description, then four sections in this order: **Settings**,
  **Problems** (this block's checks, only when it has some), **Connections** and **Testing** (movable blocks only),
  and **Remove from workflow** at the bottom.
- **Settings**: one field per setting of the block, with its help text; a required field has a *. For example:
  - the source connector: **Resources** (none ticked: every resource), **Mode** (*delta* reads what changed since the
    last sync, *full* reads everything), **Lookback (days)**;
  - Validation & enrichment: **Required fields**, **Rules** (**+ Add rule**: a field, a check *present*, *type*,
    *regex*, *range* or *in*, and its value, e.g. `>0` or `0..100`), **On failure** (*hold* keeps failed records for
    reprocessing, *reject* drops them);
  - Order late events: **Key fields** (a record missing one goes on untouched), **Newest wins by**, **Late window
    (min)**, **Time field** (the late window counted back from the newest record's time in the run);
  - Convert currency: **Target currency** (USD, EUR or INR), **Rate date** (*record* or *run*), **Rate table**,
    **Amount fields**, **Currency field**, **Source currency**, **Date field**;
  - Wait: **Duration (min)**, **Until** (records really wait and the run comes back for them); Call workflow:
    **Workflow** (starts that published workflow); Write to audit log: **Level** (one Audit entry per run);
  - Filter and condition: **Condition** (rules; rows that pass every rule are kept); Normalise units: **Field
    units**; Code-table lookup: **Code tables**; Timestamps to UTC: **Fields**, **Source zone**.

  Lists of fields are typed with commas (`field_a, field_b`). A text field takes effect when you leave it or press
  Enter; each change is one undo step and marks the draft *Unsaved changes*. A problem shows in red under the field.
  Fixed steps and agent tools say *"This step has no settings: Circularity runs it the same way in every workflow."*
- A setting the step cannot use (an unknown currency, an empty rule, a number out of range) **is saved anyway**, but it
  is a check error, so Test run and Publish refuse until you fix it. Checks that need the fields the source's records
  really carry run on the server: a key, rule or mapping field the records do not have, e.g. *"Order late events: Key
  fields opportunity_id is not a field the records carry."* The page asks the server about 0.6 s after each edit (and
  again on Validate, Test run and Publish) and shows its answer in the **Checks** panel, the inspector's **Problems**
  and on the canvas. Test run then refuses with *"Fix 1 error before running. The checks below say what and why.
  First: {message}"* and Publish with *"Cannot publish: 1 error in the checks. Fix them first. First: {message}"*.
- **Connect** steps by dragging from a step's right dot to another step, or in the inspector: **Connections** lists
  what the block **Receives from** and **Sends to**; **Next step** (or **+ Add another connection**, then **Also send
  to**, when it already sends somewhere) adds a link, and **Remove** next to a link removes it (locked links show
  *Locked*).
- **Remove a link**: click the line (the canvas selects the line nearest your click, also where branch lines leave
  the same step) and press **Remove connection**.
- **Move** by dragging (8 px grid) or with the arrow keys (Shift = 40 px). **Delete** with Delete/Backspace or
  *Remove from workflow*.
- **Fixed steps** (canonical models, evidence snapshot, decision, send instruction) and **locked links** belong to
  Circularity: they cannot be moved, re-wired or removed.
- Toolbar: zoom (50–140 %), fit, undo/redo (40 steps), auto layout, minimap, Overview / Details / Data flow views,
  expand canvas. On a phone the canvas is read-only.
- The **Checks** panel lists errors and warnings, the browser's and the server's (for example a write that bypasses
  human approval, a mapping fed by the wrong connector, a connector with no connected feed, a field the records do not
  carry). **Validate** runs them on demand.

### 7.4 Drafts, test run, save, publish, run

- **Drafts are kept on the server.** Every edit goes into your working copy (*Unsaved changes*), which is autosaved
  after two seconds without another change. Reload the page, leave it, or sign out and in again: the canvas comes back
  with your changes, still unsaved. Each person has their own copy. **More actions → Save** makes a new version
  (*"{name} saved as v{x}."*). **Discard changes** drops the copy and goes back to the last saved version (*"Changes
  discarded. Back to v{x}."*). Leaving with unsaved changes warns you once.
- **Validate** checks the draft with the server's full checks: *"No errors or warnings. This workflow is ready to
  run."*, *"No errors. N warnings to review."* or *"N errors to fix before this can run."*
- **Test run** is a dry run of the *draft* on the server, over a sample of real records (up to 25 per connector).
  Every step runs with its settings; nothing is written (no records, canonical values, held records or events) and
  nothing is sent to any system.
  - **Task instances** shows each step's state, **Try** and **Records (in / out)**, with *· N rejected* where a step
    rejected records. **Samples** next to the counts opens **Before** and **After**: the first three records into and
    out of that step. After the field mapping the records also carry their canonical `facts`.
  - The note under the counts says *"Dry run on N sampled records. Nothing was written."*, and the toast *"Test run
    finished: N records. Nothing was written."* (or *failed*, with the reason, e.g. a source that is syncing at that
    moment: *"{source} is syncing now"*; try again a little later). Records held by a rule are named, e.g. *"25 records
    held at Validation & enrichment"*.
  - At **Human approval** the test run stops (*Awaiting approval*). **Approve and continue** (Developer or Admin) is a
    simulated approval, *"Simulated approval (dry run): nothing is sent."*, and runs the rest, still dry: *"Approved
    in the test run. Simulated approval (dry run): nothing is sent to any system."* Real approvals of decisions stay
    with the approvers.
  - With errors in the checks it does not start: *"Fix N errors before running. The checks below say what and why.
    First: {message}"*
  - The **Data quality** panel then shows the test run's figures, marked *Test run (dry)*.
- **Publish** saves first if needed and refuses while there are check errors (*"Cannot publish: N errors in the
  checks. Fix them first. First: {message}"*): *"{name} published as v{x}. It runs on its trigger: {trigger}."* From
  then on **runs use the published version**. A later Save makes a new version that does not run until you publish
  it: the header shows *Runs v{pub} · v{x} not published*, and **More actions → Publish v{x}** (or **Publish** on the
  current row of **History → Versions**) publishes it (*"v{x} published. Runs now use it."*); the Publish menu item
  has become **Unpublish** (*"{name} unpublished. It will no longer run on its trigger."*). Pause and Resume are in
  the list's ⋯ menu.
- **Run now** processes real records now, on the server, with the **published** version (a workflow that was never
  published runs its saved version, if its sources are connected and its checks, field checks included, are clean;
  otherwise *"{name} is a draft with errors: …"*).
  - One run at a time: *"{name} is already running"*. A run whose worker stopped is closed as failed (*worker lost*)
    within a minute, so the workflow can run again.
  - A step that fails is tried again as often as **Retries** says, waiting 1, 2, 4, 8 … seconds; **Try** shows the
    real tries.
  - The toast follows the run: *"{name}: run finished, N records."* or *"{name}: run failed. {reason}"*. The run is
    listed under **Recent runs** and on the **History** tab with Records (in / out), **Held** (the records it still
    holds, the same ones **View failed records** lists) and Triggered by. The demo's seeded runs keep the demo's
    estimate, with a note saying so.
- **Triggers fire** for published workflows: *On a schedule* every N minutes after the later of the last run and the
  last save or publish; *On event* when the source sends Circularity a webhook (of the event type an Event trigger
  block names, if any; `offer.*` matches every `offer.` event); *On approval* when an instruction is queued for the
  target system; *On file arrival* when a sync of a file-drop source (the recycler partner) reads new files; *On case
  request* when a case moves to re-evaluation. A **Scheduler** or **Event trigger** block on the canvas sets the
  trigger (the Settings tab then says *"Set by the Scheduler block."* or *"Set by the Event trigger block …"*). A
  workflow whose source is paused, disconnected or unavailable is skipped until it is back. The run shows its trigger
  under Triggered by (Schedule, Event, File, Approval, Case, Workflow for a Call workflow step, Resume for a Wait step;
  Manual for Run now).
- **A source's sync is the run of its ingest workflow.** Publish an ingest workflow and its source's syncs (scheduled,
  **Sync now**, webhooks) run that workflow in its published version, settings included, for the resources its
  connector reads; the source's other resources keep syncing through the default graph in the same sync run. A source
  with no published ingest workflow syncs with the default graph, which passes every record on unchanged. Only
  workflows published in the app count (the starting workflows do not); Unpublish or Delete returns the source to the
  default.
- **Outbound settings apply once published here.** When an outbound workflow writing to a target is published in the
  app, the instructions sent to that target use its delivery method's **Timeout** and **Retries** and its write
  connector's **Target operation** (where changed from the defaults). Until then instructions go out as in the demo.
- **Fail this step in the next run** (inspector, under **Testing**) makes the step fail, to rehearse the failure path.
  A test run uses it at once; a real run once you save and publish it.

### 7.5 Settings, history, templates

- **Settings tab**: trigger (schedule with an interval, event, approval, file arrival, case request, manual), owner,
  **Retries** (0, 1, 3 or 5; default 3) and **Alert when** (a run fails, two runs fail in a row, success rate drops
  below 95 %, never). They are saved with the workflow (*"Saved with the workflow."*) and apply once you save and
  publish: a failed run reports *failed after N retries*, and when the alert rule matches, a *Workflow alert* appears
  on the Alerts page for Developer and Admin.
- **History tab**, two panels:
  - **Versions**: every version a save, publish, restore or applied fix made, with when, by and a note, marked
    **Current** and **Published**. The subtitle says which runs: *"Runs use v{x}. Saving makes a new version; publish
    it to make runs use it."* (or *"Not published: Run now tries the saved version."*). **Compare** shows *v{a} → v{b}*:
    added and removed steps, each changed step's settings (**Setting**, **Was**, **Now**; the setting's key, e.g.
    `currency`), links added and removed, and changed workflow settings. **Restore** puts an older version back as a new
    one: *"v0.2 restored as v0.5."*, plus *"Your unsaved changes were dropped."* and *"Publish it to make runs use it."*
    when they apply. **Publish** appears on the current row when a published workflow has a newer saved version.
  - **Runs**: only the runs that really happened, latest first, with **View** (steps with state, duration, in and out
    for the latest run; totals for older ones). Empty: *"No runs yet"*.
- **Documentation tab**: generated from the graph; **Explain this workflow** asks Ask Circularity.
- **Save as template** (More actions or Quick actions): *"Saved as a template. It appears under New workflow."*
  **Reset to template** puts the template's graph back in the draft.
- **Duplicate** creates *"{name} (copy)"* as a draft. **Export JSON** downloads the saved version, block settings
  included (**Import** on the list reads it back). **Delete** asks for confirmation and warns when the workflow is
  published.

### 7.6 When a run fails

- **Investigate** (or `?run=last`) shows which step failed after how many retries, the error log and the run's
  **Held records** by step, field and rule (for the demo's seeded failed run it says nothing was held for real).
  **Diagnose** and **Fix** ask Ask Circularity; **Run now** runs again.
- **Data quality (latest run)** shows the latest real run's records read, passed and held and the fields that failed
  most (*No real run yet* before the first run in the app).
- **Apply the suggested fix** gives the failed step back its settings (and its failure toggle) from the newest earlier
  version in which they were different, as a new version, and says exactly what changed: *"{step} is back to its
  settings from v{x}: {setting} back to {value}. Run now to confirm it turns green."* (*failure toggle off* for a
  rehearsed failure). If the failed run used the saved version, the fix is published at once; if there are unpublished
  saves, the text adds *"Publish v{x} to make runs use it."* With no such earlier version: *"There is no earlier
  version of {name} with other settings for {step} to restore. Change its settings by hand."*
- **View failed records** lists the records the latest run held (record, field, value, rule broken: the real values),
  held by the error handler or the engine, not dropped. **Export CSV** downloads them. **Reprocess** sends them back
  through the published version from the step that rejected them on (that step with its settings as they are now, and
  every step after it): *"N records sent back: X reprocessed, Y still held. Those still break a rule."* Fix the rule
  (and publish) first. With nothing held: *"No held records to reprocess."*

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

`#/integration/tables`: the tables each system exposes and how they link (the demo's systems with a table model: CRM,
EAM, ERP, FSM, PLM, WMS, and every source connected in the app).

- **Sources connected in the app** (from the catalogue or by hand) show what they really send: after their first sync,
  one table per resource they read, its columns from the records' fields with an inferred type (text, number, bool,
  date, datetime, object, list), the record key first. A link between two tables is suggested where at least 90 % of a
  column's values are keys of the other table. Tables you add or edit are kept as you left them; the others follow the
  records on every visit. The demo's systems keep their seeded models.

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
- Beside the demo's decision messages, the stream lists the real messages as they happen, newest first: sync runs
  (`sync.completed`, `sync.failed`, inbound), instructions sent to the enterprise systems (`instruction.sent`,
  `instruction.failed`, outbound) and webhook deliveries a source sent to its own address (`webhook.received`).

## 12. Conflict Queue

`#/integration/conflicts`: where two systems disagree on a canonical field.

- A conflict opens when a sync finds different values for the same field (text compared case-insensitively, numbers
  within 0.5 %). The value used is the one from the **source with authority** (for example the lease system for the
  owner tenant, WMS for location). It closes by itself when the sources agree again.
- Each card shows the field, the record, both values, the authority and the impact (routes using the field are held).
- Managers:
  - **Accept {authority}**: resolves the conflict in favour of the source with authority: *"{id} resolved: {authority}
    is authoritative for {kind}."*
  - **Choose another value**: keep the other source's value (*Keep {source}: {value}*) or **Enter a value**, and give
    a **Reason (kept in the audit trail)**, then **Resolve**: *"{id} resolved: {source}'s value is kept for {kind}."* or
    *"{id} resolved with the value you entered."* That value becomes the canonical value (recorded as a manual
    decision) and the held routes are released. Without a reason: *"Give a reason when you do not keep the value of
    the system with authority."*; with no value typed: *"Enter the value to keep."*
  - **Escalate to owner**: notifies the data owner; the card then says *"Escalated to {owner} by {person}."* The
    conflict stays open and dependent routes stay held. You can still resolve it afterwards.
- **A resolution sticks until a source changes its value.** The next sync with the same differing values does not
  reopen it; when either source sends a new value, a new conflict opens.
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

Loaded rows really reach the data: each row becomes canonical values (asset, quantity, condition grade, location,
owner, received date) from the source *manual*, checked like a sync's. They rank below every connected source (a field
whose source with authority has a value keeps that value), carry no live freshness, and never queue an instruction or
a job. The demo reset removes them again.

Values are split on plain commas: quoted values and values containing commas are not supported.

## 14. Monitor

`#/integration/monitor`: integration health over time.

- Tiles: sync success (24 h; runs with warnings do not count as successes), average latency, failed records (7 days,
  held for reprocessing), fresh within SLA, failing workflows. SLA = twice the poll interval; 15 min for event
  sources; 2 days for manual import; otherwise 60 min.
- **Sync runs, last 24 hours**: one stacked bar per hour (successful, warnings, failures). Select a dip for an
  explanation.
- **Per source** (freshness, SLA, success, failed records, latency).
- **Per workflow** (lowest success first): **Runs (24 h)**, **Success**, **Last run**, **Avg duration** and **p95
  duration**, from the real runs of the last 24 hours. The ▸ before a name opens one row per step: its **p95
  duration** and its **Held records by rule** (e.g. `range 3`, or *None held*). A workflow without a real run in the
  last 24 hours keeps the demo's figures and says so when opened: *"No real run in the last 24 hours: the figures are
  the workflow's seeded history, without steps."*

## 15. Messages you may see

| Message | Meaning |
|---|---|
| Only the Developer or Admin changes integrations. | Your role is read-only here. |
| {name} is paused. Resume it to sync. | Resume the source first. |
| {id} is disconnected/unavailable. Resume or reconnect it first. | The source is not connected. |
| {id} has no resources to read: add a read operation (GET /path) to its connection. | A hand-made source with no read operation cannot sync. |
| Credential expired on {date} | The stored credential has expired; syncs stop until you rotate it (Security tab) or re-authenticate. |
| Token rejected (HTTP 401): the credential is expired or revoked | Test connection: the system refused the credential. |
| Fix the highlighted connection settings first. | The connection fields have errors (shown in place). |
| Enter a full URL starting with https:// | Base URLs must be HTTPS. |
| Add at least one read operation. | A source must read something. |
| A source with this name and vendor already exists. | Pick another display name. |
| Cannot publish: N error(s) in the checks. Fix them first. First: {message} | Open the Checks panel; it lists the server's checks too, field checks included (7.3). |
| Fix N error(s) before running. The checks (below) say what and why. First: {message} | Test run refused by the checks, including the field checks. |
| The simulated system accepts only its sandbox key; another key fails the test at Auth. | Connect dialog: the key typed is not the simulated system's sandbox key. |
| {step}: {setting} … is not a field the records carry. | A block setting names a field the source's records do not have. |
| {step}: Target currency XYZ is not one of USD, EUR, INR. | A setting outside its choices (the same form for other settings). |
| {source} is syncing now | A test run or run reached the source while its sync was running; try again shortly. |
| {name} is a draft with errors: … | Run now refuses a draft whose run would fail. |
| {name} is already running | One run per workflow at a time; wait for the current one. |
| {name} is already published | Publish a newer saved version with More actions → Publish v{x} (or History → Versions) instead. |
| v{x} is the current version. | Restore needs an older version. |
| No held records to reprocess. | The workflow's runs hold no records. |
| The last run of {name} did not fail, so there is nothing to fix. | Apply the suggested fix works only after a failed run. |
| The suggested fix is already applied. Run now to confirm. | Run now to see it turn green. |
| There is no earlier version of {name} with other settings for {step} to restore. Change its settings by hand. | No older version had other settings for the failed step. |
| Unknown block {ref} in step {id}. / Unknown source {ref} in step {id}. | Import: the file names a block or source this workspace does not have. |
| This is not a workflow export: it has no steps. | Import: the JSON is not an Export JSON file. |
| Give a reason when you do not keep the value of the system with authority. | Choose another value needs a reason. |
| These rows were already loaded. Nothing was created twice. | The same import was loaded before. |
| Conflict CF-n is already resolved. | Someone resolved it already. |

Webhooks a source sends to its own address (`/api/webhooks/{source_id}`) are answered by the API only, never shown on a
page: a bad signature gets 401, an event older than 300 seconds 400 `stale_event`, and an event id already received
200 with `{"duplicate": true}`.

## 16. Limits and good to know

- All systems are simulated (see the top of this guide): no named vendor product is really connected. Catalogue
  systems sync from their mocks in source-sim, and a hand-made source syncs from the base URL you gave it (in the dev
  stack, the `http://source-sim:8100/sandbox/<any-name>` test API), every time, like the demo's 21 sources. The AI
  builder offers only the demo's 21 systems.
- Publishing an ingest workflow changes what its source's syncs do (7.4): its settings apply to the resources its
  connector reads (the other resources sync as before). In a demo, reset afterwards (below) to return the demo's data.
- Home's alerts and the Developer's briefing read the live Connection Fabric: one alert per source the Source Map
  shows stale or not connected (*"{name} · feed is stale"*, *sync failing*, *credential expired* or *not connected*),
  one per workflow whose last run failed, and one alert for all open conflicts (*"N open source conflicts"*, *"M hold
  up a decision"*).
- In the dev stack no source starts stale: the simulator's *expired token* fault on Ritchie Bros. Market Data is off by
  default. To show *Needs attention*, *Refresh token and re-sync* and *Re-authenticate*, switch it on with
  `curl -X POST http://localhost:8100/_sim/faults/demo` and press **Sync now** on Ritchie Bros. (or start source-sim
  with `SIM_DEMO_FAULTS=true`).
- The demo reset (`bash scripts/dev/reset.sh`) removes sources connected in the app and returns paused,
  disconnected, failing or expired demo sources to their starting state; it also clears stored credentials, edited
  mappings, manual imports, and the workflow versions and drafts made in the app.
- Workflow drafts are kept on the server per person, so a reload or a sign-out keeps them (7.4). Unsaved edits in a
  source drawer belong to your browser session; signing out drops them.
- *Run now* uses the published version (the saved one if never published); *Export JSON* the saved version; *Test
  run* and *Validate* the draft.
- The demo's seeded workflow runs keep the demo's estimated figures in the Runs table (marked by a note); every run
  made in the app shows real figures.
- Event Streams shows the 70 newest matching events; the Conflict Queue shows 60 cards at a time (*Show more*).
- The CloudEvents the simulated systems send to Circularity (`POST /api/webhooks/source-sim`, HMAC-signed) trigger
  syncs, which Event Streams lists as `sync.completed` or `sync.failed`; the shared delivery itself is not listed
  (deliveries to a source's own address are, as `webhook.received`).
