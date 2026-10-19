# Plan: demo refactor, iteration three (Command Center by section, simpler Product menu, Asset Intelligence restructure, redeploy and cost wording, edge cases, signals, region settings)

**Purpose of this file:** a self-contained brief. It does not assume any earlier conversation. Read it top to bottom, then start at **Phase 0**.

**Status:** built on `feature/demo-refactor` (2026-10-19), not pushed. Every section 4 decision is on its default and marked **(assumed)** until the Product Owner confirms it (section 10). `CHANGES.md` Update 11 is the reviewer walk-through.

**Source:** two inputs from 19 Oct 2026. (1) The build lead's notes after the Product Owner's review of the Command Center and Asset Intelligence. (2) The recorded *Circularity Deck Finalization* call (00:00–24:00, Tamil and English) and its to-do list. Participants are referred to by role: the **Product Owner (PO)**, the **build lead**, and the **senior stakeholder** who reviews the demo.

**Builds on:** `docs/feature-demo-refractor-iter-two.md` (journey strip, guide, all pathways, value states, line-item learning; `CHANGES.md` Update 10), which builds on `docs/PLAN_DEMO_SIGNIN_SINGLE_ASSET.md`, `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` and `docs/PLAN_RBAC_ADAPTIVE_UI.md`.

**Dates (from the call):** demo video recorded with an AI voiceover by **20–21 Oct**; presentation **22 Oct**; backend majority by **31 Oct**; trial run ready by **15 Nov**.

> **Compliance note.** This iteration changes wording about redeployment under customer contracts, who certifies equipment (the enterprise EAM or quality system, not Circularity), where costs come from, and what the Command Center figures mean. Per Kinective policy, that wording should be reviewed by Kinective's Legal team before it is relied on or used with clients. The demo stays synthetic: no real names, emails or customer data. Prospect company names from the call are not put into the app.

---

## 1. The feedback to solve

### 1.1 From the build lead's notes (PO review)

| # | Ask | Today (checked in `index.html`) | Wanted |
|---|---|---|---|
| U1 | **Hide "Uplift vs baseline"** on the home screen, or suggest plain business wording; end stakeholders won't understand it | KPI tile `uplift` (*Uplift vs baseline +$652k*) on the Command Center for Finance, Executive and Admin; the Finance subtitle mentions uplift; Asset Intelligence's value card has *Uplift vs sell as-is or scrap* | Hidden behind a feature flag; plain alternatives proposed (section 4, J1) |
| U2 | **Command Center sections in the sidebar, not one long page** | `#/command` renders every section on one page (health strip, filters, KPIs, exceptions, actions on me, handed off, inbox, outcomes, charts, actions table, signals, value, integration health); sidebar entries only scroll | Each sidebar entry opens its own page (`#/command/<section>`); `#/command` opens the overview (key figures) |
| U3 | **Pool optimizer hidden, not removed**; nothing in the UI about it for now | Sidebar entry, `#/product/pools`, *Portfolio Optimization Mode* switch on Treatment Intelligence, *Pool optimizer* block in the full analysis, *Pool efficiency* in Analytics, *Optimise pool* stage in Process orchestration | One flag (`FEAT.pools=false`) hides every UI trace; the code and data stay |
| U4 | **Asset intelligence at the top** of the Product (Decision Workbench) menu | Order: Returned assets, Expected returns, Pool optimizer, Asset intelligence | Order: Asset intelligence, Returned assets, Expected returns (Pool optimizer hidden) |
| U5 | **Asset Intelligence: tab list instead of the left/right split; retrieved first, then predictions, separated** | A horizontal tab bar (Overview … Related Assets, Compare similar assets); the Overview puts *What we know* and *What we predict* side by side | The tab list becomes the page's left-hand section menu (Overview, Lifecycle, Condition, Product & Components, Economic Analysis, Eligibility & Compliance, Data & Evidence, Related Assets (n), Compare similar assets). The Overview shows **Retrieved from enterprise systems** first, full width, and **Predicted by Circularity** below it, as a separate section |

