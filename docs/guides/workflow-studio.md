# Workflow Studio: user reference

Workflow Studio is the **Integration → Connection Fabric → Workflow Studio** tab (`#/integration/studio`). It is where
you build the workflows that move data in from the source systems, decide on a case, and send approved instructions
out, and where you run, watch and repair them. This is the full reference; the short version is section 7 of the
[Connection Fabric guide](connection-fabric.md), and a step-by-step walk-through is the
[workflow tutorial](workflow-tutorial.md).

> **The vendors are simulated; the workflows are real.** All data is synthetic (Northfield Industrial Leasing), and
> every "system" a workflow reads or writes (SAP S/4HANA, Salesforce, IBM Maximo …) is a local mock in the
> `source-sim` service. What a workflow does with that data is real: a run reads records from the mock, runs every
> step over them, writes canonical data, holds the records a step rejects, retries, records its history and raises
> alerts. A test run does the same without writing anything.

## Contents

1. [What a workflow is](#1-what-a-workflow-is)
2. [Who can do what](#2-who-can-do-what)
3. [The list](#3-the-list)
4. [Creating a workflow](#4-creating-a-workflow)
5. [The canvas](#5-the-canvas)
6. [The block inspector](#6-the-block-inspector)
7. [Block reference](#7-block-reference)
8. [Checks](#8-checks)
9. [Drafts and saving](#9-drafts-and-saving)
10. [Test run](#10-test-run)
11. [Publish, unpublish, pause](#11-publish-unpublish-pause)
12. [Running](#12-running)
13. [History](#13-history)
14. [When a run fails](#14-when-a-run-fails)
15. [Monitor](#15-monitor)
16. [Messages you may see](#16-messages-you-may-see)
17. [Limits and good to know](#17-limits-and-good-to-know)
18. [See also](#18-see-also)

---

## 1. What a workflow is

A workflow is a graph of **blocks** (steps) joined by **links**. Records flow along the links from left to right; each
block gets the records of the blocks that feed it and passes on what it keeps.

| Type | What it does | Starts from |
|---|---|---|
| **Ingest** | Reads one source system and turns its records into canonical data | a source connector |
| **Outbound** | Sends an approved instruction to one target system | the Decision record |
| **Decision** | Evidence, six eligibility gates, routes and predictions, a person's approval, the instruction, the outcome | Case evidence |
| **Blank** | An empty canvas you wire yourself (an ingest-type pipeline) | nothing |

**Fixed and movable blocks.** Fixed blocks belong to Circularity: the canonical models (Asset & component, Condition &
eligibility, Demand opportunity, Outcome …), Evidence snapshot, Human approval, Decision, Case evidence and Six
eligibility gates. They carry a lock, cannot be moved, removed or re-wired to each other, and links marked as fixed
(for example Decision → Human approval) cannot be removed. Everything else is movable: yours to add, arrange, connect
and remove.

**A source's sync is its ingest workflow.** Every sync of a source (Sync now, its schedule, a webhook) runs a workflow
through the same engine:

- the **published ingest workflow bound to the source**: the newest ingest workflow *published in the app* whose first
  connector reads that source. It is bound when you publish it, and unbound when you unpublish, pause or delete it;
- otherwise the **default minimal graph** (connector → ingestion channel → Validation & enrichment → field mapping →
  canonical model, with the evidence snapshot), whose steps pass every record on unchanged, so the canonical data is
  exactly what the source's adapter maps. A source the demo does not know (catalogue or hand-made) uses connector →
  field mapping → Outcome.

The starting workflows the demo seeds as *Published* are **not** bound until someone publishes one in the app, so the
demo's sources keep syncing as their adapters map. A sync that runs a bound workflow is recorded in the source's
**Sync & History**, not in the workflow's run list; records a step held there make the sync *partial*.

**A bound workflow handles only the resources its connector reads.** When its connector ticks some **Resources** (the
tutorial's SAP workflow reads `purchase_order` only), the sync reads the source's other resources through the default
graph, narrowed to them, in the same sync run (whose counts are both parts'). Publishing a workflow that reads one
resource therefore never stops the rest of the source from syncing. A connector that ticks none reads every resource,
so nothing is left to the default graph.

## 2. Who can do what

| Role | Opens Workflow Studio | Creates, edits, saves, publishes, runs | Approves a held test run |
|---|---|---|---|
| Admin | yes | yes | yes |
| Developer | yes | yes | yes (simulated approval) |
| Every other role | no (the server answers `out_of_scope`) | no | — |

- The server enforces this on every action (permission *manageWorkflows*). A refused change says *"Only the Developer
  or Admin changes workflows."*
- **Approve and continue** in a test run is a **simulated approval**: a test run is a dry run, so whoever may run it
  (*manageWorkflows*: Developer and Admin) may continue it, and the run says *"Simulated approval (dry run): nothing is
  sent."* Real approvals of decisions stay with the roles that have the approval permission.

## 3. The list

`#/integration/studio`

**Tiles**: **Total workflows** (*Across N source systems*), **Published** (*Running and healthy*), **Failing**
(published and the last run failed; *Needs attention*), **Draft or paused** (*N not yet published · N paused*).

**Toolbar**

- Search (*Search workflows, owners or systems…*): name, id, owner and the system's vendor.
- **All types** (Ingest, Outbound, Decision), **All systems**, **All statuses** (Published, Failing, Paused, Draft).
- Sort: *Last run (recent)*, *Name (A–Z)*, *24 h success (lowest)*, *Status (failing first)*.
- Filters and sort stay while you are signed in. 20 workflows per page.
- **Build with AI**, **Import** and **+ New workflow** (Admin and Developer).

**Table**: Workflow (name, then `id · version`, and *unsaved changes* when you have a draft), Type, Source system,
Trigger, Status, Last run (state, how long ago, and for a failing one the reason), 24 h success, Owner, Actions.

- Status shows *Running* while a run is going, and *Paused upstream* when the workflow's source is paused in the
  Connection Fabric.
- Actions: **Investigate** (failing; opens the last run) or **Open**, and the ⋯ menu: Edit, Run now, Publish (a draft)
  or Pause / Resume, Duplicate, Export JSON, Delete.

**Bulk bar** (tick rows): **Run** (drafts are skipped), **Pause** (published ones), **Export** (one JSON per workflow),
**Clear**.

**Import**: choose a `.json` file that Export JSON wrote. It becomes a new **draft**, checked on the server: every
step's block and source must exist (sources as they are now), links must name steps it has, settings must be objects.
On success: *"{name} imported as a draft ({id})."*, and the workflow opens. A file that is not JSON: *"{file} is not a
JSON file. Choose a file that Export JSON wrote."* The other refusals are in [section 16](#16-messages-you-may-see).

**Right column**

- *N items need attention*: failing workflows, expired source credentials and workflows with a high failure rate (10 or
  more runs, under 90 % successful), each with **Investigate** and **Diagnose** (asks Ask Circularity *"Which
  workflows are failing and why?"*).
- **Workflow health**: the share of published workflows.
- **Recent activity**: the six newest runs of any workflow (*Runs appear here as workflows fire on their triggers.*).

## 4. Creating a workflow

### 4.1 + New workflow

**+ New workflow** (also Home's *New workflow* quick action) opens a dialog:

| Field | Values |
|---|---|
| **Workflow type** | Ingest pipeline · Outbound instruction · Decision workflow · Blank pipeline |
| **Source system** (ingest) / **Target system** (outbound) | systems Circularity reads / writes to: the demo's, and any source connected from the catalogue or made by hand (an outbound one needs write operations) |
| **Delivery method** (outbound) | the ones the target accepts: Outbound API call, Event trigger, Interface file, Process orchestration |
| **Name** | optional, max 80; empty gives *Ingest · {vendor}*, *Outbound · {vendor}*, *Decision workflow* or *New pipeline* |

**Create workflow** makes a draft (version 0.1) that holds **only the blocks it needs to run**:

| Type | Starts with | Trigger |
|---|---|---|
| Ingest | connector → one ingestion channel (API gateway, or Event ingestion for an event-only source; Poll for trigger file → Download and unzip → Chunk large files for a file-only source) → Validation & enrichment → field mapping → canonical model → Evidence snapshot (not for an Outcome or file-only source) | every *n* min at the source's poll interval, else On event |
| Outbound | Decision → Human approval → Instruction envelope → delivery method (→ Create manifest for a file) → write connector → Outcome | On approval |
| Decision | Case evidence → Six eligibility gates → list_eligible_routes → predict_outcomes → request_approval → Human approval → Decision → send_instruction → Outcome → reconcile_outcome | On case request |
| Blank | nothing | Manual only |

*"{name} created as a draft with only the blocks it needs to run. Add more from the palette, then Save and Publish."*
Optional blocks (a transform, the error handler, audit log, event stream, a second channel) are never added for you.
**Reset to template** (More actions) brings back this starting graph.

A source connected from the catalogue or made by hand gets the same starting graph: its schedule is its poll interval
(none: On event), and its field mapping feeds its system type's canonical model, else Outcome. An outbound workflow
to such a source needs write operations on it; otherwise *"{name} takes no instructions. Grant it write access
first."*

**Your templates** (in the same dialog, once you have saved one): pick one to create a draft *"{workflow name} (from
template)"* with its graph, system, owner and trigger: *"Created from the template as a draft."*

### 4.2 Build with AI

**Build with AI** opens *Build a workflow with AI*. Describe the workflow (max 2000 characters; Ctrl+Enter plans it),
or pick one of the examples, then **Plan it**.

- The **Understood** row shows what it took from your words (from your description, or your answer). **Change**
  reopens an answer.
- It asks only what is still missing, in rounds: the type (*What kind of workflow is it?*); the system (*Which system
  should it read from?* / *send to?*) and, for outbound, the delivery method or, for a decision, *Which decision flow?*
  (Standard six-gate decision, Pool allocation, Evidence gaps first); then every open detail at once, each with a
  default: *When should it run?*, *How should records arrive from {source}?* (only for a source that sends both ways),
  *Which blocks should it add?*, *Error handling and logging*, *Retries when a step fails*, *Alert when*, Name and
  Owner.
- **Use defaults for the rest** accepts the defaults; **Continue** answers; **Back** goes one round back; *Edit the
  description and start again* restarts.
- A system that is not connected, or that Circularity cannot write to, is said so in a note, with the closest real
  systems listed first.
- **Settings it fills from your words**: *"to EUR"*, *"into INR"* or *"in EUR"* sets Convert currency's **Target
  currency** (USD, EUR or INR only); *"dedupe by opportunity_id"*, *"de-duplicate on a, b"* or *"order by x"* sets Order
  late events' **Key fields**. They show in the plan's *Settings* row and in Understood.
- The plan lists *Required to run* and *You asked for*, a small graph (asked-for blocks dashed), every step in run
  order with why it is there, and the checks (*Checks: 0 errors*). If a choice would break a rule it says *"The plan
  would not pass its checks…"* instead.
- Nothing exists until you press **Create workflow**: the draft is created and saved as you, then opens: *"{name}
  created as a draft from your description. Check it, then Publish."* It is never published for you.

Without a Groq key the description is read by rules over the real system names and step keywords; with a key a model
only settles wording the rules found but could not resolve. In Ask Circularity, **Refine in Workflow Studio** opens the
builder with your request.

### 4.3 Duplicate and Import

- **Duplicate** (⋯ menu, More actions or Quick actions): a draft *"{name} (copy)"* at version 0.1 with no runs and no
  published version: *"Copy created as a draft: {name}."*
- **Import**: see [section 3](#3-the-list).

## 5. The canvas

Open a workflow from the list. The page has a header, four tabs (**Workflow studio · Settings · History ·
Documentation**), and on the studio tab: the palette, the canvas, the inspector, a right column (Workflow details,
Tags, Related systems with *Open connection →*, Quick actions), then **Recent runs**, **Data quality (latest run)**,
**Checks** and **Task instances**.

**Header**: back arrow and breadcrumb, the name (editable, max 80), status, `id · version`, the chip *Runs v{pub} ·
v{x} not published* when a published workflow has a newer saved version, *Last run …*, *Unsaved changes*, then **More
actions** (Save, Discard changes, Reset to template, **Publish v{x}** when there is such a newer version, Publish /
Unpublish, Duplicate, Save as template, Export JSON, Delete), **Validate**, **Test run** and **Run now**.

### 5.1 Palette

Search with *Search components*. For an ingest, outbound or blank workflow:

| Heading | Group | Blocks |
|---|---|---|
| Sources | one group per category (CRM open) | every source; the dot is its status (green live, amber stale, red not connected) |
| Transform | **Transform steps** (open) | the workflow's own field mapping (*{system} fields*), Data enrichment, Filter and condition, Aggregation, Expression, Code-table lookup, Join, Validation & enrichment, Timestamps to UTC, Convert currency, Normalise units, Resolve identity, Order late events, Instruction envelope, Flag failed bench tests |
| Orchestration | **Orchestration steps** (open) | Scheduler, Event trigger, Branch, Loop, Call workflow, Wait |
| | **Branches** | Error handler, Write to audit log, Publish to event stream |
| More | **Integration layer** | API gateway, Event ingestion, File ingestion, Validation & enrichment |
| | **File exchange steps** | Poll for trigger file, Download and unzip, Chunk large files, Create manifest, Fetch import log, Notify with log links |
| | **Delivery methods** | Outbound API call, Event trigger, File generation, Process orchestration |
| | **Write to a system** | every system Circularity writes to |
| | **All field mappings** | every source's field mapping |

A decision workflow shows **Agent tools · read** and **Agent tools · write** instead (a write tool is marked *Needs
approval* or *Within agent scope*).

### 5.2 Working on the canvas

- **Add**: drag a block onto the canvas, or click it / press Enter or Space to place it at a free spot: *"{block}
  added. Drag from its right dot to connect it."*
- **Connect**: drag from a block's right dot onto another block, or use **Connections** in the inspector. Refused
  links say why (see [section 16](#16-messages-you-may-see)): no output, no input, a loop, already connected, two fixed
  steps.
- **Remove a link**: click the line (the line nearest your click is picked) and press **Remove connection**, or
  **Remove** next to it in the inspector.
- **Move**: drag (snaps to 8 px), or select and use the arrow keys (8 px; Shift: 40 px). Fixed blocks do not move:
  *"Fixed steps belong to Circularity and cannot be moved or removed."*
- **Remove a block**: Delete or Backspace, or **Remove from workflow** in the inspector.
- **Toolbar**: zoom out / in (50–140 %, 10 % a step), fit to width, **Undo** / **Redo** (40 steps), **Auto layout**
  (*"Steps laid out left to right in run order."*), minimap on/off, the views **Overview · Details · Data flow** (Data
  flow adds each link's records-out count), **Expand canvas** / **Show panels**.
- Each block card shows its state in the current or last run and its records out. The legend: *Fixed · owned by
  Circularity*, *Movable · yours to arrange*, *Red · failed*.
- On a phone the canvas is read-only.

Any change clears the run painted on the canvas.

## 6. The block inspector

Select a block to open the inspector on the right.

**Top (no heading)**: *Fixed* or *Movable* and the block's kind, its name and description, then what the block is
about: for a connector its status, mode, access, what it reads or writes and how data arrives or is accepted; for an
ingestion channel the sources that fit; for a delivery method the systems that accept it; for a field mapping its
first five rows and the number of fields mapped; for a fixed step its fields; for an agent tool its type, approval and
the agents that use it.

**Settings**: one control per setting of the block (see [section 7](#7-block-reference)).

- A required setting has a `*`; the help text sits under the control; a problem the browser can see (a value outside
  its choices, an empty rule) shows in red under it, in place. Problems only the server can see (a field the records
  do not carry, a Target operation the system does not take) show under **Problems** below.
- Text, number and list fields take effect when you leave the field or press Enter (one undo step per edit); selects
  and ticks at once. A select that is not required has a *None* option.
- **Field lists** take names separated by commas (*field_a, field_b*).
- **Rules** (Validation, Filter, Branch): each row is a field, a check (*present, type, regex, range, in*) and a
  value, with **Remove**; **+ Add rule** adds one.
- **Pairs** (Normalise units, Code-table lookup): a field and a value from the list, with **Remove**; **+ Add** adds
  one.
- Fixed blocks and agent tools: *"This step has no settings: Circularity runs it the same way in every workflow."* A
  block without settings: *"This block has no settings."*
- Only settings that differ from the default are stored. Every change marks the draft unsaved.

**Problems**: the checks that belong to this block (errors in red), the server's included (see
[section 8](#8-checks)).

**Connections**

- **Receives from** and **Sends to** list the block's links, each with **Remove**, or *Locked* for a fixed link. With
  none: *"Nothing: this block starts the flow."*, *"Nothing yet. Connect a step into this one."* or *"Nothing yet.
  Choose the next step below."*
- **Next step** (*Choose a step*) adds the first outgoing link; once the block sends somewhere, **+ Add another
  connection** opens the same list as *Also send to*. Only steps that can be linked are offered.

**Testing** (movable blocks): **Fail this step in the next run** makes the step raise when it runs, to rehearse the
failure path; **Stop failing this step** turns it off. A test run uses it at once; a real run uses it once the change
is saved (and published, for a published workflow). A failing step is retried like any other.

**Remove from workflow** (movable blocks). A fixed block shows *"Fixed step. It cannot be moved or removed, and its
rules apply to everything wired through it."*

Select a **link** instead and the inspector shows *Connection* (from → to) with **Remove connection**, or, for a fixed
link, *"This connection belongs to the fixed structure of the workflow and cannot be removed."*

## 7. Block reference

What each block does when a run reaches it, and its settings (label, meaning, default, allowed values). A field path
can be dotted (`line.tax`); after the field mapping, `model.field` also reads a mapped value. Unless a section says
otherwise, records a step **rejects** are held for reprocessing (see [Error handler](#73-branches)).

**Field-aware checks.** Settings that name fields (field lists, rule fields, pair fields) are also checked against the
fields the source's records really carry: the keys of its newest 300 landed records and the names its field mapping
uses. So are the text settings that name one field (Convert currency's Currency field and Date field, the Time field
of Order late events and Event ingestion), and only a setting someone set is checked (a default such as Convert
currency's `amount` is not). The server runs it on every check of the draft (the page asks about 0.6 s after an edit,
and again on Validate, Test run and Publish), on Publish and on Run now of a draft, and only once the source has
synced or has a mapping; before that it is skipped. Its errors show in the Checks panel, the inspector's Problems and
on the canvas.

### 7.1 Sources and targets

**Source connector** (palette *Sources*). Reads the source through its adapter, on the URL and stored credential set in
the Connection Fabric, from the sync cursor, and keeps every record read as a landed record. A source that is paused,
disconnected, not connected or deleted fails the step at once (no retries). A run and a sync of the same source never
overlap: a run that finds the source syncing fails the step with *"{source} is syncing now"* (retried), and a sync
that finds a run reading it is skipped.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Resources | which of the connection's resources to read | none ticked: every resource | the adapter's resources (a catalogue or hand-made source lists none: *"This connection lists no resources; every record it sends is read."*) |
| Mode | delta reads what changed since the last sync; full reads everything | delta | delta, full |
| Lookback (days) | re-read this many days before the cursor | 0 | 0–365 |

**Field mapping** (*{system} fields*, in Transform steps and All field mappings). Turns each record into canonical facts
with the source's adapter and the mapping saved in the Connection Fabric (Data Mapping), exactly as a sync does. A
record that cannot be mapped is rejected (rule `map`).

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Mapping version | *latest, or a saved version number* | latest | latest, or a whole number ≥ 1 |

*latest* applies the source's current saved mapping, as a sync does. A number applies that saved version of the
source's mapping (Data Mapping keeps every version) over the adapter's own mapping, or alone for a catalogue or
hand-made source. A version the source does not have fails the step without retries (*"{step}: no field mapping
version N for {source}"*).

**Canonical model** (fixed: Asset & component, Condition & eligibility, Demand opportunity, Outcome …). Writes each
record's facts to the canonical store; a fact that does not fit its model is held (rule `schema`) and the record's
other facts are stored. Records without facts pass through. Evidence snapshot, Human approval, Decision and the other
fixed steps pass their records on in a run. No settings.

**Write to a system** (write connector). In a workflow run it passes the instruction on; the instruction itself is sent
by Circularity's instruction queue after a person approves the decision.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Target operation | *Empty: each step's own write. Oracle Depot Repair: repair or teardown.* | empty | one of the writes the target takes |

A value the target does not take is an error: *"Target operation {x} is not a write of this system ({writes})."*

**Delivery methods** (Outbound API call, Event trigger, File generation, Process orchestration). They pass the
instruction on in a run.

| Setting | Default | Allowed |
|---|---|---|
| Timeout (s) | 30 | 1–600 |
| Retries | 3 | 0–5 |

**Where the outbound settings apply.** Once an outbound workflow writing to a target is **published in the app**
(the newest such one counts), the instructions sent to that target use its settings: the delivery method's
**Timeout** is the HTTP timeout of each write, its **Retries** how many times a write that failed on a transient error
(system down, timeout, refused credentials) is tried again before the instruction fails (never more than the job
queue's own limit), and the write connector's **Target operation** picks the repair order type for Oracle Depot
Repair (*repair* or *teardown*). Only settings changed from their defaults count. Without such a workflow (the demo's
seeded outbound workflows are not published in the app) instructions go out exactly as before. A workflow run's own
retries come from the Settings tab.

### 7.2 Transforms

**Validation & enrichment**. Checks each record: first the required fields, then the rules in order. A record is
rejected at its first failure, with the rule's name and a reason (*"qty is missing"*, *"qty -2 is outside the range
>0"*). Checks other than *present* pass when the field is missing.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Required fields | fields every record must have (a *present* check each) | none | field names |
| Rules | rows of field, check, value | none | see below |
| On failure | *Hold keeps failed records for reprocessing; reject drops them.* | hold | hold, reject |

Rule checks: **present** (not empty); **type** with `string`, `number`, `integer`, `bool` or `date`; **regex** with a
pattern the whole value must match (max 200 characters); **range** with `min..max` (either side may be left out) or one
comparison `>0`, `>=0`, `<5`, `<=5`, `=3`, `!=3`; **in** with the accepted values separated by commas. With an Error
handler wired after it, the handler's *Failed records* setting decides instead of *On failure*.

**Order late events**. Keeps the newest record per key and drops the others (counted, not held). Newest by the *Newest
wins by* field, else the change time the record carries; a tie goes to the later arrival. A record missing one of the
key fields is never merged with another: it goes on untouched.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Key fields | *Records with the same key are de-duplicated; a record missing one goes on untouched.* | none: the record id | field names |
| Newest wins by | *Empty: the source's change time.* | empty | a field name |
| Late window (min) | how late a record may be before it is rejected (rule `late_window`) | 1440 | 0–43200 |
| Time field | *Set: a record whose time is more than the late window before the newest record's in the run is rejected. Empty: only records that carry their arrival time are checked.* | empty | a field name |

Records read by a connector carry no arrival time, so for synced records the late window works through the **Time
field**: it is measured from the newest time in the same run, not from the clock, so replaying old data does not
reject all of it.

**Convert currency**. Converts each **Amount field** from the currency the record is in to the target currency at a
**dated rate** from the rate table: the newest rate dated on or before the record's **Date field** (or the run's
date), going through USD and rounding to cents. The currency a record is in is its **Currency field**, else the
**Source currency**, else USD. The rate used is kept with the record, and the Currency field (when there is one)
becomes the target. A currency without a rate is rejected (*"no rate for GBP on 2026-10-06"*); a target without a rate
fails the step.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Target currency | the currency to convert to | USD | USD, EUR, INR |
| Rate date | *The rate of the record's date, or of the run's.* | record | record, run |
| Rate table | where the rates come from | fx_rate | fx_rate |
| Amount fields | *The fields converted.* | amount | field names |
| Currency field | *The field that says what the amounts are in; it becomes the target. Empty: none.* | currency | a field name, or empty |
| Source currency | *For a record with no currency field value. Empty: USD.* | empty | USD, EUR, INR |
| Date field | *The rate of this date. Empty: the run's date.* | date | a field name, or empty |

**Timestamps to UTC**. Rewrites date-time values as UTC (`…Z`), keeping the source value. A value with an offset keeps
its instant; a local value is read in the source zone. A value that is not a timestamp is rejected (rule `utc`).

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Fields | *Empty: every timestamp field.* | none | field names |
| Source zone | *record: the offset the record carries* (a local value is then taken as UTC) | record | record, UTC, Europe/London, Europe/Berlin, America/New_York, America/Chicago, America/Los_Angeles, Asia/Kolkata, Asia/Singapore, Asia/Tokyo, Australia/Sydney |

**Normalise units**. Converts each listed field to its target unit, keeping the source value. The unit a value is in
comes from the value itself (`7500 W`), else a `<field>_unit` field. A value with no unit, or one that does not convert
(power to mass), is rejected (rule `units`).

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Field units | *Field → the unit to convert to.* | none | W, kW, MW, kWh, EA, kg, t, lb, km, mi, h, days, months, years |

**Code-table lookup**. Maps codes through a code table, keeping the source value; an unknown code is rejected (rule
`lookup`).

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Code tables | *Field → code table.* | none | grade, status, location, condition, reason |

The tables: **grade** and **condition** (`Grade B`, `B+` → `B`; letters A–E); **status** (BOOKED → active, EXPIRED →
expired, EVERGREEN → evergreen, TERMINATED → terminated, CONFIRMED → confirmed, FORECAST → forecast, CLOSED WON →
confirmed, CLOSED LOST → lost); **location** (plant 2010 → Warehouse 1, 2020 → Warehouse 2, 2030 → Repair centre, 10*n*0
→ Site *n*); **reason** (DEF defect, EOL end of lease, EXC excess, UPG upgrade, RET return).

**Filter and condition**. Keeps the records that pass every rule; the rest are counted as filtered, not held.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Condition | *Rows that pass every rule are kept.* | none: keep all | rules, as for Validation |

**Expression**. Sets the target field to the expression's value for every record (the old value is kept).

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Target field | the field to write | empty | a field name |
| Expression | the formula | empty | see the grammar |

Both empty: the step passes records on. One without the other is an error (*"Expression is needed with Target
field."*). **The grammar** (the only one any block uses): field names, numbers, `'text'` or `"text"`, `true`, `false`,
`null`, `+ - * /`, `== != < <= > >=`, `and`, `or`, `not` and parentheses; at most 500 characters. Anything else is
refused; nothing is evaluated as code. Division by zero gives null.

**Aggregation**. One record per group: the group-by fields, each total (summed under its own name) and `count`. Neither
set: pass-through.

| Setting | Default | Allowed |
|---|---|---|
| Group by | none | field names |
| Totals | none | field names |

**Join**. Joins the main input with the records of a second input step on a key, inside one tenant (the records'
`tenant` field). A matched record gets the other record's data under a field named after the second input; unmatched
records do not go on.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Second input | *The step id of the other input.* (wire that step into the Join too) | empty: pass-through | a step id |
| Join key | the field both inputs share | empty | a field name (needed with Second input) |

**Data enrichment**. Adds the canonical record of the chosen model whose key is the record's key field, under a field
named after the model; a record with no match goes on unchanged. Model or key empty: pass-through.

| Setting | Default | Allowed |
|---|---|---|
| Lookup model | None | Asset & component, Condition & eligibility, Demand opportunity, Outcome |
| Key | empty | a field name |

**Resolve identity**. Records that share any identity key value, inside one tenant (`tenant` field), become one
identity; each record gets an `identity` field.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Identity keys | *Matched within the tenant only.* | none | field names |

**Instruction envelope** (no settings) and **Flag failed bench tests** (Notify: *Empty: the workshop lead.*) pass their
records on in a run.

### 7.3 Branches

**Error handler**. Receives the records its predecessors rejected (and a Branch's *else* records), with the rule each
broke. Nothing goes on from it. It must follow Validation & enrichment.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Failed records | hold them for reprocessing, or count and drop them | hold | hold, drop |

Without an error handler, the engine holds a step's rejected records itself (unless Validation's *On failure* is
*reject*), so a rejected record is never lost silently.

**Write to audit log**. Passes records on and adds one entry per run to the audit log (the Audit page's event log,
type `workflow.audit`): *"{workflow} · run {run} · step {step}: N records ({level})"*. Not in a test run.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Level | *One entry per run in the audit log, with this level and the record count.* | info | info, warn, debug |

**Publish to event stream**. Puts a `model.updated` event on the live stream naming the topic, the workflow, the run and
up to 50 record keys. Not in a test run, and not when no records reached it. It must follow a canonical model.

| Setting | Default | Allowed |
|---|---|---|
| Topic | model.updated (required) | text |

### 7.4 Orchestration

**Branch**. Records that pass the condition go down the *then* path (the first step you linked it to); the rest go down
the *else* path (the second) and to an Error handler linked after it. An empty condition sends everything down *then*.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Condition | *Rows that pass go on; the rest take the else path.* | none | rules, as for Validation |

**Loop**. One record per item of the list at the items path (`<id>#0`, `<id>#1` …); a record without such a list goes on
as it is.

| Setting | Default | Allowed |
|---|---|---|
| Items path | empty: each record as it is | a field path |

**Wait**. Holds records back and comes back for them later. The records it holds back are parked on the server and a
resume job is queued; when it is due, the workflow runs again from the Wait step only (the run is listed with
*Resume* under Triggered by; the steps before the Wait step show *Skipped*), and the steps after it get the records
that may go on.

- Duration and Until empty: every record goes on at once (the default).
- **Duration** only: every record waits that many minutes, then all go on.
- **Until**: records that meet the expression go on now; the others wait and are checked again every Duration
  minutes (0: every 15 minutes), each time on their newest landed version. A record still waiting 7 days after it
  first waited is held (rule `wait`, *"Until (…) was not met within 7 days"*).
- While records wait, the step shows *waiting* (when none went on) and the run's note says *"N records waiting at
  {step}"*. A test run parks nothing.
- When the resume job finds the workflow running or paused it tries again a minute later; a deleted workflow takes
  its waiting records with it; if the Wait step was removed from the workflow, its records are held (rule `wait`) for
  Reprocess.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Duration (min) | *Records wait this long, then the run goes on. With Until: how often it is checked again (0: every 15 min).* | 0 | 0–10080 |
| Until | *An expression: records that meet it go on; the others wait (at most 7 days).* | empty | an expression |

**Call workflow**. Starts the named workflow (a run listed with *Workflow* under Triggered by), passing it no records,
and passes its own records on. The other workflow starts only when it is published, not already running or queued,
and workflow triggers are on; otherwise it is not started, and the step still succeeds. Calling its own workflow, a
workflow that does not exist, or one that calls this one back fails the step: *"Call workflow cannot call its own
workflow ({id})"*, *"Call workflow: there is no workflow {id}"*, *"Call workflow: {id} calls {id} back, so the calls
would go round in a circle"*. A test run starts nothing.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Workflow | *Starts this published workflow (not itself, nor one that calls back).* | empty | a workflow id |

**Scheduler** (Interval (min), 60, 1–10080) and **Event trigger** (Event type, *Empty: any event from the source.*)
start a workflow, so nothing should feed them. In a run they pass records on. A graph with one of them **sets the
workflow's trigger** (the first such block): the Scheduler *every Interval minutes*, the Event trigger *On event* of
that event type (a pattern such as `offer.*` matches every `offer.` event). Saving keeps the trigger in step with the
block, and the Settings tab shows the trigger greyed out with *"Set by the Scheduler block."* or *"Set by the Event
trigger block (event type {type})."* (see [section 12](#12-running)).

### 7.5 Ingestion and file steps

**API gateway**. Passes records on, each tagged with the limits it came in under.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Rate limit (per min) | *0: no limit.* | 0 | 0–100000 |
| Timeout (s) | | 30 | 1–600 |

**Event ingestion**. Drops exact replays (same id, same payload) and orders events by the ordering key (events without
it keep their place after the others). The replay window rejects (rule `replay_window`) an event that carries its
arrival time more than the window after its own time and, with a **Time field**, an event whose time is more than the
window before the newest event's time in the run (records read by a connector carry no arrival time, so this is how
the window applies to them).

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Ordering key | *Events with the same key are kept in order.* | empty | a field name |
| Replay window (min) | | 60 | 0–10080 |
| Time field | *Set: an event whose time is more than the replay window before the newest event's in the run is rejected. Empty: only events that carry their arrival time are checked.* | empty | a field name |

**File ingestion**. Records each record's checksum (sha256 of its payload). With *Checksum required*, a record from a
file whose checksum is missing or does not match is rejected (rule `checksum`); records read from an API pass.

| Setting | Meaning | Default | Allowed |
|---|---|---|---|
| Path | *Folder or object prefix; empty: the source's own.* | empty | text |
| Checksum required | | yes | yes, no |

**File exchange steps**: pass their records on in a run; their settings are checked but not used yet.

| Block | Setting | Default | Allowed |
|---|---|---|---|
| Poll for trigger file | File pattern (*Empty: any file.*); Poll every (min) | empty; 5 | text; 1–1440 |
| Download and unzip | Format | auto | auto, zip, gzip, none |
| Chunk large files | Rows per chunk | 10000 | 1–1000000 |
| Create manifest | Include checksums | yes | yes, no |
| Fetch import log | Wait for the log (min) | 30 | 1–1440 |
| Notify with log links | Notify (*Empty: the workflow's owner.*) | empty | text |

**Agent tools** (decision workflows) have no settings.

## 8. Checks

The **Checks** panel lists every problem with the step it belongs to (click one to select the step): **errors**
(red), **warnings** (amber) and notes; the header counts errors and warnings (*No errors* when there are none), and an
empty list says *Ready to run. Every step follows the fixed rules.* **Validate** runs them on demand and says *"N
errors to fix before this can run."*, *"No errors. N warnings to review."* or *"No errors or warnings. This workflow
is ready to run."*

- **The panel shows the server's checks too.** The browser checks the draft at once; about 0.6 s after your last edit
  (and again when you press Validate, Test run or Publish) the page asks the server to check the same draft, with the
  sources as they are now and the field-aware checks, and merges the answer in (the server's wins on a duplicate).
  So every error that would refuse Test run or Publish is listed, with its step, before you press them.
- **Errors** block Publish, Test run, and Run now of a draft. **Warnings** and notes do not. The refusals of Test run
  and Publish end with the first error: *"… First: {message}"*.
- **Bad settings save but block Publish**: Save keeps any setting; each bad one is an error naming the block and the
  field (*"Convert currency: Target currency GBP is not one of USD, EUR, INR."*).
- The checks read the sources **as they are now**: a deleted source is an error, a disconnected one has no connected
  feed, a failing or expired one is stale, and a **paused** source adds a warning (*"{source} is paused. Runs read
  nothing from it until it is resumed."*); the list then shows *Paused upstream*.

The main rules:

| Rule | Severity |
|---|---|
| A connector, write connector or mapping whose source was deleted | error |
| A source with no connected feed; a write connector with no connected system | error |
| A source reaches a canonical model without a field mapping | error |
| A mapping fed by another source's connector, or with no connector upstream, or no mapping defined, or wired to the wrong model | error |
| An ingestion channel the source does not arrive by; a file step without a file source | error |
| A delivery method or write connector that bypasses Human approval or lacks an Instruction envelope | error |
| A target that does not accept the delivery method | error |
| Create manifest not after File generation; Fetch import log not after a write connector; Notify not after Fetch import log | error |
| Error handler not after Validation & enrichment; Publish to event stream not after a canonical model | error |
| An agent tool in the wrong order (for example send_instruction before Human approval) | error |
| A bad block setting | error |
| A stale source (token expired) | warning |
| A source that does not reach a canonical model, or reaches it without an ingestion channel or validation | warning |
| A block not wired between a source and a target; a start block that something feeds | warning |
| A paused source | warning |
| A manual-import source | note |

## 9. Drafts and saving

- Every edit goes into **your draft** of the workflow (*Unsaved changes*; the list shows *unsaved changes*). After two
  seconds without another change the draft is **autosaved on the server**, so it survives a reload and a sign-out and
  comes back, still unsaved, the next time you open the workflow. Each person has their own draft; drafts are not in
  the audit journal.
- **Save** (More actions) makes a **new version** (0.1 → 0.2 …) with the graph, name, owner, trigger and run
  settings: *"{name} saved as v{x}."* It needs a name: *"Enter a workflow name before saving."* Saving a published
  workflow does not change what runs until you publish the new version (see [section 11](#11-publish-unpublish-pause)).
- **Discard changes** goes back to the last saved version: *"Changes discarded. Back to v{x}."*
- **Reset to template** puts the starting graph back in the draft: *"Workflow reset to its template. Save to keep it."*
- Leaving with unsaved changes warns once: *"You have unsaved changes. Save or Discard them, or choose All workflows
  again to leave them unsaved."*
- Save, Publish, Discard and Restore drop the draft on the server.
- **Settings tab**: Trigger (On a schedule, On event, On approval, On file arrival, On case request, Manual only), Every
  (min) for a schedule (1–1440; 15 when you switch to it), Owner (role or team, max 60), **Retries** (0, 1, 3 or 5;
  default 3) and **Alert when** (A run fails, Two runs fail in a row, Success rate drops below 95%, Never; default A
  run fails). A change says *"Saved with the workflow."*: it is kept in the draft and saved with the next Save;
  *"Changes are saved with the workflow; publish to apply them to the running version."* With a Scheduler or Event
  trigger block on the canvas the Trigger (and Every) fields are greyed out and say which block sets them.
- **Save as template**: *"Saved as a template. It appears under New workflow."* (one template per workflow).
- **Export JSON** downloads the saved version (with each block's changed settings), the file Import reads.
- **Delete** asks first (*Delete workflow*); a published one warns that anything depending on its trigger stops. Its
  versions and everyone's drafts go with it.

## 10. Test run

**Test run** runs **your draft** on the server as a **dry run**: each connector reads up to **25 real records** from the
source (a full read, not from the cursor), and every step runs over them for real, but **nothing is written**: no
landed records, cursors, canonical data, held records, events, audit entries, parked Wait records or called
workflows. It refuses while there are errors: *"Fix N errors before running. The checks below say what and why.
First: {message}"*.

- The canvas and **Task instances** fill in: each step's state, start, end, duration, Try, **Records (in / out)** with
  *· N rejected*, and **Samples**, which opens the step's first three records **Before** and **After**. The chips on
  top filter by state; *Search steps* filters by name; **Clear run** clears it.
- At the end: *"Test run finished: N records. {note}. Nothing was written."* and the note *Dry run on N sampled
  records. Nothing was written.* The **Data quality** panel shows the test run's own figures, marked *Test run (dry)*
  (see [section 13](#13-history)).
- **Human approval stops it**: the approval step shows *Awaiting approval*, the steps after it *Waiting on approval*.
  **Approve and continue** (Developer or Admin) runs it again past the approval, still dry, beside the note
  *"Simulated approval (dry run): nothing is sent."*; the toast says *"Approved in the test run. Simulated approval
  (dry run): nothing is sent to any system."*
- A test run reads the source live, so it can take a few seconds. If the source is syncing at that moment, the
  connector fails with *"{source} is syncing now"*; run it again.

## 11. Publish, unpublish, pause

- **Publish** (More actions) checks the draft with the server's full checks (errors refuse it: *"Cannot publish: N
  errors in the checks. Fix them first. First: {message}"*), saves it first if it has changes, and publishes that
  version: *"{name} published as v{x}. It runs on its trigger: {trigger}."* The server checks again and refuses with
  *"Cannot publish: N errors in the checks. Fix them first."* if anything changed in between.
- **Runs use the published version.** Saving later makes newer versions but runs keep using the published one; the
  header then shows *Runs v{pub} · v{x} not published*. To publish the newer saved version, choose **Publish v{x}**
  in More actions (or **Publish** on the current version in **History**): *"v{x} published. Runs now use it."* With
  unsaved changes it adds *"Your unsaved changes are still a draft: save and publish them to run them."*
- An ingest workflow you publish becomes the one its source's syncs run ([section 1](#1-what-a-workflow-is)).
- **Unpublish** (More actions, on a published workflow) returns it to draft: *"{name} unpublished. It will no longer
  run on its trigger."*
- **Pause / Resume** (list ⋯ menu, or bulk Pause): *"{name} paused. Scheduled runs stop until you resume it."* /
  *"{name} resumed."* A paused workflow is not started by its trigger and is no longer bound to its source; Run now
  still runs its published version. **Publish** in the list on a draft: *"{name} published."*

## 12. Running

**Run now** (header, list ⋯ menu, bulk **Run**) queues a run of the **published** version, or for a draft its saved
version. A draft runs only when its sources are connected and its checks are clean; otherwise *"{name} is a draft with
errors: …"*. When it ends: *"{name}: run finished, N records."* or *"{name}: run failed. {reason}"*.

**Triggers** start workflows published in the app on their own (the demo's seeded workflows are illustrations and fire on no trigger until a person publishes one):

| Trigger | When it runs |
|---|---|
| On a schedule (*Every n min*) | *n* minutes after the later of its last run and its last publish or save (the worker checks every 30 s) |
| On event | a webhook arrives for the workflow's source, of the workflow's event type when an Event trigger block sets one (`offer.*` matches every `offer.` event) (the bound ingest workflow is left out: the webhook's sync already runs it) |
| On approval | an instruction is queued for the workflow's target system |
| On file arrival | a sync of the workflow's source, a source that delivers files (the recycler partner's file drop), read new records (an unchanged drop reads none); the bound ingest workflow is left out, as its sync already ran it |
| On case request | a case needs a new decision: it moves to re-evaluation (declined, or changed after approval); every published case-triggered workflow runs |
| Manual only | only Run now |

A **Scheduler** or **Event trigger** block on the canvas sets the trigger instead of the Settings tab (see
[section 7.4](#74-orchestration)).

A triggered run is skipped silently when the workflow is not published, is already running, or its source is paused,
disconnected, not connected or deleted. The run list shows what started it: Manual, Schedule, Event, File, Approval,
Case, *Workflow* (a Call workflow step) or *Resume* (a Wait step coming back).

**One run at a time.** While a run is queued or going, Run now says *"{name} is already running"* and a trigger does
not queue another. A run whose worker died is closed as *Failed: worker lost*.

**Retries.** A step that fails is tried again the workflow's **Retries** times, after 1 s, 2 s, 4 s …; the **Try**
column shows how many tries it took. A source that cannot be read at all (paused, deleted, no feed) fails at once.

**States.** A step is *Success*, *Failed*, *Upstream failed* (a step before it failed), *Skipped* (no input) or waiting.
The run is **failed** if a step failed, **warning** if records were held (shown as *Success · stale*, with *N records
held at {step}*), else **success**. A published workflow whose graph has errors when it runs fails at the first error.

**What a run writes**: the records it read (landed records) and the source's cursors (moved only when no step failed),
the canonical facts the canonical step stores, the held records, a `model.updated` event for Publish to event stream,
an audit entry for Write to audit log, the records a Wait step parks (with their resume job), the run a Call workflow
step starts, the run record, and the workflow's last run (states, per-step counts, durations, tries). A workflow run
is not listed in the source's Sync & History.

**Alerts.** When a finished run matches the **Alert when** rule, a *Workflow alert · {name}* notification goes to the
Developer (Admin sees every notification) on the Alerts page: *"{name}: run {id} failed. {reason}"* (High), *"{name}:
two runs failed in a row. Latest run {id}. {reason}"* (High) or *"{name}: success rate dropped to N%, below 95%."*
(Medium).

## 13. History

The **History** tab has two panels.

**Versions** (*Runs use v{x}. Saving makes a new version; publish it to make runs use it.*, or *Not published: Run now
tries the saved version.*): every version, newest first, with when, by whom and a note (Saved, Published, Restored
v{x}, Fix applied …), and chips *Current* and *Published*.

- **Compare** shows what changed from that version to the current one: added and removed steps, each changed step's
  settings (was / now, defaults filled in), links added and removed, and changed workflow settings (name, owner,
  trigger, retries, alert). Positions on the canvas are not compared.
- **Restore** puts that version's graph and settings back as a **new** version: *"v{x} restored as v{y}."*, plus *"Your
  unsaved changes were dropped."* and *"Publish it to make runs use it."* when they apply.
- **Publish** on the current row, when the workflow is published but runs an older version.

**Runs** (*Every run of this workflow that happened, latest first*): Run ID, Status, Start time, Duration, Records (in /
out), **Held**, Triggered by and **View**. Only runs that really happened are listed. For a run made in the app the
figures are the server's: *in* the records it read, **Held** the records it still holds (the ones View failed records
lists), *out* = in − held (— for a failed run, and every figure — while it runs). A **seeded** run from the demo's
history never ran in the app and keeps the demo's estimate, with the note *"Seeded runs from the demo's history never
ran in the app: their out and held figures are the demo's estimate."* **View** opens the run: status, start,
duration, trigger, reason, for a real run its *Records (in / out)* and *Held*, and for the latest run every step with
its state, duration and records in and out (*Step timings are kept for the latest run; earlier runs keep their
totals.*), plus **View failed records** (for the latest real run only).

**Recent runs** on the studio tab shows the five newest (*View all →*).

**Data quality (latest run)**, on the studio tab, shows one set of real figures: the latest real run's records read
(*"Run {id}: N records read."*), a ring of *Passed* and *Held* with the share of valid records, **Fields that failed
most** (the held records by field; hover a field for its rules) and **View failed records (N)**. After a test run on
the canvas it shows that run instead: *"Test run (dry): N sampled records, M would be held. Nothing was written."*,
with the latest real run's held count below. A workflow that never ran in the app shows *No real run yet* (*The
figures appear after the workflow's first run in the app.*).

The **Documentation** tab describes every step in run order; **Explain this workflow** asks Ask Circularity.

## 14. When a run fails

A failing workflow shows **Investigate** in the list (or open it with `?run=last`). The **Investigation** panel names
the failed step, how many retries it took and when, an **Error log**, **Held records** (the records that run holds, by
step, field and rule; *"The run held no records."*, or for the demo's seeded failed run *"This failed run is the
demo's seeded history: nothing was held for real. Run now to see what a real run holds."*), and the buttons
**Diagnose** and **Fix** (both ask Ask Circularity) and **Run now**.

**Apply the suggested fix** gives the failed step back its settings (block settings and the failure toggle) from the
newest earlier version in which they were different, as a new version. The message says exactly what changed: *"{step}
is back to its settings from v{x}: currency back to USD."* followed by *"Run now to confirm it turns green."* If runs
used the saved version, the fix is published at once; if you had unpublished changes, they are kept and the message
adds *"Publish v{x} to make runs use it."* With no earlier version to restore: *"There is no earlier version of {name}
with other settings for {step} to restore. Change its settings by hand."* Once applied, the panel shows *Fix applied.*

**View failed records** (the Data quality panel, or a run's **View**) lists the records the latest run held:
record, field, value and the rule broken (*N records from the latest run broke a validation rule. They are held by the
error handler, not dropped.*; a record held on two fields counts once, and with 40 rows or more it adds *The first 40
rows are listed.*).

- **Export CSV** downloads them (record, field, value, rule): *"Failed records exported as CSV."*
- **Reprocess** sends every held record of the workflow's runs back through the published version, **starting at the
  step that rejected it**, with that step's settings as they are now (a record held by an error handler restarts at the
  step before the handler; one held by a canonical model at the field mapping). Records no step rejects again become
  *reprocessed*; the others stay held: *"N records sent back: N reprocessed, N still held. Those still break a rule."*
  Fix the rule (and publish it) first. With nothing held: *"No held records to reprocess."*

## 15. Monitor

**Connection Fabric → Monitor → Per workflow** (*Lowest success first*, up to 14 workflows that have runs): Workflow,
Runs (24 h), Success, Last run, Avg duration, p95 duration. The figures come from the workflow's **real runs of the last
24 hours** (a failed run counts against success). Expand a row (▸) for each step's **p95 duration** and the records it
still holds by rule (*None held* otherwise). A workflow with no real run in the window shows its seeded figures: *"No
real run in the last 24 hours: the figures are the workflow's seeded history, without steps."* The workflow's name
opens it in the studio.

On the workflow page, **Workflow details** shows the version, status, owner, trigger, last run, the next scheduled run,
the success rate over the workflow's runs and the last run's duration.

## 16. Messages you may see

| Message | Meaning |
|---|---|
| Only the Developer or Admin changes workflows. | Your role is read-only here. |
| Choose a system first. | New workflow needs a source or target system. |
| Enter a workflow name before saving. | The name is empty. |
| Retries must be 0, 1, 3 or 5. | A run setting outside its choices. |
| Cannot publish: N errors in the checks. Fix them first. First: {message} | Open the Checks panel; the first error is named. |
| Cannot publish {name}: {first error} | Publish from the list refused. |
| {name} is already published | Nothing new to publish; use More actions → Publish v{x} (or History → Publish) for a newer version. |
| Fix N errors before running. The checks (below) say what and why. First: {message} | Test run refused. |
| {name} takes no instructions. Grant it write access first. | New workflow: an outbound workflow to a source made in the app with no write operations. |
| Target operation {x} is not a write of this system ({writes}). | The write connector names a write the target does not take. |
| {step}: no field mapping version N for {source} | The field mapping's Mapping version does not exist (the step fails). |
| Call workflow cannot call its own workflow ({id}) / Call workflow: there is no workflow {id} / Call workflow: {id} calls {id} back, so the calls would go round in a circle | Call workflow refused (the step fails). |
| N records waiting at {step} | A Wait step parked records; a run labelled Resume comes back for them. |
| {name} is already running | One run at a time. |
| {name} is a draft with errors: … | Run now refuses a draft that would fail. |
| {source} has no connected feed | A connector's source is not connected (run or checks). |
| {source} is paused | The run's connector failed: resume the source. |
| {source} is syncing now | A sync of the source holds it; run again. |
| N records held at {step} | The run ended with held records (warning). |
| Failed: worker lost | The worker died during the run; it was closed. |
| No held records to reprocess. | Nothing to send back. |
| The suggested fix is already applied. Run now to confirm. | Run it to see the result. |
| The last run of {name} did not fail, so there is nothing to fix. | Apply fix needs a failed last run. |
| There is no earlier version of {name} with other settings for {step} to restore. Change its settings by hand. | No version to take the settings from. |
| v{x} is the current version. | Restore needs another version. |
| This is not a workflow export: it has no steps. | Import: the file has no steps. |
| Unknown block {ref} in step {id}. / Unknown source {ref} in step {id}. | Import: a block or source that does not exist. |
| Link {a} → {b} names a step the workflow does not have. | Import: a broken link. |
| {block} has no output. / {block} takes no input. Read connectors are where data starts. | That link is not possible. |
| That would create a loop. / Those two steps are already connected. / A step cannot connect to itself. | Link refused. |
| Fixed steps are wired by Circularity and cannot be re-wired. | Two fixed steps cannot be linked. |
| Fixed steps belong to Circularity and cannot be moved or removed. | A fixed block. |
| That connection is part of the fixed structure. | A locked link. |
| Simulated approval (dry run): nothing is sent. | Approve and continue in a test run: nothing reaches any system. |
| {block}: {setting} … is not a field the records carry. | A field-aware check: the source does not send that field. |
| {block}: {setting} rule N needs a range such as 0..100, >0 or <=5. | A rule's value does not fit its check. |

## 17. Limits and good to know

- Every vendor system is a synthetic mock; the AI builder offers only the demo's 21 systems.
- The **seeded demo workflows** keep the demo's figures (last run, success, Monitor row) until they run in the app; they
  show no step counts, and their sources are not bound to them until someone publishes one.
- **Test runs read the source live** (up to 25 records per connector) and can take a few seconds.
- The server's checks reach the Checks panel, Validate and the inspector about 0.6 s after an edit; the red text
  under a setting is the browser's own check only.
- The **seeded demo runs** keep the demo's estimate in the Runs table (with a note); every run made in the app shows
  the server's figures.
- Not used at run time yet: the file exchange steps' settings. The delivery methods' Timeout and Retries and the
  Target operation apply to the instructions sent to a target only once an outbound workflow for it is published in
  the app.
- A Wait step's resume is due on the wall clock, even when the workspace clock is pinned.
- A bound ingest workflow with a schedule trigger runs on the source's syncs **and** on its own schedule.
- The run list keeps the 40 newest runs across all workflows; the Monitor keeps the last 2000 runs' figures.
- The demo reset (`bash scripts/dev/reset.sh`) clears the versions and drafts made in the app.

## 18. See also

- [Workflow tutorial](workflow-tutorial.md): build, set up, publish and run a workflow step by step.
- [Connection Fabric guide](connection-fabric.md): the sources, mappings and syncs workflows read; section 7 is the
  short version of this guide.
- [Runbook: the Connection Fabric](../agents/runbook-fabric.md): for operators: a stuck or failed run, held records,
  triggers, credentials.
