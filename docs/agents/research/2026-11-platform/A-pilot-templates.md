# A. The two pilot templates: tool-fleet AMS and device trade-in / protection

Research report A for the platform brief ([00-brief.md](00-brief.md)), 24 Nov 2026. Business and domain view, grounded
in the repo as of commit `0c71585`. Source markers in square brackets point to the Sources section. Anything not
confirmed by a primary source is marked **unconfirmed**. Customer and prospect names are left out on purpose; where a
public source names a company that could be a customer or prospect, its URL is withheld and described instead.

> **Legal review.** Sections 1.2, 1.8, 2.3, 2.4, 2.9 and every mention of a standard, a regulation, a contract term,
> insurance or data erasure are a business summary, not legal advice. They need review by Kinective's Legal team
> before anyone relies on or acts on them.

## Summary

1. Both templates already exist in the repo as Modeler packs with their own valuers (`tool_fleet`, `device`), but they
   are ports of a prototype: one RUL number is an input, the device valuer prices lots from a fixed table, and neither
   reads contracts, telemetry, erasure certificates or fraud checks. The pilot work is mostly *new evidence and gates*,
   not new routing maths.
2. Tool fleet: the manufacturer owns the tools, so the decisive new gate is **contract disposition rights** (may this
   unit be refurbished, resold, sent abroad, or must it go back to the pool?). Grade is **read** from the repair centre.
3. Wear-and-tear index (WTI) and RUL can be fully deterministic: rated life per component from PLM, consumed life from
   run hours x load factor from IoT, reset by component replacements in the repair history. Every number becomes a
   value line with its source and table version, like the existing valuer's lines.
4. Device: the gates are fraud (blocklist, finance status, activation lock, genuine parts), certified erasure before any
   listing, and a price floor. The ML price needs an **interval** (P10–P90, conformal); wide intervals, unseen models,
   floor breaches and high value go to a person.
5. Back-testing is the sales motion; it is only credible if every case is replayed **as of its decision date** (same
   price index, same open demand, no later grades) and both sides are priced the same way, with costs and a bootstrap
   band. The repo has the simulation core (`modeler/simulate.py`) but not as-of replay or realised-vs-estimated logic.
6. Pilot MVP: 7 tool-fleet and 7 device stories (P0) below; about half are partial in the repo today.

---

## 1. Tool-fleet AMS template

### 1.1 How manufacturer-run tool fleet programmes work (public sources)

| Topic | What public sources say | Source |
|---|---|---|
| Ownership and fee | The manufacturer keeps ownership; the contractor pays one fixed monthly fee per tool ("equipment as a service"). | [S1], [S3] |
| What the fee covers | Repairs and maintenance (often "unlimited"), loan tools during repair (next working day in one country), battery and charger exchange, theft cover. | [S1] |
| Theft cover | Varies by country: up to 80% of tool cost in one market, 50% in another, full replacement in a third. | [S1] |
| Term | Typically 36 months for cordless tools and 48 months for heavy combihammers and breakers. | [S1] |
| End of contract | The tool is swapped for the current generation; or, if still productive, the contract extends automatically. Old fleet tools can earn a credit on a new fleet contract. | [S1] |
| Returns not made | A non-collection fee is charged for fleet tools not returned; tools are retired in the tool-tracking app when returned. | [S1] |
| Scale (one programme, 2021) | About 3 million tools under fleet contracts; about 1 million tools, batteries and chargers collected a year for circular use; spare-part reuse grew from 10,000 to 100,000 pieces in two years. | [S2] |
| What happens to returned tools | Usable parts reused in other tools (spare-part reuse); tools no longer fit for professional use donated or recycled; high-quality parts refurbished and reused. | [S1], [S2] |
| Refurbished resale | Several tool makers sell factory-reconditioned tools through own outlets or authorised partners, with 1–2 year warranties (one maker gives reconditioned tools its full new-tool warranty). | [S6] |
| Connected tools | Bluetooth LE tags or built-in modules report location and usage; one telematics partnership infers **run time from accelerometer vibration**; gateways in vans assign tags to tool cribs automatically. | [S4], [S5] |
| Digital fleet view | Fleet-manager functions in the tool-tracking app show fleet health, request repairs, organise loaners and see the last user. | [S2] |

**Unconfirmed:** published contract lengths beyond the two classes above, early-termination terms, whether returned
fleet tools are resold as "certified pre-owned" by the fleet programme itself (one maker's reconditioned programme
exists, but its feed from fleet returns is not stated publicly), and how often a returned tool is re-issued to another
fleet versus refurbished first.

### 1.2 Contract terms that constrain disposition

These are the questions the contract gate must answer *before* a route is valued. Wording is a hypothesis to confirm
with the pilot's contract owner (needs Legal review).

| Term | Why it matters for disposition | Gate behaviour |
|---|---|---|
| Ownership stays with the manufacturer | The customer cannot sell or scrap; every route is the owner's. | Route allowed only for owner's org unit. |
| Return reason (end of term, swap/upgrade, repair, theft recovered, early termination) | Theft-recovered tools may be under an insurer claim or police record; early returns may carry charges. | Theft-recovered: hold for a person; never resell until the claim is closed. |
| Damage beyond fair wear | Customer may be charged; the tool is evidence until the charge is settled. | Hold disposition until the damage charge is closed or waived. |
| Auto-extension | A tool "still productive" may stay on contract; a return may be a swap of a working tool. | Re-issue paths favoured; no scrap while the unit is still under a live line. |
| Regional resale limits (brand and channel protection) | A maker may not allow pre-owned sale in some markets, or only through authorised outlets. | `resell` excluded by market / channel table (**unconfirmed** that such limits exist; ask). |
| Reconditioned warranty promise | A refurbished tool sold with a warranty must meet a certified standard (test, safety check). | `refurb` and `resell` require a grade certificate and electrical safety test record. |
| Battery and electronics rules | Lithium-ion packs have transport and take-back obligations (e.g. EU Battery Regulation 2023/1542, **unconfirmed** applicability per market). | Batteries are a separate asset class with its own routes and a hazardous-transport flag. |
| Customer data on connected tools | A tag or app record links a tool to a site and a worker. | Unlink from the customer's account before re-issue (a step, not an erasure certificate). |

### 1.3 What happens to a returned tool: the routes

The repo's tool-fleet pack (`backend/di/services/modeler/valuers/tool_fleet.py`, `PATHS`) already has the six routes
the public sources describe. Mapping:

| Public practice | Repo path id | Repo name | Executing system type | Repo pre-condition |
|---|---|---|---|---|
| Re-issue to another fleet (clean and inspect) | `release` | Re-issue to fleet | Fleet contract system | grade A, a fleet order needing the unit in time |
| Refurbish, then fleet or certified pre-owned sale | `refurb` | Refurbish → place | Repair centre work orders (ERP service) | grade B/C and RUL ≥ 40%; a named order (GR-02) |
| Loaner / tool pool | `redeploy` | Tool pool | ERP stock transfer | not grade D, RUL ≥ 45%, a pool shortage |
| Pre-owned sale (bid or outlet) | `resell` | Pre-owned sale | Pre-owned sales channel | firm bid at or above grade, else outlet estimate |
| Spare-part reuse | `harvest` | Harvest parts | Repair centre teardown + spare parts | part RUL ≥ fit-for-use threshold (50%) and an open repair order |
| Recycling (or donation) | `exit` | Recycle | Recycler portal + circularity ledger | always feasible; certificate (GR-06) |

Missing from the repo: **donation** as an exit sub-route, **battery** as its own class, **trade-in credit** on a new
fleet contract as a value line, and the **contract gate** of 1.2.

### 1.4 Data that exists, per enterprise system type

| System type | Data | Used for | Repo today |
|---|---|---|---|
| Fleet contract / CRM | contract id, customer, tool serial, start, term, fee, return reason, theft claim, damage charge, auto-extension flag | contract gate, re-issue demand (renewals), trade-in credit | partial: fleet orders exist only as sample demand in the valuer |
| ERP (SD/MM/FI) | material, serial, stock location, sales orders, purchase requisitions for new pool units, cost centres, credit memos | demand, valuation, reconciliation | mocks exist (ERP, procurement) |
| Repair centre / depot repair | repair orders, components replaced (with run hours at replacement), test results, **grade A–D**, labour hours, turnaround | grade (read), component resets, refurb cost | depot-repair mock carries a predicted grade and test results |
| PLM (read-only) | bill of materials per class and revision, rated life per wear component, criticality, condemn limits, successor model | rated life, weights, upgrade logic | PLM reads exist (`backend/di/repositories/plm.py`), no rated-life field |
| IoT / connected tool | run hours, motor current or load profile, temperature excursions, drops/shocks, last seen, location | consumed life, load factor, events | IoT mock reports run hours, vibration (ISO 10816-3 zones) and alarms for motors |
| WMS | receipt, bin, condition code, kit completeness (case, charger, battery) | receiving stage, kitting | WMS mock exists |
| Remarketing / outlet | bids, listing prices, sell-through, fees | resale value | remarketing mocks exist |
| Carbon accounting | factors per class and route | CO2e on the card | carbon mock exists; not in valuers |

### 1.5 Wear-and-tear index and RUL: deterministic and auditable

Goal (brief item 5a): the grade is **read** from the repair centre; WTI and RUL are **computed** from IoT + PLM + repair
data, and every number must be explainable. ISO 13381-1:2025 frames prognosis as predicting RUL "with a satisfactory
level of confidence" and says statistical or experience-based approaches are needed because prognosis is never exact
[R1]; that supports a rule-based model with a stated confidence class rather than a black box.

**Inputs per returned tool (serial `S`, class `C`, BOM revision `r`)**

| Symbol | Meaning | Source system |
|---|---|---|
| `L_i` | rated life of wear component `i` (hours, impacts or cycles) | PLM, per class and revision |
| `w_i` | criticality weight of component `i` (sum 1) | PLM or engineering table (owner: Quality) |
| `h` | run hours of the tool (or impacts) at return | IoT; fallback: contract months x class median duty |
| `s_hi` | share of run time at high load or temperature | IoT |
| `α_i` | load sensitivity of component `i` | engineering table (owner: Quality) |
| `n_e`, `p_e` | count of events of type `e` (overheat, drop, overload) and their penalty in equivalent hours | IoT counts; penalty table (owner: Quality) |
| `h0_i` | run hours when component `i` was last replaced (0 if never) | repair history |
| `G` | repair-centre grade A–D | repair centre (read, never computed) |

**Computation (versioned rule set, no learning in the loop)**

```
k_i      = 1 + α_i · s_hi                                  load factor
U_i      = (h − h0_i) · k_i + Σ_e n_e · p_e,i              equivalent hours used since last replacement
c_i      = min(1, U_i / L_i)                               share of life consumed
RUL_i    = 100 · (1 − c_i)                                 % life left, per component
WTI      = round(100 · Σ_i w_i · c_i)                       wear-and-tear index, 0 (new) to 100 (worn out)
RUL_tool = min over critical components of RUL_i            weakest link, also shown in hours: (L_i − U_i) / k_i
```

**Confidence class** (shown next to RUL, drives hand-off):
- **High**: telemetry covers ≥ 90% of contract days and the repair history is complete.
- **Medium**: telemetry gaps filled with the class's median duty, or a component has no replacement record.
- **Low**: no telemetry (untagged tool): `h` estimated from contract months; RUL shown as a range using the class's
  P10 and P90 duty. Low confidence never auto-routes to `release` or `redeploy`.

**Cross-check with the read grade** (exceptions to a person, never silent):
- Grade A or B and WTI ≥ 60, or grade D and WTI ≤ 20 with no damage code: "grade and wear disagree".
- RUL_tool below the route threshold but grade A: route blocked with the component named.

**Illustrative worked example** (numbers invented for the demo, not real ratings). Combihammer class, 820 run hours,
30% at high load, piston kit replaced at 500 h, α = 0.5 for the motor, gearbox and piston kit, 0 for electronics:

| Component | `L_i` (h) | `w_i` | `U_i` | consumed | RUL_i |
|---|---|---|---|---|---|
| Motor armature | 1,200 | 0.4 | 820 x 1.15 = 943 | 79% | 21% |
| Gearbox | 1,500 | 0.3 | 943 | 63% | 37% |
| Electronics module | 2,000 | 0.2 | 820 | 41% | 59% |
| Piston and seal kit | 600 | 0.1 | 320 x 1.15 = 368 | 61% | 39% |

WTI = 100 x (0.4·0.79 + 0.3·0.63 + 0.2·0.41 + 0.1·0.61) = **65**. RUL_tool = **21%** (motor). The card then says:
"Re-issue blocked: motor armature at 21% life (943 equivalent hours of 1,200 rated, PLM rev C; load factor 1.15 from
30% high-load time). Refurbish with a new armature lifts tool RUL to 37% (gearbox), below the 40% refurbish threshold:
harvest electronics module (59%) for repair order …, recycle the rest." Each phrase is a value line with source, table
version and timestamp, like the existing `ValueLine` (`type`, `label`, `basis`, `amt`) in the valuer.

