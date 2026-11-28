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

## More industries (plan 9)

The demo company leases industrial assets, but the platform runs other kinds of returns from the same pages. Each
industry is a *pack*: a data file with its routes, gates, guardrails, wording and valuation. Admin chooses which pack an
organisation uses (see [admin.md](admin.md#the-organisation-tree)). The data is synthetic and the systems are
simulations, as in the rest of the demo.

| Pack | Unit | Routes | Close extras |
|---|---|---|---|
| Industrial returns | asset | redeploy, resale, internal parts, re-lease, material recovery, external parts, exit | none |
| Tool fleet returns | tool | release, refurbish, redeploy, resell, harvest parts, exit | customer credit, reporting evidence |
| Device recommerce | device | buy now, offers, auction, market, wholesale | customer credit, reporting evidence |
| Used vehicles (lease and trade-in) | car | retail, auction, dealer trade, salvage | fixed-asset retirement, lease residual, reporting evidence |
| Telecom network equipment | unit | redeploy, spare, resell, harvest, recycle | fixed-asset retirement, reporting evidence |
| Medical rental (hospital equipment) | device | re-rent, service then re-rent, refurbish, retire | fixed-asset retirement, lease residual, reporting evidence |
| IT asset disposition (IT lease end) | asset | redeploy, return to lessor, resell, harvest, recycle | none (sanitisation per serial, manifest reconciliation) |
| Rental and construction fleets | machine | re-rent, rebuild, branch transfer, retail, auction, dealer, parts, scrap | damage recovery at close |
| Telecom CPE (home routers, set-top boxes) | device | refurbish and redeploy, broker, harvest, recycle | none (decisions are per lot) |
| EV and industrial batteries | pack | reuse, remanufacture, repurpose, recycle | none (battery passport, safe lanes) |
| Automotive cores (remanufacturing) | core | reman, harvest, broker, scrap | core credit settlement, fraud hold |
| Medical capital equipment | device | refurbish and resell, resell as is, harvest, recycle | none (regulatory assessment) |
| Serialised retail returns | item | buy now, offers, auction, market, wholesale, donate, recycle, exit | reporting evidence |

Every pack is also a template in the Modeler and in the pickers (templates, Add source, Records import), so a Planner
can start a flow from any of them. The industrial pack is now in the same full pack format as the others; its numbers
and texts are unchanged. Each pack has its own demo data and mock systems, and the pickers list the packs the server
knows. The packs are in `backend/di/services/modeler/packs/`.

Two things worth knowing about the new packs:

- **Medical capital:** a case needs a regulatory assessment before it can be resold. A Planner records it on the case
  (**Record assessment**); the recorded line shows who recorded it and when.
- **Automotive cores:** a core with a fraud flag is held. An **Approver** or **Admin** releases the hold with a reason
  (it needs the permission to approve decisions); a Planner is refused and an agent never can.

What the phase-13 close adds, by role (each guide has the steps):

- **Fixed-asset retirement or transfer** (packs marked above): after the route steps, the case sends the ERP a
  retirement (sale, salvage, write-off) or a transfer. The ERP's gain or loss is shown as the ERP answered it.
- **Lease residual:** for a leased vehicle or device, the gain or loss is the proceeds minus the lease contract's
  residual.
- **Customer credit:** for a trade-in or upgrade, the credit the case computed is compared with what the ERP posted. A
  difference goes to **Finance**; see [finance.md](finance.md).
- **Reporting evidence:** a case closes only when the treatment facility's mass, material and treatment code are on it
  where the rules ask for them; see [engineer.md](engineer.md).
- **Vendor qualification:** a downstream vendor is chosen only while its certificate is approved and in date on the
  day of the decision; see [planner.md](planner.md).

> **Review before reliance.** The accounting and reporting rules named in these guides (fixed-asset retirement, waste
> treatment codes, sustainability reporting) are orientation only. Kinective's Legal team reviews them before anyone
> relies on them or offers them to a customer.

## One assistant (plan 10)

Ask Circularity, the Modeler's assistant, the Describe dialog and Set up's helper are now one assistant. Open it with
the spark button in the top bar or **Ctrl+J**; in the Modeler it sits pinned in its own column. It shows which page,
case and draft it is reading. Three modes, chosen under the box:

- **Ask:** read-only answers with their sources.
- **Change flow:** describe a change; it shows a checked, simulated preview card and applies it to the draft only when
  you press the button, with **Undo** while the draft is unchanged.
- **Set up:** draft a flow, mappings or a composition from a prompt. On the Set up page it is the conversation that
  starts your setup (see [planner.md](planner.md#set-up-a-business-in-five-steps)).

Every step shows a status line while it works, and a sentence typed in the wrong mode gets a hint, not an error. The
assistant never approves, publishes or changes access: what it prepares waits for a person
([plan 10](../../agents/plans/10-unified-assistant-ux.md)).

**Agent activity** (linked from Home and My Tasks): what each agent did (held, accepted, rejected, refused, run), with
filters for kind, agent, pack and case. It is read-only and shows only the tenants and warehouse you may see. On a
case, **Run the agent on this case** lets an Admin, Planner or Approver start a propose-only autopilot run of an enabled
agent: every write it prepares is held for a person.

## The menu

The left menu has three groups. **Decide** holds My Tasks, Cases and Alerts. **Understand** holds Pulse, Analytics,
Reports and Agents. **Advanced** holds the Modeler, Connection Fabric (with Data Checks), MCP & Tools, Data pipelines
and runs, and Audit; it is closed until you open it, and opens by itself when you are on one of its pages. *Pulse* is
the page that opened as *Command Center* in earlier versions (its own heading still reads Command Center), *Cases* was
*Decision Workbench*, and *Data pipelines and runs* was *Process Orchestration*. The routes did not change. **Set up**
is the one place that builds the business flow; *Data pipelines and runs* and the Workflow Studio's **Build a
workflow** are about moving data, not about the business flow.

Until an organisation has a published setup, the menu shows only Home, Set up and Access (and My Tasks while a setup
waits for approval), with a note that Decide and Understand open when you publish. Hiding is for display only: the
server still checks every page and action.

## Things every role has

- **Home**: a briefing, *Needs you* (items whose next step is yours), *Agent activity* (what the agent prepared) and
  *Key figures*, each explained. *Proposals for you* appears when an agent holds an action that you may accept or
  reject.
- **Pulse**: your role's key figures and work queues. Its sections differ by role (each guide lists yours).
- **My Tasks** and **Alerts**: everything whose next step is yours; escalations, failures and notifications.
- **Data pipelines and runs**: the ten stages of a case, the live run, one case stage by stage, and which agent or
  system does what.
- **Audit & Provenance**: every fetch with its source (*Fetch log*) and evidence without provenance (*Evidence gaps*;
  not for Warehouse Managers).
- **Reports**, **Data Checks** and **Settings** (profile, theme, region and agent options).
- **The assistant** (the spark button in the top bar, or Ctrl+J; *Ask Circularity* in Ask mode): ask questions in plain
  words. In Ask mode it only reads; in the other modes it proposes and a person applies. It never approves anything.

## Rules that hold for everyone

1. **A person decides.** Agents (Ask Circularity, the MCP tools, the case autopilot, the workflow builder) act as the
   signed-in person and can only read, draft or prepare. They never approve, override, decline, publish, propose or
   promote a model, register agents or change access. What they prepare waits for a person (on Home, under
   *Proposals for you*), and the person the agent acted for does not accept it: another person does. See
   [Approvals](../approvals.md).
2. **Nobody checks their own work.** A rule change or a model is approved by a different person from the ones who made
   it (for a rule change, everyone who saved or submitted the draft; for a model, also the one who proposed it). A tenant access request or an MCP server proposal is decided
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
