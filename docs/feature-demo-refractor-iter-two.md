# Plan: demo refactor, iteration two (journey-led flow, step guidance, value that builds step by step, line-item learning)

**Purpose of this file:** a self-contained brief for a fresh session. It does not assume any earlier conversation. Read it top to bottom, then start at **Phase 0**.

**Status:** built on `feature/demo-refactor` (2026-10-16), not pushed; every section 4 decision is on its default and marked **(assumed)** (section 10). `CHANGES.md` Update 10 is the reviewer walk-through. Source: a follow-up review call with the Product Owner on 2026-10-16 (Tamil and English; the translated notes are in the appendix), and a first-draft write-up of that call that this plan checks and replaces. Open decisions are in **section 4**. Each has a recommended default; until the Product Owner answers, build the default and label it **(assumed)**.

**Builds on:** `docs/PLAN_DEMO_SIGNIN_SINGLE_ASSET.md` (iteration one: sign-in form, demo path, retrieved vs predicted, exceptions by warehouse, SKU units; `CHANGES.md` Update 9), which builds on `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` and `docs/PLAN_RBAC_ADAPTIVE_UI.md`. **Branch:** keep working on `feature/demo-refactor` (iteration one is committed there and not pushed: `60eca63`, `afc68b1`, `dcc1f0d`).

**Deadline:** an in-person review with the Product Owner on **Monday morning (19 Oct 2026)**. The stakeholder meeting moved to Monday or Tuesday next week. Section 8 gives a short order if time runs out.

> **Compliance note.** This iteration adds wording about model learning (which model learns from which cost line) and about what enterprise systems decide. Per policy, wording about model outputs, data provenance and accountability should be reviewed by the Legal team before it is relied on or used with clients. The demo stays synthetic: no real names, emails or customer data. Participants are referred to by role.

> **About the first-draft notes.** The call transcript is reliable for *what was asked*. The first write-up of it, however, added details that are **not in the app** and quoted wrong line numbers (section 3). This plan uses only what was checked in `index.html`, `docs/demo/user-flow.svg` and the Product Owner's diagram (`docs/demo/user-journey-diagram.png`) on 2026-10-16.

---

## 1. The feedback to solve

| # | Ask (call time) | Today (checked in the app) | Wanted |
|---|---|---|---|
| G1 | **Exceptions are not part of the asset journey** (03:41–04:27). "We must not land on Exceptions." Exceptions is a dashboard for Executives or Planners. After sign-in the user sees what has been returned, picks one asset and follows its journey | `docs/demo/user-flow.svg` puts *Exceptions by warehouse* in box 2 of the main flow, and numbering only starts at box 4 (*1. Supply evidence*). The app itself already sends the end user (`ops`) straight to Returned assets; the Executive (`exec`) lands on the Command Center | A flow diagram that goes **Sign in → Returned assets → 1 … 10**, with the Exceptions dashboard as a side callout, not a box in the sequence |
| G2 | **Every step clickable, and it guides you** (05:27–06:40). The build lead said clicking steps 1–9 in Product → Decision Workbench takes you to the matching screen; the Product Owner agreed | The journey strip (`journey()`) renders each step as a **non-clickable `<span>`**. The demo rail (`DP_STOPS`) is clickable but merges boxes **2–3** and **6–9**, so 7, 8 and 9 cannot be opened on their own | All ten steps clickable, each opening its own screen and scroll target for the selected case |
| G3 | **Intelligent "what next" guidance** (04:29–05:14). "After looking at this, where do I go next? What is the next information I should be aware of?" | The rail has Back and Next only. Nothing says what was just established or what to look for next | A short guide at each step: what this step established, what the next step answers, and a **Continue** button |
| G4 | **All options visible at step 4** (02:28–02:40). Even when Redeploy is recommended, refurbish, resale, harvest and the rest must be visible | Treatment Intelligence step 3 lists every pathway, including the withheld one (*Sell parts externally*, no buyer in 30 days), and so does the Economic tab of Asset Intelligence. But the journey's step 4 opens Treatment Intelligence step 2, which shows only the recommendation, and the step 4 comparison shows only the **top three** (`tiMulti`) | One table at step 4 with **every route** for the case: net, P10–P90, eligible or withheld (with the reason), recommended marked |
| G5 | **Asset Intelligence fills in step by step** (00:55–01:25). "It will not be populated initially with the price and commercial value." | The predicted side of Asset Intelligence shows the recommended route and **$9,600** as soon as the page opens, whatever step you came from | Commercial value shown in stages: *pending evaluation* (before step 4) → *predicted, not committed* (after 4) → *committed against SO/WO* (after 6) → *predicted vs actual* (after 10) |
| G6 | **Value tied to a Work Order or Sales Order** (03:06–03:40). After step 10, against that order, "predicted price is so much, actual realisation is so much". Redeploy goes against a Sales Order for a customer; repair or refurbish becomes a Work Order | The Sales Order exists for RT-1048 (**SO-48102 at Site 3**, `caseDemand`) and appears on the predicted side and in the instruction preview. The handoff rows carry **no order references**. Predicted vs actual appears only as one line on the treatment page after Finance confirms (`Predicted $9,600 · actual … · variance …`), not on Asset Intelligence | Each handoff row shows the order it created (SO for ERP, WO for EAM, transfer for WMS). Asset Intelligence shows predicted vs actual **against that order** once reconciled |
| G7 | **Learning by line item, not just the net** (00:18–00:54). Example: recommended $2,500, sold for $1,800 (−$700); estimated repair $70, actual $110. "Learning will see where the difference came from." | Actual outcome is **one net number**, drawn at random when Finance confirms (`confirmOutcome`: `r.net × (1 + gauss()×.05 − .01)`), so it differs on every run. Each route already has its cost lines (`r.terms`, with a `kind`) and the predictions name their models (`prep-cost-time`, `resale-price`, `service-exposure`, `repair-success`, `time-to-sell`, all v1.3) | Actuals per cost line, deterministic, adding up to the actual net; a **line-item variance table** at step 10 naming which model learns from each line |
| G8 | **Circularity sends; the enterprise decides the execution outcome** (00:02–00:17). "We only send the approved plan and receive the reference and acknowledgements." | Already the wording since Update 8 (handoff, "Simulate system acknowledgement", "the enterprise systems carry out the work") | Keep. Add the returned **reference** to each acknowledgement (G6) |
| G9 | **Problems in steps 1–5 show in Exceptions** (00:55) | Exceptions by warehouse already covers missing evidence, condition deterioration, delayed approval, capacity and declining metrics | Keep. Make the link visible: a case with an open exception shows it on its journey, and the diagram's side callout says so (G1) |