### 1.2 From the recorded call (19 Oct)

| # | Ask (call time) | Today | Wanted |
|---|---|---|---|
| T1 | **Flow diagram: the extra top-row box is confusing** (10:09–10:26). The PO asked "what is *End user*?"; the build lead agreed to remove the Exceptions box | `docs/demo/user-flow.svg` top row: Sign in, Returned assets (*END USER · PLANNER*) and the dashed Exceptions box | Top row: Sign in → Returned assets, labelled **Planner**; no Exceptions box. PNG re-exported and ready to send |
| T2 | **Redeploy is to the customer, under a contract, not a new order** (13:55–14:38, 17:23–17:58) | RT-1048: *Site 3 · confirmed internal need*, *Prepare and redeploy RT-1048 to Site 3*, *pending order SO-48102 at Site 3* | Redeploy **to Customer A** (Site 3) **against a contract replacement or extension** that **accepts a certified refurbished unit**; a demand line that requires a **new unit cannot be served**; the certified life must cover the contract need |
| T3 | **"How do you get the cost?"** (11:36–12:35): product value from the catalogue (PLM/ERP), the **RMA** from Order Management, receipt in WMS, repair scope from EAM diagnostics, **part prices from supplier contracts** (procurement) | Asset header has *Received under GR-…*; cost sources are one line, *EAM + workshop + logistics* | A retrieved **Cost inputs** card naming each source and value, an **RMA** reference in the header, and the predicted preparation cost shown as contracted parts + modelled labour and transfer |
| T4 | **Edge cases in the demo** (14:55–17:06, 18:49–19:27): a critical part fails and no replacement is available, so the life cannot be re-certified → **harvest parts**; the demand is for a **new unit** → cannot redeploy | What-if presets: demand cancelled, parts +30%, resale −20%, certification shorter than demand | Two more presets: **Critical part unavailable** (redeploy, re-lease and whole-unit sale withheld; recovering parts ranks first) and **Customer requires a new unit** (redeploy withheld), each with its reason |
| T5 | **Circularity does not certify equipment** (18:06–18:58): the diagnostic tool (EAM or quality system) certifies after part replacement; Circularity reads the certificate | Certified-period basis: *Certified by Engineering after grade B inspection* | *Certified in QMS by the EAM diagnostic and quality process after inspection and any part replacement; Circularity reads the certificate and does not certify equipment* |
| T6 | **Every item shows its status as signals accumulate** (02:11–03:08): not every signal is there when an item arrives; the economic path appears only when ready | Returned assets shows assessment and stage chips; *Best next action* is "—" when there is no route | A **Signals** column on every row: received (RMA, WMS) · diagnostics (EAM) · certification (QMS) · economic path, with *n of 4* and what it waits for |
| T7 | **Internationalisation: language, time zone, currency** (03:10–03:41) | Currency switch USD / local (₹) on Asset Intelligence's economic view only | A **Region** menu in the top bar: language (English; Japanese, German, French and Finnish as a *navigation preview*), time zone (shown on the *As of* pill and the Command Center clock), local currency (₹, ¥, €) used by the economic view |
| T8 | **The Command Center has to explain itself** (22:57–24:00): "what is this talking about?", "what is Value at risk?", "what is Uplift?" | Tooltips only | Each Command Center page says in one line what it shows; the overview has **What these figures mean** with a plain definition per figure. *Value at risk* explained; *Uplift* hidden (U1) |
| T9 | **Demo video: one happy path, then edge cases, and how easy integration is** (09:00–21:20); AI voiceover, standard demo, first two slides tailored per prospect | `docs/demo/DEMO_SCRIPT.md` (iteration two) | Script updated for the planner-first happy path, the edge cases, the cost question and an integration segment (Source map, manual CSV import); a new **voiceover script** for the AI narration |
| T10 | **Sign-in IDs stay** (22:39–22:57): `@northfield.example` is enough | — | No change |

