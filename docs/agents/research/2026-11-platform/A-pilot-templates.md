# A. Recover pilot templates: tool-fleet AMS (three flows) and device recommerce

Research report A for the platform brief ([00-brief.md](00-brief.md)), revised 24 Nov 2026 against the Recover
"5 Industry Segments" source note ([01-recover-segments.md](01-recover-segments.md), cited as "01 §n"). Business and
domain view, grounded in the repo at commit `5b1fcfd`. Source markers in square brackets point to the Sources section.
Anything not confirmed by a primary source is marked **unconfirmed**. Numbers marked *sample, modelled* come from the
prototype's synthetic data: they are not facts, results or forecasts. Customer and prospect names are left out on
purpose. Where a public source names a company that could be a customer or prospect, the report withholds the URL and
describes the source instead.

> **Legal review.** Sections 1.2, 1.7, 1.9.5, 1.10.4, 2.3, 2.4, 2.7, 2.12 and every mention of a standard, a
> regulation, a recall, a contract term, cover or warranty terms, insurance, consumer payouts or data erasure are a
> business summary, not legal advice. They need review by Kinective's Legal team before anyone relies on or acts on
> them.

## What changed in this revision and why

**Added**

- **Two new P0 tool-fleet flows, Service desk (§1.9) and Contract refresh (§1.10).** Today's decision makes all three
  tool-fleet flows P0 (01 §4.2, §4.3). Each flow has its own section: how it works, journey, rules, guardrails, KPIs
  and data.
- **Public research for the new flows.** It covers repair-programme types (flat rate, capped quote, exchange unit),
  estimating repairs from past cases, trade-in credit vouchers on fleet contracts, and the timing of renewal work.
  Each new flow needed outside evidence, just as Returns has.
- **A map from the seven agents to each flow and to the code that serves them (§1.3, §2.9).** The prototype
  organises the work as seven agents in one decision chain (01 §3). The team needs to see what each agent can reuse
  today.
- **New guardrails from the pack (01 §4.1).** They are: a safety recall check, telematics younger than 7 days, repair
  over $600 → fleet manager, and write-off under 24 months → service operations. There are also three diversions,
  one of them blocked. These are now the pack's own controls.
- **The device recommerce controls from 01 §5.**
  - Blacklist and lock check.
  - Data-wipe certificate.
  - Lot over $25,000 → commercial manager.
  - Payout adjustment within 10% of the quote.
  - Lots built by model and grade, priced from approved-buyer bids.
  - Ageing rules: Offers → Auction after 14 days, Buy Now → Offers after 21 days.
- **One explanation of the price floor (§2.7).** The prototype says 60% of the forecast price; the repo demo's GR-D2
  says 55% of the reference value. Both are the same guardrail type with a per-customer value. Without the
  explanation, someone could "fix" the demo and break parity.
- **Back-testing aligned with the prototype's replay (§3.2).** The replay reports four things:
  - route mix, actual against flow;
  - straight-through %;
  - approvals and exceptions per day;
  - value uplift.

  The replay is Compose step 5, so the sales motion and the product show the same four numbers.
- **A "today in repo" column for every story, with file evidence.** The previous revision kept repo status in a
  separate table. Putting it next to each story makes the gaps visible where the priorities are set.
- **A short naming section (§0).** It covers Recover, Compose, Decide and Understand, and sets them against the code
  names.

**Updated**

- **Product and surface names.** The documents now say Recover, Compose (authoring), Decide (Pulse, Cases,
  Exceptions) and Understand (Analytics, Agents), per today's decision. Code and repo names are unchanged.
- **The device template** is now **device recommerce**, with channels Buy Now, Offers, Auction and wholesale lot
  (01 §5). The protection and claims angle stays, as a P1 channel: "replacement stock".
- **Story IDs and priorities.** They are re-numbered as TF (returns), SD (service desk), CR (contract refresh) and DV
  (device). Each story now names its actor (Agent or Person).
  - The old TF-11 (trade-in credit) moves into SD-04 and CR-04, where credits are actually decided.
  - The old DV-08 (lot building, P1) becomes DV-07 at P0, because wholesale lots are now a primary channel.
  - Old → new IDs:

    | Old | New |
    |---|---|
    | TF-01, TF-02, TF-03, TF-08 | unchanged |
    | TF-04 (WTI/RUL) | TF-06 |
    | TF-05 (valuation) | TF-07 |
    | TF-06 (approvals) | TF-09 |
    | TF-07 (reconciliation) | TF-10 |
    | TF-09 (grade-wear) | TF-11 |
    | TF-10 (CO2e) | TF-13 |
    | TF-11 (credit, fees) | SD-04, CR-04 and TF-14 |
    | TF-12 (calibration) | TF-15 |
    | TF-13 (batteries) | TF-16 |
    | DV-01 | unchanged |
    | DV-02 (fraud) | DV-03 |
    | DV-03 (erasure) | DV-04 |
    | DV-04 (grade read) | DV-05 |
    | DV-05 + DV-06 (price, hand-off) | DV-06 |
    | DV-07 (reconciliation) | DV-09 |
    | DV-08 (lots) | DV-07 |
    | DV-09 (replacement stock) | DV-12 |
    | DV-10 (repair, parts) | DV-11 |
    | DV-11 (GR-D5) | DV-15 |
    | DV-12 (retrain) | DV-14 |
- **The tool-fleet journey.** It moves from the four-stage view to the prototype's 8 stages (01 §4.1), and the seven
  common stages are used as the frame.
- **The demo scripts.** They are now Compose-first in seven beats: describe → adapter mapping → agent mapping →
  approve → publish to one region at 20% → Decide → Understand. This is the prototype's sales story.
- **The contract rights gate (GR-07).** It is kept. The prototype's own exception "no active contract for the serial"
  confirms that the contract is read at intake. The individual terms (theft, damage, resale limits) remain
  hypotheses to confirm.
- **Personas.** These roles are added: fleet manager, service operations, sales, site manager, technician, commercial
  manager and customer care.
- **Repo grounding.** It is now at commit `5b1fcfd`. Pieces found that serve the new flows include:
  - repair history with labour rates in the depot-repair adapter;
  - contract end dates and renewals in the leasing mock;
  - schedule triggers;
  - per-role approval limits;
  - rule suggestions from overrides.

**Deleted**

- **The "Studio first" demo wording and the four-stage journey tables as the main frame.** Compose and the seven
  stages replace them, so the old frame would only be a second, competing vocabulary.
- **The device "Own refurbished store" channel.** It is not in 01 §5 and nobody has asked for it. Marketplace
  stays in the demo pack only, for parity.
- **GR-10 (electrical safety test) as a P0 candidate.** It becomes an open question (§6). The pack's safety control
  is now the recall check, and the safety-test requirement per market is still **unconfirmed**.
- **"Donation" as an exit sub-route.** No pack mentions it. It is kept as an open question only.

---

## Summary

1. **Recover is one engine with packs** (01 §9). Tool-fleet AMS is one pack with three flows, all P0:
   - **Returns:** six paths, value-ranked, with a queue plan.
   - **Service desk:** a ticket gets its next best action: fix and return, a covered swap, or an upgrade with credit.
   - **Contract refresh:** one proposal per contract, 90 days before it ends: keep, swap to a like-life unit, or
     upgrade.

   Device recommerce is the second pack.
2. **The repo covers most of Returns' decision maths** (`valuers/tool_fleet.py`: six paths, value lines, queue plan,
   rules, simulation). It has **nothing specific to Service desk or Contract refresh**: no ticket case type, no
   estimate from past repairs, no market price lists or credit rules, no per-tool refresh logic. Those are the
   largest build items.
3. **Grade is read, not computed.** WTI and RUL are computed deterministically from telematics, PLM and repair
   history (§1.5). Telematics older than 7 days is a data-quality hold, not a silent fallback.
4. **The service-desk estimate is a nearest-neighbour estimate over the customer's own repair history.** It shows a
   range and a confidence. With ≥ 50 matches it is priced without a technician; otherwise it is a draft that a
   technician checks. Its accuracy must be shown on held-out repairs before anyone trusts it (SD-02, SD-08).
5. **Device recommerce gates:**
   - blacklist and lock (locked by the pack, and "skip under $50" is blocked);
   - the wipe certificate;
   - a price floor, which is a customer parameter;
   - payout adjustment within 10%;
   - lots over $25,000 → commercial manager.

   The ML price still needs an interval and a hand-off below the confidence threshold (default 75%, 01 §2).
6. **Back-testing equals the Compose replay.** It shows route mix actual vs flow, straight-through %, approvals and
   exceptions per day, and value uplift. It is computed **as of each decision date**, with both sides priced by the
   same valuer and a bootstrap band. The repo has rule simulation, shadow mode and pilot mode. It has no as-of
   replay and no straight-through metric.
7. **Priorities:**

   | Flow | P0 | P1 | P2 |
   |---|---|---|---|
   | Returns (TF) | 10 | 3 | 3 |
   | Service desk (SD) | 8 | 2 | 1 |
   | Contract refresh (CR) | 5 | 2 | 1 |
   | Device recommerce (DV) | 9 | 4 | 2 |

   Of the 32 P0 stories, 2 exist today (Returns valuation TF-07 and the queue plan TF-08), 15 are partial and 15
   are missing. Service desk is the least covered flow: 6 of its 8 P0 stories are missing.

---

## 0. Names used in this report

| Term | Meaning | In code today |
|---|---|---|
| Recover | The circularity product on the Decision Intelligence core (01 §1) | the app; package `di` |
| Pack | One industry template: identity, flow, guardrails, data, evidence, screens, customer layer (01 §9) | `services/modeler/templates.py`; `packs/industrial.json`; tool fleet and device built in code |
| Compose | Authoring in 5 steps: business flow → adapter mapping → agent mapping → approve → publish (01 §2) | Modeler + Connection Studio + Agents page; no 5-step wizard |
| Decide | Run-time screens: Pulse, Cases, Exceptions | Home / My work, Case, approvals |
| Understand | Analytics, Agents | Analytics, Agents pages |
| Seven stages | return/receive → match/verify → condition → value each route → decide → execute → close and learn (01 §3) | intake, evidence, valuer, decision, instructions, outcome |
| Autonomy | Prototype: Recommend only / Act within limits / Act alone, plus a confidence threshold (65–85%, default 75%) | `agent_identity.autonomy` read/propose/act; Access autonomy per role and action type (Off/Suggest/Prepare/Act); run limits (`services/agents/limits.py`); no confidence threshold |
| Guardrail types | Compliance / Data quality / Threshold / Approval, each placed at a stage (01 §9) | `TOOL_FLEET_GUARDS`, `DEVICE_GUARDS` as forbid patterns and text; no type field |
| Diversion | A customer-layer step or shortcut at a stage for a condition; skipping a compliance guardrail is blocked (01 §2) | business rules (prefer / exclude / waive / require approval); no "add a step" |

---

## 1. Tool-fleet AMS template ("after-market services · power tools", 01 §4)

### 1.1 How manufacturer-run tool fleet programmes work (public sources)

| Topic | What public sources say | Source |
|---|---|---|
| Ownership and fee | The manufacturer keeps ownership. The contractor pays one fixed monthly fee per tool ("equipment as a service"). | [S1], [S3] |
| What the fee covers | Repairs and maintenance (often "unlimited"), loan tools during repair (next working day in one country), battery and charger exchange, theft cover. | [S1] |
| Theft cover | Varies by country: up to 80% of tool cost in one market, 50% in another, full replacement in a third. | [S1] |
| Term | Typically 36 months for cordless tools and 48 months for heavy combihammers and breakers. Another market's page says about 4 years, depending on the tool type. | [S1], [S7] |
| End of contract | The tool is swapped for the current generation. If it is still productive, the contract extends (one market: month to month). One market's terms let the maker offer a new tool before the term ends, and the new tool starts its own contract. Tools cannot be bought out at the end (one market's FAQ). | [S1], [S7] |
| Trade-in credit | Returning an expired fleet tool earns a credit voucher in one market: tiered by tool, non-transferable, no cash value, to be used within 3 months. A general trade-in programme gives credit on new tools: the voucher is issued when the old tool arrives, redeemed within 90 days, open only to accounts in good standing. | [S7] |
| Repair programmes | Makers run three kinds: (a) a **flat rate** per tool, (b) a **capped or "not to exceed" quote**, and (c) **exchange**, where a replacement unit is sent (one maker: within 1–2 working days for in-warranty or fleet tools). Repair costs are often capped as a set price or as a share of the new-tool price. One programme repairs when that makes sense and replaces otherwise. | [S8] |
| Returns not made | A non-collection fee is charged for fleet tools that are not returned. Tools are retired in the tool-tracking app when returned. | [S1] |
| Scale (one programme, 2021) | About 3 million tools under fleet contracts. About 1 million tools, batteries and chargers collected a year for circular use. Spare-part reuse grew from 10,000 to 100,000 pieces in two years. | [S2] |
| What happens to returned tools | Usable parts are reused in other tools. Tools no longer fit for professional use are donated or recycled. High-quality parts are refurbished and reused. | [S1], [S2] |
| Refurbished resale | Several tool makers sell factory-reconditioned tools through their own outlets or authorised partners, with 1–2 year warranties. | [S6] |
| Connected tools | Bluetooth LE tags or built-in modules report location and usage. One telematics partnership infers **run time from accelerometer vibration**. Gateways in vans assign tags to tool cribs automatically. | [S4], [S5] |
| Safety recalls | The US consumer product safety regulator published several 2025 recalls of cordless and battery power tools. Their remedies were repair, replacement or a pro-rated refund. The remedy decides the route: a "repair" recall can go back to the fleet after the fix; a "replacement" or "refund" recall must never be re-issued or sold. | [S9] |
| Renewal timing | Contract-management guidance (May 2026) says to start renewal work 90–120 days before the *notice* deadline, not before the end date. | [S10] |

