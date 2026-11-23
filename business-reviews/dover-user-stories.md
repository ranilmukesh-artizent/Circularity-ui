# Dover-scale customer: user stories, journey, edge cases, gaps

Status: draft for internal discussion, 23 Nov 2026. Functional level only. **Security, compliance, privacy and
regulatory requirements are out of scope here** and need their own pass. Anything below that touches a regulation
(e.g. ESRS E5 reporting) is mentioned only as a data need and must be reviewed by Kinective's Legal team before it is
relied on.

How to read it: **Fact** = said in the meeting or found in a public source (linked). **Proposal** = our suggestion.
**Have** = verified in the code on `feature/fullstack-poc` (file:line). Nothing in the "Have" column is assumed.

---

## 1. What we know, and an honest read of the fit

**Facts from the meeting (Dover's head of CAD/PDM/PLM):**
- Dover is 50+ companies: 16 operating companies (opcos) plus sub-opcos, 4 more recently added; one $1B opco added
  9+ sub-opcos in two years. Even an opco director "cannot figure out who is doing what".
- His team consolidates CAD/PDM/PLM across all opcos: 25+ vendor systems. PLMs in use: ENOVIA / 3DEXPERIENCE,
  Teamcenter, Windchill (heavily), SolidWorks CAD / PDM / Manage. PLM must align with ERP (sales order ↔ design).
- Operating style: value for every dollar (e.g. floating licences across shifts), policy over ad-hoc yes, **testbeds
  and pilots before any recommendation**, "middle path" instead of a flat no. He verifies work himself on the server.
- His three asks: PLM projects, IoT / product IoT connectors, CAD/PDM/PLM resourcing.
- Next steps: we send case studies; he sends bullet points for pilots. We asked for a later session on asset
  lifecycle / "next best life for an asset".

**Facts from public sources:**
- Five segments: Engineered Products, Clean Energy & Fueling, Imaging & Identification, Pumps & Process Solutions,
  Climate & Sustainability Technologies; 2025 revenue $8.1B, four acquisitions in 2025
  ([Dover FY2025 results](https://investors.dovercorporation.com/node/28796),
  [segments overview](https://www.dovercorporation.com/docs/libraries/corporate/Dover-Segments-Overview-Jan-26.pdf)).
- Most opcos sell spare parts; several run repair and refurbishment programmes; one business runs an exchange
  programme (failed module swapped for a refurbished one); "Circularity & Waste" is a material topic mapped to ESRS E5;
  sustainability scorecards sit in the stage-gate design process
  ([Dover: Circularity and Waste](https://www.dovercorporation.com/sustainability/environmental/waste)).
- Remanufacturing research: the tools exist but ERP/PLM integration is the usual missing piece; the data structures
  that matter are the engineering BOM, the remanufacturing BOM and the remanufacturing bill of process
  ([Oxford white paper, 2026](https://eng.ox.ac.uk/about/circular-economy-and-sustainability-lab/white-paper-digital-enablers-for-remanufacturing-2026),
  [Birmingham review](https://research.birmingham.ac.uk/files/169658847/kerinm2022generic.pdf)).
- Federated PLM landscapes (no central database, changing membership) are best integrated through a two-tier design
  that cuts integration points ([Cambridge, federated PLM](https://cambridge.org/core/services/aop-cambridge-core/content/view/AD63EEEFFE01D5E39068CA117DFAAD0B/S2732527X24000622a.pdf/from-tears-to-tiers-architectural-principles-for-federated-plm-landscapes.pdf)).
- PLM vendors and MCP: PTC ships an MCP server for Onshape and positions MCP as the way agents consume its products;
  Windchill users build their own MCP servers; Dassault runs its own agents on 3DEXPERIENCE; nothing found for
  Teamcenter ([PTC: where MCP creates value](https://www.ptc.com/en/blogs/plm/where-mcp-creates-value),
  [PTC community thread](https://community.ptc.com/windchill-10/windchillpdmlink-and-mcp-172038)). Treat as unverified
  against vendor docs.
- Buyers trust agents with full autonomy only in low-risk work; manufacturing is the most cautious sector
  ([G2 AI agents report](https://learn.g2.com/enterprise-ai-agents-report),
  [Snowflake](https://www.snowflake.com/en/blog/agentic-ai-operational-roi-manufacturing/)).

**Honest read (no bias):**
- He did **not** ask for a circularity product. His world is CAD/PDM/PLM consolidation, licences, IoT connectors and
  people. Circularity was our ask.
- Where we touch his world: our decisions need his data (part master, BOM, revisions, where-used), and some
  decisions should end in his systems (a reman part number, a harvested part back into stock). So for us **he is the
  data owner and gatekeeper**, not the buyer. The likely buyers of a circularity decision platform are opco
  aftermarket / service leaders and the sustainability function.
- What would earn his trust: a **read-only testbed on one opco**, measurable value per dollar, no change to any PLM,
  and something he can check himself.
- Our product today is a single-company POC with fixed tenants and synthetic systems. The gaps in section 5 are real.

---

## 2. Personas

| # | Persona | Owns | Wants from us |
|---|---|---|---|
| P1 | Group head of CAD/PDM/PLM (gatekeeper) | PLM/CAD estate, licences, integration standards | Read-only, low-touch connectors; proof in a testbed; no new silo |
| P2 | Opco aftermarket / service manager | Returns, exchanges, spare parts, refurb | Faster, better next-life decisions; more parts recovered |
| P3 | Repair / refurb centre lead | Teardown, test, rework | Clear work orders with the right BOM revision and parts to harvest |
| P4 | Opco design / product engineer | Designs, ECOs, stage-gate scorecard | Failure and reuse data per part to design for reman |
| P5 | Integration / data engineer (Dover or us) | Connectors, mappings | Add an opco's systems in days, not months |
| P6 | Opco controller | Recovery value, write-offs | Predicted vs actual, per decision and per opco |
| P7 | Group sustainability lead | Circularity data | Materials diverted, parts reused, per opco (data only; reporting rules are Legal's) |
| P8 | Enterprise AI / agent owner | Copilot / Claude / vendor agents | Their agents can read and propose through MCP, under their rules |
| P9 | Group / segment executive | Portfolio | One view across opcos; which opco recovers the most value |

---

## 3. The end-to-end journey (A → Z), as user stories

Each stage: the story, acceptance criteria (AC), and what exists today.

### A. Testbed pilot on one opco
- **Story (P1):** As the PLM head, I want a sandbox on one opco and one product line, reading copies of PLM/ERP data,
  so that I can prove value before I recommend it to anyone.
- **AC:** separate environment; read-only credentials; no writes to any opco system until switched on per target;
  a value report at the end (decisions made, value recovered vs today).
- **Today:** the stack runs on Docker Compose with one database; `scripts/dev/fresh-clone.sh` builds an isolated copy
  for testing. Outbound writes can be held per run (the api suite forces no outbound instructions,
  `backend/tests/conftest.py`). No "read-only pilot mode" switch per target and no pilot value report.

### B. Model the organisation
- **Story (P1, P9):** As the group, I want group → segment → opco → sub-opco → site, so that data, rules and people
  sit where they belong and roll up.
- **AC:** create an opco at runtime; move a sub-opco after an acquisition; users scoped to one or more opcos; group
  roll-ups.
- **Today:** three fixed tenants read from the golden `world.json` (`backend/di/core/policy.py:72-73`); cases carry an
  `owner` tenant; only Planner is tenant-scoped (`policy.py:160-168`); extra access via `tenant_grant`. 8 sites and
  3 facilities, fixed. **No hierarchy, no runtime tenant creation.**

### C. Connect each opco's systems
- **Story (P5):** As the integration engineer, I want to connect opco X's Windchill and SAP and opco Y's Teamcenter
  and Oracle, each tagged to its opco, so that one platform serves both.
- **AC:** several instances of the same system type; each bound to an opco; credentials per instance; health per
  instance.
- **Today:** 21 mocked sources incl. Teamcenter (plm) and Aras (bom) (`source-sim/sim/core/registry.py:23-48`);
  15 more connectable from a catalogue; a new source can be created at runtime against any spec-shaped API
  (`services/actions/fabric_sources.py:399-432`, `connectors/registry.py:37-48`); a second of a type gets `erp_2`
  (`fabric_sources.py:376-382`). **No Windchill, ENOVIA/3DEXPERIENCE or SolidWorks mock or adapter; `source_system`
  has no tenant/opco column** (`backend/di/models/connectors.py:24-43`); a catalogue system connects only once.

### D. Map to one canonical model
- **Story (P5):** As the engineer, I want each PLM's part, BOM and revision mapped to one model, so that decisions do
  not care which PLM an opco uses.
- **AC:** part master, EBOM/MBOM, revision and release state, where-used, alternates/supersessions, serialised
  as-built / as-maintained; mapping versioned; source value kept.
- **Today:** canonical namespaces asset, condition, demand, intervention, market, route, sustainability, vendor,
  outcome (`services/canonical/schema.py:34`). Teamcenter facts: item/revision, release status, `bom_ref`,
  compatible items, alternates; Aras: components with harvestable flag, BOM revision/state. **No where-used, no ECO,
  no CAD files, no MBOM/reman BOM** (grep for where-used/ECO in `backend/di`: no hits).

### E. Resolve identity across systems
- **Story (P5, P2):** As the engineer, I want serial → part → BOM revision resolved across ERP, PLM and service, and
  the same part number in two PLMs kept apart, so that we never harvest the wrong part.
- **Today:** an "identity resolution" workflow step exists in the palette (`workflow_builder.py` STEP_KW `x_ident`);
  facts carry a source. Cross-PLM part-number collisions per opco: **not handled** (sources have no opco).

### F. A return or end-of-life signal opens a case
- **Story (P2):** As the aftermarket manager, I want a case opened automatically from an RMA, an exchange request,
  a lease end or an IoT end-of-life signal, so that nothing waits for a spreadsheet.
- **Today:** **cases are opened only from the engine's book, once, when the table is empty**
  (`backend/di/services/cases/store.py:6-9`). Synced or imported assets do not create cases. IoT is off by default.

### G. Assess condition
- **Story (P3):** As the refurb lead, I want inspection results, telemetry and service history per component, so that
  the decision uses real condition.
- **Today:** inspection, repair and service facts are ingested (mocks). IoT facts (run hours, vibration, bearing temp)
  ingest once IoT is connected, but **the engine reads none of them** (no telemetry hits in `services/engine`).
  Components assessed come from a fixed list per asset class (`services/execution/prep.py:110-117`).

### H. Decide the next best life
- **Story (P2):** As the aftermarket manager, I want routes ranked by value — redeploy, exchange pool, reman, harvest
  parts for open demand, resell, recycle — with the reasons, so that I pick the best one.
- **AC:** parts value from the BOM and real demand (open service orders, where-used in active products, stock);
  reman as a route; per-opco economics.
- **Today:** seven routes (redeploy, resale, internal parts, re-lease, material, external parts, exit); six fixed
  gates (`services/engine/gates.py:29-79`); **parts value is a formula on new price × grade with random noise, not the
  BOM** (`services/engine/predictor.py:111-113`). **No reman route, no exchange-pool route.** Demand finding exists
  (`demand.find`, MCP `find_demand`) on mocked market/dealer data.

### I. Business owners edit the rules (the PO's Modeler)
- **Story (P2):** As the opco owner, I want to add "never recycle units under 40% life from repair centre R" and see
  which open decisions flip and the dollar effect before it goes live, so that I change policy safely.
- **AC:** rules per opco; guardrails nobody can break; simulate on the open queue; maker-checker; draft → review →
  shadow → publish; versions and audit.
- **Today:** gates are hard-coded; Admin can change approval limits, self-approval, agent autonomy and run limits only.
  **No editable decision rules, no per-opco policy, no simulation, no shadow.**

### J. Approve
- **Story (P2, P6):** As an approver, I want limits per role and per opco, escalation above my limit, and no
  self-approval.
- **Today:** approval limits per role, no self-approval unless Admin allows, escalation to Admin, override needs a
  15+ character reason (`services/actions/decisions.py:214-229`). **Not per opco.**

### K. Execute in the owning systems
- **Story (P3, P1):** As the refurb lead, I want the approved decision to become a teardown order with the right BOM
  revision, a stock move, a transport order and a finance entry; and, where a reman part number is needed, a change
  **request** to the opco's PLM (engineering owns the change), so that nobody re-keys anything.
- **Today:** writers for order allocation/delivery, repair/teardown order, transport, warehouse move, journal entry
  (`services/instructions/writers.py:385-392`); sale, lease and certificate are acknowledged by a simulated adapter.
  **No PLM write (no change request), no exchange-programme order.**

### L. Confirm and close
- **Story (P6):** As the controller, I want each step confirmed by the target's own reference, and actual vs
  predicted value recorded, so that the case closes with real numbers.
- **Today:** webhook confirmations matched to steps; `outcome.confirm` stores actual vs predicted per cost line
  (`services/actions/execution.py:53-66`). Retries with backoff then `failed` (`core/jobs.py:54-57`). **No dead-letter
  queue** (listed gap, `docs/backend-steps.md`).

### M. Learn
- **Story (P2, P4):** As the owner, I want the predictions to improve from actuals, and design engineers to get
  failure and reuse rates per part, so that the next product is easier to remanufacture.
- **Today:** actuals are stored. "Learning records … queued for the next retraining" is display text only
  (`services/screens/orchestration.py:599-605`); the predictor is `FormulaPredictor` with fixed model versions.
  **No retraining, no feedback to rules, no design feedback report.**

### N. Report
- **Story (P9, P7, P6):** As the group, I want value recovered, parts reused and materials diverted per opco and per
  segment, exportable.
- **Today:** analytics (waterfall, route mix, predicted vs actual, overrides, sustainability, pool), Command Center
  KPIs, CSV export. **No opco/segment roll-up** (no hierarchy).

### O. Agents: theirs and ours (MCP)
- **Story (P8):** As the enterprise AI owner, I want our Copilot/Claude agents to read cases and propose actions
  through MCP, limited to the opcos and tools I allow, held for a person, with a log, so that agents help without
  acting alone.
- **Story (P1):** As the PLM head, I want the platform to read the PLM through the vendor's or our own MCP server
  where one exists, so that we do not build a new point-to-point integration per PLM.
- **AC:** per-agent tool allow-list and opco scope; propose → hold → person approves; kill switch; call log; platform
  as an MCP **client** to external MCP servers.
- **Today:** MCP server at `/mcp` with 10 tools (6 read; `request_missing_evidence`, `request_approval`,
  `send_instruction` which needs an approval reference, and `reconcile_outcome`) (`backend/di/mcp/tools.py:40-51`);
  `Authorization: Bearer` + `X-Agent` (9 fixed agents) + optional `X-Tenant`; kill switch per agent; call log.
  **No MCP client** (the "client servers" screen is display state; no MCP client library used outside tests). Agents
  are a fixed list of 9, not registered by the customer.

### P. Chat with and edit workflows and processes
- **Story (P5, P2):** As the engineer I want to describe a new opco's ingest in words and get a working draft; as the
  owner I want to ask "why did case X go to recycle" and "what if we raise the life threshold".
- **Today:** Workflow Studio's Build with AI (`workflow.plan`, keyword slots + optional Groq) proposes ingest /
  outbound / decision graphs; nothing saved until a person clicks. Ask (Groq, 12 read tools incl. `what_if`) answers
  and suggests, never acts. **No chat that edits a business process / rule; no BPMN-style process map.**

### Q. Roll out to the next opco
- **Story (P1):** As the PLM head, I want opco #2 onboarded from opco #1's template (connectors, mappings, rules,
  workflows), with only the differences changed, so that 16 opcos is a repeatable job.
- **Today:** workflows are versioned and can be built from a template per source; **no opco template, no
  copy-an-opco, no per-opco configuration at all.**

### Z. Operate at scale
- **Story (P9):** As the group, I want thousands of returns a month across opcos, fleet-level bulk cases, and paging.
- **Today:** 128 cases, ~1,450 assets, ~55,000 facts after a full sync; `cases.list` pages with a limit; manual CSV
  import writes facts only. Code is almost entirely synchronous; job queue is a Postgres table without priorities or
  DLQ (plans 02 and 04 written, not run).

---

## 4. Edge cases (functional)

**Organisation and ownership**
1. A sub-opco is acquired mid-pilot and moves to another opco: its open cases, rules and users must move with it.
2. Asset returned to opco A, but the harvested part is needed by opco B: inter-company transfer, value split.
3. Customer-owned vs company-owned vs leased asset: different routes allowed.
4. Two opcos use the same part number for different parts.

**PLM / BOM data**
5. As-built revision ≠ current released revision; the part was superseded or is obsolete.
6. BOM missing for a recently acquired company (data still in spreadsheets or a legacy PDM).
7. The opco is mid-migration from one PLM to another: both systems live, which one wins per part.
8. Serial not found in ERP or PLM; asset known only from the service system.
9. ERP and PLM disagree (sales order configuration vs BOM).
10. A harvestable part has no demand today but will next quarter (hold vs sell).

**Condition and IoT**
11. No telemetry for older units; decision must still run on inspection only.
12. Telemetry flood or gaps from offline sites; late events arriving after the decision.
13. IoT alarm on an installed unit that is not returned (predictive, not a return).

**Decision and policy**
14. Regulated equipment (e.g. gas handling) needs a recertification before redeploy (functional gate; the rule itself
    is Legal/engineering's).
15. Recall or field action overrides any route.
16. Warranty claim vs commercial return: different owner, different money.
17. A rule changes while cases are in flight: which version applies (pin per case).
18. A draft rule breaks a guardrail; two rules conflict.
19. Price or demand moves after approval but before execution.

**Execution**
20. Target system rejects the instruction (closed period, unknown material, locked BOM).
21. Approver unavailable; escalation path per opco.
22. Duplicate RMA for the same serial.
23. Partial teardown: some parts harvested, rest scrapped.
24. Fleet end-of-lease: 500 units at once, one decision per unit or per lot.

**Agents**
25. An external agent asks for data across opcos it is not scoped to.
26. An agent proposes an action beyond its authority (must be held, not done).
27. The vendor's MCP server is down or changes its tools; fall back to the API connector.
28. The language model is unavailable or over quota: the deterministic path must still work (it does today for Ask and
    the workflow planner).

---

## 5. Gap table, one to one

Size: S ≈ ≤ 1 week, M ≈ 2–4 weeks, L ≈ > 4 weeks, one experienced engineer, rough.

| Need (stage) | Have today (verified) | Gap | Size |
|---|---|---|---|
| Org hierarchy, runtime opcos (B) | 3 fixed tenants from golden data (`core/policy.py:72-73`) | Tenant table + hierarchy, scoping on every query, roll-ups; breaks parity → decision-log entry | L |
| Sources per opco (C) | Runtime sources, `erp_2` style duplicates; no opco column (`models/connectors.py:24-43`) | Opco on source, mapping, credentials; catalogue multi-instance | M |
| Windchill / 3DEXPERIENCE / SolidWorks PDM-Manage (C) | Names only; Teamcenter + Aras mocks | Mocks + adapters (spec-built generic mocks can speed this) | M each |
| BOM depth: where-used, ECO, MBOM/reman BOM (D) | Item/revision/alternates/harvestable flag | Canonical BOM model and where-used query | M–L |
| Cross-PLM identity (E) | Identity step in palette | Per-opco keys, collision rules | M |
| Case intake from live events (F) | Cases only from the engine book (`services/cases/store.py:6-9`) | Open cases from RMA / lease end / IoT / import; the engine's random route values need real inputs | L |
| Telemetry in decisions (G) | IoT ingest when connected; engine reads none | Condition features from telemetry into the predictor/gates | M |
| BOM-based parts value, reman and exchange routes (H) | Formula with noise (`predictor.py:111-113`); 7 routes | BOM × demand parts value; new routes; parity decision | L |
| Editable rules, simulation, shadow, maker-checker (I) | Hard-coded gates; Admin limits only | The PO's Modeler on the backend (earlier estimate 3–5 weeks core) | L |
| Per-opco approval limits (J) | Per role | Scope limits by opco | S–M |
| PLM change request, exchange order (K) | Writers for order, repair, transport, warehouse, journal | New writers + mocks; PLM write as request only | M |
| DLQ and replay (L) | Retries then `failed` | Plan 02 (queue / DLQ) | M |
| Learning loop (M) | Actuals stored; "retraining" is text (`orchestration.py:599-605`) | Real model, retraining on actuals, design feedback report | L |
| Opco / segment reporting (N) | Analytics + CSV | Roll-ups once hierarchy exists | M |
| Customer agents via MCP (O) | Server, 10 tools, 9 fixed agents, X-Tenant, kill switch | Register agents at runtime, per-agent tool and opco allow-lists | M |
| Platform as MCP client (O) | None | MCP client connector type in the Fabric | M |
| Chat edits rules/process; process map (P) | Workflow builder (data plumbing), Ask read-only | Modeler assistant (LLM → structured rule → same validator) | M (on top of I) |
| Opco templates and copy (Q) | Workflow versions only | Export/import of an opco's configuration | M |
| Scale, async, queue priorities (Z) | Mostly sync; Postgres job table | Plans 02 and 04 | L |
| Email / Teams notifications | In-app only | Outbound notification channels | S–M |
| Licence / CAD seat analytics, resourcing | Not found | Not our product; a separate services offer if wanted | — |

---

## 6. What to do (proposal)

1. **Lead with what he asked for.** Case studies on PLM consolidation, multi-PLM integration and IoT connectors
   (his three asks). Circularity comes second, framed as "one use of the PLM and IoT data you already consolidate".
2. **Offer a read-only testbed,** shaped like his own method: one opco, one product line with a repair/exchange
   programme, one PLM (Windchill, since he says it is used heavily), its ERP, inspection data; decisions shown, nothing
   written back. End with a value report.
3. **Build only what that pilot needs first:** opco on sources (C), a Windchill mock + adapter (C), BOM where-used and
   BOM-based parts value (D, H), case intake from an RMA/exchange feed (F), telemetry features if the opco has IoT (G).
4. **Then the Modeler (I)** so the opco owner can own the rules, and **multi-opco (B, Q)** before a second opco.
5. **Agents:** keep "agents read and propose, people approve" (matches buyers' caution); add runtime agent
   registration with per-agent scope (O) and an MCP client connector so vendor MCP servers can replace custom adapters
   where they exist.
6. Ask his team for the pilot bullet points he promised, and check them against this list before we size anything.

Open questions for Dover (to replace assumptions): which opco and product line has the most returns or exchanges;
which PLM and ERP it runs; whether serialised as-built data exists; whether any opco already streams product IoT;
who owns aftermarket decisions today.