**Not in scope (actions for people, not code):** tailoring the first two deck slides per prospect; telling the Reconcile module owner to drop the IEEPA refund use case and focus on normal customs invoice matching; sending the updated flow PNG to the PO; recording the video and voiceover; the backend that lets any Excel file power the system end to end (31 Oct). Numbers already shown elsewhere (128 live cases, 1,400 closed, every recommendation and every total) must not change.

---

## 2. Orientation: where the code is

Still **one file, `index.html`**, no build step. Search by name; line numbers drift.

| Area | Where |
|---|---|
| Feature flags | New `FEAT` next to `RB_SECS` |
| Sidebar | `NAV`, `navKids`, `navHTML`, `navSync`, `navActiveKey`, `ANCH` |
| Command Center | `renderCommand`, `CC_LAYOUT`, `ccKpiSet`, `ccExHTML`, `ccAomeHTML`, `ccHandedHTML`, `ccInboxHTML`, `ccOutcomesHTML`, `ACT.ccScroll`, `ACT.ccPick` |
| Pool optimizer | `poolsPage`, `poolBlock`, `ACT.tiMode`, `poolChart`, `OR_STAGES` (`opt`), `canPage` |
| Asset Intelligence | `/*ASSET-START*/ … /*ASSET-END*/`: `assetPage`, `assetTabs`, `asOverview`, `assetFacts`, `asKnownCert`, `asDemand`, `asEcon`, `asMoney` |
| Treatment Intelligence | `/*TI-START*/ … /*TI-END*/`: `TI_PRESETS`, `ACT.tiPreset`, `tiChanged`, `tiElig`, `tiPredicted`, `tiOutcome`, `tiHandoff`, `bestCard`; `scenRoutes`; `caseRul`, `caseDemand` |
| Returned assets | `queueTable`, `qRow` |
| RT-1048 | the seeded block `/* ---- RT-1048 · industrial motor · redeploy ---- */` |
| Top bar | `shell` |

---

## 3. Verification of the call notes

| Claim in the to-do list | Verdict | Finding |
|---|---|---|
| Line numbers (e.g. `JSTEPS` 715, `asDemand` 1110) | **Wrong** | The file is longer; search by name |
| `CASE_BY_ID['RT-1048']` has `demandLabel:'Site 3 · confirmed internal need'` | True | In the seeded block, not in `CASE_BY_ID` directly |
| "Internal demand tick box" in step 4 | True | *Confirmed internal demand is cancelled* (`scenDemand`) |
| Currency is converted on a "Local currency" tab | True | Asset Intelligence → Economic view, USD / ₹ only (`AS_FX = 83.5`) |
| A 5th preset should switch the top route to **intparts** for RT-1048 | **Only if whole-unit sale is also withheld** | With only redeploy and re-lease withheld, *Sell + buy* ($4,800) ranks above *Recover parts* ($3,200). A unit with a failed critical part cannot be sold whole as working, so the preset withholds the whole-unit sale too (J6) |
| Uplift +$652k = $1.80M vs $1.15M | Plausible | Same figure as Analytics; not changed, only hidden on the home screen |
| `@northfield.example` sign-in is enough | True | No change |

---

## 4. Decisions needed from the Product Owner

If there is no answer, build the default and mark it **(assumed)**.