**Unconfirmed:**

- published contract lengths beyond the classes above;
- early-termination terms;
- whether the fleet programme resells returned fleet tools as "certified pre-owned" itself;
- how often a returned tool is re-issued without refurbishment;
- whether a refresh proposal 90 days ahead is standard practice in tool fleets (the prototype's 90% vs 81% renewal
  figure is *sample, modelled*).

### 1.2 Contract terms that constrain disposition (needs Legal review)

These are the questions the contract gate (GR-07) must answer *before* a route is valued. The wording is a hypothesis
to confirm with the pilot's contract owner. The prototype confirms only that the contract is looked up: "no active
contract for the serial" is one of its exceptions (01 §4.1).

| Term | Why it matters for disposition | Gate behaviour |
|---|---|---|
| Ownership stays with the manufacturer | The customer cannot sell or scrap; every route belongs to the owner. | Route allowed only for the owner's org unit. |
| Return reason (end of term, swap/upgrade, repair, theft recovered, early termination) | Theft-recovered tools may be under an insurer claim or police record. Early returns may carry charges. | Theft-recovered: hold for a person; never resell until the claim is closed. |
| Damage beyond fair wear | The customer may be charged; the tool is evidence until the charge is settled. | Hold disposition until the damage charge is closed or waived. |
| Auto-extension | A tool that is "still productive" may stay on contract, so a return may be a swap of a working tool. | Re-issue paths favoured; no scrap while the unit is still under a live line. |
| Cover terms (service desk) | Decide whether a covered swap is allowed (sample: "swap allowed for cordless tools"; 01 §4.2). | Covered swap is offered only when the cover is active and the terms allow it. |
| Regional resale limits | A maker may not allow pre-owned sale in some markets, or only through authorised outlets. | Pre-owned sale excluded by a market/channel table (**unconfirmed** that such limits exist). |
| Battery and electronics rules | Lithium-ion packs have transport and take-back duties (e.g. EU Battery Regulation 2023/1542; applicability per market **unconfirmed**). | Batteries as their own class (TF-16). |
| Customer data on connected tools | A tag or app record links a tool to a site and a worker. | Unlink the tool from the customer's account before re-issue: a step, not an erasure certificate. |

### 1.3 The seven agents across the three flows, and the code that serves them

The prototype runs one decision chain of seven agents for every tool-fleet flow (01 §3). Service desk and Contract
refresh reuse the chain; only the inputs and outputs change. The ticket runs intake → estimate → cover check →
valuation → disposition → follow-through. The contract runs intake → condition and life → refurbished-stock matching
→ valuation → disposition (01 §4.2, §4.3).

| # | Agent | Returns | Service desk | Contract refresh | Code that serves it today |
|---|---|---|---|---|---|
| 1 | Intake | One case per returned tool from a fleet contract, service order, trade-in or pool event | One case per ticket, or per batch from a site manager | One case per contract entering the 90-day window | `services/cases/intake.py` `open_case` (reasons `rma`, `lease_end`, `trade_in`, `contract_end`, `iot_alarm`, `manual`; dedupe on asset + reason). Webhooks, sync and file drops (`connectors/`, `fabric_records`). Schedule and event triggers (`workflow/triggers.py`). **No** ticket or refresh reason. |
| 2 | Condition and life | Grade and fault read from the repair workbench; RUL from usage and repair history | Fault from the ticket or technician; age, past repairs, life used (for the upgrade rule) | Hours and faults per tool on the contract, last 12 months; life left per tool | Depot-repair adapter has authority over `grade` and `test_result` and also reads `teardown_findings` (`connectors/adapters/depot_repair.py`). IoT adapter reads `run_hours` (`adapters/aws_iot.py`). PLM reads (`repositories/plm.py`). Tool-fleet case takes `rul`/`partRul` as **inputs**. Grade falls back to `estGrade`. |
| 3 | Demand discovery | Fleet renewals and orders, pool shortages, open repair orders, trade-buyer bids | Refurbished stock for a covered swap; the current model for an upgrade | Refurbished like-life units in stock or in the returns queue | Tool-fleet case demand `dem` (lease, so, bid, proj, wo, rcq) as sample data in `valuers/tool_fleet.py`. The leasing mock serves contract end dates and renewals (`source-sim/sim/vendors/oracle_lease`). Seeded agent `finder` (`find_demand`). |
| 4 | Fit-for-use | Certifies harvested parts only above Quality's threshold | (none) | Certifies refurbished units as "like-life" | `BASEP["rulMin"] = 50` and GR-03 in `tool_fleet.py` / `templates.py`. |
| 5 | Valuation | Prices six paths net of cost, logistics and time held | Prices fix / covered swap / upgrade for the customer and the margin, net of parts, labour, credit and logistics | Prices the proposal: fee, saving against new, likelihood to renew | `tool_fleet._value` (value lines `ValueLine`: type, label, basis, amount). `engine/predictor.py`, `engine/calibration.py`. **No** estimate, price list, credit or renewal logic. |
| 6 | Disposition | Plans the whole queue: each order once, refurbishment within repair slots | Picks the next best action, or splits a batch | One proposal per contract: keep / like-life swap / upgrade | `tool_fleet._decide1` (best, second, uplift vs default route, rules), `_plan_queue` (slots), `engine/pool.py` `solve_pool`. Business rules (`modeler/apply.py`). |
| 7 | Follow-through | Hands the decision to the executing application, reminds the owner, records the outcome | Service order / sale order / take-back order on market terms; credit released when the tool arrives | Emails the proposal (after approval), drafts contract lines, reserves refurbished tools | `playbooks/case_autopilot.py` (submit, wait for approval, resend). Instructions and execution (`services/instructions`, `services/execution`). Seeded agents `coordinator` and `reconciler`. Pilot mode holds instructions (`actions/org_pilot.py`). |

**Autonomy (Compose step 3).**

| Prototype autonomy | Repo equivalent | Status |
|---|---|---|
| "Recommend only" | autonomy `propose` (held as a proposal) | Exists |
| "Act alone" | autonomy `act` | Exists |
| "Act within limits" | Run limits (count, bulk) | Partial: no value limits or guardrail-typed limits |

The **confidence threshold** (below it, the item goes to a person) is **missing**. Agents never approve, publish or
override (`services/agents/forbidden.py`), whatever the autonomy.

### 1.4 Data per system type (all three flows)

The pack lists seven systems (01 §4.1): ERP, CRM, fleet contract system, connected-tool telematics, service desk,
spare-parts catalogue, and a legacy depot repair log that needs a connector.

| System type | Data | Used by flow | Repo today |
|---|---|---|---|
| Fleet contract system / CRM | contract id, serials, start, end, term, fee, return reason, cover terms and dates, swap rights, renewal status, theft claim, damage charge, customer history (upgrades this year) | all three: GR-07, cover check, refresh window, renewal demand 60 days ahead | Leasing mock has contract end, renewals and asset returns; there is no tool-fleet contract feed. |
| Service desk / field service | ticket id, serial, reported fault, site, batch id, requester role, loaner promised | Service desk intake | The ITSM/field-service mock has work orders with a labour rate, for the industrial demo only. |
| ERP (SD/MM/FI, service) | material, serial, stock location, sales orders, service orders, take-back orders, purchase requisitions for new pool units, credit memos | all | ERP and procurement mocks |
| Repair centre / depot repair (+ legacy log) | repair orders, fault codes, components replaced with run hours at replacement, labour hours, parts cost, labour rate, **grade A–D**, test results, turnaround | Returns (grade), Service desk (**past repairs** for the estimate), Refresh (refurbished stock) | The depot-repair adapter maps grade, cost, hours, `parts_cost` and `labour_rate`. A history of past repairs per family / age / fault is **not** queried. |
| Price lists, labour rates, credit rules (per market) | parts price list per market and month, labour rate per hour (sample €42/h DE, €46/h FR), credit rules (versioned), fleet rate card | Service desk, Refresh | missing |
| PLM (read-only) | BOM per class and revision, rated life per wear component, criticality, condemn limits, **successor model and end-of-parts date** | Returns (RUL), Refresh (upgrade when parts end before the next term) | PLM reads exist; no rated-life or end-of-parts field |
| Connected-tool telematics | run hours, load profile, temperature, drops, **last seen** (freshness < 7 days) | Returns (RUL, guardrail), Refresh (usage per tool) | IoT mock and adapter read `run_hours` and vibration for motors; no freshness check |
| Recall register (manufacturer's or regulator's) | affected model / serial range, remedy (repair, replace, refund) | all: safety recall guardrail | missing |
| Spare-parts catalogue | parts on open repair orders, prices | Returns (harvest), Service desk | sample demand `wo` in the valuer |
| Remarketing / pre-owned outlet | bids, listing prices, fees | Returns (pre-owned sale) | remarketing mocks |
| Carbon accounting | factors per class and route | CO2e on the card (brief item 6) | carbon mock; not in valuers |

**Canonical entities** (01 §4.1): tool, return event, condition grade, remaining life, demand signal, market price,
cost rate. Service desk adds **ticket**, **price list / credit rule** and **cover term**. Refresh adds **contract
line**. That breaks the pack contract's "about seven entities" (01 §9). The extra entities could also be modelled as
kinds of demand signal and cost rate, which is a design choice for plan 9.

### 1.5 Wear-and-tear index and RUL: deterministic and auditable

The grade is **read** from the repair centre. WTI and RUL are **computed** from telematics, PLM and repair data, and
every number must be explainable (brief item 5a). ISO 13381-1:2025 frames prognosis as predicting RUL "with a
satisfactory level of confidence" and says statistical or experience-based approaches are needed [R1]. That supports
a rule-based model with a stated confidence class. The prototype's model catalogue lists a "remaining-life estimator
(survival model)" (01 §3). A survival model can come later as a *candidate* with maker-checker promotion. The pilot
starts deterministic.

**Inputs per tool (serial `S`, class `C`, BOM revision `r`)**

| Symbol | Meaning | Source system |
|---|---|---|
| `L_i` | rated life of wear component `i` (hours, impacts or cycles) | PLM, per class and revision |
| `w_i` | criticality weight of component `i` (sum 1) | PLM or engineering table (owner: Quality) |
| `h` | run hours of the tool (or impacts) at evaluation | telematics; fallback: contract months x class median duty |
| `s_hi` | share of run time at high load or temperature | telematics |
| `α_i` | load sensitivity of component `i` | engineering table (owner: Quality) |
| `n_e`, `p_e` | count of events of type `e` (overheat, drop, overload) and their penalty in equivalent hours | telematics counts; penalty table (owner: Quality) |
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

**Confidence class** (shown next to RUL; it drives the hand-off and the 75% default threshold):

| Class | When | Effect |
|---|---|---|
| High | Telemetry covers ≥ 90% of contract days, the last reading is under 7 days old (pack guardrail), and the repair history is complete | Normal routing |
| Medium | Telemetry gaps were filled with the class's median duty, or a component has no replacement record | Normal routing, class shown |
| Low | No telemetry, or the last reading is 7 days old or more. `h` is estimated from contract months, and RUL is shown as a range using the class's P10 and P90 duty. | Never routes to re-issue or pool on its own; the telematics guardrail raises an exception |

**Cross-check with the read grade.** Disagreements go to a person, never silently. "Telematics and inspection
disagree" is a pack exception (01 §4.1).

- Grade A or B and WTI ≥ 60, or grade D and WTI ≤ 20 with no damage code: an exception.
- RUL_tool below the route threshold but grade A: the route is blocked, and the component is named.

**Illustrative worked example** (numbers invented for the demo, not real ratings). Combihammer class, 820 run hours,
30% at high load, piston kit replaced at 500 h, α = 0.5 for the motor, gearbox and piston kit, and 0 for the
electronics:

| Component | `L_i` (h) | `w_i` | `U_i` | consumed | RUL_i |
|---|---|---|---|---|---|
| Motor armature | 1,200 | 0.4 | 820 x 1.15 = 943 | 79% | 21% |
| Gearbox | 1,500 | 0.3 | 943 | 63% | 37% |
| Electronics module | 2,000 | 0.2 | 820 | 41% | 59% |
| Piston and seal kit | 600 | 0.1 | 320 x 1.15 = 368 | 61% | 39% |

WTI = 100 x (0.4·0.79 + 0.3·0.63 + 0.2·0.41 + 0.1·0.61) = **65**. RUL_tool = **21%** (motor).

What each flow does with this tool:

- **Returns:** re-issue is blocked (motor at 21%). Refurbishing with a new armature lifts RUL to 37% (gearbox),
  which is below the 40% refurbish threshold. So the electronics module (59%) is harvested for an open repair order
  and the rest is recycled.
- **Contract refresh:** 21% < 25%, so the proposal is a **like-life swap**.
- **Service desk:** the tool is past 50% of its life, so an **upgrade** may be offered.

