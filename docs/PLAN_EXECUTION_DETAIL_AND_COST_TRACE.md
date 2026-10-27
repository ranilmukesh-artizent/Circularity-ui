# Plan: execution detail and cost trace (where, how, who, which order, and where every cost comes from)

**Purpose of this file.** It records what the Product Owner asked for in the Treatment Intelligence review, the decisions taken, the design that answers each ask, and how the build was checked. A fresh session can rebuild or extend the work from it.

| | |
|---|---|
| **Status** | Built on branch `feature/execution-detail` (cut from `docs/di-framework`). Not committed, pushed or merged. |
| **Source** | Product Owner review of Treatment Intelligence for RT-1048 (*Redeploy · $9,600*), 27 Oct 2026; decisions K1–K8 from the same day |
| **Builds on** | `PLAN_LIVE_RUN_AND_LIVE_UI.md` (run board, live wording), `feature-demo-refractor-iter-two.md` (journey, value that builds), `feature-demo-refactor-iter-three.md` (cost wording), CHANGES Updates 10–15 |
| **Branch** | `feature/execution-detail` |

> **Legal review.** This work adds contract prices, labour and machine rates, carrier rates, time limits and escalation rules. All of them are invented for the demo (K9–K15 are assumed, not confirmed). Kinective's Legal team should review how they are presented before they are shown to clients or prospects, together with the notes in README section 13.

---

## 1. Feedback mapped

| ID | The ask | Where it is answered |
|---|---|---|
| N1 | Where to: customer site, warehouse, order number | 5.1, 5.3 |
| N2 | How, who, what action, in which app | 5.2 |
| N3 | Edge cases: not confident, or nobody acts | 5.5 |
| N4 | Which systems; orders move from ERP to OMS | 5.2, K1 |
| N5 | Real work order, transfer and order numbers | 5.2 |
| N6 | Outcome: which order, which customer, route, ETD and ETA | 5.3, 5.5 |
| N7 | Rationale for everything | 5.2, 5.4, 5.5 |
| N8 | Where and how every cost and value is picked up | 5.4 |
| N9 | Refurbishment: which parts, how they are priced; labour, machine, hours and units | 5.4 |
| N10 | Order number on the Predictions page | 5.1 |

## 2. Orientation (code by name; line numbers drift)

All new code sits in one block in `index.html`, just before the step plans: *Execution detail and cost trace*. Names: `LOCS`, `FAC_LOC`, `SITE_LOC`, `TENANT_SITES`, `laneKm`, `RATE_CARD`, `laneCost`, `EX_STEP`, `STEP_TPL`, `exKinds`, `exDocRef`, `workAdd`, `exClock`, `exSweep`, `stepOwner`, `exMove`, `exMoveRaw`, `EX_BOM`, `EX_LAB`, `EX_OPS`, `exPrepParts`, `exSvc`, `exTrace`, `exActual`, `exPlan`, `exWhatIf`, and the screen helpers `exMethod`, `exSrcBtn`, `exTraceHTML`, `exPlanHTML`, `exMoveHTML`, `exWhatIfHTML`, `exDelivered`. The drawer handlers `ACT.exSrc` and `ACT.exSrcAll` sit next to `ACT.advance`.

Changed in place: `stepsFor`, `hoKind`, `ackRef`, `ackNote`, `HANDOFF_MODEL`, `mkExec`, the seeded events, `jgDone`, `jgEst`, `jgWait`, `ackStep`, `adapter.acknowledge`, `afStageStates`, `afStageLines` (stages 3, 8, 9), `afPacketData` and `AF_CARDS.packet`, `instrPayload`, `tiHandoff`, `tiStatus`, `caseDemand`, `asPredRec`, `asDemand`, `asPartPrices`, `asCostInputs`, `asCostBuild`, `explainBlock`, `asTabEconomic`, `tiReconcile`, `afEvidencePack`, `aomeItems`, `afLease`, `SOURCES`, `SRC_TYPES`, `SRC_CFG`, `MAPPINGS`, `CANON_EX`, `OR_STAGES`.

## 3. What the code did before

