# Where Recover stands against the known failure modes of supply chain AI agents

28 November 2026. Internal note. It compares what is in this repository today with the failure modes and the vendor
comparison in the market summary the product owner shared. Every statement about our side is about code that exists and
is tested on synthetic data; nothing here has run at a customer or against a real enterprise system.

A one-page version in the product's look: [2026-11-28-agent-landscape.html](2026-11-28-agent-landscape.html).

Before any of this is used with a customer, Kinective's Legal team should review the security, audit and governance
statements.

**How to read the market statements.** Everything said about the market, the failure modes and the vendors comes from
the AI search summary the product owner pasted, and is reported by the linked source. We have not read those pages
ourselves and have not verified any of it. Vendor descriptions are as reported by the linked sources, not verified by
us. Numbers in square brackets point to the Sources list at the end.

## The short answer

- **Governance of agents is our strongest area.** Agents can only read, draft or hold for a person; the server refuses
  anything else. This is the area where the market summary says most deployments are weakest.
- **Integration is built, and unproven.** The Connection Fabric runs for real (credentials, mappings, sync, conflicts),
  but every system behind it is a mock we wrote.
- **Production readiness is the main gap.** No production instance, no paid model access, no security testing, no
  volume testing.
- **Scope is narrower than the suites named.** We decide what happens to returned assets. We do not plan demand,
  procure, or run a warehouse.

## Failure mode by failure mode

The summary names three root causes behind most failures: fragmented data, no real-time integration across legacy
systems, and autonomous actions nobody verified [1, 2, 3, 4, 5, 6]. The eight rows below are the specific modes it lists.

| Failure mode in the summary | Sources (reported) | What we have | What we do not have | Standing |
|---|---|---|---|---|
| **Messy or stale master data** | [7, 4, 5] | Each source has a status (stale, unavailable, failing, sign-in expired) shown in the menu and the Fabric. Conflicts between systems are recorded, and an open conflict on an asset holds its decision. Canonical checks run on every record. Evidence is re-checked before a decision. Each figure carries where it came from (provenance, fetch log, evidence gaps). | Master data cleansing or matching across systems (no duplicate resolution, no golden record). No measured behaviour on a customer's real data quality. | Partly covered |
| **Siloed systems, missing context** | [3, 1, 7] | Connection Fabric: encrypted credentials, configured connections, mappings that run, sync on triggers, webhooks, an adapter registry with test and production environments, import from an OpenAPI description, MCP client sources. A canonical model that every pack maps to. | A real connection to any named enterprise system: all are synthetic mocks. Flat-file and EDI feeds beyond the SFTP mock. Visibility beyond the systems a customer connects (no supplier tiers). | Built, unproven |
| **Misread business meaning** | [8] | Mapping suggestions rank candidates by name and by sample values, then a model reranks them; results come in calibrated bands (pre-ticked, check, no proposal) and a person confirms each one that is not certain. A field can be sent to the system owner as a question. Customers map and rename canonical fields; they do not add new ones. | A knowledge graph or ontology of the business. Status codes and flags are mapped field by field, not learned. | Partly covered |
| **Hallucination in high-stakes actions** | [9, 10] | Values, routes and rankings come from the deterministic engine, checked against 128 reference cases; the model reasons and explains but does not produce the numbers. Every agent-prepared action that is not a read or a draft is refused by the action pipeline (`services/agents/forbidden.py`), whatever the caller claims. A proposal holds for a person. Answers say which lookups they used and whether a model wrote them. | Measured hallucination rates. Evaluation sets for the model's own outputs (drafts, mapping reasons) beyond unit tests. | Covered by design |
| **Multi-agent clashes and loops** | [11, 2, 6] | Agents of a pack run as one ordered chain of stages, not as peers negotiating. Each stage has an autonomy level, limits and a confidence threshold, set in Set up and approved by a second person. Run limits, budgets and cooldowns on the model router; kill switches per agent. | Agents that trade off competing goals (cost against speed against service). Nothing here needs it today, and nothing here does it. | Avoided by design |
| **Unclear accountability, weak guardrails** | [12, 13, 1] | Every write goes through one action pipeline and is journalled. Maker and checker are different people for setups, flows and access. A changed flow runs in shadow, is replayed on past items, and starts for a share of one region with rollback. Guardrails are part of a pack and apply at every autonomy level. Traces of each agent run. | An exported audit report in a form an auditor has accepted. Retention rules. | Covered |
| **Expanded attack surface** | [14, 15, 12] | Access is enforced on the server: tenant boundary, warehouse lock, role permissions. Per-agent credentials; OAuth for outside MCP clients (S256 only, tokens bound to an audience); organisation sign-in, SCIM, directory groups to roles. Credentials for sources are encrypted. Model-written text is rendered without running any HTML. | Prompt-injection testing. A penetration test. A review of what data leaves for the model provider (today the free tiers of two public model APIs). Secrets in a managed key service. | Partly covered |
| **Low planner trust** | [2, 1, 7] | Each recommendation shows its evidence, cost trace and the routes it rejected. Replay figures are labelled as modelled. Analytics compare predicted with actual, and count overrides. Autonomy starts at "recommend only" if the customer chooses. | Evidence from real planners using it. The model's explanations have not been judged by users. | Covered, untested with users |