**Audit record per evaluation**: input snapshot (hours, events, repair rows, PLM revision), table versions (`α`, event
penalties, thresholds), rule-set version, output. Re-running the same snapshot gives the same numbers.

**Calibration (later, by a person)**: compare predicted RUL at return with the repair centre's teardown findings
(component condemned yes/no). Adjust `L_i` or `α_i` through the Modeler's maker-checker lifecycle, never automatically.
The repo already has calibration and model candidates for the industrial template (`model.fit`), not for RUL.

### 1.6 Personas and roles

| Persona | Goal | Repo role |
|---|---|---|
| Fleet desk / fleet contract admin | Close the contract line, raise charges, re-issue to renewals | Planner |
| Repair centre lead | Grade, refurbish, harvest; capacity of repair slots | Engineer |
| Tool pool planner | Keep loaner pools stocked | Planner |
| Remarketing lead | Pre-owned sale, bids, outlet pricing | Planner / Approver |
| Service parts planner | Certified used parts for repair orders | Planner |
| Quality | Owns rated-life tables, fit-for-use threshold, grade-wear exceptions | Approver (rules) |
| Finance | Holding cost rate, reconciliation of credits, charges and recovered value | Finance |
| Sustainability lead | Recycling certificates, CO2e | Approver (exit) |
| Business analyst (Studio user) | Builds and tunes the template | Admin / Developer |
| Agent (case autopilot) | Gathers evidence, values routes, proposes; never approves | agent registry |

### 1.7 End-to-end journey across the four stages

| Stage | Steps | Decision points | Who |
|---|---|---|---|
| 1. RMA intake and fraud triage | Return request from contract end, swap, repair request or pool excess; case opened by serial; contract read; theft/claim and damage checks | Is this tool ours and on this contract? Theft-recovered? Damage charge? Duplicate return? | Agent opens and checks; person on theft, damage, unknown serial |
| 2. Receiving and grading | WMS receipt, kit check (battery, charger, case); repair-centre inspection and **grade (read)**; IoT and repair history pulled; WTI and RUL computed | Kit complete? Grade and WTI agree? Confidence class? | Warehouse and repair centre record; agent computes; person on disagreement |
| 3. Smart disposition and recommerce | Contract gate, then all six routes valued with demand (renewals, pool shortages, bids, repair orders), queue plan across open returns and repair slots; best route proposed with second best and why | Which route? Above value threshold? Rules applied? Slots contested? | Agent proposes; named owner approves (GR-05); exceptions to Quality |
| 4. ERP/WMS financial reconciliation | Instruction sent (fleet issue, work order, transfer, sale order, teardown, recycler order); confirmations tracked; contract closed, credit or charge posted; realised vs predicted | Confirmation received? Variance above tolerance? | Agent tracks and flags; Finance confirms outcome |

### 1.8 Guardrails and gates

| Id | Gate or guardrail | Owner | Repo status |
|---|---|---|---|
| GR-01 | Grade C and D never issued to a fleet without refurbishment | Fleet desk | exists (rule check) |
| GR-02 | Refurbishment always ends in a named fleet contract, sales order or pool request | Repair centre lead | exists (text guard) and in valuer |
| GR-03 | Harvested parts certified only at or above the fit-for-use threshold | Quality | exists (`rulMin` 50) |
| GR-04 | Holding cost rate set by Finance | Finance | exists (text guard) |
| GR-05 | Every decision approved by a named owner before execution | Governance board | exists |
| GR-06 | Recycling only through a certified recycler, certificate and CO2 record on file | Sustainability | text only, no check |
| new GR-07 | Contract disposition right confirmed (owner, reason, no open claim or charge) | Fleet desk | missing |
| new GR-08 | RUL and grade certification before refurbish or redeploy (brief item 3) | Quality | partial (RUL is an input) |
| new GR-09 | Low RUL confidence never auto-routes to re-issue or pool | Quality | missing |
| new GR-10 | Electrical safety test record before any re-issue or sale (**unconfirmed** requirement per market) | Quality | missing |
| new GR-11 | Customer account unlinked from a connected tool before re-issue | Fleet desk | missing |

Approval thresholds (proposal): auto-propose for every case; a person approves all at pilot start (GR-05), then
by value band once the back-test shows agreement (for example net value below a set amount and high confidence goes to
a single click "approve batch").

### 1.9 KPIs

| KPI | Definition |
|---|---|
| Net recovery per returned tool | realised net (value lines minus costs and holding) / returns |
| Uplift vs default | net of chosen route minus net of the default route (`_default_path` in the valuer) |
| Re-issue and pool rate | share of returns re-issued or pooled (avoids new purchases) |
| Avoided new purchases | pool requisitions and renewals met from returns, at new-unit cost |
| Refurbish turnaround | receipt to ready, days; repair-slot utilisation |
| Part reuse | certified parts issued to repair orders; customer wait avoided |
| Touchless rate | cases where the person only approved (no data entry, no re-planning) |
| Grade-wear disagreement rate | exceptions / graded returns (a data-quality signal) |
| RUL accuracy | predicted vs teardown verdict per component |
| CO2e avoided | per route, deterministic factors (brief item 6) |
| Contract exceptions | returns blocked by GR-07 and their time to clear |

### 1.10 User stories (tool fleet), prioritised

P0 = pilot MVP. "Agent" = the case autopilot or another registered agent acting through the action pipeline (read or
propose only). "Person" = the role that approves.

