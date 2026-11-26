# Engineer guide

**Sign in as** `engineer`. Any password.

The Engineer "inspects assets, records assessments and test results, and owns technical eligibility". You work from
the Repair centre and see **all customers**. Your Command Center is described as: "Inspection queue, failed
eligibility gates, condition and parts at risk."

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures |
| Command Center | Key figures, Actions on me, Handed off, Portfolio charts, Actions to prioritise, Signals and capacity |
| Decision Workbench | Returned assets, Expected returns, Asset intelligence, the case pages |
| Asset intelligence tabs | Overview, Lifecycle, Condition, Product, Eligibility, Data, Related |
| Analytics | Engineering economics, Sustainability |
| Connection Fabric | Overview, Source Map, Source Tables, Canonical Models, Monitor (read only) |
| MCP & Tools | Tool catalog, Agent registry, Permission matrix, Call log and gate, As MCP client, Server proposals (read only) |
| Also | My Tasks, Alerts, Process Orchestration, Audit & Provenance, Reports, Data Checks, Settings |

## What you can do

| Action | Where |
|---|---|
| **Record an inspection or test result** | Case, stage 5 (*Inspect and grade*) |
| Request missing evidence or an inspection | Case, stages 4–5 |
| Check for the next acknowledgement during execution | Case, stage 8 |
| Acknowledge notifications | Home, My Tasks, Alerts |

## Your day

### 1. Work the inspection queue

Your key figures include the inspection queue, failed gates, graded assets and parts at risk. **Home → Needs you** and
**My Tasks** list the cases whose next step is yours: inspections that were requested and wait for a result.

### 2. Request an inspection or test

If a case is missing evidence (status *Needs evidence*) and nobody has asked yet, stage 4 or 5 offers the request, for
example **Request inspection** or **Request photos**, naming who owns it. Pressing it sends a request with a work order
reference (WO-…). Planners and Warehouse Managers can request too; a second request is refused as a duplicate.

Example: RT-1051, a hydraulic pump of Customer A in Warehouse 1, "has not been inspected. No route can be evaluated
without condition and remaining-life evidence."

### 3. Record the result

1. Open the case on stage 5 (**Inspect and grade**). Once the request is out, the box shows **Record the result**
   ("Records the inspection result from the inspection system; the routes are built next.").
2. Press it. Circularity records the result from the inspection system: the **grade** (A to D), the **engineering
   life** in months (grade D is "Below minimum"), and the next inspection date. You do not type the grade.
3. Every evidence item is marked ready, every route is rebuilt and ranked, and a new evidence snapshot is taken. If a
   route is eligible, the case moves to *Awaiting approval* and the Planner submits it; otherwise it waits for review.

Tabs on stage 5: *Findings*, *Diagnostic condition*, *Certified period*, *Photos*.

### 4. Own technical eligibility

Every route must pass six gates: *Condition & life*, *Post-intervention*, *Policy & certification*, *Demand fit*,
*Economics* and *Sustainability*. The first ones rest on the inspection evidence you record. When every route fails a
gate, stage 6 shows: "Every route failed a gate.
Engineering and policy owners resolve failed gates; the agent cannot waive them." Nobody can approve an excluded
route; the way forward is new evidence (a test, a repair scope, a certification).

### 5. Repair work during execution

When a redeploy or re-lease is approved, one execution step is a **Refurbishment work order** (or a **Teardown work
order** for parts recovery) in the depot repair system, owned by the Repair centre lead (Engineer). The repair system
acknowledges it and returns the work order number; follow it in stage 8 *Messages and acknowledgements*.

### 6. Reporting evidence before a case closes

For recycle and exit routes, and for organisations flagged for sustainability reporting, a case does not
close until the treatment facility's evidence is on it: the **mass in kilograms** and the **material** (organisations in
scope), and a **treatment code** of the form R or D plus a number, such as R4 or D10 (recycle and exit routes). The last
step then shows that it is waiting for the evidence. When the facility has reported it, use **Attach reporting evidence**:
case, mass, material, treatment code and a source reference. When nothing is missing any more, the case closes. Waste and
reporting rules are orientation only: Kinective's Legal team reviews them before anyone relies on them.

### 6b. When you are named as a system owner

A connection's **system owner** is a named person. When someone asks for production access or write-back on a system
you own, or asks you a question about one of its fields while mapping it (**Ask the owner**), an item opens in **My
work**. For access, **Approve**, or **Decline** with a reason; the requester never approves their own request, and an
Admin can answer for any system. For a field question, answer in the thread; the mapping stays blocked until you do.
Nothing reaches the system in production until you approve.

### 7. Read the data behind a case

- **Asset intelligence**: condition, product, eligibility and data tabs for one asset.
- **Connection Fabric** (read only): where each source's data comes from, how tables link, the canonical models, and
  integration health. See the [Connection Fabric guide](../connection-fabric.md).
- **Audit & Provenance → Fetch log** and **Evidence gaps**: every fetch with its source, and evidence without
  provenance.
- **Analytics → Engineering economics** and **Sustainability**.

## What you cannot do, and why

- **Submit, approve, override or decline** decisions: the Planner prepares and the Approver decides.
- **Re-evaluate** a case or save what-if scenarios: those are the Planner's and Approver's tools.
- **Confirm outcomes**: Finance owns the actual numbers.
- **Change sources, workflows or agents**: integration belongs to the Developer and Admin.

## Tips

- Record the result as soon as the inspection is done: the case is valued at that moment, and the holding-cost clock
  has been running since the asset was received.
- If a result looks wrong, ask Ask Circularity (Ctrl+J) to explain the case, and check the *Fetch log* for the
  source of each value.

See [the case journey](../case-journey.md) for all ten stages.

## For the technical team

Engineer permissions: request, assess (evidence.recordResult), execSim, ack. Not tenant-scoped. Connection Fabric
sections: overview, map, tables, models, monitor; MCP sections without the playground.