- `afPacketData` computed the matched order (SO-48102) but the packet never showed it. *After approval* was a list of label and system.
- Orders were labelled *ERP · Order Management*; there was no order management source.
- `stepsFor` hard-coded four steps (reserve, prepare, transfer, confirm). Document numbers appeared only on acknowledgement, and event names followed the step's position, so the order step emitted `stock.reserved`.
- `c.location` was "Warehouse 1". There were no codes, bins, distances, lanes or outbound move.
- One demand had four unlinked identifiers: SO-48102, PO-49048, DEM-9902 and an OPP- record.
- Part prices were 55% of preparation split by a hash; *Labour and transfer* was the remainder. Freight was computed twice and disagreed.
- Low confidence and missed approvals changed text only. Nothing acted on time.

## 4. Decisions

| # | Decision | State |
|---|---|---|
| K1 | Orders live in **IBM Sterling OMS** (new source). SAP S/4HANA keeps **finance only** (actual cost posting). | Decided |
| K2 | Keep RT-1048's figures ($9,600, P10–P90 $8,371–$10,608, preparation $1,800, actual $9,230). The breakdowns add up to them exactly. | Decided |
| K3 | **Enforce time-limit escalation only**: each step has an owner and a limit; a breach escalates to the Approver, then Admin. Low confidence, expiry and fallback get *What happens if* guidance, not enforcement. | Decided |
| K4 | **All 128 cases** get generated, deterministic detail; RT-1048 is hand-tuned. | Decided |
| K5 | Warehouse 1 = Pune `WH-PNQ-01`, Warehouse 2 = Chennai `WH-MAA-02`, Repair centre = Hosur `RC-HSR-01`; sites get location codes (Site 3 Chennai Foundry = `LOC-CHN-03`); staging is the warehouse nearest the ship-to. | Decided |
| K6 | Source in INR, decide in USD at ₹83.5 (`RG_CUR`). | Decided |
| K7 | Transport is a step in **ShipLane TMS**; the carrier bill appears in Reconcile. | Decided |
| K8 | Plan document first. | Superseded: the build was asked for on 27 Oct |
| K9 | Owner roles per step (table in 5.2) | Assumed |
| K10 | Time limits: 4 working hours for OMS, EAM and TMS, 2 for WMS, 2 working days for finance; working hours are Mon–Sat 08:00–18:00 | Assumed |
| K11 | Site 3 receives **Tue/Thu/Sat 08:00–12:00** (the review example said Mon/Wed/Fri, but 13 Oct 2026 is a Tuesday) | Assumed |
| K12 | The motor bill of materials and the other class BOMs | Assumed |
| K13 | INR rates: labour ₹850/h (motors, pumps), ₹950 (controls), ₹520 (bench); field labour ₹1,100/h; lane rate ₹20/km + ₹1,200 loading, minimum ₹3,600 | Assumed |
| K14 | A refurbished unit is certified in QMS by the Maximo work order before it leaves the Repair centre (no separate step) | Assumed |
| K15 | Northline 3PL carries the outbound legs | Assumed |

## 5. Design

### 5.1 One demand, one set of identifiers (N1, N5, N10)

`caseDemand` now returns `line`, `shipTo`, `needBy`, `avoidedPo` and `oms`. For RT-1048: **SO-48102 line 10** in IBM Sterling OMS, Customer A, ship-to `LOC-CHN-03` (Chennai Foundry, Site 3), need-by **17 Oct 2026** (Day 10), avoiding planned **PO-49048** (SAP Ariba, ₹10,02,000 = $12,000). `CANON_EX` uses `SO-48102-10` instead of DEM-9902.

The order and line show in the decision packet (*Against SO-48102 line 10 · Customer A · Chennai Foundry (Site 3) · need-by 17 Oct 2026 · replaces planned PO-49048*), the Predictions page value header (`#asOrderLine`), the matched-demand card, the handoff *Destination* row and the instruction payload (`orderLine`, `shipTo`, `needBy`, `avoidedPurchase`, `sourceLocation`, `stagingWarehouse`, `etd`, `eta`, `legs`, `steps`).

