# Tutorial: build a working workflow by hand

This walk-through builds a real, running ingest workflow in Workflow Studio without any AI help. **New workflow**
starts you with only the blocks a workflow needs to run; you then mix and match the rest from the palette: four
data-quality blocks on the main line and two side branches. Then you set the trigger and run settings, save, publish
and run it. It takes about ten minutes and is safe to do live in a demo.

Every step below was performed in the app (Chrome, signed in as Developer, 21 Nov 2026), and the texts in quotes are
what the app showed. Version numbers and record counts can differ slightly on your run.

> All systems are simulated (`source-sim`); no real SAP system is involved.

## What you will build

What **Create workflow** gives you (only the blocks it needs to run):

```
SAP S/4HANA → API gateway → Validation & enrichment → ERP fields → Demand opportunity → Evidence snapshot
```

What you will end with (12 blocks):

```
SAP S/4HANA → API gateway → Validation & enrichment → Order late events → Convert currency → Filter and condition
            → Normalise units → ERP fields → Demand opportunity → Evidence snapshot
Validation & enrichment └→ Error handler            ERP fields └→ Write to audit log
```

| | What New workflow gives you | Your workflow |
|---|---|---|
| Name | Ingest · SAP S/4HANA | SAP returns · demand feed with quality gates |
| Blocks | 6 (required to run) | 12 (adds Order late events, Convert currency, Filter and condition, Normalise units, Error handler, Write to audit log) |
| Trigger | the source's poll interval (every 5 min) | On a schedule, every 30 min |
| Owner | the source's owner | Remarketing Ops |
| Retries / alert | 3 / A run fails | 5 / Two runs fail in a row |

Why these blocks:
- **Order late events** removes duplicates and puts late events in order.
- **Convert currency** turns amounts into USD at a dated rate.
- **Filter and condition** keeps only the rows that matter.
- **Normalise units** converts units (W → kW, EA, months) before the fields are mapped.
- **Error handler** holds the rows validation rejects, for reprocessing.
- **Write to audit log** records each run's counts and timings.

The six starting blocks are what makes it run: the source, one way in (API gateway), validation, the field mapping,
and the canonical model with its evidence snapshot (dark outline: placed by Circularity, they cannot be moved or
removed).

## Before you start

- The stack is running (`docker compose up -d`) and http://localhost:5173 opens.
- Sign in as **`developer`** (or `admin`) with any password. Only these two roles can open Workflow Studio.
- Optional, for a clean demo: reset the data first (`bash scripts/dev/reset.sh`; see the README).

## Part 1: create the draft

1. In the left menu, open **Connection Fabric**, then the **Workflow Studio** tab.
2. Press **+ New workflow**.
3. In the dialog:
   - **Workflow type**: *Ingest pipeline · one source system into a canonical model*
   - **Source system**: *ERP · SAP S/4HANA*
   - **Name**: `SAP returns · demand feed with quality gates`
4. Press **Create workflow**.

✅ Toast: *"SAP returns · demand feed with quality gates created as a draft with only the blocks it needs to run. Add
more from the palette, then Save and Publish."* The canvas shows the six blocks above; **Checks** says **No errors**.

Tip: press **Fit to width** in the canvas toolbar so every block is visible.

## Part 2: make room on the main line

5. **Remove the link Validation & enrichment → ERP fields.** Click that line. The right-hand inspector shows the link
   (*Validation & enrichment → ERP fields*); press **Remove connection**.
   - Checks now show a few warnings (the mapping is no longer fed). That is expected until step 11.

## Part 3: add four blocks to the main line