## The limits the summary names for "one platform"

The summary says no single platform solves all of this out of the box [16, 17].

| Limit | Sources (reported) | Where we stand |
|---|---|---|
| Garbage in still breaks agents | [24, 25] | Same for us. We surface stale and conflicting data and hold decisions on it; we do not clean it. |
| Multi-tenant SaaS against strict deployment control | [16, 23] | In our favour on paper: the whole product runs from Docker Compose, so a single-tenant or customer-hosted install is possible. Not done: a hardened production deployment, high availability, backups, monitoring in place (OpenTelemetry exists and is off by default). |
| Suite commitment against custom build | [18, 19] | We sit between: thirteen template packs as a starting point, changed by describing the business, with a Modeler for the detail. |

## Landscape

Vendor descriptions in this section are as reported by the linked sources (the product owner's summary of them), and
are not verified by us. The summary's market category reference is [23]. "Against Recover" is our positioning, taken
from the table in the next section; it is not a feature count.

| Platform | Reported strength | Reported handling of agent failures | Trade-off as reported | Sources | Against Recover |
|---|---|---|---|---|---|
| **Blue Yonder** | Planning plus warehouse and transport execution | A supply chain knowledge graph for shared context; five domain agents under a central orchestrator; every action logged and reversible | Heavy commitment to the whole suite | [18, 19] | One decision: the next life of a returned asset, and the handover to the systems of record. |
| **Kinaxis Maestro** | Real-time concurrent planning; strongest in planning and disruption response | In-memory, synchronised planning data; human-in-the-loop "digital co-workers" | Not deep in execution | [20] | One decision: the next life of a returned asset, and the handover to the systems of record. |
| **o9 Solutions** | Integrated business planning | An enterprise knowledge graph; a planning and decision layer | Relies on external ERPs and warehouse systems for execution | [19, 21] | A canonical model for returns, with mappings a person confirms. |
| **SAP and Oracle SCM** | Agents native to the ERP | Built-in role permissions and audit logs | Reliable only when the supply chain is standardised on that ERP | [22, 21] | Independent of the ERP; connects through adapters. Less depth in any one system. |
| **Palantir Foundry and AIP** | A custom ontology over messy sources | Deterministic logic tools; granular access control | Needs heavy engineering; no prebuilt supply chain apps | none given in the summary | Templates first; a setup is five steps with an approver, not a build project. |

Reported limits across all of them: most suites are multi-tenant SaaS, so strict deployment control usually means
building a dedicated layer [16, 23]; garbage in still breaks agents [24, 25].

**Internal observation, 27 November 2026 review meeting (no source).** Large engineering and IT services firms are
bringing similar offers to market, so speed matters.

### What the repository already says about competitors

The summary names suites. The repository's own research (24 November 2026, also vendor claims and not tested hands-on,
and itself marked for Legal review where it touches licences) names closer competitors, and says so for each
segment. This is reused, not re-researched.

- **Blue Yonder** (planning suite, above): the repo research reports a returns management product with a disposition
  engine that routes each return to store, distribution centre or recommerce, and Optoro bought in August 2025. It is
  aimed at retail, not at industrial assets [26, section 2.2, 8].
- **Retail returns platforms**: ReverseLogix, Loop, Narvar, ReturnPro, Happy Returns, Inmar [26, section 3.1]. They
  center on fraud, forecasting and decision support for consumer returns.
- **Used cars**: ACV (per-vehicle retail or wholesale advice), Cox Automotive (vAuto, Manheim) and OPENLANE
  [26, section 4.2]. The repo research reports no product found that makes the lessor-side lease-return decision with
  maker-checker and replay; marked unconfirmed there.
- **Decision intelligence**: Aera Technology, in Gartner's first Magic Quadrant for the category [26, section 5.2];
  o9 Solutions is listed among that quadrant's vendors there. Nearest in language (policies, a decision ledger), with no
  returns content.
