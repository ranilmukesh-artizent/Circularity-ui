# Circularity Decision Workbench: user guides

Circularity decides what to do with an asset that comes back at the end of a lease: redeploy it, resell it, re-lease
it, recover its parts, recover its material, or exit it responsibly. It gathers the evidence from the systems the
company already runs, values every route, recommends one, waits for a person to approve it, hands the approved
decision to those systems, and finally compares what was predicted with what actually came back.

> **Everything you see is a demonstration.** All data is synthetic: the company is *Northfield Industrial Leasing*,
> with three customers (Customer A, B and C), eight customer sites, two warehouses and a repair centre. The
> enterprise systems Circularity talks to (order management, repair, transport, warehouse, finance and others) are
> local simulations that imitate the style of well-known products. No real vendor system is connected.

## Who is who

Every person signs in with one role. The role decides which pages you see and which buttons work. The server checks
every action again, so a button you cannot use is either hidden or refused with a short reason.

| Role | What the role is for | Sees | Guide |
|---|---|---|---|
| **Planner** | Prepares cases, closes evidence gaps, tries what-if scenarios and submits decisions for approval. Edits the business rules of their own organisation; fits and proposes models; requests access to other customers. | Own customer (tenant) only | [planner.md](planner.md) |
| **Approver** | Approves, overrides or declines decisions; approves rule changes and model promotions; decides access requests and MCP server proposals that Admin delegates. | All customers | [approver.md](approver.md) |
| **Engineer** | Inspects assets and records inspection and test results; owns technical eligibility. | All customers | [engineer.md](engineer.md) |
| **Finance** | Confirms outcomes (actual against predicted), tracks recovered value, avoided spend and variance. | All customers | [finance.md](finance.md) |
| **Warehouse Manager** | Runs one warehouse: the cases there, inbound returns, capacity, items waiting on handoff outcomes. | Own warehouse only | [warehouse-manager.md](warehouse-manager.md) |
| **Executive** | Senior read-only view: value realised, portfolio health, ranked exceptions; can notify an owner. | All customers | [executive.md](executive.md) |
| **Developer** | Integration staff: connects source systems, builds workflows, proposes MCP servers, watches the agents. | All customers | [developer.md](developer.md) |
| **Admin** | Everything above, plus accounts, the organisation tree (configuration packs, pilot mode), delegations, approval limits, agent autonomy and the agents themselves. | Everything | [admin.md](admin.md) |

Not sure where to start? Read the [case journey](../case-journey.md) first: it follows one returned motor (RT-1048)
from the end of its lease to the lessons learned, and every role guide refers to its stages.

## Signing in

Open the app and sign in with one of these IDs and **any password**. You can also type the work email,
`<id>@northfield.example` (for example `planner.b@northfield.example`).

| Sign in as | Account | Scope |
|---|---|---|
| `ops` (or `planner.a`) | Planner · Customer A | Customer A only. Owns the demo case RT-1048. |
| `planner.b` | Planner · Customer B | Customer B only |
| `planner.c` | Planner · Customer C | Customer C only |
| `approver` | Approver | All customers |
| `engineer` | Engineer (Repair centre) | All customers |
| `finance` | Finance | All customers |
| `developer` | Developer | All customers |
| `exec` | Executive | All customers |
| `warehouse1` | Warehouse Manager · Warehouse 1 | Cases located in Warehouse 1 |
| `warehouse2` | Warehouse Manager · Warehouse 2 | Cases located in Warehouse 2 |
| `admin` | Admin | Everything |

Your account menu (top right) shows your role, your description and, for a Planner, the customers you can see. A
Planner also finds **Request tenant access** there. Use **Switch account** or **Sign out** there.

## Things every role has

- **Home**: a briefing, *Needs you* (items whose next step is yours), *Agent activity* (what the agent prepared) and
  *Key figures*, each explained. *Proposals for you* appears when an agent holds an action that you may accept or
  reject.
- **Command Center**: your role's key figures and work queues. Its sections differ by role (each guide lists yours).
- **My Tasks** and **Alerts**: everything whose next step is yours; escalations, failures and notifications.
- **Process Orchestration**: the ten stages of a case, the live run, one case stage by stage, and which agent or
  system does what.
- **Audit & Provenance**: every fetch with its source (*Fetch log*) and evidence without provenance (*Evidence gaps*;
  not for Warehouse Managers).
- **Reports**, **Data Checks** and **Settings** (profile, theme, region and agent options).
- **Ask Circularity** (the spark button in the top bar, or Ctrl+J): ask questions in plain words. It only reads; it
  never approves or changes anything.

## Rules that hold for everyone

1. **A person decides.** Agents (Ask Circularity, the MCP tools, the case autopilot, the workflow builder) act as the
   signed-in person and can only read, draft or prepare. They never approve, override, decline, publish, propose or
   promote a model, register agents or change access. What they prepare waits for a person (on Home, under
   *Proposals for you*). See [Approvals](../approvals.md).
2. **Nobody checks their own work.** A rule change or a model is approved by a different person from the one who made
   it (for a model, also from the one who proposed it). A tenant access request or an MCP server proposal is decided
   by someone other than the person who made it. A decision you submitted is approved by someone else unless Admin
   allows self-approval within a limit.
3. **Nothing reaches an enterprise system without an approval reference.**
4. **The tenant boundary holds.** A Planner sees only their own customer unless access to another one is granted
   (until the grant ends or is revoked); a Warehouse Manager sees only cases in their warehouse.
5. **Everything is recorded.** Every change is written to the audit log with who did it and when.

## Guides

- Per role: [Admin](admin.md) · [Approver](approver.md) · [Planner](planner.md) · [Engineer](engineer.md) ·
  [Finance](finance.md) · [Developer](developer.md) · [Executive](executive.md) ·
  [Warehouse Manager](warehouse-manager.md)
- [The case journey](../case-journey.md): the ten stages, from lease end to learning, with RT-1048 as the example.
- [Approvals](../approvals.md): every approval in the product, who approves what, limits and delegations.
- [Connection Fabric](../connection-fabric.md): connecting source systems, mappings, conflicts, imports, monitoring.
- [Workflow Studio](../workflow-studio.md) and the [workflow tutorial](../workflow-tutorial.md): building the
  workflows that move data in and instructions out.