Each phrase is a value line with its source, table version and timestamp, like the existing `ValueLine` in the
valuer.

**Audit record per evaluation:** the input snapshot (hours, events, repair rows, PLM revision), the table versions,
the rule-set version and the output. Re-running the same snapshot gives the same numbers.

**Calibration (later, by a person):** compare predicted RUL with the repair centre's teardown findings. Adjust `L_i`
or `α_i` through the Modeler's maker-checker lifecycle, never automatically. Calibration and model candidates exist
for the industrial template only (`actions/models.py`, `engine/calibration.py`).

### 1.6 Personas and roles

| Persona | Flows | Goal | Repo role |
|---|---|---|---|
| Fleet services lead (pack author) | all | Describes the business in Compose; owns the pack | Admin / Developer |
| Fleet desk / contract admin | Returns, Refresh | Contract lines, charges, re-issue to renewals | Planner |
| Fleet manager | Returns, Service desk | Approves repairs over $600 | Approver (new limit) |
| Service operations | Returns, Service desk | Approves write-offs under 24 months | Approver (new limit) |
| Service desk agent / technician | Service desk | Posts faults; checks draft estimates (< 50 matches) | Engineer |
| Site manager (customer side) | Service desk | Sends a batch of tools | external; no repo role |
| Sales | Refresh, Service desk | Approves credits over $300; owns the customer conversation | new role or Approver scope (**missing**) |
| Repair centre lead | Returns | Grade, refurbish, harvest; repair-slot capacity | Engineer |
| Tool pool planner | Returns | Keep loaner pools stocked | Planner |
| Remarketing lead | Returns | Pre-owned sale, bids, outlet | Planner / Approver |
| Service parts planner | Returns | Certified used parts for repair orders | Planner |
| Quality | all | Rated-life tables, fit-for-use threshold, grade-wear exceptions, recall quarantine | Approver (rules) |
| Finance | all | Holding cost, credits, charges, recovered value | Finance |
| Sustainability lead | Returns | Recycling certificates, CO2e | Approver (exit) |
| Agents (the seven) | all | Gather, value, propose; never approve | agent registry |

### 1.7 Guardrails shared by the three flows (needs Legal review for recall and contract items)

Types follow 01 §9. "Pack" means locked by the pack: a customer can tighten it but not weaken, suspend or remove it.

| Id | Guardrail | Type | Stage | Owner | Origin | Repo status |
|---|---|---|---|---|---|---|
| GR-01 | Grade C and D never issued to a fleet without refurbishment | Compliance | decide | Fleet desk | demo | exists (`TOOL_FLEET_GUARDS` forbid) |
| GR-02 | Refurbishment always ends in a named fleet contract, sales order or pool request | Compliance | decide | Repair centre lead | demo | exists (text guard; valuer `dest`) |
| GR-03 | Harvested parts certified only at or above the fit-for-use threshold | Threshold | condition | Quality | demo | exists (`rulMin` 50) |
| GR-04 | Holding cost rate set by Finance | Threshold | value | Finance | demo | exists (text guard) |
| GR-05 | Every decision approved by a named owner before execution | Approval | decide | Governance board | demo | exists. Relaxed by threshold in a Recover flow (see the note below this table) |
| GR-06 | Recycling only through a certified recycler, certificate and CO2 record on file | Compliance | execute | Sustainability | demo | text only |
| GR-07 | Contract disposition right confirmed: active contract for the serial, owner, reason, no open claim or charge | Compliance | match/verify | Fleet desk | this report + 01 exception | missing |
| GR-12 | **Safety recall check**; an active recall → quarantine (a diversion that adds a step) | Compliance (pack) | match/verify | Quality | 01 §4.1 | missing |
| GR-13 | **Telematics under 7 days old**, else the RUL is low confidence and an exception opens | Data quality (pack) | condition | Quality | 01 §4.1 | missing |
| GR-14 | **Repair over $600 → fleet manager** | Approval (stated) | decide | Fleet manager | 01 §4.1 | partial: per-role approval limits (`core/policy.py` `STARTING_LIMITS`, `actions/decisions.py` limit check); not tied to repair cost or to a named role |
| GR-15 | **Write-off under 24 months → service operations** | Approval (added in plain words) | decide | Service operations | 01 §4.1 | missing |
| GR-08 | RUL and grade certified before refurbish or redeploy (brief item 3) | Compliance | condition | Quality | brief | partial (RUL is an input) |
| GR-11 | Customer account unlinked from a connected tool before re-issue | Compliance | execute | Fleet desk | this report | missing |

GR-09 (low RUL confidence never auto-routes) is now part of GR-13 and the confidence class. GR-10 (electrical safety
test) moved to the open questions (§6).

**Note on GR-05 versus straight-through.** The demo requires a named approver for every decision. A Recover flow
reports straight-through % (sample 81%, *modelled*). Both can hold: the demo pack keeps GR-05 for parity, and a
Recover flow sets GR-05 as an approval *by threshold*. Items under all thresholds, above the confidence threshold and
with no guardrail hit are approved in a batch or by policy. Who signs that policy is a governance decision for plan 9
(**open**).

**Diversions (customer layer, 01 §4.1):**

- active safety recall → quarantine;
- key account → account-manager review;
- "new tool under 3 months: skip the recall check" → **blocked**, because it skips a compliance guardrail.

---

### 1.8 Flow A: Returns (the Recover case)

#### 1.8.1 How it works

A tool comes back from one of four sources:

- a fleet contract (end of term, swap);
- a service order (beyond economic repair);
- a trade-in;
- tool-pool excess.

The flow then:

1. Reads the contract.
2. Reads the grade from the repair workbench.
3. Computes life left.
4. Finds named demand for every path.
5. Values all six paths.
6. Plans the whole queue so that each order is filled once and refurbishment stays within repair-centre capacity.
7. Hands the approved decision to the executing application (01 §3, §4.1).

**Paths.** The six repo paths are the prototype's paths, so they stay for parity.

| Path (repo id) | What happens | Executing application | Owner | Repo pre-condition |
|---|---|---|---|---|
| Re-issue to fleet (`release`) | Issued against a named renewal or order | Fleet contract system | Fleet desk | grade A; a fleet order that needs the unit in time |
| Refurbish → place (`refurb`) | Always ends in a named contract, buyer order or pool request | Repair-centre work orders | Repair centre lead | grade B/C and RUL ≥ 40%; a named order (GR-02) |
| Tool pool (`redeploy`) | Loaner or pool stock transfer | ERP stock transfer | Tool pool planner | not grade D; RUL ≥ 45%; a pool shortage |
| Pre-owned sale (`resell`) | Sold to a named trade buyer or through the outlet | Pre-owned sales channel | Remarketing | firm bid at or above grade, else an outlet estimate |
| Harvest parts (`harvest`) | Certified parts for *open repair orders* | Teardown and spare parts | Service parts planner | part RUL ≥ 50% and an open repair order |
| Recycle (`exit`) | Certified recycling plus a circularity record | Recycler portal and ledger | Sustainability | always feasible; certificate (GR-06) |

**Note on the Compose route list.** The Compose pack lists different routes: redeploy, refurbish and re-rent, fix and
return, upgrade offer, harvest and recycle (01 §4.1). "Fix and return" and "upgrade offer" are Service desk outcomes,
and "pre-owned sale" is missing from that list. This report reads the pack's route list as the union of the three
flows. It keeps pre-owned sale in Returns. Whether pre-owned sale belongs in the pilot is an **open question** (§6).

#### 1.8.2 Journey (8 stages, 01 §4.1)

| # | Stage | What happens | Agent → person |
|---|---|---|---|
| 1 | Tools in use on site | Contract with end dates and swap rights; renewal demand seen 60 days ahead | Demand discovery watches |
| 2 | Repair or return requested | Fleet app; a loaner is promised | Intake opens the case |
| 3 | Pickup and inbound | Logistics; WMS receipt; kit check | Intake tracks |
| 4 | Intake and diagnosis | Technician grade, fault, estimate, remaining life, safety rules (GR-07, GR-12, GR-13) | Condition and life; a person on exceptions |
| 5 | Best next life decided | All paths valued; queue plan; best and second best, explained against the standard route | Valuation, Disposition |
| 6 | Approved and executed in place | Within thresholds: straight through. Otherwise the fleet manager, service operations or the path owner approves. | Follow-through |
| 7 | Customer stays productive | Back inside the turnaround promise | Follow-through reminds |
| 8 | Learn and report | Actual costs, pass rates and prices retrain the models; CO2 and parts reuse counted per tool | Analytics |

**Four value patterns the demo must show** (01 §4.1). Pattern (d) is what the repo's queue plan
(`_plan_queue`) does. Patterns (a)–(c) are path comparisons the valuer already makes. Whether the sample world holds a
case for each pattern was **not checked** case by case.

- a) A tool being repaired for a contract that is about to end → issue it to a renewal instead.
- b) A grade A return that would be sold while a pool is short → send it to the pool and cancel the new-unit
  requisition.
- c) A tool about to be scrapped whose parts are on open repair orders → harvest and certify those parts.
- d) Two returns promised to the same renewal → the queue plan fills each order once.

#### 1.8.3 Exceptions and KPIs

**Exceptions (01 §4.1):**

| Exception | Owner |
|---|---|
| No active contract for the serial | fleet desk |
| Telematics and inspection disagree | Quality |
| Repair over the limit | fleet manager |
| Write-off under 24 months | service operations |
| Inspection backlog at a depot | repair centre lead |

**KPIs.** The six pack KPIs come first (01 §4.1), with their *sample, modelled* values (prototype script, line 1912)
and definitions. The rest are kept from the previous revision.

| KPI | Sample value (*modelled*) | Definition |
|---|---|---|
| Value recovered per tool | $224 | realised net (value lines minus costs and holding) / returns |
| Days to next use | 6.4 | receipt to the next productive use (issue, pool or sale) |
| Redeploy rate | 46% | share of returns re-issued or pooled |
| Straight-through % | 81% | cases closed without a person changing data or the route (approval by policy counts) |
| Upgrade offers accepted | 18% | accepted / offered (comes from Service desk and Refresh) |
| % held by guardrails | 4.2% | cases stopped by any guardrail / cases |
| Uplift vs standard route | (none) | chosen net minus the default route's net (`_default_path`) |
| Avoided new purchases | (none) | pool requisitions and renewals met from returns, at new-unit cost |
| Part reuse | (none) | certified parts issued to repair orders |
| Grade-wear disagreement rate | (none) | exceptions / graded returns |
| CO2e avoided | (none) | per route, deterministic factors (brief item 6) |

#### 1.8.4 Returns user stories

"Today in repo": **exists** means it works for tool-fleet cases now; **partial** means a piece exists, as named;
**missing** means nothing specific exists.

