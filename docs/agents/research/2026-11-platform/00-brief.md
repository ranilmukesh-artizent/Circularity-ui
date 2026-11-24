# Research brief: platform direction (24 Nov 2026)

Shared context for the research reports in this folder. Each report (`A-…` to `G-…`) answers one part; `README.md`
is the synthesis with the decisions.

What changed in this revision and why:
- Resolve and Reconcile removed (parked as out of scope, user decision 25 Nov 2026).

## The target: Recover and its five industry segments (added 24 Nov 2026)

The team's Recover prototype ("5 Industry Segments", pre-final) is the target the research builds towards. It is
summarised in [01-recover-segments.md](01-recover-segments.md). The product owner shared it **for the concept, not
the UI design**. Use it for capabilities, rules, data and flows. Never treat its screens or layout as requirements.

- **The Decision Intelligence core behind Recover** (circularity: where is this returned item worth most?).
- **Compose** is the authoring experience: describe a business → adapter mapping → agent mapping → approve or
  modify → publish. Publishing generates the run-time screens: **Decide** (Pulse, Cases, Exceptions) and
  **Understand** (Analytics, Agents).
- **Five industry segments:**
  - tool fleet AMS (returns, service desk, contract refresh);
  - device recommerce;
  - used cars (lease and trade-in returns);
  - telecom network equipment;
  - medical rental equipment.

**The user's answers on 24 Nov 2026 (second round):**
1. **The five segments.** Build towards them first, with user stories for each. Then complete the stories of the
   other industries researched earlier in the same plan. They stay, as later segments.
2. Resolve and Reconcile were researched, then parked as out of scope on 25 Nov 2026 (not reverse logistics); see
   parked/.
3. **Tool fleet AMS:** returns, service desk and contract refresh are all P0.
4. **Naming:** the docs use Recover, Compose, Decide and Understand. The code and repo names stay as they are.

Where this brief says "Connection Studio" or "Business Studio" below, read them as Compose's adapter step and its
flow and guardrail steps.

## The product today

A decision intelligence platform for reverse logistics and circularity. When an asset comes back (RMA, lease end,
trade-in, contract end, field-service return, IoT alarm, manual entry), the platform opens a **case**, gathers data
about the asset from many enterprise systems, decides what to do with it (redeploy, refurbish, resell, re-lease,
harvest parts, recycle, exit), explains why (value, risk, carbon, rules applied), gets a person to approve anything
consequential, then hands the decision to the enterprise systems as instructions (sales order, transfer, work order,
credit memo) and tracks their confirmations.

Status: a full-stack POC on synthetic data (128 demo cases, 11 roles, org units/tenants, pilot mode). Every
enterprise system is a mock. About 4,500 api tests. Next: production hardening and a customer pilot.

### Stack (self-hosted, Docker Compose; a trial package is shipped to customers)

- Backend: Python, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (psycopg 3); an api service and a worker.
- Frontend: React 18 + TypeScript + Vite; canvas UIs for the visual builders (hand-built today).
- Queue: own Postgres job queue (priorities, dedupe, retries, dead letters, reaper, LISTEN/NOTIFY).
- LLM: provider-neutral port; today an open-weight model on a hosted inference API with per-model rate limits;
  rule-based fallback when there is no key.
- Postgres is the only datastore. No Kafka, Redis, JVM or Elasticsearch.

### Tier 1 + 2: Connection Studio

- Connection Fabric: adapters for ~21 system types (ERP, procurement, OMS, WMS, TMS, EAM, field service/ITSM, CRM,
  PLM read-only, QMS, inspection apps, IoT telemetry, leasing, carbon accounting, remarketing/auction, depot repair),
  plus generic spec-built mocks and MCP-client sources. Encrypted credentials, discovery/probe, delta reads,
  webhooks, SFTP/CSV file drops, manual CSV import, health states.
- Mappings into a canonical model (Asset & component, Condition & eligibility, Demand opportunity, Outcome) with
  unit/currency/time-zone/code normalisation; canonical checks; failing records are held; conflicts between sources
  go to a conflict queue for a person.
- Workflow Studio: visual canvas (trigger → read → map → transform → quality → branch → write/emit), block settings,
  validation, test run, versions, draft → publish; a source's sync is its ingest workflow; workflows export as JSON.
  "Build with AI" drafts a workflow from a sentence (today it maps the prompt onto the nearest known topology).

### Tier 3a: Business Studio ("the Modeler")

- Decision flows per case template: gate rules (hard eligibility) first, then business rules
  (prefer/exclude/waive/require approval) scoped by class, grade, site, owner. Guardrails with named owners.