6. In the palette on the left, under **Transform steps**, click each of these once (each shows *"… added. Drag from
   its right dot to connect it."*):
   - **Order late events** (*De-duplicate, replay safely*)
   - **Convert currency** (*Dated rate, USD base*)
   - **Filter and condition** (*Keep rows that match*)
   - **Normalise units** (*W → kW, EA, months*)
7. Click **Validation & enrichment**. In the inspector, open **Connect output to** and choose **Order late events**.
8. Click **Order late events** → **Connect output to** → **Convert currency**.
9. Click **Convert currency** → **Connect output to** → **Filter and condition**.
10. Click **Filter and condition** → **Connect output to** → **Normalise units**.
11. Click **Normalise units** → **Connect output to** → **ERP fields** (*Field mapping → Demand opportunity*).
    ✅ Checks: **No errors**, no warnings.

You can also connect by dragging from a block's right-hand dot onto the next block; the dropdown is easier to do
precisely in front of an audience.

## Part 4: add two side branches

12. In the palette, open **Branches** and click **Error handler**.
13. Click **Validation & enrichment** → **Connect output to** → **Error handler**. (A step can feed more than one
    block: the main line continues, rejected rows go to the error handler.)
14. Under **Branches**, click **Write to audit log**.
15. Click **ERP fields** → **Connect output to** → **Write to audit log**.
    ✅ Checks: **No errors**.
16. Press **Auto layout** in the canvas toolbar.
    ✅ Toast: *"Steps laid out left to right in run order."*
17. Press **Validate** (top right).
    ✅ Toast: *"No errors or warnings. This workflow is ready to run."*

If a warning remains, select the block it names in the Checks panel: usually one link is missing.

## Part 5: change the trigger and run settings

18. Open the **Settings** tab (under the workflow name).
19. Set:
    - **Trigger**: *On a schedule*, and **Every (min)**: `30`
    - **Owner (role or team)**: `Remarketing Ops`
    - **Retries**: `5`
    - **Alert when**: *Two runs fail in a row*
    ✅ Toast for Retries and Alert: *"Saved with the workflow."* (they are kept in the draft until you save)

## Part 6: save, test, publish, run

20. Open **More actions** (top right) and choose **Save**.
    ✅ Toast: *"SAP returns · demand feed with quality gates saved as v0.2."* The *Unsaved changes* chip disappears.
21. Go back to the **Workflow studio** tab and press **Test run**. The run goes block by block on the canvas
    (green = success); the **Task instances** panel below ends with **Success**. A test run sends nothing to any
    system.
22. **More actions → Publish**.
    ✅ Toast: *"SAP returns · demand feed with quality gates published as v0.2. It runs on its trigger: Every 30 min."*
    The status chip changes to **Published**.
23. Press **Run now**.
    ✅ After a few seconds: *"SAP returns · demand feed with quality gates: run finished, N records."* The header
    shows *Last run … ago*; the run is listed under **Recent runs** and on the **History** tab.
24. Open **Workflow Studio** (breadcrumb) to see it in the list as **Published**, with its trigger *Every 30 min*,
    owner *Remarketing Ops* and its first run.

## Optional demo extras

- **Show a failure and the fix** (about two minutes):
  1. Click a movable block (e.g. *Filter and condition*) and press **Fail this step in the next run**.
  2. Change something small so there is something to save (e.g. add ` (rehearsal)` to the name), then
     **More actions → Save** and **Run now**.
     ✅ *"…: run failed. …"* and the **Investigation** panel: *"{block} failed after 5 retries"* (your Retries
     setting), with the error log and schema drift.
  3. Press **Apply the suggested fix**. ✅ *"Fix applied. Run now to confirm it turns green."*
  4. **Run now** again. ✅ *"…: run finished, N records."*
  Because *Alert when* is *Two runs fail in a row*, one failure raises no alert; two in a row put a *Workflow alert*
  on the Alerts page.
- **Start over**: **More actions → Reset to template** puts the six starting blocks back (*"Workflow reset to its
  template. Save to keep it."*); **Discard changes** returns to the last save.
- **Save it as a template**: **More actions → Save as template** (*"Saved as a template. It appears under New
  workflow."*). The next **+ New workflow** dialog lists it under **Your templates**; one click creates a copy.
- **Export**: **More actions → Export JSON** downloads the saved version with every block and link.
- **The same with AI**: **Build with AI** and *"Ingest from SAP S/4HANA with de-duplication, currency conversion, a
  filter and unit normalisation, an error handler and an audit log, every 30 minutes, 5 retries, alert when two runs
  fail in a row"* plans a workflow with the same twelve blocks (it may order the four data-quality blocks
  differently) and shows which blocks are required and which you asked for.

## More workflows to build

Six more workflows, each built from a different starting point and with different blocks. They use exactly the same
moves as the main tutorial: **+ New workflow**, remove a link (click it → **Remove connection**),
click blocks in the palette, wire them with **Connect output to**, then **Auto layout**, **Validate**, the
**Settings** tab, **More actions → Save**, **Test run**, **More actions → Publish** and **Run now**.

Each one was built this way in the app on 21 Nov 2026 as Developer. Every one passed **Validate** with *"No errors
or warnings. This workflow is ready to run."*, was published as v0.2 and finished **Run now** with *"…: run finished,
N records."*

In the workflows that go through **Human approval** (outbound and decision), **Test run** stops there with *Awaiting
approval*. A Developer cannot press **Approve and continue** (*"Your role cannot approve. Switch to Approver to
continue the run."*); Admin can. **Run now** runs the whole saved workflow.

Palette groups used below: **Transform steps** and **Orchestration steps** are open by default. Open **Branches**
(Error handler, Write to audit log, Publish to event stream) and **File exchange steps** (Fetch import log, Notify
with log links …) by clicking their heading.

### A. Event-driven ingest: Maximo asset events with identity and timestamps

*New blocks: Timestamps to UTC, Resolve identity, Code-table lookup, Publish to event stream (branch).*

- **New workflow**: *Ingest pipeline*, source *EAM · IBM Maximo*, name `Maximo asset events · identity and
  timestamps`.
- **It starts with**: IBM Maximo → **Event ingestion** → Validation & enrichment → EAM fields → Asset & component →
  Evidence snapshot. Maximo sends events, so its one way in is event ingestion, and the trigger is *On event*.
- **Steps**:
  1. Remove the link *Validation & enrichment → EAM fields*.
  2. Add **Timestamps to UTC**, **Resolve identity** and **Code-table lookup**.
  3. Connect *Validation & enrichment → Timestamps to UTC → Resolve identity → Code-table lookup → EAM fields*.
  4. Under **Branches**, add **Publish to event stream**, then connect *Asset & component → Publish to event stream*.
- **Settings**: Owner `Asset Data Office`, Retries 3, Alert when *A run fails*.
- **Result**: 10 blocks; *"published as v0.2. It runs on its trigger: On event."*; Run now finished (484 records).
- **What it shows**: local times become UTC, the same asset seen under two IDs becomes one record (inside one
  tenant), status codes become Circularity's grades, and each update of the asset model is announced on the event
  stream.

### B. Scheduled ingest: dealer listings as enriched price signals

*New blocks: Data enrichment, Expression, Aggregation, Error handler (branch).*

- **New workflow**: *Ingest pipeline*, source *Dealer network · Machinio*, name `Dealer listings · enriched price
  signals`.
- **It starts with**: Dealer network → Event ingestion → Validation & enrichment → Dealer network fields → Demand
  opportunity → Evidence snapshot.
- **Steps**:
  1. Remove the link *Validation & enrichment → Dealer network fields*.
  2. Add **Data enrichment**, **Expression** and **Aggregation**.
  3. Connect *Validation & enrichment → Data enrichment → Expression → Aggregation → Dealer network fields*.
  4. Under **Branches**, add **Error handler**, then connect *Validation & enrichment → Error handler*.
- **Settings**: Trigger *On a schedule*, Every (min) `60`, Owner `Remarketing`, Retries 1, Alert when *Success rate
  drops below 95%*.
- **Result**: 10 blocks; *"published as v0.2. It runs on its trigger: Every 60 min."*; Run now finished (252
  records).
- **What it shows**: listings are looked up and enriched, a derived field is computed, and they are grouped and
  totalled before they become demand signals; rejected rows wait in the error handler.

### C. File drop ingest: recycler CSV into certified outcomes

*New blocks: Normalise units, Filter and condition, Write to audit log (branch). Starting blocks include the
file-exchange steps.*

- **New workflow**: *Ingest pipeline*, source *Recycler partner · Sims Lifecycle Services*, name `Recycler CSV drop ·
  certified outcomes`.
- **It starts with**: Sims → **Poll for trigger file → Download and unzip → Chunk large files** → Validation &
  enrichment → Recycler partner fields → **Outcome**. Sims delivers files only, so the file steps are its way in, and
  it feeds the Outcome model (no evidence snapshot).
- **Steps**:
  1. Remove the link *Validation & enrichment → Recycler partner fields*.
  2. Add **Normalise units** and **Filter and condition**.
  3. Connect *Validation & enrichment → Normalise units → Filter and condition → Recycler partner fields*.
  4. Under **Branches**, add **Write to audit log**, then connect *Recycler partner fields → Write to audit log*.
- **Settings**: Owner `Sustainability`, Alert when *Never*.
- **Result**: 10 blocks; *"published as v0.2. It runs on its trigger: On event."* (the trigger it was created with);
  Run now finished (460 records). Sims is a manual-import source: it supports evaluation, not live automation.

### D. Outbound by API: putaway instructions to Manhattan WMS

*New blocks: Code-table lookup and Normalise units on the outbound side, Write to audit log (branch).*

- **New workflow**: *Outbound instruction*, target *WMS · Manhattan Active Warehouse Management*, delivery *Outbound
  API call*, name `Putaway instructions to Manhattan WMS`.
- **It starts with**: Decision → Human approval → Instruction envelope → Outbound API call → WMS → Outcome. Decision →
  Human approval is locked: anything that commits stock stops at a person.
- **Steps**:
  1. Remove the link *Instruction envelope → Outbound API call*.
  2. Add **Code-table lookup** and **Normalise units**.
  3. Connect *Instruction envelope → Code-table lookup → Normalise units → Outbound API call*.
  4. Under **Branches**, add **Write to audit log**, then connect *Instruction envelope → Write to audit log*.
- **Settings**: Owner `Warehouse Operations`, Retries 3, Alert when *Two runs fail in a row*.
- **Result**: 9 blocks; *"published as v0.2. It runs on its trigger: On approval."*; Run now finished (6 records).
- **What it shows**: the approved instruction is translated into the WMS's codes and units before the API call, and
  every instruction is written to the audit log.

### E. Outbound by file: recovery postings to SAP with the import log

*New blocks: Convert currency, Fetch import log, Notify with log links. Starting blocks include File generation and
Create manifest.*

- **New workflow**: *Outbound instruction*, target *ERP · SAP S/4HANA*, delivery *Interface file*, name `Recovery
  postings to SAP by interface file`.
- **It starts with**: Decision → Human approval → Instruction envelope → **File generation → Create manifest** →
  SAP → Outcome.
- **Steps**:
  1. Remove the link *Instruction envelope → File generation*.
  2. Add **Convert currency**, then connect *Instruction envelope → Convert currency → File generation*.
  3. Under **File exchange steps**, add **Fetch import log** and **Notify with log links**.
  4. Connect *SAP → Fetch import log → Notify with log links*. The import log can only be fetched after the target
     has imported, so it follows the write connector.
- **Settings**: Owner `Finance Systems`, Retries 5, Alert when *A run fails*.
- **Result**: 10 blocks, published (*On approval*), Run now finished (4 records).

### F. Decision workflow: pool allocation with a demand search

*New blocks: the agent tools find_demand and optimize_pool. A decision canvas shows agent tools in its palette, not
pipeline blocks.*

- **New workflow**: *Decision workflow · six gates to approval*, name `Pool allocation with demand search`.
- **It starts with**: Case evidence → Six eligibility gates → list_eligible_routes → predict_outcomes →
  request_approval → Human approval → Decision → send_instruction → Outcome → reconcile_outcome.
- **Steps**:
  1. Under **Agent tools · read**, add **find_demand**.
  2. Connect *Case evidence → find_demand → Six eligibility gates*. Demand fit is gate 4, so demand has to be found
     before the gates run.
  3. Add **optimize_pool**.
  4. Connect *predict_outcomes → optimize_pool → request_approval*. Allocation works on eligible routes, and nothing
     is committed until a person approves.
- **Settings**: Owner `Decision Services`, Retries 1.
- **Result**: 12 blocks; *"published as v0.2. It runs on its trigger: On case request."*; Run now finished.
- **If you place a tool where the rules do not allow it** (e.g. find_demand after the gates), Checks names the rule:
  *"find_demand has to come before Six eligibility gates. Demand fit is gate 4 …"*.

## If something goes wrong

| What you see | What to do |
|---|---|
| **+ New workflow** is missing | Sign in as `developer` or `admin`. |
| The inspector shows a different link than you meant | Where two links leave the same block they run on top of each other for a moment; click a little further along the line you mean. |
| *"That connection is part of the fixed structure."* | That link is locked (Demand opportunity → Evidence snapshot); leave it. |
| *"That would create a loop."* / *"Those two steps are already connected."* | Pick another target in **Connect output to**. |
| Warnings after removing a link | Normal until the new blocks are wired in; finish the next steps. |
| *"Cannot publish: N error(s) in the checks. Fix them first."* | Select each error in the Checks panel; it names the block and the missing link. |
| **Save** is greyed out | Nothing changed since the last save (marking a block to fail alone does not count as a change). |
| *"Run now"* says the workflow is already running | Wait for the toast of the current run. |