- **Kinaxis**: appears in the repo's parked research (the "Resolve" idea, out of scope since 25 November) as a
  forward supply chain planning and control tower product [27].
- **Palantir**: not researched anywhere in the repo.
- The repo research names as its sharper risk a horizontal platform plus a systems integrator's template, which fits
  the internal observation above.

## Against the vendors named

This is positioning, not a feature count: each of these is a mature product with years of customer use, and ours is a
proof of concept one week into its current build.

| Their approach | Ours |
|---|---|
| Planning and execution suites (demand, supply, warehouse, transport) | One decision: the next life of a returned asset (redeploy, resell, re-lease, parts, recycle, exit), and the handover to the systems of record. |
| Knowledge graph or ontology across the enterprise | A canonical model for returns, with mappings a person confirms. |
| Agents native to one ERP | Independent of the ERP; connects through adapters. Less depth in any one system. |
| Custom ontology and agent platform with heavy engineering | Templates first; a setup is five steps with an approver, not a build project. |

## What is missing, in the order it blocks a customer

1. **Paid model access and a production instance.** Free tiers rate-limit after a few requests; a demo stalled on this.
2. **A real system connected.** One live connection to a customer's ERP or warehouse system would prove the Fabric.
3. **Security testing.** Prompt injection, a penetration test, and a decision on what data may go to a model provider.
4. **Volume and async.** The replay has run 200 items; nothing is tested at tens of thousands. Plan 4 (async) is open.
5. **Evaluation of model outputs.** Drafts and mapping reasons are tested for shape, not scored for quality.
6. **User evidence.** No planner or approver outside the team has used it.

## What not to claim

- That any named enterprise system is connected. Every one is a synthetic mock.
- "80 % done" as a measure of readiness. Most planned features exist and pass their tests; readiness for a customer is
  the list above.
- Compliance with any standard. None has been assessed.

Before any of this is used with a customer, Kinective's Legal team should review it.

## Sources

Market sources are those the product owner's summary cites, accessed through that summary only (not read by us, not
verified). Vendor descriptions are as reported by these sources.

1. https://www.hcltech.com/trends-and-insights/agentic-ai-supply-chain-evolution
2. https://intuceo.com/blog/agentic-ai-in-supply-chain/
3. https://www.linkedin.com/pulse/stop-blaming-agents-your-supply-chain-ai-has-integration-problem-2wxbf
4. https://sd3it.com/the-hidden-risks-of-ai-supply-chains/
5. https://7t.ai/blog/agentic-ai-risks-challenges-and-solutions-7tt/
6. https://www.paloaltonetworks.com/cyberpedia/what-is-agentic-ai-governance
7. https://www.supplychainbrain.com/technology/artificial-intelligence/article/16425619/the-five-barriers-keeping-ai-agents-out-of-supply-chain-planning
8. https://www.linkedin.com/posts/diwakarsinghbamentor_ai-hallucination-explained-how-business-activity-7531222738582159360-Y8VV
9. https://www.youtube.com/watch?v=DChOoXj_OUw
10. https://medium.com/@amitkharche/agentic-ai-pitfalls-loops-hallucinations-ethical-failures-fixes-77bd97805f9f
11. https://www.youtube.com/watch?v=D37Ijn2o5U0
12. https://www.blueprism.com/resources/blog/ai-agent-challenges-risks-how-overcome/
13. https://www.youtube.com/watch?v=oCQsSaAAm64
14. https://www.awsquality.com/agentic-ai-hidden-risks-how-to-manage-them/
15. https://reinsec.io/blog/agentic-ai-risks/
16. https://intuceo.com/blog/supply-chain-ai-tools/
17. https://www.datarobot.com/blog/agentic-ai-supply-chain/
18. https://blueyonder.com/why-blue-yonder/ai-and-machine-learning/ai-agents
19. https://agenticindex.io/compare/blue-yonder-vs-o9-solutions
20. https://www.kinaxis.com/en
21. https://www.bizz.ai/blog/kinaxis-vs-o9-vs-blue-yonder-vs-sap-ibp-vs-oracle-scm/
22. https://www.oracle.com/scm/oracle-vs-competition/
23. https://www.gartner.com/reviews/market/integrated-supply-chain-ai-agents
24. https://www.slimstock.com/blog/agentic-ai-in-supply-chain/
25. https://www.youtube.com/watch?v=ftSkQFCNVyM
26. Repository: `docs/agents/research/2026-11-platform/C-competitive-landscape.md` (24 November 2026; vendor claims, not tested hands-on)
27. Repository: `docs/agents/research/2026-11-platform/parked/H-resolve.md` (parked research, Kinaxis row)