| Id | P | Story | Given / When / Then | Agent | Person |
|---|---|---|---|---|---|
| TF-01 | P0 | As fleet desk, I want a case opened for every returned serial so nobody keys returns | Given a contract-end or swap event with a serial, When it arrives by webhook, file or sync, Then one case opens with contract, class and reason, and a second event for the same serial and reason is refused as duplicate | opens case | none |
| TF-02 | P0 | As fleet desk, I want the contract gate checked first | Given a case, When the contract says theft-recovered, open damage charge or not our owner, Then every route is blocked with the term named and the case goes to *My work* of the fleet desk | checks | fleet desk clears |
| TF-03 | P0 | As repair centre lead, I want the grade read from my system, not recomputed | Given a repair order with grade and test results, When it is confirmed, Then the case shows grade with its source and time, and the estimated grade is replaced | reads | engineer records grade |
| TF-04 | P0 | As Quality, I want WTI and RUL per component with a confidence class | Given run hours, load share, events, BOM ratings and replacements, When the case is evaluated, Then WTI, RUL per component and RUL_tool appear with each input's source and table version, and re-running gives the same numbers | computes | none |
| TF-05 | P0 | As remarketing lead, I want every route valued with the best proposed and the second best explained | Given grade, RUL, demand and bids, When evaluated, Then six routes show net with value lines; blocked ones show why; best and second are named | proposes | approver approves |
| TF-06 | P0 | As an approver, I want only exceptions and threshold cases in my queue | Given a proposal, When value is above my threshold, confidence is low, grade and wear disagree or a guardrail fired, Then it waits for me; otherwise it waits as a batch I can approve in one action | sorts | approver |
| TF-07 | P0 | As Finance, I want the instruction, confirmation and realised value reconciled | Given an approved route, When the system confirms (work order closed, sale invoiced), Then realised vs predicted and variance show, and variance above tolerance becomes a task | tracks | finance confirms |
| TF-08 | P1 | As tool pool planner, I want returns matched to pool shortages and renewals across the queue | Given several open returns and limited demand and repair slots, When planned, Then each order goes to the return where it adds most (queue plan) and the losing returns say why | plans | planner |
| TF-09 | P1 | As Quality, I want grade-wear disagreements flagged | Given grade A and WTI ≥ 60, When evaluated, Then an exception opens naming the components | flags | Quality decides |
| TF-10 | P1 | As sustainability lead, I want CO2e and the recycling certificate on the card | Given exit or any route, When valued, Then CO2e avoided per route shows from a versioned factor table; exit cannot close without a certificate | computes | sustainability |
| TF-11 | P1 | As fleet desk, I want trade-in credit and non-return fees as value lines | Given a swap to a new contract, When valued, Then the credit is shown and booked to the contract | computes | fleet desk |
| TF-12 | P2 | As Quality, I want to calibrate rated life from teardown findings | Given 3 months of teardown verdicts, When I fit, Then a candidate table with error metrics is proposed and another person promotes it | fits | Quality + approver |
| TF-13 | P2 | As remarketing lead, I want batteries routed as their own class with transport rules | Given a returned pack, When valued, Then hazardous-transport and take-back routes apply | values | remarketing |

---

## 2. Device trade-in / protection template

### 2.1 How the programmes work

Two inflows share one back end [D9]:

- **Trade-in / upgrade.** The customer gets a quote from a self-declared condition, ships or hands in the device, the
  device is graded; if the grade differs, the quote is revised (accept, or the device is returned); credit is issued;
  the device is erased, graded, repaired or not, and sold.
- **Protection / insurance replacement.** A claim is filed; fraud checks run; a replacement (often refurbished stock)
  is shipped; the damaged device must be returned within a window or a non-return fee applies; the returned device is
  owned by the programme and goes through erasure, diagnostics, repair-or-not, then reuse as replacement stock,
  resale, parts or recycling. One provider describes a quick replacement followed by data removal and a multi-point
  inspection before resale [D9] (**unconfirmed**: return windows and fees per programme).

Trade press lists insurance claims, upgrades, trade-ins, leases, warranty and remorse returns as the inflows, and
repair, resale, parts recovery, certified pre-owned placement or recycling as the outcomes [D9].

### 2.2 Grading scales

- CTIA's Reverse Logistics and Service Quality working group published a voluntary wireless device grading standard
  in February 2019 to make grading consistent across the pre-owned market [D1]. A 2024 revision aligned it with SERI's
  R2 equipment categorisation; version 5.1 (June 2026) maps wholesale grades into consumer terms and adds standardised
  functional testing, battery-health requirements and a genuine-parts declaration [D2] (**unconfirmed**: thresholds;
  the 5.1 text was not read, only the announcement).
- SERI's guidance says the CTIA scales apply only to devices that have been processed, and R2 facilities categorise on
  receipt and re-categorise through processing [D3]. A functional scale from 0 (fully functional) to 9 is reported by a
  secondary source (**unconfirmed**).
- Practical model for the template: keep **cosmetic grade** (A–D, CTIA-aligned), **functional status** (pass / fail
  list), **battery health %**, **parts status** (genuine / unknown / used per part) as four separate facts. The repo
  device valuer has only the grade.

### 2.3 Data erasure (needs Legal review)

- **NIST SP 800-88 Rev. 2**, final 26 Sep 2025, supersedes Rev. 1 (17 Dec 2014). It now guides an organisation's
  sanitisation *programme* and points to IEEE 2883 (or NSA specifications) for media-specific techniques, keeping
  cryptographic erase in its own text [D4].
- **IEEE 2883-2022** (Standard for Sanitizing Storage) defines Clear, Purge and Destruct with media- and
  interface-specific techniques and how to use cryptographic erase correctly; NIST's FAQ says IEEE 2883 deprecates
  shredding and pulverising for modern drives [D4], [D5].
- **R2v3 Appendix B** applies to facilities that do logical sanitisation and requires verification and added quality
  controls; Appendix C (test and repair) requires validated sanitisation [D3].
- **Certificate content.** A secondary source lists device make, model and serial, method, tool and version,
  verification, operator, date, location and signature, citing Rev. 2 section 4.6 (**unconfirmed** against the NIST
  text). Template rule: a certificate record per IMEI/serial with method (Clear/Purge per IEEE 2883), tool version,
  verification result and operator; **no listing, sale or re-issue without it** (repo GR-D1).
- Per brief item 3, the erasure certificate is required for IT/compute assets (phones, tablets, laptops) and not for
  tools and motors.

### 2.4 Fraud checks (needs Legal review)

| Check | What it catches | Source / note | Stage |
|---|---|---|---|
| Device blocklist (IMEI) | reported lost or stolen; operators share IMEIs through the GSMA registry; buyers (recyclers, insurers, pawnshops) query before buying; in one case study 2–3% of queries hit a stolen report | [D6] | intake, again at receiving |
| Finance / ownership status | device still under a financing balance or ownership claim (newer registry flags include fraud, trade and financial claims) | [D6] | intake |
| Activation lock / account lock | device still tied to the previous owner's account; removal needs proof of purchase; locked devices often go to recycling only | [D8] (vendor support and community pages; **unconfirmed** policy for trade-in) | receiving |
| Genuine parts | non-genuine or "used" display, battery, cameras flagged in the device's parts history on newer models | [D7] | grading |
| Wrong or swapped device | IMEI received differs from IMEI claimed; claim for model X, model Y received | operator practice (**unconfirmed** rates) | receiving |
| Repeat claims | same IMEI or same customer across many claims | operator practice | intake |

Fraud outcomes are holds for a person (fraud analyst), never automatic declines by an agent (repo golden rule 10).
Personal data: the template stores IMEI and claim ids only; no customer names, addresses or account numbers flow into
the platform or back-test files.

### 2.5 Price prediction and the hand-off to a person