| # | Question | Default |
|---|---|---|
| J1 | Hide *Uplift vs baseline*, or rename it? | **Hide** on the Command Center (flag `FEAT.uplift`), and the *Uplift vs sell as-is or scrap* line on Asset Intelligence. Plain alternatives to choose from: **Extra value recovered** (*$652k more than selling as-is or scrapping*), **Value recovered** (actual net, already shown as *Net recovery*), **New purchases avoided** (already shown as *Avoided spend*). Analytics keeps its waterfall unchanged |
| J2 | What does `#/command` open? | The **overview** (key figures, with definitions). Each other entry opens its own page; sections a role does not have are not listed |
| J3 | Keep *Returned assets* in the Product menu? | **Yes.** It is where the journey starts. Only Pool optimizer is hidden; Asset intelligence moves to the top. The *Product* heading still opens Returned assets |
| J4 | Asset Intelligence layout | The tab list becomes a **left section menu**; Overview stacks **Retrieved** above **Predicted**, each full width, cards two across. Phone: the menu becomes a scrollable row |
| J5 | Redeploy wording | *Redeploy RT-1048 to Customer A (Site 3)* against **contract replacement order SO-48102**, which **accepts a certified refurbished unit** for **24 months**; a new-only demand line is never matched |
| J6 | Critical part unavailable preset | Withholds redeploy, re-lease and whole-unit sale (*critical component failed; no replacement in supplier contracts, so EAM/QMS cannot re-certify its life*); RT-1048's top route becomes *Recover parts* |
| J7 | Languages | English plus a **navigation preview** in Japanese, German, French and Finnish (menu, journey step names, guide labels), marked *preview, not reviewed by a native speaker*. Full translation needs a string catalogue (backend phase) |
| J8 | Time zones and currency | UTC (default), India, Japan, Central Europe, Finland, US Eastern. Local currency ₹ (default, as today), ¥, €; rates are illustrative and named as such |
| J9 | Cost inputs | Catalogue value (the avoided purchase price where a route has one, else the class list price), RMA (Order Management), receipt (WMS), repair scope (EAM: components worn or due for replacement), contracted part prices (procurement). Predicted preparation = contracted parts + modelled labour and transfer, adding up to the route's preparation line |
| J10 | Signals on Returned assets | Four signals per row (received, diagnostics, certification, economic path) and the next one awaited |

---

## 5. Design

### 5.1 Feature flags (U1, U3)
`const FEAT={uplift:false,pools:false}`. `canPage` returns false for `product/pools` and `analytics/pool` while `FEAT.pools` is off, so the sidebar, routes, the *Portfolio Optimization Mode* switch and the Analytics section disappear together; `poolBlock` and the orchestration stage text check the flag too (*Optimise pool* reads *Optimise plan* while hidden). `FEAT.uplift` removes the `uplift` tile from every Command Center layout and the uplift line from Asset Intelligence. Turning a flag on restores the current behaviour.

### 5.2 Command Center by section (U2, T8)
`#/command/<key>` renders only that section: `kpis` (health strip, filters, insights, key figures and **What these figures mean**), `exceptions`, `aome`, `handed`, `approvals`, `outcomes`, `charts`, `actions`, `signals`, `value`, `health`. The header keeps the role chip and the Admin Operational/Senior switch, and one line says what the page shows. The sidebar and the sub-navigation list only the sections the role's layout has. KPI tiles that used to scroll to a section now open it; chart and KPI filters open the *Actions to prioritise* page when the role has it. `command` leaves `ANCH`, so each entry re-renders.

### 5.3 Product menu (U3, U4)
Product sections: Asset intelligence, Returned assets, Expected returns (Pool optimizer hidden). The *Product* heading still opens Returned assets.

### 5.4 Asset Intelligence (U5, T3, T5, T2)
- Left section menu with the eight tabs and *Compare similar assets*; *Evaluate treatments →* below it.
- Overview: section **Retrieved from enterprise systems** (journey step 1) then **Predicted by Circularity** (steps 2–3), stacked, each a two-column card grid; wide cards span both columns. Ids `#aszKnown`, `#aszPred` and all journey targets stay.
- New retrieved card **Cost inputs** (`#asCostCard`): catalogue value, RMA and receipt, repair scope from EAM, contracted part prices from procurement.
- Economic intelligence adds **How the preparation cost is built** (predicted): contracted parts + labour and transfer = the preparation line.
- Header: **Return authorisation RMA-… · Order Management**.
- Certified period basis per T5. Matched demand per T2 (customer, contract, accepts refurbished, certified life needed vs certified).