### 5.2 Execution plan per route (N2, N4, N5, K3)

`STEP_TPL` lists step kinds per route; `stepsFor` builds as many steps as the route has. A step's identity, document type and event come from its kind, never its position. RT-1048:

| # | Action | System | Document | Owner (role) | Time limit |
|---|---|---|---|---|---|
| 1 | Allocate to the order line; cancel the planned purchase | IBM Sterling OMS | SO-48102 line 10 · PO-49048 cancelled | Customer operations · order desk | 4 working h |
| 2 | Refurbishment work order | IBM Maximo · RC-HSR-01 | WO-47349 | Repair centre lead (Engineer) | 4 working h |
| 3 | Book transport, 3 legs | ShipLane TMS | LD-47388 | Transport planner | 4 working h |
| 4 | Warehouse moves and outbound delivery | Manhattan Active WM | TR-47362 · OBD-47363 | Warehouse Manager · Warehouse 1 | 2 working h |
| 5 | Delivery confirmed | IBM Sterling OMS | FUL-47375 | Customer operations | on delivery |
| 6 | Actual costs posted | SAP S/4HANA finance | FI-47401 | Finance | 2 working days |

Other routes: **resale** reserve (WM) → sale order (OMS) → shipment (TMS) → shipped and invoiced (OMS) → receipts (ERP), with a Maximo work order added for the refurbish variant; **re-lease** Maximo → TMS → WM putaway → Oracle Lease contract → finance; **internal parts** Maximo teardown → WM putaway → stock transfer → finance; **external parts**, **material**, **exit** and **hold** keep their four steps.

Planned numbers show before acknowledgement (*to be created*); the acknowledgement confirms the same number, so WO-47349, TR-47362 and FUL-47375 are unchanged. Events follow the kind: `order.allocated`, `workorder.created`, `load.booked`, `movement.confirmed`, `delivery.confirmed`, `outcome.reported` and so on. `ACK_NOTE` is replaced by a note on every kind.

### 5.3 Route, ETD and ETA, and staging (N1, N6, K5, K7)

`LOCS` holds three facilities, eight customer sites, two buyer hubs and the recycler, with coordinates and receiving days and hours. `laneKm` uses measured road distances where pinned and straight line × 1.25 elsewhere. Rate card **RC-2026.2** (ShipLane TMS, Northline 3PL): dedicated LCV ₹20/km + ₹1,200 loading, minimum ₹3,600; part load by weight band. The staging rule picks the warehouse nearest the ship-to, or delivers direct from the Repair centre when that is nearer.

