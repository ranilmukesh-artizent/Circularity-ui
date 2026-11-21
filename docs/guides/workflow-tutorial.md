# Tutorial: build a working workflow by hand

This walk-through builds a real, running ingest workflow in Workflow Studio without any AI help. You start from the
standard SAP S/4HANA ingest template, re-wire it with three extra blocks, change its trigger and run settings, then
save, publish and run it. It takes about ten minutes and is safe to do live in a demo.

Every step below was performed in the app (Chrome, signed in as Developer, 21 Nov 2026), and the texts in quotes are
what the app showed. Version numbers and record counts can differ slightly on your run.

> All systems are simulated (`source-sim`); no real SAP system is involved.

## What you will build

The standard template (what **Create workflow** gives you):

```
SAP S/4HANA → API gateway → Validation & enrichment → Convert currency → ERP fields → Demand opportunity → Evidence snapshot
                                   └→ Error handler      ERP fields └→ Write to audit log   Demand opportunity └→ Publish to event stream
```

What you will end with:

```
SAP S/4HANA → API gateway → Order late events → Validation & enrichment → Convert currency → Filter and condition
            → Normalise units → ERP fields → Demand opportunity → Evidence snapshot
  (the error-handler, audit-log and event-stream branches stay)
```

| | Standard template | Your workflow |
|---|---|---|
| Name | Ingest · SAP S/4HANA | SAP returns · demand feed with quality gates |
| Steps | 10 | 13 (adds Order late events, Filter and condition, Normalise units) |
| Trigger | the source's poll interval | On a schedule, every 30 min |
| Owner | the source's owner | Remarketing Ops |
| Retries / alert | 3 / A run fails | 5 / Two runs fail in a row |

Why these blocks: *Order late events* removes duplicates and puts late events in order before validation;
*Filter and condition* keeps only the rows that matter after currency conversion; *Normalise units* converts units
(W → kW, EA, months) before the fields are mapped to the canonical model.

## Before you start

- The stack is running (`docker compose up -d`) and http://localhost:5173 opens.
- Sign in as **`developer`** (or `admin`) with any password. Only these two roles can open Workflow Studio.
- Optional, for a clean demo: reset the data first (`bash scripts/dev/reset.sh`; see the README).

## Part 1: create the draft from the template

1. In the left menu, open **Connection Fabric**, then the **Workflow Studio** tab.
2. Press **+ New workflow**.
3. In the dialog:
   - **Workflow type**: *Ingest pipeline · one source system into a canonical model*
   - **Source system**: *ERP · SAP S/4HANA*
   - **Name**: `SAP returns · demand feed with quality gates`
4. Press **Create workflow**.

✅ Toast: *"SAP returns · demand feed with quality gates created as a draft. Arrange it, then Save and Publish."*
The workflow page opens with 10 steps on the canvas, and the **Checks** panel says **No errors**.

Tip: press **Fit to width** in the canvas toolbar so every step is visible.

## Part 2: add "Order late events" after the API gateway

5. **Remove the link API gateway → Validation & enrichment.** Click the line between those two steps, close to
   the arrowhead that points at *Validation & enrichment*. The right-hand inspector shows the link; press
   **Remove connection**.
   - Checks now show *1 error* (validation is no longer fed). That is expected; it goes away in step 8.
6. In the palette on the left, under **Transform › Transform steps**, click **Order late events**
   (*De-duplicate, replay safely*).
   ✅ Toast: *"Order late events added. Drag from its right dot to connect it."*
7. Click the **API gateway** step. In the inspector, open **Connect output to** and choose **Order late events**.
8. Click the new **Order late events** step. In **Connect output to**, choose **Validation & enrichment**.
   ✅ Checks: **No errors** (a few warnings remain until the other new steps are wired).

You can also connect by dragging from a step's right-hand dot onto the next step; the dropdown is easier to do
precisely in front of an audience.

## Part 3: add "Filter and condition" and "Normalise units" after Convert currency

9. In the palette, click **Filter and condition** (*Keep rows that match*), then **Normalise units**
   (*W → kW, EA, months*). Each shows its "… added" toast.
10. **Remove the link Convert currency → ERP fields**: click that line near the arrowhead pointing at *ERP fields*,
    then **Remove connection**.