**Inputs.** SKU (model, storage, colour, carrier lock), cosmetic grade, functional status, battery health, parts
status, age since launch, region, channel, lot size, and a **market price feed** (wholesale clearing prices by SKU and
grade per week) plus launch-event dates. Studies of used-phone prices find brand, model, usage period and refurbished
condition drive price; gradient-boosted trees perform well on such features [D10] (academic, small data sets;
**unconfirmed** at production scale). A trade guide recommends a 30-day same-SKU comparison and a 3-month rolling slope
for depreciation, with step-downs after launch events [W1] (blog, weak source).

**Output per device or lot, per channel:** expected net cash (price x (1 − fee) − fixed − logistics − expected buyer
returns − holding x days), days to sell, and an interval (P10–P90).

**Confidence.** Use quantile regression or split conformal prediction over the price model; conformal intervals adapt
when error varies by input and support a reject option [D11]. Hand to a person when any of:
- interval width / point estimate above a set share (for example 25%);
- SKU unseen or with fewer than N sales in the window (novelty);
- recovery below the floor (repo GR-D2: 55% of reference value);
- value above the approver's threshold;
- price feed stale (older than the last weekly update) or drift alarm (realised vs predicted error rising).

Routing then picks the channel with the best risk-adjusted score; the repo's device valuer already does this from a
fixed table (`DST`, `score`, `decide`): cash net of fees, logistics, return rate and price erosion, penalised for days
past a 60-day SLA, with grade D kept off Buy Now and Marketplace and lot-size caps.

### 2.6 Channels

| Channel | Typical fit | Repo |
|---|---|---|
| Reuse as claim replacement stock | good grade, current models; avoids buying replacements | missing |
| B2C refurbished marketplace (single units) | grade A/B, needs warranty and battery threshold | `market` (lot-based) |
| Own refurbished store | grade A | missing |
| Wholesale: Buy Now, Offers, Auction lots | mixed grades; speed | `buynow`, `offers`, `auction` |
| Repair then resell | when repair cost < grade uplift | missing (no repair step) |
| Parts harvest | functional parts from grade D or locked devices | missing |
| Certified recycling (R2) | locked, blocklisted (as law allows), beyond repair | missing |

### 2.7 Personas

| Persona | Goal | Repo role |
|---|---|---|
| Claims / trade-in operations | intake, quote revisions, customer credits | Planner |
| Fraud analyst | blocklist, lock and claim holds | Approver (fraud queue, new) |
| Receiving and grading lead | erase, test, grade | Warehouse manager / Engineer |
| Pricing analyst | price model, floors, feeds | Approver (models) |
| Channel ops / recommerce manager | channel mix, lot building, caps | Planner |
| Compliance | erasure certificates, recycling | Approver |
| Recommerce finance | credits, claim cost offset, realised value | Finance |

### 2.8 Journey across the four stages

| Stage | Steps | Decision points | Who |
|---|---|---|---|
| 1. RMA intake and fraud triage | claim or trade-in arrives with IMEI and declared condition; blocklist and finance check; repeat-claim check; quote | Clear to accept? Quote? | Agent checks and quotes inside policy; fraud analyst on any hit |
| 2. Receiving and grading | IMEI matched; activation lock check; erasure with certificate; diagnostics; cosmetic grade, battery, parts status; quote revised if grade differs | Match? Locked? Erased? Re-quote? | Receiving records; agent re-quotes inside tolerance; person outside |
| 3. Smart disposition and recommerce | price per channel with interval; reuse-as-replacement vs resale vs repair vs parts vs recycle; lot building | Channel? Confidence? Floor? | Agent proposes and builds lots; pricing analyst on low confidence or floor; channel ops approves lots |
| 4. ERP/WMS financial reconciliation | listing, sale, settlement; credits to customers; claim cost offset; realised vs predicted feeds the model | Variance? Buyer returns? | Agent tracks; finance confirms |

### 2.9 Guardrails and gates

| Id | Rule | Owner | Repo status |
|---|---|---|---|
| GR-D1 | Certified data wipe before any listing | Compliance | text guard only; valuer does not check |
| GR-D2 | Recovery floor: below 55% of reference value goes to human review | Recommerce finance | text guard only; `DG["floor"]` defined in `device.py` but never used |
| GR-D3 | Grade D never on Buy Now or Marketplace | Channel ops | enforced in `score` |
| GR-D4 | Maximum lot size per channel | Channel ops | enforced in `score` |
| GR-D5 | Marketplace never undercuts the live Buy Now price | Pricing | text guard only |
| GR-D6 | Every routing approved by a named owner | Governance board | exists |
| new GR-D7 | Blocklist, finance and activation-lock clear before any sale (locked: parts or recycle only, as law allows) | Fraud | missing |
| new GR-D8 | Low price confidence or unseen SKU goes to a person | Pricing | missing (no ML, no interval) |
| new GR-D9 | Parts status declared on every listing (genuine-parts declaration) | Compliance | missing |

These rules touch consumer law, data protection and insurance regulation: Legal review needed.

### 2.10 KPIs

Net recovery % of reference value; days to cash; sell-through per channel; buyer return rate; replacement stock
sourced from returns (avoided purchases); erasure certificate coverage (target 100%); fraud hit rate and false-hold
rate; price error (MAE, and interval coverage: share of realised prices inside P10–P90, target near 80%); share routed
without manual pricing; human queue age; CO2e avoided per route.

### 2.11 User stories (device), prioritised

| Id | P | Story | Given / When / Then | Agent | Person |
|---|---|---|---|---|---|
| DV-01 | P0 | As claims ops, I want a case per returned IMEI | Given a claim or trade-in with IMEI, When it arrives, Then one case opens per IMEI (or per lot for bulk), duplicates refused | opens | none |
| DV-02 | P0 | As fraud analyst, I want blocklist, finance and lock checks before value | Given a case, When a check hits, Then routes other than hold, return-to-sender, parts or recycle are blocked and the case is in my queue with the check's evidence | checks | fraud analyst |
| DV-03 | P0 | As compliance, I want no listing without an erasure certificate | Given a device, When a sale route is proposed and no certificate (method, tool version, verification, operator) is on file, Then the route is blocked with GR-D1 named | checks | compliance (exceptions) |
| DV-04 | P0 | As grading lead, I want grade, battery and parts status read from the diagnostics system | Given a diagnostics result, When it is received, Then four facts show with source; a grade worse than declared triggers a re-quote proposal | reads, proposes re-quote | ops outside tolerance |
| DV-05 | P0 | As pricing analyst, I want price per channel with a P10–P90 interval | Given SKU, grade, age and the latest feed, When evaluated, Then each channel shows expected net, days and interval, and the feed date | prices | none |
| DV-06 | P0 | As pricing analyst, I want low-confidence items handed to me | Given an interval wider than the set share, an unseen SKU, a floor breach or a stale feed, When proposed, Then it waits for me with the reason; others wait as an approvable batch | sorts | pricing analyst |
| DV-07 | P0 | As finance, I want realised value reconciled and fed back | Given a sale settles, When confirmed, Then realised vs predicted, fees and buyer returns post; the error feeds calibration | tracks | finance |
| DV-08 | P1 | As channel ops, I want lots built by the agent within caps | Given approved routes, When building, Then lots respect GR-D3/D4 and are proposed for approval | builds | channel ops |
| DV-09 | P1 | As claims ops, I want reuse as replacement stock valued as a channel | Given demand for replacements of that SKU, When valued, Then avoided purchase cost shows as a channel | values | ops |
| DV-10 | P1 | As channel ops, I want repair-then-sell and parts as routes | Given repair cost and parts demand, When valued, Then repair and parts routes appear with their costs | values | ops |
| DV-11 | P1 | As pricing, I want GR-D5 checked | Given a marketplace price below live Buy Now, When proposed, Then blocked with both prices | checks | pricing |
| DV-12 | P2 | As pricing analyst, I want to propose a retrained model and have another person promote it | Given new outcomes, When fitted, Then a candidate with MAE and coverage is proposed; shadow mode before promotion | fits | pricing + approver |