| Id | P | Story | Given / When / Then | Actor | Today in repo |
|---|---|---|---|---|---|
| TF-01 | P0 | As fleet desk, I want one case per returned tool, so nobody keys returns | Given a contract-end, swap, service-order or pool event with a serial, When it arrives by webhook, file or sync, Then one case opens with contract, class and reason, and a second event for the same serial and reason is refused as a duplicate | Agent (Intake) | **partial**: `cases/intake.py` `open_case` with dedupe (`intake_key`), `tool_fleet_case`; no fleet-contract or pool feed |
| TF-02 | P0 | As fleet desk, I want the contract right checked first (GR-07) | Given a case, When there is no active contract for the serial, or the contract says theft-recovered, open damage charge or not our owner, Then every route is blocked with the term named and an exception goes to the fleet desk | Agent checks; Person clears | **missing**: no contract data in the valuer or packs |
| TF-03 | P0 | As repair centre lead, I want the grade read from my workbench, never recomputed | Given a repair order with grade and test results, When it is confirmed, Then the case shows the grade with its source and age; an estimated grade is shown only when the workbench grade is late, labelled "estimate" | Agent (Condition) | **partial**: `adapters/depot_repair.py` has authority over `grade`; `tool_fleet._grade` falls back to `estGrade` (not labelled on the card) |
| TF-04 | P0 | As Quality, I want a safety recall check with quarantine (GR-12) | Given a recall register entry for the model or serial range, When a tool of that range is at match/verify, Then it is diverted to quarantine; re-issue, pool and sale are blocked; the remedy (repair / replace / refund) decides what remains; a customer diversion that skips the check is refused | Agent checks; Person (Quality) releases | **missing** |
| TF-05 | P0 | As Quality, I want stale telematics caught (GR-13) | Given the last telematics reading is 7 days old or more, When the case is evaluated, Then RUL is low confidence, an exception opens, and re-issue/pool are not proposed on their own | Agent | **missing**: `adapters/aws_iot.py` reads `run_hours`; no age check |
| TF-06 | P0 | As Quality, I want WTI and RUL per tool and per part with a confidence class (§1.5) | Given run hours, load share, events, BOM ratings and replacements, When evaluated, Then WTI, RUL per component and RUL_tool show with each input's source and table version, and re-running gives the same numbers | Agent (Condition) | **missing**: `rul`, `partRul` are inputs in `tool_fleet.py` |
| TF-07 | P0 | As remarketing lead, I want all six paths valued against named demand, with best, second best and the standard route explained | Given grade, RUL, demand and bids, When evaluated, Then six paths show net with value lines; blocked ones show why; best and second are named; uplift vs the default route shows | Agent (Demand, Valuation) | **exists**: `tool_fleet._value`, `_decide1` |
| TF-08 | P0 | As tool pool planner, I want the whole queue planned (pattern d) | Given open returns competing for orders and repair slots, When planned, Then each order is filled once, refurbishment stays within slots, and losing returns say why | Agent (Disposition) | **exists**: `tool_fleet._plan_queue` (`slots`), `engine/pool.py` |
| TF-09 | P0 | As fleet manager / service operations, I want only threshold cases (GR-14, GR-15) | Given a proposal, When repair cost > $600, or a write-off of a tool younger than 24 months, or confidence < the threshold, or a guardrail fired, Then it waits for the named role; otherwise it goes straight through within the agent's autonomy | Agent sorts; Person approves | **partial**: approval limits per role (`actions/decisions.py`, `core/policy.py`); no repair-cost or age rule, no confidence threshold |
| TF-10 | P0 | As Finance, I want follow-through and the outcome recorded | Given an approved path, When the executing application confirms, Then realised vs predicted shows, variance above tolerance becomes a task, and the case closes | Agent (Follow-through) | **partial**: instructions, `case_autopilot` resend, `reconciler`; tool-fleet executing apps not mapped |
| TF-11 | P1 | As Quality, I want telematics-vs-inspection disagreements flagged | Given grade A and WTI ≥ 60 (or grade D and WTI ≤ 20), When evaluated, Then an exception opens naming the components | Agent flags; Person decides | **missing** (needs TF-06) |
| TF-12 | P1 | As account manager, I want key-account returns diverted to my review | Given a case for a key account, When decided, Then it waits for account-manager review | Agent; Person | **partial**: business rules with action "require approval" scoped by owner (`modeler/apply.py`); no named reviewer |
| TF-13 | P1 | As sustainability lead, I want CO2e and the recycling certificate on the card | Given any route, When valued, Then CO2e avoided per route shows from a versioned factor table; recycle cannot close without a certificate | Agent; Person | **partial**: carbon on industrial screens; GR-06 text only |
| TF-14 | P2 | As fleet desk, I want non-return fees as value lines | Given a contract line closed without the tool, When valued, Then the fee shows and posts | Agent | **missing** |
| TF-15 | P2 | As Quality, I want to calibrate rated life from teardown findings | Given 3 months of teardown verdicts, When I fit, Then a candidate table with error metrics is proposed and another person promotes it | Agent fits; Person promotes | **partial**: `model.fit` for industrial only |
| TF-16 | P2 | As remarketing lead, I want batteries routed as their own class | Given a returned pack, When valued, Then hazardous-transport and take-back routes apply | Agent | **missing** |

---

### 1.9 Flow B: Service desk ("every tool in for service, its next best action", 01 §4.2)

#### 1.9.1 How it works

A customer or site manager raises a repair ticket for one tool or a batch. Today a manual quote takes days (prototype
baseline: 4 days, *sample, modelled*). The flow:

1. Drafts an **estimate from similar past repairs** (same family, age band and fault, last 3 years).
2. Checks the **cover**.
3. Prices three options for the customer and the margin:
   - **fix and return**;
   - **covered swap** from refurbished stock, when the cover terms allow;
   - **upgrade with credit** to the current model.
4. Proposes the best option, net of parts, labour, credit and logistics.
5. On approval, creates the orders on the market's terms: a service order, or a sale order plus a take-back order.
   The credit is released when the old tool arrives.
6. Sends the taken-back tool into **Returns**.

That link is what makes service desk a Recover flow rather than a quoting tool: the upgraded customer's old tool
becomes supply for the returns queue.

**What public practice supports.** Tool makers run flat-rate repairs, capped quotes and exchange units [S8]. Fleet and
trade-in programmes give credits against new tools, under rules that differ by market [S7]. So the three options
exist in the market. The new part is choosing among them per ticket from the customer's own history.

**Estimate from past repairs.** This is case-based estimation: retrieve the k most similar past cases and adapt
their costs. The literature says retrieval is reliable but adaptation is the weak point, and that ensembles or
regression on top of the neighbours help when the case base is small [S11]. Most of that work is in construction and
maintenance, not tool repair, so accuracy at production scale is **unconfirmed** here. For the pilot that means:

| Element | Rule | Why |
|---|---|---|
| Similarity key | product family + age band + fault code; widen to family + fault if fewer matches | the prototype's key (01 §4.2) |
| Window | last 3 years | prototype |
| Point estimate | median of the matches' parts + labour, re-priced at **today's** market price list and labour rate | old repairs carry old prices; re-pricing keeps the estimate current and explainable line by line |
| Range | P10–P90 of the re-priced matches, shown with the estimate | sample: $430, range $395–470, 92% confidence |
| Auto-price threshold | ≥ 50 matches and a range width under a set share → priced without a technician | prototype: ≥ 50; the width rule is this report's addition, so that a wide spread of 50 cases does not auto-price |
| Draft | fewer than 50 matches, or a fault that is unclear → draft estimate; a technician check is booked; options re-run when the fault is posted | prototype (sample ticket: 37 matches → draft) |
| Accuracy | shown on held-out repairs (prototype: last 8 weeks, per family): MAE and the share of actuals inside the range | prototype; it also makes the threshold defensible |

**Per-market rules** (01 §4.2):

- labour rates (sample: €42/h DE, €46/h FR);
- parts price lists per market and month;
- **credit rules** per market, versioned (sample "credit rules v3");
- cover terms (sample "swap allowed for cordless tools").

Markets are DE, UK, US and AU, with FR in pilot. In Compose, FR is a region publish at 20% (§4).

**Business rule:** upgrade only when the tool is past 50% of its life, or when the cover rules allow it (01 §4.2;
prototype script, line 563).

**Batches:** a site manager sends a batch. The flow decides per tool and returns one split, for example 22 tools →
upgrade 9, fix 11, covered swap 2 (*sample*). It produces one sale order, one service order and one delivery back to
the site.

**"Test this decision":**

- a credit lever shows expected margin against the credit offered;
- take-up comes from the customer's last 24 months of offers;
- levers also exist for repair cost (80–150% of the price list) and for wait.

The prototype computes expected margin as take-up x upgrade margin plus (1 − take-up) x fix margin. Take-up rises
with the credit. The repo's rule simulation (`modeler/simulate.py`) compares rule sets; it has no lever-based
what-if.

#### 1.9.2 Journey

| # | Stage (common seven) | Service desk step | Agent → person |
|---|---|---|---|
| 1 | Return / receive | Ticket raised (tool or batch); loaner promised | Intake |
| 2 | Match / verify | Serial on an active contract (GR-07); recall (GR-12); cover status and dates | Intake, Condition |
| 3 | Condition | Fault from the ticket or technician; age; past repairs; life used | Condition and life; technician on drafts |
| 4 | Value each route | Estimate from past repairs; fix / covered swap / upgrade priced for customer and margin | Valuation |
| 5 | Decide | Next best action, or a split for a batch; business rule on upgrades | Disposition; fleet manager if repair > $600 (GR-14); sales if credit > $300 (GR-C1) |
| 6 | Execute | Service order or sale order + take-back order on market terms; proposal valid 14 days (sample) | Follow-through |
| 7 | Close and learn | Customer's choice, actual repair cost, take-up feed the estimate and the take-up model | Analytics |

#### 1.9.3 Guardrails and rules (service desk)

| Id | Rule | Type | Owner | Repo status |
|---|---|---|---|---|
| GR-07, GR-12, GR-14, GR-15 | Shared (§1.7) | | | see §1.7 |
| GR-S1 | Instant price only with ≥ 50 matching past repairs (and a range under the set width); otherwise a technician checks | Data quality | Service operations | missing |
| GR-S2 | Covered swap only while the cover is active and its terms allow a swap for that class | Compliance | Fleet desk | missing |
| GR-S3 | Prices, labour rates and credits only from the market's current, approved version | Compliance | Finance (per market) | missing |
| GR-C1 | Credit above $300 → sales approval (shared with Refresh) | Approval | Sales | missing |
| BR-S1 | Upgrade only past 50% of life or when cover rules allow (business rule, can be tuned) | Business rule | Fleet services lead | missing |

#### 1.9.4 KPIs

The *sample, modelled* values are from the prototype script, line 575.

| KPI | Sample | Definition |
|---|---|---|
| Ticket to priced next best action | 8 s (was 4 days manual) | median time, ticket received → priced option set |
| Instant estimates | 82% | tickets priced without a technician / tickets |
| Upgrade take-up on uncovered tickets | 13% (was 6% with repair-only quotes) | accepted upgrades / uncovered tickets offered one |
| Estimate accuracy | per family, held-out | MAE and range coverage on repairs closed in the last 8 weeks |
| Margin per ticket | (none) | realised margin net of parts, labour, credit and logistics |
| Taken-back tools into Returns | (none) | count and value recovered (links to Flow A) |

#### 1.9.5 Data (beyond §1.4) and the legal points

- **Data.**
  - Service desk: tickets with fault text or code, batch id, requester.
  - Repair history: ≥ 3 years of closed repairs with family, age at repair, fault code, parts lines, labour hours,
    market.
  - Price lists, labour rates and credit rules per market, with versions and dates.
  - Cover terms per contract.
  - The customer's past upgrade offers and answers (24 months).
- **Legal review:** credit rules, cover terms and per-market pricing are contract and consumer-pricing matters.
  Showing a customer a price that an agent prepared, even after a person approves it, needs Legal review per market.

#### 1.9.6 Service desk user stories

| Id | P | Story | Given / When / Then | Actor | Today in repo |
|---|---|---|---|---|---|
| SD-01 | P0 | As service operations, I want one case per ticket (or batch) | Given a ticket from the service desk with serial(s), fault and site, When it arrives, Then one case opens per ticket (a batch keeps its tools as lines), duplicates refused, contract, cover and recall checked (GR-07, GR-12) | Agent (Intake) | **missing**: no ticket reason in `intake.REASONS`; the ITSM mock work orders serve the industrial demo only |
| SD-02 | P0 | As service operations, I want an estimate from similar past repairs | Given ≥ 50 closed repairs of the same family, age band and fault in 3 years, When the ticket is evaluated, Then an estimate with range, confidence, match count and price lines (parts, labour at the market rate, test) shows and is priced without a technician; under 50, a draft shows and a technician check is requested | Agent (Valuation); Person (technician) on drafts | **missing**: repair cost, hours, `parts_cost`, `labour_rate` exist per repair order in `adapters/depot_repair.py`, but nothing queries history by similarity |
| SD-03 | P0 | As Finance, I want price lists, labour rates, credit rules and cover terms per market as versioned tables | Given DE, UK, US, AU (and FR in pilot), When a ticket is priced, Then the lines cite the market's table and version; a table change goes through maker-checker | Person maintains; Agent reads | **missing** (the lifecycle exists for flows, not for tables) |
| SD-04 | P0 | As fleet services lead, I want fix / covered swap / upgrade priced for the customer and the margin | Given the estimate, cover and the customer's take-up, When valued, Then each option shows the customer price, margin, days out of use and why; covered swap only under GR-S2; upgrade only under BR-S1; credits under GR-C1 | Agent (Valuation, Disposition) | **missing** |
| SD-05 | P0 | As service operations, I want the approved option executed on market terms | Given an approved option, When sent, Then a service order, or a sale order plus a take-back order, is created in ERP service, the credit is released on receipt of the old tool, and the taken-back tool opens a Returns case | Agent (Follow-through); Person approves | **partial**: instruction pipeline and `case_autopilot`; no service-desk instruction templates; no link to Returns intake |
| SD-06 | P0 | As a technician, I want options re-run when I post the fault | Given a draft ticket, When the fault is posted, Then the estimate firms up and the options re-run without re-keying | Agent | **partial**: `case.reevaluate`, the `on_case` trigger (`workflow/triggers.py`) |
| SD-07 | P0 | As a site manager's account owner, I want a batch decided per tool and returned as one split | Given a batch of N tools, When decided, Then each tool has its option, the batch shows the split (e.g. upgrade 9 / fix 11 / swap 2) and one set of orders and one delivery | Agent; Person approves | **missing** |
| SD-08 | P0 | As service operations, I want estimate accuracy on held-out repairs before trusting instant prices | Given repairs closed in the last 8 weeks, When the model page opens, Then MAE and range coverage per family show; a family below the agreed accuracy loses instant pricing | Agent computes; Person sets the bar | **missing** (model validation exists for the industrial predictor only) |
| SD-09 | P1 | As sales, I want to test a credit before offering it | Given a ticket, When I move the credit or the take-up lever, Then expected margin and whether the decision flips show; nothing is sent | Person | **partial**: `modeler/simulate.py` compares rule sets; no lever what-if |
| SD-10 | P1 | As FR pilot owner, I want the market published at 20% of volume | Given the flow published for FR, When tickets arrive, Then 20% follow the flow and the rest the standard quote, and the report compares them | Platform | **partial**: pilot mode per org unit (`actions/org_pilot.py`), shadow mode; no % split |
| SD-11 | P2 | As analytics, I want the take-up model learned from offers | Given 24 months of offers and answers, When fitted, Then a candidate take-up curve with error is proposed and another person promotes it | Agent; Person | **missing** |

---

