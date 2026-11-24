# C. Competitive landscape (24 Nov 2026, revision 2: Recover)

Part C of the platform research (brief: [00-brief.md](00-brief.md); target: [01-recover-segments.md](01-recover-segments.md),
cited as "01 §n"). It covers:

- who else orchestrates agents, people and deterministic process;
- who sells AI for returns and reverse logistics, and for each of Recover's five industry segments;
- who offers a "describe your business, get a flow or app" experience like **Compose**;
- where we stand, what to copy, and whether the "6–8 month window" claim holds.

Sources are listed at the end as [S#] with dates. Vendor claims are vendor claims: nothing here was tested
hands-on. Licence lines need review by Kinective's Legal team before anyone relies on them.

## What changed in this revision and why

**Added**

| What | Why |
|---|---|
| §4 Segment competitors: used cars (remarketing, recon, auction and wholesale pricing, dealer inventory and lot transfers), telecom network equipment (asset recovery services, OEM take-back, network inventory, spares planning), medical rental equipment (clinical asset management and CMMS, RTLS, rental software) | 01 §6–8 adds three segments. Each needs its rivals, the systems Recover reads from (**sources**), and the gaps. |
| §4.1 Short pointers for tool fleet AMS and device recommerce | These two segments were already covered in §2.5 and §3.2. They now sit beside the other three. |
| §5.1 "Describe your business → generated flow or app" (Appian Composer, ServiceNow Build Agent, Power Apps Plans, UiPath Autopilot for Maestro, Camunda BPMN Copilot, Pega Blueprint, Manhattan Agent Foundry, Aera Skill Building) | Compose (01 §2) is now the front door of the product. We need to know what others generate, which guardrails they keep, whether they have maker-checker, and whether they offer a percentage rollout. |
| §5.2 Decision intelligence platforms (Aera Technology, the Gartner Magic Quadrant for Decision Intelligence Platforms) | The product is now framed as a "Decision Intelligence core" (01 §1). Buyers will compare it with the vendors that category list names. Aera's Oct 2026 Policy Studio and Decision Ledger are the nearest analogue to our guardrails and journal. |
| §7.5 Positioning of Recover, at summary level | 01 §1. |
| New rows in §6 (strengths and weaknesses) and §7 (matrix, table stakes, "what nobody else does", "what to copy"), and segment lines in §8 (the window) | These sections now cover the five segments and Compose. |

**Updated**

| What | Why |
|---|---|
| "Us" in Scope and method now means Recover with Compose, Decide and Understand (01 §2), and says what the POC has today | The target changed. The honest gaps changed with it: three of the five packs do not exist yet, and nothing in the brief describes a volume-percentage rollout. |
| Summary rewritten (eight points instead of six) | New segments, new threats (Aera, ACV MAX Recommendations) and the Compose comparison. |
| §1.1 Camunda 8.10 release date added: 13 Oct 2026 [S57] | Answered in V-verification.md (claim 2). The open question is removed from "Unconfirmed". |
| §1.9 "Us" row: 131 actions instead of 125 | V-verification.md claim 16 counted 131 actions in the catalogue. |
| §1.4 Appian and §1.5 ServiceNow: app generation from a description (Composer GA 12 Nov 2025; Build Agent update 6 May 2026) | New facts that matter for Compose. Details are in §5.1. |
| §2.2 Blue Yonder: AI-native Order Management launched 5 Nov 2026, with returns linked to each order [S56]. Still no named returns agent and no GA date for the Aug 2026 returns features | A refresh check. The verification correction ("announced", not "shipped") is kept. |
| §3.1 Pattern line: CarGurus has wound down the transaction side of its CarOffer wholesale business [S37] (moved to §4.2) | A 2025–2026 change in the used-car wholesale landscape. |
| Old §4 (strengths and weaknesses) is now §6, old §5 (positioning) is §7, and old §6 (the window) is §8 | The new segment and Compose sections come before the comparison. No other report cites these section numbers. |

**Deleted**

| What | Why |
|---|---|
| The open question "exact GA date of Camunda 8.10" | V-verification.md answered it (13 Oct 2026). |
| "Template-pack gallery (industrial, tool fleet, device)" in "what to copy" | Replaced by the five-segment pack gallery with a locked compliance layer (§7.4). |
| Resolve and Reconcile removed (parked as out of scope, user decision 25 Nov 2026). | The product is Recover only. |

No verified fact from revision 1 was removed. The verification correction on Blue Yonder (§8) is kept word for word.

## Summary

1. **Horizontal agent orchestrators** (Camunda, UiPath Maestro, Pega, Appian, ServiceNow, Microsoft, Workato, n8n)
   all mix a deterministic flow, an LLM agent with a governed tool set, and human tasks. None ships returns or
   circularity content: no asset valuers, no disposition routes, no canonical asset model. They are the "how", not
   the "what". Camunda remains the best pattern source for the agent run view [S1–S3].
2. **Compose has many look-alikes on the "describe it" step and none on what follows it.** Appian Composer (GA
   Nov 2025), ServiceNow Build Agent, Power Apps Plans, UiPath Autopilot for Maestro (GA Dec 2025), Camunda BPMN
   Copilot (alpha), Pega Blueprint and Manhattan Agent Foundry all turn a description into a plan, an app or a
   diagram, with a person reviewing before build [S11, S17, S49–S53]. We found none that does all of these:
   - matches an industry pack whose compliance guardrails the customer cannot weaken;
   - proposes adapter field mappings with a confidence score and a reason;
   - sets autonomy per agent with a confidence threshold;
   - replays past items through the draft before publish;
   - publishes to one region at a volume percentage.
3. **New horizontal threat: Aera Technology.** It is a Leader in Gartner's first Magic Quadrant for Decision
   Intelligence Platforms (26 Jan 2026) [S54]. At AeraHUB 26 (late Oct 2026) it announced:
   - **Skill Building**: a decision automation built from a prompt;
   - **Policy Studio**: rules drafted from a policy document or plain words, approved by a person, tested against
     live decisions before enforcement, with outcomes block / require approval / warn;
   - **Decision Ledger**: a record of every decision, including decisions made on other platforms.

   Availability was not stated [S54]. It has no returns content, but it says the same things we say.
4. **Suite vendors** (Manhattan, Blue Yonder, SAP, Oracle, IFS) ship agents on their own data layer. Blue Yonder is
   still the only one with returns-specific agentic features (announced Aug 2026), and it targets retail [S18].
5. **Used cars: the window is already closed for the dealer-side channel call.**
   - ACV MAX Recommendations (launched 19 Mar 2026) gives each VIN a "retail, wholesale, or adjust pricing"
     recommendation with its reasoning, a profit-versus-speed trade-off and a predicted outcome [S35].
   - vAuto (Cox Automotive) has group-wide transfer optimisation (Jan 2026) [S32].
   - OPENLANE offers a 30/60/90-day forward value per vehicle [S36].

   Each of the three also runs a wholesale marketplace. The space left for Recover is the lessor/captive
   lease-return decision (title and lien, recall, recon approval, named lot demand) with maker-checker and replay.
   We found no product that does that (**unconfirmed**).
6. **Telecom network equipment: the window is open.** Asset recovery here is a managed service (TXO, Comtek,
   Netceed, Carritech) or an OEM take-back programme (Nokia, Ericsson) [S40, S41]. Network inventory vendors are
   adding agents for reconciliation, not disposition (Blue Planet, 2026) [S42]. We found no software that decides
   redeploy / spare / broker / harvest / recycle against open site demand with export and wipe guardrails.
7. **Medical rental equipment: the window is open, with a fast adjacent mover.** TRIMEDX-AIQ (launched Dec 2025)
   added predictive failure and supply-chain automation (Feb 2026) and a technician agent (May 2026) [S45].
   ServiceNow pushes AI agents into healthcare operations (Feb 2026) [S46]. Neither routes a returned rental device
   to the next hospital on certification, decontamination and demand. CMMS, RTLS and rental systems are **sources**.
8. **What still nobody combines:**
   - one engine and seven stages across five asset segments, with every route valued against named demand;
   - locked compliance guardrails plus a customer layer whose compliance-skipping diversions are blocked;
   - maker-checker, replay before publish and a percentage rollout;
   - agents that structurally cannot approve;
   - a vendor-neutral fabric with a conflict queue;
   - self-hosted in the client's tenancy.

   The sharper risk is still a horizontal platform plus a systems integrator's template, now joined by Aera.

## Scope and method

- Date of research: 24 Nov 2026. Web pages read on that date unless a source gives its own date. Searches used
  generic terms and competitor names only.
- Revision 1 read the team-shared pages first (Camunda, Manhattan Agent Foundry, ReverseLogix, Loop, Blue Yonder),
  then searched by vendor and topic. Revision 2 searched per segment (used-car remarketing, recon, auction pricing,
  dealer inventory; telecom asset recovery, network inventory, spares planning; medical rental, CMMS, RTLS) and for
  prompt-to-app generation in orchestration and low-code platforms.
- "Us" means **Recover** as specified in 01:
  - **Compose**: business flow → adapter mapping → agent mapping with per-agent autonomy → approve (maker-checker)
    → publish to one region at 20%, which generates the run-time screens **Decide** (Pulse, Cases, Exceptions) and
    **Understand** (Analytics, Agents);
  - industry packs with locked compliance guardrails and a customer layer;
  - one engine with seven stages;
  - runs in the client's tenancy and reuses the client's adapters.

  It also means what the POC has today (brief):
  - the Connection Fabric (21 system types, canonical model, held records, conflict queue);
  - the Modeler (gate rules, business rules, guardrails, simulation, maker-checker, shadow, rollback, pilot mode);
  - one action pipeline with a forbidden list for agents;
  - a journal with provenance;
  - self-hosted Docker Compose and a trial package.
- Honest gaps on our side:
  - no LLM reasoning loop yet;
  - every connector is a mock;
  - the industrial, tool-fleet and device packs exist, but the **used-car, telecom and medical packs do not**;
  - a volume-percentage rollout is not described in the brief (shadow and pilot mode are);
  - no BPMN/DMN standard, no SaaS, no security attestation, no consumer return portal.

---

## 1. Agentic orchestration and BPA platforms

### 1.1 Camunda 8 (closest architectural peer)

- **What it does.** Process orchestration on BPMN/DMN. Components [S5]:
  - Modeler;
  - Zeebe engine;
  - Operate (monitoring, incidents, audit);
  - Tasklist (human tasks);
  - Optimize (bottleneck dashboards);
  - Connectors and Hub;
  - Identity (RBAC, SSO, SCIM).
- **Agent capability.**
  - The AI Agent connector runs an LLM loop inside the engine, as an AI Agent Sub-process (recommended) or an AI
    Agent Task. Providers include Anthropic, Amazon Bedrock, Google Gemini and OpenAI [S2].
  - The **ad-hoc sub-process is the tool set**: each element inside it is a tool. Tools may run in any order, many
    times, in parallel, or not at all. Camunda calls it "a governed toolbox" [S2]. The LLM picks the tool and its
    parameters; Camunda runs the activity with retries, incidents, variables and human tasks [S1, S2].
  - An MCP Client connector (tools from MCP servers), a vector database connector and an ad-hoc tools schema
    resolver [S2]. Shipped with 8.8 (Oct 2025) [S9].
  - 8.9 (14 Apr 2026) added [S6]:
    - an Orchestration Cluster MCP Server (cluster operations for coding assistants, same authorisation as the REST
      API);
    - three A2A connectors, with A2A agents usable as tools;
    - BPMN conditional events that react to agent outputs;
    - relational databases (including PostgreSQL) as secondary storage;
    - a central audit log.
  - 8.10 (minor release **13 Oct 2026** [S57]) added the **Operate agent view** [S3]. It shows:
    - the agent instance key;
    - its state (Thinking, Tool calling, Idle, Completed);
    - the model and the system prompt;
    - the resolved tools;
    - token use, tool-call count and model-call count against the configured limit;
    - the conversation grouped by loop iteration, with each tool call's input and output;
    - thinking content when the model returns it.

    8.10-alpha3 (29 Jul 2026) also previewed an Agent Instance API (so LangGraph/CrewAI agents get the same view),
    runtime DMN version selection by FEEL expression, and physical tenants [S7].
  - "External agents" (LangGraph, Bedrock, custom) are supported, but Camunda shows only what they report [S2].
  - BPMN Copilot (early access, alpha) drafts a diagram from a description; see §5.1 [S53].
- **Rules/BPMN.** BPMN 2.0 and DMN are native; processes stay portable as standard BPMN [S5].
- **How it mixes the three.**
  - Deterministic BPMN "from the outside": a mandatory fraud check, approval before disbursement, timers.
  - Deterministic BPMN "from the inside": BPMN controls which tools the agent may call, and some tools route to a
    human review.
  - Autonomy can be raised or lowered per tool by changing the model, not the agent [S4].
- **Connectors.** Prebuilt for ERP, CRM, ITSM and LLM providers over MCP, A2A and REST [S5]. Generic, not
  returns-specific.
- **Deployment.** SaaS (99.9% on Advanced clusters, cross-region DR) and Self-Managed [S5].
- **Licence and pricing.** Prices are not published ("Talk to sales") [S5]. Source code is under the Camunda
  License 1.0 (source-available). Since 8.6, Self-Managed needs a paid licence key for production; the free edition
  is non-production only [S8]. **Flag for Legal:** source-available, not OSI open source; no redistribution in a
  customer trial package without a commercial agreement.
- **Strengths vs us.** A mature engine; standards (BPMN/DMN); process versioning and instance migration; a polished
  agent run view; MCP and A2A both ways; a large partner ecosystem; SaaS and self-managed.
- **Weaknesses vs us.**
  - No decision content (valuers, routes, carbon, canonical asset model): a customer must build all of it.
  - Guardrails are what you model, not a built-in forbidden list.
  - No canonical data checks or conflict queue across sources.
  - Self-managed is a heavy stack and paid in production.
  - Rule changes are DMN deployments. We found no maker-checker, shadow mode or back-test over history for rules
    (**unconfirmed**).
- **Their own framing helps our pitch.** Camunda's 2026 report (a vendor survey) [S4]: 71% of organisations use AI
  agents, but only 11% of agentic use cases reached production, and 85% say they lack process maturity.

### 1.2 UiPath Maestro

- **What it does.** "Business orchestration" over UiPath robots, third-party agents, enterprise systems and
  people [S10]. It has:
  - three canvases: Case, Flow and BPMN 2.0 (extended with UiPath task types);
  - DMN decision tables;
  - live instance management, routing, exception handling and SLA tracking [S10].
- **Mix.** Agents reason, robots execute and people direct, with human-in-the-loop steps where a person must
  decide [S10]. The Case canvas lets the path evolve as information arrives (closest to our case model).
- **Autopilot for Maestro** (GA for developers, Dec 2025) generates BPMN from a description; see §5.1 [S52].
- **Connectors.** UiPath Integration Service, plus RPA for systems without APIs (count **unconfirmed**).
- **Deployment.** Automation Cloud and Automation Suite (self-hosted); the docs exist for both [S10].
- **Pricing signal.** Not checked. UiPath sells platform and agent units by contract (**unconfirmed**).
- **Strengths.** RPA reaches systems with no API (useful for legacy WMS/ERP screens); case management; DMN.
- **Weaknesses vs us.** Generic; its value depends on the UiPath estate; no returns content; agents are governed by
  process design, not by a hard forbidden list.

### 1.3 Pega (Agentic Process Fabric, Blueprint, Infinity '25)

- **What it does.** A case management and decisioning platform.
  - Agentic Process Fabric, announced 2 Jun 2025, coordinates agents, apps, systems and data [S11].
  - Infinity '25 (GA 24 Sep 2025) has workflows "composed of both agentic and deterministic steps", runtime agents
    that find and execute the right workflow step, and MCP and A2A support [S11].
- **Blueprint.** An AI workflow designer. It analyses legacy assets and drafts case types, personas, data and
  integrations; it is offered free as the entry point [S11]. Pega's message is "predictable AI": agents run inside
  governed case types [S11].
- **Champion-challenger.** Pega decisioning has long split traffic between a champion and challenger strategies by
  percentage. A challenger model gets a small share of cases, raised gradually. Simulations run a challenger strategy
  against the same population before production [S55]. This is the nearest established pattern to Compose's "one
  region at 20%", but it applies to decision strategies, not to generated flows.
- **Deployment.** Pega Cloud first; client-managed timing for the agentic features is **unconfirmed** [S11].
- **Pricing signal.** Blueprint is free; the platform is sold by contract.
- **Strengths.** The strongest case management and next-best-action decisioning. The "free design tool as lead
  generator" motion is clever.
- **Weaknesses vs us.** Heavy, expensive, long implementations; no reverse-logistics content; a Pega estate is
  itself a lock-in.

### 1.4 Appian

- **What it does.** A low-code process platform with a data fabric.
  - Agent Studio GA Nov 2025; agents can call other agents as tools.
  - MCP adopted (28 Apr 2026) both ways: Appian agents call external systems, and an Appian MCP server exposes the
    data fabric, process models and expression rules to outside agents.
  - Snowflake partnership [S12].
- **Composer** (GA 12 Nov 2025) builds an application plan from requirements; see §5.1 [S49].
- **Mix.** Agents are steps inside Appian process models; rules are Appian expression rules and decisions.
- **Deployment.** Appian Cloud and self-managed (**unconfirmed** for agent features).
- **Strengths.** A data fabric with a unified metadata model (the nearest analogue to our canonical model); a
  regulated-industry footprint.
- **Weaknesses vs us.** Generic. Several April 2026 items were announced as future releases [S12].

### 1.5 ServiceNow (AI Agent Orchestrator, AI Control Tower, AI Agent Fabric, Build Agent)

- **What it does.** A workflow platform (ITSM, CSM, FSM).
  - AI Agent Orchestrator coordinates agents.
  - AI Control Tower (expanded 5 May 2026) discovers, observes, governs, secures and measures AI, including agents
    built on other platforms such as Copilot Studio. It can stop an agent that exceeds its permissions (a "kill
    switch") [S13].
  - AI Agent Fabric carries agent-to-agent and agent-to-tool traffic over A2A and MCP; Workflow Data Fabric is the
    data layer [S13]. The release timing of Agent Fabric differs between sources (**unconfirmed**).
- **Build Agent.** It turns plain language into applications and metadata. Since 6 May 2026 it works inside the
  major AI coding tools, and App Engine Management Center (governance of apps before deployment) is free to all
  customers; see §5.1 [S50].
- **Healthcare.** Healthcare Operations was launched at ViVE (Feb 2026), and there is a clinical device management
  product; see §4.4 [S46].
- **Mix.** Agents act inside ServiceNow flows and playbooks; approvals and tasks are native.
- **Deployment.** SaaS (ServiceNow cloud).
- **Strengths.** Governance across vendors' agents. Its field service, asset (EAM) and clinical device footprint
  makes it a plausible home for industrial service returns and hospital equipment.
- **Weaknesses vs us.** Expensive per-seat/per-assist licensing (**unconfirmed** numbers); no disposition logic.

### 1.6 Microsoft Power Automate, Copilot Studio and Power Apps

- **What it does.**
  - Agent flows in Copilot Studio are deterministic flows that agents call as tools; a flow can pause for approval
    in Outlook or Teams [S14].
  - "Request for information" (preview since Nov 2025) pauses a flow to collect input from a named reviewer and
    uses it in later steps [S14].
  - Advanced (multi-stage) approvals are in preview.
- **Power Apps Plans** draft a solution from a described business problem; see §5.1 [S51].
- **Connectors.** The Power Platform connector library (very large; Dynamics 365 native).
- **Deployment.** Microsoft cloud only.
- **Pricing signal.** Copilot Credits: $200 per pack of 25,000 credits per month, or pay-as-you-go at $0.01 per
  credit. Unused credits do not roll over [S14].
- **Strengths.** Already licensed in most enterprises; approvals in Teams/Outlook, where people already are.
- **Weaknesses vs us.** Citizen-developer sprawl; no domain content; governance is per tenant, not per decision.

### 1.7 Workato (Agent Studio, Genies, Enterprise MCP)

- **What it does.** An iPaaS.
  - Agent Studio builds "genies" (agents) from skills. Genies are MCP clients of hosted and external MCP servers
    (Jan 2026) [S15].
  - Enterprise MCP turns API collections and recipes into MCP servers, with an MCP registry, SSO, RBAC and audit
    trails. The Aug 2026 update added multiple clients per genie [S15].
- **Recipes.** Workflow recipes, API recipes, skills and data-pipeline recipes [S15].
- **Common data model.** A shared, editable schema used by several connectors, so integrations survive when an
  application is added or swapped [S15]. The closest commercial match to our canonical model.
- **Deployment.** SaaS (US, EU, AU, SG, JP data centres) [S15]; an on-prem agent for private systems.
- **Pricing signal.** Genies only on specific plans; no public prices [S15].
- **Strengths.** Connector breadth, recipe reuse, governed MCP exposure.
- **Weaknesses vs us.** Integration first, decision second; no case, no disposition, no maker-checker on business
  policy.

### 1.8 n8n

- **What it does.** Node-based workflow automation with an AI Agent node.
  - Human-in-the-loop per tool: the workflow pauses and asks in Slack, Telegram or chat. Approved calls run with the
    agent's input; denied calls are cancelled and the agent is told [S16]. A community post ties the feature to
    v2.6 (**unconfirmed**).
  - A community report on 2.10.4 says the result does not return to the agent when approval comes from an external
    channel [S16].
- **Builder UX.** Input and output panels per node. Data pinning reuses a node's output in test runs and can be
  edited as JSON. "Debug in editor" copies a failed past execution's data into the editor [S16].
- **Deployment.** Cloud and self-hosted.
- **Licence.** Sustainable Use License (fair-code, not OSI). Files with `.ee.` in the name are under the n8n
  Enterprise License. Charging users for a service that relies significantly on n8n needs a commercial
  agreement [S16]. A forum figure of about $50k/year for Embed is **unconfirmed**. **Flag for Legal:** we cannot
  ship n8n inside our trial package without an agreement.
- **Strengths.** The best builder feedback loop on the market; a huge community template library.
- **Weaknesses vs us.** No case model, no governance beyond per-tool approval, and the licence blocks embedding.

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
| Aera | Skills (decision automations), Policy Studio rules | Agentic reasoning inside skills | Approve on policy hit | Policy outcomes block / require approval / warn (announced Oct 2026) [S54] |
| **Us (Recover)** | Action pipeline (131 actions, 12 steps), decision flows with gate and business rules, Workflow Studio | Agent registry; six stage agents per pack (01 §3); playbook runtime (LLM loop not built) | Proposals held for a person; approvals with delegation; Decide · Exceptions by role | Forbidden list in code (never approve, publish, override, decline, change access); autonomy per agent (Recommend only / Act within limits / Act alone) with a confidence threshold (01 §2); per-agent allow-lists and run limits |

---

## 2. Supply-chain suites with agents

### 2.1 Manhattan Associates (Agent Foundry)

- **What.** A no-code agent builder on the Manhattan Active data layer, with three ways to build [S17]:
  - describe the job in plain language and get a proposed agent structure;
  - start from a template (Labor, Wave, Store, CSR agents);
  - build from scratch with a visual builder, prompt templates, conditions and direct API access.

  Lifecycle: create, version, test, deploy, publish, retire. Guardrails, permissions and human approvals are built
  in [S17].
- **Timeline.** [S17]
  - Launched at Momentum (May 2025).
  - Agents commercially available 8 Jan 2026 (Interactive and Autonomous agents, MCP and A2A compatible).
  - Apr 2026 added Store Associate, Contact Center and OMS Configuration agents.
  - Momentum 2026 added a Marketplace for agents and accelerators.
- **Returns.** No returns-specific agent on the Foundry page [S17]. Manhattan Active Omni handles returns, so a
  customer could build one (**unconfirmed** that any exists).
- **Pricing signal.** Agent Foundry is "included with all Manhattan Active solutions" [S17].
- **Deployment.** SaaS (Manhattan Active).
- **Strengths.** An excellent pitch flow ("describe the job, get the agent") that mirrors Compose; WMS/TMS depth.
- **Weaknesses vs us.** Agents act only on Manhattan data and APIs; no circularity or asset valuation; useful only
  to Manhattan customers.

### 2.2 Blue Yonder (Returns Management, Optoro, Cognitive Solutions)

- **What.** Returns Management with a Smart Disposition engine that combines business rules and ML to route each
  return to store, DC or recommerce [S18, 9 Jan 2026]. It also has:
  - ML resale-value prediction by location;
  - bulk receipt and sorting;
  - recommerce and liquidation workflows;
  - refund rules per shopper.

  Blue Yonder bought Optoro (closed 19 Aug 2025) [S18]. The 2026.1 release brings Optoro into one returns
  portfolio (**unconfirmed** detail) [S56].
- **Agentic (26–27 Aug 2026).** A Cognitive Solutions update covering returns [S18]:
  - customer-specific policies;
  - receipt controls;
  - disposition settings;
  - **test-and-grade workflows**;
  - **unit-level simulation of disposition outcomes**;
  - per-item next-step recommendations;
  - returns projections inside allocation and replenishment.

  Vendor claim: returned goods back to sellable about 25% faster [S18]. No named returns agent [S18].
- **5 Nov 2026.** An AI-native Order Management solution that links inventory, fulfilment, customer service and
  returns around each order; cloud-native and modular [S56]. Still no named returns agent, and no GA date for the
  Aug 2026 returns features.
- **Platform.** "AI agents on the Blue Yonder Platform" monitor the network, with Orchestrator as the interaction
  layer. MCP is not mentioned on the home page [S18].
- **Deployment.** SaaS.
- **Strengths.** The most direct functional overlap with our disposition engine, at retail scale, with Optoro's
  returns data.
- **Weaknesses vs us.** Retail/B2C first. No B2B industrial assets, leases, RUL, PLM or IoT operating hours.
  Disposition lives inside the Blue Yonder estate. Carbon is a separate sustainability product (**unconfirmed**
  link to disposition).

### 2.3 SAP

- **What.** Sapphire (14 May 2026) announced Autonomous Supply Chain Management [S19]:
  - Joule Assistants (Asset and Service, Business Network, Logistics, Manufacturing, Planning, Product Design);
  - "more than 60" supply-chain agents (e.g. Asset Performance Alert Processing, Technician Briefing), GA "phased
    throughout 2026";
  - a new SAP Field Service and Asset Management solution.
- **Returns and circularity.** The May 2026 announcement has no returns, refurbishment or circularity agent [S19].
  Existing pieces [S19]:
  - SAP Intelligent Returns Management (AI in the return process);
  - a reprocessing template for repair, refurbishment and remanufacturing, triggered by maintenance, a customer
    request, a sales order or IoT (blog, date **unconfirmed**);
  - Sustainability Footprint Management and Green Ledger for carbon;
  - partner apps for second-life workflows via SAP Commerce.

  SAP Signavio also offers text-to-process modelling [S53].
- **Deployment.** SAP cloud (BTP, Cloud ERP) and private editions.
- **Strengths.** It owns the ERP record our instructions land in, and it has every building block (returns, EWM
  inspection, footprint, asset management).
- **Weaknesses vs us.** The blocks are not assembled into a cross-route decision; anything non-SAP is second class.
- **Watch.** SAP is the single most credible "window closer" for industrial circularity: the asset-service
  assistant plus reprocessing plus footprint is one product decision away from our story.

### 2.4 Oracle

- **What.** [S20]
  - 10 Feb 2026: SCM agents built with AI Agent Studio (Planning Cycle, Inventory Tasking, Product Configuration,
    PO-to-SO Converter, Service Parts Advisor). One agent recommends returns or transfers for ageing stock and
    executes the chosen action.
  - The solution brief: 100+ agents in Fusion Cloud SCM at no added licence cost.
  - 29 Jun 2026: four Fusion Agentic Applications, built on teams of agents.
- **Returns.** No packaged RMA or disposition agent found (**unconfirmed**); customers can build one in AI Agent
  Studio [S20].
- **Strengths.** "No added cost" agents set a price anchor buyers will quote back to us.
- **Weaknesses vs us.** Oracle-only data; no circularity routing.

### 2.5 Adjacent: IFS, Syncron and PTC Servigistics (industrial service, service parts)

- **IFS.** IFS Cloud 25R2 (27 Nov 2025) introduced agentic Digital Workers across ERP, EAM and FSM. IFS Loops Agent
  Studio (23 Apr 2026) configures and governs them, with built-in guardrails and outcome metrics [S21]. No
  returns/repair Digital Worker found. IFS owns many industrial asset and service-repair processes, so it is an
  adjacent threat for the tool-fleet AMS pack.
- **Syncron.** Aftermarket (service parts, pricing, warranty). 2026 news [S22]:
  - a field-data partnership for warranty decisions (29 May);
  - enterprise data platform integrations (30 Jun);
  - Service Contract Performance (7 Oct).

  No agentic disposition found. A possible partner rather than a rival.
- **PTC Servigistics.** A service parts planning tool. An AI Assistant for planners (GA Oct 2025 per PTC's 2025
  release). A 2026 PTC blog describes an agent that turns a business request into planning scenarios and runs the
  planning engines, with "defined limits" on its authority and human review points [S43]. It is a **source** for
  the telecom pack's spares-planning system (01 §7).

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

Others seen but not researched in depth (**unconfirmed** detail):

- AfterShip Returns, ZigZag, ReBound, Two Boxes (B2C returns);
- B-Stock and Liquidity Services (liquidation marketplaces);
- DHL's returns network with an in-house re-SKU tool [S29].

A large US retailer runs its own algorithm that decides resell, donate, recycle or liquidate per item every day; a
footwear brand runs a rules engine it can change itself [S29]. Retailers building in-house are competitors too.

**Pattern.** Retail returns AI concentrates on three things: fraud, return forecasting and decision support [S29].
An NRF/Happy Returns survey: 85% of merchants use AI/ML for returns fraud, but only 45% think it works well
alone [S29]. That supports our "humans approve, agents plan" stance.

### 3.2 ITAD and device recommerce software

- **Diagnostics, grading and erasure.** [S30]
  - Phonecheck: IMEI checks for blacklist, finance, carrier lock, MDM and iCloud; 80-point diagnostics; a device
    history report.
  - Blancco: 75+ diagnostic tests, certified erasure, mobile buy-back with real-time pricing; a kiosk grading
    station trial in Japan.
  - One overview groups Blancco, Phonecheck, NSYS and BlackBelt as diagnostics plus certified erasure, and Apkudo
    and FutureDial as automation, AI testing and cosmetic grading.
- **Recommerce integration layer.** Device Network integrates BlackBelt, Phonecheck, NSYS, Blancco, FutureDial and
  others for trade-in [S30].
- **ERPs for ITAD and refurbishers.** [S31]
  - Makor ERP: sales, CRM, financials, inventory; data wipe and destruction reporting; chain of custody.
  - RazorERP: cloud ERP for e-waste, ITAD and brokers; multichannel sync.
- **Market size signal.** US mobile trade-in payouts were $1.63bn in Q1 2026 and $1.43bn in Q2 2026 (a
  device-protection provider's quarterly data, secondary) [S30].
- **Implication.** For the device recommerce pack (01 §5) these tools are **sources**, not rivals. We read the
  grade, the data-wipe certificate and the blacklist/lock status, and decide the channel (Buy Now, Offers, Auction,
  wholesale lot). We found no ITAD vendor offering a cross-route decision with value, risk and carbon. Pricing
  engines exist inside trade-in programmes (**unconfirmed** depth).

---

## 4. Competitors per Recover segment

Reading guide for every table:

- **Rival**: it makes the same decision as Recover for the same buyer.
- **Source**: Recover reads its output (01 §6–8 "Systems").
- **Both**: it decides part of the chain and also holds data we need.

Announced vs shipped is given where the source says so.

### 4.1 Tool fleet AMS and device recommerce (pointers)

- **Tool fleet AMS** (01 §4). Adjacent suites are covered in §2.5: IFS (EAM/FSM, Digital Workers), Syncron (parts,
  warranty, contracts) and PTC Servigistics (service parts). SAP is the window closer (§2.3). No vendor found that
  plans the whole return queue against named renewals, pool shortages and open repair orders.
- **Device recommerce** (01 §5). Diagnostics, erasure and trade-in tools are covered in §3.2 (sources). Returns
  platforms are covered in §3.1 (rivals for retail). The channel and ageing decision (Offers → Auction after 14
  days) exists inside marketplace and trade-in programmes, depth **unconfirmed**.

### 4.2 Used cars (lease-end and trade-in remarketing)

Recover's decision (01 §6): title and lien → inspect and estimate recon → price by channel → retail lot (which lot)
/ wholesale auction / dealer trade / salvage. Guardrails: clear title, no retail with an open recall, recon over a
limit → used-car manager.

| Who | What they decide | AI / agentic features (dated) | Rival or source | Gaps vs Recover |
|---|---|---|---|---|
| **Cox Automotive** (vAuto, Manheim, Dealertrack, VinSolutions, iRecon) | Dealer appraisal, pricing and stocking (vAuto); wholesale auction (Manheim); recon workflow (iRecon) | NADA 2026 press release (30 Jan 2026): vAuto "enhanced pricing science", **"group-wide transfer optimization"** and "next-gen appraisal intelligence"; Manheim physical and digital unified, with AI features; a joint AI inspection offering with UVeye (go-to-market date not given) [S32]. VinSolutions' next-generation Virtual Assistant is "an agentic AI solution" that handles sales, acquisition and Instant Cash Offer leads by text and email and hands off to staff (press release 28 Jan 2026; availability date not given) [S33]. vAuto uses AI to estimate recon cost [S38]. | **Both.** Rival for the dealer-side "which lot / retail or wholesale" call. Source for the pricing guide, the auction platform and the DMS (01 §6 systems). | Dealer-centred, not lessor-centred; no title/lien or recall guardrail as a locked control (**unconfirmed**); owns the auction it may recommend; no maker-checker or replay of a policy change found |
| **ACV** (ACV Auctions, ACV MAX, ClearCar, True360) | Per-VIN **retail vs wholesale vs reprice**; trade-in offers | ACV MAX Recommendations, **launched 19 Mar 2026**: a side panel with per-VIN pricing advice, the reasoning (key data signals), a **profit-vs-speed trade-off**, predicted outcomes, and "recommendations to retail, wholesale, or adjust pricing strategy for each unit" [S35]. VIPER AI inspection towers with a Virtual Lift, demonstrated at NADA (2 Feb 2026) [S34]. An all-in-one MAX inventory suite with automated imaging, VIN-level pricing and AI condition analysis (7 May 2026) [S35]. ClearCar pricing powers a third-party AI trade-in agent (trade press, Sep 2026, **unconfirmed** date) [S35]. | **Rival** for the channel decision at dealers; **source** for condition and auction prices | Advises; no approval routing, guardrails or diversions; dealer inventory only, not lease returns before grounding; also sells the wholesale channel |
| **OPENLANE** (formerly KAR) | Wholesale marketplace, incl. off-lease and commercial consignors | "OPENLANE Intelligence" umbrella (20 Jan 2026): AI exterior damage detection, OBD2 scan data in colour codes, AI engine-audio anomaly detection; pricing named then as near-term work [S36]. By the Q1 2026 call (5 May 2026) predictive pricing gives a **30/60/90-day forward value** for every dealer vehicle [S36]. Visual Boost AI highlights damage on condition-report photos (date **unconfirmed**) [S36]. Management says off-lease volumes are growing through 2026 [S36]. | **Source** (auction platform, condition reports, prices); a partial **rival** for lessors' upstream channel choice | No cross-channel decision with recon cost, lot demand and title guardrails found; marketplace-centred |
| **CarGurus** (CarOffer) | Was a digital wholesale trade platform | The transaction side of CarOffer has been wound down (end of 2025 per one source); CarGurus now sells dealer software and data, e.g. PriceVantage (2026) [S37] | Neither now (pricing data at most) | Shows that running wholesale transactions is hard; the field consolidates around Cox, ACV and OPENLANE |
| **Recon workflow tools**: Rapid Recon (Vehlo), iRecon (vAuto), Repair360 (Repairify), others | Track each recon step and its time and cost | Rapid Recon added an AI layer that cuts assessment "from days to hours" (vendor, NADA 2026) [S38]. Repair360 has a workflow module from trade-in evaluation to touch-up paint (Feb 2026) [S38]. | **Source** (recon estimate and status; 01 §6 "legacy body-shop system") | They track recon; they do not decide whether recon is worth it against auction net of fees |
| **Inspection AI**: UVeye, ACV VIPER, OPENLANE condition reports | Condition and damage | Shipped in 2025–2026 (see above) [S32, S34, S36] | **Source** (inspection app) | Condition only |
| **Valuation guides and lessor remarketing services**: J.D. Power, auction houses' remarketing desks | Residual and wholesale values; managed remarketing | J.D. Power Remarketing Solutions offers managed remarketing (page read; no AI claim checked) [S38] | **Source** (pricing guide); services compete with a lessor's in-house desk | Not researched in depth (**unconfirmed**) |

**Read-out.**

- Recommending per-VIN retail vs wholesale with reasoning has **shipped** (ACV MAX, Mar 2026). So has group-wide
  lot transfer (vAuto, Jan 2026). Recover must not pitch the channel call itself as new to dealers.
- Our angle is the **lessor or captive return flow**:
  - title and lien and the recall check as locked compliance guardrails;
  - recon approval thresholds;
  - "send each retail-ready car to the lot where it sells fastest";
  - EV battery-health diversions;
  - replay of a quarter's returns before publish;
  - neutrality: we do not run the auction we recommend.

  We found no product that covers this lessor flow (**unconfirmed**; lessor-internal tools are invisible to web
  search).

### 4.3 Telecom network equipment (decommissioned kit, spares, brokers, export control)

Recover's decision (01 §7): match the unit to the network inventory → configuration wipe and bench test → value
redeploy to a site / refurbish as a spare / resell to a broker / harvest boards / recycle. Guardrails: inventory
match, wipe certificate, export-control check before resale, "spares before new".

| Who | What they decide | AI / agentic features (dated) | Rival or source | Gaps vs Recover |
|---|---|---|---|---|
| **Asset recovery service providers**: TXO, Comtek, Netceed, Carritech (and others) | De-installation, test, repair, refurbish, resale, recycling, spares supply, as a managed service [S41] | None advertised on the pages read [S41]. An Oct 2026 trade article on telecom equipment reuse mentions no AI at all [S39]. | **Rival** to the operator's own decision (they decide and execute for the operator); also **sources** (broker listing, refurbishment order, recycler portal in 01 §7) | Decisions are made by service staff inside the provider; the operator gets reports, not a governed per-unit decision against its own site demand and spares pools |
| **OEM take-back and circular programmes**: Nokia (asset recovery, take-back and buyback, refurbished products), Ericsson (take-back in 180+ countries with secure data destruction) [S40] | Buy back or take back the OEM's own kit; refurbish and resell it | No AI claims found [S40] | A **route** (an outbound channel), and a rival for the "resell" path | Single-vendor; the operator's multi-vendor estate is not theirs to optimise |
| **Network inventory**: Ciena Blue Planet, Netcracker, Ericsson, Nokia | The record of what is installed where | Blue Planet positions its inventory as the foundation for agentic AI, with OSS agents for device reconciliation and equipment modelling, run from Blue Planet AI Studio (2026) [S42]. Configuration and change-management agents with pre-change impact analysis were reported in June 2026 (trade press, **unconfirmed** date) [S42]. Ericsson (Sep 2026) says agents need unified real-time inventory [S42]. Netcracker has an agentic AI framework for OSS (analyst profiles only, **unconfirmed** detail) [S42]. | **Source** (01 §7 "network inventory"; "match to the network inventory" is a pack guardrail) | Reconciliation and change, not disposition; we found no decommission-to-reuse agent (**unconfirmed**) |
| **Spares planning**: PTC Servigistics, Syncron, ERP planning | Spares stock levels per location | Servigistics AI Assistant (GA Oct 2025) and an agent that runs planning scenarios within limits (2026 blog) [S43] | **Source** (spares need per region feeds "spares before new") | Plans spares to buy; does not decide which returned unit fills which pool |
| **Trade compliance screening** (e.g. SAP GTS) | Export classification and licence checks | Not researched (**unconfirmed**) | **Source** for the export-control guardrail | 01 §7 infers the export class from the part number at low confidence; a compliance tool should be the system of record |

**Market signals** (trade article, 13 Oct 2026 [S39]; operators not named here):

- one European operator's wholesale arm targets 10% of eligible capex from refurbished equipment in 2026;
- another operator reports circular material at 14% of network technology procurement (2025);
- a third reused only 1% of its network e-waste in FY2026.

The article says the financial evidence "remains uneven". An industry association paper (Feb 2024) sets a strategy
for circular network equipment [S40].

**Read-out.** No software rival found for the decision itself. The risks are:

- a network inventory vendor adding a "decommission and reuse" agent on top of reconciliation;
- a large asset recovery provider productising its internal decision tooling.

In our judgement both are plausible within 12 months; no announcement was found. Our edge: "spares before new" across regions, firmware and
site-demand matching, locked wipe and export guardrails, and "new spend avoided" as the KPI.

### 4.4 Medical rental equipment (hospital rental fleets, decontamination, service and certification)

Recover's decision (01 §8): device returned → decontamination record verified → functional test and service status
→ re-rent / service then re-rent / refurbish / retire. Guardrails: service and certification in date for the whole
rental, a decontamination record required, retire under 5 years → clinical engineering.

| Who | What they decide | AI / agentic features (dated) | Rival or source | Gaps vs Recover |
|---|---|---|---|---|
| **TRIMEDX** (clinical engineering services, TRIMEDX-AIQ) | Maintenance, repair and replacement planning for hospital-owned medical devices | TRIMEDX-AIQ, "AI-native clinical asset intelligence", launched 15 Dec 2025; expanded with supply-chain automation and predictive failure intelligence (24 Feb 2026); a **technician agent** inside its CMMS answers troubleshooting questions from error codes, location data and past repairs (21 May 2026) [S45] | **Both.** Rival for "retire or repair"; a source for service history where a hospital uses it | Hospital-owned fleets, not rental-fleet routing; no re-rent-to-next-hospital decision found |
| **ServiceNow** (clinical device management, Healthcare Operations) and **Nuvolo** (on ServiceNow, part of Trane Technologies) | Clinical equipment lifecycle, planned maintenance, work orders, contracts and parts; device security | ServiceNow Healthcare Operations with AI agents that triage requests and coordinate handoffs (ViVE, Feb 2026) [S46]. Nuvolo: HTM asset management; 2026 ServiceNow partner award (27 Feb 2026); no dated 2026 AI release found [S46] | **Source** (01 §8 "asset management", "biomedical service system") | Workflow and records; no valued route decision |
| **RTLS vendors**: CenTrak, Kontakt.io, HID Global (and others) | Where each device is, how much it is used, idle units; HID says it can monitor workflows such as sanitising between uses [S47] | Analytics and predictive claims in vendor material (**unconfirmed**) [S47] | **Source** (location, utilisation; possibly cleaning status) | No routing or certification guardrail |
| **Rental management software**: Wynne Systems (RentalResult), EZRentOut, Booqable, MCS and others; HME billing tools for home-care rental [S48] | Bookings, contracts, billing, availability | No AI routing found in the pages read [S48] | **Source** (01 §8 "rental system") | System of record, not decision |
| **OEM fleet services** (e.g. GE HealthCare fleet management) | Service of the OEM's installed base; fleet advice to health systems [S48] | Not researched (**unconfirmed**) | A partial **rival** for advice to hospitals | Single-OEM |
| **Rental fleet operators** themselves | The buyers of this pack. They run their own customer portals that show rental history, maintenance and utilisation | AI-driven predictive maintenance mentioned only by a data aggregator (**unconfirmed**) | Buyers, not rivals; not named here (brief rule) | n/a |

**Read-out.** The nearest mover is TRIMEDX-AIQ, which ships agents for hospital-owned fleets. No product found
routes a returned rental device to the next hospital by least travel while keeping service and certification in
date for the rental, and holds it on a missing decontamination record. The "emergency: skip the decontamination
record → blocked" diversion is a strong demo line. Every system in 01 §8 already exists as a product category, so
the pack is a **read-and-decide** pack: adapter coverage matters more than models.

---

## 5. Compose-like experiences and decision intelligence platforms

### 5.1 "Describe your business → generated flow or app"

| Product | Input | What it generates | Guardrails | Review / maker-checker | Rollout | Status (dated) |
|---|---|---|---|---|---|---|
| **Appian Composer** | Text, images, legacy documents; since Q1 2026 several files at once (spreadsheets, BRDs) | An interactive **plan**: user stories, data, processes and UX; then foundational objects (records, process models, initial interfaces) | Platform security; docs advise reviewing every AI suggestion | Human review of the plan; maker-checker not described | Normal app deployment | GA 12 Nov 2025 (with Agent Studio); 130+ organisations, 1,300+ apps at GA (vendor) [S49] |
| **ServiceNow Build Agent** | Plain-language prompts, multi-turn chat in Studio/IDE and inside major AI coding tools | Applications and metadata, "using the platform's domain language and guardrails"; can modify existing apps | Platform guardrails; App Engine Management Center governs apps before deployment (free to all customers from 6 May 2026) | You review changes before they are built and installed; the docs say it suits standalone apps with limited flow interaction | Normal ServiceNow deployment | Shipped (Zurich docs); update 6 May 2026; trial 100 interactions / 30 days [S50] |
| **Microsoft Power Apps Plans** (plan designer) + generative pages | A described business problem | A plan (user stories, data schema, apps, flows, agents to build), then a solution: Dataverse tables, apps, Power Automate flows, Pages, Power BI | Tenant policies | Maker reviews the plan; no direct link yet from plans to generative pages (FAQ) | Normal environment promotion | Generative pages GA 2 Apr 2026 (US region first); vibe coding of whole model-driven apps GA in the Sep 2026 update [S51] |
| **UiPath Autopilot for Maestro** | A plain-language description or uploaded files (preview) | End-to-end BPMN, streamed onto the canvas element by element | Docs advise reviewing and testing before production | A coding agent (preview) pauses for user approval before building | Normal Maestro deployment | GA for developers, Dec 2025 [S52] |
| **Camunda BPMN Copilot** | A process description | A BPMN diagram (no pools/lanes/collaborations; overwrites existing work) | n/a | Modeller edits by hand | Normal deployment | Early access (alpha) [S53] |
| **SAP Signavio** text-to-process | Text | A process model | n/a | n/a | n/a | Product page [S53]; not researched further |
| **Pega Blueprint** | Legacy assets, descriptions | Case types, personas, data, integrations | Governed case types ("predictable AI") | Human design review | Champion-challenger exists for decision strategies (not for generated apps) [S55] | Free entry tool [S11] |
| **Manhattan Agent Foundry** | "Describe the job" | A proposed agent structure; templates | Guardrails, permissions, human approvals built in | Lifecycle: create, version, test, deploy, publish, retire | Not stated | Agents commercially available 8 Jan 2026 [S17] |
| **Aera Skill Building + Policy Studio + Dynamic UX** | A business prompt; a policy document or a rule in plain words | A decision automation (skill) with a proposed plan; rules; interfaces from prompts, published with the skill | Policy Studio rules **block / require approval / warn**; results in Decision Ledger | A person approves drafted rules; rules **tested against live decisions before enforcement** | Not stated | Announced at AeraHUB 26 NYC (late Oct 2026; press 28 Oct–10 Nov 2026); availability not stated [S54] |

**What Compose does differently** (01 §2). For each claim we say how far the public material supports it.

1. **It starts from an industry pack, not a blank plan.** The configuration agent matches the description to one
   of five packs. It lists the fields, stages, routes, guardrails (stated plus from the pack), systems and KPIs, and
   asks **one** clarifying question. Others generate from the prompt alone or from generic templates (Manhattan
   templates are WMS jobs). No competitor found with returns or asset-disposition packs.
2. **The pack locks compliance guardrails, and there is a customer layer on top.**
   - A customer can tighten a guardrail or add an approver.
   - A customer cannot weaken, suspend or remove a compliance guardrail.
   - A diversion that skips a compliance guardrail is **blocked**.
   - Pack updates never overwrite customer changes.

   Platform guardrails elsewhere are generic (security, permissions). Aera's Policy Studio is the nearest, but its
   rules are customer-written. We found no "vendor-locked, customer-extensible" policy layer (**unconfirmed**).
3. **Adapter mapping is part of the flow.** Fields come with a confidence score and a reason, and five actions
   (accept, choose another, convert, not needed, ask the system owner). Then a test run puts past items through the
   draft. The app generators assume the data sits in the platform's own store (Dataverse, ServiceNow tables, Appian
   data fabric).
4. **Autonomy is set per agent, with a confidence threshold** (65–85%, default 75%). The platform enforces
   guardrails whatever the autonomy. Others set approvals per tool or per process step (n8n, Camunda, Manhattan).
5. **Maker-checker on the composition itself.** The composer cannot approve, and the approver can send back a
   change pinned to a step. ServiceNow's App Engine Management Center and normal ALM pipelines govern deployment;
   none found separates the author and the approver of a *generated business flow* as a product rule
   (**unconfirmed**).
6. **Replay before publish, then one region at 20%.**
   - The replay compares the route mix (actual against flow), straight-through %, approvals and exceptions per day,
     and modelled uplift.
   - Aera tests rules against live decisions before enforcement, the nearest match.
   - Pega's champion-challenger splits traffic by percentage for decision strategies [S55].
   - No app generator found offers a percentage or regional rollout of a generated flow.
7. **Publishing makes the pack's run-time views available from the decision model** (Decide: cases, exceptions,
   suggestions; Understand: analytics, agents). The prototype shows the concept, not a layout. Aera Dynamic UX and Power Apps generative pages generate screens too, but from a prompt per page, not
   from the decision model.

**Honest caveat.** Several of these are target behaviours in 01, not POC features (see Scope). The generators above
are shipped products with large installed bases. The race is on the parts after "describe".

### 5.2 Decision intelligence platforms

- **The category is now formal.** Gartner published its first Magic Quadrant for Decision Intelligence Platforms on
  26 Jan 2026 [S54]. Vendors covered: ACTICO, Aera Technology, CRIF, Decisions, Faculty, FICO, FlexRule, IBM, InRule
  Technology, o9 Solutions, Oracle, Pegasystems, Quantexa, RelationalAI, Rulex, Sapiens and SAS. IBM, SAS and Aera
  each say they are a Leader. The full placement is paywalled (**unconfirmed** beyond those three).
- **Aera Technology.**
  - Agentic reasoning "from situation to action in one conversation", in a governed, auditable environment
    (4 May 2026) [S54].
  - AeraHUB 26 (late Oct 2026) announced six items: Skill Building, Decision Ledger, Policy Studio, Agent
    Interoperability (Copilot Studio, A2A, MCP), Dynamic UX and Command Center. Availability was not stated [S54].
  - Decision Ledger records the context, reasoning, policies checked, actions and outcome of each decision,
    including decisions passed in by API from other platforms [S54].
  - Domain: supply chain (production, shipping, procurement, demand). No returns or circularity content found.
  - A third-party review (4 Nov 2026) says the public material does not establish a reliable economic evaluation of
    decisions [S54]. That is where back-testing with a value uplift (01 §2 step 5) differentiates us.
- **Rule and decision engines** (FICO, IBM, InRule, Sapiens, ACTICO, FlexRule, Pega) offer rule authoring,
  champion-challenger and simulation. None has returns content. They are what a buyer's IT may propose instead of
  Recover's decision flows (**unconfirmed** for each feature per vendor).
- **Implication.** Calling Recover "Decision Intelligence" puts it on the same shortlist as Aera and the rule
  engines. The answer has to be domain depth (packs, valuers, named demand, carbon) plus governance (locked
  guardrails, maker-checker, replay), not "we also do agents".

---

## 6. Strengths and weaknesses against our design

Our pillars:

- **D**: decision-first;
- **F**: vendor-neutral fabric;
- **M**: maker-checker (including on compositions);
- **J**: journal;
- **S**: self-hosted / client tenancy;
- **P**: industry packs with locked guardrails (new).

Reading: Y = has it, P = partly, N = no evidence found, ? = unknown. This is our reading of public pages, not
tested.

| Vendor | D | F | M | J | S | P | Biggest threat to us | Biggest gap vs us |
|---|---|---|---|---|---|---|---|---|
| Camunda | N | P (generic connectors) | P (process versioning, no rule maker-checker found) | Y (audit log, Operate history) | Y (paid in prod) | N | Customer or SI builds a returns solution on it | No domain content |
| UiPath Maestro | N | P (RPA reaches anything) | ? | Y | Y | N | Existing RPA estates; Autopilot drafts BPMN | No domain content |
| Pega | P (decisioning) | P | Y (Pega governance, **unconfirmed** detail) | Y | P | N | Free Blueprint drafts a returns app; champion-challenger | Cost, speed |
| Appian | N | P (data fabric) | ? | Y | P | N | Composer + data fabric + MCP server | No domain content |
| ServiceNow | N | P | P (App Engine Management Center) | Y | N | N | FSM/EAM/clinical customers stay in one platform; Build Agent | No disposition |
| Microsoft | N | P (connectors) | N | P | N | N | Already paid for; Plans generate solutions | Governance per decision |
| Workato | N | Y (common data model) | N | Y | N | N | Integration layer + genies | No case, no decision |
| n8n | N | P | N | P | Y (licence limits) | N | Cheap DIY | Governance, licence |
| **Aera** | Y (supply chain) | P (connectors, API intake) | P (rule approval, **unconfirmed** separation of roles) | Y (Decision Ledger) | ? | N | Same vocabulary: DI, prompt-built skills, plain-language policies, ledger | No returns/asset content; no locked pack guardrails found |
| Manhattan | P | N (Manhattan data) | P | Y | N | P (templates) | Returns agent built in Foundry | Single vendor, no circularity |
| Blue Yonder | Y (retail) | N | ? | Y | N | N | Disposition simulation, ML resale value | Retail only, BY estate |
| SAP | P | N | P | Y | P (private cloud) | N | Assembles its blocks | Non-SAP second class |
| Oracle | P | N | ? | Y | N | N | Free agents anchor price | Oracle only |
| ReverseLogix | P (rules) | P (ERP connectors) | ? | ? | N | N | B2B returns + warranty in one SaaS | Rules, not valued routes; no agents to speak of |
| Loop / Narvar | P (policy) | N (Shopify-centred) | N | ? | N | N | Owns the shopper front door | B2C only |
| ReturnPro | P (AIRE) | N | ? | ? | N | N | Software + returns centres + marketplaces | Captive to its network |
| **Cox (vAuto, Manheim)** | P (pricing, transfers) | N (own data) | ? | ? | N | N | Dealer data and the auction in one company | Dealer-side; no lessor return flow; not neutral |
| **ACV MAX** | Y (per-VIN retail/wholesale/reprice) | N | N | ? | N | N | Shipped explainable channel advice (Mar 2026) | Advice only; no guardrails, approvals, replay |
| **OPENLANE** | P (forward pricing) | N | ? | ? | N | N | Lessor relationships plus pricing | Marketplace-centred |
| **TXO / asset recovery providers** | P (staff decide) | N | ? | P (reports) | N | N | Operator outsources the whole decision | Not a governed per-unit decision for the operator |
| **Blue Planet** (network inventory) | N | P (inventory reconciliation) | ? | Y | ? | N | Adds a decommission-and-reuse agent | No disposition or valuation |
| **TRIMEDX-AIQ** | P (repair/replace) | P (own CMMS data) | ? | Y | N | N | Agents already in biomedical workflows | Hospital-owned fleets; no rental routing |

What we lack that buyers will compare:

- a SaaS option;
- SOC 2 / ISO 27001 (ReverseLogix claims both [S23]);
- real production connectors (ours are mocks);
- three of the five packs;
- a consumer return portal;
- computer-vision grading (we read it, which is fine, but buyers will ask);
- BPMN/DMN portability;
- an LLM agent loop and an agent run view;
- a shipped percentage rollout.

---

## 7. Positioning

### 7.1 Matrix

```
 Orchestration generality (agents + process for any domain)
  high |  Camunda  UiPath  Pega  Appian  ServiceNow             |
       |  Microsoft  Workato  n8n   (+ their app generators)    |   <- target: domain decision
       |          Aera (DI, supply chain)                       |      content on a general,
       |                                   [RECOVER, target] -> |      vendor-neutral platform,
  mid  |  Manhattan Foundry   Oracle Agent Studio               |      five packs, Compose
       |  SAP Joule   IFS Loops   Blue Planet (inventory)       |
       |                      Blue Yonder (retail returns)      |
  low  |  Makor/RazorERP  Blancco/Phonecheck  RTLS  rental SW   |
       |  Narvar Loop Happy Returns ReverseLogix ReturnPro      |
       |  ACV MAX  vAuto/Manheim  OPENLANE  (used cars)         |
       |  TRIMEDX-AIQ  Nuvolo  (medical)   TXO Comtek (telecom) |
       +--------------------------------------------------------+
         none          returns/disposition domain depth            deep
         (vendor-locked suites sit mid-height: general inside their own estate only)
```

Reading:

- The top-left is crowded and well funded, and every player there now has a prompt-to-app generator.
- The bottom-right is crowded with single-segment tools: retail returns SaaS, used-car pricing and auction
  platforms, biomedical CMMS.
- The top-right (general orchestration **and** deep disposition content across segments, vendor-neutral) is empty
  today.
- Aera is moving right on the general axis (decision ledger, policies) but has no disposition depth.
- Blue Yonder is the nearest on depth, but only inside its own retail estate.

### 7.2 Table-stakes features we must have

Horizontal (from revision 1, still valid):

1. **Agent run view**: state, model, prompt, tools offered, every tool call with input and output, tokens and cost
   against limits. Camunda [S3] sets the bar; our LLM loop is not built yet.
2. **Human steps beyond approve/reject**: request for information, delegation, SLA timers and escalation (Microsoft
   RFI [S14], Maestro SLAs [S10]).
3. **Per-tool human approval and limits** for agents (n8n [S16], Camunda [S2]). We have per-agent; add per-tool.
4. **MCP server and client**, A2A on the roadmap. All horizontal players, Manhattan and Aera ship both [S6, S11,
   S12, S13, S17, S54].
5. **Multi-provider LLM with fallback** (Camunda supports Anthropic, Bedrock, Gemini, OpenAI [S2]).
6. **A natural-language builder** that drafts a flow, app or agent from a description. Now everyone has one:
   Appian [S49], ServiceNow [S50], Microsoft [S51], UiPath [S52], Manhattan [S17], Pega [S11], Aera [S54]. Ours
   maps to the nearest topology today. Compose must at least show a reviewable plan and stream the draft onto the
   canvas.
7. **Versioned, testable flows** with draft/publish and instance history (everyone).
8. **Production connectors** to SAP, Oracle, NetSuite, D365, Salesforce, Shopify and carriers (ReverseLogix lists
   exactly these [S23]).
9. **RBAC, SSO, SCIM, audit log, multi-tenancy** (Camunda Identity [S5]). 01 §2 adds directory-group mapping and
   "test a user".
10. **Returns domain basics**: RMA intake, grading capture (read from tools), fraud signals, ML resale value,
    refund/credit rules, analytics (Blue Yonder [S18], ReverseLogix [S23], Loop [S24]).
11. **A SaaS option and security attestations**, even if self-hosted / client tenancy stays our differentiator.
12. **A decision record that accepts decisions made elsewhere** (Aera Decision Ledger via API [S54]). Our journal
    records our own actions only.

Per segment (new):

| Segment | Table stakes a buyer will expect on day one |
|---|---|
| Tool fleet AMS | Read the repair-centre grade and IoT hours; RUL with an explanation; contract terms; service parts availability (Servigistics/Syncron class [S22, S43]) |
| Device recommerce | Read diagnostics, wipe certificate and lock status (Phonecheck, Blancco [S30]); channel fees; price feeds; ageing rules |
| Used cars | VIN-level price with reasoning and a profit-vs-speed view (ACV MAX [S35]); forward value at 30/60/90 days (OPENLANE [S36]); group-wide transfers (vAuto [S32]); recon cost estimate [S38]; AI inspection input (UVeye, VIPER [S32, S34]); DMS, title/lien and recall checks |
| Telecom network equipment | Match to network inventory and reconcile (Blue Planet class [S42]); wipe certificate; firmware level; export classification from a compliance system; spares need per region [S43]; new spend avoided and circularity metrics [S39] |
| Medical rental equipment | Service and certification dates from the CMMS (TRIMEDX, Nuvolo/ServiceNow [S45, S46]); decontamination record; RTLS location and utilisation [S47]; rental bookings [S48]; turnaround and utilisation KPIs |

### 7.3 What nobody does that we do (as far as public material shows)

1. **Decision-first across every route, in five asset segments, on one engine.**
   - Each case values every route against named demand (renewals, pool shortages, open repair orders, buyer bids,
     open site demand, next hospital).
   - The rules applied are explained, with deterministic carbon on every card (today only the industrial template
     computes carbon; V-verification claim 19).
   - Blue Yonder does profit-led disposition for retail [S18]; ACV MAX does per-VIN channel advice for dealers
     [S35]. Nobody found does it across segments, or for B2B assets with carbon on the card.
2. **Industry packs with locked compliance guardrails and a customer layer.** Diversions that skip a compliance
   control are blocked, and pack updates never overwrite customer changes (01 §2). Generators build on generic
   platform guardrails; Aera's Policy Studio rules are customer-written [S54].
3. **Compose's governed path from a sentence to production:** adapter mapping with confidence and reasons → agent
   autonomy with a threshold → maker-checker on the composition → replay → one region at 20%. Each step exists
   somewhere (plans: Appian, Microsoft; review before build: ServiceNow, UiPath; test before enforcement: Aera;
   percentage split: Pega decisioning). None found chains them for a generated business flow.
4. **A vendor-neutral fabric with data governance**: a canonical model with unit/currency/time normalisation,
   canonical checks, held records and a **conflict queue between sources** for a person. Workato's common data
   model is the nearest [S15], without the conflict queue or holds.
5. **Maker-checker, shadow mode and rollback on business rules**, with simulation over historical cases. Camunda
   selects DMN versions at runtime [S7], but we found no maker-checker or shadow mode (**unconfirmed**).
6. **Agents that structurally cannot approve**: a forbidden list enforced in the single write pipeline for every
   agent-prepared call. Others offer configurable guardrails, policies or a kill switch [S13, S54]. None advertises
   a hard-coded "agents never approve, publish, override, decline or change access".
7. **Back-testing with a value uplift as the sales motion**: replay a quarter of the customer's returns and show net
   uplift against what they did. Blue Yonder's unit-level disposition simulation [S18] and Aera's test-before-
   enforcement [S54] are the only near matches. A third party notes Aera lacks a reliable economic evaluation
   [S54].
8. **Self-hosted / in the client's tenancy, Postgres only, trial package in under a week.** Camunda self-managed is
   heavier and paid in production [S8]. The suites, returns SaaS and segment tools are cloud only.
9. **Queue-level planning** (01 §3, agent 6): each order filled once, refurbishment within repair-centre capacity.
   Segment tools recommend per unit (ACV MAX per VIN [S35]); we found none that plans the whole return queue
   against demand (**unconfirmed**).

### 7.4 What to copy

UX patterns:

| Pattern | From | How it maps to us |
|---|---|---|
| Agent instance panel: state badge (Thinking / Tool calling / Idle / Completed), model and system prompt, resolved tools, tokens, model calls and tool calls against limits, conversation grouped by iteration, expand a tool call to see input and output, hover for usage breakdown | Camunda Operate 8.10 [S3] | An "Agent run" drawer on the case and on Understand · Agents, fed by the journal; usage against run limits; link each tool call to the action id and the case event |
| Highlight the agent's live state on the process diagram; link each tool call to its diagram element | Camunda 8.10-alpha3 [S7] | Light up the current stage on the Compose/Modeler canvas during a run |
| Input and output panels per node; pin a sample and edit it as JSON; "Debug in editor" from a failed past run | n8n [S16] | Compose step 2 test run: show a real past item in and out of every stage; open a stopped case in the canvas with its data |
| Per-tool approve/deny, and tell the agent it was denied | n8n [S16] | Per-tool autonomy under the per-agent level; a declined proposal goes back to the agent as context |
| Autonomy spectrum per tool, moved up or down over time | Camunda blog [S4] | The per-agent autonomy dial in Compose step 3, changed by maker-checker; show the history |
| Three ways to build: describe it, start from a template, build from scratch; lifecycle with "retire" | Manhattan Agent Foundry [S17] | Compose entry: describe, pick a pack sample prompt, or open the Modeler; add "retire" to flows, agents and packs |
| A **plan view before generation**: user stories, data, processes, screens | Appian Composer [S49], Power Apps Plans [S51] | Compose step 1 shows the configuration agent's plan (fields, stages, routes, guardrails, systems, KPIs) as an editable list before it draws the flow |
| Elements **stream onto the canvas** as they are generated, so the user can stop early | UiPath Autopilot for Maestro [S52] | The Compose draft streams stage by stage into the Modeler |
| Review changes before they are built and installed | ServiceNow Build Agent [S50] | Every Compose edit after publish is a diff the approver sees, pinned to its step |
| Policy from a document or plain words; human approves; **test against live decisions before enforcement**; outcomes **block / require approval / warn** | Aera Policy Studio [S54] | "Guardrails in plain words" (01 §2): add a "warn" outcome next to block and approval; run a new guardrail in shadow over live cases before it bites |
| Per-VIN **reasoning, profit-vs-speed trade-off, predicted outcome** in a side panel | ACV MAX Recommendations [S35] | Decide · Cases: show value against days-to-sale for each alternative and the predicted outcome of the recommended route |
| **Forward value at 30/60/90 days** | OPENLANE predictive pricing [S36] | Holding-cost line in Pulse's ageing suggestion rules ("Offers → Auction after 14 days") and in the used-car auction-vs-retail comparison |
| Group-wide transfer optimisation | vAuto [S32] | One pattern for "which lot" (used cars), cross-region power units (telecom) and the next hospital (medical) |
| Technician agent that answers from past repairs and error codes | TRIMEDX-AIQ [S45] | Service desk estimate from similar past repairs (01 §4.2); reuse it for the medical "service then re-rent" route |
| Marketplace for agents and accelerators | Manhattan Momentum 2026 [S17] | Pack gallery (five segments), each with a pack version, locked compliance layer and changelog; partners can add packs |
| Request for information (pause to collect a value, not just a yes/no) | Microsoft Copilot Studio [S14] | "Ask the system owner" in adapter mapping, and a "needs info" proposal type |
| Kill switch for an agent that strays | ServiceNow AI Control Tower [S13] | One-click "pause agent" on Understand · Agents, journalled |
| Case canvas where the path evolves | UiPath Maestro [S10] | Our case timeline already is this; name it so buyers recognise it |
| Free design tool as the door in | Pega Blueprint [S11] | Free replay report from one quarter of returns as the first step of a sale |

Architecture patterns:

| Pattern | From | Note for us |
|---|---|---|
| Ad-hoc sub-process as a governed toolbox: the tool set is drawn on the canvas | Camunda [S2] | Draw an agent's allow-list as a box on the stage; the tool catalogue already holds the schemas |
| Every tool call is a governed activity with retries and incidents | Camunda [S1, S2] | Already true: every tool call goes through `pipeline.invoke`; add an incident view for failed agent calls |
| Usage limits as first-class config (tokens, model calls, tool calls) | Camunda [S3] | Extend agent run limits to tokens and cost |
| Agent Instance API so external agents report into the same view | Camunda 8.10 [S7] | Let MCP-client agents post run events into our journal |
| A decision ledger that also takes decisions made on other platforms via API | Aera Decision Ledger [S54] | Journal entries for overrides and decisions taken in the source systems, so replay and learning see them |
| Champion-challenger with a small share raised gradually; simulation against the same population first | Pega decisioning [S55] | "One region at 20%" with a ramp schedule (20 → 50 → 100) and written promotion and rollback criteria |
| Runtime decision-version selection by expression | Camunda 8.10-alpha3 [S7] | Pick a flow version by region, org unit or volume share without republishing |
| Conditional events reacting to agent output | Camunda 8.9 [S6] | Triggers on proposal content (e.g. confidence below threshold opens an exception) |
| Common data model shared by connectors | Workato [S15] | Make the canonical model visible, versioned and editable by customer IT, per pack (about seven entities each, 01 §9) |
| Recipes and skills exposed as MCP tools via a registry | Workato [S15] | MCP generated from the action catalogue (already decided) plus a registry page |
| MCP server for operators' coding tools (incidents, instances, tasks) | Camunda 8.9 [S6] | Our MCP server should cover operations, not only business actions |

### 7.5 Recover's position (summary)

| Product | Nearest competitor types (summary) | Our position | Detail |
|---|---|---|---|
| **Recover** (circularity) | Retail returns SaaS (§3.1); suites (§2); segment tools: used-car pricing and auctions (§4.2), telecom asset recovery services (§4.3), biomedical asset intelligence (§4.4); DI platforms (§5.2) | The only cross-segment, vendor-neutral disposition decision with locked guardrails, replay and maker-checker found | This report |

**Core-level claim.** One core (models, agents, governance, memory) serves Recover's decision across five segments.
Most rivals sell one segment's tool, or sell the core without the decision (Aera, Camunda, Pega). The risk: the claim
is only credible once Recover is live in at least one segment. Until then it is a roadmap slide, and buyers will
treat it as one.

---

## 8. The "6–8 month window" claim

The claim: large suite vendors will ship comparable circularity features in 6–8 months.

### Evidence that the window is closing (or closed)

- **Retail B2C returns: closed.** Blue Yonder announced test-and-grade workflows and unit-level disposition
  simulation on 26 Aug 2026 (press release; general availability not stated) (corrected in verification, see
  V-verification.md) and owns Optoro since Aug 2025 [S18]. Loop (Apr 2026), Narvar (Jan 2026), ReverseLogix and
  Happy Returns all ship AI for returns [S23–S26]. Blue Yonder's AI-native OMS (5 Nov 2026) ties returns to each
  order [S56].
- **Used cars, dealer side: closed.**
  - ACV MAX Recommendations (shipped 19 Mar 2026): per-VIN retail / wholesale / reprice with reasoning [S35].
  - vAuto: group-wide transfer optimisation (Jan 2026) [S32].
  - OPENLANE: forward pricing (2026) [S36].
- **Build-your-own agents inside suites exist today:**
  - Manhattan Agent Foundry (GA Jan 2026, included with all Manhattan Active solutions) [S17];
  - Oracle AI Agent Studio, with 100+ SCM agents at no added cost [S20];
  - IFS Loops Agent Studio [S21];
  - SAP's 60+ supply-chain agents, phased through 2026 [S19].

  A customer or integrator can build a returns agent on any of them now.
- **Prompt-to-app generators are GA** (Appian Composer Nov 2025, UiPath Autopilot for Maestro Dec 2025, Power Apps
  generative pages Apr 2026, ServiceNow Build Agent May 2026 update) [S49–S52]. An integrator can draft a returns
  app from a description in a day; the domain content is still missing.
- **SAP has every block**: Intelligent Returns Management, a reprocessing template (repair, refurbish,
  remanufacture, IoT-triggered), Field Service and Asset Management, Footprint Management and Green Ledger [S19].
- **Horizontal and DI platforms are generic but ready.** Camunda, Pega, Appian and ServiceNow all ship agents, MCP
  and A2A in 2025–2026 [S6, S11–S13]. Aera announced plain-language policies and a decision ledger in Oct 2026
  [S54].
- **The next big event dates fall right at the end of the window**: Blue Yonder ICON 17–19 May 2027 [S18],
  Manhattan Momentum 18–20 May 2027 [S17]. SAP Sapphire is usually in May–June (2027 date **unconfirmed**). If a
  suite announces industrial circularity, it is most likely there, about 6 months from today.

### Evidence that a window exists

- No suite announcement found for **B2B industrial asset returns, lease-end, tool-fleet or cross-vendor
  circularity** decisions:
  - SAP's May 2026 supply-chain news does not mention returns or circularity [S19];
  - Oracle has no packaged RMA agent [S20];
  - Manhattan's Foundry page lists no returns agent [S17];
  - IFS has no returns Digital Worker [S21];
  - Syncron's 2026 news is about warranty and contracts [S22].
- **Telecom network equipment**: asset recovery is a managed service or an OEM programme. Inventory vendors' agents
  do reconciliation and change [S39–S42]. No disposition software found.
- **Medical rental**: TRIMEDX-AIQ and ServiceNow add agents for hospital-owned equipment [S45, S46]. No rental
  re-rent routing found.
- **Used cars, lessor side**: no product found for the lease-return flow with title/lien and recall guardrails,
  recon approval and replay (**unconfirmed**).
- Blue Yonder's returns news is explicitly retail [S18].
- Suite agents act on their own data layer (Manhattan "runs on the Manhattan Active data layer" [S17]). The
  multi-vendor estate (SAP ERP + other WMS + other EAM + IoT + PLM) is structurally not theirs to serve.
- Suite agent catalogues are broad and shallow (planning, labour, inventory, field service). Disposition with
  valuation, contract checks and carbon is specialised content.
- Announcement to usable product is slow. SAP phases GA "throughout 2026" [S19]. Pega's fabric followed Infinity '25
  by a month, and client-managed timing is unclear [S11]. Aera's Oct 2026 items have no stated availability [S54].

### Verdict

- **Partly supported, and segment-dependent.**

  | Market | Window |
  |---|---|
  | Retail B2C returns | Closed |
  | Dealer-side used-car channel advice | Closed |
  | B2B industrial and multi-vendor asset circularity (tool fleet), telecom network equipment, medical rental routing | 6–8 months is plausible for suite or platform *feature announcements* (May 2027 events); 12+ months for usable, cross-vendor product |
  | Device recommerce | Closing: retail returns players and trade-in programmes are near |
- **The sharper risk is not a suite feature.** It is one of these:
  - a horizontal platform (Camunda, Pega, ServiceNow, Appian) with its prompt-to-app generator plus a systems
    integrator's returns template;
  - a DI platform (Aera) adding an asset-disposition skill;
  - in used cars, ACV, Cox or OPENLANE extending dealer advice to lessors.

  Our defence is domain content and proof, not the orchestration engine:
  - packs with locked guardrails;
  - valuers and named demand;
  - the canonical asset model;
  - replay results and reference pilots.
- **Recommendation for the pitch.**
  - Say: "No suite ships cross-vendor industrial, telecom or medical-rental disposition today (as of Nov 2026); the
    next likely announcements are the May 2027 conferences."
  - In used cars, lead with the lessor flow and neutrality, not with channel advice.
  - Avoid claiming a precise 6–8 months as fact.

---

## Unconfirmed

- Whether Camunda supports maker-checker or shadow mode for DMN.
- UiPath Maestro pricing units and connector count; whether agent features run on Automation Suite (self-hosted)
  at parity with the cloud.
- Pega client-managed timing for agentic features; Pega governance detail.
- Appian agent features on self-managed deployments; ServiceNow AI Agent Fabric release timing (sources differ).
- Workato human-approval step inside recipes; Workato and ServiceNow price levels.
- n8n HITL version (v2.6 per a community post) and the ~$50k/year Embed figure.
- Whether a returns agent exists in Manhattan Active Omni or Agent Foundry templates.
- Whether Blue Yonder links disposition to carbon; the 25% faster-to-sellable figure (vendor claim); GA of the
  Aug 2026 returns features; detail of the 2026.1 Optoro integration.
- SAP reprocessing-template blog date; any SAP returns/circularity Joule agent; Sapphire 2027 date.
- Oracle packaged RMA agent.
- ReverseLogix deployment model (SaaS assumed) and any named agent product; Happy Returns exact press date for the
  10,000-location milestone.
- Depth of pricing engines in device trade-in programmes; AfterShip, ZigZag, ReBound, Two Boxes, B-Stock details.
- **Used cars:**
  - the availability date of the UVeye joint offering and of the VinSolutions agentic Virtual Assistant;
  - the date of the ClearCar-powered AI trade agent;
  - the date of OPENLANE Visual Boost AI;
  - whether any product serves the lessor lease-return decision with guardrails and approvals;
  - J.D. Power remarketing AI features.
- **Telecom:**
  - Netcracker agentic inventory detail;
  - whether any asset recovery provider sells its decision tooling as software;
  - trade-compliance tool coverage of telecom export classes.
- **Medical rental:**
  - rental operators' own AI tooling;
  - whether RTLS vendors record decontamination status in a form we can read;
  - OEM fleet-service AI;
  - a dated Nuvolo AI release.
- **Compose comparison:**
  - whether any generator enforces author ≠ approver for generated flows;
  - whether any offers a percentage or regional rollout of a generated flow;
  - the availability of Aera's six Oct 2026 items;
  - the exact AeraHUB 26 date (coverage says 27–28 Oct 2026);
  - the full Leader list in Gartner's DI Magic Quadrant.
- The PTC Servigistics agent blog's exact date (search results place it in Oct 2026).
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
- S18 Blue Yonder home page: https://blueyonder.com/ ; Blue Yonder blog, returns enhancements [9 Jan 2026]: https://blueyonder.com/blog/2026/new-returns-enhancements-help-retailers-capture-value-as-peak-returns-begin ; Business Wire, agentic AI for stockouts and returns [26 Aug 2026]: https://secure.businesswire.com/news/home/20260826662159/en/ ; IT Brief Australia on agentic returns [27 Aug 2026]: https://itbrief.com.au/story/blue-yonder-adds-ai-retail-tools-for-returns-stock ; Optoro acquisition [18 Aug 2025]: https://www.businesswire.com/news/home/20250818415001/en/ ; Digital Commerce 360 [22 Aug 2025]: https://www.digitalcommerce360.com/2025/08/22/blue-yonder-buys-optoro-acquisition-returns/
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
- S32 Cox Automotive press release, "AI-powered, people-driven: Cox Automotive showcases ... at NADA 2026" [30 Jan 2026]: https://www.coxautoinc.com/press-releases/ai-powered-people-driven-cox-automotive-showcases-industry-leading-capabilities-and-an-unmatched-breadth-of-technology-at-nada-2026/
- S33 CBT News, "Cox Automotive advances dealer workflows" [press release 28 Jan 2026; article 9 Feb 2026]: https://www.cbtnews.com/cox-automotive-advances-dealer-workflows/
- S34 ACV, "ACV Demonstrates VIPER, AI-Powered Inspection Towers, at the 2026 NADA Conference" [2 Feb 2026]: https://www.businesswire.com/news/home/20260202473425/en ; https://www.acvauctions.com/blog/acv-demonstrates-viper-ai-powered-inspection-towers-at-the-2026-national-automobile-dealers-association-conference
- S35 ACV press release, "ACV Expands MAX Suite ... with New ACV MAX Recommendations Feature" [19 Mar 2026] (PDF read in full): https://d1io3yog0oux5.cloudfront.net/_ebab29a741b14975ad396b0e24e0797b/acvauto/news/2026-03-19_ACV_Expands_MAX_Suite_Delivers_AI_Powered_Profit_105.pdf (Business Wire: https://www.businesswire.com/news/home/20260319251914/en/) ; "ACV Unveils All-in-One Inventory Intelligence Suite for Dealers" [7 May 2026]: https://secure.businesswire.com/news/home/20260507999669/en/ACV-Unveils-All-in-One-Inventory-Intelligence-Suite-for-Dealers ; Digital Dealer on the ClearCar-powered AI trade agent [2026, date unconfirmed]: https://digitaldealer.com/news/inrides-trade-agent-ai-and-acvs-clearcar-integration-puts-ai-powered-follow-up-behind-every-trade-in-opportunity-turning-leads-into-booked-appointments/173293/
- S36 OPENLANE, "OPENLANE Unifies AI and Data Capabilities Under OPENLANE Intelligence" [20 Jan 2026]: https://www.nasdaq.com/press-release/openlane-unifies-ai-and-data-capabilities-under-openlane-intelligence-2026-01-20 ; Q1 2026 earnings call transcript [5 May 2026]: https://s202.q4cdn.com/474948805/files/doc_financials/2026/q1/OPENLANE-1Q26-Earnings-Call-Transcript-050526.pdf ; Automotive Fleet, Visual Boost AI [date unconfirmed]: https://www.automotive-fleet.com/10213094/openlane-launches-ai-tool-to-pinpoint-vehicle-damage
- S37 PYMNTS, "CarGurus exits wholesale platform to go all-in on AI SaaS" [2026]: https://www.pymnts.com/earnings/2026/cargurus-exits-wholesale-platform-to-go-all-in-on-ai-saas/
- S38 Auto Remarketing, "AI's potential on display at NADA Show" [2026]: https://www.autoremarketing.com/ar/technology/ais-potential-on-display-at-nada-show-as-it-expands-into-more-areas-of-dealership-operations/ ; Motor, Repairify Repair360 enhancements [Feb 2026]: https://www.motor.com/2026/02/repairify-announces-new-enhancements-to-repair360 ; vAuto iRecon: https://www.vauto.com/irecon/ ; Rapid Recon: https://rapidrecon.com/reconditioning-software/ ; J.D. Power Remarketing Solutions: https://www.jdpower.com/business/jd-power-remarketing-solutions/
- S39 TelecomLead, "Telecom equipment reuse in 2026: how operators extend hardware life to control procurement costs" [13 Oct 2026]: https://telecomlead.com/telecom-equipment/telecom-equipment-reuse-in-2026-how-operators-extend-hardware-life-to-control-procurement-costs-128147
- S40 Nokia, asset recovery: https://nokia.com/networks/services/asset-recovery ; Nokia, circular products and services: https://nokia.com/networks/services/circular-products-and-services ; Ericsson, circularity: https://www.ericsson.com/en/about-us/sustainability-and-corporate-responsibility/circularity ; GSMA, Strategy Paper for Circular Economy: Network Equipment [Feb 2024]: https://www.gsma.com/solutions-and-impact/industry-services/wp-content/uploads/2024/02/Strategy-Paper-for-Circular-Economy-Network-Equipment-1.pdf
- S41 TXO, asset recovery services: https://www.txo.com/resources/asset-recovery-services/ ; Comtek: https://comtek.co.uk/?p=399663 ; Netceed, refurbishment: https://netceed.com/services/refurbishment/ ; Carritech [2026]: https://carritech.com/circular-telecoms-network-resilience-2026/
- S42 Blue Planet blog, "AI-driven inventory: the foundation for autonomous networks in the age of agentic AI" [2026]: https://www.blueplanet.com/blog/2026/ai-driven-inventory-the-foundation-for-autonomous-networks-in-the-age-of-agentic-ai ; Blue Planet blog, "Agentic AI in telecom OSS: practical execution amid industry realities" [2026]: https://www.blueplanet.com/blog/2026/agentic-ai-in-telecom-oss-practical-execution-amid-industry-realities ; ConvergeDigest on configuration and change agents [Jun 2026, seen in search only]: https://convergedigest.com/?p=111585 ; Ericsson blog, unified real-time inventory for AI agents [Sep 2026]: https://www.ericsson.com/en/blog/2026/9/enabling-ai-agents-why-unified-real-time-inventory-is-the-foundation-for-autonomous-networks ; TM Forum Inform, "If your inventory is wrong your network decisions are wrong" [2026]: https://inform.tmforum.org/research-and-analysis/proofs-of-concept/if-your-inventory-is-wrong-your-network-decisions-are-wrong ; Analysys Mason, Netcracker agentic AI profile: https://www.analysysmason.com/research/content/company-profiles/netcracker-agentic-ai/
- S43 PTC blog, "From urgent to important: how agentic AI can elevate service planning" [2026, month unconfirmed]: https://www.ptc.com/en/blogs/service/how-servigistics-agentic-ai-elevates-optimization ; PTC, new SLM AI solutions [2025]: https://www.ptc.com/en/news/2025/ptc-delivers-new-slm-ai-solutions
- S44 (not used; number kept free so revision-2 numbering stays stable)
- S45 TRIMEDX, TRIMEDX-AIQ launch [15 Dec 2025]: https://www.trimedx.com/blog/trimedx-launches-trimedx-aiq ; expansion with supply-chain automation and predictive failure intelligence [24 Feb 2026]: https://www.globenewswire.com/news-release/2026/02/24/3243838/0/en/TRIMEDX-expands-AI-native-TRIMEDX-AIQ-with-supply-chain-automation-and-advanced-predictive-failure-intelligence.html ; technician agent [21 May 2026]: https://www.trimedx.com/resource/trimedx-introduces-new-agentic-ai-capabilities
- S46 ServiceNow, ViVE 2026 Healthcare Operations [Feb 2026]: https://newsroom.servicenow.com/press-releases/details/2026/ViVE-2026-ServiceNow-Healthcare-Operations-automates-the-tedious-work-that-pulls-clinicians-away-from-patient-care/default.aspx ; ServiceNow clinical device management: https://www.servicenow.com/products/clinical-device-management.html ; Nuvolo, 2026 ServiceNow Partner of the Year [27 Feb 2026]: https://www.nuvolo.com/news/nuvolo-named-a-2026-servicenow-partner-of-the-year/ ; Nuvolo clinical: https://www.nuvolo.com/solutions/clinical
- S47 CenTrak asset tracking: https://centrak.com/solutions/asset-tracking-management/ ; Kontakt.io, asset management in healthcare: https://kontakt.io/blog/asset-management-in-healthcare/ ; HID Global, asset management for healthcare facilities: https://www.hidglobal.com/solutions/asset-management-healthcare-facilities
- S48 Wynne Systems, medical equipment rental software: https://wynnesystems.com/?p=31883 ; EZRentOut, medical equipment rental software: https://ezo.io/ezrentout/industries/medical-equipment-rental-software/ ; Booqable, medical equipment: https://booqable.com/industries/medical-equipment ; GE HealthCare, "The strategic role of fleet management in modern health systems": https://www.gehealthcare.com/en/insights/article/the-strategic-role-of-fleet-management-in-modern-health-systems
- S49 Appian press release, "Appian launches new AI capabilities ..." (Composer and Agent Studio GA) [12 Nov 2025]: https://appian.com/about/explore/press-releases/2025/appian-launches-new-ai-capabilities-to-automate-complex-work ; Appian Q1 2026 release highlights: https://appian.com/blog/2026/q1-release-highlights ; Appian docs, AI copilot in Composer (26.7): https://docs.appian.com/suite/help/26.7/ai-copilot-in-composer.html ; AI-assisted development: https://appian.com/products/platform/artificial-intelligence/ai-assisted-development
- S50 ServiceNow press release, "Build Agent now works inside every major AI coding tool, governed by default" [6 May 2026]: https://newsroom.servicenow.com/press-releases/details/2026/ServiceNow-Build-Agent-now-works-inside-every-major-AI-coding-tool-governed-by-default/default.aspx ; docs, Build Agent: https://www.servicenow.com/docs/r/application-development/build-agent.html ; Exploring Build Agent (Zurich): https://www.servicenow.com/docs/r/zurich/application-development/building-applications/exploring-build-agent.html
- S51 Microsoft Learn, plan designer FAQ: https://learn.microsoft.com/en-my/power-apps/maker/common/faq-plan-designer ; generative pages: https://learn.microsoft.com/power-apps/maker/model-driven-apps/generative-pages ; What's new in Power Platform, Sep 2026: https://microsoft.com/en-us/power-platform/blog/power-apps/whats-new-in-power-platform-september-2026-feature-update ; Message Center MC1268500: https://mc.merill.net/message/MC1268500
- S52 UiPath docs, Autopilot for Maestro: https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/autopilot-for-maestro ; Maestro release notes [Dec 2025]: https://docs.uipath.com/maestro/automation-cloud/latest/release-notes/december-2025 ; Autopilot in Studio Web, Maestro BPMN: https://docs.uipath.com/autopilot/other/latest/user-guide/autopilot-in-studio-web-maestro-bpmn
- S53 Camunda docs, BPMN Copilot (early access, alpha): https://docs.camunda.io/docs/components/early-access/alpha/bpmn-copilot/ ; SAP Signavio text-to-process: https://www.sap.com/products/technology-platform/signavio-solutions-process-modeler-text-to-process.html
- S54 Gartner, Magic Quadrant for Decision Intelligence Platforms, abstract [26 Jan 2026]: https://www.gartner.com/en/documents/7363830 ; Aera, agentic reasoning press release [4 May 2026]: https://www.businesswire.com/news/home/20260504336200/en/Aera-Technology-Introduces-Agentic-Reasoning-for-Enterprise-Decisions-Moving-from-Situation-to-Action-in-One-Conversation ; IT Brief Australia, "Aera unveils six tools to automate enterprise decisions" [10 Nov 2026]: https://itbrief.com.au/story/aera-unveils-six-tools-to-automate-enterprise-decisions ; Supply & Demand Chain Executive, six agentic innovations [Oct 2026]: https://www.sdcexec.com/software-technology/ai-ar/news/22977397/aera-technology-aera-technology-launches-6-agentic-innovations-for-enterprise-decisions ; Lokad review of Aera [4 Nov 2026]: https://www.lokad.com/review-of-aeratechnology-com/
- S55 Pega Academy and docs on champion-challenger and model challengers (undated training pages): https://academy.pega.com/node/7596 ; https://academy.pega.com/challenge/testing-decision-strategy/v6 ; https://docs-previous.pega.com/node/2640646
- S56 Logistics Viewpoints, "Blue Yonder launches AI-native order management for retailers and distributors" [5 Nov 2026]: https://logisticsviewpoints.com/2026/11/05/blue-yonder-launches-ai-native-order-management-for-retailers-and-distributors/ ; Blue Yonder 2026.1 release, Cognitive Solutions for Execution: https://blueyonder.com/release-announcements/2026-1-release/cognitive-solutions-for-execution
- S57 Camunda 8.10 announcements (minor release 13 Oct 2026), as read in V-verification.md claim 2: https://docs.camunda.io/docs/reference/announcements-release-notes/8100/8100-announcements/
- Repo: `../2026-11-agent-foundation.md` (agent runtime decision, Orkes Conductor and Agno rejected as the platform); `01-recover-segments.md` (Recover target); `V-verification.md` (corrections kept).
