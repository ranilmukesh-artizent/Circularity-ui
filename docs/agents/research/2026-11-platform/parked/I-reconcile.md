# I. Reconcile: service and logistics settlement on the same core (24 Nov 2026)

> Plan task IDs (P9-x.y) in this report follow [plan 9 revision 2](../../plans/09-agentic-platform.md) (remapped 25 Nov 2026; its last table maps old to new).

Report I of the platform research (brief: [00-brief.md](00-brief.md); product family: [01 §1](01-recover-segments.md)).
Reconcile answers *"What should be paid, charged, recovered or settled for this repair or shipment?"* It is the third
product on the Decision Intelligence core, after Recover and Resolve. This report also folds in the gap the research
called "stage 4: ERP/WMS financial reconciliation" (README §1, G §4.D, plan 9 revision 1 P9-5.2, now Reconcile v1 P9-7.1).

How it was made:

- The code was read at `5b1fcfd` (`feature/fullstack-poc`). Nothing was run.
- Web sources were read on 24 Nov 2026 with generic search terms. They are listed at the end as [R#] with dates.
- Vendor statements are vendor claims. Nothing was tested hands-on.
- Anything not confirmed is marked **unconfirmed**.

Sizes follow G: **S** ≤ 2 days, **M** ≤ 1 week, **L** > 1 week (one engineer who knows the repo, tests included).
These are first-pass estimates, not commitments. Links are relative to this folder (`../../../../` is the repo root).

**Legal and Finance note.** Everything below on contracts, statutory dispute windows, freight law, warranty law,
accounting standards (derecognition, revenue, provisions), tax and licences is orientation only. It needs review by
Kinective's Legal team, and the accounting parts also need the customer's Finance team, before anyone relies on or
acts on them.

## Summary

1. **Reconcile is Recover's missing back end, and it fits the same seven stages.** Recover predicts every cost line
   of a route: `ex_trace` gives each line a method (Retrieved, Contracted or Modelled), a source and a why
   ([trace.py:21](../../../../backend/di/services/execution/trace.py#L21)). Reconcile checks the invoices that arrive
   afterwards against what actually happened. It then decides one of six outcomes: **pay, short-pay, dispute, charge
   the customer, recover from a supplier, or accrue**. A person approves anything that moves money, or a standing
   policy that a person owns approves it (D4).
2. **The demo already sketches it.** RT-1048's actuals include "Waiting charge at LOC-CHN-03", sourced as
   "Reconcile · … 3PL bill", with the note "Detention clause 7.2, checked against gate and release times"
   ([trace.py:292–300](../../../../backend/di/services/execution/trace.py#L292)). The OTM mock's rate card already
   carries docket, part-load minimum, detention free minutes and detention $/h. Its tracking events carry the X12 214
   arrival and delivery codes (X1, D1). **But nothing computes the check today:**
   - `detFree` and `detUsd` are declared in [lanes.py:46](../../../../backend/di/services/execution/lanes.py#L46)
     and used nowhere else;
   - the OTM adapter reads rate terms 1–3 only ([otm.py:210–212](../../../../backend/di/connectors/adapters/otm.py#L210));
   - every other modelled actual is a deterministic ±25% hash, apart from a few pinned lines (`LEARN_PIN`, `LINE_EXACT`) ([trace.py:274](../../../../backend/di/services/execution/trace.py#L274)).
3. **Stage 4 folds in as Reconcile's "close" half.** Freight audit and repair-invoice validation set the actual cost
   lines. Those lines replace the hashed actuals behind `outcome.confirm`. Credit settlement, fixed-asset retirement,
   accruals and the variance queue become Reconcile outcomes that are executed as instructions to the ERP. The ERP
   stays the book of record. **We never pay**: we release, block or short-pay invoices that the ERP pays.
4. **The market is split three ways:** freight audit and payment (FAP) providers (the most agentic in 2026), warranty
   management suites (claims and supplier recovery), and AP automation suites with agents. None links a charge to a
   *decision* about the asset (route, predicted cost, contract cover) across freight, repair and warranty in one case.
   That link is our angle. FAP vendors sell audit as a service, often paying for you; we are self-hosted software that
   hands the result to the customer's own AP.
5. **OSS: small, permissive, no new container:** `pydifact` (MIT) and our own X12 tokenizer with 210/214/810 loop maps
   (D3); `pdfplumber` (MIT) and `pypdf` (BSD-3); `factur-x` (BSD) for EU e-invoices; `rapidfuzz` (MIT); ZEN (MIT) for
   rate-term, tolerance and cover tables (D2); scikit-learn `IsolationForest` (BSD-3) once D2's ML step brings numpy.
   **Avoid:** PyMuPDF (AGPL or commercial), marker's weights (OpenRAIL-M, $5M revenue limit), Bots (GPL).
6. **Stories:** 22 RC stories, P0 8, P1 9, P2 5. Tool fleet first.
7. **Proposed plan-9 slot:** RC-08 (real actuals into the outcome) joins **TF-07 in Phase 3** (P9-3.5, pilot-critical);
   Reconcile v1 (freight and repair audit, settlement, AP handoff) **replaces revision 1's P9-5.2 as P9-7.1 in Phase 7**, size **L**; warranty
   attribution with supplier recovery, then finance close, follow at **M–L** each.

## 1. What Reconcile decides

### 1.0 The decision shape (shared by every case kind below)

A **settlement case** opens per charge document: a carrier invoice, a repair invoice, an auction or broker settlement
statement, a trade-in payout batch, or a period-end close item. It links to the Recover case(s) and the executed
instructions it charges for. It runs the same seven stages as every pack (01 §3): charge received → match to what
happened (shipment, work order, PO, receipt, contract) → establish facts (evidence) → price each outcome → settle →
hand to AP/AR/supplier portal → close and learn.

**Outcomes (per line, rolled up per document):**

| Outcome | Meaning | Executed as (instruction) |
|---|---|---|
| Pay | Line matches expected within tolerance | Release the AP invoice (or leave it unblocked) |
| Short-pay | Pay the expected amount; the difference is disputed or written back | AP partial payment / reduced approval with a reason code; a debit memo for the difference |
| Dispute | Hold the line; send an evidence pack to the payee | AP payment block with a reason; a dispute record with a deadline |
| Charge customer | The cost is the customer's (misuse, out of cover, missing tool, damage) | AR invoice / billing request in the ERP |
| Recover from supplier | The cost is a supplier's (supplier warranty, carrier liability, repairer rework) | Supplier claim / chargeback / debit memo |
| Accrue | Service delivered, not yet billed (or disputed at period end) | Accrual journal entry, reversed when the invoice lands |

**Pricing each outcome.** Each outcome is priced like a route: net amount, chance of success, cost to pursue
(handling time, relationship) and time to cash. Disputing a $9 accessorial costs more than it recovers. An agent
should say so and propose "pay and flag the carrier" instead.

### 1.1 Freight audit (tool pickup and delivery, inbound returns, transfers)

- **Evidence:** the TMS shipment (lane, carrier, weight, equipment ordered, status); the contracted rate card (lane
  rate, per km, minimum, docket, part-load bands, accessorial schedule, fuel table); tracking events (arrival X1,
  departure, delivery with proof of delivery D1, failed delivery, appointment); gate-in/out times from the WMS or yard;
  the carrier invoice (EDI 210, CSV or PDF); the fuel index for the invoice week (e.g. the EIA weekly diesel price [R17]).
- **Checks:**
  - **Rate vs contract:** billed base vs the rate card in force on the ship date, with minimum-charge logic.
  - **Accessorials:** *detention* only beyond the free minutes, from arrival and release times; *liftgate* only if the
    equipment ordered or the site profile needs one; *residential* by site type; *re-delivery* not billable after a
    carrier-caused failed delivery; *fuel surcharge* = the table row for the index week; inside delivery, appointment.
  - **Duplicates:** the same load, PRO or invoice number (fuzzy) billed twice, or a re-bill overlapping the original
    [R27]. **Weight:** billed vs shipped. **Not ours:** shipment not in the TMS.
- **Outcomes:** pay; short-pay with a reason code per line; dispute (e.g. detention without matching gate times);
  recover from the carrier (damage or loss claims: separate, out of v1); accrue delivered loads with no invoice.
- **Approvals and tolerances** (pack data; *sample* defaults):
  - Auto-pay when every line is within ±2% or $10 and the total is under $500: a standing policy owned by the
    logistics finance lead. Any short-pay or dispute goes to a person until the customer approves a standing policy for
    named reason codes (e.g. "detention without gate evidence").
  - In US practice the shipper has 180 days from receipt to contest a motor carrier bill, and the carrier 180 days to
    issue extra bills (49 U.S.C. 13710(a)(3), [R14]); court actions over charges have 18 months (49 U.S.C. 14705,
    [R15]). Reconcile runs these as **timers on the dispute**, configured per jurisdiction. Legal review needed.

**The demo's worked case, RT-1048:** rate card `RC-2026.2` with `detFree` 120 min and `detUsd` 72
([lanes.py:43–47](../../../../backend/di/services/execution/lanes.py#L43)); the bill shows 75 billable minutes = $90.00
= ₹7,515 at 83.5 ([trace.py:297](../../../../backend/di/services/execution/trace.py#L297)). Reconcile v1 must
**recompute that line from tracking events and get the same ₹7,515** (parity, rule 1).

### 1.2 Third-party repair invoice validation

- **Evidence:** the repair order (fault, scope, operations and hours, parts issued, labour rate; the Depot Repair
  adapter already writes `intervention.hours`, `labour_rate`, `parts`, `parts_cost`, `cost`, `repair_order_ref`,
  [depot_repair.py:11–16](../../../../backend/di/connectors/adapters/depot_repair.py#L11)); **standard hours** per
  family and fault (Recover's service desk already prices from "similar past repairs", 01 §4.2); the repairer contract
  (labour rate per market, e.g. €42/h DE and €46/h FR *sample*; parts mark-up cap; approval limit); BOM and spare-parts
  catalogue; teardown findings and photos; the estimate the decision approved.
- **Checks:** hours vs a standard *band* learned from past repairs; rate vs contract for the market and date; each
  part on the BOM for that model, issued to that work order, priced within catalogue plus cap; total vs the approved
  estimate (an overrun past "repair over $600 → fleet manager", 01 §4.1, needs that approver); no repeat repair on the
  same serial within the rework window (charge the repairer instead).
- **Outcomes:** pay; short-pay hours over standard without a reason; dispute parts not on the BOM; recover rework from
  the repairer; charge the customer when the fault is out of cover (§1.3).
- **Approvals:** within +10% of estimate and standard, a standing policy; above that or any part off the BOM, the
  repair-centre lead.

### 1.3 Warranty versus chargeable attribution, and supplier recovery

- **Evidence:** the cover (warranty or service contract: start, end, what it covers, exclusions such as misuse, wear
  parts, consumables; ServiceNow already gives `warranty_expiration`,
  [servicenow.py:174](../../../../backend/di/connectors/adapters/servicenow.py#L174)); the in-service date; telemetry
  (overload events, drop and impact counters, hours beyond rated duty); teardown findings (misuse vs manufacturing
  defect); photos; recalls and service bulletins; the supplier's terms for the failed component (part mapping,
  recovery window, parts-return rule).
- **Decision:** who bears the cost (our warranty, the customer, or a supplier) and the share when mixed (a covered
  motor with a chargeable broken housing). Each attribution is a rule match or a model score **with the evidence
  lines shown**, like Recover's value lines.
- **Outcomes:** accept under warranty (cost to the reserve); charge the customer; recover from the supplier (a claim
  with the evidence bundle, the failed part held or returned); goodwill (a person's choice with a reason, logged like
  an override).
- **Approvals:** customer charges above a threshold, any goodwill and any misuse finding that rests on a model score
  go to a person (service operations); supplier claims are sent by a person or a standing policy per supplier.

Warranty vendors sell supplier recovery as automatic claim generation from supplier terms and part mapping
[R11][R12]. That is the part to copy (§3).

### 1.4 Trade-in payouts and buyer settlements (device recommerce)

- **Payout adjustment at receipt.** The pack rule exists (01 §5): a grade within 10% below the quote adjusts the
  payout automatically; a larger gap goes to customer care with the grading photos. Reconcile owns the money side:
  the adjusted amount, the reason code, a clawback when a device later proves blacklisted or locked, and the payout
  instruction to the trade-in platform.
- **Buyer settlements:** marketplace payouts net of fees vs expected fees per channel; buyer returns and chargebacks
  after sale; wholesale lot settlements vs the winning bid, less grade disputes.
- **Outcomes:** pay as adjusted; hold the payout (fraud evidence); dispute a marketplace fee; accept a buyer return
  and send the device back to Recover.

### 1.5 Recycler and broker settlements, auction fees and recon invoices (telecom, used cars)

- **Telecom:** broker settlements vs listing price, bench-test result and export-control check; recycler settlements
  (rebate per kg by material, or a charge) vs the weights recorded at handover; the certificate of recycling or
  destruction is **required evidence before payment or release** (R2v3 requires qualified, tracked downstream vendors
  [R22]; Legal review needed).
- **Used cars:** auction fee statements (buy and sell fees, transport, recon) vs the fee schedule; post-sale
  arbitration adjustments within the auction's window (windows vary by channel and local policy; the NAAA guidelines
  are revised each 1 June [R21]); body-shop recon invoices vs the approved estimate, with the "recon over $2,500"
  guardrail on the overrun (01 §6).

### 1.6 Fixed-asset retirement, credit settlement, accruals and the variance queue (stage 4)

These are the P9-7.1 items. Each is an outcome of a closed Recover case plus its Reconcile cases:

- **Fixed-asset retirement.** When a route ends the asset's life in the owner's books (sell, recycle, harvest with
  scrap of the rest, exit), Reconcile proposes a retirement: asset number, date, proceeds net of the reconciled costs,
  and for harvest which parts move to inventory. Under IAS 16 an item is derecognised on disposal or when no future benefit is expected. The gain or loss is the net
  disposal proceeds less the carrying amount (paras 67 and 71, [R19]); US GAAP has its own guidance (ASC 360, not read
  here, **unconfirmed**). The asset's `book_value` already comes from S/4
  ([s4.py docstring](../../../../backend/di/connectors/adapters/s4.py#L1)). The posting is Finance's: an instruction
  held for Finance, never an agent write.
- **Credit settlement:** a customer credit memo or refund on a return, swap or trade-in, and credits under the
  service-desk and contract-refresh rules (01 §4.2–4.3: "credits above $300 need sales approval", *sample*). Revenue
  reversal and refund-liability accounting is orientation only (IFRS 15 B20–B27, B28–B33 [R20]); Finance decides.
- **Accruals** for delivered-unbilled freight and closed-uninvoiced repairs at period end, reversed when the invoice
  is reconciled.
- **Variance queue:** every line outside tolerance, unmatched invoice and unreconciled outcome is an item in "My
  work" (P9-5.8) with owner, age and recommended action; WMS stock value vs ERP (G §2.12) joins as one more check.

## 2. Industry practice

- **Freight audit and payment (FAP).** Pre-audit before payment (rate, duplicate and accessorial checks against
  contract and shipment data); post-audit recovery after payment, usually by a contingency-fee firm; payment often run
  by the FAP provider. Common errors across vendor guides: duplicates, fuel surcharge miscalculation, accessorials not
  provided (detention, re-delivery, inside delivery), wrong rates; recoverable error is put at 3–7% of spend by vendor
  benchmarks (**unconfirmed**) [R27]. EDI: the 210 is the motor carrier invoice (B3 header with net amount due and
  SCAC; L1 charge lines with codes such as 405 fuel surcharge and BAS base charge; L3 totals) [R16]; the 214 carries
  shipment status; EDIFACT INVOIC is the international invoice [R28]. The shipper's audit compares the 210 with the
  TMS's rated cost. Shipium's 2026 launch rests on "the expected cost already exists as a platform record" [R1], which
  is our position too (`ex_trace`).
- **Three-way match.** Invoice vs PO price and vs receipt quantity, with tolerances. Outside tolerance Oracle holds
  the invoice until released; Dynamics 365 flags it, with a default price tolerance of 0% [R18]. Freight and services
  have no goods receipt: their "receipt" is the proof of delivery or the work-order confirmation, so Reconcile
  supplies the third leg for service invoices.
- **Warranty management and supplier recovery.** Claim intake and validation (cover, duplicates, labour-time
  standards, parts), adjudication, payment or credit to the dealer or repairer, then **supplier recovery**: map the
  failed part to its supplier, apply the supplier's terms, generate a claim, manage the parts return, track the
  recovery rate [R11][R12]. Warranty AI vendors add suspect-claim analytics, claim clustering and peer averaging of
  labour and parts cost [R10].
- **Dispute and deduction management.** Score claims by value and recovery likelihood, assemble backup documents
  (contract, proof of delivery, pricing), submit on portals, track deadlines [R13]; Basware's planned Supplier Agent
  explains disputed invoices to suppliers [R6].
- **Accounting references (orientation only; Legal and Finance to confirm).** IAS 16 paras 67–72 derecognition [R19];
  IFRS 15 B20–B27 right of return and refund liability, B28–B33 assurance-type vs service-type warranties, with
  assurance-type under IAS 37 and ASC 606/460 for US GAAP [R20]; ASC 360 retirement (**unconfirmed**, not read). We
  compute none of this: we propose entries with evidence; the ERP and Finance post them.

## 3. Competitive landscape

| Vendor | Category | What it does | Agentic features (status, date) | Gap against Reconcile |
|---|---|---|---|---|
| **Loop** | FAP, logistics data platform | Freight and parcel audit and pay; "Logistics Data Platform" | Launched 4 May 2026 with agents rolling out (vendor onboarding, PO validation, GL coding, audit expansion); "Loop Intelligence" assistant 13 Jul 2026 [R3]. Named in a 2026 analyst market guide for FAP (vendor's claim) | Freight only; no asset decision, repair or warranty; SaaS |
| **Trax Technologies** | Global FAP | Audit, payment, spend data | AI Extractor and Audit Optimizer described as live; invoice-contract comparison agents and "autonomous exception management" are **roadmap, undated** [R2] | Freight only; exceptions roadmap; SaaS |
| **Shipium** | Shipping execution + audit | "Always-On Audit": real-time check against the rate it chose at execution; findings feed carrier selection | Announced 25/26 Aug 2026; "an increasing number of AI agents"; GA **unconfirmed** [R1] | Parcel/outbound focus; tied to its own execution |
| **Cass Information Systems** | FAP, payment processor | Freight payables at scale ($37B a year, per coverage) | Tariff/customs AI via a partnership, 26 Feb 2026 [R4]; no freight-audit agent found (**unconfirmed**) | Service-heavy; no asset or warranty link |
| Transflo | Carrier/broker side | Workflow AI for LTL audit and invoicing, 22 Jan 2026 [R5] | Carrier-side | Not a shipper tool |
| **Tavant** (Warranty AI, Supplier Recovery) | Warranty management | Claim creation from DMS work orders, AI adjudication with an explanation, suspect-claim analytics, supplier recovery from supplier terms and part mapping | Agents named on the product page (Claim Creator, AI Adjudicator, Partner Assist); no GA dates [R10][R11] | Dealer and OEM warranty; no freight; no disposition |
| **Syncron** (Warranty) | Aftermarket suite | Claims, supplier recovery, service contracts | Field-data partnership for warranty decisions 29 May 2026; Service Contract Performance 7 Oct 2026; no agentic claim automation found [R12] | Same as above; possible partner (C §2.5) |
| PTC Servigistics | Service parts | Agentic AI for service planning (Spring 2026) | No warranty-claims agent found (**unconfirmed**) | Planning, not settlement |
| **Basware** | AP automation | Invoice capture, matching, approvals | AP Business and Data agents introduced; Supplier Agent (disputes) and AP Pro Agent planned for 2026; "autonomy gates" apply policy before an action, 24 Feb 2026 [R6] | Generic AP; no operational evidence (tracking, telemetry, teardown) |
| Tungsten Automation | AP automation | InvoiceAgility+: agents across intake, matching, coding, approvals | Announced 30 Sep 2026; GA **unconfirmed** [R7] | Same |
| Microsoft Dynamics 365 BC / AvidXchange | ERP / AP | PO-to-invoice matching agents | Payables Agent (2025 wave 2) [R8]; AvidXchange PO Matching Agent, Jul 2025 [R9] | Matching only; goods POs |
| HighRadius | Order-to-cash deductions | Claims capture, backup gathering, dispute packages, portal submission | "12+ AI agents" (vendor page, undated) [R13] | Receivables side (customer deductions), CPG focus |

- **Top three to watch:** (1) **Loop**, the most agentic FAP, funded, platform ambition; (2) **Tavant**, warranty
  adjudication and supplier recovery with agents; (3) **Basware**, AP agents behind explicit policy and "autonomy
  gates", the same pattern as our hold policy.
- **Gaps they leave:** no one ties freight, repair, warranty and disposal of the **same asset** to the decision that
  caused them; no one shows the predicted line beside the billed line with its method and source; none is
  self-hosted with maker-checker on the audit rules themselves.
- **What to copy:**
  - **Expected-cost-at-execution** as the audit baseline (Shipium) [R1]. We have it in `ex_trace`.
  - **Reason-coded short-pay** and dispute packages assembled automatically (HighRadius) [R13].
  - **Supplier recovery from supplier terms + part mapping** with a parts-return step (Tavant) [R11].
  - **Labour/parts peer averaging by cluster** for repair invoices (Tavant) [R10]. That is our "similar past repairs".
  - **Policy gates before any action**, and a supplier-facing dispute explainer that a person approves (Basware) [R6].
  - Feeding audit findings back into routing and carrier selection [R1]. For us that means Recover's valuer.

## 4. Open source for the Reconcile parts

The constraints: Postgres is the only store; no new container in the trial package; permissive licences;
Python 3.12 in the api and worker. Versions and dates come from PyPI on 24 Nov 2026 [R23] unless noted. Licence
lines need review by Kinective's Legal team.

| Need | Project | Licence | Latest (date) | Python fit | Verdict |
|---|---|---|---|---|---|
| EDIFACT INVOIC | `pydifact` | MIT | 0.2.3 (10 Apr 2026) | Pure Python | **Adopt** (already chosen, D3) |
| X12 210 / 214 / 810 / 820 | Own tokenizer + loop maps as data | ours | n/a | Pure Python | **Build** (D3 named 180/856 first; add 210, 214, 810 maps: ~3 days more) |
| X12 reference | `pyx12` | BSD | 4.1.0 (6 Nov 2026) | Healthcare maps | Learn from |
| EDI translator | Bots | **GPL-3.0** | 3.3.1 (2019) | Server | **Avoid** |
| PDF text and tables | `pdfplumber` | MIT | 0.11.11 (21 Nov 2026) | Pure Python | **Adopt** |
| PDF basics | `pypdf` | BSD-3 | 7.1.1 (18 Nov 2026) | Pure Python | **Adopt** |
| PDF tables | `camelot-py` | MIT | 2.2.0 (21 Nov 2026) | Needs a PDF backend | Optional |
| Template invoice extraction | `invoice2data` | MIT | 1.0.1 (1 Aug 2026) | YAML templates per issuer | **Learn from / adopt** for fixed-layout repairer invoices |
| EU e-invoice (Factur-X/ZUGFeRD XML in PDF) | `factur-x` | BSD (classifier) | 7.10 (19 Nov 2026) | Pure Python | **Adopt narrowly** (EU repairers) |
| Layout-aware conversion | `docling` | MIT (code) | 2.152.0 (23 Nov 2026) | Brings torch and models; model page tags apache-2.0 and cdla-permissive-2.0, which applies to what is **unconfirmed** [R26] | Optional profile only, not in the trial |
| Layout conversion | `unstructured` | Apache-2.0 | 0.27.37 (6 Nov 2026) | Heavy | Avoid in the trial |
| PDF to markdown | `marker-pdf` | Code Apache-2.0; **weights modified OpenRAIL-M, free only under $5M revenue/funding** [R24] | 2.2.0 (12 Nov 2026) | Heavy | **Avoid** (source-available-like weights) |
| PDF engine | PyMuPDF | **AGPL-3.0 or commercial** | 2.1 (2 Nov 2026) | Native | **Avoid** |
| Fuzzy matching (invoice no., PRO, names) | `rapidfuzz` | MIT | 3.14.6 (30 Aug 2026) | Native wheels | **Adopt** |
| Phonetic matching | `jellyfish` | MIT | 1.3.0 (16 Oct 2026) | Native wheels | Optional |
| Record linkage | `splink` | MIT | 5.0.0 (28 Sep 2026) | Postgres backend is "relatively new", minimally supported, with fuzzy-string gaps [R25]; DuckDB default | Learn from; maybe for back-test batches only |
| Record linkage | `dedupe` | MIT | 3.0.3 (15 Aug 2024) | Slow cadence | Avoid |
| Record linkage | `recordlinkage` | BSD-3 | 0.16 (20 Jul 2023) | Stale | Avoid |
| Rate terms, tolerances, cover tables | `zen-engine` | MIT | 2.1.8 (20 Nov 2026) | abi3 wheels | **Adopt** (D2). Use it to *pick* the term or row; do the money arithmetic in Python `Decimal` (E §3.1: ZEN number precision **unconfirmed**) |
| Anomaly flags | scikit-learn `IsolationForest` | BSD-3 | 1.9.1 (10 Sep 2026) | Comes with LightGBM/MAPIE (D2) | **Adopt** when D2's ML lands |
| Anomaly library | `pyod` | BSD-2 | 3.6.9 (22 Nov 2026) | Many models | Learn from |
| Back-test imports of paid invoices | `pandera` | MIT | 0.36.0 (10 Nov 2026) | pandas | **Adopt narrowly** (D3) |
| Money type | `py-moneyed` | BSD | 3.0 (27 Nov 2022) | Stale | Avoid; keep `Decimal` and dated FX notes as the adapters do ([otm.py:45](../../../../backend/di/connectors/adapters/otm.py#L45)) |

**Notes on the table:**

- **No numpy or scikit-learn today.** The api's direct dependencies are FastAPI, SQLAlchemy, psycopg, httpx, mcp,
  groq and a few more ([requirements.in](../../../../backend/requirements.in)). Anything ML arrives with D2's
  LightGBM/MAPIE step, not before.
- **Rules first.** Reconcile v1 needs no ML: rate cards, tolerances and evidence rules are deterministic.
- **Document extraction.** Use D1's **dual-LLM extraction**: a quarantined call with no tools returns a typed
  `ChargeDocument`, which is validated (the totals add up, the lines sum to the invoice, the payee is known) before
  the planner sees it. A run that read an untrusted PDF holds its writes (D1 taint rule).

## 5. Data needed and canonical entities to add

| System type | What Reconcile reads | Today in the repo |
|---|---|---|
| TMS | Shipments, rate offerings (all terms incl. accessorials and fuel table), tracking events (arrival, departure, failed delivery, POD), actual cost | OTM: rates, shipments, tracking X1/D1, `totalActualCost`. The adapter maps terms 1–3 only; terms 4–7 (docket, part-load minimum, detention free min, detention $/h) sit unread in the mock ([seed.py:167–170](../../../../source-sim/sim/vendors/otm/seed.py#L167)) |
| Carrier invoices | EDI 210 / CSV / PDF; EDIFACT INVOIC | **Missing**: no invoice resource in the OTM mock |
| WMS / yard | Gate-in/out, receipt confirmation | Manhattan reservations and orders; gate times **missing** |
| ERP AP | Supplier invoices and lines, payment blocks, payment status, debit memos | EBS payables catalogue mock (invoices and suppliers; invoices deliberately "not mapped", [catalog.py:132–137](../../../../backend/di/connectors/catalog.py#L132), [catalog_ebs.py](../../../../source-sim/sim/generic/specs/catalog_ebs.py)); S/4 AP **missing** |
| ERP GL / FI-AA | Journal entries, asset book value, retirement, accruals | S/4 journal post and read-back ([writers.py:320](../../../../backend/di/services/instructions/writers.py#L320)); `book_value`; retirement and accruals **missing** |
| ERP AR / billing | Customer invoices, credit memos | **Missing** (B13b: credit memo is a simulated acknowledgement) |
| Service / repair | Repair orders, hours, labour rate, parts, teardown findings, estimate | Depot Repair (yes); standard hours **missing** |
| Warranty registry / contracts | Cover terms, exclusions, in-service date, supplier terms, part-to-supplier map | `warranty_expiration` only; contract terms are TF-02 (P9-3.1, missing) |
| Telematics | Overload, impact and hours beyond duty | AWS IoT facts (hours) |
| Rate cards and contracts | Carrier MSA, repairer contract, recycler rebate schedule, auction fee schedule | Rate card as a constant ([lanes.py:43](../../../../backend/di/services/execution/lanes.py#L43)) and in OTM |
| Marketplaces / auctions / brokers / recyclers | Settlement statements, fees, arbitration, weights, certificates | Machinio and auction mocks for demand; settlements **missing** |

**New canonical models**, added to `CONNECTOR_FIELDS` with types
([fields.py](../../../../backend/di/services/canonical/fields.py)) and the same held-record and conflict rules:

| Model | Key fields |
|---|---|
| `charge_doc` | doc_id, kind (freight, repair, settlement, payout, fee), payee, payer, currency, total, issue_date, received_date, source_format, refs (shipment, WO, PO, case) |
| `charge_line` | doc_id, seq, code (normalised: base, fuel, detention, liftgate, residential, redelivery, labour, part, fee, rebate), qty, unit, rate, amount, ref |
| `rate_term` | contract_ref, payee, term code, basis, value, valid_from/to, free_qty (e.g. free minutes) |
| `service_event` | ref, kind (arrived, departed, POD, failed delivery, gate in/out, WO closed), at, source |
| `cover` | asset/serial, kind (warranty, service contract, supplier warranty), start, end, covered parts, exclusions |
| `claim` | kind (dispute, supplier recovery, customer charge, carrier liability), against, amount, status, deadline, evidence refs |
| `settlement` | doc_id, per-line outcome and expected amount, reason code, policy/approver, instruction refs, status |
| `retirement` / `accrual` | asset, proceeds, carrying amount (read), period; accrual amount, reverse-on doc |

## 6. Roles and user stories

**Roles.** New: logistics finance (freight AP), warranty administrator, AP clerk, controller (period close). Existing:
Finance (`finance`), repair-centre lead, service operations, fleet manager. Actor *Agent* = the agent acts; *Person* =
a person approves or acts.

| ID | P | Story (Given / When / Then) | Actor |
|---|---|---|---|
| RC-01 | P0 | Given a carrier invoice arrives (210, CSV or PDF), When it is read, Then one settlement case opens per invoice, linked to its shipments and Recover cases; a duplicate (same load, or invoice no. within a fuzzy match) opens no second case and is flagged | Agent |
| RC-02 | P0 | Given an invoice line and the rate card in force on the ship date, When audited, Then the expected amount with its calculation ("34 km × ₹20 + ₹1,200 load, min ₹3,600") sits beside the billed amount, with the variance and the rule | Agent |
| RC-03 | P0 | Given an accessorial line, When audited, Then it is checked against evidence (detention vs arrival/release minus free minutes; liftgate vs equipment; re-delivery vs failed-delivery cause; fuel vs the index-week row); RT-1048's detention recomputes to ₹7,515 | Agent |
| RC-04 | P0 | Given a repair invoice, When audited, Then hours vs the standard band, the rate vs the market contract, each part vs the BOM and issue, and the total vs the approved estimate are shown with a variance per line | Agent |
| RC-05 | P0 | Given a repair on a tool, When attributed, Then it is marked warranty, chargeable or supplier-recoverable (or split) with the cover, the dates and the misuse evidence lines; low confidence goes to a person | Agent; Person on low confidence |
| RC-06 | P0 | Given a proposed settlement, When every line is within tolerance and under the value threshold, Then a standing policy approves it and the journal says "approved by policy P vN, owner X"; otherwise it waits for a named person | Person / policy |
| RC-07 | P0 | Given an approved settlement, When executed, Then AP receives release, short-pay with a reason code, or a payment block with a dispute reference, idempotent on the settlement key, and the confirmation is read back | Agent |
| RC-08 | P0 | Given a closed Recover case with reconciled invoices, When Finance confirms the outcome, Then the actual cost lines come from the settlements (not the hashed actuals), each with the explanation; the demo cases keep today's lines (parity) | Agent; Person confirms |
| RC-09 | P1 | Given a disputed line, When the agent assembles the dispute pack (contract clause, tracking events, POD, calculation), Then a person reviews and sends it; the 180-day window (US, configurable) runs as a timer | Agent drafts; Person sends |
| RC-10 | P1 | Given a warranty repair of a supplier's component, When the supplier terms cover it, Then a recovery claim is drafted with part mapping and evidence and the failed part is held for return | Agent drafts; Person submits |
| RC-11 | P1 | Given a chargeable repair, misuse or missing tool, When approved, Then an AR billing request goes to the ERP with the evidence | Person |
| RC-12 | P1 | Given delivered loads or closed work orders without an invoice at period end, When close starts, Then accruals are proposed per line and reversed when the invoice reconciles | Agent proposes; Finance approves |
| RC-13 | P1 | Given any line outside tolerance, unmatched invoice or unreconciled outcome, When it arises, Then it is a variance-queue item in "My work" with owner, age and recommended action | Agent |
| RC-14 | P1 | Given a Recover route that ends the asset's book life, When the case closes, Then a retirement with proceeds and the read carrying amount is proposed to Finance | Agent proposes; Finance posts |
| RC-15 | P1 | Given a return, swap or contract-refresh credit, When the credit rules apply, Then the credit memo is proposed with the rule; credits above the threshold go to sales (01 §4.3) | Agent; Person |
| RC-16 | P1 | Given a new invoice, When scored, Then duplicates and anomalies (amount far from the lane's history, new payee, a payee bank-detail change reported by the ERP) hold the settlement | Agent; Person |
| RC-17 | P1 | Given one quarter of paid invoices with their shipments and work orders, When replayed as of each invoice date, Then the report shows overbilling found, by carrier, repairer and reason, with a band (P9-3 harness) | Agent; Person reviews |
| RC-18 | P2 | Given reconciled freight and repair history, When the valuer prices a route, Then the expected cost uses each carrier's and repairer's billing accuracy | Agent |
| RC-19 | P2 | Given dispute outcomes (won, lost, written off), When enough exist, Then rule suggestions ("stop disputing liftgate under $15") are proposed in the Modeler | Agent; Person applies |
| RC-20 | P2 | Given a PDF invoice from a repairer without EDI, When extracted (quarantined model, typed output), Then totals are validated before audit and the run's writes are held (taint) | Agent |
| RC-21 | P2 | Given a dispute or claim deadline (contract or statute), When it nears, Then the owner is reminded and the item escalates | Agent |
| RC-22 | P2 | Given Ask, When a person asks "why did we short-pay invoice X", Then the answer cites the lines, rules and evidence | Agent (read) |

Counts: **P0 8, P1 9, P2 5** (22).

**Notes for the other four segments** (same stories, other documents and evidence):

- **Device recommerce:** payout adjustments and clawbacks (RC-05/06 with grade and fraud evidence); marketplace fee
  and payout settlements (RC-02 on fee schedules); buyer returns and chargebacks (re-open a Recover case); wholesale
  lot settlements vs bids.
- **Used cars:** auction fee statements vs the schedule; arbitration adjustments with the auction's window as the
  RC-21 timer; recon invoices vs the estimate (RC-04 with labour-time guides).
- **Telecom network equipment:** broker settlements vs listing and bench test; recycler rebates per kg vs handover
  weights; a certificate of recycling as a payment gate; export-control holds block settlement release.
- **Medical rental:** hospital damage, loss and late-return charges (RC-11); OEM service-contract claims (RC-10);
  biomedical service invoices vs standard (RC-04); decontamination charges; extra care over charging regulated
  customers (Legal review).

## 7. Agents for Reconcile

By analogy with Recover's seven-agent chain (01 §3). Autonomy uses the Compose levels: *Recommend only / Act within
limits / Act alone*.

| # | Agent | Does | Autonomy |
|---|---|---|---|
| 1 | Intake | Reads charge documents (EDI, CSV, PDF via quarantined extraction, portals); opens one settlement case per document; dedupes | Act alone |
| 2 | Match | Links lines to shipments, work orders, POs, receipts, contracts and Recover cases; unmatched becomes an exception | Act alone |
| 3 | Evidence | Gathers events, gate times, teardown findings, telemetry, photos, certificates; requests missing evidence | Act alone (reads; requests held if external) |
| 4 | Attribution | Warranty vs chargeable vs supplier; carrier vs shipper responsibility | Act within limits (confidence threshold, default 75% as Compose) |
| 5 | Audit and valuation | Expected amount per line (rate terms, standards, catalogue); variance; prices each outcome (amount, success chance, cost to pursue, time) | Act alone (computes only) |
| 6 | Settlement | Proposes the outcome per line and document | Recommend only; Act within limits only under a standing policy |
| 7 | Follow-through | Instructions to AP, AR and supplier portals; dispute and claim timers; records results; feeds Recover's outcome and the learning | Act within limits; every external message is held for a person |

**Money rule (D4).** Every action that moves or commits money (approving a settlement, a payout, a short-pay, a
dispute, a customer charge, a supplier claim, an accrual, a retirement) is approved by a named person or by a standing
policy. The policy has an owner, went through maker-checker, is scoped to reason codes and amounts, and is journaled
with its version ("approved by policy P vN, owner X").

**Add to `FORBIDDEN_ACTIONS`** ([forbidden.py](../../../../backend/di/services/agents/forbidden.py)):
`settlement.approve`, `settlement.override`, `claim.submit` and `dispute.send` (a person sends, or a policy where the
customer opts in), `accrual.post`, `asset.retire`, `settlementPolicy.` (writing or publishing a standing policy). No
payee master-data or bank-detail action exists in Reconcile at all.

**Hold reasons** (extend P9-2.4's hold policy): a line outside tolerance; a document total over the value threshold;
any short-pay, dispute, charge or claim with no standing policy; attribution confidence below the threshold; a misuse
finding resting on a model score; a new payee, or a payee whose bank details changed recently (the business email
compromise pattern: we flag, never change); the run read an untrusted document (taint); conflicting sources (TMS vs
WMS times); a dispute deadline within N days; a closed period.

## 8. What the core provides vs what is new

| Capability | Core today | New for Reconcile | Size |
|---|---|---|---|
| Case, stages, dedupe | Cases, lifecycle, intake dedupe ([intake.py:54](../../../../backend/di/services/cases/intake.py#L54)) | Case kind `settlement` with its seven stages, linked to Recover cases | M |
| Expected cost per line | `ex_trace` methods and sources; lanes and rate card; prep parts and labour ([trace.py](../../../../backend/di/services/execution/trace.py), [lanes.py](../../../../backend/di/services/execution/lanes.py)) | Expose as a reusable "expected line" service by shipment or WO; detention and fuel terms | S–M |
| Connectors | OTM, Depot Repair, ServiceNow, S/4, EBS catalogue mock | OTM terms 4–7 and failed-delivery events; carrier invoice resource; S/4 supplier invoice and AP block; AR billing; fixed-asset retirement; warranty cover and supplier terms | L |
| Formats | X12 tokenizer and pydifact (planned, D3) | 210/214/810 loop maps; PDF via pdfplumber + quarantined extraction; factur-x | M |
| Canonical | 11 models with typed fields, held records, conflicts | 8 models (§5) | M |
| Rules | Modeler gates and rules, guardrails, simulation, shadow; ZEN table node (P9-5.7) | Audit-rule and tolerance tables, reason codes, cover tables as pack data | M (after P9-5.7) |
| Approvals | Pipeline, proposals, maker-checker; standing policy (D4, P9-2.4) | `settlement.approve`, money thresholds per pack, forbidden additions | S |
| Execution | Idempotent writers ([writers.py](../../../../backend/di/services/instructions/writers.py)); S/4 journal post | Writers: AP release / block / short-pay, debit memo, AR billing, supplier claim, accrual, retirement (+ mocks) | L |
| Outcomes and learning | `outcome.confirm` ([execution.py:53](../../../../backend/di/services/actions/execution.py#L53)), outcome rows ([outcomes.py](../../../../backend/di/repositories/outcomes.py)), calibration ([calibration.py:34](../../../../backend/di/services/engine/calibration.py#L34)) | Real actuals from settlements; carrier and repairer accuracy into the valuer | S–M |
| Agents | Runtime, playbooks, proposals, MCP; `reconcile_outcome` read tool ([mcp/tools.py:284](../../../../backend/di/mcp/tools.py#L284)) | Playbook `reconcile_autopilot` (seven agents as steps); generated MCP tools (P9-2.8) cover the new actions | M |
| Screens | Case stage 10 "Reconciler" fields ([case.py:545–563](../../../../backend/di/services/screens/case.py#L545)) | Settlement case screen (billed vs expected vs evidence per line); variance queue in "My work" | M |
| Back-test | P9-3 harness (planned) | Replay paid invoices: "overbilling found" report | S (after P9-3) |

**Overall (first pass):** Reconcile v1 (tool-fleet freight and repair audit, settlement, AP handoff, real actuals)
**L, about 6–8 engineer-weeks**; warranty attribution and supplier recovery **M–L**; finance close (accruals,
retirement, credit settlement, variance queue) **M**.

**Proposed phases for plan 9:**

- **Phase 3, P9-3.5 (pilot-critical):** RC-08 joins TF-07: read real actuals where invoices exist, keep the hashed actuals for
  the demo cases (decision-log entry); the OTM adapter maps rate terms 4–7.
- **Phase 4:** RC-17 reuses the back-test harness as Reconcile's sales motion ("upload a quarter of paid freight and
  repair invoices").
- **Phase 7, replacing revision 1's P9-5.2:** **P9-7.1** Reconcile v1, RC-01–07 and RC-13 (**L**); **P9-7.2** warranty
  attribution and supplier recovery, RC-05 in full and RC-10/11 (**M–L**); **P9-7.3** finance close, RC-12/14/15
  (**M**); **P9-7.3** device payouts and marketplace settlements with the device pack (**M**). Used-car, telecom and
  medical settlements come later with their packs.

**Parity guard.** The 128 demo cases and RT-1048 keep their numbers. Reconcile changes a case's actuals only where real
settlements exist, and RT-1048's detention line must come out the same from the rule (a test).

## 9. Open questions

1. **Scope for the pilots.** Does the tool-fleet pilot include freight and repair invoices (P0 here), or only the
   outcome link (RC-08)? This is README open question 2.
2. **Who pays.** Does the customer use an FAP provider today? If so, Reconcile reads the FAP's audit results and
   adds the asset link and the evidence, rather than re-auditing. This needs a decision.
3. **Standing policies for money.** Are they acceptable to the pilot customers' auditors and Finance (D4)? Which
   reason codes may a policy short-pay?
4. **Writing to AP.** Release, block and short-pay need write access to ERP AP. Is read-plus-propose (a person posts
   in the ERP) enough for the pilot?
5. **Standard repair hours.** Do the customer's repairers or OEM publish labour-time standards, or do we learn bands
   from history only?
6. **Warranty data.** Is there a warranty registry with cover terms and supplier terms, or only an expiry date as
   today?
7. **Accounting.** Retirement and credit settlement entries depend on the customer's policies (IFRS or US GAAP) and
   chart of accounts. These need Finance and Legal sign-off.
8. **Jurisdictions.** Dispute windows and the rules on charging customers differ by country. Which markets come
   first? (01 §4.2: DE, UK, US, AU, FR pilot.)
9. **Payment fraud.** Bank-detail changes stay out of scope; confirm that the ERP's vendor master controls are the
   customer's.

## Unconfirmed

- GA status of Shipium Always-On Audit [R1], Tungsten InvoiceAgility+ [R7], Basware's Supplier and AP Pro agents
  ("planned" for 2026) [R6], Trax's agents (roadmap, undated) [R2] and Tavant's agents (no dates) [R10][R11].
- Loop's agent list and dates: the vendor's release and secondary coverage [R3]; the analyst recognition is the
  vendor's own claim.
- No freight-audit agent found at Cass [R4]; no warranty-claims agent found at PTC.
- The 3–7% of freight spend recoverable by audit: vendor benchmarks only [R27].
- docling model weights: which of the two licence tags applies [R26]. ZEN money precision in the Python wheel (E §3.1).
- ASC 360 retirement guidance: not read. IAS 16 para 68 numbering varies between sources [R19].
- Whether the 180-day rule [R14] applies to a given customer's freight (exemptions, contract carriage, non-US lanes):
  Legal.

## Sources

Code (read 24 Nov 2026, commit `5b1fcfd`): `backend/di/services/execution/{trace,lanes}.py`,
`backend/di/services/instructions/writers.py`, `backend/di/services/actions/execution.py`,
`backend/di/repositories/outcomes.py`, `backend/di/services/engine/calibration.py`,
`backend/di/connectors/adapters/{otm,depot_repair,s4,servicenow,ariba,oracle_lease}.py`,
`backend/di/connectors/catalog.py`, `backend/di/services/canonical/fields.py`,
`backend/di/services/agents/{forbidden,proposals}.py`, `backend/di/services/screens/case.py`, `backend/di/mcp/tools.py`,
`source-sim/sim/vendors/otm/{__init__,seed}.py`, `source-sim/sim/generic/specs/catalog_ebs.py`, `backend/requirements.in`.

Research in this folder: 00-brief.md, 01-recover-segments.md, README.md (D1–D4); C §2.5, D §2.1, E §3, F §6, G §2.12
and §4; plan 9 (`../../plans/09-agentic-platform.md`).

Web (read 24 Nov 2026):

- R1 Shipium, "Shipium launches Always-On Audit", press release dated 25 Aug 2026 (dateline 26 Aug):
  https://www.shipium.com/pr/shipium-launches-always-on-audit
- R2 Trax Technologies, "AI vision and roadmap" (undated): https://www.traxtech.com/products/ai-vision-and-roadmap
  ; Prizma.AI launch blog (Aug 2025): https://www.traxtech.com/blog/trax-technologies-unveils-prizma.ai-the-future-of-supply-chain-intelligence
- R3 Loop, "Loop Launches the Logistics Data Platform Powered by New AI Capabilities", Business Wire, 4 May 2026:
  https://www.businesswire.com/news/home/20260504771246/en/ ; "Introducing Loop Intelligence" (13 Jul 2026, per
  coverage): https://www.loop.com/article/introducing-loop-intelligence-instant-answers-and-insights-to-top-logistics-questions
- R4 Cass Information Systems, "Cass and Caspian Partner to Deliver Tariff Cost Management Solution", 26 Feb 2026:
  https://www.cassinfo.com/news/cass-and-caspian-partner-to-deliver-tariff-cost-management-solution
- R5 Transflo, "Transflo unveils Workflow AI for LTL", 22 Jan 2026: https://www.transflo.com/news/transflo-unveils-workflow-ai-for-ltl/
- R6 Basware, agentic AI press release, 24 Feb 2026:
  https://www.cfodive.com/press-release/20260224-basware-launches-new-agentic-ai-capabilities-to-transform-intelligent-finan-1/
- R7 PYMNTS, "Tungsten Debuts Tool to Streamline Invoice-to-Pay Automation" (InvoiceAgility+), 30 Sep 2026:
  https://www.pymnts.com/?p=4255560
- R8 Microsoft Learn, Business Central "Match purchase invoices to orders with the Payables Agent", 2025 release
  wave 2: https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/match-purchase-invoices-orders-payables-agent
- R9 CPA Practice Advisor, "AvidXchange Unveils New AI Agents…", 23 Jul 2025:
  https://www.cpapracticeadvisor.com/2025/07/23/avidxchange-unveils-new-ai-agents-to-elevate-accounts-payable-processes/158299/
- R10 Tavant, Warranty AI product page (© 2026, capabilities undated): https://tavant.com/products/warranty-ai/
- R11 Tavant, Supplier Recovery product page (© 2026): https://tavant.com/products/supplier-recovery/
- R12 Syncron press releases, 29 May 2026 and 7 Oct 2026:
  https://www.syncron.com/press-releases/syncron-and-truecontext-help-manufacturers-turn-field-execution-into-better-warranty-decisions ;
  https://www.financialcontent.com/article/gnwcq-2026-10-7-syncron-launches-service-contract-performance-to-help-oems-grow-profitable-service-revenue
- R13 HighRadius, deductions management pages (undated): https://www.highradius.com/solutions/deductions-management/
- R14 49 U.S.C. § 13710 (added 29 Dec 1995, in force 1 Jan 1996), LII: https://www.law.cornell.edu/uscode/text/49/13710
- R15 49 U.S.C. § 14705, LII: https://www.law.cornell.edu/uscode/text/49/14705
- R16 Stedi, X12 004010 210 "Motor Carrier Freight Details and Invoice": https://www.stedi.com/edi/x12-004010/210
- R17 U.S. EIA, "Gasoline and Diesel Fuel Update" (weekly; release of 24 Nov 2026): https://www.eia.gov/petroleum/gasdiesel/
- R18 Microsoft Learn, Dynamics 365 Finance "Accounts payable invoice matching":
  https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching ;
  Oracle Payables "Two-, Three-, and Four-way Matching": https://docs.oracle.com/cd/A60725_05/html/comnls/us/ap/point04.htm
- R19 IAS 16 Property, Plant and Equipment, paras 67–72 (IFRS Foundation HTML; AASB equivalent):
  https://ifrs.org/content/dam/ifrs/publications/html-standards/english/2022/issued/ias16.html ; https://standards.aasb.gov.au/node/474
- R20 IFRS 15, Appendix B (B20–B33), 2026 issued HTML:
  https://www.ifrs.org/content/dam/ifrs/publications/html-standards/english/2026/issued/ifrs15.html ; Deloitte DART,
  ASC 606 roadmap §5.5 Warranties: https://dart.deloitte.com/USDART/home/codification/revenue/asc606-10/roadmap-revenue-recognition/chapter-5-step-2-identify-performance/5-5-warranties
- R21 NAAA Arbitration Guidelines 2026 (effective 1 Jun 2026): https://naaa.com/wp-content/uploads/2026/06/NAAA-Arb-Guidelines-2026.pdf
- R22 NSF, "R2v3 certification transition" (downstream vendor requirements): https://www.nsf.org/knowledge-library/r2v3-certification-transition
- R23 PyPI JSON API for each package in §4 (pydifact, pyx12, pdfplumber, pypdf, camelot-py, invoice2data, factur-x,
  docling, unstructured, marker-pdf, pymupdf, rapidfuzz, jellyfish, splink, dedupe, recordlinkage, zen-engine,
  scikit-learn, pyod, pandera, py-moneyed): https://pypi.org/pypi/<name>/json ; Bots status from D §2.1
- R24 marker README, licence section: https://github.com/datalab-to/marker
- R25 Splink, "Backends" topic guide: https://moj-analytical-services.github.io/splink/topic_guides/splink_fundamentals/backends/backends.html
- R26 Hugging Face, `ds4sd/docling-models` model card: https://huggingface.co/ds4sd/docling-models
- R27 Freight invoice error guides (vendor content): Intelligent Audit, "The top billing discrepancies in freight
  billing": https://intelligentaudit.com/blog/the-top-billing-discrepancies-in-freight-billing-and-what-to-do-about-them
  ; nShift, "Freight invoice audit guide": https://nshift.com/content-library/freight-invoice-audit-guide
- R28 UN Digital Library, "UN/EDIFACT draft Directory D.96A" (Jan 1996): https://digitallibrary.un.org/record/227731
