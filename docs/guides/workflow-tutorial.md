# Tutorial: build a working workflow by hand

This walk-through builds a real, running ingest workflow in Workflow Studio without any AI help. **New workflow**
starts you with only the blocks a workflow needs to run; you then mix and match the rest from the palette: four
data-quality blocks on the main line and two side branches. You give the blocks their settings in the inspector, try
the draft with a dry **Test run** on real records, save, publish and run it. It takes about fifteen minutes.

Every control and screen is described in [workflow-studio.md](workflow-studio.md) (detailed reference); this page is
the hands-on path.

How this was checked: the canvas steps (creating, wiring, Auto layout, Validate) were performed in the app (Chrome,
signed in as Developer, 21 Nov 2026), and the texts in quotes are what the app shows. The block settings and the Test
run results below were checked with dry runs of the same graphs on the server on 21 Nov 2026 (the counts are those of
that data). The Save, Publish, Run now and fix texts are the ones the code reports. Version numbers and record counts
can differ on your run.

> All systems are simulated (`source-sim`); no real SAP system is involved.

> **Publishing changes what the source's syncs do.** Once you publish an ingest workflow, its source's syncs run that
> workflow, with your settings (see [connection-fabric.md](connection-fabric.md#74-drafts-test-run-save-publish-run)).
> The one below reads only SAP's purchase orders. After a demo, reset the data (`bash scripts/dev/reset.sh`) so SAP
> syncs as before and the workflows you made are removed.

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
| Block settings | the defaults | SAP reads purchase orders in full; required `PurchaseOrder`; de-duplicated on `PurchaseOrder`; EUR; confirmed orders only |
| Trigger | the source's poll interval (every 5 min) | On a schedule, every 30 min |
| Owner | the source's owner | Remarketing Ops |
| Retries / alert | 3 / A run fails | 5 / Two runs fail in a row |

Why these blocks:
- **Order late events** removes duplicates (the newest record per key wins) and puts late events in order.
- **Convert currency** turns amount fields into the target currency at a dated rate.
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
- Your draft is autosaved on the server two seconds after each change. If you reload the page or sign out half way,
  open the workflow again: your changes are still there, marked *Unsaved changes*.

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
   (*Validation & enrichment → ERP fields*); press **Remove connection**. (Or click **Validation & enrichment** and
   press **Remove** next to *ERP fields* under **Connections → Sends to**.)
   - Checks now show a few warnings (the mapping is no longer fed). That is expected until step 11.

## Part 3: add four blocks to the main line

6. In the palette on the left, under **Transform steps**, click each of these once (each shows *"… added. Drag from
   its right dot to connect it."*):
   - **Order late events** (*De-duplicate, replay safely*)
   - **Convert currency** (*Dated rate, USD base*)
   - **Filter and condition** (*Keep rows that match*)
   - **Normalise units** (*W → kW, EA, months*)
7. Click **Validation & enrichment**. In the inspector, under **Connections → Sends to**, open **Next step** and choose
   **Order late events**.
8. Click **Order late events** → **Next step** → **Convert currency**.
9. Click **Convert currency** → **Next step** → **Filter and condition**.
10. Click **Filter and condition** → **Next step** → **Normalise units**.
11. Click **Normalise units** → **Next step** → **ERP fields** (*Field mapping → Demand opportunity*).
    ✅ Checks: **No errors**, no warnings.

You can also connect by dragging from a block's right-hand dot onto the next block; the dropdown is easier to do
precisely in front of an audience.

## Part 4: add two side branches

12. In the palette, open **Branches** and click **Error handler**.
13. Click **Validation & enrichment** → **+ Add another connection** → **Also send to** → **Error handler**. (A step can
    feed more than one block: the main line continues, rejected rows go to the error handler.)
14. Under **Branches**, click **Write to audit log**.
15. Click **ERP fields** → **+ Add another connection** → **Also send to** → **Write to audit log**.
    ✅ Checks: **No errors**.
16. Press **Auto layout** in the canvas toolbar.
    ✅ Toast: *"Steps laid out left to right in run order."*

## Part 5: give the blocks their settings

Click a block; its **Settings** are the first section of the inspector. A text or list field takes effect when you
leave it or press Enter. Each change marks the draft *Unsaved changes* and can be undone.

17. Click **SAP S/4HANA** (the source connector):
    - **Resources**: tick `purchase_order` only. This workflow feeds Demand opportunity from SAP's purchase orders;
      reading only them lets the next steps key on the purchase order number.
    - **Mode**: `full`. Each run reads every purchase order. (With *delta* a run reads only what changed since the
      last sync, which is often nothing.)
18. Click **Validation & enrichment** → **Required fields**: `PurchaseOrder`. A record without it is rejected and held
    by the Error handler.
19. Click **Order late events**:
    - **Key fields**: `PurchaseOrder` (records with the same purchase order are de-duplicated);
    - **Newest wins by**: `LastChangeDateTime`.
20. Click **Convert currency** → **Target currency**: `EUR`. (The step converts top-level amount fields. SAP's
    purchase orders carry their price inside the order items, in INR, and the SAP field mapping converts that itself,
    so on this feed the records leave the step unchanged; the setting is stored, checked and compared like any other.)
21. Click **Filter and condition** → **+ Add rule**: field `PurchasingDocumentCategory`, check `in`, value `F`. Only
    confirmed purchase orders go on. (A rule passes a record that does not carry the field at all.)
22. Leave **Normalise units** with no **Field units**: SAP's purchase orders carry no unit at the top level, so it
    passes every record on.
    ✅ Checks: **No errors**.

## Part 6: validate

23. Press **Validate** (top right).
    ✅ Toast: *"No errors or warnings. This workflow is ready to run."*
24. Optional, to show the field checks: in **Order late events → Key fields** type `opportunity_id` instead, then press
    **Test run**. ✅ Toast: *"Fix 1 error before running. The checks say what and why."* The server checks setting
    names against the fields SAP's records really carry, and SAP has no `opportunity_id`. (The canvas's Checks panel
    and Validate do not list this check yet.) Put `PurchaseOrder` back.

If a warning remains, select the block it names in the Checks panel: usually one link is missing.

## Part 7: change the trigger and run settings

25. Open the **Settings** tab (under the workflow name).
26. Set:
    - **Trigger**: *On a schedule*, and **Every (min)**: `30`
    - **Owner (role or team)**: `Remarketing Ops`
    - **Retries**: `5`
    - **Alert when**: *Two runs fail in a row*
    ✅ Toast for Retries and Alert: *"Saved with the workflow."* (they are kept in the draft until you save)

## Part 8: test run, save, publish, run

27. Go back to the **Workflow studio** tab and press **Test run**. The draft runs dry on the server over a sample of
    SAP's real purchase orders.
    ✅ Toast: *"Test run finished: 25 records. Nothing was written."* Under **Task instances** every step shows
    **Success**, the note says *"Dry run on 25 sampled records. Nothing was written."*, and **Records (in / out)** shows
    *25 / 25* on the main line and *0 / 0* on the Error handler.
    What to look for under **Samples** (next to a step's counts):
    - **SAP S/4HANA → After**: purchase orders, with `PurchaseOrder`, `PurchasingDocumentCategory` `F` and
      `DocumentCurrency` `INR`;
    - **Filter and condition**: *25 / 25*, every sampled order is confirmed;
    - **ERP fields → After**: each record now carries its canonical `facts` (the demand values the mapping writes).
    Nothing reached any system and no data changed.
28. Open **More actions** (top right) and choose **Save**.
    ✅ Toast: *"SAP returns · demand feed with quality gates saved as v0.2."* The *Unsaved changes* chip disappears.
29. **More actions → Publish**. Publish before Run now: runs use the published version.
    ✅ Toast: *"SAP returns · demand feed with quality gates published as v0.2. It runs on its trigger: Every 30 min."*
    The status chip changes to **Published**, and SAP S/4HANA's syncs now run this workflow.
30. Press **Run now**.
    ✅ After a few seconds: *"SAP returns · demand feed with quality gates: run finished, N records."* (N is the
    number of purchase orders SAP holds.) The header shows *Last run … ago*; the run is listed under **Recent runs**
    with Records (in / out) and *Manual* under Triggered by.
31. Open the **History** tab. **Versions** lists *v0.2* (**Current**, **Published**) and *v0.1*, the version you
    started from; the subtitle says *"Runs use v0.2. …"*. Press **Compare** on v0.1: *v0.1 → v0.2* lists the added
    steps, the settings you changed on the starting blocks (e.g. SAP S/4HANA `mode` delta → full, Validation &
    enrichment `required`), the links and the workflow settings. **Runs** lists the run you just made.
32. Open **Workflow Studio** (breadcrumb) to see it in the list as **Published**, with its trigger *Every 30 min*,
    owner *Remarketing Ops* and its first run. From now on it also runs every 30 minutes by itself.

## Optional demo extras

- **Show a failure and the fix** (about three minutes):
  1. Click **Filter and condition** and, under **Testing**, press **Fail this step in the next run**.
  2. Change something small so there is something to save (e.g. add ` (rehearsal)` to the name), then
     **More actions → Save** (v0.3).
  3. Open **History**: v0.3 is **Current**, v0.2 still **Published**. Press **Publish** on the v0.3 row.
     ✅ *"v0.3 published. Runs now use it."* (The **More actions** item now reads **Unpublish**, so a newer version is
     published from here.)
  4. **Run now**. Because Retries is 5, the step is tried six times, 1, 2, 4, 8 and 16 seconds apart, so this takes
     about half a minute. ✅ *"…: run failed. …"* and the **Investigation** panel: *"Filter and condition failed after
     5 retries"*, with the error log.
  5. Press **Apply the suggested fix**. ✅ *"Filter and condition is back to its settings from v0.2: failure toggle
     off. Run now to confirm it turns green."* The fix is a new version (v0.4), published at once because v0.3 was the
     published one; History shows it with the note *Fix applied: Filter and condition settings from v0.2*.
  6. **Run now** again. ✅ *"…: run finished, N records."*

  Because *Alert when* is *Two runs fail in a row*, one failure raises no alert; two in a row put a *Workflow alert*
  on the Alerts page.
- **Hold records and reprocess them**: in **Validation & enrichment → Rules**, **+ Add rule** `CompanyCode`, `in`,
  `2000` (SAP's orders belong to company code 1000), and press **Test run**: Validation & enrichment shows *25 / 0 ·
  25 held*, the Error handler *25 / 0*, and the toast names *"25 records held at Validation & enrichment"*. Published
  and run for real, those records are held: **View failed records** (Data quality panel) lists them with the rule
  broken; after you remove the rule, save and publish, **Reprocess** sends them back from that step: *"N records sent
  back: N reprocessed, 0 still held."*
- **Go back to a version**: **History → Restore** on v0.2. ✅ *"v0.2 restored as v{x}. Publish it to make runs use
  it."* (v{x} is the next version number; the second sentence shows for a published workflow), then **Publish** on
  the new row.
- **Start over**: **More actions → Reset to template** puts the six starting blocks back (*"Workflow reset to its
  template. Save to keep it."*); **Discard changes** drops your draft and returns to the last save (*"Changes
  discarded. Back to v{x}."*).
- **Save it as a template**: **More actions → Save as template** (*"Saved as a template. It appears under New
  workflow."*). The next **+ New workflow** dialog lists it under **Your templates**; one click creates a copy.
- **Export and import**: **More actions → Export JSON** downloads the saved version with every block, link and
  setting. **Import** on the Workflow Studio list reads such a file back as a new draft (*"… imported as a draft
  (WF-…)."*).
- **The same with AI**: **Build with AI** and *"Ingest from SAP S/4HANA with de-duplication, currency conversion to
  EUR, a filter and unit normalisation, an error handler and an audit log, every 30 minutes, 5 retries, alert when two
  runs fail in a row"* plans a workflow with the same twelve blocks (it may order the four data-quality blocks
  differently), sets Convert currency's Target currency to EUR, and shows which blocks are required and which you
  asked for. Set the other settings in the inspector as in Part 5.

## More workflows to build

Six more workflows, each built from a different starting point and with different blocks. They use exactly the same
moves as the main tutorial:

1. **+ New workflow**; remove a link (click it → **Remove connection**, or **Remove** in the inspector);
2. click blocks in the palette and wire them in the inspector (**Next step**, or **+ Add another connection** →
   **Also send to** when the block already sends somewhere), then **Auto layout**;
3. give the blocks their **Settings** (inspector);
4. **Validate**, the **Settings** tab, then **Test run** and read the counts and **Samples**;
5. **More actions → Save**, **More actions → Publish** (before Run now: runs use the published version), **Run now**;
6. **History**: the published version, and **Compare** with v0.1 to see what you changed.

The wiring of each was performed in the app on 21 Nov 2026 as Developer and passed **Validate** with *"No errors or
warnings. This workflow is ready to run."* The settings and Test run results were checked with dry runs of the same
graphs on the server; record counts are those of the dev data and can differ. Each publishes as v0.2 with *"…
published as v0.2. It runs on its trigger: …"*, and Run now ends with *"…: run finished, N records."*

- **Ingest workflows** (A to C) become what their source's syncs run once published; reset after a demo (see the top
  of this page).
- **Outbound and decision workflows** (D to F) read no source records: their Test run shows *0 / 0* on every step. It
  stops at **Human approval** with *Awaiting approval*. A Developer cannot press **Approve and continue** (*"Your role
  cannot approve. Switch to Approver to continue the run."*); Admin can (*"Approved in the test run. No instruction is
  sent to any system."*), and the steps after it run, still dry.

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
- **Block settings**:
  - Timestamps to UTC: **Fields** `changedate`; **Source zone** stays *record* (Maximo's times carry their offset).
  - Resolve identity: **Identity keys** `assetnum, serialnum`. It matches only within one tenant.
  - Code-table lookup: **Code tables** → **+ Add**: field `conditioncode`, table `condition`.
  - Publish to event stream: **Topic** stays `model.updated`.
- **Settings tab**: Owner `Asset Data Office`, Retries 3, Alert when *A run fails*.
- **Test run**: *25 records*, every step *25 / 25*. In **Samples**:
  - Timestamps to UTC: `changedate` with an offset becomes UTC, e.g. `2026-10-06T14:30:00+05:30` →
    `2026-10-06T09:00:00Z`;
  - Code-table lookup: a grade such as `C-` becomes `C`;
  - Resolve identity: Maximo's asset records carry no tenant field, so they pass unchanged.
  Try **Code tables** `status` → `status` instead: Maximo's statuses (`LIMITEDUSE`, `DECOMMISSIONED`) are not in that
  table, so the test run holds every record: *"25 records held at Code-table lookup"*. Set it back.
- **Result**: 10 blocks; *"published as v0.2. It runs on its trigger: On event."* Run now reads Maximo's records; a
  Maximo webhook also starts it, through the source's sync.
- **What it shows**: local times become UTC, codes become Circularity's grades, and each update of the asset model is
  announced on the event stream.

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
- **Block settings**:
  - Validation & enrichment: **Rules** → **+ Add rule** `offer_amount`, `range`, `>0`.
  - Data enrichment: **Lookup model** *Asset & component*, **Key** `stock_number`.
  - Expression: **Target field** `offer_total`, **Expression** `offer_amount * quantity`.
  - Aggregation: leave **Group by** and **Totals** empty (see the test below).
- **Settings tab**: Trigger *On a schedule*, Every (min) `60`, Owner `Remarketing`, Retries 1, Alert when *Success
  rate drops below 95%*.
- **Test run**: *25 records*, every step *25 / 25*, Error handler *0 / 0*. In **Samples**:
  - Data enrichment → After: each offer gains an `asset` object, the canonical asset its `stock_number` names (e.g.
    `PMP-0320`, a hydraulic pump of Customer A);
  - Expression → After: each offer has `offer_total`.
  Then try **Group by** `dealer_id` and **Totals** `offer_amount` on Aggregation and Test run again: Aggregation shows
  *25 / 5* (one record per dealer, with the summed `offer_amount` and a `count`), and *Dealer network fields* *5 / 0 ·
  5 held* (*"5 records held at Dealer network fields"*), because a dealer total is not an offer the mapping can map.
  Aggregation belongs after the mapping or in a reporting flow; clear both fields before you publish.
- **Result**: 10 blocks; *"published as v0.2. It runs on its trigger: Every 60 min."*
- **What it shows**: offers are enriched from the canonical store and get a derived field before they become demand
  signals; rows that break the rule wait in the error handler; the test run shows the effect of a setting before
  anything is published.

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
- **Block settings**:
  - Filter and condition: **+ Add rule** `STATUS`, `in`, `APPROVED`. Vendor approvals that lapsed are left out; the
    other files (custody certificates, yields, rates) carry no `STATUS` and pass.
  - Normalise units: no **Field units** (the files' quantities are inside their rows); it passes records on.
  - Write to audit log: **Level** stays *info*.
- **Settings tab**: Owner `Sustainability`, Alert when *Never*.
- **Test run**: *6 records*. Filter and condition shows *6 / 5*: the record left out is the vendor approval whose
  `STATUS` is `LAPSED` (**Samples** show the first three records before and after the step).
- **Result**: 10 blocks; *"published as v0.2. It runs on its trigger: On event."* (the trigger it was created with).
  Sims is a manual-import source: it supports evaluation, not live automation.

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
- **Block settings**: Code-table lookup: **Code tables** `ReasonCode` → `reason`; Normalise units: **Field units**
  `Quantity` → `EA`. Outbound API call: **Timeout (s)** and **Retries** (defaults 30 and 3). With no source upstream,
  the server has no record fields to check these names against.
- **Settings tab**: Owner `Warehouse Operations`, Retries 3, Alert when *Two runs fail in a row*.
- **Test run**: stops at Human approval (*Awaiting approval*), the steps after it *Waiting*; as Admin, **Approve and
  continue** runs them; *0 / 0* records throughout.
- **Result**: 9 blocks; *"published as v0.2. It runs on its trigger: On approval."* It runs when an instruction is
  queued for the WMS after a person approves a decision.
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
- **Block settings**: Convert currency: **Target currency** `INR`; Fetch import log: **Wait for the log (min)** `60`;
  Notify with log links: **Notify** `Finance Systems` (empty: the workflow's owner); Create manifest: **Include
  checksums** stays ticked.
- **Settings tab**: Owner `Finance Systems`, Retries 5, Alert when *A run fails*.
- **Test run**: stops at Human approval; after **Approve and continue** (Admin) every step is *Success* with *0 / 0*.
- **Result**: 10 blocks, published (*On approval*).

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
- **Block settings**: none. Agent tools and fixed steps say *"This step has no settings: Circularity runs it the same
  way in every workflow."*
- **Settings tab**: Owner `Decision Services`, Retries 1.
- **Test run**: the steps up to request_approval succeed, Human approval waits (*Awaiting approval*).
- **Result**: 12 blocks; *"published as v0.2. It runs on its trigger: On case request."* Nothing starts *On case
  request* yet, so use **Run now**.
- **If you place a tool where the rules do not allow it** (e.g. find_demand after the gates), Checks names the rule:
  *"find_demand has to come before Six eligibility gates. Demand fit is gate 4 …"*.

## If something goes wrong

| What you see | What to do |
|---|---|
| **+ New workflow** is missing | Sign in as `developer` or `admin`. |
| The inspector shows a different link than you meant | Where two links leave the same block they run on top of each other for a moment; click a little further along the line you mean. |
| *"That connection is part of the fixed structure."* | That link is locked (Demand opportunity → Evidence snapshot); leave it. |
| *"That would create a loop."* / *"Those two steps are already connected."* | Pick another step in **Next step** / **Also send to**. |
| Warnings after removing a link | Normal until the new blocks are wired in; finish the next steps. |
| A red message under a setting | The value cannot be used (e.g. a rule without a value); fix it, or Test run and Publish refuse. |
| *"Fix 1 error before running. The checks say what and why."* but the Checks panel shows none | A setting names a field the source's records do not carry (Part 6). Compare with the connector's **Samples**. |
| *"Cannot publish: N error(s) in the checks. Fix them first."* | Select each error in the Checks panel; it names the block and the missing link or setting. If the panel is empty, see the row above. |
| Test run fails at the source with *"… is syncing now"* | A sync of that source was running; press Test run again. |
| A step shows *25 / 0 · 25 held* in a test run | A rule or setting rejects every record; open its **Samples** and compare the fields with the setting. |
| **Save** is greyed out | Nothing changed since the last save (marking a block to fail alone does not count as a change). |
| A change you saved does not show in runs | Runs use the published version: **History → Publish** on the current row. |
| *"… is already running"* | One run at a time; wait for the toast of the current run. |
| *"There is no earlier version of … to restore."* | Apply the fix needs an earlier version with other settings for that step; change the setting by hand. |