---

## 3. Back-testing (both templates)

### 3.1 What historical data to request (one month or one quarter)

| Data | Tool fleet | Device |
|---|---|---|
| Returns | serial, class, return date, reason, contract id, site | IMEI (or hashed), SKU, claim/trade-in id, date, reason |
| Condition at the time | repair-centre grade and test results with dates; run hours and events if tagged; repair history | diagnostics grade, battery, parts, lock and blocklist results with dates |
| Actual decision | route taken, decision date, who | channel, lot, list date |
| Actual outcome | realised revenue or avoided cost, costs (labour, parts, freight, fees), completion date | sale price, fees, logistics, buyer returns, days to sell |
| Demand at the time | open renewals, pool requisitions, bids, open repair orders, with created/expiry dates | price feed history by SKU and grade per week; channel caps |
| Reference tables | new prices, rated lives (PLM), cost rates, as dated versions | reference values, fee schedules, as dated versions |

Ask for de-identified extracts: no customer names, addresses, account or card numbers (organisation policy). IMEIs can
be salted hashes if the fraud checks are not part of the back-test.

### 3.2 Computing uplift fairly

1. **As-of replay.** Freeze each case at its actual decision date `t0`. Use only facts timestamped before `t0`: the
   price index of that week, bids live at `t0`, demand open at `t0`, the grade known at `t0` (not a later re-inspection).
   Reject any input dated after `t0`: this is the leakage test, automated and reported.
2. **Same yardstick for both sides.** Primary measure: value the actual route and our route with the **same** valuer
   and the **same** as-of inputs ("estimated vs estimated"). Secondary: realised value of the actual route vs our
   estimate, corrected by the valuer's bias measured on the cases where our route equals the actual route (the
   agreement set is a free calibration sample). Show both; lead with the conservative one.
3. **Constraints honoured.** One renewal, pool requisition or bid can take one unit; repair slots and channel caps are
   finite. Replay the queue in date order with the queue plan, not case by case (the repo's `plan_queue` already does
   this for open cases).
4. **All costs in.** Freight between sites, refurbishment labour, test, channel fees, buyer returns, holding cost per
   day, and price erosion over days to sell.
5. **Bands, not a single number.** Bootstrap over cases (resample returns 1,000 times) for an 80% and 95% interval on
   total uplift; sensitivity at ±10% market index and ±20% labour.
6. **Counterfactuals are estimates.** Logged data shows only the action taken (selection bias); reward-model estimates
   carry modelling bias, and a small live randomised or shadow period is the clean reference [B1]. So: back-test to
   sell, then pilot mode and shadow mode to prove (both exist in the repo: pilot mode per org unit, shadow in the
   Modeler lifecycle).
7. **No tuning on the test set.** Rules and tables are frozen before the replay; any change is a new, dated run.

### 3.3 Presenting it

- One waterfall: actual net → same-route repricing (bias) → route changes by type (re-issue, pool, harvest, channel)
  → constraint losses → **net uplift with its band**.
- Flip table: cases whose route changes, from → to, value delta, top reason; with the 10 largest explained in full.
- Agreement rate (where we would have done the same) and the cases we would have **held for a person** (that is a
  feature: it shows the control).
- Data-quality findings (missing grades, untagged tools, stale feeds) as a separate list: it sells the fabric.
- A one-page method note listing the as-of rule, the yardstick and the leakage test result.

---

## 4. Ten-minute demo scripts (Studio first)

Marked **[exists]**, **[partial]** or **[build]** against the repo today.

### 4.1 Tool-fleet AMS

| Min | Screen | Say and do |
|---|---|---|
| 0:00 | Studio | Type "create a template for my AMS process: tools come back at contract end, swap or repair; we own them". **[build]** The assistant drafts the flow: intake → contract gate → receive and grade → WTI/RUL → six routes → approval → instructions → reconciliation. |
| 1:30 | Studio, adapters | It lists the sources to connect: fleet contracts, ERP, repair centre, PLM (read-only), IoT, WMS, remarketing, carbon; shows suggested field mappings; user confirms. **[partial]** (adapters, mappings and "Build with AI" exist; template drafting does not) |
| 3:00 | Modeler | Show guardrails GR-01…GR-11 with owners; type "repair centre returns grade A/B: prefer tool pool" and see the proposed rule, its check and simulation. **[exists]** for GR-01–06 and rule proposals |
| 4:00 | Home / My work | A contract-end return arrives (webhook); the agent opens the case. **[exists]** intake; **[build]** contract gate |
| 5:00 | Case | Evidence: grade B read from the repair centre with time; IoT 820 h, 30% high load; PLM ratings; repair history. WTI 65, RUL 21% motor, confidence high, each line explained. **[build]** WTI/RUL; **[partial]** grade read |
| 6:30 | Case, routes | Six routes with value lines; re-issue blocked (motor); refurbish vs harvest vs pool; best and second best; CO2e per route. **[exists]** valuation, **[build]** CO2e |
| 7:30 | Queue plan | Two returns compete for one renewal; the plan gives it where it adds most. **[exists]** |
| 8:15 | Approvals | Approver sees only threshold and exception cases; approves. **[partial]** (approvals exist; value/confidence routing to be built) |
| 9:00 | Back-test | One quarter replayed: waterfall, band, flips, held cases. **[build]** |

### 4.2 Device trade-in / protection