- Template packs: industrial returns, tool fleet, device recommerce, each with its own valuer.
- Simulation of a draft over historical cases; maker-checker lifecycle (draft → submit → approve → publish), shadow
  mode, rollback, history. Plain-language assistant turns a sentence into a proposed rule.
- Learning: calibration, model candidates (a person proposes, another promotes), rule suggestions from outcomes.

### Tier 3b: Orchestration

- One write path: every write (person or agent) goes through one action pipeline (~125 actions, 12 steps:
  validation, permission, tenant, agent gate, agent limits, idempotency, hold for a person, journal).
- Forbidden list: agents never approve, publish, override, decline or change access.
- Agent registry with autonomy (act/propose), per-agent tool allow-lists, run limits; proposals held until a person
  accepts. Runtime runs a deterministic playbook ("case autopilot"); **no LLM reasoning loop yet**.
- Tool catalogue (every action as JSON Schema), MCP server (Streamable HTTP) and MCP client; Ask panel (chat over
  read actions); execution step templates per route; live event stream; journal with provenance.

### Already decided (research note `../2026-11-agent-foundation.md`)

- Keep the control plane in-house (pipeline, proposals, journal, queue, approvals). Embed libraries only where they
  don't bring a second state store, approval store, workflow engine or API server.
- Agent loop: Pydantic AI behind our own port (its deferred tools map onto proposals); LangGraph as fallback.
  Rejected as the platform: Orkes Conductor, Agno AgentOS.
- Exposure order: MCP generated from the action catalogue with OAuth → OpenAPI + CLI → A2A agent card → AG-UI.

## What the team wants next (from the 24 Nov reviews; names left out)

1. **Pitch flow, Studio first.** A business user types "create a template for my AMS process". The AI drafts the
   end-to-end business flow, says which adapters to connect and maps the fields; the user confirms. Then the agent
   picks up returned assets, IoT telemetry (operating hours), PLM remaining useful life, repair-centre grading,
   evaluates every route and proposes the highest-recovery one.
2. **Humans approve, agents plan.** No manual planning or data entry. People step in only on high-value thresholds,
   low model confidence, exceptions and conflicts.
3. **Guardrails per asset type.** Data-erasure certificate only for IT/compute assets (re-deploy to another customer
   or scrap). For tools/motors/hardware: RUL and grade certification before refurbish/redeploy.
4. **Back-testing as the sales motion.** The customer hands over one month or one quarter of historical returns and
   dispositions; we replay them and show the net uplift against what they actually achieved.
5. **Two pilot templates.** (a) Tool-fleet AMS: a manufacturer's fleet-management / aftermarket service; a tool
   comes back; we *read* its grading (not compute it), check the contract terms (may we refurbish and resell?),
   check market value, pick the best path; wear-and-tear index and RUL from IoT + PLM readings must be explainable.
   (b) Device trade-in / protection: consumer devices, ML price prediction, dynamic channel routing.
   Then more industries and processes.
6. **Carbon on every disposition card**: deterministic CO2e avoided per route.
7. **Agentic CRUD across the platform** (create/read/update/delete workflows, rules, sources by natural language)
   within about a week; the whole platform as an MCP server.
8. **Adapter generation in hours, not weeks**, by agents, for systems we don't have.
9. **LLM resilience**: rate limits are per model, so fall back across models/providers automatically.
10. **Declarative workflow JSON** as the contract: an agent generates JSON, the canvas renders it.
11. One role-based home (no duplicate Home vs Command Center); exceptions and alerts inside "My work".
12. Keep **connection workflows** (ETL, adapters) separate from **decision rules** (business policy).
13. Positioning: vendor-neutral fabric versus vendor-locked suites; deploy in under a week; a 6–8 month window
    before large suite vendors ship comparable circularity features. The ambition is "an agentic orchestration
    platform like the leading BPMN + agents vendors, but domain-agnostic for any returns and industry domain".

Answers given to an outside assistant: build = **mix of custom and OSS**; studio users = **all three** (internal
forward-deployed engineers, customer IT, non-technical operations managers); reverse-logistics stages = **all four**
(RMA intake and fraud triage, warehouse receiving and grading, smart disposition and recommerce, ERP/WMS financial
reconciliation).

## Rules for every report

- English, plain words. Cite primary sources (repo, docs, release notes, licence file) with dates. Mark anything you
  could not confirm as **unconfirmed**.
- Licences: flag source-available, BSL, ELv2, SSPL, Sustainable Use, AGPL, and recent licence changes. We ship a
  trial package to customers, so redistribution matters. Licence findings need review by Kinective's Legal team
  before anyone relies on them.
- No customer or prospect company names in the reports: say "tool-fleet AMS template" and "device trade-in
  template". Competitors and OSS projects may be named.
- Don't put our company, product or people names in web searches or fetches.
