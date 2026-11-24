# Recover: the five industry segments (source note, 24 Nov 2026)

What the team's **Recover prototype, "5 Industry Segments" (pre-final, received 24 Nov 2026)** specifies. It is the
target the research and plan 9 build towards.

> **Concept, not UI design.** The product owner shared the prototype to convey the *concept*: products, segments,
> decisions, stages, agents, guardrails, rules and data. It is **not** a UI or layout specification. Screen names
> (Pulse, Cases, Exceptions, Analytics…), the menu, panels and step tabs show what the product must *do*, not how it
> must look. Our UI follows our own design and the demo's parity rules. This note restates it in plain words so every report can cite it as
"01 §n". Numbers marked *sample* are the prototype's sample data (modelled, synthetic), not facts or forecasts.
Sample company, hospital and person names are left out.

What changed in this revision and why:
- Resolve and Reconcile removed (parked as out of scope, user decision 25 Nov 2026).

## 1. Recover on the Decision Intelligence core

**Decision Intelligence core:** models, agents, governance and memory. It reads signals from the enterprise
applications already in place. It puts one governed, explainable decision in front of the right owner and hands the
decision back to those applications to execute. It then learns from the outcome. There is no rip-and-replace: the
existing systems stay the systems of record. Recover runs in the client's cloud tenancy and reuses the client's data
adapters. If Recover is unavailable, returns follow the standard route.

| Product | Decision it answers | Signals | Status in the prototype |
|---|---|---|---|
| **Recover**: circularity | "Where is this returned item worth most?" It weighs every next life on total value against *named* demand (renewals, short pools, open repair orders, buyer bids). | Repair requests, contract ends, fleet swaps, pool excess, trade-ins, service desk, contract refresh | Live demo |

The prototype also showed two later products on the same core, Resolve and Reconcile. They are out of scope (user
decision, 25 Nov 2026); see parked/.

## 2. Recover's surfaces

- **Compose** (authoring, always present). Describe a business, and Recover builds the flow and connects the data.
  - **The five steps:**
    1. **Business flow.** The user types a description or picks a sample prompt. The *configuration agent* reads it
       (word count, explicit controls), matches an industry pack and lists the asset fields, stages, routes,
       guardrails (stated plus from the pack), systems (with adapters or needing one) and KPIs. It asks **one**
       clarifying question, then drafts the flow in the modeler. "It writes configuration, never code."
    2. **Adapter mapping.** Fields are proposed from the connected systems with a confidence score. Low-confidence
       fields carry a reason (for example "coded 0/1; meaning taken from the registry documentation"). A person can:
       - accept the field as suggested;
       - choose a different field;
       - accept it with a conversion;
       - mark it not needed;
       - ask the system owner.

       A **test run** puts past items through the draft flow and shows where cases stopped.
    3. **Agent mapping.** Each stage gets its agent and an autonomy level per agent (**Recommend only / Act within
       limits / Act alone**). A **confidence threshold** (65–85%, default 75%) applies: below it, any agent sends the
       item to a person with its recommendation. Guardrails are enforced by the platform whatever the autonomy.
    4. **Approve or modify.** The approver sees everything composed in steps 1–3. They can approve it, or send it
       back with a change pinned to the step it belongs to. Maker-checker applies: the person who composed it cannot
       approve it.
    5. **Publish.**
       - v1.0 is published to **one region at 20% of volume**.
       - A **replay** of past items compares the route mix (actual against flow) and reports straight-through %,
         approvals and exceptions per day, and modelled value uplift.
  - **Publishing generates the run-time screens.** **Decide** contains Pulse, Cases and Exceptions. **Understand**
    contains Analytics and Agents.
  - **Version history:** each version is listed with its audit log.
  - **Extensions:**
    - Add a system from the adapter registry.
      - Sources: catalogue connectors maintained by Recover, a generic REST adapter, or a connector built once from
        an API specification.
      - Sign-in: OAuth 2.0, a service account or an API key.
      - Environment: test first, then production. Access is read-only, or read plus writing decisions back.
      - Credentials go to the vault and are never shown again. The system owner approves the connection.
      - Discovery reads the objects and fields, samples 500 records and proposes mappings.
    - **Guardrails in plain words.** The assistant places a typed control on the right stage, and the screens,
      inbox, audit trail and KPIs update with it.
    - **Customer layer.**
      - A guardrail can be tightened or given an extra approver.
      - Compliance guardrails locked by the pack can't be weakened, suspended or removed.
      - **Diversions** add a step or a shortcut at a stage for a condition. A diversion that skips a compliance
        guardrail is **blocked**.
      - Pack updates never overwrite the customer's changes.