### 5.5 Redeploy wording (T2)
RT-1048's redeploy reads *Customer A · Site 3 contract replacement (accepts certified refurbished)*; its target is *Customer A · Site 3*; the decision card title *Redeploy RT-1048 to Customer A (Site 3)*; matched-demand lines on Treatment Intelligence, the instruction preview and the journey guide say *contract replacement order SO-48102*. Facts: the baseline is buying a new motor for Customer A. Route names, values and the order number do not change.

### 5.6 Edge cases (T4)
Presets `ecm` (*Critical part unavailable*) and `newonly` (*Customer requires a new unit*) in `TI_PRESETS`; `scenRoutes` withholds the affected routes and gives the reason, shown in the eligibility list, the what-if *changed from base* chips and the result sentence.

### 5.7 Signals on Returned assets (T6)
A **Signals** column: four segments with labels in the tooltip, *n of 4*, and the next signal awaited (*awaiting EAM diagnostics*, *awaiting QMS certification*, *economic path ready*).

### 5.8 Region menu (T7)
Top-bar menu: Language, Time zone, Local currency, saved per browser. Language translates the sidebar, sub-navigation, journey step names and guide labels; `<html lang>` follows. Time zone formats the *As of* pill and the Command Center clock. Currency drives Asset Intelligence's local-currency view.

### 5.9 Flow diagram (T1)
Top row: *PLANNER · Sign in* → *PLANNER · Returned assets*; the Exceptions box and its connector go; the value-state callout stays at the bottom.

### 5.10 Demo and voiceover scripts (T9)
`DEMO_SCRIPT.md`: planner first, happy path RT-1048, edge cases (critical part unavailable → recover parts; new unit required; certification shorter than demand), *How do you get the cost?* on Cost inputs, integration (Source map, Manual import with the sample CSV), Command Center sections last. New `docs/demo/VOICEOVER_SCRIPT.md`: scene-by-scene narration for the AI voice, about four minutes.

### 5.11 What stays the same
Sign-in, roles and scopes, the journey strip and guide, value states, references, line-item reconciliation, every seeded number and recommendation.

---

## 6. Data additions (synthetic, deterministic)
Derived at render time from `hashId`; no new `rnd()` calls.

| Field | Derived from |
|---|---|
| RMA | `RMA-` + 55800 + `asHex(c,'rma') % 900` |
| Contracted part price | component, case and class list price; parts subtotal ≈ 55% of the preparation line |
| Supplier contract | `SC-` + 7000 + `asHex(c,'sc') % 900` |
| Signals | evidence states, assessment, `caseRul`, recommendation |

---

## 7. Phases (each ends with tests and a screenshot)

0. **Baseline:** role 208, guided flow 110, demo 91, iteration two 50, 390 px 20.
1. **Flags and menus** (U1, U3, U4): `FEAT`, pool hiding, uplift hiding, Product order.
2. **Command Center by section** (U2, T8).
3. **Asset Intelligence restructure** (U5) with Cost inputs, RMA, certification and demand wording (T2, T3, T5).
4. **Redeploy wording and edge cases** (T2, T4).
5. **Signals column** (T6).
6. **Region menu** (T7).
7. **Diagram, scripts, docs** (T1, T9): `user-flow.svg/png/md`, `DEMO_SCRIPT.md`, `VOICEOVER_SCRIPT.md`, `CHANGES.md` Update 11, README, screenshots `iter3-*.webp`, section 10 here.

---

## 8. Project rules
As in the earlier plans: palette tokens only, prefixed class names (new: `cc` sections, `asside`, `sg` signals, `rg` region), `data-act` + `ACT` + `esc()`, hash routes for every state, container queries, 390/768/1280/1600 px, synthetic data only, plain English, `CHANGES.md` for every visible change, no push until asked. Additional: hidden features stay in the code behind `FEAT`; Circularity never claims to certify equipment or carry out the work.

