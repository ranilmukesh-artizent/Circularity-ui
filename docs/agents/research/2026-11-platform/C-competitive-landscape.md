# C. Competitive landscape (24 Nov 2026)

Part C of the platform research (brief: [00-brief.md](00-brief.md)). Who else orchestrates agents, people and
deterministic process; who sells AI for returns and reverse logistics; where we stand; what to copy; and whether the
"6–8 month window" claim holds. Sources are listed at the end as [S#] with dates. Vendor claims are vendor claims:
nothing here was tested hands-on. Licence lines need review by Kinective's Legal team before anyone relies on them.

## Summary

1. Horizontal agent orchestrators (Camunda, UiPath Maestro, Pega, Appian, ServiceNow, Microsoft, Workato, n8n) all
   now mix a deterministic flow, an LLM agent with a governed tool set, and human tasks. None ships returns or
   circularity content: no asset valuers, no disposition routes, no canonical asset model. They are the "how", not
   the "what".
2. Camunda is the closest architectural peer and the best pattern source: agent loop runs inside the engine, each
   tool call is a BPMN activity, Operate 8.10 shows agent state, tokens, model and tool calls against limits [S1–S3].
3. Suite vendors (Manhattan, Blue Yonder, SAP, Oracle, IFS) ship agents on their own data layer. Blue Yonder is the
   only one with returns-specific agentic features (Aug 2026: test-and-grade, unit-level disposition simulation)
   and it targets retail [S18]. We found no suite agent for B2B industrial asset returns or cross-vendor circularity.
4. Returns point solutions (Loop, Narvar, ReverseLogix, Happy Returns, ReturnPro, Optoro inside Blue Yonder) are
   B2C/retail-first, SaaS, and add AI for fraud, policy and chat. ITAD/device tools own grading, diagnostics and
   erasure; we should read their outputs, not compete.
5. What nobody else combines: decision-first case across every route (value, risk, carbon), a vendor-neutral fabric
   with canonical checks and a conflict queue, maker-checker with shadow mode on business rules, agents that are
   structurally forbidden from approving, self-hosted, and back-testing as the sales motion.
6. The 6–8 month window is real for B2B industrial/asset circularity but already closed for retail B2C returns.
   The bigger threat is not a suite feature but a horizontal platform plus a systems integrator's template.

## Scope and method

- Date of research: 24 Nov 2026. Web pages read on that date unless a source gives its own date.
- Read first (team-shared): Camunda agentic overview, Camunda BPMN blog, Camunda platform, Manhattan Agent Foundry,
  ReverseLogix, Loop, Blue Yonder home pages. Then searches by vendor and topic.
- "Us" means the design in the brief: decision-first case, Connection Fabric (21 system types, canonical model,
  held records, conflict queue), Modeler (gate rules, business rules, guardrails, simulation, maker-checker, shadow,
  rollback), one action pipeline with a forbidden list for agents, journal with provenance, self-hosted Docker
  Compose and a trial package. Honest gaps on our side: no LLM reasoning loop yet, every connector is a mock, no
  BPMN/DMN standard, no SaaS, no security attestation, no consumer return portal.

---

## 1. Agentic orchestration and BPA platforms

### 1.1 Camunda 8 (closest architectural peer)

- **What it does.** Process orchestration on BPMN/DMN: Modeler, Zeebe engine, Operate (monitoring, incidents,
  audit), Tasklist (human tasks), Optimize (bottleneck dashboards), Connectors, Hub, Identity (RBAC, SSO, SCIM) [S5].
- **Agent capability.**
  - The AI Agent connector runs an LLM loop inside the engine, as an AI Agent Sub-process (recommended) or an AI
    Agent Task. Providers include Anthropic, Amazon Bedrock, Google Gemini, OpenAI [S2].
  - The **ad-hoc sub-process is the tool set**: each element inside it is a tool; tools may run in any order, many
    times, in parallel, or not at all. Camunda calls it "a governed toolbox" [S2]. The LLM picks the tool and
    parameters; Camunda runs the activity with retries, incidents, variables and human tasks [S1, S2].
  - MCP Client connector (tools from MCP servers), vector database connector, ad-hoc tools schema resolver [S2].
    Shipped with 8.8 (Oct 2025) [S9].
  - 8.9 (14 Apr 2026): Orchestration Cluster MCP Server (cluster operations for coding assistants, same authz as
    the REST API), three A2A connectors with A2A agents usable as tools, BPMN conditional events that react to agent
    outputs, relational databases (incl. PostgreSQL) as secondary storage, a central audit log [S6].
  - 8.10: **Operate agent view** (needs 8.10 or later): agent instance key; state (Thinking, Tool calling, Idle,
    Completed); model and system prompt; resolved tools; token use, tool-call count and model-call count against
    the configured limit; conversation grouped by loop iteration with each tool call's input and output; thinking
    content when the model returns it [S3]. 8.10-alpha3 (29 Jul 2026) also previewed an Agent Instance API so
    LangGraph/CrewAI agents get the same view, runtime DMN version selection by FEEL expression, and physical
    tenants [S7].
  - "External agents" (LangGraph, Bedrock, custom) are supported, but Camunda shows only what they report [S2].
- **Rules/BPMN.** BPMN 2.0 and DMN are native; processes stay portable as standard BPMN [S5].
- **How it mixes the three.** Deterministic BPMN "from the outside" (mandatory fraud check, approval before
  disbursement, timers) and "from the inside" (BPMN controls which tools the agent may call; some tools route to a
  human review). Autonomy can be raised or lowered per tool by changing the model, not the agent [S4].
- **Connectors.** Prebuilt for ERP, CRM, ITSM and LLM providers over MCP, A2A and REST [S5]; generic, not
  returns-specific.
- **Deployment.** SaaS (99.9% on Advanced clusters, cross-region DR) and Self-Managed [S5].
- **Licence and pricing.** Prices not published ("Talk to sales") [S5]. Source code under the Camunda License 1.0
  (source-available); since 8.6 Self-Managed needs a paid licence key for production, the free edition is
  non-production only [S8]. **Flag for Legal:** source-available, not OSI open source; no redistribution in a
  customer trial package without a commercial agreement.
- **Strengths vs us.** Mature engine, standards (BPMN/DMN), process versioning and instance migration, a polished
  agent run view, MCP and A2A both ways, large partner ecosystem, SaaS and self-managed.
- **Weaknesses vs us.** No decision content (valuers, routes, carbon, canonical asset model); a customer must build
  all of it. Guardrails are what you model, not a built-in forbidden list. No canonical data checks or conflict
  queue across sources. Self-managed is a heavy stack and paid in production. Rule changes are DMN deployments; we
  found no maker-checker, shadow mode or back-test over history for rules (**unconfirmed**).
- **Their own framing helps our pitch.** Camunda's 2026 report: 71% of organisations use AI agents but only 11% of
  agentic use cases reached production; 85% say they lack process maturity [S4] (vendor survey).

### 1.2 UiPath Maestro

- **What it does.** "Business orchestration" over UiPath robots, third-party agents, enterprise systems and
  people [S10]. Three canvases: Case, Flow and BPMN 2.0 (extended with UiPath task types); DMN decision tables;
  live instance management, routing, exception handling and SLA tracking [S10].
- **Mix.** Agents reason, robots execute, people direct; human-in-the-loop steps where a person must decide [S10].
  Case canvas lets the path evolve as information arrives (closest to our case model).
- **Connectors.** UiPath Integration Service plus RPA for systems without APIs (**unconfirmed** count).
- **Deployment.** Automation Cloud and Automation Suite (self-hosted); the docs exist for both [S10].
- **Pricing signal.** Not checked; UiPath sells platform/agent units by contract (**unconfirmed**).
- **Strengths.** RPA reaches systems with no API (useful for legacy WMS/ERP screens); case management; DMN.
- **Weaknesses vs us.** Generic; value depends on the UiPath estate; no returns content; agents are governed by
  process design, not by a hard forbidden list.

### 1.3 Pega (Agentic Process Fabric, Blueprint, Infinity '25)

- **What it does.** Case management and decisioning platform. Agentic Process Fabric announced 2 Jun 2025 to
  coordinate agents, apps, systems and data [S11]. Infinity '25 GA 24 Sep 2025: workflows "composed of both agentic
  and deterministic steps", runtime agents that find and execute the right workflow step, MCP and A2A support [S11].
- **Blueprint.** AI workflow designer; analyses legacy assets and drafts case types, personas, data and
  integrations; offered free as the entry point [S11]. Pega's message is "predictable AI": agents run inside
  governed case types [S11].
- **Deployment.** Pega Cloud first; client-managed timing for the agentic features **unconfirmed** [S11].
- **Pricing signal.** Blueprint free; platform by contract.
- **Strengths.** Strongest case management and next-best-action decisioning; the "free design tool as lead
  generator" motion is clever.
- **Weaknesses vs us.** Heavy, expensive, long implementations; no reverse-logistics content; a Pega estate is
  itself a lock-in.

### 1.4 Appian

- **What it does.** Low-code process platform with a data fabric. Agent Studio GA Nov 2025; agents can call other
  agents as tools; MCP adopted (28 Apr 2026) both ways: Appian agents call external systems, and an Appian MCP
  server exposes data fabric, process models and expression rules to outside agents; Snowflake partnership [S12].
- **Mix.** Agents are steps inside Appian process models; rules are Appian expression rules and decisions.
- **Deployment.** Appian Cloud and self-managed (**unconfirmed** for agent features).
- **Strengths.** Data fabric with a unified metadata model (the nearest analogue to our canonical model);
  regulated-industry footprint.
- **Weaknesses vs us.** Generic; several April 2026 items were announced as future releases [S12].

### 1.5 ServiceNow (AI Agent Orchestrator, AI Control Tower, AI Agent Fabric)

- **What it does.** Workflow platform (ITSM, CSM, FSM). AI Agent Orchestrator coordinates agents; AI Control
  Tower (expanded 5 May 2026) discovers, observes, governs, secures and measures AI, including agents built on
  other platforms such as Copilot Studio; it can stop an agent that exceeds its permissions (a "kill switch") [S13].
  AI Agent Fabric carries agent-to-agent and agent-to-tool traffic over A2A and MCP; Workflow Data Fabric is the
  data layer [S13]. Release timing of Agent Fabric differs between sources (**unconfirmed**).
- **Mix.** Agents act inside ServiceNow flows and playbooks; approvals and tasks are native.
- **Deployment.** SaaS (ServiceNow cloud).
- **Strengths.** Governance across vendors' agents; field service and asset (EAM) footprint makes it a plausible
  home for industrial service returns.
- **Weaknesses vs us.** Expensive per-seat/per-assist licensing (**unconfirmed** numbers); no disposition logic.

### 1.6 Microsoft Power Automate and Copilot Studio

- **What it does.** Agent flows in Copilot Studio are deterministic flows that agents call as tools; a flow can
  pause for approval in Outlook or Teams [S14]. "Request for information" (preview since Nov 2025) pauses a flow to
  collect input from a named reviewer and uses it in later steps [S14]. Advanced approvals (multi-stage) in preview.
- **Connectors.** The Power Platform connector library (very large; Dynamics 365 native).
- **Deployment.** Microsoft cloud only.
- **Pricing signal.** Copilot Credits: $200 per pack of 25,000 credits per month, or pay-as-you-go at $0.01 per
  credit; unused credits do not roll over [S14].
- **Strengths.** Already licensed in most enterprises; Teams/Outlook approvals where people already are.
- **Weaknesses vs us.** Citizen-developer sprawl; no domain content; governance is per tenant, not per decision.

### 1.7 Workato (Agent Studio, Genies, Enterprise MCP)

- **What it does.** iPaaS. Agent Studio builds "genies" (agents) from skills; genies are MCP clients of hosted and
  external MCP servers (Jan 2026) [S15]. Enterprise MCP turns API collections and recipes into MCP servers, with an
  MCP registry, SSO, RBAC and audit trails (Aug 2026 update: multiple clients per genie) [S15].
- **Recipes.** Workflow recipes, API recipes, skills, data-pipeline recipes [S15].
- **Common data model.** A shared, editable schema used by several connectors so integrations survive when an
  application is added or swapped [S15]. Closest commercial match to our canonical model.
- **Deployment.** SaaS (US, EU, AU, SG, JP data centres) [S15]; on-prem agent for private systems.
- **Pricing signal.** Genies only on specific plans; no public prices [S15].
- **Strengths.** Connector breadth, recipe reuse, governed MCP exposure.
- **Weaknesses vs us.** Integration first, decision second; no case, no disposition, no maker-checker on business
  policy.

### 1.8 n8n

- **What it does.** Node-based workflow automation with an AI Agent node. Human-in-the-loop per tool: the workflow
  pauses, asks in Slack/Telegram/chat; approved calls run with the agent's input, denied calls are cancelled and the
  agent is told [S16] (feature tied to v2.6 in a community post, **unconfirmed**). A community report on 2.10.4
  says the result does not return to the agent when approval comes from an external channel [S16].
- **Builder UX.** Input and output panels per node; data pinning reuses a node's output in test runs and can be
  edited as JSON; "Debug in editor" copies a failed past execution's data into the editor [S16].
- **Deployment.** Cloud and self-hosted.
- **Licence.** Sustainable Use License (fair-code, not OSI); files with `.ee.` in the name under the n8n Enterprise
  License; charging users for a service that relies significantly on n8n needs a commercial agreement [S16]. A
  forum figure of about $50k/year for Embed is **unconfirmed**. **Flag for Legal:** we cannot ship n8n inside our
  trial package without an agreement.
- **Strengths.** Best builder feedback loop on the market; huge community template library.
- **Weaknesses vs us.** No case model, no governance beyond per-tool approval, licence blocks embedding.

### 1.9 How each mixes deterministic process, agents and people

| Platform | Deterministic backbone | Where the agent sits | Human step | Hard limits on agents |
|---|---|---|---|---|
| Camunda 8.10 | BPMN + DMN, engine-run | Inside an ad-hoc sub-process; tools = BPMN elements | User task; any tool can route to review | Token/model-call/tool-call limits per agent; tool set by model [S2, S3] |
| UiPath Maestro | BPMN, Flow, Case + DMN | Agent tasks among robot tasks | HITL steps, SLAs | By process design [S10] |
| Pega | Case types, decisioning | Runtime agents choose workflow steps | Case assignments | "Predictable AI", governed case types [S11] |
| Appian | Process models, expression rules | Agent Studio agents as steps; agents as tools | Tasks | By process design [S12] |
| ServiceNow | Flows, playbooks | Agent Orchestrator | Native approvals | Control Tower kill switch, permission checks [S13] |
| Microsoft | Agent flows (deterministic) | Copilot Studio agent calls flows as tools | Approvals, request for information | Tenant policies [S14] |
| Workato | Recipes | Genies with skills / MCP | Approvals in recipes (**unconfirmed**) | RBAC, policies, audit [S15] |
| n8n | Node workflow | AI Agent node with tools | Per-tool approve/deny | Per-tool approval only [S16] |
| **Us** | Action pipeline (125 actions, 12 steps), decision flows, Workflow Studio | Agent registry; playbook runtime (LLM loop not built) | Proposals held for a person; approvals with delegation | Forbidden list in code (never approve, publish, override, decline, change access); per-agent allow-lists and run limits |

---

## 2. Supply-chain suites with agents

### 2.1 Manhattan Associates (Agent Foundry)

- **What.** No-code agent builder on the Manhattan Active data layer, three paths: describe the job in plain
  language and get a proposed agent structure; start from a template (Labor, Wave, Store, CSR agents); or build
  from scratch with a visual builder, prompt templates, conditions and direct API access [S17]. Lifecycle: create,
  version, test, deploy, publish, retire; guardrails, permissions and human approvals built in [S17].
- **Timeline.** Launched at Momentum (May 2025); agents commercially available 8 Jan 2026 (Interactive and
  Autonomous agents, MCP and A2A compatible); Apr 2026 added Store Associate, Contact Center and OMS Configuration
  agents; Momentum 2026 added a Marketplace for agents and accelerators [S17].
- **Returns.** No returns-specific agent on the Foundry page [S17]. Manhattan Active Omni handles returns, so a
  customer could build one (**unconfirmed** that any exists).
- **Pricing signal.** Agent Foundry "included with all Manhattan Active solutions" [S17].
- **Deployment.** SaaS (Manhattan Active).
- **Strengths.** Excellent pitch flow ("describe the job, get the agent") that mirrors our Studio-first pitch;
  WMS/TMS depth.
- **Weaknesses vs us.** Agents act only on Manhattan data and APIs; no circularity or asset valuation; useful only
  to Manhattan customers.

### 2.2 Blue Yonder (Returns Management, Optoro, Cognitive Solutions)

- **What.** Returns Management with a Smart Disposition engine that combines business rules and ML to route each
  return to store, DC or recommerce; ML resale-value prediction by location; bulk receipt and sorting; recommerce
  and liquidation workflows; refund rules per shopper [S18, 9 Jan 2026]. Bought Optoro (closed 19 Aug 2025) [S18].
- **Agentic (26–27 Aug 2026).** Cognitive Solutions update covering returns: customer-specific policies, receipt
  controls, disposition settings, **test-and-grade workflows**, **unit-level simulation of disposition outcomes**,
  per-item next-step recommendations, returns projections inside allocation and replenishment [S18]. Vendor claim:
  returned goods back to sellable about 25% faster [S18]. No named returns agent [S18].
- **Platform.** "AI agents on the Blue Yonder Platform" monitor the network; Orchestrator as interaction layer;
  MCP not mentioned on the home page [S18].
- **Deployment.** SaaS.
- **Strengths.** The most direct functional overlap with our disposition engine, at retail scale, with Optoro's
  returns data.
- **Weaknesses vs us.** Retail/B2C first; no B2B industrial assets, leases, RUL, PLM, IoT operating hours;
  disposition lives inside the Blue Yonder estate. Carbon is a separate sustainability product (**unconfirmed**
  link to disposition).

### 2.3 SAP

- **What.** Sapphire (14 May 2026): Autonomous Supply Chain Management with Joule Assistants (Asset and Service,
  Business Network, Logistics, Manufacturing, Planning, Product Design) and "more than 60" supply-chain agents
  (e.g. Asset Performance Alert Processing, Technician Briefing); GA "phased throughout 2026" [S19]. A new SAP
  Field Service and Asset Management solution [S19].
- **Returns and circularity.** No returns, refurbishment or circularity agent in the May 2026 announcement [S19].
  Existing pieces: SAP Intelligent Returns Management (AI in the return process) [S19]; a reprocessing template
  for repair, refurbishment and remanufacturing triggered by maintenance, customer request, sales order or IoT
  (blog, date **unconfirmed**) [S19]; Sustainability Footprint Management and Green Ledger for carbon [S19];
  partner apps for second-life workflows via SAP Commerce [S19].
- **Deployment.** SAP cloud (BTP, Cloud ERP); private editions.
- **Strengths.** Owns the ERP record our instructions land in; has every building block (returns, EWM inspection,
  footprint, asset management).
- **Weaknesses vs us.** Blocks are not assembled into a cross-route decision; anything non-SAP is second class.
- **Watch.** SAP is the single most credible "window closer" for industrial circularity: the asset-service
  assistant plus reprocessing plus footprint is one product decision away from our story.

### 2.4 Oracle

- **What.** 10 Feb 2026: SCM agents built with AI Agent Studio (Planning Cycle, Inventory Tasking, Product
  Configuration, PO-to-SO Converter, Service Parts Advisor); an agent recommends returns or transfers for aging
  stock and executes the chosen action [S20]. Solution brief: 100+ agents in Fusion Cloud SCM at no added licence
  cost [S20]. 29 Jun 2026: four Fusion Agentic Applications, built on teams of agents [S20].
- **Returns.** No packaged RMA or disposition agent found (**unconfirmed**); customers can build one in AI Agent
  Studio [S20].
- **Strengths.** "No added cost" agents set a price anchor buyers will quote back to us.
- **Weaknesses vs us.** Oracle-only data; no circularity routing.

### 2.5 Adjacent: IFS and Syncron (industrial service)

- **IFS.** IFS Cloud 25R2 (27 Nov 2025) introduced agentic Digital Workers across ERP, EAM, FSM; IFS Loops Agent
  Studio (23 Apr 2026) configures and governs them, with built-in guardrails and outcome metrics [S21]. No
  returns/repair Digital Worker found. IFS owns many industrial asset and service-repair processes, so it is an
  adjacent threat for the tool-fleet AMS template.
- **Syncron.** Aftermarket (service parts, pricing, warranty). 2026 news: field-data partnership for warranty
  decisions (29 May), enterprise data platform integrations (30 Jun), Service Contract Performance (7 Oct) [S22].
  No agentic disposition found. Possible partner rather than rival.

---

## 3. Returns, reverse logistics, ITAD and device recommerce

### 3.1 Returns platforms

| Vendor | What it does | AI / agent capability | Rules | Connectors | Deployment, pricing signal |
|---|---|---|---|---|---|
| **ReverseLogix** | Returns, warranty, repair, recommerce on one platform; B2C and B2B (bulk freight, distributor rules); receiving, inspection, grading, disposition, 3PL routing [S23] | Vision AI reads photos at initiation and grades; fraud by serial, frequency, reason; AI chatbot; "AI recommends, retailers remain in control" [S23] | Business rules: entitlement vs warranty and distributor contracts, credit validation [S23] | SAP, Oracle, NetSuite, D365, Salesforce, Shopify, carriers [S23] | SaaS (**unconfirmed** on the page); Shopify app launched 10 Feb 2026 with base plan; ROI/TCO calculators, no prices [S23] |
| **Loop** | Post-purchase for e-commerce: returns, exchanges, fraud, tracking, editing, shipping [S24] | Loop Intelligence (100M+ returns, 200M+ shoppers) adjusts policies per shopper; AI agent for CX teams (Spring 2026); AI suite launch 28 Apr 2026 [S24] | Policies that adapt to shopper data [S24] | Shopify native; others custom [S24] | SaaS; plans for all sizes, no prices; Shopify go-live 15–45 days [S24] |
| **Optoro** (Blue Yonder since Aug 2025) | Returns optimisation, disposition, recommerce for large retailers [S18] | Folded into Smart Disposition [S18] | BY rules + ML | BY platform | BY SaaS |
| **Happy Returns** (UPS) | Box-free return drop-off network (Return Bars; 10,000 locations, Apr 2026) [S25] | Return Vision: computer vision compares returns to catalogue photos; behavioural risk scoring; humans make the final call; wider rollout planned for 2026 [S25, S29] | Network policies | Retailer integrations | Service + software |
| **Narvar** | Post-purchase: tracking, returns (Shield), claims [S26] | IRIS engine (policy per consumer, risk and abuse flags, next move); NAVI agentic assistant for delivery issues, returns, refunds, exchanges (12 Jan 2026) [S26] | Policies applied by IRIS | Retail commerce stacks | SaaS |
| **Inmar** | Reverse distribution, strongest in pharmacy returns, recall and compliance [S27] | No 2026 AI returns product found [S27] | Compliance rules | Pharmacy/retail | Service + software |
| **ReturnPro** | Returns SaaS, 13 returns centres, recommerce on 20+ marketplaces, B2B wholesale marketplace [S28] | AIRE "AI Returns Engine" for real-time disposition decisions; AI fraud partner (Feb 2026) [S28] | Disposition logic in AIRE | Shopify app (5 Jan 2026), marketplaces [S28] | SaaS + operated services |

Others seen but not researched in depth (**unconfirmed** detail): AfterShip Returns, ZigZag, ReBound, Two Boxes
(B2C returns); B-Stock and Liquidity Services (liquidation marketplaces); DHL's returns network with an in-house
re-SKU tool [S29]. A large US retailer runs its own algorithm that decides resell, donate, recycle or liquidate per
item every day; a footwear brand runs a rules engine it can change itself [S29]. Retailers building in-house is a
competitor too.

**Pattern.** Retail returns AI concentrates on three things: fraud, return forecasting and decision support [S29].
An NRF/Happy Returns survey: 85% of merchants use AI/ML for returns fraud, only 45% think it works well alone [S29].
That supports our "humans approve, agents plan" stance.

### 3.2 ITAD and device recommerce software

- **Diagnostics, grading and erasure.** Phonecheck (IMEI checks for blacklist, finance, carrier lock, MDM, iCloud;
  80-point diagnostics; device history report) [S30]. Blancco (75+ diagnostic tests, certified erasure, mobile
  buy-back with real-time pricing; kiosk grading station trial in Japan) [S30]. One overview groups Blancco,
  Phonecheck, NSYS, BlackBelt as diagnostics + certified erasure and Apkudo, FutureDial as automation, AI testing
  and cosmetic grading [S30].
- **Recommerce integration layer.** Device Network integrates BlackBelt, Phonecheck, NSYS, Blancco, FutureDial and
  others for trade-in [S30].
- **ERPs for ITAD and refurbishers.** Makor ERP (sales, CRM, financials, inventory; data wipe and destruction
  reporting; chain of custody) and RazorERP (cloud ERP for e-waste, ITAD and brokers; multichannel sync) [S31].
- **Market size signal.** US mobile trade-in payouts $1.63bn in Q1 2026 and $1.43bn in Q2 2026 (a device-protection
  provider's quarterly data, secondary) [S30].
- **Implication.** For the device trade-in template these tools are **sources**, not rivals: we read the grade,
  the erasure certificate and the lock status (brief item 3: erasure certificate only for IT/compute assets) and
  decide the route and channel. We found no ITAD vendor offering a cross-route decision with value, risk and
  carbon; pricing engines exist inside trade-in programmes (**unconfirmed** depth).

---

## 4. Strengths and weaknesses against our design

Our five pillars: (D) decision-first, (F) vendor-neutral fabric, (M) maker-checker, (J) journal, (S) self-hosted.
Reading: Y = has it, P = partly, N = no evidence found, ? = unknown. Our reading of public pages, not tested.

| Vendor | D | F | M | J | S | Biggest threat to us | Biggest gap vs us |
|---|---|---|---|---|---|---|---|
| Camunda | N | P (generic connectors) | P (process versioning, no rule maker-checker found) | Y (audit log, Operate history) | Y (paid in prod) | Customer or SI builds a returns solution on it | No domain content |
| UiPath Maestro | N | P (RPA reaches anything) | ? | Y | Y | Existing RPA estates | No domain content |
| Pega | P (decisioning) | P | Y (Pega governance, **unconfirmed** detail) | Y | P | Free Blueprint drafts a returns app | Cost, speed |
| Appian | N | P (data fabric) | ? | Y | P | Data fabric + MCP server | No domain content |
| ServiceNow | N | P | P | Y | N | FSM/EAM customers stay in one platform | No disposition |
| Microsoft | N | P (connectors) | N | P | N | Already paid for | Governance per decision |
| Workato | N | Y (common data model) | N | Y | N | Integration layer + genies | No case, no decision |
| n8n | N | P | N | P | Y (licence limits) | Cheap DIY | Governance, licence |
| Manhattan | P | N (Manhattan data) | P | Y | N | Returns agent built in Foundry | Single vendor, no circularity |
| Blue Yonder | Y (retail) | N | ? | Y | N | Disposition simulation, ML resale value | Retail only, BY estate |
| SAP | P | N | P | Y | P (private cloud) | Assembles its blocks | Non-SAP second class |
| Oracle | P | N | ? | Y | N | Free agents anchor price | Oracle only |
| ReverseLogix | P (rules) | P (ERP connectors) | ? | ? | N | B2B returns + warranty in one SaaS | Rules, not valued routes; no agents to speak of |
| Loop / Narvar | P (policy) | N (Shopify-centred) | N | ? | N | Owns the shopper front door | B2C only |
| ReturnPro | P (AIRE) | N | ? | ? | N | Software + returns centres + marketplaces | Captive to its network |

What we lack that buyers will compare: SaaS option, SOC 2 / ISO 27001 (ReverseLogix claims both [S23]), real
production connectors (ours are mocks), a consumer return portal, computer-vision grading, BPMN/DMN portability, an
LLM agent loop and an agent run view.

---

## 5. Positioning

### 5.1 Matrix

```
 Orchestration generality (agents + process for any domain)
  high |  Camunda  UiPath  Pega  Appian                    |
       |  ServiceNow  Microsoft  Workato  n8n              |   <- target: domain decision
       |                                                   |      content on a general,
       |                                 [US, target] ---> |      vendor-neutral platform
  mid  |  Manhattan Foundry   Oracle Agent Studio          |
       |  SAP Joule   IFS Loops                            |
       |                      Blue Yonder (retail returns) |
  low  |  Makor/RazorERP   Blancco/Phonecheck             |
       |  Narvar   Loop   Happy Returns   ReverseLogix   ReturnPro
       +---------------------------------------------------+
         none          returns/disposition domain depth           deep
         (vendor-locked suites sit mid-height: general inside their own estate only)
```

Reading: the top-left is crowded and well funded; the bottom-right is crowded with retail SaaS. The top-right
(general orchestration **and** deep disposition content, vendor-neutral) is empty today. Blue Yonder is the
nearest, but only inside its own retail estate.

### 5.2 Table-stakes features we must have

1. **Agent run view**: state, model, prompt, tools offered, every tool call with input and output, tokens and cost
   against limits (Camunda [S3] sets the bar; LLM loop not built yet on our side).
2. **Human steps beyond approve/reject**: request for information, delegation, SLA timers and escalation
   (Microsoft RFI [S14], Maestro SLAs [S10]).
3. **Per-tool human approval and limits** for agents (n8n [S16], Camunda [S2]); we have per-agent; add per-tool.
4. **MCP server and client**, A2A on the roadmap (all horizontal players and Manhattan ship both [S6, S11, S12,
   S13, S17]).
5. **Multi-provider LLM with fallback** (Camunda supports Anthropic, Bedrock, Gemini, OpenAI [S2]).
6. **Natural-language builder** that drafts a flow or agent from a sentence (Manhattan [S17], Pega Blueprint [S11]);
   ours maps to the nearest topology today.
7. **Versioned, testable flows** with draft/publish and instance history (everyone).
8. **Production connectors** to SAP, Oracle, NetSuite, D365, Salesforce, Shopify, carriers (ReverseLogix lists
   exactly these [S23]).
9. **RBAC, SSO, SCIM, audit log, multi-tenancy** (Camunda Identity [S5]).
10. **Returns domain basics**: RMA intake, grading capture (read from tools), fraud signals, ML resale value,
    refund/credit rules, analytics (Blue Yonder [S18], ReverseLogix [S23], Loop [S24]).
11. **A SaaS option and security attestations**, even if self-hosted stays our differentiator.

### 5.3 What nobody does that we do (as far as public material shows)

1. **Decision-first across every route.** One case, every route (redeploy, refurbish, resell, re-lease, harvest,
   recycle, exit) valued with value, risk and **deterministic carbon on every card**, with the rules applied
   explained. Blue Yonder does profit-led disposition for retail [S18]; nobody found does it for B2B assets with
   carbon on the card.
2. **Vendor-neutral fabric with data governance.** Canonical model with unit/currency/time normalisation, canonical
   checks, held records and a **conflict queue between sources** for a person. Workato's common data model is the
   nearest [S15], without the conflict queue or holds.
3. **Maker-checker, shadow mode and rollback on business rules**, with simulation over historical cases. Camunda
   selects DMN versions at runtime [S7] but we found no maker-checker or shadow mode (**unconfirmed**).
4. **Agents that structurally cannot approve.** A forbidden list enforced in the single write pipeline for every
   agent-prepared call. Others offer configurable guardrails or a kill switch [S13]; none advertises a hard-coded
   "agents never approve, publish, override, decline or change access".
5. **Back-testing as the sales motion**: replay a quarter of the customer's returns and show net uplift against
   what they did. Blue Yonder's unit-level disposition simulation [S18] is the only near match.
6. **Self-hosted, Postgres only, trial package in under a week.** Camunda self-managed is heavier and paid in
   production [S8]; the suites and returns SaaS are cloud only.
7. **B2B industrial assets with IoT hours, PLM remaining useful life and contract terms** in the decision
   (tool-fleet AMS template). Suites have the pieces (SAP asset service, IFS EAM) but not the decision [S19, S21].

### 5.4 What to copy

UX patterns:

| Pattern | From | How it maps to us |
|---|---|---|
| Agent instance panel: state badge (Thinking / Tool calling / Idle / Completed), model and system prompt, resolved tools, tokens, model calls and tool calls against limits, conversation grouped by iteration, expand a tool call to see input and output, hover for usage breakdown | Camunda Operate 8.10 [S3] | An "Agent run" drawer on the case and on the Agents page, fed by the journal; usage against `run limits`; link each tool call to the action id and the case event |
| Highlight the agent's live state on the process diagram; link each tool call to its diagram element | Camunda 8.10-alpha3 [S7] | Light up the current block on the Modeler/Workflow canvas during a run |
| Input and output panels per node; pin a sample and edit it as JSON; "Debug in editor" from a failed past run | n8n [S16] | Workflow Studio: show a real sample record in and out of every block; pin a record for test runs; open a failed sync run in the canvas with its data |
| Per-tool approve/deny, and tell the agent it was denied | n8n [S16] | Per-tool autonomy (act / propose) on top of per-agent; a declined proposal goes back to the agent as context |
| Autonomy spectrum per tool, moved up or down over time | Camunda blog [S4] | Autonomy dial per action in the agent registry, changed by maker-checker |
| Three ways to build: describe it, start from a template, build from scratch; lifecycle with "retire" | Manhattan Agent Foundry [S17] | Studio entry screen with the same three doors; add "retire" to flows, agents and template packs |
| Marketplace for agents and accelerators | Manhattan Momentum 2026 [S17] | Template-pack gallery (industrial, tool fleet, device) that partners can add to |
| Request for information (pause to collect a value, not just a yes/no) | Microsoft Copilot Studio [S14] | Proposal type "needs info": the agent asks a named person for a missing field (e.g. contract clause) |
| Kill switch for an agent that strays | ServiceNow AI Control Tower [S13] | One-click "pause agent" on the Agents page, journalled |
| Case canvas where the path evolves | UiPath Maestro [S10] | Our case timeline already is this; name it so buyers recognise it |
| Free design tool as the door in | Pega Blueprint [S11] | Free back-test report or free template draft as the first step of a sale |

Architecture patterns:

| Pattern | From | Note for us |
|---|---|---|
| Ad-hoc sub-process as a governed toolbox: the tool set is drawn on the canvas | Camunda [S2] | Draw an agent's allow-list as a box on the canvas; the tool catalogue already holds the schemas |
| Every tool call is a governed activity with retries and incidents | Camunda [S1, S2] | Already true: every tool call goes through `pipeline.invoke`; add incident view for failed agent calls |
| Usage limits as first-class config (tokens, model calls, tool calls) | Camunda [S3] | Extend agent run limits to tokens and cost |
| Agent Instance API so external agents report into the same view | Camunda 8.10 [S7] | Let MCP-client agents post run events into our journal |
| Runtime decision-version selection by expression | Camunda 8.10-alpha3 [S7] | Pick a business-rule version by org unit or pilot cohort without republishing |
| Conditional events reacting to agent output | Camunda 8.9 [S6] | Triggers on proposal content (e.g. confidence below threshold opens an exception) |
| Common data model shared by connectors | Workato [S15] | Make the canonical model visible, versioned and editable by customer IT, per template pack |
| Recipes and skills exposed as MCP tools via a registry | Workato [S15] | MCP generated from the action catalogue (already decided) plus a registry page |
| MCP server for operators' coding tools (incidents, instances, tasks) | Camunda 8.9 [S6] | Our MCP server should cover operations, not only business actions |

---

## 6. The "6–8 month window" claim

The claim: large suite vendors will ship comparable circularity features in 6–8 months.

### Evidence that the window is closing (or closed)

- **Retail B2C returns: closed.** Blue Yonder announced test-and-grade workflows and unit-level disposition
  simulation on 26 Aug 2026 (press release; general availability not stated) (corrected in verification, see
  V-verification.md) and owns Optoro since Aug 2025 [S18]. Loop (Apr 2026), Narvar (Jan 2026),
  ReverseLogix and Happy Returns all ship AI for returns [S23–S26].
- **Build-your-own agents inside suites exist today.** Manhattan Agent Foundry (GA Jan 2026, included with all
  Manhattan Active solutions) [S17], Oracle AI Agent Studio with 100+ SCM agents at no added cost [S20], IFS Loops
  Agent Studio [S21], SAP's 60+ supply-chain agents phased through 2026 [S19]. A customer or integrator can build
  a returns agent on any of them now.
- **SAP has every block.** Intelligent Returns Management, a reprocessing template (repair, refurbish,
  remanufacture, IoT-triggered), Field Service and Asset Management, Footprint Management and Green Ledger [S19].
- **Horizontal platforms are generic but ready.** Camunda, Pega, Appian and ServiceNow all ship agents, MCP and A2A
  in 2025–2026 [S6, S11–S13]; Pega Blueprint drafts an application from a description for free [S11].
- **Next big event dates fall right at the end of the window**: Blue Yonder ICON 17–19 May 2027 [S18], Manhattan
  Momentum 18–20 May 2027 [S17]; SAP Sapphire is usually in May–June (2027 date **unconfirmed**). If a suite
  announces industrial circularity, it is most likely there, about 6 months from today.

### Evidence that a window exists

- No suite announcement found for **B2B industrial asset returns, lease-end, tool-fleet or cross-vendor
  circularity** decisions: SAP's May 2026 supply-chain news does not mention returns or circularity [S19]; Oracle has
  no packaged RMA agent [S20]; Manhattan's Foundry page lists no returns agent [S17]; IFS has no returns Digital
  Worker [S21]; Syncron's 2026 news is warranty and contracts [S22].
- Blue Yonder's returns news is explicitly retail [S18].
- Suite agents act on their own data layer (Manhattan "runs on the Manhattan Active data layer" [S17]); the
  multi-vendor estate (SAP ERP + other WMS + other EAM + IoT + PLM) is structurally not theirs to serve.
- Suite agent catalogues are broad and shallow (planning, labour, inventory, field service); disposition with
  valuation, contract checks and carbon is specialised content.
- Announcement to usable product is slow: SAP phases GA "throughout 2026" [S19]; Pega's fabric followed Infinity
  '25 by a month and client-managed timing is unclear [S11].

### Verdict

- **Partly supported.** For retail B2C returns the window has closed. For B2B industrial and multi-vendor asset
  circularity, 6–8 months is plausible for suite *feature announcements* (May 2027 events), and longer (12+ months)
  for usable, cross-vendor product.
- **The sharper risk is not a suite feature.** It is a horizontal platform (Camunda, Pega, ServiceNow) plus a
  systems integrator's returns template, or a suite customer building a disposition agent in Agent Foundry or AI
  Agent Studio. Our defence is domain content and proof, not the orchestration engine: template packs, valuers,
  the canonical asset model, back-test results and reference pilots.
- **Recommendation for the pitch.** Say "no suite ships cross-vendor industrial disposition today (as of Nov 2026);
  the next likely announcements are the May 2027 conferences". Avoid claiming a precise 6–8 months as fact.

---

## Unconfirmed

- Exact GA date of Camunda 8.10 (docs list 8.10 as current and 8.11 as unreleased [S2]); whether Camunda supports
  maker-checker or shadow mode for DMN.
- UiPath Maestro pricing units and connector count; whether agent features run on Automation Suite (self-hosted)
  at parity with the cloud.
- Pega client-managed timing for agentic features; Pega governance detail.
- Appian agent features on self-managed deployments; ServiceNow AI Agent Fabric release timing (sources differ).
- Workato human-approval step inside recipes; Workato and ServiceNow price levels.
- n8n HITL version (v2.6 per a community post) and the ~$50k/year Embed figure.
- Whether a returns agent exists in Manhattan Active Omni or Agent Foundry templates.
- Whether Blue Yonder links disposition to carbon; the 25% faster-to-sellable figure (vendor claim).
- SAP reprocessing-template blog date; any SAP returns/circularity Joule agent; Sapphire 2027 date.
- Oracle packaged RMA agent.
- ReverseLogix deployment model (SaaS assumed) and any named agent product; Happy Returns exact press date for the
  10,000-location milestone.
- Depth of pricing engines in device trade-in programmes; AfterShip, ZigZag, ReBound, Two Boxes, B-Stock details.
- All capability claims are vendor-reported; none was tested hands-on. Licence readings (Camunda, n8n) need review
  by Kinective's Legal team.

## Sources

Accessed 24 Nov 2026 unless another date is given. Dates in brackets are the publication dates.

- S1 Camunda docs, Agentic orchestration overview (8.10 docs): https://docs.camunda.io/docs/components/agentic-orchestration/agentic-orchestration-overview/
- S2 Camunda docs, AI agents (8.10; 8.11 unreleased): https://docs.camunda.io/docs/components/agentic-orchestration/ai-agents/
- S3 Camunda docs, Monitor AI agents (Operate 8.10 or later): https://docs.camunda.io/docs/components/agentic-orchestration/monitor-ai-agents/
- S4 Camunda blog, B. Ruecker, "Why BPMN still matters, especially in the age of AI" [3 Apr 2026]: https://camunda.com/blog/2026/04/why-bpmn-still-matters-especially-in-the-age-of-ai/
- S5 Camunda platform page: https://camunda.com/platform/
- S6 Camunda blog, "Camunda 8.9: your fastest path to agentic orchestration" [14 Apr 2026]: https://camunda.com/blog/2026/04/camunda-8-9-fastest-path-to-agentic-orchestration/
- S7 Camunda blog, "Inside Camunda 8.10-alpha3" [29 Jul 2026]: https://camunda.com/blog/2026/07/inside-camunda-810-alpha3-the-architecture-that-makes-agentic-orchestration-trustworthy/
- S8 Camunda licences docs: https://docs.camunda.io/docs/reference/licenses/ ; Camunda blog, "Camunda licensing: what you need to know" [Oct 2024]: https://camunda.com/blog/2024/10/camunda-licensing-what-you-need-to-know/
- S9 Camunda forum, "Camunda 8.8 has been released" [Oct 2025]: https://forum.camunda.io/t/camunda-8-8-has-been-released/65363 ; Camunda blog, "Enterprise-grade agentic automation is here" [Oct 2025]: https://camunda.com/blog/2025/10/enterprise-grade-agentic-automation-is-here/
- S10 UiPath Maestro docs, value proposition: https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/value-proposition ; Automation Suite docs: https://docs.uipath.com/maestro/automation-suite/2.2510/user-guide/value-proposition ; product page: https://www.uipath.com/product/maestro
- S11 Pega, Agentic Process Fabric press release [2 Jun 2025]: https://www.businesswire.com/news/home/20250602953139/en/ ; Pega Infinity '25 GA [24 Sep 2025]: https://www.businesswire.com/news/home/20250924975521/en ; TechTarget on Blueprint agent builder [2026]: https://www.techtarget.com/enterprise-software/news/366643870/Pegasystems-refines-Blueprint-agent-builder-expands-marketing-tools
- S12 SiliconANGLE, Appian adopts MCP, Snowflake partnership [28 Apr 2026]: https://siliconangle.com/2026/04/28/appian-adopts-mcp-protocol-partners-snowflake-provide-structure-control-ai-agents/ ; Appian Q2 2026 product highlights: https://appian.com/blog/2026/q2-product-highlights
- S13 ServiceNow press release, AI Control Tower expansion [5 May 2026]: https://newsroom.servicenow.com/press-releases/details/2026/ServiceNow-expands-AI-Control-Tower-to-discover-observe-govern-secure-and-measure-AI-deployed-across-any-system-in-the-enterprise/default.aspx ; The Register [5 May 2026]: https://theregister.com/2026/05/05/servicenow_clears_agents_for_landing/
- S14 Microsoft Learn, Request information from human review in agent flows: https://learn.microsoft.com/en-us/microsoft-copilot-studio/flows-request-for-information ; What's new in Copilot Studio [Nov 2025]: https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/whats-new-in-microsoft-copilot-studio-november-2025/ ; Copilot Studio pricing: https://www.microsoft.com/en-us/microsoft-365-copilot/pricing/copilot-studio ; licensing guide: https://www.microsoft.com/licensing/guidance/microsoft-copilot-studio
- S15 Workato docs, Agent Studio: https://docs.workato.com/agentic/agent-studio ; Product Scoop [Jan 2026]: https://www.workato.com/product-hub/product-scoop-january-2026/ ; Product Scoop [Aug 2026]: https://www.workato.com/product-hub/product-scoop-august-2026/ ; Common data model: https://docs.workato.com/features/common-data-model ; Agentic FAQ: https://docs.workato.com/agentic/faqs
- S16 n8n docs, Human-in-the-loop for AI tool calls: https://docs.n8n.io/advanced-ai/human-in-the-loop-tools ; data pinning: https://docs.n8n.io/data/data-pinning ; debug executions: https://docs.n8n.io/workflows/executions/debug ; Sustainable Use License: https://docs.n8n.io/n8n-community-license/sustainable-use-license ; licence FAQ: https://docs.n8n.io/n8n-community-license/community-license/license-faq ; community report on 2.10.4: https://community.n8n.io/t/hitl-on-latest-2-10-4/274050
- S17 Manhattan Agent Foundry page: https://www.manh.com/solutions/manhattan-active-platform/build-ai-agents-agent-foundry ; commercial availability of AI agents [8 Jan 2026]: https://ir.manh.com/node/21131 ; retail enhancements [Apr 2026]: https://ir.manh.com/node/21136 ; Momentum 2026 blog: https://www.manh.com/our-insights/resources/blog/momentum-2026-welcome-agentic-era
- S18 Blue Yonder home page: https://blueyonder.com/ ; Blue Yonder blog, returns enhancements [9 Jan 2026]: https://blueyonder.com/blog/2026/new-returns-enhancements-help-retailers-capture-value-as-peak-returns-begin ; IT Brief Australia on agentic returns [27 Aug 2026]: https://itbrief.com.au/story/blue-yonder-adds-ai-retail-tools-for-returns-stock ; Optoro acquisition [18 Aug 2025]: https://www.businesswire.com/news/home/20250818415001/en/ ; Digital Commerce 360 [22 Aug 2025]: https://www.digitalcommerce360.com/2025/08/22/blue-yonder-buys-optoro-acquisition-returns/
- S19 SAP News, "A more autonomous supply chain" [14 May 2026]: https://news.sap.com/2026/05/more-autonomous-supply-chain ; SAP Intelligent Returns Management [Dec 2023]: https://www.sap.com/assetdetail/2023/12/62ec9f2a-9f7e-0010-bca6-c68f7e60039b.html ; SAP blog on reprocessing (date unconfirmed): https://blogs.sap.com/t5/product-lifecycle-management-blogs-by-sap/maximizing-profitability-increase-re-use-in-the-discrete-industry/ba-p/13579203 ; Sustainability Footprint Management: https://www.sap.com/products/scm/sustainability-footprint-management.html ; reverse logistics partner app: https://www.sap.com/products/crm/partners/sav-group-reversio.html
- S20 Oracle press release, SCM AI agents [10 Feb 2026]: https://www.oracle.com/news/announcement/oracle-ai-agents-help-boost-supply-chain-efficiency-and-strengthen-resiliency-2026-02-10/ ; Fusion Agentic Applications for SCM [29 Jun 2026]: https://www.oracle.com/sg/news/announcement/oracle-adds-new-fusion-agentic-applications-to-help-customers-improve-supply-chain-performance-2026-06-29/ ; solution brief: https://www.oracle.com/a/ocom/docs/applications/scm/autonomous-ai-powered-supply-chain.pdf
- S21 IFS, "IFS Loops launches Agent Studio" [23 Apr 2026]: https://ifs.com/en/insights/news/ifs-loops-launches-agent-studio ; IFS Cloud 25R2 [27 Nov 2025]: https://www.ifs.com/de/insights/news/ifs-cloud-25r2
- S22 Syncron press releases [29 May 2026; 30 Jun 2026; 7 Oct 2026]: https://www.syncron.com/press-releases/syncron-and-truecontext-help-manufacturers-turn-field-execution-into-better-warranty-decisions ; https://www.syncron.com/press-releases/syncron-expands-integration-capabilities-to-connect-aftermarket-intelligence-with-enterprise-data-platforms
- S23 ReverseLogix home page: https://www.reverselogix.com/ ; AI returns page: https://www.reverselogix.com/ai-powered-returns-management-platform/ ; Shopify app [launched 10 Feb 2026]: https://apps.shopify.com/reverselogix-rms
- S24 Loop home page: https://www.loopreturns.com/ ; Spring 2026 launch: https://www.loopreturns.com/launches/spring-2026/ ; IT Brief UK [28 Apr 2026]: https://itbrief.co.uk/story/loop-launches-ai-suite-to-cut-retailer-returns-costs
- S25 Supply Chain Dive, Happy Returns vision software pilot [date unconfirmed, late 2025]: https://www.supplychaindive.com/news/ups-happy-returns-vision-software-pilot-everlane/808785/ ; UPS newsroom, box-free label network [Apr 2026, exact date unconfirmed]: https://about.ups.com/gb/en/newsroom/press-releases/customer-first/ups-and-happy-returns-cement-position-as-largest-box-free-label-.html
- S26 Narvar, NAVI agentic assistant [12 Jan 2026]: https://corp.narvar.com/press/narvar-introduces-navi-an-agentic-assistant-for-post-purchase-automation ; IRIS and Narvar Assist [9 Jan 2025]: https://corp.narvar.com/press/narvar-introduces-iris-the-ai-engine-powering-the-future-of-post-purchase-launches-narvar-assist-as-its-first-iris-powered-solution ; IRIS page: https://corp.narvar.com/iris
- S27 Inmar pharmacy reverse distribution renewal [effective 1 Feb 2026]: https://www.biospace.com/press-releases/inmar-intelligence-awarded-renewed-pharmacy-reverse-distribution-agreement-with-premier-inc
- S28 ReturnPro Returns SaaS: https://returnpro.com/solutions/returns-saas ; Shopify app [5 Jan 2026]: https://www.businesswire.com/news/home/20260105402701/en/
- S29 Sourcing Journal via Yahoo Finance, "AI rewrites the playbook for reverse logistics" [6 Feb 2026]: https://finance.yahoo.com/news/ai-rewrites-playbook-reverse-logistics-174500059.html
- S30 Phonecheck buyback: https://www.phonecheck.com/industries/buyback ; Blancco in-store trade-in blog: https://blancco.com/resources/blog-the-in-store-phone-trade-in-has-evolved-so-must-carriers-and-retailers/ ; Platform Professional, smartphone recommerce tech stack (secondary): https://platformprofessional.substack.com/p/the-tech-stack-powering-smartphone ; ChannelX on Device Network [Jul 2026]: https://channelx.world/2026/07/device-network-makes-trade-in-simpler-smarter-and-more-transparent/ ; Automation World, device lifecycle [2026]: https://www.automationworld.com/analytics/news/55408464/ai-and-automation-are-rewriting-the-device-lifecycle
- S31 Makor ERP (Capterra): https://www.capterra.com/p/184102/Makor-ERP/ ; Makor ERP (TrustRadius): https://www.trustradius.com/products/makor-erp/details ; RazorERP (Capterra): https://www.capterra.com/p/148503/RazorERP/
- Repo: `../2026-11-agent-foundation.md` (agent runtime decision, Orkes Conductor and Agno rejected as the platform).