RT-1048 (*why: WH-MAA-02 is 34 km from LOC-CHN-03; WH-PNQ-01 is 1,180 km; meets the site's Tue/Thu/Sat 08:00–12:00 window*):

| Day | Date | Event |
|---|---|---|
| 0 | 7 Oct | Approved |
| 1 | 8 Oct 08:00 | ETD WH-PNQ-01 → RC-HSR-01, 930 km, ₹19,800 |
| 2 | 9 Oct 08:54 | Arrives at the Repair centre |
| 4 | 11 Oct 18:00 | Refurbished and certified (22 labour hours) |
| 5 | 12 Oct 08:00 → 12:42 | RC-HSR-01 → WH-MAA-02, 260 km, ₹6,400 |
| 6 | 13 Oct 08:00 → 08:36 | WH-MAA-02 → LOC-CHN-03, 34 km, ₹3,600 (minimum); 4 days of slack against Day 10 |

**Change from the review draft:** the Hosur–Chennai leg is **260 km**, not 160 km. 260 km is the road distance, and it is what makes ₹6,400 follow the same rate card as the other legs.

Reconcile shows the move as pre-bill **INV-NL-11902**: three linehaul lines checked against RC-2026.2 ($237.13 + $76.65 + $43.11 = $356.89 = ₹29,800), with no fuel surcharge because LCV lanes are all-in.

### 5.4 A cost line behind every term (N8, N9, K2, K6)

`exTrace(case, route, term)` returns lines, each with a **method** (Retrieved, Contracted or Modelled), a **source** (system and record), a **calculation** in ₹ and a **why**; the lines add up exactly to the term at ₹83.5. One drawer, *Where this number comes from*, opens from the packet, *What influenced this decision*, *How the recommended net is built*, the preparation build and Reconcile and learn.

RT-1048, pinned:

- **Avoided purchase $12,000** = ₹10,02,000: new Voltara V4 at the SAP Ariba contract price, planned PO-49048.
- **Preparation and transfer $1,800** = ₹1,50,300:
  - parts ₹83,500 ($1,000): bearing 6316-2Z/C3 ₹13,400, bearing 6314-2Z/C3 ₹11,600, seal kit 2 × ₹1,850, cooling fan and cowl ₹14,200, terminal block and gasket ₹9,600, PT100 sensor 3 × ₹4,800, varnish and consumables ₹16,600;
  - labour ₹18,700 (22 h × ₹850, solved last); machine ₹9,800 (bake oven 8 h × ₹350, balancing 1 h × ₹1,600, load test 3 h × ₹1,400, surge and insulation 1 h × ₹1,200); transport ₹29,800 (three legs); packing ₹8,500. Labour, machine and transfer = ₹66,800 ($800), the same split as before.
- **Service exposure $900** = ₹75,150 = 1.5 interventions over 30 months × ₹50,100 (call-out ₹6,500, field labour 12 h × ₹1,100, parts ₹22,900, downtime ₹7,500).
- **Residual +$300** = ₹25,050 from the resale-price model.
- **Actual preparation $2,070** = ₹1,72,845, explained: +6 labour hours (₹5,100), a shaft repair sleeve found at strip-down (₹9,930) and a waiting charge at LOC-CHN-03 from Reconcile (75 billable minutes at $72/h = $90 = ₹7,515). The actual net stays **$9,230**.

Generated cases use class BOMs, labour rates and standard hours, machine operations and packing, plus the lane rate card. Parts in scope are those whose component is not *Good*; parts are added or dropped to keep labour within half to twice its standard hours, and labour is solved last. Route nets, rankings and Analytics do not change.

**One deliberate change:** the inbound return's freight in `afLease` now comes off the same rate card (a return collection is a dedicated LCV), and *Fees and freight* splits into freight on that card plus the channel fee. Reconcile's 128 inbound bills use the same figures ($43–$369).

### 5.5 Edge cases and rationale (N3, N6, N7, K3)

- **Enforced:** a clock on the active step. Past its limit it escalates to the Approver; past a second limit, to Admin. Each escalation is one audit event (`handoff.escalated`), a line on the run board (stage 8), an item in *Needs you* and a chip in the plan. **RT-1009** is seeded: its Maximo work order has been with the Repair centre since noon on 6 Oct, so it escalated to the Approver at 16:00 and reaches Admin at 10:00 on 7 Oct.
- **Guidance, not enforced:** *What happens if* in the packet and the handoff: confidence is low (compare first), not approved by the expiry date (re-evaluated), the order line is cancelled (next eligible route, named with its value), a gate fails after approval (the existing exclusion).
- **Outcome reported** now says which order, which customer, the route and the ETD and ETA (delivery event, run stage 9, journey step 9, Reconcile and learn).
- Every new field carries a short why and its source; the evidence pack adds `execution_plan`, `move`, `cost_trace` and `what_happens_if`.

### 5.6 Also fixed

- Chennai Foundry is Customer A's (Site 3) in Reconcile and Resolve, as in Circularity. Customer A returns from Pune Works, Chennai Foundry, Hosur Assembly and Nashik Plant.
- The order step no longer emits `stock.reserved`.
- Every step kind has an acknowledgement note.
- *Check for acknowledgement* is no longer disabled after four steps.

**What stays the same:** route values, rankings, gates, approvals, roles, RT-1048's headline figures and Analytics totals.

## 6. Data rules

- Everything derives from the case at render. **No new `rnd()` calls**; the seeded data does not move.
- Invariant: for every term of every route of every case, `sum(lines ₹) === round(|term $| × 83.5)`.
- Invariant: every planned step has a system, an owner, a document and a time limit.
- Invariant: staging is the nearest facility, and every delivery lands in the site's receiving window.

## 7. Phases (as built)

| Phase | Content | State |
|---|---|---|
| 0 | Baseline: 16 suites, 945 checks green | — |
| 1–7 | Locations and lanes, OMS and TMS sources, one demand; variable-length plans with owners, limits and documents; transport legs and staging; cost lines and BOMs; trace drawer and *why*; escalation and *What happens if*; Reconcile pre-bill and framework alignment | Built, not committed |
| 8 | README, CHANGES Update 16, this file, screenshots | Built, not committed |

## 8. Rules followed

Plain English; Circularity recommends and sends approved instructions, and the enterprise systems do the work; no *simulated* or *demo* wording in the interface; roles, not names; `$9,600` and `−$370` money format; middle-dot system labels.

## 9. Tests

New suite `exec.js`, **46 checks**: every term adds up exactly (1,500+ terms); RT-1048 pinned values; every step has a system, owner, document and limit; the order and line in the packet, Predictions page and payload; the RT-1048 timeline and slack; staging and receiving windows for every redeploy; one rate card inbound and outbound; escalation to the Approver, then Admin, recorded once, on the run board and in *Needs you*; six acknowledgements confirming the planned numbers; event names by kind; the outcome naming order, customer, route, ETD and ETA; the actual explained line by line; no *ERP · Order Management* on screen; new tables inside scroll wrappers.

Six existing checks assumed four steps or the old labels and were updated (not weakened): `gf_run` (handoff names IBM Sterling OMS), `iter2` (`order.allocated`; LD, TR, FUL and FI references), `iter3` (*Labour, machine and transfer*; return authorisation from IBM Sterling OMS), `af1a` (five more acknowledgements close the six-step plan), `af2` (one *Next* per remaining step), `af5` (one system acknowledgement per planned step).

## 10. Product Owner decisions still open

K9–K15 in section 4 are assumed. Also open: whether the order desk, Repair centre lead and Transport planner become sign-in roles (today they are owners shown on the plan, not accounts), and whether escalations should notify by email or chat.

## 11. Definition of done

- [x] Every ask N1–N10 visible in the interface (table 13)
- [x] RT-1048 figures unchanged; every breakdown adds up exactly
- [x] All existing suites green; `exec.js` green
- [x] Screenshots retaken (`docs/screenshots/exec-*.webp`)
- [x] README and CHANGES updated
- [ ] Product Owner confirms K9–K15
- [ ] Legal review of the presented rates and rules

## 12. Prompt for a fresh session

> Read `docs/PLAN_EXECUTION_DETAIL_AND_COST_TRACE.md` and CHANGES Update 16. The code is the *Execution detail and cost trace* block in `index.html`. Keep RT-1048 at $9,600 and $9,230, add no `rnd()` calls, keep every cost line adding up exactly, and run the full suite plus `exec.js` before and after any change.

## 13. Does the build match the asks?

| Ask | Where to see it | Match |
|---|---|---|
| N1 Where to | Packet *Against …*, handoff *Destination* and *Route and timing* | Yes |
| N2 How, who, what action, which app | Packet *After approval* table; handoff instruction table | Yes |
| N3 Edge cases | *What happens if*; RT-1009 escalation | **Partly**: only the time limit is enforced (K3); low confidence and expiry are guidance |
| N4 Which systems, ERP to OMS | Target applications; Integration › Source map (IBM Sterling OMS, ShipLane TMS) | Yes |
| N5 Real reference numbers | Planned documents before acknowledgement; same numbers after | Yes |
| N6 Outcome: order, customer, route, ETD and ETA | Delivery event, run stage 9, journey step 9, Reconcile and learn | Yes |
| N7 Rationale for everything | A why on every step, leg, part, rate and hour; evidence pack | Yes |
| N8 Every cost and value, across the product | *Where this number comes from* on every term, everywhere terms appear | Yes |
| N9 Parts, pricing, labour, machine, hours, units | Preparation build and drawer | Yes |
| N10 Order number on Predictions | `#asOrderLine` in the value header | Yes |