---

## 9. Test plan
Run the five existing suites; change expectations only where this plan changes behaviour (Command Center sections, RT-1048 wording, uplift hidden, pools hidden) and record each in `CHANGES.md`. The role suite turns `FEAT.pools` on, so the hidden pool code stays covered. Add an iteration-three suite:
1. Flags: no *Uplift* tile on any Command Center; no pool entry, route, switch, block or Analytics section; flags on restore them.
2. Command Center: every sidebar entry opens its own page with only its section, for each role; `#/command` is the overview with definitions; KPI tiles open their section.
3. Product menu order; Returned assets still the journey start.
4. Asset Intelligence: left menu with the nine entries; Overview has retrieved before predicted, stacked; Cost inputs and RMA; certification wording; demand wording; every case renders with no `undefined`, `NaN` or `null`, and no route name or value on the retrieved side.
5. Edge cases: *Critical part unavailable* makes *Recover parts* first for RT-1048 with the reason; *Customer requires a new unit* withholds redeploy.
6. Signals: every row has four signals and a next step; counts match evidence.
7. Region: language changes the menu and `<html lang>`, time zone changes the *As of* pill, currency changes the local view; English restores everything.
8. Diagram: no Exceptions box; *Planner* labels; PNG exists.
9. Regression: invariants, 390 px on the new pages, dark mode, no console errors.

---

## 10. Product Owner decisions

| # | Answer | Where it lands |
|---|---|---|
| J1 | Pending (assumed: hide) | `FEAT.uplift=false`: `ccKeys` drops the tile; the Finance subtitle and the asset value card follow the flag |
| J2 | Pending (assumed: overview) | `renderCommand(r)`, `ccSec`, `ccSecOK`, `CC_DESC`, `ccDefsHTML`; `navKids` lists only the role's sections |
| J3 | Pending (assumed: keep Returned assets) | `NAV` Product order; the heading still links to Returned assets |
| J4 | Pending (assumed: left menu, stacked) | `assetTabs` (`.asside`), `.asbody2`, `.aszs`/`.asz` grid, `aszw` wide cards |
| J5 | Pending (assumed: customer contract wording) | RT-1048 seed (`demandLabel`, `target`, `why`, `facts`), `bestCard`, `tiPredicted`, `tiOutcome`, `tiHandoff`, `jgEst`, `asDemand`, `assetFacts` |
| J6 | Pending (assumed: withhold redeploy, re-lease, whole sale) | `SCEN_WHY`, `scenRoutes`, `TI_PRESETS` (`ecm`, `newonly`) |
| J7 | Pending (assumed: navigation preview) | `I18N_KEYS`, `I18N`, `tr`, `RG_CONT` |
| J8 | Pending (assumed: six zones, three currencies) | `RG_TZ`, `RG_CUR`, `rgAsOf`, `ccClockText`, `asMoney` |
| J9 | Pending (assumed: the listed inputs) | `asCostInputs`, `asCostBuild`, `asPartPrices`, `asRMA`, `asSC` |
| J10 | Pending (assumed: four signals) | `sigOf`, `sigHTML` in `qRow` |

---

## 11. Definition of done
- No *Uplift* on the home screen; plain alternatives proposed.
- Command Center: one section per page from the sidebar; the overview explains its figures.
- Pool optimizer invisible in the UI, still in the code behind a flag; Asset intelligence first in the Product menu.
- Asset Intelligence: left section menu; retrieved first, predictions below, separated; cost inputs and RMA; certification and redeploy wording as the call described.
- Two new edge-case presets; signals on every returned asset; a Region menu.
- Flow diagram without the Exceptions box; demo and voiceover scripts ready for the 20–21 Oct recording.
- All checks pass with no console errors; numbers unchanged; light, dark and 390 px correct. Committed, not pushed.