**Not in scope:** new analytics pages, backend work, real connectors, model changes. Numbers already shown elsewhere (128 live cases, 1,400 closed, Executive figures) must not change.

---

## 2. Orientation: where the code is

Still **one file, `index.html`**, no build step. **Search by name; line numbers drift** (the first-draft notes quoted line numbers that were wrong; see section 3).

| Area | Where (as of 2026-10-16) |
|---|---|
| Journey strip | `JSTEPS` (~line 1566, already uses the diagram's ten names), `journey(on)` (~1598); mounted by `route()` into `#jmount` |
| Demo rail | `DEMO_ID`, `dpId`, `DP_STOPS` (~1573), `dpStops`, `dpStop`, `dpRail`, `dpHint`; links use `?focus=`, `?zone=`, `?step=`, `?at=handoff`, `?dp=` (read with `hq()`) |
| After-render scrolling | `afterRender()`: `?zone=` scrolls to `#aszKnown` / `#aszPred`; `?step=N` calls `ACT.tiStep(N)`; `?at=handoff` scrolls to `#tiHandoff` |
| Sign-in | `signInFormHTML` (~1806), `SIGNIN_IDS`, `signInResolve`, `homeOf` |
| Asset Intelligence | `/*ASSET-START*/ … /*ASSET-END*/`: `asOverview` (zones `#aszKnown` ~2871, `#aszPred`), `asPredRec`, `asPredRul`, `asEcon`, `asPredRoutes`, `asElig`, `assetHead`, `assetFacts`, `skuStrip`, `skuUnits` (~2723) |
| Treatment Intelligence | `/*TI-START*/ … /*TI-END*/`: `caseView` (steps 1–5, `#step-1…5`), `tiOutcome`, `tiClv` (`tiKnown` / `tiPredicted`), `tiMulti` (top-3 comparison), `tiHandoff`, `instrPayload` |
| Handoff and outcome | `stepsOf(c)` (for RT-1048: ERP · Order Management *Redeployment order* → EAM · Diagnostic and Repair *Refurbishment work order* → WMS · transfer *Transfer to site* → ERP · order fulfilled *Outcome reported*), `execBlock` (`#tiHandoff`), `ackStep`, `ACT.advance`, `ACT.confirmOutcome` |
| References | `S.seq.wo` already issues `WO-` numbers (evidence requests); `caseDemand(c).order` gives the Sales Order |
| Exceptions | `ccExList`, `ccExRows`, `ccExHTML`, `exOwner` |
| Analytics | `renderAnalytics`; section *Predicted vs actual* (portfolio level, from `ROWS`; `?dp=` does not filter it) |

**The demo record, RT-1048** (checked 2026-10-16): Voltara V4 motor, `MTR-2041`, `SN6399949`, Customer A, Warehouse 1, Grade B, awaiting approval. Routes: **Redeploy RT-1048 $9,600** (recommended), *Sell + buy for Site 3* $4,800, *Re-lease + buy for Site 3* $3,600, *Recover parts + buy for Site 3* $3,200, *Recover material* $310, *Responsible exit* −$60, *Sell parts externally* $1,580 (**withheld**: no confirmed buyer within 30 days). Matched demand **SO-48102 at Site 3**; re-lease opportunity **LS-5530** (forecast). Estimated life 30–40 months; certified 24 months (QMS-2906).

---

## 3. Verification of the first-draft notes

Each claim in the first write-up, checked against the source files on 2026-10-16.

### 3.1 The diagrams

| Claim | Verdict | Finding |
|---|---|---|
| In the as-built flow image, the first three boxes are unnumbered and *1. Supply evidence* is box 4 | **True** | `docs/demo/user-flow.svg`: Sign in → Exceptions by warehouse → Returned assets, then 1, 2–3, 4, 5, 6, 7–9, 10 |
| *Exceptions by warehouse* sits in the main sequence | **True** | Box 2, with the arrow "Notify owner · Planner signs in" to Returned assets. This is the point the Product Owner rejected |
| `user-flow.svg` has a rendering issue: text not visible in standard image previews | **Not reproduced** | The file is valid XML with 88 `<text>` elements and renders in Chrome. It uses system fonts (Arial, Segoe UI). Some previewers (file-explorer thumbnails, some chat uploads) do not draw SVG text. Fix: also export a PNG of each diagram (phase 1) |
| `image_710f7c.png` is the current image | **Not in the repo** | Presumably a screenshot of `user-flow.svg` taken elsewhere |
| The Product Owner's diagram has ten separate boxes | **True** | `docs/demo/user-journey-diagram.png`: 1 Supply evidence · 2 Build alternatives · 3 Predict outcomes · 4 Optimize plan · 5 Plan approval · 6 Send instruction · 7 Create execution work · 8 Repair & certify · 9 Action & return outcome · 10 Reconcile & learn. The first draft's proposed diagram merges **7–8**; this plan keeps all ten separate so the diagram matches G2 |
| Box 1 includes pending orders and contracts (ERP / CRM) | **Partly** | The PO's box 1 says EAM inspection and history, PLM/quality eligibility, ERP/WMS cost and stock. Checking internal and external **demand** is box 2 ("Check internal and external demand"). This plan follows the PO's diagram |

### 3.2 The app (`index.html`)

| Claim | Verdict | Finding |
|---|---|---|
| Sign-in form `signInFormHTML()` "at line 662" | Function **true**, line **wrong** | ~1806 |
| Retrieved/predicted split `#aszKnown` vs `#aszPred` "at line 424" | True, line **wrong** | ~2871 |
| SKU unit switcher `.skusel` / `skuUnits` "at line 480" | True, line **wrong** | ~2723 |
| `journey(on)` "line 614" renders non-clickable `<span class="jstep">` | **True**, line wrong (~1598) | |
| `DP_STOPS` "line 581" merges 2–3 and 6–9 | **True**, line wrong (~1573) | |
| Step 2 scroll target `#asElig` | **Does not exist** | `asElig` is a function; Asset Intelligence panels have no ids. Ids must be added (5.2) |
| Handoff rows: 1 *Redeployment order → ERP · Order Management*, 2 *Refurbishment work order → EAM · WO-94001*, 3 *Repair, test & QMS certification*, 4 *Outcome reported* | **Partly wrong** | Rows 1, 2 and 4 exist. Row 3 is **WMS · transfer, *Transfer to site***; there is no QMS certification row. **WO-94001 does not exist**; no handoff row carries a reference today |
| A one-click *"Simulate ERP Outcome"* button | **Does not exist** | Each row has **Simulate system acknowledgement**; the fourth acknowledgement reports the outcome |
| Intake Work Order **WO-91240** in the asset header | **Does not exist** | The header has no order reference. Receiving is a WMS receipt, not a work order (decision H5) |
| Step 4 options *Redeploy $9,600, Resale $4,800, Re-lease $3,600, **Harvest parts** $3,200* | **Label wrong** | $3,200 is **Recover parts + buy for Site 3** (internal recovered-part use), not harvest. There is no *Refurbish* route for RT-1048 (refurbish appears as *Refurbish, then sell* on other units, e.g. RT-1001) |
| "15 units in stock" at step 1 | **Wrong meaning** | 15 is the number of **Voltara V4 motors returned by Customer A** (`skuUnits`), not WMS stock |
| Re-lease option **LS-5530** | **True, with a quirk** | LS-5530 is the re-lease opportunity in the route notes ("Opportunity LS-5530 · forecast"), but the asset header shows it as **Ownership: Customer A · lease LS-5530**. Fix the header label while here (5.6) |
| Sales Order **SO-48102 · Site 3 · Customer A** for Redeploy | **True** | From `caseDemand` |
| Model names `prep-cost-time v1.3`, `resale-price v1.3` | **True** | Plus `service-exposure`, `repair-success`, `time-to-sell` |
| Line-item variance in Step 10 or Analytics | **Does not exist** | Only a net predicted vs actual line on the treatment page after Finance confirms; the actual net is random per run |
| $2,500 → $1,800 and $70 → $110 | **The PO's illustration** | Not RT-1048 figures. The demo must use RT-1048's own cost lines (6.1) |
| "Exception Center" | **Name not used in the app** | The panel is **Exceptions by warehouse** on the Command Center |

---

## 4. Decisions needed from the Product Owner

Ask these on Monday. If there is no answer, build the **default** and mark it **(assumed)**.

| # | Question | Recommended default |
|---|---|---|
| H1 | The Executive still lands on the Command Center (with Exceptions). Is that right, given "we must not land on Exceptions"? | **Yes.** The objection is to Exceptions inside the *asset journey* and the flow diagram. The end user already lands on Returned assets. The diagram shows the Executive's dashboard as a side entry |
| H2 | Merge the demo rail into the ten-step journey strip? | **Yes.** One strip, ten clickable boxes plus a *Start · Returned assets* chip, with Back and Next. The separate rail with merged pills goes |
| H3 | Which screen does each step open? | The map in **5.2**: 1–3 on Asset Intelligence, 4–5 on Treatment Intelligence, 6–9 on the handoff rows, 10 on a new *Reconcile & learn* block (Analytics stays a link from there) |
| H4 | Before step 4, should the predicted side of Asset Intelligence be hidden? | **Collapsed, not hidden**, when opened from step 1: a placeholder "Not evaluated yet: steps 2–4 add eligible treatments, life and value", with a button to step 2. Opened directly (not on the journey), the page behaves as today |
| H5 | Do you want an intake reference on the asset header? | **No work order at intake.** Show the WMS receipt reference (e.g. `GR-…`) as *Received under*. Downstream orders (SO for redeploy or sale, WO for repair or refurbish) appear once handed off |
| H6 | Should certification be its own handoff row (QMS)? | **No new row** (keeps the four acknowledgements and every existing total). The EAM acknowledgement says "repaired, tested and certified; QMS record updated" and step 8 points to it |
| H7 | Which model learns from which cost line? | `prep` and `fees` → **prep-cost-time**; `sale`, `parts`, `material`, `lease` → **resale-price**; `service` → **service-exposure**; avoided **purchase** → no model (it is an ERP price, retrieved) |
| H8 | How large should synthetic actual-vs-predicted differences be? | Per line, within ±25% of the prediction, deterministic per case, adding up to the actual net. RT-1048's repair line should come out **over** estimate so the story matches the call ("repair cost more than we thought") |
| H9 | Show the line-item variance at portfolio level in Analytics too? | **Not now.** Case level only (step 10). Analytics *Predicted vs actual* stays as is, linked from the step |
| H10 | Keep `docs/demo/user-flow.svg` or replace it? | **Replace** it with the corrected flow (5.1), and keep a PNG export next to every diagram |

---

## 5. Design

### 5.1 Flow diagram, version 2 (G1)

Redraw `docs/demo/user-flow.svg` (and the Mermaid in `docs/demo/user-flow.md`) in the Product Owner's style:

- **Entry row:** *Sign in* → *Returned assets* (pick one asset: RT-1048). Small, unnumbered, before the journey.
- **Journey:** ten separate boxes, **numbered exactly like the PO's diagram**, same names and colours (Circularity yellow, enterprise systems white, human in the loop white). Under each box, the screen that shows it (5.2).
- **Side callouts (not in the sequence):** *Exceptions dashboard (Executive, Planner)*: "a gate failure, missing evidence, a delayed approval or a capacity problem in steps 1–5 surfaces here; Notify owner sends it to the person who acts". *Asset Intelligence fills in as you go*: the value states from 5.5.
- Export `user-flow.png` and `journey-slide.png` next to the SVGs (the "text not visible" report).

### 5.2 Ten clickable steps (G2, H2, H3)

The journey strip becomes the navigation for the selected case (`dpId()`, default RT-1048). Each step is an `<a>` with its own deep link; the current step is highlighted; Back and Next stay. New query `jstep=N` is additive (old links keep working).

| Step | Opens | Scrolls to and highlights |
|---|---|---|
| Start | `product/received?focus=RT-1048` | The case row, *Start here* |
| 1 Supply evidence | `product/asset/RT-1048?zone=known&jstep=1` | `#aszKnown` (EAM condition, QMS certified period, lifecycle, return history, specs) |
| 2 Build alternatives | `product/asset/RT-1048?zone=predicted&jstep=2` | New id `#asEligCard` (eligibility and gates) plus matched demand (SO-48102, LS-5530) |
| 3 Predict outcomes | `product/asset/RT-1048?zone=predicted&jstep=3` | New ids `#asRulCard`, `#asEconCard` (life, value by route, costs) |
| 4 Optimize plan | `product/RT-1048?step=2&jstep=4` | Step 2 with the new **all pathways** table (5.4) |
| 5 Plan approval | `product/RT-1048?step=5&jstep=5` | The decision card: Submit, or Approve / Override / Decline |
| 6 Send instruction | `product/RT-1048?step=5&at=handoff&jstep=6` | Instruction preview, or the sent payload |
| 7 Create execution work | `…&jstep=7` | Handoff rows 1–2: ERP Redeployment order (SO), EAM Refurbishment work order (WO) |
| 8 Repair & certify | `…&jstep=8` | Handoff row 2 detail: repaired, tested, certified (H6) |
| 9 Action & return outcome | `…&jstep=9` | Rows 3–4: WMS Transfer to site, ERP Outcome reported |
| 10 Reconcile & learn | `product/RT-1048?step=5&at=reconcile&jstep=10` | New `#tiReconcile` block (5.7), with a link to Analytics *Predicted vs actual* |

Rules: each step shows its status for the case (done, current, not reached yet) from the case's stage; a step not reached yet still opens, and its guide says what has to happen first. Roles without a page skip its step (for example the Warehouse Manager has no Analytics link at step 10). The rail's `DP_STOPS` is replaced by this map (prefix `jg`).

### 5.3 "What next" guide (G3)

A short block at the bottom of each step's screen, built from the case's data, not hard-coded to RT-1048:

- **Established here:** one line, e.g. step 1: "Grade B from EAM, certified for 24 months (QMS-2906), received at Warehouse 1, returned twice before." Step 2: "6 of 7 routes eligible; *Sell parts externally* withheld (no buyer in 30 days); confirmed demand SO-48102 at Site 3."
- **Next, and what to look for:** e.g. "Step 3 · Predict outcomes: how long it will last and what each route is worth."
- **Continue to step N →** (primary button), and **Back**.
- When the step is not reached yet: "This happens after approval (step 5)" instead of the established line.

Prefix `jg`. Same wording rules as the rest of the app: plain English, decision-intelligence wording.

### 5.4 Every option at step 4 (G4)

On Treatment Intelligence step 2, under the recommended outcome, an **All pathways** table: every route for the case, sorted by net: name, net, P10–P90, status (*Recommended*, *Eligible*, *Withheld: reason*). For RT-1048: 7 rows, 6 eligible, 1 withheld. The top-3 comparison in step 4 stays as is.

### 5.5 Value that builds step by step (G5, H4)

A **Commercial value** card on the predicted side of Asset Intelligence with four states, from the case's stage:

| State | When | Shows |
|---|---|---|
| Pending evaluation | No recommendation yet | "Evaluated in steps 2–4" |
| Predicted, not committed | Recommendation, awaiting approval | Recommended route and predicted net, labelled *predicted* |
| Committed | Approved or handed off | The same, plus the order it is committed against (SO-48102, or the WO) |
| Predicted vs actual | Outcome confirmed | Predicted net, actual net, variance, against the order; link to step 10 |

When Asset Intelligence is opened from **step 1** (`jstep=1`), the predicted side is collapsed to the placeholder in H4. The retrieved side never shows a route or a value (rule from iteration one, still tested).

### 5.6 Orders on the handoff (G6, G8, H5)

- Each acknowledgement stores the reference the enterprise system returned: ERP Redeployment order → **SO-48102** (the matched order) or a new `SO-` for a sale; EAM Refurbishment work order → a new `WO-` from `S.seq.wo`; WMS transfer → `TR-…`; ERP outcome → the invoice or fulfilment reference. Shown on the row and in the audit event.
- Asset header: *Received under GR-…* (H5). Fix the *Ownership* fact so it shows the current lease, and show **LS-5530** as a re-lease *opportunity* on the predicted side.

### 5.7 Reconcile and learn by line item (G7, H7, H8)

- **Deterministic actuals:** when the outcome is reported, derive an actual for each cost line of the chosen route from `hashId(case + line)`, within ±25% (H8), and set the actual net to their sum. Replace the random `gauss()` in `ACT.confirmOutcome`.
- **`#tiReconcile` block** (step 10) after Finance confirms: table **Cost line · Predicted · Actual · Δ · Learns** (model and version from H7), with the net row at the bottom. Above it: "Predicted $9,600 against SO-48102 · actual $… · variance …". Before confirmation: "Waiting for the outcome from ERP (step 9) and Finance's confirmation."
- The same predicted vs actual summary appears on Asset Intelligence (5.5, last state).

### 5.8 What stays the same

Sign-in, roles and scopes, retrieved vs predicted zones, exceptions by warehouse, SKU units, presenter mode, Update 8 behaviour, the 128 seeded cases, every recommendation and every total.

### 5.9 Do not break

- Deep links from iteration one (`?focus=`, `?zone=`, `?step=`, `?at=handoff`, `?dp=`) still work; `jstep=` is additive.
- No route name or route value on the retrieved side, for any case.
- Numbers: 128 live, 1,400 closed, Executive equals Finance, 38 handed off, exception totals.
- RBAC: hide-don't-disable, tenant and warehouse locks, every account reachable.
- Phone width 390 px, dark mode, print.

---

## 6. Data additions (synthetic, deterministic)

Derive at render time. **Do not add `rnd()` calls to the generator**; it would shift every seeded number.

| Field | Derived from | Notes |
|---|---|---|
| Actual per cost line | `hashId(c.id + term.label)`, ±25% | Sum is the actual net; replaces `gauss()` |
| Model per cost line | `term.kind` → H7 map | `prep-cost-time`, `resale-price`, `service-exposure`, or "ERP price (retrieved)" |
| Handoff references | `caseDemand(c).order`, `S.seq.wo`, `hashId` | SO, WO, TR, invoice |
| Receipt reference | `hashId(c.id + 'gr')` | `GR-…` on the header |
| Step status per case | `c.stage`, `c.exec` steps, `c.outcome` | done, current, not reached |

New invariants in `runInvariants`: for every confirmed outcome, line actuals add up to the actual net; the same case gives the same actuals on every run.

---

## 7. Phases (each ends with tests, a screenshot and a short report)

**Phase 0: Baseline.** Rebuild the harness (RBAC plan section 8; the "headless harness quirks" note). Run the role suite (208), guided-flow suite (110) and demo suite (91). Screenshot Returned assets, Asset Intelligence for RT-1048, steps 2 and 5, and the handoff.

**Phase 1: Flow diagram v2 (G1, H10).** Redraw `user-flow.svg` and the Mermaid; export PNGs; update `DEMO_SCRIPT.md` part 0. Test: renders in Chrome and as PNG; ten numbered boxes match the PO's names; Exceptions only as a side callout.

**Phase 2: Ten clickable steps (G2, H2, H3).** Journey strip as navigation, step map, panel ids, `jstep=`, retire the merged rail. Test: each step opens its screen and highlights its target for Planner A, Approver, Admin and Executive; Back and Next walk 1 → 10 and back; roles without a page skip that step.

**Phase 3: What next guide (G3).** Test: every step shows an established line, a next line and a working Continue button for all 128 cases, with no `undefined` or `NaN`.

**Phase 4: All pathways at step 4 (G4).** Test: the table lists every route of every case; withheld routes show their reason; the recommended one is marked.

**Phase 5: Value states and orders (G5, G6, H4, H5).** Commercial value card, step-1 collapse, references on the handoff, receipt reference, ownership fix. Test: each state appears for a case in that stage; references appear only after the matching acknowledgement; the retrieved side still has no route or value.

**Phase 6: Line-item reconciliation (G7, H7, H8).** Deterministic actuals, `#tiReconcile`, summary on Asset Intelligence. Test: lines add up; same result on every run; each line names its model; RT-1048's repair line is over estimate.

**Phase 7: Docs.** `CHANGES.md` **Update 10**, README (journey, Asset Intelligence, the decision page), `DEMO_SCRIPT.md`, screenshots `docs/screenshots/iter2-*.webp`, this plan's section 10.

**If time is short:** 1 → 2 → 4 → 3 → 5 → 6 → 7. The diagram and clickable steps carry the call's main asks; line-item learning can be shown on RT-1048 alone.

---

## 8. Project rules

All rules in `docs/PLAN_RBAC_ADAPTIVE_UI.md` section 7, `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` section 8 and `docs/PLAN_DEMO_SIGNIN_SINGLE_ASSET.md` section 8 apply: palette tokens only, prefixed class names (new prefixes here: `jg` journey guide and steps, `rc` reconciliation), reuse existing components, no new libraries, `data-act` + `ACT` + `esc()`, hash routes for every state, container queries, 390/768/1280/1600 px, synthetic data only, plain English, `CHANGES.md` for every visible change, decision-intelligence wording, no push until asked.

Additional rules for this plan:
- **The PO's diagram is the reference.** Step numbers and names in the app, the slides and the script are the diagram's, exactly.
- **Value appears when the step that produces it has run.** Never show an actual before the outcome is confirmed, or a commitment before handoff.
- **Every variance names its source.** A line-item difference always says which model (or which retrieved price) it belongs to.
- **Enterprise systems decide execution.** Circularity sends the approved instruction and records references and acknowledgements; wording must not imply Circularity carries out the work.

---

## 9. Test plan (extends the existing suites)

Run the three existing suites; change expectations only where this plan changes behaviour (the rail, the step-4 table, the value card, the outcome figure) and note each one in `CHANGES.md`. Add:

1. **Diagram:** ten boxes with the PO's names and numbers; Exceptions not in the sequence; PNG exports exist.
2. **Steps:** for Planner A, Approver, Admin and Executive, each of the ten steps (plus Start) opens its route, highlights its target and lights only its box in the strip; Back and Next both ways; Warehouse Manager skips the Analytics link.
3. **Guide:** for all 128 cases, steps 1–10 each render an established line (or a "not reached" line), a next line and a Continue link to the next step.
4. **Step 4:** the all-pathways table row count equals `c.routes.length` for every case; withheld rows carry `failReason`.
5. **Value states:** one case per stage shows the right state; step-1 entry collapses the predicted side; no route or value on the retrieved side for any case.
6. **Orders:** RT-1048's first acknowledgement shows SO-48102; the EAM acknowledgement shows a WO; references appear in audit events.
7. **Reconcile:** after Finance confirms RT-1048, line actuals add up to the actual net, match on a second run, and every line names a model or "ERP price (retrieved)".
8. **Regression:** 390 px on every new block, dark mode, invariants, no console errors.

---

## 10. Product Owner decisions

No answers yet: each row is built on the recommended default and stays **(assumed)** until the Product Owner confirms it on Monday. "Where it lands" names the code (search `index.html` by name) and the visible change.

| # | Answer | Where it lands |
|---|---|---|
| H1 | Pending (assumed: yes, the Executive still lands on the Command Center) | `homeOf` unchanged; the flow diagram shows Exceptions as a dashed side dashboard (`docs/demo/user-flow.svg`) |
| H2 | Pending (assumed: one strip replaces the rail) | `jgStrip` (Start + ten links, Back, Next); `DP_STOPS` and `dpRail` removed; non-journey pages keep `journey()` |
| H3 | Pending (assumed: the map in 5.2) | `JG` (links, `?jstep=N`) and `JG_TGT` (targets); `afterRender` scrolls and adds `.jghl`; new ids `#asEligCard`, `#asDemandCard`, `#asRulCard`, `#asEconCard`, `#tiAllPaths`, `#tiDecision`, `#tiInstr`, `#tiHo1…4`, `#tiReconcile` |
| H4 | Pending (assumed: collapsed, not hidden, from step 1) | `asCollapsed` with *Continue to step 2* and *Show the predictions now* (`ACT.asShowPred`); other entries unchanged |
| H5 | Pending (assumed: WMS receipt, no intake work order) | `asReceipt` (*Received under GR-…*); `asLease` for the lease that ended; LS-5530 only as the re-lease opportunity (`asDemand`) |
| H6 | Pending (assumed: no new QMS row) | `ACK_NOTE['Refurbishment work order']`: *repaired, tested and certified; QMS record updated*; step 8 points at handoff row 2 |
| H7 | Pending (assumed: the map in section 4) | `LEARN` (prep, fees → prep-cost-time; sale, parts, material, lease, residual → resale-price; service → service-exposure; risk → repair-success) and `LEARN_RET` (purchase, avoid → ERP price, retrieved; credit → vendor contract, retrieved) |
| H8 | Pending (assumed: ±25%, deterministic, RT-1048 repair over estimate) | `lineActuals` (from `hashId(case + line)`); `LEARN_PIN` pins RT-1048's preparation line 15% over: actual $9,230 vs $9,600 |
| H9 | Pending (assumed: case level only) | `tiReconcile` on the decision page, with a link to Analytics *Predicted vs actual* (unchanged) |
| H10 | Pending (assumed: replace) | `docs/demo/user-flow.svg`, `user-flow.md`, PNG exports of the flow and the journey slide |

---

## 11. Definition of done

- The flow diagram goes Sign in → Returned assets → steps 1–10 numbered like the PO's diagram, with Exceptions as a side dashboard; PNG copies exist.
- Every one of the ten steps is clickable for the selected case and opens the right screen and section; Back and Next walk the whole journey.
- Each step says what it established and what to look at next, with a Continue button.
- Step 4 shows every route, including withheld ones with the reason.
- Asset Intelligence shows commercial value in stages: pending, predicted, committed against an order, predicted vs actual.
- Each handoff acknowledgement carries the order reference the enterprise system returned.
- Step 10 shows predicted vs actual by cost line, the same on every run, with the model that learns from each line.
- All checks pass with no console errors; numbers reconcile; light and dark correct; no overflow at 390 px. `CHANGES.md` Update 10 and `README.md` updated; committed, not pushed until asked.

---

## 12. Prompt to paste into the fresh session

> Read `docs/feature-demo-refractor-iter-two.md` fully, then `docs/PLAN_DEMO_SIGNIN_SINGLE_ASSET.md` sections 2, 4 and 8, and look at `docs/demo/user-journey-diagram.png`. Skim `index.html` around `JSTEPS`, `journey(`, `DP_STOPS`, `dpRail`, `afterRender`, `/*ASSET-START*/` (`asOverview`, `asPredRec`, `assetHead`), and `/*TI-START*/` (`caseView`, `tiOutcome`, `tiMulti`, `execBlock`, `stepsOf`, `ACT.confirmOutcome`). Work on branch `feature/demo-refactor`. Follow the project rules in section 8 exactly. Start with Phase 0, then one phase at a time in the order of section 7, running tests and sharing a screenshot after each. Commit with detailed messages; do not push or merge until I say so.

---

## 13. Does the plan match the asks?

| Ask | Covered in | Match | Notes |
|---|---|---|---|
| Don't land on Exceptions; start from returned assets (G1) | 5.1, H1 | Yes | The app already does this for the end user; the diagram is fixed |
| Every step clickable, guiding the user (G2) | 5.2, H2, H3 | Yes | Ten single steps, no merged pills |
| "Where do I go next, what should I know next" (G3) | 5.3 | Yes | Built from case data |
| All options visible at step 4 (G4) | 5.4 | Yes | Including withheld routes |
| Asset Intelligence updates step by step (G5) | 5.5, H4 | Yes | Collapsed, not hidden, from step 1 |
| Value against the Work Order or Sales Order (G6) | 5.5, 5.6, H5 | Yes | No intake work order (H5) |
| Learning by line item (G7) | 5.7, H7, H8 | Yes | Deterministic; replaces the random actual |
| We send, they decide execution (G8) | 5.6, rule in 8 | Yes | Already the wording; references added |
| Problems surface in Exceptions (G9) | 5.1 callout | Yes | No change to the Exceptions logic |

**Changed from the first-draft notes:** line numbers replaced by function names; no invented references (WO-91240, WO-94001) or buttons (*Simulate ERP Outcome*); handoff row 3 is the WMS transfer, not QMS certification; $3,200 is *Recover parts*, not harvest; "15 units" means units returned, not stock; steps 7 and 8 stay separate; the PO's $2,500/$1,800 and $70/$110 are an illustration, and the demo uses RT-1048's own cost lines; the "SVG text not visible" report was not reproduced, so PNG exports are added instead of a rewrite.

---

## Appendix A: The call, translated (2026-10-16)

Participants: the **Product Owner (PO)** and the **build lead**. Times are from the recording. The original lines were in Tamil and English; quotes below are the English translation.

**A. Steps 6–10, the ERP outcome and line-item learning (00:02–01:25)**
- **00:02, PO:** All the variations between predicted and actual get updated, and *they* (the enterprise systems) decide the final outcome; we don't.
- **00:09, build lead:** Right. We only send the instruction: the approved plan. We receive back the reference and the acknowledgements.
- **00:18, PO:** When that information comes back, say we recommended $2,500 and they sold for $1,800, $700 less, we record it for learning. Learning won't stop at the difference; it will see *where* the difference came from. We estimated $70 for the repair; they spent $110. We must record all of that.
- **00:55, PO:** There are steps 1 to 5, and if there is a problem in them, it shows in the Exceptions dashboard. Asset Intelligence is also updated only step by step. It is not populated at the start with the price and commercial value; that updates only after the steps are done.

**B. The 1–10 sequence and order binding (01:26–03:40)**
- **01:27, build lead:** Step 1: data comes in, for example a Voltara V4 motor from Customer A at Warehouse 1, with raw data from EAM and other sources.
- **01:47, build lead:** Steps 2 and 3: asset information, eligible treatments, gates and remaining useful life in Asset Intelligence.
- **02:06, build lead:** Step 4: building the plan: which outcomes are possible, why one is recommended, which alternatives exist.
- **02:28, PO:** All those options must be visible at step 4. Even if we recommend Redeploy, refurbish, resale, harvest, whatever it is, it is there.
- **02:41, both:** Step 5 approval (approve, override, decline); step 6 send the approved instruction to ERP, EAM and WMS; steps 7–9 wait for their updates; step 10 reconcile the actuals and use them for learning.
- **03:06, PO:** Only then, against that Work Order number in Asset Intelligence, is the commercial value updated: "predicted price so much, actual realisation so much". That is tied to one Work Order, which becomes another work order in the enterprise application; or, for Redeploy, a Sales Order to a particular customer.

**C. The diagram sequence and guidance (03:41–06:45)**
- **03:41, PO:** We need to correct the sequence. We must not land on Exceptions. Exceptions is only a dashboard for the Executive or Planners. When a person signs in, they see which assets have been returned, take one, and we show its journey.
- **04:13, build lead:** I started *1. Supply evidence* at the fourth box instead of the first. Reordering fixes it.
- **04:29, PO:** It should guide you intelligently in each scenario: after seeing this, where do I go next, and what should I know next? Once the asset arrives, we pull its condition, remaining useful life, inventory, pending orders outside, whether it can be re-leased; then we decide the best next path.
- **05:27–06:40, both:** The build lead showed the sign-in page and said clicking steps 1 to 9 under Product → Decision Workbench takes the user through the matching screens. The PO agreed.
- **07:03–08:08:** The stakeholder meeting moved to Monday or Tuesday next week; in-person review with the PO on Monday morning.