| Min | Screen | Say and do |
|---|---|---|
| 0:00 | Studio | "Create a template for insurance replacement and trade-in returns of phones". **[build]** Flow: intake → fraud checks → receive, erase, grade → price per channel → lots → approval → settlement. |
| 1:30 | Studio, adapters | Sources: claims system, device blocklist service, diagnostics and erasure tool, WMS, price feed, channels, ERP. Mappings proposed; confirm. **[partial]** |
| 3:00 | Modeler | Guardrails GR-D1…D9; try "list grade D on Buy Now" and see it blocked by GR-D3. **[exists]** |
| 4:00 | Intake | 200 claim returns arrive; three hit the blocklist or a lock and go to the fraud queue with evidence. **[build]** |
| 5:00 | Case | Erasure certificate (method, tool version, verified); grade B, battery 84%, display "unknown part". **[build]** |
| 6:00 | Pricing | Per channel: expected net, days, P10–P90; two items flagged low confidence (unseen SKU, wide interval) go to the pricing analyst. **[build]** ML and interval; **[exists]** channel scoring from the fixed table |
| 7:30 | Lots | Agent proposes lots inside caps; one marketplace price blocked by GR-D5. **[build]** |
| 8:30 | Approvals and finance | Channel ops approves the batch; settlement reconciles realised vs predicted. **[partial]** |
| 9:15 | Back-test | One month replayed on the as-of price index: uplift with band, days-to-cash change. **[build]** |

---

## 5. Grounding in the repo

What exists today (read 24 Nov 2026):

- **Packs** (`backend/di/services/modeler/templates.py`): `industrial` from `packs/industrial.json`; `tool_fleet` and
  `device` are built in code from the PO goldens (`fixtures/golden/po/templates.json`), with guardrail checks as data
  (`TOOL_FLEET_GUARDS`, `DEVICE_GUARDS`). Only `industrial.json` exists as a packaged file, so a Studio-generated
  template has no file format to write to yet.
- **Tool-fleet valuer** (`valuers/tool_fleet.py`, 1,116 lines): six paths, value lines per path, demand matching,
  queue plan over open returns and repair slots, rules, simulation. `rul` and `partRul` are inputs; grade is `grade`
  else `estGrade`. No contract, IoT, PLM or carbon inputs.
- **Device valuer** (`valuers/device.py`): four wholesale channels, a fixed channel table by grade x age band, lot-size
  caps, grade-D exclusion, SLA penalty. No ML, no interval, no erasure or fraud check; the 55% floor is defined and
  unused.
- **Intake** (`services/cases/intake.py`): opens tool-fleet and device cases from data (reasons `rma`, `lease_end`,
  `trade_in`, `contract_end`, `iot_alarm`, `manual`), with dedupe; file imports can open a case per row
  (`fabric_records.py`).
- **Simulation and pilot**: `modeler/simulate.py` (candidate vs published rules over a queue), pilot mode and its
  report (`actions/org_pilot.py`), calibration and model candidates for the industrial template (`actions/models.py`).
- **Agents**: case autopilot playbook (evidence, request, re-evaluate, submit, wait for approval, resend); proposals
  held for a person; forbidden list.
- **Mocks**: IoT (run hours, vibration zones, alarms), depot repair (repair orders, predicted grade, test results),
  three PLM systems, leasing, remarketing, carbon, WMS, ERP.
- **Industrial gate** for data erasure exists for class `it` (`engine/gates.py`), not wired to the device pack.

| Story | Status | Evidence / gap |
|---|---|---|
| TF-01 case per returned serial | partial | `intake.open_case` with dedupe; no contract system feed for tool-fleet |
| TF-02 contract gate | missing | no contract data in the valuer or packs |
| TF-03 grade read from repair centre | partial | depot-repair mock has a grade; tool-fleet case takes `grade` from facts, no mapping from repair orders shown |
| TF-04 WTI and RUL per component | missing | RUL and part RUL are inputs; IoT run hours exist only for industrial motors |
| TF-05 route valuation with why | exists | `tool_fleet._value`, `_decide1` (best, second, uplift, rules) |
| TF-06 exceptions-only approvals | partial | approvals and proposals exist; no value/confidence routing rule |
| TF-07 reconciliation | partial | instructions and outcome confirmation exist for cases; tool-fleet specific systems not mapped |
| TF-08 queue plan | exists | `plan_queue` |
| TF-09 grade-wear disagreement | missing | needs TF-04 |
| TF-10 CO2e and recycling certificate | partial | carbon shown on industrial screens; GR-06 text only |
| TF-11 trade-in credit, non-return fee | missing | |
| TF-12 RUL calibration | missing | calibration exists for industrial predictor only |
| TF-13 batteries as a class | missing | |
| DV-01 case per IMEI or lot | partial | device lot intake exists; no IMEI-level case |
| DV-02 fraud checks | missing | |
| DV-03 erasure certificate gate | partial | GR-D1 text guard; industrial erasure gate not used by the device pack |
| DV-04 grade, battery, parts read | partial | grade only |
| DV-05 price per channel with interval | partial | channel scoring from a fixed table; no feed, no interval |
| DV-06 low-confidence hand-off | missing | |
| DV-07 reconciliation and feedback | partial | generic outcome confirmation; no device calibration |
| DV-08 lot building | missing | lots are given, not built |
| DV-09 reuse as replacement stock | missing | |
| DV-10 repair and parts routes | missing | |
| DV-11 GR-D5 check | missing | text guard only |
| DV-12 model candidates | partial | model lifecycle exists for industrial |
| Studio "create a template" | missing | Build with AI maps workflows to known topologies; packs are code |
| Back-test as-of replay | partial | rule simulation exists; no as-of inputs, no realised-vs-estimated, no band |

---

## 6. Unconfirmed / open questions for the domain expert

Tool fleet:
1. Which contract terms decide disposition (ownership, theft-recovered, damage, regional resale limits)? Is there a
   machine-readable contract field for each?
2. Does the repair centre's grade come with component findings (replaced, condemned) and run hours at repair?
3. Are rated lives per wear component available from PLM, or only service intervals? In hours, impacts or cycles?
4. What share of the fleet is tagged or connected, and does the tag report run time, load or only location?
5. Are fleet returns resold as reconditioned tools, and through which channel? Is there a donation route with rules?
6. Is an electrical safety test required before re-issue or resale in the pilot's markets?
7. How are batteries handled: same case as the tool, or their own flow?
8. Approval thresholds: which value and confidence bands may an approver clear in a batch?

