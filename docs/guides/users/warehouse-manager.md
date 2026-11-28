# Warehouse Manager guide

**Sign in as** `warehouse1` (Warehouse 1) or `warehouse2` (Warehouse 2). Any password.

The Warehouse Manager "runs one warehouse: cases at that location, inbound expected returns, capacity and items
awaiting handoff outcomes. Requests evidence and acknowledges notifications; WMS stays the system of record." Your
Pulse is described as: "Your warehouse: what is on you, inbound expected returns, and items with enterprise
systems awaiting an outcome."

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## Your scope: one warehouse

You see the cases **whose asset is currently in your warehouse**, for every customer. A case in the other warehouse
or in the Repair centre is outside your scope: the server refuses any action on it with "RT-… is at Warehouse 2,
outside your warehouse." Lists, figures and charts are filtered the same way.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures |
| Pulse | Key figures, Exceptions, Actions on me, Handed off, Portfolio charts, Signals and capacity |
| Cases | Returned assets, Expected returns, Asset intelligence, the case pages (your warehouse) |
| Asset intelligence tabs | Overview, Lifecycle, Condition, Data, Related |
| Audit & Provenance | Fetch log |
| Also | My Tasks, Alerts, Data pipelines and runs, Reports, Data Checks, Settings |

## What you can do

| Action | Where |
|---|---|
| **Request missing evidence** (an inspection, photos …) | Case, stages 4–5 |
| Acknowledge notifications | Home, My Tasks, Alerts |

## Your day

### 1. See what is on you

**Pulse → Actions on me** and **Home → Needs you** list what waits on you. **Exceptions** ranks the issues in
your warehouse. **Signals and capacity** shows what needs attention and how full the warehouse is.

### 2. Plan inbound returns

**Cases → Expected returns** lists returns that are planned but not yet received (planning signals).
**Returned assets** lists what is in your warehouse now, with each case's stage.

### 3. Close an evidence gap

When a case in your warehouse is missing evidence (*Needs evidence*), stage 4 or 5 offers the request, for example
**Request inspection** or **Request photos**. Press it: a request with a work order reference goes to the owner, and
the case continues when the result arrives. The Engineer records the result.

### 4. Follow what is handed off

**Pulse → Handed off** lists cases with the enterprise systems, awaiting an outcome. In an approved route,
the warehouse steps are yours in the real world: *Warehouse moves and outbound delivery* (picks, staging and dispatch
against the load), *Reserve unit* for a sale, *Putaway after refurbishment* for a re-lease, *Parts putaway* for
recovered parts. The warehouse management system acknowledges each step with its document (a transfer, a
reservation, a putaway); you see it in the case's stage 8 *Messages and acknowledgements*. The warehouse system stays
the system of record: Circularity sends the instruction and reads the acknowledgement, it does not replace your
warehouse processes.

### 5. Acknowledge notifications

Notifications addressed to you appear in **Alerts**, **Home** and **My Tasks**. Acknowledge them once handled.

## What you cannot do, and why

- **See other warehouses' cases**: you are locked to your own warehouse.
- **Submit, approve or re-evaluate** decisions, or save what-if scenarios: planners and approvers decide.
- **Record inspection results**: the Engineer owns technical eligibility.
- **Confirm outcomes**: Finance owns the actual numbers.
- **Press Check for the next acknowledgement** in execution: acknowledgements still arrive on their own; the case
  page updates as they do.
- **See Analytics, the Connection Fabric, MCP & Tools, the Modeler, Agents or Access.**

## Tips

- Request missing evidence early: no route can be valued without condition and remaining-life evidence, and the
  holding-cost clock runs from the day the asset is received.
- Use Ask Circularity (Ctrl+J) for "what is waiting in my warehouse?"-style questions; it answers within your scope.

See [the case journey](../case-journey.md) for all ten stages.

## For the technical team

Warehouse Manager permissions: request, ack. Warehouse-scoped (the case's current location must be the account's
warehouse); not tenant-scoped. Audit: log only. No analytics, integration, mcp, modeler, agents or access pages.
