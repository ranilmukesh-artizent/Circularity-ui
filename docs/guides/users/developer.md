# Developer guide

**Sign in as** `developer`. Any password.

The Developer (integration staff) "connects sources, builds workflows, proposes MCP servers and governs agent tools".
You see **all customers**. Your Command Center is described as: "Health of connected systems, workflows, conflicts and
MCP server proposals."

> **Everything is simulated.** All data is synthetic (Northfield Industrial Leasing). Each enterprise system in the
> catalogue is a local simulation that imitates that product's API style; connecting one connects to its simulation.
> No real vendor product is connected. What Circularity does with the data (syncs, mappings, credential storage,
> checks, conflicts, workflow runs) works for real.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures |
| Command Center | Key figures, Actions on me, Integration health |
| Connection Fabric | All tabs: Overview, Workflow Studio, Source Map, Source Tables, Canonical Models, Event Streams, Conflict Queue, Manual Import, Monitor |
| MCP & Tools | All sections, including the Playground |
| Agents | Registry, Runs, Proposals waiting for you, the tool catalogue, Models (read only, except proposals you may decide) |
| Also | My Tasks, Alerts, Process Orchestration, Audit & Provenance, Reports, Data Checks, Settings |

You do not see the Decision Workbench, Analytics, the Modeler or Access: decisions and access belong to other roles.

## What you can do

| Action | Where |
|---|---|
| Connect, configure, sync, pause, disconnect and delete sources; rotate credentials | Connection Fabric |
| Map fields, edit source tables, load a manual import, resolve or escalate conflicts | Connection Fabric |
| Open a case for each imported row | Connection Fabric → Manual Import |
| Build, test, publish, pause and run workflows, including the *Open case* block | Connection Fabric → Workflow Studio |
| Comment on a source | Connection Fabric (source drawer) |
| Try agent tools in the playground | MCP & Tools → Playground |
| Propose a new MCP server | MCP & Tools → Server proposals |
| Accept or reject an agent's proposal for an action you hold | Home → Proposals for you; Agents → Proposals waiting for you |
| Acknowledge notifications | Home, My Tasks, Alerts |

## Your day

### 1. Check integration health

**Command Center → Integration health** and **Connection Fabric → Overview** show each source's state (healthy,
stale, failing, token expired), the workflows whose last run failed and the open conflicts. **Monitor** shows health
over time against the SLA. The demo's starting data includes one failed workflow (*Ingest · Oracle Depot Repair*, a
validation failure), so you have something to fix.

### 2. Connect and keep sources running

Everything about sources, credentials, mappings, tables, events, conflicts, imports and monitoring is in the
[Connection Fabric guide](../connection-fabric.md). The [runbook](../../agents/runbook-fabric.md) covers failing
sources, keys, webhooks, stuck runs and held records.

**The adapter registry (plan 9).** **Add source** and Compose's mapping step start from the registry: the connection
templates, the generic REST connector, and entries made from an API spec. Each entry has a kind (*catalogue*,
*generic_rest* or *from_spec*) and a state (*draft*, *tested*, *released*). Steps:

1. **Import an API spec:** paste an OpenAPI 3 document. The import turns it into a *from_spec* draft with its notes and
   checks. Or ask the **Integration Assistant** to draft the connector: it drafts, code checks the draft, and one
   proposal holds it for a person (an agent can draft an entry, never release it).
2. **Test environment first:** a new connection starts in *test*, read only, with no schedule and no instruction sent.
   Discovery reads up to 500 records per resource into a dry store so you can see the fields.
3. **Release:** a person who did not draft the entry releases it.
4. **Production:** each of production access and write-back is a request that the named system owner approves in **My
   work**. You cannot approve your own request. After the owner approves, **Promote** moves the connection to production
   (you enter the secret again; it is stored encrypted and never shown).

**Mapping suggestions and the five choices.** For each source field the suggestions panel proposes a canonical field
with a calibrated confidence and the reason. Nothing is accepted for you. Choose one of: **Accept**, **Choose another
field**, **Accept with a conversion** (shows the converted sample values), **Not needed** (blocked on a required field),
or **Ask the owner** (sends a short question to the system owner and holds **Save mapping** while it is open). A field
the pack knows to be unsure, such as two mileage fields, always needs your choice. Sample values shown on screen are
masked (emails, phone numbers, names, long free text).

### 3. Build workflows

Workflows move data in (ingest) and approved instructions out, and can react to cases. See the
[Workflow Studio reference](../workflow-studio.md) and the hands-on [workflow tutorial](../workflow-tutorial.md).