Device:
9. Which inflows in the pilot: insurance replacement, trade-in, or both? Who owns the device after a claim?
10. Which grading scale and diagnostics tool; does it report battery health and parts status per IMEI?
11. Which erasure tool and certificate format; is the certificate per IMEI and machine-readable?
12. Which blocklist and finance checks are licensed; what is the policy for locked or blocklisted devices?
13. Is a weekly wholesale price feed available per SKU and grade, and for how many months back?
14. What is the floor and the confidence threshold the business accepts for auto-routing?
15. Are lots built by the programme or by the buyer platform?

Both:
16. Can historical extracts be de-identified at source (no names, addresses, account numbers)?
17. Which value counts as "actual": invoiced price, settled cash, or booked recovery?

**Unconfirmed in this report:** CTIA 5.1 thresholds; the NIST Rev. 2 certificate field list; the 0–9 functional
scale; return windows and non-return fees in protection programmes; regional resale limits and safety-test rules for
reconditioned tools; battery-regulation applicability; academic price-model accuracy at production scale; weekly
price-erosion rates (the repo's 1.3% a week is a prototype value).

---

## Sources

All read or searched on 24 Nov 2026 unless stated. "Withheld" = the URL names a company that may be a customer or
prospect, per the brief.

- [S1] A tool manufacturer's public fleet-management pages and help centre (US, UK, Canada, Finland, South Africa
  editions; terms flyer for fleet exchange). Withheld. Undated web pages.
- [S2] Same manufacturer, 2021 company report, chapter on continuous improvement of tool fleet management. Withheld.
- [S3] SMACNA news, "Cost Predictability + Enhanced Productivity with Fleet Management", 14 Nov 2025:
  https://www.smacna.org/news/products-and-services-updates/article/2025/11/14/cost-predictability---enhanced-productivity-with-fleet-management
- [S4] Silicon Labs, "The benefits of Bluetooth LE connectivity in power tools" (white paper, undated):
  https://silabs.com/whitepapers/the-benefits-of-bluetooth-le-connectivity-in-power-tools
- [S5] Construction trade press on Bluetooth tool tracking and accelerometer run time (forconstructionpros.com, undated
  articles). Withheld (names the tool manufacturer).
- [S6] Several tool makers' and authorised outlets' reconditioned-tool pages and a consumer-tech article on a
  marketplace's certified refurbished tools programme (2-year warranty). Withheld (may name prospects).
- [R1] ISO 13381-1:2025, Condition monitoring and diagnostics of machine systems — Prognostics — Part 1, Sep 2025:
  https://www.iso.org/standard/88029.html (abstract and contents only; standard text not read).
- [D1] TelecomTV, "CTIA establishes industry standard for grading pre-owned wireless devices", 12 Feb 2019:
  https://www.telecomtv.com/content/devices/ctia-establishes-industry-standard-for-grading-pre-owned-wireless-devices-34026/
- [D2] PR Newswire, CTIA publishes wireless device grading standard (version 5.1), 10 Jun 2026 (search snippet only):
  https://www.prnewswire.com/news-releases/ctia-publishes-wireless-device-grading-standard-in-support-of-greater-transparency-for-pre-owned-devices-302796919.html
- [D3] SERI R2 knowledge base, CTIA grading Q&A: https://sustainableelectronics.org/knowledge-base/ctia-grading-qa/ ;
  Summary of R2v3 Requirements (May 2021):
  https://sustainableelectronics.org/wp-content/uploads/2021/05/Summary-of-R2v3-Requirements.pdf
- [D4] NIST SP 800-88 Rev. 2, Guidelines for Media Sanitization, final 26 Sep 2025:
  https://csrc.nist.gov/pubs/sp/800/88/r2/final ; FAQ:
  https://csrc.nist.gov/files/pubs/sp/800/88/r2/final/docs/sp800-88r2-faq.pdf (FAQ content via search summary; PDF
  not rendered here).
- [D5] IEEE 2883-2022, Standard for Sanitizing Storage: https://standards.ieee.org/ieee/2883/10277/ ; SNIA Security
  Summit 2022 talk on IEEE 2883:
  https://snia.org/sites/default/files/Security-Summit/2022/SNIA-SSS22-Hatfield-IEEE-2883-Standard.pdf
- [D6] GSMA Device Check: https://www.gsma.com/services/tac/about-device-check/ ; GSMA Device Registry:
  https://www.gsma.com/services/deviceregistry/ ; GSMA phone theft white paper, Oct 2024:
  https://gsma.com/solutions-and-impact/industry-services/wp-content/uploads/2024/10/Phone-Theft-White-Paper-MWC-Vegas-Oct-2024_10_08_24.pdf
- [D7] A phone maker's support pages on genuine displays and batteries and on parts and service history. Withheld.
- [D8] The same maker's activation-lock support and community pages. Withheld. Community posts are not policy.
- [D9] Resource Recycling, "Reverse logistics: the engine of the smartphone supply chain", 21 Jan 2026:
  https://resource-recycling.com/e-scrap/2026/01/21/reverse-logistics-the-engine-of-the-smartphone-supply-chain/ ;
  protection-provider refurbishment pages (withheld).
- [D10] Journal of Socioeconomics and Engineering (JSES) 2021, used-phone recovery value in Taiwan:
  https://reference-global.com/download/article/10.2478/jses-2021-0003.pdf ; refurbished smartphone price study
  (DergiPark, 2026, search snippet only): https://dergipark.org.tr/tr/download/article-file/4469969
- [D11] Sokol, Moniz, Chawla, "Conformalized Selective Regression", arXiv 2402.16300 (2024):
  https://arxiv.org/abs/2402.16300 ; selective prediction sets with abstention, arXiv 1906.05473.
- [B1] Kato et al., "A Practical Guide of Off-Policy Evaluation for Bandit Problems", arXiv 2010.12470 (2020):
  https://arxiv.org/pdf/2010.12470 ; Joachims, counterfactual evaluation lecture (Cornell, 2016):
  https://www.cs.cornell.edu/courses/cs7792/2016fa/lectures/03-counterfactualmodel.pdf ; offline evaluation under
  unobserved confounding, arXiv 2309.04222.
- [W1] Trade blog on used-phone depreciation methods (verifieddealers.pages.dev, 2026). Weak source.
- Repo: `backend/di/services/modeler/templates.py`, `valuers/tool_fleet.py`, `valuers/device.py`,
  `services/cases/intake.py`, `modeler/simulate.py`, `actions/org_pilot.py`, `actions/org_pack.py`,
  `agents/playbooks/case_autopilot.py`, `engine/gates.py`, `repositories/plm.py`, `fixtures/golden/po/templates.json`,
  `source-sim/sim/vendors/` (IoT, depot repair), `docs/guides/users/README.md`; commit `0c71585`.