### 1.10 Flow C: Contract refresh ("one proposal per expiring contract, built ahead", 01 §4.3)

#### 1.10.1 How it works

Ninety days before a fleet contract ends, the flow builds **one proposal** for the whole contract:

- **keep** tools with good remaining life;
- **swap** worn tools for refurbished units whose life is close to the rest of the fleet ("like-life"), so the whole
  contract ages evenly;
- **upgrade** where parts end before the next term.

The proposal shows the fee, the saving against new tools and the likelihood to renew. Credits above $300 need sales
approval. On approval, the proposal is emailed, the contract lines are drafted and the refurbished tools are
reserved.

**Public practice.** At the end of a fleet term, makers swap tools for the current generation or extend those still
productive. Expired fleet tools may earn a credit voucher [S1], [S7]. Renewal guidance says to start 90–120 days
before the notice deadline [S10]. So 90 days before the end date may be too late where the notice period is long:
the window should be computed from the **notice date** when the contract has one (**unconfirmed** for tool-fleet
contracts).

**The flow links all three flows.** Like-life units come from the Returns queue (refurbish → place against the
refresh as a named order, which satisfies GR-02). Upgraded tools come back as returns. So Contract refresh is Returns'
largest source of named demand.

#### 1.10.2 Per-tool rule and the like-life match

```
for each tool t on the contract:
  if PLM end-of-parts date of t's model < next term end        → Upgrade
  elif RUL_tool(t) < 25%                                       → Like-life swap
  else                                                          → Keep
like-life target   = median RUL of the tools marked Keep (sample: about 60%)
match              = refurbished unit of the same class with |RUL − target| smallest, each unit reserved once
                     (sources: refurbished stock at the repair centre, then the Returns queue)
```

The swap threshold (25%) and the upgrade condition are business rules (01 §4.3). The prototype's "Test this
proposal" moves the threshold and the upgrade switch and shows which tools change action. The match is an assignment
problem: the repo's `engine/pool.py` (`solve_pool`, exact for small pools) and `tool_fleet._plan_queue` already
allocate each unit once. Neither knows "like-life".

#### 1.10.3 Journey

| # | Stage | Contract refresh step | Agent → person |
|---|---|---|---|
| 1 | Return / receive | Contract enters the window (90 days before the end, or before the notice date) | Intake (schedule trigger) |
| 2 | Match / verify | Contract lines, serials, swap rights, account in good standing | Intake |
| 3 | Condition | Hours, faults and repairs per tool, last 12 months; RUL per tool (TF-06); telematics freshness (GR-13) | Condition and life |
| 4 | Value each route | Like-life matches reserved; fee, saving vs new, likelihood to renew | Demand discovery, Valuation |
| 5 | Decide | One proposal: keep N, swap M, upgrade K | Disposition; sales if credits > $300 |
| 6 | Execute | Proposal emailed; contract lines drafted; refurbished units reserved | Follow-through (sending is held for a person) |
| 7 | Close and learn | Renewed or not; the actual fee; which swaps were accepted | Analytics |

#### 1.10.4 Guardrails, KPIs, data (needs Legal review for the proposal and contract lines)

| Id | Rule | Type | Owner | Repo status |
|---|---|---|---|---|
| GR-C1 | Credits above $300 → sales approval | Approval | Sales | missing |
| GR-C2 | A proposal goes to the customer only after a person approves (an agent never sends a commercial offer on its own) | Approval | Sales / fleet desk | partial: the forbidden list and hold-for-a-person exist (`services/agents/forbidden.py`); the email action does not |
| GR-C3 | A like-life unit is reserved once and is certified (grade and RUL, GR-08) | Compliance | Repair centre lead | partial (queue plan reserves once) |
| BR-C1 | Swap below 25% life; upgrade when parts end before the next term | Business rule | Fleet services lead | missing |
| GR-07, GR-12, GR-13 | Shared (§1.7) | | | see §1.7 |

**KPIs:**

- **Renewal rate with vs without a proposal.** The sample is 90% vs 81% (*sample, modelled*). It is an
  observational comparison, so see §3.4 on selection bias.
- **Proposal ready by day −90.**
- **Fleet life evenness after the proposal.** For example, the spread of RUL across the contract.
- **Refurbished units placed from returns.** This avoids new purchases.
- **Saving vs new.**
- **Credit cost per renewal.**

**Data:**

- contract lines with end and notice dates and the fee;
- the fleet rate card (sample "v4");
- per-tool usage for 12 months;
- PLM end-of-parts and successor model;
- refurbished stock with RUL;
- contract history for 2 years (renewed or not).

#### 1.10.5 Contract refresh user stories

| Id | P | Story | Given / When / Then | Actor | Today in repo |
|---|---|---|---|---|---|
| CR-01 | P0 | As fleet desk, I want one refresh case per contract entering the window | Given a contract whose end (or notice date) is 90 days away, When the daily schedule runs, Then one refresh case opens with its lines and serials; it opens once per contract and term | Agent (Intake) | **partial**: schedule triggers (`workflow/triggers.py`); the leasing mock serves end dates and renewals; no refresh case type or reason |
| CR-02 | P0 | As fleet services lead, I want each tool marked keep / like-life swap / upgrade by rule | Given RUL per tool and PLM end-of-parts dates, When evaluated, Then each tool shows its action and why (BR-C1) | Agent (Condition, Disposition) | **missing**: needs TF-06 and PLM end-of-parts; `repositories/plm.py` has no such field |
| CR-03 | P0 | As repair centre lead, I want like-life units matched and reserved once | Given refurbished stock and returns in the queue, When the proposal is built, Then each worn tool gets the unit closest to the fleet's median life; a unit is never promised twice, across contracts and the Returns queue | Agent (Demand discovery) | **partial**: `engine/pool.py` `solve_pool` and `_plan_queue` allocate each unit once; no like-life objective |
| CR-04 | P0 | As sales, I want the proposal priced: fee, saving vs new, likelihood to renew, credits | Given the rate card and contract history, When valued, Then the proposal shows current vs proposed fee, saving vs new, renewal likelihood and credits; credits above $300 wait for me (GR-C1) | Agent (Valuation); Person (sales) | **missing** |
| CR-05 | P0 | As sales, I want approval to send the proposal, draft the contract lines and reserve the units | Given an approved proposal, When I approve, Then the proposal is emailed, contract lines are drafted in the fleet contract system and the units are reserved; nothing goes out before approval (GR-C2) | Person approves; Agent (Follow-through) | **partial**: hold for a person, instructions; no proposal document or email action |
| CR-06 | P1 | As fleet services lead, I want to test the proposal rules | Given a proposal, When I move the swap threshold or switch upgrades, Then the tools that change action and the fee/renewal impact show; nothing is sent | Person | **partial**: `modeler/simulate.py` (rule sets only) |
| CR-07 | P1 | As analytics, I want renewal outcomes recorded and compared | Given contracts closed in the period, When reported, Then renewal rate with vs without a proposal shows, with the bias caveat | Agent | **missing** |
| CR-08 | P2 | As fleet desk, I want the window computed from the notice date | Given a contract with a notice period, When scheduling, Then the window opens 90 days before the notice date | Agent | **missing** |

---

## 2. Device recommerce template ("Recommerce · phones and devices", 01 §5)

### 2.1 How the programmes work

Two inflows share one back end [D9]:

- **Trade-in / upgrade** (the pack's primary inflow, 01 §5):
  1. The customer gets a quote from a self-declared condition.
  2. The device is received and **verified against the quote**: IMEI, model, capacity.
  3. It is graded.
  4. If the grade differs, the payout is adjusted: within 10% automatically, larger gaps go to customer care with the
     grading photos.
  5. The device is wiped with a certificate and sold through a channel.
- **Protection / insurance replacement** (kept as a **P1 channel**, DV-12):
  1. A claim triggers fraud checks.
  2. A replacement (often refurbished stock) ships.
  3. The damaged device must come back within a window, or a fee applies (**unconfirmed**).
  4. The returned device goes through the same wipe-grade-decide chain.

  The protection angle adds a channel, **reuse as replacement stock**, which avoids buying replacements. That is why
  it is kept.

Trade press lists insurance claims, upgrades, trade-ins, leases, warranty and remorse returns as the inflows. It lists
repair, resale, parts recovery, certified pre-owned placement or recycling as the outcomes [D9].

### 2.2 Grading scales

- CTIA published a voluntary wireless device grading standard in February 2019 [D1]. A 2024 revision aligned it with
  SERI's R2 categorisation. Version 5.1 (June 2026) maps wholesale grades into consumer terms and adds functional
  testing, battery-health requirements and a genuine-parts declaration [D2]. The 5.1 thresholds are
  **unconfirmed**: only the announcement was read.
- SERI says the CTIA scales apply only to processed devices. R2 facilities categorise on receipt and re-categorise
  through processing [D3].
- A B2B liquidation marketplace's buyer guide uses grades A (like-new) to E (salvage), plus N for ungraded. It notes
  that a phone in grade A condition but **locked** should be graded salvage. Lot listings state the model mix,
  capacity split and seller grade [D12]. These are platform-specific.
- The template keeps four separate facts, per 01 §5 stage 3:
  - **cosmetic grade** (A–D, CTIA-aligned, from photo grading);
  - **functional status** (pass / fail list from diagnostics);
  - **battery health %**;
  - **parts status**.

  The repo device valuer has only the grade.

### 2.3 Data erasure (needs Legal review)

- **NIST SP 800-88 Rev. 2**, final on 26 Sep 2025, supersedes Rev. 1. It guides a sanitisation *programme* and points
  to IEEE 2883 for media-specific techniques [D4].
- **IEEE 2883-2022** defines Clear, Purge and Destruct, with media-specific techniques and the correct use of
  cryptographic erase [D4], [D5].
- **R2v3 Appendix B** requires verification for logical sanitisation, and Appendix C requires validated sanitisation
  [D3].
- **Certificate content.** The template keeps one record per IMEI/serial with:
  - the method (Clear/Purge per IEEE 2883);
  - the tool version;
  - the verification result;
  - the operator.

  The rule is: **no listing, sale or re-issue without the certificate** (GR-D1, now a stated guardrail in 01 §5). The
  field list from a secondary source is **unconfirmed** against the NIST text.
- **Batch behaviour (01 §5):** missing certificates on a batch are held, and released automatically when they arrive.
- Per brief item 3, the erasure certificate is required for IT/compute assets, not for tools and motors.

### 2.4 Blacklist, lock and fraud checks (needs Legal review)

| Check | What it catches | Source / note | Stage |
|---|---|---|---|
| Device blacklist (IMEI) | Devices reported lost or stolen. Operators share IMEIs through the GSMA registry, and buyers query it before buying. In one case study, 2–3% of queries hit a stolen report. | [D6] | verify, again at diagnose |
| Finance / ownership status | A financing balance or ownership claim on the device | [D6] | verify |
| Activation lock / account lock | The device is still tied to the previous owner's account. Locked devices often go to recycling or salvage only. | [D8], [D12] (**unconfirmed** policy for trade-in) | diagnose |
| Quote mismatch | IMEI, model or capacity differs from the quote | 01 §5 stage 2 | verify |
| Genuine parts | Non-genuine or "used" parts flagged in the parts history on newer models | [D7] | grade |
| Repeat trade-ins or claims | The same IMEI or customer across many events | operator practice | intake |

In the pack, the **blacklist and lock check is a locked compliance guardrail**. The diversion "quote under $50: skip
the blacklist check" is **blocked** (01 §5). Fraud outcomes are holds for a person, never automatic declines by an
agent (golden rule 10). The template stores IMEIs and event ids only; no customer names, addresses or account numbers
flow into the platform or the back-test files.

### 2.5 Price prediction and the hand-off to a person

**Inputs:**

- SKU: model, storage, colour, carrier lock;
- the four condition facts;
- age since launch;
- region, channel and lot size;
- a **market price feed** (prices by SKU and grade per week) and launch-event dates.

Studies of used-phone prices find brand, model, usage period and refurbished condition drive price, and that
gradient-boosted trees perform well [D10]. Those are academic studies on small data, so accuracy at production scale
is **unconfirmed**. The prototype's model catalogue also uses gradient boosting for the resale price (01 §3).

**Output per device or lot, per channel:**

- expected net cash = price x (1 − fee) − fixed − logistics − expected buyer returns − holding x days;
- days to sell;
- an interval (P10–P90).

Use quantile regression or split conformal prediction. Conformal intervals adapt when the error varies and support a
reject option [D11].

**Hand to a person** (the Compose confidence threshold, default 75%, 01 §2) when any of these hold:

- the interval width / point estimate is above a set share;
- the SKU is unseen, or has fewer than N sales in the window;
- the price is below the **floor** (§2.7);
- the value is above the approver's threshold;
- the price feed is stale, or a drift alarm fires (01 §5 alert: "marketplace price drop after a launch").

**Example evidence line (01 §5):** "a battery swap lifts the price by $28 but costs $24 and adds 5 days". It shows
that repair-then-sell must be valued with time held, not price alone.

### 2.6 Channels

| Channel | Fit | Pack (01 §5) | Repo `valuers/device.py` |
|---|---|---|---|
| Buy Now | Single units or small lots, grades A/B | yes | `buynow` |
| Offers | Mixed; slower | yes | `offers` |
| Auction | Speed; any grade | yes | `auction` |
| **Wholesale lot** (approved buyers bid; sold to the best net bid) | Grade C/D, older models, volume | yes | **missing** (the repo prices given lots; no bid intake) |
| Marketplace | Consumer marketplace | not in the pack | `market` (demo pack only, for parity; GR-D3 and GR-D5 reference it) |
| Reuse as replacement stock (protection) | Good grade, current models | **P1** (kept from the previous revision) | missing |
| Repair then sell | Repair cost below the price uplift, net of days | evidence line only | missing |
| Parts harvest / certified recycling (R2) | Locked, blacklisted (as law allows), beyond repair | implied by the guardrails | missing |

### 2.7 The price floor: one guardrail type, a per-customer value

| | Repo demo pack (GR-D2) | Recover device pack (01 §5) |
|---|---|---|
| Text | "Recovery floor: below 55% of reference value goes to human review" (`fixtures/golden/po/templates.json`) | "never below 60% of the forecast price" (stated by the pack author) |
| Base | reference value of the lot (`ref` in `device.py`) | the model's forecast price for the item |
| Value | 55% | 60% |
| Effect | to human review | blocks the sale; in Compose, a guardrail hit goes to a person |
| Code | `DG["floor"] = 0.55` in `valuers/device.py`; defined but **never read** by `score` or `decide` | n/a |

**Reading.** Both are a **Threshold** guardrail with three parameters: *base* (reference value or forecast),
*percentage* and *action* (hold for a person). The percentage is a **customer parameter**, set by the pack author.
Under 01 §2 the customer layer can tighten it, and a pack may lock a minimum. The two numbers are not comparable:
60% of a forecast and 55% of a reference value test different things. The first asks "are we selling far below what
we expect?"; the second asks "are we recovering too little of what the device was worth?".

**Parity:** the demo pack keeps 55% of reference value. The Recover device pack defaults to 60% of forecast. Both run
on the same guardrail type once it is implemented, which is also when the unused `DG["floor"]` gets wired. Whether a
customer may *loosen* the floor below the pack default is a governance question (**open**).

### 2.8 Customer rules and ageing rules (01 §5)

- **Payout adjustment.** Grade below the quote within 10% → the payout is adjusted automatically. A larger gap goes
  to customer care with the grading photos. (Consumer-facing payout changes: **needs Legal review** per market.)
- **Wholesale lots.**
  - Lots are built by model and grade.
  - Bids come from **approved** buyers only.
  - The lot sells to the best **net** bid (after fees and logistics).
  - A lot over $25,000 → commercial manager (GR-D10).
- **Ageing suggestion rules** (shown on the Decide overview; a person turns a suggestion into a rule):
  - Offers → Auction after 14 days with no offer (choices 7, 10, 14 or 21 days);
  - Buy Now → Offers after 21 days unsold.

  Marketplace practice confirms that time-based moves are platform-set, not standard. One marketplace requires 14
  days without a price change before a listing enters a sale event. Reserve-price auctions do not have to sell below
  the reserve [D13]. So the ageing defaults are the customer's policy, not an industry rule.
- **Diversions:**
  - a device from a named retail partner → a second grading check;
  - grade C and the model older than 3 years → straight to a wholesale lot;
  - "quote under $50: skip the blacklist check" → **blocked**.

### 2.9 The agents on device recommerce

| Agent | Device step | Code today |
|---|---|---|
| Intake | Trade-in received; one case per device (or lot) | `intake.open_case` + `device_lot` (lot-level only) |
| Condition | Verify against the quote; diagnostics, battery, photo grade; wipe certificate; blacklist and lock | none for device; erasure gate for class `it` in `engine/gates.py` (industrial only) |
| Demand discovery | Channel prices, open buyer bids, replacement-stock demand | fixed table `DST` in `device.py` |
| Valuation | Price per channel, net, days, interval | `device.score` (fees, logistics, return rate, erosion, SLA penalty) |
| Disposition / Routing | Best channel; lot building; ageing moves | `device.decide`, `DR-01` (exclude Buy Now at ≥ 45 days on hand) |
| Follow-through | List and ship; settle | generic instructions |
| Analytics | Price realised vs forecast; grading disputes by partner | generic analytics; no device calibration |

### 2.10 Personas

| Persona | Goal | Repo role |
|---|---|---|
| Recommerce operations lead (pack author) | Writes the description in Compose | Admin / Developer |
| Trade-in operations / customer care | Quote mismatches, payout gaps above 10%, photos | Planner |
| Fraud / compliance | Blacklist, lock, wipe certificates | Approver (new queue) |
| Receiving and grading lead | Wipe, test, grade | Warehouse manager / Engineer |
| Pricing analyst | Price model, floors, feeds | Approver (models) |
| Channel ops | Channel mix, ageing rules, lots | Planner |
| Commercial manager | Lots over $25,000; approved buyers | Approver (new limit) |
| Recommerce finance | Payouts, settlement, realised value | Finance |

### 2.11 Journey (7 stages, 01 §5)

| # | Stage | Decision points | Agent → person |
|---|---|---|---|
| 1 | Trade-in received | Duplicate? Repeat customer? | Intake |
| 2 | Verify against the quote (IMEI, model, capacity) | Match? Blacklisted? Financed? | Agent; fraud/compliance on a hit |
| 3 | Diagnose and grade (functional tests, battery health, photo grading); wipe | Locked? Grade vs quote within 10%? Certificate? | Agent adjusts payout within 10%; customer care beyond |
| 4 | Price by channel (market prices and channel fees) | Confidence above threshold? Floor? | Agent; pricing analyst below threshold |
| 5 | Decide the channel | Channel; lot membership | Agent; commercial manager if lot > $25,000 |
| 6 | List and ship | Ageing moves (overview suggestions) | Agent proposes; channel ops accepts rules |
| 7 | Settle and learn | Price realised vs forecast; disputes | Agent; finance |

### 2.12 Guardrails (needs Legal review)

| Id | Rule | Type | Origin | Owner | Repo status |
|---|---|---|---|---|---|
| GR-D1 | Data-wipe certificate before any listing; batches held until the certificates arrive | Compliance (stated) | demo + 01 §5 | Compliance | text guard (`DEVICE_GUARDS`); the valuer does not check |
| GR-D2 | Price floor: *base* x *percentage* → a person (demo 55% of reference; Recover 60% of forecast) | Threshold (customer value) | demo + 01 §5 | Recommerce finance | text guard; `DG["floor"]` unused |
| GR-D3 | Grade D never on Buy Now or Marketplace | Compliance | demo | Channel ops | enforced in `device.score` |
| GR-D4 | Maximum lot size per channel | Threshold | demo | Channel ops | enforced in `device.score` |
| GR-D5 | Marketplace never undercuts the live Buy Now price | Threshold | demo (demo pack only) | Pricing | text guard |
| GR-D6 | Every routing approved by a named owner | Approval | demo | Governance | exists; by threshold in Recover (see the note under §1.7) |
| GR-D7 | **Blacklist and lock check** clear before any sale; locked → parts or recycle only, as law allows | Compliance (**pack, locked**) | 01 §5 | Fraud / compliance | missing |
| GR-D8 | Low price confidence or unseen SKU → a person | Data quality | this report | Pricing | missing |
| GR-D10 | **Lot over $25,000 → commercial manager** | Approval (added) | 01 §5 | Commercial manager | partial: per-role approval limits, not per lot value |
| GR-D11 | Payout change within 10% automatic; above → customer care with photos | Threshold | 01 §5 (customer rule) | Customer care | missing |
| GR-D12 | Wholesale bids only from approved buyers | Compliance | 01 §5 (customer rule) | Commercial manager | missing |

GR-D9 (genuine-parts declaration on every listing) moves to P2.

**Exceptions and alerts** (01 §5):

- grade well below the quote;
- missing wipe certificates on a batch;
- a marketplace price drop after a launch;
- an auction reserve not met, showing the cost of holding;
- a wholesale lot over the limit.

**KPIs.** The *sample, modelled* values are from the prototype script, line 1943.

| KPI | Sample value (*modelled*) |
|---|---|
| Recovery rate of original value | 63% |
| Days to sale | 9.1 |
| Price realised against forecast | 98.6% |
| Straight-through % | 88% |
| Data-wipe compliance | 100% |
| Grading disputes | 1.9% |

Kept from the previous revision:

- interval coverage (target near 80% for P10–P90);
- fraud false-hold rate;
- replacement stock sourced from returns (P1);
- CO2e per route.

### 2.13 Device user stories

| Id | P | Story | Given / When / Then | Actor | Today in repo |
|---|---|---|---|---|---|
| DV-01 | P0 | As trade-in ops, I want one case per received device | Given a trade-in with IMEI and quote, When received, Then one case opens per IMEI (bulk: per lot with device lines), duplicates refused | Agent (Intake) | **partial**: `intake.device_lot` opens lot-level cases; no IMEI-level case |
| DV-02 | P0 | As trade-in ops, I want the device verified against the quote | Given the quote's IMEI, model and capacity, When diagnostics report, Then a mismatch opens an exception with both values | Agent; Person on mismatch | **missing** |
| DV-03 | P0 | As compliance, I want the blacklist and lock check (GR-D7) | Given a case, When the blacklist, finance or lock check hits, Then sale channels are blocked, the case waits for compliance with the evidence, and a customer diversion that skips the check is refused | Agent checks; Person decides | **missing** |
| DV-04 | P0 | As compliance, I want no listing without a wipe certificate (GR-D1) | Given a device or a batch, When a sale channel is proposed without a certificate (method, tool version, verification, operator), Then it is blocked; a batch is held and released automatically when the certificates arrive | Agent | **partial**: GR-D1 text guard; `engine/gates.py` erasure gate only for industrial class `it` |
| DV-05 | P0 | As customer care, I want payout adjusted inside 10% and larger gaps sent to me with photos (GR-D11) | Given the grade, battery, functional and photo results, When graded below the quote, Then within 10% the payout is adjusted and recorded; above, the case waits for customer care with the photos | Agent; Person above 10% | **partial**: grade fact only; no quote, no payout |
| DV-06 | P0 | As pricing analyst, I want price per channel with an interval, the floor applied and low confidence handed to me | Given SKU, condition facts, age and the latest feed, When evaluated, Then Buy Now, Offers, Auction and wholesale lot show expected net, days and P10–P90 with the feed date; below the floor (GR-D2) or below the confidence threshold (GR-D8), it waits for me | Agent (Valuation); Person below threshold | **partial**: `device.score` from the fixed table `DST`; no feed, no interval; floor unused |
| DV-07 | P0 | As commercial manager, I want wholesale lots built by model and grade and sold to the best approved bid | Given devices routed to wholesale, When lots are built, Then lots group by model and grade within the caps (GR-D4), bids come only from approved buyers (GR-D12), the best net bid is proposed, and a lot over $25,000 waits for me (GR-D10) | Agent builds; Person approves big lots | **missing**: lots are given (`sample_lots`), not built; no bids |
| DV-08 | P0 | As channel ops, I want ageing suggestions on the overview | Given listings, When an Offers listing has had no offer for 14 days (setting 7/10/14/21) or a Buy Now listing is unsold after 21 days, Then the overview suggests the move, oldest value bands first; accepting turns it into a rule through maker-checker | Agent suggests; Person accepts | **partial**: `DR-01` excludes Buy Now at ≥ 45 days on hand (`device.py`); `modeler/suggest.py` suggests rules from overrides; no listing age, no suggestion on the overview |
| DV-09 | P0 | As finance, I want settlement and learning | Given a sale settles, When confirmed, Then price realised vs forecast, fees and buyer returns post, and the error feeds calibration | Agent (Follow-through); Person confirms | **partial**: generic outcome confirmation; no device calibration |
| DV-10 | P1 | As channel ops, I want the customer diversions | Given a device from a named retail partner, Then a second grading check is added; Given grade C and a model older than 3 years, Then it goes straight to a wholesale lot | Agent | **partial**: business rules scope by grade/owner (`modeler/apply.py`); no "add a step" |
| DV-11 | P1 | As channel ops, I want repair-then-sell, parts and recycle as routes | Given a repair cost and its price uplift and days, When valued, Then repair-then-sell shows net of days (e.g. battery swap +$28 price, −$24 cost, +5 days) | Agent | **missing** |
| DV-12 | P1 | As claims ops, I want reuse as replacement stock valued as a channel (protection angle) | Given open replacement demand for that SKU, When valued, Then the avoided purchase cost shows as a channel | Agent | **missing** |
| DV-13 | P1 | As analytics, I want the two worked questions | Given settled sales, When asked, Then "price realised dropped after a launch" and "grading disputes by retail partner" are answered as a chart with example records | Agent (Analytics) | **partial**: Ask and analytics queries exist; no device data |
| DV-14 | P2 | As pricing analyst, I want to propose a retrained price model and have another person promote it | Given new outcomes, When fitted, Then a candidate with MAE and interval coverage is proposed; shadow before promotion | Agent; Person | **partial**: model lifecycle for industrial only |
| DV-15 | P2 | As compliance, I want the demo-pack checks GR-D5 and GR-D9 | Given a marketplace price below live Buy Now, or a listing without a parts declaration, Then it is blocked | Agent | **missing** (text guards only) |

---

## 3. Back-testing and replay (both templates)

### 3.1 What historical data to request (one month or one quarter)

| Data | Tool fleet: Returns | Tool fleet: Service desk | Tool fleet: Refresh | Device |
|---|---|---|---|---|
| Items | serial, class, return date, reason, contract id, site | tickets: serial, fault, market, date, batch id | contracts ending in the period: lines, serials, end/notice dates, fee | IMEI (salted hash), SKU, trade-in id, date |
| Condition at the time | grade and tests with dates; run hours and events; repair history | age, past repairs, fault posted by the technician | per-tool usage, faults, RUL inputs | diagnostics, battery, photos, lock/blacklist with dates |
| Actual decision | route, date, who | option quoted and chosen; quote time | renewed or not; what was swapped | channel, lot, list date, moves |
| Actual outcome | realised value or avoided cost; all costs | actual repair cost; margin; credit given | new fee; tools swapped or upgraded | sale price, fees, logistics, buyer returns, days to sell |
| Demand at the time | open renewals, pool requisitions, bids, repair orders, with dates | refurbished stock; current models | refurbished stock and returns | price feed history by SKU and grade; bids; caps |
| Reference tables | new prices, rated lives, cost rates (dated) | **≥ 3 years of closed repairs**; price lists, labour rates, credit rules, cover terms (dated) | rate card, end-of-parts dates (dated) | reference values, fees (dated) |

Ask for de-identified extracts: no customer names, addresses, account or card numbers (organisation policy).

### 3.2 What the replay reports (aligned with Compose step 5)

The prototype's replay runs past items through the draft flow and reports four things (01 §2). This report adds a
definition to each, so the numbers can be computed the same way in the product and in a sales back-test.

| Output | Definition |
|---|---|
| **Route mix, actual vs flow** | For each route or channel: % of items the customer actually sent there vs % the flow would send |
| **Straight-through %** | Items the flow would decide with no person touching data or the route: no guardrail hit, no exception, confidence ≥ threshold, under every approval threshold |
| **Approvals per day, exceptions per day** | Items that would wait for an approver or an exception owner, divided by business days in the period; split by guardrail and owner |
| **Value uplift** | (flow net − actual net) / actual net, both priced by the same valuer as of the decision date (§3.3), with a band |

Prototype sample replays (*sample, modelled*; prototype script lines 1899, 1930):

| Tool fleet, 3,420 tools: route | Actual % | Flow % |
|---|---|---|
| Redeploy to pool | 38 | 46 |
| Refurbish and re-rent | 22 | 21 |
| Fix and return | 16 | 14 |
| Harvest parts | 8 | 11 |
| Upgrade offer | 0 | 3 |
| Recycle | 16 | 5 |
| **Straight-through** | | **81%** |
| **Approvals / exceptions per day** | | **11 / 6** |
| **Value recovered vs actual** | | **+9%** |

| Device, 18,600 devices: channel | Actual % | Flow % |
|---|---|---|
| Buy Now | 38 | 41 |
| Offers | 27 | 22 |
| Auction | 14 | 21 |
| Wholesale lot | 21 | 16 |
| **Straight-through** | | **88%** |
| **Approvals / exceptions per day** | | **14 / 22** |
| **Net recovery vs actual** | | **+6%** |

The device sample has more exceptions than approvals per day (22 vs 14). That is plausible: missing wipe
certificates and grade gaps are frequent but cheap to clear. The pitch should expect the question.

**Repo today.**

- `modeler/simulate.py` compares a candidate rule set with the published one over a queue: cases that flip and the
  value difference.
- Shadow mode records both decisions live (`actions/decisions.py`, `shadow_decision`).
- The pilot report counts cases, approvals, net and `by_route` per org unit (`actions/org_pilot.py`).
- **Missing:**
  - an import of historical outcomes;
  - "actual" as a side of the comparison;
  - as-of inputs;
  - straight-through % and approvals or exceptions per day;
  - a band;
  - publish "to one region at 20% of volume" (pilot mode is all-or-nothing per unit).

### 3.3 Computing uplift fairly (kept from the previous revision)

1. **As-of replay.** Freeze each item at its actual decision date `t0`. Use only facts timestamped before `t0`: that
   week's price index, bids live at `t0`, demand open at `t0`, the grade known at `t0`. Reject any input dated after
   `t0`. This is the leakage test: automated and reported.
2. **Same yardstick for both sides.**
   - Primary measure: value the actual route and the flow's route with the **same** valuer and the **same** as-of
     inputs ("estimated vs estimated").
   - Secondary measure: realised value of the actual route vs the flow's estimate, corrected by the valuer's bias.
     Measure that bias on the agreement set, where the flow equals the actual route.
   - Show both; lead with the conservative one.
3. **Constraints honoured.** One renewal, requisition, bid or like-life unit serves one item. Repair slots and channel
   caps are finite. Replay the queue in date order with the queue plan (`tool_fleet._plan_queue`), not case by case.
4. **All costs in.** Freight, refurbishment labour, test, channel fees, buyer returns, holding cost per day, and price
   erosion over days to sell.
5. **Bands, not a single number.** Bootstrap over items (1,000 resamples) for an 80% and 95% interval on total
   uplift. Run sensitivity at ±10% market index and ±20% labour.
6. **Counterfactuals are estimates.** Logged data shows only the action taken (selection bias). A shadow or small
   live split is the clean reference [B1]. So: back-test to sell, then **publish to one region at 20%** (01 §2) and
   shadow to prove.
7. **No tuning on the test set.** Rules and tables are frozen before the replay; a change is a new, dated run.

### 3.4 Specific to Service desk and Contract refresh

- **Service desk.** There are two separate replays:
  - **Estimate accuracy.** For each closed repair in the period, estimate from repairs closed before it. Report MAE,
    range coverage and the share that would have been auto-priced (≥ 50 matches).
  - **Option choice.** Upgrade take-up under a flow offer is a counterfactual: the customer was never offered it. Use
    take-up from the customer's past offers (24 months, 01 §4.2) as the model. Report the uplift as *modelled*, with
    the take-up band, never as measured.
- **Contract refresh.** "90% renewed with a proposal vs 81% without" (*sample*) is observational. Contracts that got
  a proposal may differ, for example as larger or better accounts. Report it with that caveat, compare like-for-like
  segments (size, age, market), and prove it with a 20% region publish.

### 3.5 Presenting it

- The replay screen's four numbers first: route mix, straight-through, approvals/exceptions per day, uplift with its
  band.
- One waterfall:
  1. actual net;
  2. same-route repricing (bias);
  3. route changes by type;
  4. constraint losses;
  5. **net uplift with its band**.
- A flip table (from → to, value delta, top reason), with the 10 largest flips explained in full.
- Agreement rate, and the items **held for a person**. That is a feature: it shows the control.
- Data-quality findings as a separate list: untagged tools, stale telematics, missing grades, missing wipe
  certificates, stale feeds. It sells the fabric.
- A one-page method note: the as-of rule, the yardstick, the leakage test, and the bias caveats of §3.4.

---

## 4. Demo scripts (Compose first)

Marked **[exists]**, **[partial]** or **[build]** against the repo today. Each beat follows the prototype's sales
story: describe → adapter mapping → agent mapping → approve → publish to one region at 20% → Decide → Understand.
Every number in the scripts is *sample, modelled* (from the prototype) or illustrative (e.g. the $31,000 lot, the −6%
payout adjustment, battery 84%).

### 4.1 Tool-fleet AMS (about 12 minutes)

| Min | Surface | Say and do |
|---|---|---|
| 0:00 | Compose 1: Business flow | The fleet services lead types: "Tools come back at contract end or for repair; tickets come from the service desk; contracts are refreshed 90 days ahead; repairs over $600 need the fleet manager." The configuration agent shows its reading log and matches the tool-fleet pack v3.2. It lists fields, the 7 stages, the three flows, guardrails (recall, telematics < 7 days from the pack; $600 as stated) and the 7 systems (one needs a connector). It asks **one** question, e.g. "Who approves write-offs of young tools?" Answer: "service operations, under 24 months". **[build]** (Build with AI drafts workflows only; `modeler/propose.py` drafts single rules) |
| 2:00 | Compose 2: Adapter mapping | Fields proposed with confidence; one low-confidence field with its reason (e.g. a 0/1 cover flag "meaning taken from the registry documentation"); accept, convert, ask the owner. Test run of past tools shows where cases stopped. **[partial]** (`mapping.suggest`, `integrator` agent; no confidence-with-reason, no test run through a decision flow) |
| 3:30 | Compose 3: Agent mapping | The seven agents on the stages; autonomy per agent; confidence threshold 75%. **[partial]** (registry and autonomy exist; no "act within limits" by value, no threshold) |
| 4:15 | Compose 4: Approve | A second person approves; the maker cannot (maker-checker). Show a change sent back pinned to step 1. **[partial]** (the flow lifecycle has maker-checker; no pinning to a step) |
| 5:00 | Compose 5: Publish | v1.0 to **one region at 20%**. Replay: 3,420 tools, route mix, 81% straight-through, 11 approvals / 6 exceptions a day, +9% (*sample, modelled*). **[build]** (shadow and pilot mode exist; no % split, no replay of actuals) |
| 6:30 | Decide · overview | Rates, leaks ("pool short while grade A sells"), new items. **[partial]** (Home / My work) |
| 7:00 | Decide · Cases (Returns) | A return: grade read from the workbench with its age; telematics 3 days old; WTI 65, RUL 21% motor; six paths with value lines; re-issue blocked; harvest + recycle chosen; queue plan keeps one renewal for the better return. **[exists]** valuation and queue plan; **[build]** WTI/RUL, recall, freshness |
| 8:30 | Decide · Service desk | A ticket: estimate $430 from 186 similar repairs, range shown, priced in seconds; upgrade with credit beats fix; a batch of 22 split 9/11/2; a credit above $300 waits for sales (*sample*). **[build]** |
| 9:45 | Decide · Contract refresh | A contract 90 days out: keep / like-life swap / upgrade per tool, units reserved from returns; "Test this proposal" moves the 25% threshold. **[build]** |
| 10:45 | Decide · Exceptions | Recall quarantine; telematics vs inspection; repair over $600 to the fleet manager. **[partial]** (approvals; no typed exceptions) |
| 11:15 | Understand | Analytics drill-down; Agents with their limits; Models with quality and drift (estimate accuracy on held-out repairs). **[partial]** (Analytics, Agents, Models panel for industrial) |

### 4.2 Device recommerce (about 10 minutes)

| Min | Surface | Say and do |
|---|---|---|
| 0:00 | Compose 1 | The recommerce operations lead types a description; the pack v2.7 matches. Guardrails: blacklist and lock (pack), wipe certificate and floor 60% of forecast (stated). One question, e.g. "Who approves large wholesale lots?" Answer: "commercial manager over $25,000". **[build]** |
| 1:45 | Compose 2 | 8 systems; mappings with confidence; test run. **[partial]** |
| 3:00 | Compose 3–4 | Agents and autonomy; maker-checker approval. **[partial]** |
| 3:45 | Compose: customer layer | Add "retail partner → second grading". Try "quote under $50: skip the blacklist check": **blocked**. **[partial]** (guard patterns block weakening text; no typed diversion) |
| 4:30 | Compose 5 | Publish to one region at 20%; replay 18,600 devices, 88% straight-through, 14 approvals / 22 exceptions a day, +6% (*sample, modelled*). **[build]** |
| 5:30 | Decide · Cases | Device verified against the quote; wipe certificate; grade B, battery 84%; payout adjusted −6% automatically; price per channel with P10–P90; evidence line "battery swap +$28, costs $24, +5 days". **[build]** (channel scoring from the fixed table **[exists]**) |
| 7:00 | Decide · lots | Wholesale lot by model and grade; approved-buyer bids; $31,000 lot waits for the commercial manager. **[build]** |
| 8:00 | Decide · overview | "Move 12 Offers listings to Auction: 14 days, no offer." Accept → becomes a rule. **[build]** |
| 8:45 | Decide · Exceptions | Batch held for missing wipe certificates, released when they arrive; a blacklist hit. **[build]** |
| 9:15 | Understand | "Why did price realised drop?" → after a launch; "Who causes grading disputes?" → two partners (screens graded before power-on). **[partial]** |

---

## 5. Grounding in the repo (read 24 Nov 2026, commit `5b1fcfd`)

- **Packs** (`backend/di/services/modeler/templates.py`).
  - `industrial` comes from `packs/industrial.json`.
  - `tool_fleet` and `device` are built in code from `fixtures/golden/po/templates.json`, with guardrail checks as
    data (`TOOL_FLEET_GUARDS`, `DEVICE_GUARDS`).
  - Guardrails have no *type* and no *stage*.
  - There is no pack file format for Compose to write into.
- **Tool-fleet valuer** (`valuers/tool_fleet.py`, 1,116 lines). It is a port of an earlier prototype.
  - Six paths, value lines, demand matching.
  - Queue plan `_plan_queue` over open returns and repair slots (`slots` 8).
  - Rules (`BR-01`, `BR-02`), simulation.
  - `rul` and `partRul` are inputs; grade is `grade`, else `estGrade`.
  - No contract, telematics, PLM, recall, carbon, service-desk or refresh logic.
- **Device valuer** (`valuers/device.py`, 286 lines).
  - Channels `buynow`, `offers`, `auction`, `market`; a fixed table by grade x age band; lot caps; grade-D exclusion;
    SLA penalty; rule `DR-01`.
  - No wholesale lot with bids, no ML, no interval, no wipe or blacklist check.
  - `DG["floor"] = 0.55` is never read.
- **Intake** (`services/cases/intake.py`): tool-fleet and device cases from data. Reasons: `rma`, `lease_end`,
  `trade_in`, `contract_end`, `iot_alarm`, `manual`. Dedupe on asset + reason. There is no `service_ticket` or
  `contract_refresh` reason.
- **Engine** (`services/engine/`): `pool.py` (`solve_pool`, exact allocation, each unit once), `predictor.py`,
  `calibration.py`, `gates.py` (erasure gate for class `it`). Note: `plan_queue` lives in `valuers/tool_fleet.py`,
  not in `engine/`.
- **Agents.**
  - Ten seeded agents (`migrations/versions/0023_agent_identity.py`): evidence assembler, opportunity finder, gap
    requester, handoff coordinator, reconciler, briefing, analytics explainer, integration assistant, audit assistant,
    Ask.
  - The case autopilot playbook. Autonomy `read`/`propose`/`act`.
  - Access autonomy per role and action type, and run limits (`services/agents/limits.py`).
  - The forbidden list.
  - None of the seeded agents is named for the prototype's seven; their tools would serve Intake, Demand discovery,
    Follow-through and Analytics.
- **Approvals.** Per-role approval limits (`core/policy.py` `STARTING_LIMITS`, `actions/decisions.py`); no
  self-approval.
- **Lifecycle and learning.**
  - Flow maker-checker, shadow, rollback.
  - `modeler/simulate.py`.
  - Rule suggestions from overrides (`modeler/suggest.py`), which matches "an override needs a reason, used to tune
    the rules" (01 §2).
  - `model.fit` for the industrial template.
- **Pilot:** pilot mode per org unit and the pilot report (`actions/org_pilot.py`); no % of volume.
- **Triggers:** schedule, event, approval, file and case triggers (`workflow/triggers.py`); a daily refresh-window
  scan can be a schedule workflow.
- **Mocks (synthetic) that serve the new flows:**
  - depot repair (grade, repair orders, parts cost, labour rate, teardown findings);
  - leasing (contract end dates, renewals, asset returns);
  - IoT (run hours);
  - field service / ITSM (work orders with a labour rate);
  - QMS certificates incl. `DATA_ERASURE`;
  - three PLM systems;
  - remarketing, carbon, WMS, ERP.

  There are **no** mocks for a recall register, a device blacklist, diagnostics/photo grading or a price feed.

---

## 6. Open questions for the domain experts

Tool fleet:

1. Which contract terms decide disposition (ownership, theft-recovered, damage, regional resale limits)? Is there a
   machine-readable field for each? Is there a notice date separate from the end date (for the refresh window)?
2. Does the repair workbench report component findings and run hours at repair? How far back does repair history go
   per market, and are fault codes consistent across markets (needed for "≥ 50 similar repairs")?
3. Are rated lives per wear component and **end-of-parts dates** available from PLM?
4. What share of the fleet is connected, and does the tag report run time, load or only location? How often does it
   report (for the 7-day freshness rule)?
5. Which recall source is authoritative (the maker's own register, a regulator, both)? Does it give serial ranges?
6. Is pre-owned sale in scope for the pilot? The Compose route list omits it (§1.8.1). Is donation a route?
7. Who approves credits: is "sales" one role, or one per market? Is $300 per tool or per proposal?
8. Is an electrical safety test required before re-issue or resale in the pilot markets (the former GR-10)?
9. Batteries: the same case as the tool, or their own flow?
10. Who signs the policy that lets low-value, high-confidence decisions go straight through (GR-05 by threshold)?

Device:

11. Which inflows are in the pilot: trade-in only, or protection replacement too (DV-12)?
12. Which diagnostics, photo-grading and wipe tools? Is the certificate per IMEI and machine-readable?
13. Which blacklist and finance checks are licensed? What is the policy for locked or blacklisted devices?
14. Is a weekly price feed available per SKU and grade, and how far back?
15. The floor: what base and percentage does the customer want (forecast or reference value)? May a customer set it
    below the pack default?
16. Who are the approved wholesale buyers, and how are bids received (platform or email)?

Both:

17. Can historical extracts be de-identified at source?
18. Which value counts as "actual": invoiced price, settled cash, or booked recovery?

**Unconfirmed in this report:**

- CTIA 5.1 thresholds;
- the NIST Rev. 2 certificate field list;
- return windows and fees in protection programmes;
- regional resale limits and safety-test rules for reconditioned tools;
- battery-regulation applicability;
- repair-estimate accuracy at production scale for tools;
- price-model accuracy at production scale;
- whether 90 days before the end date is the right refresh trigger for tool-fleet contracts;
- weekly price erosion (the repo's 1.3% a week is a prototype value);
- every *sample, modelled* figure from the prototype.

---

## Sources

All read or searched on 24 Nov 2026 unless stated otherwise. "Withheld" means the URL names a company that may be a
customer, prospect or channel partner, per the brief.

- [P] Recover prototype "5 Industry Segments", pre-final, received 24 Nov 2026, restated in
  [01-recover-segments.md](01-recover-segments.md). Figures not in 01 are cited from the extracted prototype script
  (team-internal; lines 13–30 paths, 409–468 service desk sample tickets, 560–575 service desk agent steps and KPIs,
  654–721 contract refresh, 1890 credit approval, 1884–1946 pack replays and KPIs). All its numbers are *sample, modelled*. Sample company
  and person names in it are not reproduced.
- [S1] A tool manufacturer's public fleet-management pages and help centre (US, UK, Canada, Finland, South Africa
  editions; terms flyer for fleet exchange). Withheld. Undated web pages.
- [S2] The same manufacturer's 2021 company report, chapter on tool fleet management. Withheld.
- [S3] SMACNA news, "Cost Predictability + Enhanced Productivity with Fleet Management", 14 Nov 2025:
  https://www.smacna.org/news/products-and-services-updates/article/2025/11/14/cost-predictability---enhanced-productivity-with-fleet-management
- [S4] Silicon Labs, "The benefits of Bluetooth LE connectivity in power tools" (white paper, undated):
  https://silabs.com/whitepapers/the-benefits-of-bluetooth-le-connectivity-in-power-tools
- [S5] Construction trade press on Bluetooth tool tracking and accelerometer run time (undated). Withheld (names the
  tool manufacturer).
- [S6] Several tool makers' and authorised outlets' reconditioned-tool pages. Withheld.
- [S7] The same manufacturer as [S1]: fleet-exchange flyer (Canada), trade-in voucher flyer (Oct 2023), fleet terms
  and conditions (New Zealand), fleet brochure (Australia, 2021), trade-in programme page (US), UK fleet FAQ.
  Withheld. Search results and snippets, 24 Nov 2026. Terms differ by country.
- [S8] Repair-programme pages of several tool makers (flat-rate repair, capped "not to exceed" or guaranteed repair
  cost, exchange within 1–2 working days, repair-or-replace with a 1-year warranty), and a trade-magazine comparison
  of tool warranties and repair caps. Withheld. Search results, 24 Nov 2026; terms not read in full.
- [S9] US Consumer Product Safety Commission, recalls: https://www.cpsc.gov/Recalls. 2025 recall notices for cordless
  and battery power tools, with remedies of repair, replacement or pro-rated refund (search results, 24 Nov 2026;
  individual notices name manufacturers and are not linked).
- [S10] Ironclad Journal, "Contract renewal strategy", 11 May 2026 (vendor guidance):
  https://ironcladapp.com/journal/contract-management/contract-renewal-strategy
- [S11] Case-based estimation literature, listings only (full texts not read):
  - IEEE Access, Jan 2021, cluster-based case adaptation with multi-output support vector regression for maintenance
    cost estimation: https://doaj.org/article/c8fa8558a1e64cbcab581ec844d80136 (the page refused automated access;
    title **unconfirmed**).
  - Buildings 13(3):651, 2023, bootstrap-aggregated CBR for conceptual cost estimation:
    https://open.metu.edu.tr/bitstream/handle/11511/102686/buildings-13-00651-v3.pdf
  - A PolyU thesis on GA-tuned CBR (more accurate with small case bases):
    https://theses.lib.polyu.edu.hk/bitstream/200/11018/3/5483.pdf
- [R1] ISO 13381-1:2025, Condition monitoring and diagnostics of machine systems — Prognostics — Part 1, Sep 2025:
  https://www.iso.org/standard/88029.html (abstract and contents only).
- [D1] TelecomTV, "CTIA establishes industry standard for grading pre-owned wireless devices", 12 Feb 2019:
  https://www.telecomtv.com/content/devices/ctia-establishes-industry-standard-for-grading-pre-owned-wireless-devices-34026/
- [D2] PR Newswire, CTIA wireless device grading standard (version 5.1), 10 Jun 2026 (search snippet only):
  https://www.prnewswire.com/news-releases/ctia-publishes-wireless-device-grading-standard-in-support-of-greater-transparency-for-pre-owned-devices-302796919.html
- [D3] SERI R2 knowledge base, CTIA grading Q&A: https://sustainableelectronics.org/knowledge-base/ctia-grading-qa/ ;
  Summary of R2v3 Requirements (May 2021):
  https://sustainableelectronics.org/wp-content/uploads/2021/05/Summary-of-R2v3-Requirements.pdf
- [D4] NIST SP 800-88 Rev. 2, Guidelines for Media Sanitization, final 26 Sep 2025:
  https://csrc.nist.gov/pubs/sp/800/88/r2/final ; FAQ:
  https://csrc.nist.gov/files/pubs/sp/800/88/r2/final/docs/sp800-88r2-faq.pdf (FAQ via search summary).
- [D5] IEEE 2883-2022, Standard for Sanitizing Storage: https://standards.ieee.org/ieee/2883/10277/ ; SNIA talk:
  https://snia.org/sites/default/files/Security-Summit/2022/SNIA-SSS22-Hatfield-IEEE-2883-Standard.pdf
- [D6] GSMA Device Check: https://www.gsma.com/services/tac/about-device-check/ ; GSMA Device Registry:
  https://www.gsma.com/services/deviceregistry/ ; GSMA phone theft white paper, Oct 2024:
  https://gsma.com/solutions-and-impact/industry-services/wp-content/uploads/2024/10/Phone-Theft-White-Paper-MWC-Vegas-Oct-2024_10_08_24.pdf
- [D7] A phone maker's support pages on genuine parts and parts history. Withheld.
- [D8] The same maker's activation-lock support and community pages. Withheld; community posts are not policy.
- [D9] Resource Recycling, "Reverse logistics: the engine of the smartphone supply chain", 21 Jan 2026:
  https://resource-recycling.com/e-scrap/2026/01/21/reverse-logistics-the-engine-of-the-smartphone-supply-chain/ ;
  protection-provider refurbishment pages (withheld).
- [D10] JSES 2021, used-phone recovery value: https://reference-global.com/download/article/10.2478/jses-2021-0003.pdf ;
  refurbished smartphone price study (DergiPark, 2026, snippet only): https://dergipark.org.tr/tr/download/article-file/4469969
- [D11] Sokol, Moniz, Chawla, "Conformalized Selective Regression", arXiv 2402.16300 (2024):
  https://arxiv.org/abs/2402.16300 ; selective prediction sets with abstention, arXiv 1906.05473.
- [D12] A B2B liquidation marketplace's buyer guide on bulk phones (grades A–E and N; lot manifests by model, capacity
  and grade) and a liquidation services firm's guide on phone lots (locked → salvage). Withheld (may be channel
  partners). Search results, 24 Nov 2026; vendor sources.
