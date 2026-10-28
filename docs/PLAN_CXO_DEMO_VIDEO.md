# Plan: the CXO demo video, end to end (DI landing → Recover → ten stages → Connection Fabric → Analytics → close), plus the MRO system role

**Purpose of this file.** It records what the current demo video misses (measured), what research says about demoing to senior executives, the UI work the new video needs, the MRO change from the product owner, the run of show and the recording pipeline. A fresh session can build the work from it. The narration draft is [`demo/VIDEO_SCRIPT_CXO.md`](demo/VIDEO_SCRIPT_CXO.md).

| | |
|---|---|
| **Status** | Built and recorded 28 Oct 2026 (section 14). D1, D2, D4, D6 answered by the user; D3 decided on SME grounds; D5, D7, D8 assumed |
| **Source** | User, 28 Oct 2026: the existing demo misses assets and has too much scrolling. Regenerate end to end: start on the DI landing page (three modules, ≤ 10 s); sign in to Circularity (admin); open a returned asset (details and photo, RT-1048 motor); stages 1–10 with prediction explainability, the evidence snapshot at the side and what-if sliders; Connection Fabric (Overview, Workflow Studio, Source Map, Source Tables, Canonical Models) with an agent drafting a workflow from chat and the canvas changing; Analytics predicted vs actual with the agent beside it; close on industry-agnostic, plug and play, no rip and replace. 5–6 minutes, at most one scroll per screen, calm senior-expert business language, agentic without bragging. **PO, same day:** repair, refurbishment and the workshop are run by an **MRO** application, not by ERP or OMS; ERP and OMS handle the redeploy and resale orders |
| **Builds on** | `PLAN_DECISION_WORKBENCH_STAGE_PAGES.md` (stage pages, PR #18), `PLAN_SIDEBAR_AND_CONNECTION_FABRIC_REVAMP.md` (Fabric, workflow canvas, PR #16/#17), `PLAN_LIVE_RUN_AND_LIVE_UI.md` (run board), `docs/demo/video/HANDOFF.md` (the 4:11 video and its pipeline) |
| **Branch** | `feature/cxo-demo`, cut from `fix/home-tabs-scrollbar` (dfe79bc) so the Home tabs fix is included; rebase onto `main` once PR #19 merges |
| **Legal** | The narration makes governance, audit and human-oversight claims and the screens show vendor product names and "Live" labels on synthetic data. **Kinective's Legal team should review the script and the final video before anyone outside the team sees it.** All data is synthetic; no real customer or member data may appear |

---

## 1. The asks

| ID | The ask |
|---|---|
| V1 | **Open on the DI landing page** (`framework/index.html`): Recover, Resolve, Reconcile in **≤ 10 s**, then click into Recover |
| V2 | **Sign in** to core Circularity (`index.html`) as **admin**, one role for the whole video if possible |
| V3 | **Returned assets → one asset**: details, the motor photo (RT-1048, Voltara V4, `assets/products/motor.webp`) |
| V4 | **Stages 1 to 10**, evidence to learning, in business terms, with the agents shown doing the work |
| V5 | At the **prediction**: why this outcome, **evidence snapshot at the side**, **what-if sliders** moved on camera |
| V6 | **No scrolling, at most one scroll** per screen |
| V7 | **Connection Fabric**: Overview, Workflow Studio, Source Map, Source Tables, Canonical Models. Plug and play, not rip and replace; editable by hand but built for agents, and what we see was built by agents |
| V8 | **Agentic Fabric moment** (20–30 s): ask for a workflow in chat → it is generated → open it and **see the canvas change** → configure it by asking |
| V9 | **Analytics before the close**: predicted vs actual graph, with the agent assisting at the side |
| V10 | **Close**: industry agnostic, not rip and replace, plug and play on top of any application, assisted by DI Platform agents |
| V11 | **5–6 minutes** total |
| V12 | **Language**: a 40-year subject-matter expert talking to CXOs aged 50+. Calm, plain business terms, professional, agentic without bragging, no tech talk |
| V13 | **MRO** (PO): repair, refurbishment and the workshop belong to an MRO application. Update the app (`index.html`) and the flow docs |
| V14 | **Script before video**, researched; a plan in the repo's style; questions asked |

## 2. Today, measured (28 Oct 2026, admin, RT-1048, 1440 × 900, Playwright + Chrome)

Harness: `survey.py`, `probe2.py`, `probe3.py`, `probe4.py` in the session scratchpad (section 9). "Screens" = page height ÷ 900 px.

| Screen | Route | Screens | Verdict for the video |
|---|---|---|---|
| DI landing | `framework/index.html` | 1.42 | Hero and three module cards fit the first screen. **Recover** links to `../index.html` (sign-in). OK |
| Sign-in | `index.html` | 1 | OK |
| Returned assets | `#/product/received` | 2.82 | First screen shows the KPI strip and RT-1048 *Start here*. OK without scrolling |
| Asset & Product Intelligence | `#/product/asset/RT-1048` | **3.87** | Hero (photo, identity, health ring) fits the first screen; the rest needs scrolling. Shows **"IBM Sterling OMS"** on screen. OK if we stay on the hero |
| Case overview | `#/product/RT-1048/overview` | 1.41 | Stage map with photo. OK |
| Stages 1–5, 7–10 | `#/product/RT-1048/stage/n` | 1.17–1.70 | Each leads with *What happened / What it means / What you do now* on the first screen. OK |
| Stage 6 Decide | `…/stage/6` | **2.79** | Has the tabs *Why this outcome, Evidence, What-if and edge cases, How it was predicted…*; with a tab open, 1.6–2.8 screens. **Why, evidence and what-if are never on one screen together** (gap G3) |
| Full analysis | `…/full` | **10.87** | What-if sliders (4 sliders, *Demand cancelled* and 5 more presets) at 5.8 screens down. Not for the video |
| Fabric Overview | `#/integration/overview` | **3.77** | First screen: 20 connected, 4 need attention, 15 available, category chips. OK without scrolling |
| Workflow Studio | `#/integration/studio` | 2.97 | First screen: 35 workflows, list. OK |
| Source Map | `#/integration/map` | 1.44 | Graph of 21 systems → 7 canonical models → decisions, with inner scroll. OK |
| Source Tables | `#/integration/tables` | 1.32 | Table graph (raw SAP table names: MARA, VBAK…). OK for 3–4 s |
| Canonical Models | `#/integration/models` | 1.75 | Seven versioned models, *Fed by EAM · PLM · WMS · CRM*. OK |
| Workflow canvas | `#/integration/studio/WF-…` | 2.09 | Canvas, details, *Assist* button. OK |
| Analytics | `#/analytics/predicted` | **3.63** | The deep link **lands at the top** (waterfall); *Predicted vs actual* sits 1.6 screens down (gap G6) |

**Interactions tested**

| Interaction | Result |
|---|---|
| Admin approves on stage 7 | Works: *Approve Redeploy RT-1048* opens the approval card with the agent-drafted rationale and the override routes. The status chip still says *Waiting on Planner* (G4) |
| Ask → *Draft a workflow that ingests repair results from the MRO workshop system…* | Works: the agent drafts 9 steps (*Repair management fields*, *Condition & eligibility*, *Evidence snapshot*, error handler, audit log…), checks them (0 errors), *Accept all as a new draft* creates WF-136. **The canvas does not open after Accept**; it stays on the list with a toast (G5) |
| Open WF-136 | Canvas renders the draft, *AI draft* badge, tags *EAM · Repair*. It mapped "MRO workshop" to the **Fixably** source because there is no MRO system (G1) |
| Ask on the canvas: *Change the trigger to every 5 minutes and add a step that flags units failing the bench test* | **"I can't do that yet."** The agent cannot edit a workflow from chat (G5) |
| Seeded state | RT-1048 starts at **stage 7, awaiting approval**. Stages 8–10 are *Not reached* until the video approves and the run moves on (G7) |

**MRO today.** `MRO` appears **0 times** in `index.html`. Repair and refurbishment are owned by **EAM (IBM Maximo)**: the stage list says *"EAM repair work order"*, handoff rows say *"Refurbishment work order … repaired, tested and certified"* with *"…plans the work order and its operations in Maximo"*, the run board sends the work order via `lrVendor('eam')`, the returned-assets list says *"awaiting EAM"*, and `docs/demo/user-flow.svg` says *"EAM: refurbishment work order"*. About 24 work-order mentions and 87 *repair* mentions need checking.

**The old video pipeline is broken for this UI.** `docs/demo/video/pipeline/record.py` targets the pre–stage-pages UI (`details.asmenu`, *Open decision analysis*, one-page Treatment Intelligence, `#/product/asset` scrolls). It must be rewritten, not patched.

## 3. What research says (deep research run, 28 Oct 2026; 21 sources, 25 claims verified 3-vote, 16 confirmed, 9 refuted)

| # | Finding | Confidence | Sources | What we do with it |
|---|---|---|---|---|
| R1 | **Lead with the business outcome**, then **Tell-Show-Tell**: context before any software, one idea per Show, close by restating benefits for every stakeholder | medium | [Presales Collective](https://www.presalescollective.com/content/the-1-most-important-foundational-demo-technique-on-the-planet-tell-show-tell), [PresalesPulse](https://presalespulse-com.pages.dev/glossary/executive-demo/) (Cohan, *Great Demo!*: "do the last thing first") | Landing page = opening Tell; each stage = one Show; the close names the CFO (value), COO (workshop and flow) and CIO (no replacement) |
| R2 | "Beyond five minutes on one topic you are piling on features" | medium | Presales Collective | No scene longer than 60 s; Decide (the longest) is split into why → evidence → what-if |
| R3 | Executives distrust autonomous agents: **trust in fully autonomous agents fell from 43% to 27%** in a year; most value comes with humans in the loop | high | [Capgemini, 2025](https://www.capgemini.com/news/press-releases/trust-and-human-ai-collaboration-set-to-define-the-next-era-of-agentic-ai-unlocking-450-billion-opportunity-by-2028/) | Frame agents as supervised colleagues: **"the agents do the groundwork; your people make the call."** Never say "autonomous", "revolutionary", "magic" |
| R4 | **Over 40% of agentic AI projects will be cancelled by end-2027** (cost, unclear value, weak risk controls); "agent washing", with only about 130 vendors genuinely agentic | high | [Gartner, June 2025](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027) | Show agents **doing real work with evidence** (pricing routes, drafting the workflow, mapping sources), not talking about agents. Name value and controls first |
| R5 | Credibility = an **audit trail**: what the agent saw, what it recommended, what it did, who reviewed it; say where autonomy ends | medium | [Publicis Sapient](https://knowledge.publicissapient.com/12/google-cloud-agenticai-discovery-workshop-jepj.html) | Stage 6: why + evidence + what-if on one screen (G3). Stage 7: a person approves; "nothing leaves until someone signs" |
| R6 | **"It does not replace your ERP… your systems stay the systems of record"** is the established wording | medium | [ReverseLogix](https://www.reverselogix.com/platform/integrations/) | Close and Fabric lines: "Your ERP keeps the orders, your MRO keeps the workshop, your order system keeps the shipments. We sit on top" |
| R7 | **System ownership**: ERP/OMS own the commercial return or repair order (RMA), shipping and invoicing; a **shop-floor / depot-repair application owns repair execution** (shop orders, serialized receipt, multi-step routings, several work orders per RMA) and reports completion back to ERP | high | [SAP ME repair flow](https://help.sap.com/saphelp_me60/helpdata/EN/ec/c06c79a47e4c6f925fa600d7ebff90/content.htm), [Oracle Depot Repair](https://docs.oracle.com/cd/E26401_01/doc.122/e48963/T349819T349822.htm), [Oracle Service Logistics](https://docs.oracle.com/en/cloud/saas/service-logistics/) | Confirms the PO: MRO owns inspection-to-certify in the workshop; ERP/OMS own the redeploy and resale orders (section 6) |

**Do not cite** (refuted 0-3): the IDC/Rimini Street figures on AI without ERP replacement (53%, 72.5%), the aviation-MRO "15–20 departments" claim. **Not verified by research**, used here as practitioner convention: narration at **130–145 words per minute**, one idea per scene, cursor ripple and gentle zoom, burned-in captions. Date any statistic used on screen ("a 2025 Capgemini survey"); the video itself should not quote statistics.

## 4. Target, at a glance (run of show, ≈ 5:30)

| # | Time | Scene | Screen and action | Scroll |
|---|---|---|---|---|
| 0 | 0:00–0:12 | **Opening Tell** | DI landing: hero, then cursor over Recover, Resolve, Reconcile cards → click Recover | 0 |
| 1 | 0:12–0:20 | Sign in | Sign-in (typing cut), caption *Admin* | 0 |
| 2 | 0:20–0:42 | Returned assets → RT-1048 | List (128 back, RT-1048 *Start here*) → asset hero: **photo enlarged** (G2), identity, health 75/100, grade B | 0 |
| 3 | 0:42–1:05 | Stages 1–5 (Arrive, evidence) | Overview stage map → stage 1, 4, 5 pages (5 *Photos* tab); stages 2–3 named in passing | 0 |
| 4 | 1:05–2:05 | **Stage 6 Decide** | Recommendation → **Explain view (G3)**: why on the left, **evidence snapshot pinned on the right**, **what-if sliders**: parts cost +30% (still wins), *Demand cancelled* (ranking flips) | 0 |
| 5 | 2:05–2:25 | Stage 7 Approve | Approval card with the agent-drafted rationale → approve | 0 |
| 6 | 2:25–2:55 | Stages 8–9 Execute, Outcome | Stage 8: ERP order, **MRO refurbishment work order**, WMS transfer, each acknowledged (G7); stage 9: outcome reported | 0 |
| 7 | 2:55–3:15 | Stage 10 Reconcile and learn | Predicted $9,600, actual $9,230, by cost line, each line naming the model that learns | 0 |
| 8 | 3:15–4:20 | **Connection Fabric** | Overview (3 s) → Source Map (5 s) → Source Tables + *✦ Suggest links* (5 s) → Canonical Models (4 s) → Ask "*draft a workflow…*" → Accept → **canvas builds node by node** (G5) → Ask "*every 5 minutes, flag failed bench tests*" → **canvas diff** → Accept | 0 |
| 9 | 4:20–4:50 | **Analytics** | Predicted vs actual scatter + model versions (error 17.7% → 12.5%) on one screen (G6); ✦ opens the agent beside the chart explaining what changed | 0 |
| 10 | 4:50–5:20 | **Closing Tell** | Close card (app palette): industry agnostic · plug and play · no rip and replace · agents do the groundwork, people decide | 0 |

Total narration ≈ 690–720 words at ≈ 140 wpm; the script is in [`demo/VIDEO_SCRIPT_CXO.md`](demo/VIDEO_SCRIPT_CXO.md).

## 5. UI gaps and what to build (in `index.html` unless noted)

All new code in a new block `/*CX-START*/…/*CX-END*/` and `/*CX-CSS-START*/…/*CX-CSS-END*/` after `ST-END`, wrapping existing functions, as the AF/FR/ST blocks do. Keep every existing id and `data-act` (tests and the recorder depend on them). `?cx=0` turns the block off.

| ID | Gap | Build | Size |
|---|---|---|---|
| **G1** | **No MRO system**; EAM/Maximo owns repair work | Section 6. Add an **MRO · workshop** system and category; move repair/refurbish/teardown work orders, bench test and certification release to it; keep EAM for the installed base, asset register and failure history | M |
| **G2** | Asset photo is small (≈ 180 px) on the hero | Click the photo → lightbox (photo plus inspection photos from stage 5 *Photos*), Esc closes. Recorder opens it for 3 s | S |
| **G3** | **Why, evidence and what-if are never on one screen** on stage 6 | Stage 6 tab **Explain** (first after *Decision packet*; deep link `…/stage/6?tab=explain`): left column = *Why this outcome* as 3–4 business drivers (avoided purchase, refurbishment cost, certified life vs demand term, market price) + the 4 what-if sliders and the presets *Parts cost +30%* and *Demand cancelled*, with the result card (base vs scenario, rank change); right rail (≈ 360 px, sticky) = **evidence snapshot** (each input: value, source system, record, fetched time) with the inputs a slider touches highlighted. Must fit 1440 × 900 with no page scroll. Reuse the existing slider handlers (`data-in="scen"`) and `tiPreset` logic; no new numbers | L |
| **G4** | Stage 7 says *Waiting on Planner* while admin can approve | When the viewer can approve, the chip reads *Ready for your approval*; keep *Waiting on Planner* for others. If D2 = planner→approver, nothing to change | S |
| **G5** | Accepting an agent workflow draft stays on the list; **the agent cannot edit a workflow** | (a) After *Accept all as a new draft*, open the new workflow's canvas and **reveal nodes and edges one at a time** (≈ 250 ms each, respects reduced motion). (b) New agent intent **`workflow.edit`** on a workflow page: parses "every N minutes" / "on event" (trigger) and "add a step that …" (inserts a validation/flag node before the error handler); shows the change as a **ghost diff on the canvas** (added node dashed yellow, changed trigger highlighted in *Workflow details*), checks it, *Apply* / *Discard*. Apply bumps the draft version (v0.1 → v0.2) and writes the audit log. Draft stays unpublished; a person publishes. (c) The drafting agent maps "MRO / workshop / repair" to the new MRO source (G1), not Fixably | L |
| **G6** | `#/analytics/predicted` lands on the waterfall | The deep link opens a **focused view**: *Predicted vs actual* and *Model versions* side by side on the first screen (the others below), and **✦** beside the chart opens the agent panel with a drafted explanation (within ±10% share, error by version, bias, where it over- and under-predicts, link to the cases). Generated from the existing analytics data | M |
| **G7** | RT-1048 starts at stage 7; stages 8–10 need acknowledgements and a Finance confirmation | Verify admin can move the run on from the stage pages (stage 8 *Check for the next acknowledgement*, stage 9 confirm outcome). If admin lacks the Finance permission, add **`?presenter=1` fast-forward** (a small *Advance* control visible only in presenter mode) rather than switching users on camera | M |
| **G8** | Vendor product names on screen (IBM Sterling OMS, SAP S/4HANA, Salesforce, Maximo…) | Per D4: either keep (Legal review) or a **`?generic=1`** label mode that shows the category (*Order management*, *ERP*, *CRM*, *EAM*, *MRO · workshop*) instead of the product. The narration never names a vendor either way | M (if chosen) |
| **G9** | `docs/demo/user-flow.md` and `user-flow.svg` use the old step names and EAM for repair | Re-draw for the app's ten stages (Lease ends … Reconcile and learn) with MRO in stages 5, 8 and 9 | S |
| **G10** | Recorder targets the old UI | New `docs/demo/video/pipeline/record_cxo.py` (section 7) | M |

**Not needed** (already good): stage pages 1–5 and 7–10 fit; Returned assets first screen; Fabric tabs fit without scrolling; landing page fits; the ✦ buttons on analytics charts exist; the Source Map *✦ Diagnose* and Source Tables *✦ Suggest links* exist.

## 6. The MRO change (V13, G1)

**Ownership after the change** (research R7; PO, 28 Oct):

| System | Owns | In RT-1048's journey |
|---|---|---|
| Lease management | The lease contract, end date, customer intent | Stage 1 |
| **OMS** (order management) | The return authorisation (RMA), shipping, the customer-facing return | Stages 2–3; resale shipment |
| WMS | Receipt, putaway, stock moves | Stage 4; stage 9 transfer to Site 3 |
| **MRO · workshop** (new) | **Inspection on receipt, teardown, repair and refurbishment work orders, bench test, certification release** | Stage 5 (grading, findings, photos); stage 8 refurbishment work order; stage 9 *repaired, tested, certified* |
| EAM | The installed base: asset register, failure history, criticality | Stage 1–5 evidence (history), canonical *Asset & component* |
| QMS | The certificate record | Stage 9 certificate updated |
| **ERP** | The redeploy (replacement) or resale sales order, parts reservation, actual costs, finance | Stage 8 SO-48102; stage 9 fulfilled, actual costs |

**Changes in `index.html`** (find by text; line numbers drift):

1. **Catalogue and sources**: add category `MRO` and a connected source *MRO · workshop* (generic name if D4 = generic; otherwise a neutral placeholder, never a real product without the PO's choice), with tables (work order, operation, test result, release), fields and a canonical mapping into *Intervention* and *Condition & eligibility*. Source Map shows it; *Fed by* lines on Canonical Models include MRO.
2. **Stages and handoff**: `AF_STAGES` / stage list *"EAM repair work order"* → *"MRO refurbishment work order"*; handoff rows *Refurbishment work order*, *Teardown work order* → system MRO; the *why* text *"…in Maximo"* → *"…in the MRO workshop system"*; the run board `lrVendor('eam')` for the work order → `lrVendor('mro')`; stage 7 *What it means* lists the MRO system among the instructions' targets.
3. **Inspection evidence**: stage 5 findings and grade *Retrieved · MRO*; returned-assets *"awaiting EAM"* → *"awaiting inspection (MRO)"*.
4. **Execution detail and cost trace**: labour and parts actuals for refurbishment come from MRO, posted to ERP finance.
5. **Workflows**: one seeded workflow *Ingest · MRO workshop* (work orders and test results, every 15 min) and one *Outbound · MRO* (on approval). Workflow counts update.
6. **Wording sweep**: every *work order* and *repair* mention reviewed; EAM stays where it means the asset register.
7. **DI landing** (`framework/index.html`): no system names today; add *MRO* to the foundation line only if the PO wants it (D5).
8. **Docs**: `docs/demo/user-flow.md`/`.svg` (G9), README system table, CHANGES *Update 19*.

## 7. Recording pipeline

Reuse `docs/demo/video/pipeline/` (Kokoro `am_michael`, speed 0.94, Playwright with the installed Chrome, 1440 × 900, cursor and ripple, cuts and role captions, `mux.py`). New files:

| File | What |
|---|---|
| `narration_cxo.json` | Lines `x0`…`x10b` from the script, with pronunciation spellings (*E R P*, *M R O*, *O M S*, amounts in words) |
| `record_cxo.py` | Scenes from section 4. Starts at `framework/index.html` (no title card), clicks **Recover** to reach sign-in. Each stage is reached by its own URL or the bottom-bar *Next*, never by scrolling; the one allowed scroll is a gentle glide on the stage 10 cost-line table if it does not fit |
| `card_close_cxo.html` | Close card: *Industry agnostic · Plug and play · No rip and replace · Agents do the groundwork, people decide*; adoption path *Shadow → One route → Closed loop → Portfolio* |
| `tts.py`, `mux.py` | Unchanged; `tts.py --src narration_cxo.json` |

Rules: one idea per scene; the cursor points at what the line names before it is said; a pause of 0.4–0.8 s after each number; no line overlaps the next; captions from the SRT.

**Verification of every take** (as in HANDOFF 7.1): no traceback; no overlapping lines; a frame at each line's start + 1 s and end − 0.4 s, tiled and checked (the screen shows what the line says: sliders moved while the what-if line plays, the canvas diff visible during the edit line, the scatter during the analytics line); **scroll count per scene ≤ 1** (the recorder logs every `scrollTo`/`glide`); duration 5:00–6:00.

## 8. Phases (each ends with tests, screenshots and a short report)

| Phase | Work | Done when |
|---|---|---|
| 0 | Answer section 10; confirm admin can move RT-1048 through stages 8–10 (G7); baseline the harness suites | Answers recorded; baseline green |
| 1 | **Script lock**: user approves `VIDEO_SCRIPT_CXO.md`; render the narration and measure durations | Total narration 4:45–5:20 |
| 2 | G1 + G9: MRO system, wording, docs | `mro.js` green; no *EAM … work order* left for repair |
| 3 | G3 Explain view on stage 6 | Fits 1440 × 900 without page scroll; sliders change the result and highlight evidence |
| 4 | G5 workflow canvas reveal + `workflow.edit` | Accept opens the canvas; the edit prompt shows a ghost diff; Apply bumps the version |
| 5 | G6 analytics focus, G2 lightbox, G4 chip, G7 presenter advance, G8 if chosen | Each screen of section 4 fits its scene |
| 6 | `record_cxo.py`, record, mux, verify frames | Video 5:00–6:00, every check in section 7 passes |
| 7 | Docs: CHANGES *Update 19*, README row, HANDOFF section for the CXO cut, screenshots; Legal-review note | User reviews the video |

## 9. Tests

Harness: the session scratchpad of 353d552e (`tools/all.sh`, `aft.py --w 1464 --h 999`) plus this session's probes (`C:\Users\ranilmj\AppData\Local\Temp\claude\C--repos-astra-prism-DI-ayush-ui-Circularity-ui\c9766b7b-e35b-47e0-9ba2-2a646934cf3e\scratchpad\survey.py`, `probe2.py`–`probe4.py`; Python with Playwright at `…\08dcd09d-…\scratchpad\venv\vid\Scripts\python.exe`).

| Suite | Checks |
|---|---|
| Existing (`live run exec smoke fabric video menus stages`) | Stay green; expectations that name EAM for the work order move to MRO, and each move is listed |
| `mro.js` (new) | MRO source in catalogue, Source Map and Canonical *Fed by*; stage 5, 8, 9 name MRO; run board sends the work order to MRO; no repair work order is attributed to EAM; `?cx=0` restores the old text |
| `cx.js` (new) | Stage 6 `?tab=explain` page height ≤ 900 px at 1440 × 900; evidence rail visible; moving *Preparation, parts and fees* to +30% keeps Redeploy first; *Demand cancelled* flips the rank and highlights the demand evidence; Accept opens `#/integration/studio/WF-…` and reveals all nodes; `workflow.edit` adds one node and changes the trigger, Apply → v0.2, audit entry; `#/analytics/predicted` shows the scatter in the first screen; ✦ opens the explanation |
| `survey.py` re-run | Every scene's screen ≤ 1 scroll |

## 10. Decisions (assumed until answered)

| ID | Question | Assumed |
|---|---|---|
| D1 ✔ app's stages | Which "ten steps": the **app's ten stages** (Lease ends … Reconcile and learn), which are what the viewer sees, or the older `user-flow.svg` steps (Supply evidence … Reconcile and learn)? | The app's stages; stages 1–3 together in one line, depth on 5, 6, 7, 10 |
| D2 ✔ Planner submits, Approver signs, Admin for Fabric | **Admin only**, or show the Planner submitting and an Approver signing (a cut and a caption, +8 s)? Separation of duties is a credibility point for CFOs | Admin only, narrated as "the approver signs"; the chip fix G4 |
| D3 ✔ MRO owns receiving inspection, teardown, repair/refurbish, bench test, release (motors and pumps); EAM keeps the asset register and failure history | MRO scope: does MRO also own **inspection and grading on receipt** (stage 5), or only repair/refurbish work orders and certification (stages 8–9)? | MRO owns inspection, repair, refurbish, bench test and release; EAM keeps the asset register and history |
| D4 ✔ keep real vendor names; MRO = Oracle Depot Repair | Vendor names on screen: keep the real product names and logos (Legal review), or a **generic label mode** for the video? | Generic mode for the video (G8), real names stay the default in the app |
| D5 | DI landing page: add MRO to its foundation wording? | No; it names no systems today |
| D6 ✔ close card, as in the last video | Close: a close card in the app palette, or end on the DI landing page? | Close card, then 2 s on the landing page |
| D7 | Voice: keep Kokoro `am_michael` (Apache 2.0, chosen before)? | Keep |
| D8 | Any customer or industry name to tailor to, or stay industry-neutral (Northfield Industrial Leasing, synthetic)? | Industry-neutral |

## 11. Definition of done

- A 5:00–6:00 video, 1440 × 900, with SRT, generated from the UI by `record_cxo.py`; every scene ≤ 1 scroll; frames checked.
- Every ask V1–V14 maps to a scene or a change (section 12).
- MRO owns the workshop work in the app and the docs; tests green.
- Script approved by the user before recording; Legal-review note in HANDOFF and on the PR.
- Nothing pushed or merged without the user asking.

## 12. Does the plan match the asks?

| Ask | Where |
|---|---|
| V1 landing ≤ 10 s | Scene 0, script x0 |
| V2 admin sign-in | Scene 1, D2 |
| V3 asset + photo | Scene 2, G2 |
| V4 stages 1–10 | Scenes 3–7, D1 |
| V5 why, evidence at side, sliders | Scene 4, G3 |
| V6 ≤ 1 scroll | Section 2 measurements, G3, G6, recorder rule, `survey.py` re-run |
| V7 Fabric tabs, plug and play, built by agents | Scene 8, R6 |
| V8 chat → workflow → canvas changes → configure by asking | Scene 8, G5 |
| V9 analytics predicted vs actual with agent | Scene 9, G6 |
| V10 close | Scene 10, D6 |
| V11 5–6 min | Section 4 (≈ 5:30), phase 1 timing gate |
| V12 language | Section 3 R1–R6, the script's style rules |
| V13 MRO | Section 6, G1, D3 |
| V14 script, plan, questions | `VIDEO_SCRIPT_CXO.md`, this file, section 10 |

## 13. Prompt for a fresh session

> Read `docs/PLAN_CXO_DEMO_VIDEO.md`, `docs/demo/VIDEO_SCRIPT_CXO.md` and `docs/demo/video/HANDOFF.md`. On branch `feature/cxo-demo`, build phases 2–7 in order. Put all code in the CX block of `index.html`, keep every existing id and `data-act`, and verify each phase at 1440 × 900 with the harness. Do not push or merge without asking.

## 14. Build report (28 Oct 2026)

**MRO (G1, G9 partly).** `Repair management` became **MRO and workshop** (short `MRO`), connected as **Oracle Depot Repair** (EBS 12.2.13), its own Connection Fabric category. Motors and pumps are graded by the MRO workshop at stage 5 (evidence and provenance trace to it); the refurbishment and teardown work orders, labour and machine hours go to it at stage 8; stage 8 systems are OMS · MRO · TMS · WMS · ERP finance; canonical *Fed by* lines and agent tool lists include MRO. EAM (IBM Maximo) keeps the asset register, failure history and service exposure. 44 exact-text edits (script in the session scratchpad, `tools/cx_mro.py`). `docs/demo/user-flow.*` not yet redrawn.

**CX block** (`/*CX-START*/…/*CX-END*/`, `/*CX-CSS-START*/…`, `?cx=0` turns it off; the MRO data edits are not behind the flag):
- G3 **Explain this decision** on stage 6: one 1440 × 900 screen with drivers in business words, next best and withheld routes, four what-if sliders and presets with the result card, and the evidence snapshot pinned right; moving an assumption lights the evidence it rests on.
- G5 Accepting an agent workflow draft opens its canvas full width and draws it step by step; new intent `workflow.edit` ("every five minutes, flag failed bench tests") lists the change, applies it to the canvas as v0.2 with the new step highlighted, never publishes. *Expand canvas* toggle on workflow pages.
- G6 `#/analytics/predicted` opens with the scatter and model versions first; new intent `analytics.accuracy` answers "What changed and why?" beside the chart from the model-version data.
- G2 product photo lightbox. Stage 9 gets the missing *Check for the next acknowledgement* button. Fixed "just now ago".
- G4 not needed (Planner submits, Approver approves). G7 solved by the stage 9 button; Finance confirms off camera. G8 not built (D4: keep vendor names).

**Video.** `docs/demo/video/circularity-cxo-demo.mp4` + `.srt` (5:15, 1440 × 900), from `pipeline/record_cxo.py`, `narration_cxo.json` (Kokoro `am_michael`), `card_close_cxo.html`; `tts.py`/`mux.py` take `--src narration_cxo.json`. Checked frame by frame at each line's start and end; no scroll in any scene; no overlapping lines. Not committed (size). Known: the app's live simulation raises the failing-workflow count over the take (7 failing on the Fabric screens).

### 14.1 Revision after review (28 Oct 2026, user and PO)

- **Landing:** Recover in our words; Resolve and Reconcile read as their cards on `framework/index.html` say (PO).
- **Agent as the subject:** every line says what our agent did (collected, predicted with ML models, drafted, set up, built the chart).
- **Agent panel on most pages:** asset summary (retrieved vs predicted), stage 5 and stage 10 **"what our agent did at this stage"** cards (new: `ACT.stAsk` override, `AF_CARDS.cxstage`, built from `stData`), the stage 6 Explain view, the approval rationale, the source-map diagnosis of the stale market feed, the 12 suggested table links, the workflow draft and change, the analytics answer.
- **Stages 1–3** each get their own short beat, then 4 and 5.
- **Run replay at 2×** on the run board after stage 10 (caption "Replay · 2× speed"; *Skip to now* when the line ends).
- **Connection Fabric:** about 10 s each for Overview, Source Map, Source Tables, Canonical Models and Workflow Studio. The Source Map gets **Expand map** (new, hides the duplicate system list), zooms out to the whole map, picks MRO and ERP to light their data paths, and scrolls the full graph.
- **ERP wording:** never "you don't need an ERP"; it is "we sit on top of your ERP, order management and MRO workshop".
- **Length:** 7:27, over the 5–6 minute target; cut options are in the session report.

## 15. Session record and open items (28 Oct 2026)

**In the repository (branch `feature/cxo-demo`):**
- `index.html`: the MRO edits and the CX block.
- `docs/PLAN_CXO_DEMO_VIDEO.md`: this file.
- `docs/demo/VIDEO_SCRIPT_CXO.md`: the script.
- `docs/demo/video/circularity-cxo-demo.mp4` and `.srt`: the video.
- `docs/demo/video/pipeline/`: `record_cxo.py`, `narration_cxo.json`, `durations_cxo.json`, `card_close_cxo.html`, `tts.py`/`mux.py` with `--src`, and `check/` (`frames.py`, `strip.py`, `flow.py`, `survey.py`).
- `docs/demo/video/HANDOFF.md` section 9: how to regenerate, take checks, gotchas, and every temporary path.
- `docs/screenshots/cx-*.webp`.
- CHANGES Update 19 and a README row.

**Outside the repository:** session scratchpad `C:\Users\ranilmj\AppData\Local\Temp\claude\C--repos-astra-prism-DI-ayush-ui-Circularity-ui\c9766b7b-e35b-47e0-9ba2-2a646934cf3e\scratchpad`. It holds the CX source (`cx/`), the patch and inject scripts (`tools/`), probes, screenshots, the UI review page and the regression log; HANDOFF section 9 lists each one. The deep-research run is `wf_acc2363f-521`; its findings are in section 3.

**Open items:**
- Length is 7:27, against the 5–6 minute target. Cut options were offered to the user: shorter module reading, drop the asset summary, merge stages 3–4, shorter Fabric lines, drop the stage 10 card, tighter pauses.
- Should Recover also be read from its card on the landing page?
- Should the replay come right after approval instead of after stage 10?
- `docs/demo/user-flow.md`/`.svg` still show EAM doing repair work; redraw them with the app's ten stages and MRO.
- G8 (generic vendor labels) was not built, because D4 says keep vendor names.
- The live simulation's failing-workflow count drifts during a take.
- Legal review of the video and script.

**Regression (28 Oct, final):** the headless harness passes 22 suites, **1,324 checks, 0 failures**. Five expectations moved from EAM to MRO wording: `iter2` ×2, `iter3` ×2, `exec` (originals in the harness scratchpad `orig_cx/`). Run `stages` at a true 1440 × 900 (`--w 1464 --h 999`); at the default 1416 × 801 window stages 3, 4 and 6 overflow by a few pixels, and they do so with `?cx=0` too.