11. Click **Convert currency** → **Connect output to** → **Filter and condition**.
12. Click **Filter and condition** → **Connect output to** → **Normalise units**.
13. Click **Normalise units** → **Connect output to** → **ERP fields** (*Field mapping → Demand opportunity*).
    ✅ Checks: **No errors**, no warnings.
14. Press **Auto layout** in the canvas toolbar.
    ✅ Toast: *"Steps laid out left to right in run order."*
15. Press **Validate** (top right).
    ✅ Toast: *"No errors or warnings. This workflow is ready to run."*

If a warning remains, select the step it names in the Checks panel: usually one link is missing. Fixed steps (dark
outline: the canonical model, Evidence snapshot) and locked links cannot be changed, so work around them.

## Part 4: change the trigger and run settings

16. Open the **Settings** tab (under the workflow name).
17. Set:
    - **Trigger**: *On a schedule*, and **Every (min)**: `30`
    - **Owner (role or team)**: `Remarketing Ops`
    - **Retries**: `5`
    - **Alert when**: *Two runs fail in a row*
    ✅ Toast for Retries and Alert: *"Saved with the workflow."* (they are kept in the draft until you save)

## Part 5: save, test, publish, run

18. Open **More actions** (top right) and choose **Save**.
    ✅ Toast: *"SAP returns · demand feed with quality gates saved as v0.2."* The *Unsaved changes* chip disappears.
19. Go back to the **Workflow studio** tab and press **Test run**. The run goes step by step on the canvas
    (green = success); the **Task instances** panel below ends with **Success**. A test run sends nothing to any
    system.
20. **More actions → Publish**.
    ✅ Toast: *"SAP returns · demand feed with quality gates published as v0.2. It runs on its trigger: Every 30 min."*
    The status chip changes to **Published**.
21. Press **Run now**.
    ✅ After a few seconds: *"SAP returns · demand feed with quality gates: run finished, 874 records."* (the record
    count varies). The header shows *Last run … ago*; the run is listed under **Recent runs** and on the **History**
    tab.
22. Open **Workflow Studio** (breadcrumb) to see it in the list as **Published**, with its trigger *Every 30 min*,
    owner *Remarketing Ops* and its first run.

## Optional demo extras

- **Show a failure and the fix** (about two minutes):
  1. Click a movable step (e.g. *Filter and condition*) and press **Fail this step in the next run**.
  2. Change something small so there is something to save (e.g. add ` (rehearsal)` to the name), then
     **More actions → Save** and **Run now**.
     ✅ *"…: run failed. …"* and the **Investigation** panel: *"{step} failed after 5 retries"* (your Retries
     setting), with the error log and schema drift.
  3. Press **Apply the suggested fix**. ✅ *"Fix applied. Run now to confirm it turns green."*
  4. **Run now** again. ✅ *"…: run finished, N records."*
  Because *Alert when* is *Two runs fail in a row*, one failure raises no alert; two in a row put a *Workflow alert*
  on the Alerts page.
- **Save it as a template**: **More actions → Save as template** (*"Saved as a template. It appears under New
  workflow."*). The next **+ New workflow** dialog lists it under **Your templates**; one click creates a copy
  (*"Created from the template as a draft."*).
- **Export**: **More actions → Export JSON** downloads the saved version with every step and link.

## If something goes wrong

| What you see | What to do |
|---|---|
| **+ New workflow** is missing | Sign in as `developer` or `admin`. |
| Clicking a line selects a different link | Click closer to the arrowhead of the link you mean; near a step's output dot, branch links overlap. Press Escape and try again. |
| *"That connection is part of the fixed structure."* | That link is locked (e.g. Demand opportunity → Evidence snapshot); leave it. |
| *"That would create a loop."* / *"Those two steps are already connected."* | Pick another target in **Connect output to**. |
| Checks show an error after removing a link | Normal until the new step is wired in; finish the next steps. |
| *"Cannot publish: N error(s) in the checks. Fix them first."* | Select each error in the Checks panel; it names the step and the missing link. |
| **Save** is greyed out | Nothing changed since the last save (marking a step to fail alone does not count as a change). |
| *"Run now"* says the workflow is already running | Wait for the toast of the current run. |
| You want to start over | **More actions → Discard changes** (back to the last save) or **Reset to template**. |