- [D13] A large consumer marketplace's help pages on reserve prices and sale-event eligibility (14 days without a
  price change), and an auction house's ageing-fee policy. Withheld. Search results, 24 Nov 2026; platform-specific.
- [B1] Kato et al., "A Practical Guide of Off-Policy Evaluation for Bandit Problems", arXiv 2010.12470 (2020):
  https://arxiv.org/pdf/2010.12470 ; Joachims, counterfactual evaluation lecture (Cornell, 2016):
  https://www.cs.cornell.edu/courses/cs7792/2016fa/lectures/03-counterfactualmodel.pdf ; arXiv 2309.04222.
- [W1] Trade blog on used-phone depreciation methods (2026). Weak source; kept only for the repo's prototype erosion
  value.
- Repo (commit `5b1fcfd`):
  - `backend/di/services/modeler/templates.py`, `valuers/tool_fleet.py`, `valuers/device.py`, `modeler/simulate.py`,
    `modeler/suggest.py`, `modeler/apply.py`, `modeler/facts.py`
  - `services/cases/intake.py`
  - `services/engine/pool.py`, `gates.py`, `calibration.py`
  - `services/agents/limits.py`, `registry.py`, `forbidden.py`, `playbooks/case_autopilot.py`
  - `services/actions/decisions.py`, `org_pilot.py`, `models.py`
  - `core/policy.py`, `workflow/triggers.py`
  - `connectors/adapters/depot_repair.py`, `aws_iot.py`
  - `migrations/versions/0023_agent_identity.py`
  - `fixtures/golden/po/templates.json`
  - `source-sim/sim/vendors/` (leasing, depot repair, IoT, field service, QMS)
