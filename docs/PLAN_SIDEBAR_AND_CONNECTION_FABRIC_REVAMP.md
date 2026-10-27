# Plan: sidebar, Home and Connection Fabric revamp (new menu, new Home, component kit, warm charcoal and white themes, real icons and logos, near-real integration flows)

**Purpose of this file.** It records what the six design mockups in `images-for-pasting/` ask for, how today's UI differs, the decisions taken, and the design and phases to build it, without losing any agent feature. A fresh session can build the work from it.

| | |
|---|---|
| **Status** | Built on `feature/fabric-revamp` (27 Oct 2026), phases 0–10. W9–W15 and W17–W20 are built as assumed and wait for the Product Owner. Build report: section 14 |
| **Source** | Six design mockups in `images-for-pasting/` (ignored by git), reviewed 27 Oct 2026: the sidebar showcase, four Connection Fabric screens, and *ARTIZENT Circ revamped ui* (Home), added the same day. Decisions W1–W8 taken in the same session |
| **Builds on** | `PLAN_AGENT_FIRST_WORKBENCH.md` (Ask, cards, intents), `PLAN_RBAC_ADAPTIVE_UI.md` (who sees what), `PLAN_LIVE_RUN_AND_LIVE_UI.md` (live wording, run board), `PLAN_EXECUTION_DETAIL_AND_COST_TRACE.md` (IBM Sterling OMS and ShipLane TMS sources) |
| **Branch** | `feature/fabric-revamp`, cut from `main` (PR #15 is merged, so `main` has the execution detail work) |


---

## 1. The asks (from the mockups)

| ID | Mockup | The ask |
|---|---|---|
| V1 | Sidebar Modes Showcase | A **new menu**: section headings (Product, Integration), single-line items, search inside the menu, My Tasks, Alerts, Reports, Data Checks and Settings, Connection Fabric with nine pages, company and user cards at the bottom |
| V2 | Sidebar Modes Showcase | **Four modes**: dark expanded, dark collapsed, light expanded, light collapsed. The dark menu is navy; the light menu is white; the collapsed rail has hover labels and an alert dot |
| V3 | All five | **Real icons** throughout (one consistent line icon set) |
| V4 | Workflow Dashboard, Source Map, SaaS Dashboard, Workflow detail | **Real vendor logos** on systems, workflows and catalogue cards |
| V5 | SaaS Dashboard-2 | A **Connection Fabric Overview**: integration catalogue with counts, category pills, a featured banner, *Recommended for you*, *All integrations* with a category list, and a detail drawer (Overview, Configuration, Data Mapping, Sync & History, Security; usage chart; Sync now, Pause, Edit, Disconnect) |
| V6 | Workflow Dashboard | A **workflow list** with summary tiles, four filters, Open + ⋯ per row, failing rows highlighted with the reason and *Investigate*, 24 h success bars, pagination, and a right column (needs attention, health ring, recent activity) |
| V7 | Workflow detail | A **workflow page**: header with status, version, last run, Validate, Test run, Run now; tabs (Studio, Settings, History, Documentation); a palette of Sources, Transform and Orchestration blocks; white node cards with status and record counts; an error-handler branch, an audit branch and a minimap; recent runs; data quality; workflow details, tags, related systems and quick actions |
| V8 | Source Map | A **source map graph**: systems → canonical tables → models with field links; Graph, List and Matrix views; a system tree; a detail panel with connection details, 30-day usage, sync history and *Test connection*; five summary tiles with monthly change |
| V9 | All | **Near-real flows**: connect, test, sync, pause, disconnect, investigate a failure, run, view failed records, export, save as template |
| V10 | Your instruction | **Keep every agent feature** we have today |
| V11 | Circ revamped ui | A **new Home**: date and greeting with a hero illustration and tagline; an Ask box with five modes (Ask, Analyze, Find, Notify, Automate), example chips and *View more examples*; five KPI tiles with icon, delta and sparkline; *Agent activity* as a timeline with Live, Today and This week and status chips; *Workflow health*; *Key figures* with a period picker; a right column with Activity, Watchlist and Notifications tabs, an attention card and *Quick actions*; *Classic modules* as a grid of module cards with Grid, List and Customize |
| V12 | Circ revamped ui (and all) | A **better-looking component kit** used everywhere: tinted icon tiles, KPI tiles with delta and sparkline, status chips, timelines, pill tabs and segmented controls, quick-action rows, module cards, a top bar with one search that also asks |

## 2. Orientation (code by name; line numbers drift)

| Area | Where it lives today |
|---|---|
| Menu | `NAV`, `navHTML`, `ACT.navToggle`, `ACT.navRail`, `PAGES`, `ANCH`, `INT_TABS` |
| Theme | `:root` and `:root[data-theme="dark"]` tokens (`--side:#141414` / `#000`), `ACT.theme` |
| Icons | `ICON` (28 inline icons) |
| Connection Fabric | `renderIntegration`, tabs from `INT_TABS` |
| Source map | `smGridHTML`, `smChipsHTML`, `smKpiHTML`, `smSideHTML`, `smTick`, `startSync`, `hhInit`/`hhTotals` (health history), the source drawer `sdOpen`/`sdRender`/`sdTabBody`/`sdTestHTML` |
| Workflows | `wfInit`, `wfSeed`, `wfSeedRuns`, `wfListHTML`, `wfRowHTML`, `wfHTML`, `wfEditorHead`, `wfPalHTML`, `wfNodeHTML`, `wfWorldHTML`, `wfInspHTML`, `wfValidate`, `wfSimRun`, `wfRunHTML`, `wfMiniHTML`, `ACT.wfOpen` |
| Source tables | `tgLayout`, `tgGraphHTML`, `tgListHTML`, `tgHTML` |
| Other tabs | `intModels`, `evTable`, `intConflicts`, `intImport` |
| Home | `renderHome`, `afBriefing`, `aomeItems` (Needs you), `AF.journal` and `AF.ui.runs` (Agent activity), `AF.ui.pins` (Pinned), `AF.ui.watches` (Watching), `afFiguresHTML` (Key figures with *Explain this number*), `AF_STARTERS`, `#afhq` and `ACT.afHomeAsk`, `ACT.afMode` (Business / Technical) |
| Top bar | search, tenant, *Live · updated*, region, *Data checks* pill, ✦ Ask, inbox, account, theme |
| Agent features | `AF` block: `defIntent` for `sources.stale`, `sources.diagnose`, `mapping.suggest`, `mapping.refine`, `source.setup`, `workflow.draft`, `workflow.explain`, `workflow.diagnose`, `workflow.fix`, `workflow.clone`; `afAssist` (✦) buttons; Ask panel; `#afTgx` (Suggest links); `#afClean` (Clean this file); *Assist* in the workflow editor |

## 3. Today against the mockups (checked 27 Oct 2026)

| Area | Today | Mockup |
|---|---|---|
| Menu | Two-line items, no section headings; black in both themes; search in the top bar; no My Tasks, Alerts, Reports, Data Checks or Settings; user in the top bar | Sections, single lines, search in the menu, five new items, company and user cards at the bottom; white in light mode, navy in dark |
| Connection Fabric pages | Seven tabs; no Overview, no Monitor | Nine pages, including Overview and Monitor |
| Workflow list | Text chips (35, 33, 1, 1); search and type filter; five buttons per row; no right column | Tiles, four filters, Open + ⋯, failing row in red with the reason, right column, pagination |
| Workflow editor | System palette as yellow cards; yellow nodes with *Success* only; no record counts, error branch or minimap; no run history or data quality panel | Generic block palette; white cards with record counts; error-handler and audit branches; minimap; runs; data quality; details panel |
| Source map | Card grid with freshness, completeness and confidence bars | Graph with field links, tree, detail panel, Graph, List and Matrix views |
| Catalogue | None; *Add source* opens a draft connection | Full catalogue with categories, recommendations and a detail drawer |
| Icons and logos | 28 home-made icons; two-letter badges for systems | One icon set; full-colour logos |
| Agent features | Ask, ✦ on many rows, mapping and workflow intents, journey strip | Not shown (the mockups pre-date them) |
| Home | Title, Business / Technical switch, Ask box with three starters, Briefing (bullets), Needs you, Pinned, Agent activity (list), Watching, Key figures (three tiles with *Explain this number*) | Greeting and date, hero, Ask with five modes and examples, five KPI tiles with sparklines, Agent activity timeline with tabs and status chips, Workflow health ring, six Key figures with a period picker, right column (Activity, Watchlist, Notifications; attention card; Quick actions), Classic modules grid. No Briefing or Needs you panel |
| Top bar | Search, tenant, Live, region, *Data checks*, ✦ Ask, inbox, account, theme | One search (*Search returns, assets, workflows, or ask anything… ⌘K*), tenant, Live dropdown, region, bell, theme, avatar |
| Components | Flat chips and panels; few icons; one accent | Pastel icon tiles in several hues, deltas with arrows, sparklines, timelines, pill tabs, module cards |

**Problems in the mockups**, resolved by the decisions below:
- their figures disagree with each other and with the app;
- each mockup shows a different Integration menu;
- they show a named person and email under *Connected by*;
- they omit the journey strip, Ask and ✦ (the Home mockup also drops Briefing and Needs you);
- they use green and navy primary buttons alongside yellow.

## 4. Decisions

| # | Decision | State |
|---|---|---|
| W1 | **Logos:** full-colour, as inline SVG inside the page. They work offline and on GitHub Pages, with no external calls. approved | Decided |
| W2 | **Systems the app doesn't have** (Workday, Jira, Confluence, PostgreSQL, MySQL, SQL Server, Amazon S3, Azure Blob, Excel/SharePoint, Dynamics 365, Oracle EBS, NetSuite, Microsoft Teams, Google Drive, Snowflake) appear in the catalogue as **Available**, not connected. Connected sources, workflows and decision figures do not change | Decided |
| W3 | **Numbers are derived from app data.** Every tile, ring, chart and count is computed from `SOURCES`, `S.wf`, `MAPPINGS`, the table models and the health history, so all pages agree. The mockups are layout, not data | Decided |
| W4 | **New look for the whole app:** a new dark mode and a white menu in light mode, on every page. The dark mode was first built navy; W21 replaces navy with warm charcoal | Decided, revised by W21 |
| W5 | **My Tasks, Alerts, Reports, Data Checks and Settings become real pages**, built from what exists (see 5.5) | Decided |
| W6 | **Artizent yellow stays the accent:** primary buttons, active markers and focus rings. Charcoal is only the dark-mode surface; warnings are amber, not yellow | Decided |
| W7 | **Workflow canvas uses the mockup's white cards** (charcoal in dark mode), with logos or step icons, per-node status, records in and out, an error-handler branch and a minimap; yellow marks selection, red marks failure | Decided |
| W8 | **Branch from `main`** once PR #15 is merged (it is) | Decided |
| W9 | **Monitor** = integration health over time: sync success, latency, failed records, freshness against SLA, per source and per workflow | Assumed |
| W10 | **Reports** = six exportable reports: predicted vs actual, evidence packs, recovery waterfall, carbon avoided, integration health, audit extract (CSV or PDF via print) | Assumed |
| W11 | **Settings** = profile, theme, region and currency, notifications, agent autonomy (also stays under Access), presenter options | Assumed |
| W12 | **Roles, not names:** *Connected by* shows a role (for example *Sales Operations · integration owner*), never a person's name or email | Assumed (house rule) |
| W13 | **Icon set:** Lucide (ISC licence), inline SVG paths, no font or CDN | Assumed |
| W14 | **On a phone**, the source map opens in List view and the workflow canvas opens read-only with *Open on a larger screen* | Assumed |
| W15 | **Catalogue size:** today's 21 sources (20 connected, 1 not yet provisioned) plus the 15 Available ones, so 36 integrations (not the mockup's 82) | Assumed, follows W3 |
| W16 | **Component kit from the Home mockup:** tinted icon tiles use a fixed set of category hues (decisions, evidence, re-evaluation, inspections, money, integration, agents, alerts) as soft fills behind line icons, in both themes. **Yellow stays the only action colour** (buttons, active markers, focus), so W6 holds | Decided |
| W17 | **Top bar as in the mockup:** one search that finds records and also asks (a question opens the Ask panel; a command runs from the command bar); tenant; a *Live* dropdown (live, or pause live updates for a presentation); region; the bell (Alerts); theme; account menu. *Data checks* moves to the menu and Quick actions; the inbox merges into the bell. A compact ✦ Ask icon stays beside the bell so Ask is one click away on every page | Assumed |
| W18 | **Hero:** an original illustration drawn as SVG in our palette (no stock photo), with the tagline *From data to decisions, with clarity.* It is hidden on phones and in Technical mode | Assumed |
| W19 | **Home stays role-aware:** the five KPI tiles, the middle panels and Quick actions change by role (table in 5.13). *Workflow health* appears for Developer and Admin only | Assumed |
| W21 | **Dark mode is warm charcoal, not navy and not pitch black** (27 Oct 2026, after reviewing the built navy theme and the pre-agent build's warm black). Page #0E0E0D, panels #181816 / #1F1F1D / #292926, menu #0A0A09, borders #2C2B28, text #F3F2EE / #CBC8C1 / #A19D95, amber warnings #E5A543, muted category hues. Brand yellow stays #FFDD00, the yellow in the logo artwork. Applies to the revamp, the previous look, the demo build and the framework pages | Decided |
| W20 | **Briefing and Needs you are kept:** Briefing becomes the line under the greeting (*Your AI agents are ready. 2 access requests to decide; 3 workflows need attention.*); Needs you becomes the first tab of the right column, open by default when it has items | Assumed |

## 5. Design

### 5.1 Theme tokens (V2, W4, W6)

**New tokens**
- `--side-bg`, `--side-ink`, `--side-mut`, `--side-act` (active row), `--side-line` for the menu.
- `--surface-raised` for drawers and floating panels.
- `--char-950` to `--char-600` for the dark mode (W21).

**Values**

| Theme | Page | Panels | Menu |
|---|---|---|---|
| Light | `#FAF8F5`, as today | white | white menu, ink text, yellow left bar and soft yellow fill on the active row |
| Dark (W21) | `#0E0E0D` | `#181816` / `#1F1F1D` | `#0A0A09` |

- **Dark lines and muted text:** blue-grey at the same contrast as today.
- **Yellow accent:** unchanged in both themes.
- **Charts:** chart colours are re-checked on charcoal. The run board and the Analytics charts keep their meaning.
- **Contrast:** every pair of text and background meets WCAG AA. A token table goes in the build report.

### 5.2 Icons (V3, W13)

- **Replace the 28 `ICON` entries** with Lucide equivalents. Same keys, so call sites don't change.
- **Add the icons the mockups need:** tasks, bell, report, checks, settings, building, logout, search, workflow, database, file, api, stream, mapping, enrichment, filter, aggregation, expression, lookup, join, scheduler, event trigger, branch, loop, call workflow, wait, minimap, graph, list, matrix, play, pause, sync, unplug and shield.
- **Format:** 24 px grid, 1.75 stroke, `currentColor`, so they follow the theme.

### 5.3 Logos (V4, W1, W2)

- **Library:** a `LOGO` map from system key to inline SVG (viewBox 0 0 32 32), with brand colours.
  - **Connected sources:** Salesforce, Oracle (Lease and Finance Management), SAP (S/4HANA, Ariba), IBM (Maximo, Sterling OMS), ServiceNow, Siemens Teamcenter, Aras, MasterControl, Bentley, Manhattan Associates, Optoro, SafetyCulture, Fixably, AWS, Ritchie Bros., Machinio, Sims Lifecycle, Persefoni, and ShipLane (our own, fictional mark).
  - **Catalogue-only systems (W2):** Workday, Atlassian Jira and Confluence, PostgreSQL, MySQL, Microsoft SQL Server, Amazon S3, Azure Blob Storage, Microsoft Excel/SharePoint, Dynamics 365, Oracle EBS, NetSuite, Microsoft Teams, Google Drive, Snowflake.
- **Size:** each mark is simplified to 1–3 KB, about 80 KB in all.
- **Fallback:** today's two-letter badge, used when a key has no logo (for example a source the user adds).

- **Where logos appear:**
  - source cards, the tree, the graph and the detail panel;
  - workflow rows and canvas nodes;
  - catalogue cards and the table;
  - the handoff *Target applications* chips;
  - the run board system column.

### 5.4 The menu (V1, V2, V10)

**Structure**

| Section | Items |
|---|---|
| (top) | Home · Command Center › · My Tasks (count) · Alerts (count) |
| **PRODUCT** | Decision Workbench › (Asset intelligence, Returned assets, Expected returns) · Analytics › · Reports › · Data Checks › |
| **INTEGRATION** | Connection Fabric ▾ (Overview, Workflow Studio, Source Map, Source Tables, Canonical Models, Event Streams, Conflict Queue, Manual Import, Monitor) |
| (rest) | MCP & Tools › · Process Orchestration › · Audit & Provenance › · Access & Governance › · Settings |
| (bottom) | Company card (Northfield Industrial Leasing · Production · 8 sites, with a dropdown for the tenant and *DI Framework overview*) · user card (role, sign-out) |

**Behaviour**
- **Search box with ⌘K / Ctrl+K:** opens today's command bar, so agent commands and search stay one feature.
- **Counts:**
  - My Tasks = `aomeItems().length`;
  - Alerts = open notifications + escalations + failing sources and workflows;
  - Connection Fabric pages keep today's badges.
- **Collapsed rail:**
  - icons only, with a tooltip on hover and keyboard focus;
  - a red dot on Alerts when there are any;
  - the active page keeps the yellow bar;
  - the company and user cards shrink to icons.
- **Roles:** what each role sees is unchanged. `canPage` still hides pages; for example the Executive has no Connection Fabric. Hidden sections drop their heading.
- **Phone:** the menu opens as today's drawer, with the same sections.
- **URLs:** existing hashes keep working. New ones: `#/tasks`, `#/alerts`, `#/reports`, `#/checks`, `#/settings`, `#/integration/overview`, `#/integration/monitor`, `#/integration/studio/WF-101` (a workflow's own page). `#/integration` opens Overview.
- **Breadcrumb:** pages under Integration get *Integration › Connection Fabric › Source Map* above the title, as in the mockups.

### 5.5 New pages (W5, W9–W11)

| Page | Content | Reuses |
|---|---|---|
| **My Tasks** | Everything whose next step is yours, grouped (decide, supply evidence, confirm, fix integration), with filters and the ✦ *Do it for me* plans | `aomeItems`, Home › Needs you, `afPlan` |
| **Alerts** | Notifications, escalations (the execution-detail clock), failing workflows, stale or unavailable sources and open conflicts. Each alert can be acknowledged, assigned or opened; ✦ *Explain* | `S.notes`, `handoff.escalated` events, `S.wf`, `SOURCES`, `CONFLICTS` |
| **Reports** | Six reports (W10), each with a preview, scope (tenant, period) and export. ✦ *Summarise this report* | Analytics data, `afEvidencePack`, the audit log |
| **Data Checks** | Today's data checks as a page: what is checked, last result, owner, ✦ *Explain*. The top-bar pill stays as a shortcut | the Data checks drawer |
| **Settings** | Profile (role), theme, region and currency, notifications, agent autonomy, presenter options | `ACT.theme`, `S.rg`, `AF.cfg.auto` |

### 5.6 Connection Fabric › Overview, the catalogue (V5, W2, W15)

**Layout**
- **Header:** *Connection Fabric*, with the integration guide.
- **Tiles:** Connected · Needs attention · Available.
- **Search and New integration:** the search accepts plain language and runs the `source.setup` intent, for example *"connect our HR system"*.
- **Category pills with counts:** CRM, ERP, OMS, EAM, WMS, TMS, Databases, Collaboration, Storage, Analytics, Security, Custom.
- **Featured banner:** *Build a connected enterprise*, with three claims, worded as product capability and not as certification (see section 8).
- **Recommended for you:** four cards ranked by the agent from open gaps, for example *ShipLane TMS feed is stale* or *Oracle EBS would supply supplier invoices for Reconcile*. Each card has a ✦ *Why recommended* and *Connect* or *Manage*.
- **All integrations:** a category list on the left and a table on the right (integration, type, status, last sync, owner role, ⋯), with sorting.

**Detail drawer** (clicking a row or card)

| Tab | Content | Today's equivalent |
|---|---|---|
| Overview | Connection health, connection details (environment, instance, auth, *Connected by* as a role, connected on, last sync), usage and performance (records synced, API calls, success rate; 7D, 30D and 90D chart from the health history), permissions, key features, troubleshooting | — |
| Configuration | The connection settings | the source drawer's Connection tab |
| Data Mapping | The field mapping, with ✦ *Suggest mappings* and *Accept all high* | Mappings |
| Sync & History | Sync history and failures | Sync |
| Security | Auth, scopes, secrets rotation and audit | Security |

**Footer:** Sync now · Pause · Edit · Disconnect. Disconnect lists the workflows that use the source (`wfUsing`) and asks for confirmation.

**Available (catalogue-only) systems** open a connect flow (5.10) instead of the drawer.

### 5.7 Workflow Studio, the list (V6)

**Header and controls**
- **Tiles:** Total workflows (across N source systems) · Published (running and healthy) · Failing (needs attention) · Draft (not yet published). Derived (W3).
- **Filters:** search; All types (Ingest, Outbound, Decision); All systems (with logos); All statuses; sort by Last run.
- **New workflow:** yellow.

**Table**
- **Columns:** checkbox · workflow (name and ID · version) · type · source system (logo, system type and vendor) · trigger · status · last run · 24 h success with a mini bar · owner (role) · actions.
- **Actions:** *Open* and ⋯ (Run now, Pause, Duplicate, Export JSON, Delete). Edit, Run, Pause, Copy and Delete move into ⋯, and the guarded actions keep their checks.
- **Failing row:** red tint, the reason inline (*Schema drift · 3 retries*) and an *Investigate* button.
- **Bulk bar:** appears when rows are selected; Run, Pause and Export.
- **Pagination:** 20 per page.

**Right column**
- **Needs attention:** failing workflows, expired credentials and high failure rates, each with ✦ *Diagnose*.
- **Workflow health:** a ring with published, failing and draft.
- **Recent activity:** the last runs, with time ago.

### 5.8 Workflow Studio, a workflow's page (V7)

**URL and header**
- **URL:** `#/integration/studio/WF-101`. `ACT.wfOpen` routes here.
- **Header:**
  - back arrow, logo, name, status chip, version, *Last run 8 min ago*;
  - More actions, Validate, Test run, **Run now**, and ✦ *Assist* (today's editor Assist).
- **Tabs:** Workflow studio · Settings (trigger, schedule, owner, retries, alerts; today's Trigger and Owner move here) · History (all runs) · Documentation (generated from the graph, with ✦ *Explain this workflow*).

**Canvas (W7)**
- **Palette, grouped:**
  - **Sources:** CRM, ERP, OMS, EAM, WMS, TMS, Database, File, API and Streaming. Each opens a list of the connected systems of that type, with logos.
  - **Transform:** field mapping, enrichment, filter and condition, aggregation, expression, lookup, join, validation, timestamps to UTC, currency.
  - **Orchestration:** scheduler, event trigger, branch, loop, call workflow, wait.
  - **Fixed Circularity steps:** canonical models, evidence snapshot, decision, send instruction. They keep today's rules: they can't be rewired or deleted.
- **Node cards:** logo or icon, name, subtitle, status dot, records in and out, time ago. A failed node is red, with the reason.
- **Branches:**
  - every ingest workflow gets an **Error handler** (invalid records, with reprocess);
  - every workflow gets **Write to audit log**;
  - ingest workflows get **Publish to event stream** after *Load to model*.
  - These are real nodes that validation understands.
- **Canvas tools:** zoom, fit, auto layout, undo and redo, **minimap**, and an *Overview / Details / Data flow* switch. Data flow labels each edge with its record count.
- **Rules and actions kept:** validation (`wfValidate`), drag to link (`wfCanLink`), test run (`wfSimRun`) and every agent action are unchanged in behaviour.

**Panels**
- **Recent runs:** run ID, status, start, duration, records in and out, errors, triggered by, *View*. *View* opens the run, with per-node timings and *View failed records*.
- **Data quality (latest run):** a valid, warnings and errors ring; field completeness bars; *View failed records*.
- **Right column:**
  - workflow details (name, description, version, status, owner role, trigger, schedule, last and next run, 7-day success, average duration);
  - tags;
  - related systems;
  - quick actions (Duplicate, Save as template, Export JSON, Delete).

### 5.9 Source Map (V8)

**Header and filters**
- **Tiles:** Connected sources · Tables modelled · Field mappings · Active workflows · Integration health, each with *+N this month*, derived from the health history and the event log.
- **Filters:** search; All systems; All categories; All statuses; **Show field links** toggle; Graph · List · Matrix.

**Graph view**
- **Columns:** systems (logo, status, tables and fields) → canonical tables (Asset, Condition, Demand, Intervention, Lease, Service case: the canonical models we have, per W3) → models and decisions (Demand matching, Condition grading, Resale price, Prep cost and time, Service exposure, Decision, Reconcile).
- **Edges:** coloured by system.
- **Interaction:** clicking a node highlights its paths. Field links show counts, and the field pairs on hover.
- **Navigation:** minimap, zoom, fit.

**List view:** today's source cards, kept as they are (freshness, completeness, confidence, method chip, steps used), restyled.

**Matrix view:** systems × canonical models. Each cell shows the mapped field count, and turns red for a stale or broken mapping.

**Left tree:** Systems (N) and Tables (58), grouped by category, with logos and status dots, and a search box.

**Right panel** (selected system)
- **Header:** logo, name, *type · connector*, Live chip.
- **Tabs:** Overview, Tables (N), Fields (N), Sync, Settings.
- **Content:** description, connection details, usage over the last 30 days (records synced, success rate, failed records), recent sync history, *Test connection* (today's `sdTestHTML` steps), ⋯ (Sync now, Pause, Disconnect), and ✦ *Diagnose* when the source is stale.

### 5.10 Near-real flows (V9)

Each flow runs in the page, with realistic steps, timings and results; nothing leaves the browser.

| Flow | Steps |
|---|---|
| **Connect an integration** | Catalogue card → choose an auth method (OAuth consent screen, API key, service principal, SFTP) → scopes → **Test connection** (DNS, TLS, auth, permissions, sample read, each with a result) → ✦ *Suggest mappings*, then accept or edit → first sync with a progress bar → Connected. It appears in the source map and creates its ingest workflow as a draft |
| **Investigate a failing workflow** | *Investigate* → the run page with the failed node, error log, retries and a schema-drift diff → ✦ *Diagnose* (`workflow.diagnose`) → ✦ *Fix* (`workflow.fix`) shown as a plan → apply → *Run now* → green |
| **Sync now / Pause / Resume** | Sync now shows progress and the record count; Pause stops scheduled syncs and marks dependent workflows *Paused upstream* |
| **Disconnect** | Shows the workflows and decisions that depend on the source, asks for a typed confirmation, then marks it *Disconnected* with *Reconnect* |
| **Run now / Test run / Validate** | Today's simulation, now with per-node record counts, the error branch and a run record in History |
| **View failed records** | A table of the invalid records (field, value, rule broken), with *Reprocess* and *Export CSV* |
| **Export / Save as template / Duplicate** | Downloads the workflow JSON; templates appear under *New workflow* |
| **Credential expiry** | One source's token expires on a schedule; it shows in Needs attention, Alerts and the source panel, and *Re-authenticate* reruns the OAuth step |

### 5.11 Agent features we keep, and where they go (V10)

| Feature today | Where it is after the revamp |
|---|---|
| Ask panel (Ctrl+J), the ✦ Ask button | The top-bar search also asks (W17); a compact ✦ Ask icon stays beside the bell; Ctrl+J unchanged; available on every new page |
| Command bar (Ctrl+K) | Opened from the menu's search box as well as the shortcut |
| Home: Briefing, Needs you, Agent activity, Key figures, Pinned, Watching, Business / Technical, starters | All kept in the new Home (5.13):
- Briefing under the greeting;
- Needs you as the first right-column tab;
- Agent activity as the timeline (with *Show trace* and *Undo*);
- Key figures with ✦ *Explain this number*;
- Pinned in the right column;
- Watching as Watchlist;
- the switch in the header;
- starters as example chips.

Needs you also feeds My Tasks |
| ✦ on rows (sources, events, conflicts, cases) | Kept on every row in the new tables, tree and graph panels |
| `sources.stale`, `sources.diagnose` | ✦ *Diagnose* in Needs attention, Alerts and the source panel |
| `mapping.suggest`, `mapping.refine`, *Accept all high* | Catalogue drawer › Data Mapping; the connect flow; source panel › Fields |
| `source.setup` | Catalogue search, *New integration*, the connect flow |
| `workflow.draft`, `workflow.explain`, `workflow.diagnose`, `workflow.fix`, `workflow.clone` | *New workflow*, Documentation tab, *Investigate*, Assist, Duplicate |
| Source tables ✦ *Suggest links* (`#afTgx`) | Kept on Source Tables, and in the Matrix view |
| Manual import ✦ *Clean this file* (`#afClean`) | Kept on Manual Import |
| Data checks pill | The Data Checks page, the menu and *Run data checks* in Quick actions (W17) |
| Journey strip (10 steps) | Kept under the top bar on every page that has it today |
| Live run board, model cards, presenter menu, evidence pack, *Prepared by agent* badges, autonomy settings | Unchanged; autonomy is also reachable from Settings |
| New | ✦ *Why recommended* on catalogue cards; ✦ *Explain* on alerts and on Monitor dips; ✦ *Summarise* on reports; the five Ask modes on Home |

### 5.12 Component kit (V12, W16)

One set of components, built once and used on Home, the new pages and every Connection Fabric page. Each is a small render function with light, dark and phone styles.

| Component | What it looks like | Used on |
|---|---|---|
| **Icon tile** | 36 px rounded square, soft fill of a category hue, Lucide icon in that hue | KPI tiles, Key figures, module cards, Quick actions, timelines |
| **KPI tile** | Icon tile, value, label, delta (▲ or ▼ with %, coloured green or red by meaning, not by direction) and a 30-day sparkline; the whole tile is a link | Home, Overview, Workflow Studio, Source Map, Monitor |
| **Status chip** | Pill with a dot: Completed, Success, Published, In progress, Investigating, Action required, Failed, Draft, Live, Syncing, Stale, Available | Everywhere statuses show |
| **Timeline list** | Vertical rule with coloured dots; each row has an icon tile, title, sub-line, time ago and a status chip | Agent activity, Recent activity, run history, Alerts |
| **Pill tabs and segmented control** | Rounded tabs (Live · Today · This week; Grid · List; Graph · List · Matrix; 7D · 30D · 90D), keyboard-navigable | Home, Source Map, catalogue drawer, Monitor |
| **Quick-action row** | Icon, label, chevron; a settings gear chooses which actions show | Home right column, Settings |
| **Module card** | Icon tile, module name, one-line purpose, arrow; Grid or List; *Customize* hides, shows and reorders cards, remembered per account | Home *Classic modules* |
| **Attention card** | Red-tinted card with a warning icon, a count headline, one line and a button | Home, Workflow Studio, Alerts |
| **Health ring** | Donut with the % in the centre and a legend with counts | Workflow health, Data quality, Monitor |
| **Ask box** | Mode tabs (Ask, Analyze, Find, Notify, Automate), input with a ✦ icon, yellow send button, example chips, *View more examples* | Home; the same box opens in the Ask panel |

**Delta basis (W3):** the same measure 30 days earlier, from the existing monthly series (`MONTHS`, Analytics) or the health history. Where no history exists, the delta and sparkline are left out, never invented.

### 5.13 Home (V11, W17–W20)

**Layout (desktop), top to bottom**

1. **Header:**
   - date (from the app clock) and *Good morning / afternoon / evening, {role}*;
   - the Briefing line (W20);
   - the hero illustration and tagline at the right (W18);
   - Business / Technical switch and the agent provider label, kept at the right of the header.
2. **Ask box** (V12):

   | Mode | What it runs | Today's equivalent |
   |---|---|---|
   | **Ask** | The question goes to the agent | `#afhq`, `ACT.afHomeAsk` |
   | **Analyze** | What-if, compare routes, explain | Explain and what-if intents |
   | **Find** | Searches records | The command bar's search |
   | **Notify** | Drafts a notification or escalation | `notify.send`, `escalation.send` |
   | **Automate** | Drafts a workflow or an autonomy change | `workflow.draft`, autonomy |

   The example chips are today's role starters (`AF_STARTERS`); *View more examples* lists every intent the role can run.
3. **Five KPI tiles** for the role (table below). Each opens its filtered list.
4. **Two columns:**
   - **Agent activity:** Live, Today and This week tabs; a timeline fed by the journal, runs and events, with statuses Completed, Investigating, In progress and Action required; *View all* goes to Audit. *Show trace* and *Undo* stay on each row.
   - **Workflow health** for Developer and Admin; a *Decisions by stage* ring for other roles.
   - **Key figures:** six tiles with a *Last 30 days / 90 days / 12 months* picker; ✦ *Explain this number* stays on every figure.
5. **Classic modules:** module cards for every page the role can open, with Grid, List and Customize.

**Right column**

- **Tabs:** Needs you (W20) · Activity · Watchlist (today's *Watching* rules, plus *Add watch*) · Notifications (count).
- **Attention card:** failing workflows, escalations or SLA risks for the role, with *View issues*.
- **Quick actions:** per role, for example *New workflow*, *Connect a source system*, *Run data checks*, *View Command Center*, *Open Decision Workbench*. The gear chooses which show.
- **Pinned cards:** below Quick actions.

**Role table (W19)**

| Role | Five KPI tiles | Middle panel | Quick actions |
|---|---|---|---|
| Admin | Decisions ready · Cases missing evidence · Require re-evaluation · Inspections due · Potential recovery | Workflow health | New workflow, Connect a source, Run data checks, Command Center, Decision Workbench |
| Developer | Failing workflows · Stale sources · Mappings needing attention · Conflicts open · Integration health | Workflow health | New workflow, Connect a source, Run data checks, Event stream, Source map |
| Planner | Ready to submit · Missing evidence · Re-evaluate · Received this week · Potential recovery | Decisions by stage | Returned assets, Request evidence, Compare routes, Decision Workbench |
| Approver | Waiting for me · Escalations · Close calls · Over my limit · Value waiting | Decisions by stage | Approval inbox, Escalations, Compare routes |
| Engineer | Inspections due · Results to record · Certifications expiring · Re-tests · Gate holds | Inspections by grade | Record a result, Inspection queue |
| Finance | Outcomes to confirm · Variance this month · Predicted vs actual · Carrier bills to check · Net recovery | Predicted vs actual ring | Confirm outcomes, Reconcile and learn, Reports |
| Warehouse Manager | Inbound this week · Steps waiting on WMS · Escalations · Capacity used · Holding days | Receiving load | Plan receiving, Steps waiting |
| Executive | Net recovery · Potential recovery · Value at risk · Decisions open · Carbon avoided | Recovery waterfall (mini) | Command Center, Analytics, Reports |

**IDs kept:** `#afNeeds` (the Needs you tab panel), `#afActivity`, `#afFigures` and `#afhq`. Tests and the video use them.

**Phone:**
- greeting and Ask first;
- KPI tiles in a two-column grid;
- the right column folds under the main column;
- no hero.

### What stays the same
Every decision, value, route, gate, role rule and URL that exists today. The agent, its intents and its guard rails. Run board behaviour. The execution-detail work (OMS, TMS, cost trace, escalation).

### Do not break
- **All existing suites**, including:
  - `af4`, which drives mapping, Source Tables, the workflow editor, conflicts, import and events;
  - `rbac`, for read-only Integration views;
  - `live`, which scans Integration in both themes.
- **The demo video pipeline** (`docs/demo/video/pipeline/record.py`, which uses Integration selectors).
- **Element IDs and `data-act` names that tests use** stay as they are. Where markup moves, the ID moves with it.

## 6. Data rules

- Everything new is **derived at render**: counts from `SOURCES`, `S.wf`, `MAPPINGS` and the table models; history and charts from `hhInit` and a deterministic series per source (`hashId`). **No new `rnd()` calls**, so the seeded data does not move.
- Catalogue-only systems live in a separate `CATALOG` list with `status:'available'`. They are never counted as connected, never feed a decision, and never appear in workflow pickers until they are connected through the flow in 5.10.
- Invariants:
  - every tile agrees with the table under it;
  - Overview, Source Map and Monitor show the same connected and failing counts;
  - every logo key resolves or falls back to a badge.

## 7. Phases (each ends with tests, screenshots and a short report)

| # | Phase |
|---|---|
| 0 | Baseline: all suites green on `main` |
| 1 | Theme tokens (charcoal dark, white menu in light), the Lucide icon set and the component kit (5.12) |
| 2 | The menu: sections, search, new items, counts, rail with tooltips, company and user cards, phone drawer, breadcrumbs |
| 3 | Top bar (W17) and the new Home (5.13) for all eight roles |
| 3b | New pages: My Tasks, Alerts, Reports, Data Checks, Settings |
| 4 | Logo library and `CATALOG`; Connection Fabric › Overview with the detail drawer |
| 5 | Workflow Studio list: tiles, filters, Open + ⋯, failing rows, right column, pagination |
| 6 | A workflow's page: header, tabs, grouped palette, white nodes with counts, error and audit branches, minimap, runs, data quality, details |
| 7 | Source Map: graph, list, matrix, tree, detail panel |
| 8 | Monitor; restyle Source Tables, Canonical Models, Event Streams, Conflict Queue and Manual Import with the same header, tiles and logos |
| 9 | Near-real flows (5.10) |
| 10 | Docs (README, CHANGES Update 17), screenshots, and a check that the demo video still records |

**If time is short:** 1 → 2 → 3 → 5 → 6 → 7 → 4 → 3b → 9 → 8.

## 8. Rules

- Plain English.
- Circularity recommends and sends approved instructions; the enterprise systems do the work.
- No *simulated* or *demo* wording in the interface.
- Roles, not names (W12).
- `$9,600` and `−$370` money format; middle-dot labels.
- Yellow is the only accent (W6).
- No security or compliance claims stated as fact: the featured banner says *Role-based access and audit on every connection*. better use rbac and audit , no soc2 and any compliance pls

## 9. Tests

**New suite `fabric.js`**
- menu sections and items per role;
- counts on My Tasks and Alerts equal their pages;
- rail tooltips, and the rail working by keyboard;
- every page reachable, in both themes;
- contrast of key token pairs;
- every system shows a logo or a badge, and `FEAT.logos=false` removes every logo;
- catalogue counts match `SOURCES` and `CATALOG`; Available systems never appear as connected;
- workflow tiles equal the table;
- a failing row shows the reason and *Investigate*;
- the workflow page shows record counts, the error branch and the minimap;
- run history and data quality agree with the last run;
- source map Graph, List and Matrix agree on counts;
- each flow in 5.10 completes and leaves the right state, including disconnect impact and reconnect;
- every agent entry point in 5.11 is present and opens its intent;
- Home for all eight roles:
  - the right tiles;
  - deltas only where history exists;
  - each tile's number equals its list;
  - all five Ask modes route correctly;
- `#afNeeds`, `#afActivity`, `#afFigures` and `#afhq` are present; Briefing, Pinned and Watchlist work;
- *Customize* on Classic modules is remembered per account;
- the top-bar search asks and finds;
- the phone layout works at 390 px;
- no *undefined* or *NaN* on any page.

**Existing suites:** all green. Any expectation that changes because markup moved is updated and listed in CHANGES, never weakened.

## 10. Product Owner questions (recorded as assumed)

- **W9:** what Monitor should show.
- **W10:** which reports.
- **W11:** what Settings holds.
- **W12:** roles instead of names under *Connected by*.
- **W13:** the icon set.
- **W14:** the phone behaviour of the graph and canvas.
- **W15:** catalogue size.
- **Featured banner claims:** which security or compliance claims (if any) may be shown.
- **ShipLane:** its logo (it is our fictional TMS).
- **W17:** dropping the *Data checks* pill and the inbox from the top bar.
- **W18:** the hero illustration and tagline.
- **W19:** the KPI tiles per role.
- **W20:** Briefing as a line, Needs you as a tab.
- **Copy:** whether the greeting uses the role (*Good afternoon, Approver*) or the account label.

## 11. Definition of done

- [x] V1–V12 visible and working (table 13)
- [x] Every agent feature in 5.11 present
- [x] All suites green, `fabric.js` green; the video recorder's selectors checked (the recording itself was not re-run, see 14.6)
- [x] Screenshots of the new screens in light, dark and phone
- [x] README and CHANGES updated
- [ ] Product Owner confirms W9–W15 and W17–W20

## 12. Prompt for a fresh session

> Read `docs/PLAN_SIDEBAR_AND_CONNECTION_FABRIC_REVAMP.md` and the six images in `images-for-pasting/`. Branch `feature/fabric-revamp` from `main`. Build the phases in order. Keep every agent feature listed in 5.11, keep existing element IDs and `data-act` names, derive every number from app data, add no `rnd()` calls, and run all suites before and after each phase.

## 13. Does the plan match the asks?

| Ask | Section | Match |
|---|---|---|
| V1 New menu | 5.4 | Yes |
| V2 Four modes, dark and white | 5.1, 5.4 | Yes; dark is charcoal, not the mockup's navy (W21) |
| V3 Real icons | 5.2 | Yes |
| V4 Real logos | 5.3 | Yes|
| V5 Catalogue Overview | 5.6 | Yes; 36 integrations, not 82 (W15) |
| V6 Workflow list | 5.7 | Yes |
| V7 Workflow page | 5.8 | Yes |
| V8 Source map graph | 5.9 | Yes; canonical names are ours, not the mockup's |
| V9 Near-real flows | 5.10 | Yes, in-page |
| V10 Keep every agent feature | 5.11 | Yes |
| V11 New Home | 5.13 | Yes; role-aware, with Briefing and Needs you kept (W19, W20) |
| V12 Component kit | 5.12 | Yes; yellow stays the action colour (W16) |

## 14. Build report (27 Oct 2026)

### 14.1 How it is built

- **One block.** All new code sits between `/*FR-START*/ … /*FR-END*/` (after the agent block) and `/*FR-CSS-START*/ … /*FR-CSS-END*/` in `index.html`. It wraps existing functions (`shell`, `route`, `renderHome`, `renderIntegration`, `wfListHTML`, `wfNodeHTML`, `wfPaint`, `wfValidate`, `bIngest`, `sdRender`, `sdTabBody` and others) instead of rewriting them, so every element ID and `data-act` name the tests and the video use is still there.
- **One early patch.** `const vlogo` became `let vlogo`, so logos can replace the two-letter badge.
- **A switch.** The revamp is on with the agent build. `?fabric=0` restores the previous look on this device (remembered as `circ-fabric`), the same way `?agent=0` restores the demo build. The demo build (`?agent=0`) is unchanged.
- **No new `rnd()` calls.** Every new number is counted from `SOURCES`, `S.wf`, `MAPPINGS`, the table models, `ROWS` (monthly history) and the 24-hour health history, or derived with `hashId`.

### 14.2 What was built, by phase

| # | Built |
|---|---|
| 1 | Warm charcoal dark theme (W21; first built navy), white menu in light mode, new tokens (`--side-*`, `--surface-raised`, `--char-*`, category hues `--h-*`). Lucide icons under the old keys plus the new ones. Component kit: `frIt`, `frKpi`, `frSpark`, `frDelta`, `frSt`, `frSeg`, `frTl`, `frQa`, `frAttn`, `frRing`, `frPanel`, `frHead` |
| 2 | Menu with Product and Integration headings, single-line items, menu search (opens the command bar, Ctrl+K), My Tasks and Alerts with counts, Connection Fabric with nine pages, company card (tenant, *DI Framework overview*) and user card (sign-out). Collapsed rail with hover labels (the flyout), focus labels and the Alerts dot. Phone drawer with a menu button. Breadcrumbs on Connection Fabric |
| 3 | Top bar: one search that finds and asks, tenant, *Live* dropdown with *Pause live updates*, region, the bell (alerts and agent runs), a compact ✦ Ask, theme, account. Home: date and greeting, the Briefing as a line, hero and tagline (not on phones or in Technical mode), the Ask box with five modes, five KPI tiles per role, Agent activity timeline (Live, Today, This week), the role's middle panel, six key figures with a period picker, right column (Needs you, Activity, Watchlist, Notifications), attention card, Quick actions with a gear, Pinned, Classic modules with Grid, List and Customize |
| 3b | My Tasks, Alerts, Reports (six), Data Checks, Settings |
| 4 | 34 logos as inline SVG; `CATALOG` with 15 Available systems; Overview with tiles, search (plain language: *connect our HR system*), category pills, featured banner, four recommendations with ✦ *Why recommended*, All integrations with a category list and a sortable table; the drawer's Overview, Configuration, Data Mapping, Sync & History and Security tabs and the Sync now · Pause · Edit · Disconnect footer |
| 5 | Workflow list: tiles, four filters and a sort, Open + ⋯, failing rows with the reason and *Investigate*, bulk bar, 20 per page, right column |
| 6 | A workflow's page at `#/integration/studio/WF-101`: header, tabs (Workflow studio, Settings, History, Documentation), grouped palette, white node cards with records and status, error-handler, audit and event-stream branches that validation understands, undo and redo, auto layout, minimap, Overview · Details · Data flow, recent runs, data quality, details, tags, related systems, quick actions |
| 7 | Source Map: tiles, filters, Graph (systems → canonical models → models and decisions, with field-link counts and highlighting), List (the previous source cards), Matrix, the system tree, the detail panel with *Test connection* |
| 8 | Monitor; tiles on Source Tables, Canonical Models, Event Streams and Conflict Queue |
| 9 | Connect (auth, consent, scopes, test, suggested mappings, first sync, Connected with a draft ingest workflow), investigate a failure, sync, pause and resume (*Paused upstream*), disconnect with a typed confirmation and reconnect, run, view failed records with reprocess and CSV, export JSON, save as template, credential expiry (ShipLane TMS, five days) with *Re-authenticate* |
| 10 | README, CHANGES Update 17, screenshots `docs/screenshots/fabric-*.webp` |

### 14.3 Numbers you will see

21 sources (20 connected, 1 not provisioned) and 15 Available systems: 36 integrations. 35 workflows across 21 source systems. 58 tables modelled, 65 field mappings. Needs attention: 4 (the stale market feed, the failing Fixably ingest, AWS IoT Core not connected, ShipLane TMS's credential expiring). Overview, Source Map and Monitor count from the same helpers. Live runs keep firing, so failing and success counts move during a session, as before.

### 14.4 Contrast (WCAG AA, text on background)

| Theme | Pair | Ratio |
|---|---|---|
| Light | `--ink` #141414 on `--bg` #FAF8F5 | 17.4 |
| Light | `--muted` #7B726D on `--panel` #FFFFFF | 4.7 |
| Light | `--side-ink` #1A1917 on `--side-bg` #FFFFFF | 17.6 |
| Light | `--side-ink` on `--side-act` #FFF6CC (active row) | 14.1 |
| Light | `--side-mut` #6B665E on `--side-bg` #FFFFFF | 5.7 |
| Dark | `--ink` #F3F2EE on `--bg` #0E0E0D | 17.2 |
| Dark | `--ink2` #CBC8C1 on `--panel` #181816 | 10.6 |
| Dark | `--muted` #A19D95 on `--panel2` #1F1F1D | 6.1 |
| Dark | `--muted` #A19D95 on `--panel3` #292926 | 5.4 |
| Dark | `--side-mut` #A19D95 on `--side-bg` #0A0A09 | 7.3 |
| Dark | `--warn` #E5A543 / `--bad` #EC7A6E on `--panel` | 8.3 / 6.4 |
| Both | #141414 on `--yellow` #FFDD00 (primary button) | 13.7 |

`fabric.js` measures the same pairs from the live tokens.

### 14.5 Tests

See CHANGES Update 17 for the counts. One existing expectation changed because W17 moved the control, and it was replaced, not removed: `live` checked the top-bar *Data checks* pill; it now checks that *Data Checks* is in the menu and the pill is gone.

### 14.6 Not done, or done differently

- **The demo video was not re-recorded.** Playwright is not installed on this machine and the narration timings are not in the repo. Every selector `record.py` uses before the case steps was checked in the headless harness instead; the Source Map panel opens on the first source that needs attention, so the video's *Diagnose* step finds its button in Graph view.
- **Phone at 390 px** is checked with screenshots, not in `fabric.js` (the headless window cannot be narrower than about 500 px).
- **Canonical tables in the graph** are our seven canonical models, not the mockup's names (W3).
- **Logos** are simplified marks drawn for this page, not the vendors' artwork.
- **Run history** older than the runs made in the session is derived from each workflow's run count and success rate (deterministic, no `rnd()`).

> **Legal review.** The catalogue shows real vendors' names and simplified versions of their logos, and the featured banner states *Role-based access and audit on every connection*. Kinective's Legal team should review the use of third-party marks and the wording of that claim before the page is shown to clients or prospects.