**Workflow author and canvas samples.** Describe the workflow in a sentence (the assistant's Set up mode, or the
workflow page). It plans the graph, asks only what it cannot assume, drafts it, checks every block against the real
fields of the source (up to three repair rounds), test runs it dry and saves a draft with every block marked as
AI-made. It never publishes: you read the draft and publish it yourself. On the canvas, **Test run** shows the records
before and after each block (masked, as above) and the ones a block held; nothing is written by a test run.

**Opening cases from data.** Add the **Open case** block ("A case for each record") to an ingest workflow. Set the
*Asset field* that holds the asset key, the template (any pack, for example *industrial*, *tool_fleet* or *device*), the reason (*rma*,
*lease_end*, *trade_in*, *contract_end*, *iot_alarm*, *manual*) and the *Org unit* (or bind the source to an org unit,
in the Connect dialog or under *Configuration* in its drawer, and leave it empty). *Only if* takes `field=value` to open cases only for matching records. A test run opens nothing
("Would open N cases"). When the published workflow runs, each new asset and reason opens one case, valued at once by
the template and the organisation's published business rules; a record whose asset already has a case for that reason
is skipped. See
[the case journey](../case-journey.md#3-how-a-case-opens).

**From a file.** In **Manual Import**, validate the CSV, tick **Open a case for each row**, pick the template and
reason, and press **Load … rows for evaluation**. Each row's *owner* names the organisation unit. Rejected rows are
never partially loaded. Tool-fleet and device rows carry their template's extra columns and are valued by that
template; the message after loading counts the cases opened, already open and not opened (with the reason). See
[Manual Import](../connection-fabric.md#13-manual-import).

### 4. Propose an MCP server

In **MCP & Tools → Server proposals**, press **Propose MCP server** and fill in: server name, vendor or owner,
purpose, tools it exposes (comma separated), access (*Read only* or *Read and write*), and the data it touches
(categories only; never paste real records). **Submit for review**: "It waits for an Approver or Admin." Once
approved, the server joins the MCP client list as *approved · not yet connected*; connecting it is a separate step.
See [Approvals](../approvals.md#4-mcp-server-proposals).

### 5. Try agent tools

**MCP & Tools → Playground** runs a tool call as an agent would, within your permissions and a chosen tenant. **Call
log and gate** shows every agent call and the write gate that stops agents from committing anything on their own.
**Permission matrix** shows what each agent may do per tenant.

### 6. Watch the agents

The **Agents** page is split into sections: *Registry* (kind, on or stopped, autonomy, tools, organisation scope),
*Credentials*, *Proposals waiting for you*, *Runs* (step by step) and the *Tool catalogue*, and outside clients for Admin.
**Agent activity** (linked from Home and My Tasks) is the read-only log across all agents. On a case, **Run the agent on
this case** starts a propose-only run: every write it prepares is held for a person. The tool catalogue shows which
actions an agent may call; the **Models** panel shows the base model, the active calibration per template and the
fitted models. The page is read only for you: Admin registers (**Register
agent**), changes, starts and stops agents and starts the case autopilot; Planners and Admin fit and propose models,
and an Approver or Admin approves their promotion.

**Proposals waiting for you** lists actions an agent prepared and held for a person, filtered to those you may
decide: the held action must be one your role may run (for example a source sync). The same proposals show on Home
under *Proposals for you*. **Accept** runs it as you; **Reject** asks for a short reason for the agent's owner. A
proposal from an agent that acted for you (for example an MCP client using your sign-in) shows "Your agent's
proposal: another person accepts it." instead of **Accept**; you can only reject it. See
[Approvals](../approvals.md#5-agent-proposals).

## What you cannot do, and why

- **Open a case's decision, approve, override or decline**: you do not see the Decision Workbench; decisions belong to
  planners and approvers.
- **Approve your own MCP proposal**: another person (an Approver or Admin) reviews every new server.
- **Change agents, autonomy, limits or access**: Admin governs them.
- **Edit business rules**: the Modeler belongs to Planners, Approvers and Admin.

## Tips

- Pause a source rather than disconnect it when you only need to stop syncs for a while.
- Test-run every workflow before you publish it; for an *Open case* workflow the test tells you how many cases it
  would open.
- Agents never publish, pause or delete a workflow, and never change a source connection; if a draft came from the
  AI builder, you are the one who publishes it.

## For the technical team

Developer permissions: manageIntegrations, manageWorkflows, useTools, proposeMcp, comment, ack; plan 8 adds openCases.
Pages: integration (all sections), mcp (all sections), agents (read only: no manageAgents), command (kpis, aome,
health), home, tasks, alerts, orchestration, audit, reports, checks, settings. The background job queue (tasks API,
`/api/v1/tasks`: list, enqueue, retry, cancel, reprioritise) is open to Admin and Developer; it has no screen.