- **Access:** roles and scopes from the identity provider. Directory groups map to Recover roles. There is a "what
  each role can do" matrix and a "test a user" check. Members get access on the next sync.
- **Decide · Pulse:**
  - rates, suggestions and new items waiting;
  - where value is leaking right now;
  - *suggestion rules* that target the oldest value bands first (for example "move Offers → Auction when a listing
    has had no offer for 14 days").
- **Decide · Cases:** one decision per item, with its rationale. It shows:
  - the facts from connected systems, each with its source and age;
  - the recommendation, with value and confidence;
  - the alternatives, each with its value;
  - the evidence lines;
  - the guardrail results;
  - approve or override. An override needs a reason, which is logged and used to tune the rules.
- **Decide · Exceptions:** approvals, exceptions and alerts routed by role. Each item shows its cause, a recommended
  action and the owner.
- **Understand · Analytics:**
  - rates by item and drill-down;
  - analysis from a prompt, as a chart plus example records;
  - saved shared views;
  - alerts on a measure.
- **Understand · Agents:** the agents this flow runs, and their limits.
- **Tool-fleet extras** (Recover tool-fleet demo):
  - Service desk;
  - Contract refresh;
  - What-if ("move the market, see decisions change");
  - Models (a catalogue with quality and drift);
  - Integrations;
  - Modeler (process flows from industry templates, inside locked guardrails);
  - Data;
  - Ask.

## 3. The agents

**Recover tool fleet: seven agents, one decision chain** (sample runs, last 30 days):

| # | Agent | Does |
|---|---|---|
| 1 | Intake | Reads return events (fleet contract, service order, trade-in, tool pool) and opens one case per tool |
| 2 | Condition and life | Grade and fault from the repair workbench; remaining life from usage and repair history |
| 3 | Demand discovery | Real demand for every path: fleet renewals and orders, pool shortages, open repair orders needing parts, trade-buyer bids |
| 4 | Fit-for-use | Certifies harvested parts only when remaining life clears the threshold set by Quality |
| 5 | Valuation | Prices all six paths net of cost, logistics and time held |
| 6 | Disposition | Plans the **whole queue** on total enterprise value: each order filled once, refurbishment within repair-centre capacity, explained against the standard route |
| 7 | Follow-through | Hands the approved decision to the executing application, reminds the owner, records the outcome |

**Compose (every pack):** six stage agents: Intake (*act alone*), Condition (*act within limits*), Valuation (*act
alone*), Routing (*act within limits*), Follow-through (*act within limits*) and Analytics (*act alone*).

**Every pack uses the same seven stages:** return/receive → match/verify → condition → value each route → decide →
execute → close and learn.

**Model catalogue** (tool fleet):

| Model | Type | What it does |
|---|---|---|
| Condition estimate | Classifier | Fallback used only when the workbench grade is late, and always labelled as an estimate |
| Remaining-life estimator | Survival model | Remaining life per tool and per part |
| Demand forecaster | Time series per path | Forecasts demand on each path |
| Resale price estimator | Gradient boosting | Expected resale price |
| Refurbishment cost estimator | Regression | Expected refurbishment cost |
| Disposition optimiser | Constrained optimisation over the queue | Learns from every closed outcome |

Every model is shown with its quality, drift, last-trained date and retraining cadence. Thresholds and factor
tables change only with a person's approval.

## 4. Tool fleet AMS ("after-market services · power tools", pack v3.2)

Written by the fleet services lead. Unit: tools.

### 4.1 Returns (the Recover case)

- **Paths (Recover demo):** each path names its executing application and owner.

  | Path | What happens | Executing application | Owner |
  |---|---|---|---|
  | Re-issue to fleet | Issued against a named renewal or order | Fleet contract system | Fleet desk |
  | Refurbish → place | Always ends in a named destination: a contract, a buyer order or a pool request | Repair-centre work orders | Repair centre lead |
  | Tool pool | Loaner or pool stock transfer | Stock transfer | Tool pool planner |
  | Pre-owned sale | Sold to a named trade buyer or through the outlet | Pre-owned sales channel | Remarketing |
  | Harvest parts | Certified parts for *open repair orders* | Teardown and spare parts | Service parts planner |
  | Recycle | Certified recycling plus a circularity record | Recycler portal and ledger | Sustainability |

- **Routes (Compose pack):** redeploy, refurbish and re-rent, fix and return, upgrade offer, harvest, recycle.
- **Journey (8 stages):**
  1. Tools in use on site (the contract, with end dates and swap rights; renewal demand seen 60 days ahead).
  2. Repair or return requested (fleet app; a loaner promised).
  3. Pickup and inbound.
  4. Intake and diagnosis (technician grade, fault, estimate, remaining life, safety rules).
  5. Best next life decided.
  6. Approved and executed in place.
  7. Customer stays productive (back inside the turnaround promise).
  8. Learn and report (actual costs, pass rates and prices retrain the models; CO2 and parts reuse counted per
     tool).
- **Four value patterns:**
  - repairing a tool for a contract about to end → issue it to a renewal instead;
  - selling a grade A return while a pool is short → send it to the pool and cancel the new-unit requisition;
  - scrapping a tool whose parts are on open repair orders → harvest and certify those parts;
  - two returns promised to the same renewal → the queue plan fills each order once.
- **Guardrails:**
  - from the pack: safety recall check (compliance) and telematics under 7 days old (data quality);
  - stated: repair over $600 → fleet manager;
  - example added in plain words: write-off under 24 months → service operations.
- **Diversions:**
  - active safety recall → quarantine (a new step);
  - key account → account-manager review;
  - "new tool under 3 months: skip the recall check" → **blocked**.
- **Systems (7):** ERP, CRM, fleet contract system, connected-tool telematics, service desk, spare-parts catalogue,
  and a legacy depot repair log (needs a connector).
- **Canonical entities:** tool, return event, condition grade, remaining life, demand signal, market price, cost
  rate.
- **Exceptions:**
  - no active contract for the serial;
  - telematics and inspection disagree;
  - repair over the limit;
  - write-off under 24 months;
  - inspection backlog at a depot.
- **KPIs:**
  - value recovered per tool;
  - days to next use;
  - redeploy rate;
  - straight-through %;
  - upgrade offers accepted;
  - % held by guardrails.
- **Sample replay:** 3,420 tools, 81% straight-through and +9% value recovered, both modelled.

### 4.2 Service desk

"Every tool in for service, its next best action." Each ticket runs through intake, estimate, cover check,
valuation, disposition and follow-through.

- **Estimate:**
  - It is drafted from **similar past repairs** (same family, age band and fault, last 3 years).
  - Tickets with ≥50 matching past repairs are priced without a technician. The rest get a draft and a technician
    check.
  - Options re-run when the technician posts the fault.
  - Accuracy is shown on held-out repairs.
- **Options, priced for the customer and the margin:**
  - fix and return;
  - covered swap from refurbished stock (when cover terms allow);
  - upgrade with credit.

  Each option is net of parts, labour, credit and logistics.
- **Per-market rules:**
  - labour rates (for example €42/h in DE, €46/h in FR);
  - price lists and **credit rules** per market;
  - cover terms (for example "swap allowed for cordless tools").
- **Business rule:** upgrade only when the tool is past 50% of its life or the cover rules allow it.
- **Batches:** a site manager can send a batch, for example 22 tools split into upgrade 9, fix 11 and covered swap 2.
- **Test this decision:**
  - a credit lever shows the expected margin against the credit offered;
  - it uses take-up from the customer's last 24 months of offers.
- **Markets:** DE, UK, US and AU, with FR in pilot.
- **Sample measures:**
  - median time to a priced next best action, against 4 days for a manual quote before Recover;
  - upgrade take-up on uncovered tickets, against 6% when quotes were repair-only.

### 4.3 Contract refresh

"One proposal per expiring contract, built ahead" (90 days before the end). It runs intake, condition and life,
refurbished-stock matching, valuation and disposition.

- **Proposal content:**
  - keep tools with good remaining life;
  - **swap** worn tools for refurbished units with a life close to the rest of the fleet;
  - **upgrade** where parts end before the next term.
- **Business rule:** swap below 25% life; upgrade when parts end before the next term.
- **Pricing and approval:**
  - the proposal shows the fee, the saving against new tools and the likelihood to renew;
  - credits above $300 need sales approval;
  - on approval the proposal is emailed, the contract lines are drafted and the refurbished tools are reserved.
- **Sample:** contracts with a proposal 90 days ahead renewed at 90%, against 81% without.
- **Test this proposal:** levers for how evenly the fleet ages, and which tools change action.

## 5. Device recommerce ("Recommerce · phones and devices", pack v2.7)

Written by the recommerce operations lead. Unit: devices.

- **Stages:**
  1. Trade-in received.
  2. Verify against the quote (IMEI, model, capacity).
  3. Diagnose and grade (functional tests, battery health, photo grading).
  4. Price by channel (market prices and channel fees).
  5. Decide the channel.
  6. List and ship.
  7. Settle and learn.
- **Channels:** Buy Now, Offers, Auction and wholesale lot.
- **Guardrails:**
  - pack: blacklist and lock check;
  - stated: data-wipe certificate required, and never below 60% of the forecast price;
  - added: lot over $25,000 → commercial manager.
- **Customer rules:**
  - grade below the quote within 10% → adjust the payout automatically; larger gaps go to customer care with the
    grading photos;
  - wholesale lots are built by model and grade, bids come from approved buyers, and the lot sells to the best net
    bid.
- **Ageing suggestion rules:**
  - Offers → Auction after 14 days with no offer (choices 7, 10, 14 or 21);
  - Buy Now → Offers after 21 days unsold.
- **Diversions:**
  - a device from a named retail partner → a second grading check;
  - grade C and the model older than 3 years → wholesale lot directly;
  - "quote under $50: skip the blacklist check" → **blocked**.
- **Systems (8):** trade-in platform, diagnostics, photo grading, data-wipe tool, device registry
  (blacklist/lock), marketplaces, price feeds, ERP.
- **Canonical entities:** device, trade-in event, condition grade, compliance record, market price, cost rate,
  channel.
- **Exceptions and alerts:**
  - grade well below the quote;
  - missing wipe certificates on a batch (held and released automatically when they arrive);
  - marketplace price drop after a launch;
  - auction reserve not met (showing the cost of holding);
  - a wholesale lot over the limit.
- **KPIs:**
  - recovery rate of original value;
  - days to sale;
  - price realised against forecast;
  - straight-through %;
  - data-wipe compliance (100%);
  - grading disputes.
- **Analytics examples:**
  - price realised dropped after a new model launch, so move volume to wholesale earlier;
  - two retail partners cause 58% of grading disputes (screens graded before power-on).
- **Sample replay:** 18,600 devices, 88% straight-through and +6% net recovery, both modelled.
- **Example evidence line:** a battery swap lifts the price by $28 but costs $24 and adds 5 days.

## 6. Used cars ("Used vehicles · lease and trade-in returns", pack v1.9)

Written by the remarketing director. Unit: cars.

- **Stages:**
  1. Car returned (lease end or trade-in).
  2. Title and finance (title status, liens, outstanding finance).
  3. Inspect and estimate (inspection, photos, reconditioning estimate).
  4. Price by channel.
  5. Decide the channel.
  6. Recondition and list.
  7. Sold and learn.
- **Channels:** retail lot (which lot), wholesale auction, dealer trade, salvage.
- **Guardrails:**
  - pack: clear title with no open finance, and no retail with an open recall;
  - stated: recon over $2,500 → used-car manager;
  - added: auction under 40,000 miles → remarketing manager.
- **Customer rules:**
  - send each retail-ready car to the lot where it will sell fastest at the best price;
  - compare retail gross after recon with the auction price net of fees and transport;
  - flag cars on a lot for more than 45 days;
  - hail damage under the recon limit stays retail-eligible.
- **Diversions:**
  - an EV with battery health under 80% → battery assessment;
  - over 120,000 miles → auction directly;
  - "dealer trade within the group: skip the title check" → **blocked**.
- **Systems (8):** lease system, dealer management system, title and lien service, inspection app, recall
  database, auction platform, pricing guide, and a legacy body-shop system.
- **Exceptions and alerts:**
  - a lien found after check-in;
  - the odometer photo doesn't match the lease system;
  - EVs ageing at one lot (move them to the lot with demand).
- **KPIs:**
  - gross per car;
  - days in stock;
  - retail share;
  - straight-through %;
  - recon cost per car;
  - % held by guardrails.
- **Sample replay:** 2,140 cars, 79% straight-through and +$410 gross per car, both modelled.

## 7. Telecom network equipment ("Telecom network equipment", pack v1.4)

Written by the network asset manager. Units: radios, baseband units, routers, line cards, power units and microwave
links recovered from sites being upgraded.

- **Stages:**
  1. Decommission notified.
  2. Match to the network inventory.
  3. Wipe and test (configuration wipe, bench test, firmware).
  4. Value each route (open site demand, spares need, resale value).
  5. Decide the route.
  6. Execute (transfer, refurbishment order, broker listing).
  7. Close and learn (new spend avoided).
- **Routes:** redeploy to a site, refurbish as a spare, resell to a broker, harvest boards, recycle.
- **Guardrails:**
  - pack: the unit matches the network inventory, and a configuration-wipe certificate exists;
  - stated: export-control check before resale;
  - added: resale of current-generation cards → network planning.
- **Customer rules:**
  - spares before new: stock each region's spares pool from returns before buying new;
  - resell only what no region needs in the next 6 months;
  - the site-swap programme matches units to open site demand by model and firmware;
  - firmware two or more major versions behind must be upgraded before redeployment.
- **Diversions:**
  - a unit from a core site → security inspection;
  - firmware behind → upgrade step;
  - "urgent site outage: skip the configuration wipe" → **blocked**.
- **Systems (8):** network inventory, decommission tracker, ERP, field service app, test bench, spares planning,
  broker marketplace, recycler portal.
- **Example mapping:** the export class is inferred from the part number at low confidence (needs a person).
- **Exceptions and alerts:**
  - a unit not in the network inventory;
  - the configuration wipe failed;
  - power units idle in one region while another region buys new (a cross-region transfer rule).
- **KPIs:**
  - new spend avoided;
  - reuse rate;
  - spares filled from returns;
  - straight-through %;
  - days to redeploy;
  - export holds.
- **Sample replay:** 1,260 units, 84% straight-through and $1.1M new spend avoided, both modelled.

## 8. Medical rental equipment ("Medical rental · hospital equipment", pack v1.6)

Written by the rental fleet director. Devices: infusion pumps, patient monitors, electric beds, syringe drivers,
transport ventilators and pulse oximeters rented to hospitals.

- **Stages:**
  1. Device returned.
  2. Decontamination (record verified).
  3. Inspect and test (functional test, service status).
  4. Value each route (next demand, service cost).
  5. Decide the route.
  6. Execute (dispatch, service order, retirement).
  7. Close and learn (utilisation, turnaround).
- **Routes:** re-rent, service then re-rent, refurbish, retire.
- **Guardrails:**
  - pack: service and certification in date for the whole rental period;
  - stated: a decontamination record is required, and a repair over $1,000 → fleet manager;
  - added: retire under 5 years → clinical engineering.
- **Customer rules:**
  - send each device to the hospital that needs it next with the least travel, while service and certification
    stay in date for the rental;
  - bring servicing forward when it falls due within the next rental, and schedule it when the region's demand is
    lowest.
- **Diversions:**
  - from an isolation ward → enhanced decontamination;
  - the same hospital asks again within 24 h → re-rent directly;
  - "emergency request: skip the decontamination record" → **blocked**.
- **Systems (8):** rental system, asset management, decontamination log, biomedical service system, CRM, ERP, parts
  supplier portal, disposal partner.
- **Exceptions and alerts:**
  - no decontamination record (held until one exists);
  - certification expires during the rental (send a different unit);
  - turnaround slipping at a depot.
- **KPIs:**
  - fleet utilisation;
  - turnaround time;
  - re-rented within 48 h;
  - straight-through %;
  - compliance exceptions;
  - repairs over the limit.
- **Sample replay:** 1,880 devices, 83% straight-through and +6 pts utilisation, both modelled.

## 9. What is common to all five (the pack contract)

Every pack carries the same parts:

- **Identity:** a name, a pack version and the unit.
- **Author:** the role that writes the description.
- **Sample prompts:** three.
- **Configuration agent:** its reading log and the one clarifying question.
- **The flow:**
  - seven stages, each with its agent;
  - routes or channels;
  - guardrails typed *Compliance / Data quality / Threshold / Approval*, each placed at a stage.
- **Data:**
  - the systems needed, each marked as having an adapter or needing a connector;
  - about seven canonical entities;
  - field mappings with confidence, and the reason when a mapping is unsure.
- **Evidence:**
  - a replay dataset;
  - an example asset with facts, each showing its source and age;
  - the recommendation, alternatives, evidence and guardrail results.
- **Run-time screens:**
  - exception and alert types with an owner each;
  - six KPIs and a trend;
  - two worked analytics questions.
- **Customer layer:** diversions, including one blocked compliance skip.

The engine is the same for every pack. "Decide and Understand" is one engine for every industry pack.
