# Finance guide

**Sign in as** `finance`. Any password.

Finance "confirms outcomes and tracks recovery, avoided spend and variance", and reads and comments on the audit log
and the Source Map. You see **all customers**. Your Command Center is described as: "Recovered value, avoided spend and
outcomes waiting for confirmation."

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures |
| Command Center | Key figures, Actions on me, **Outcomes to confirm**, Portfolio charts, Value realisation |
| Decision Workbench | Returned assets, Expected returns, Asset intelligence, the case pages |
| Asset intelligence tabs | Overview, Lifecycle, Economic, Data, Related |
| Analytics | All sections (Recovery waterfall, Pipeline, Route mix, Predicted vs actual, Model versions, Overrides, Engineering economics, Sustainability) |
| Connection Fabric | Overview, Source Map, Monitor (read only; you may comment on a source) |
| Also | My Tasks, Alerts, Process Orchestration, Audit & Provenance, Reports, Data Checks, Settings |

## What you can do

| Action | Where |
|---|---|
| **Confirm an outcome** (actual against predicted) | Case, stage 9; Command Center → Outcomes to confirm |
| Comment on a source or record | Connection Fabric (source drawer), Audit |
| Acknowledge notifications | Home, My Tasks, Alerts |

## Your day

### 1. Find the outcomes to confirm

**Command Center → Outcomes to confirm** ("Results that need Finance") lists the cases whose instructions are all
acknowledged and whose actual costs and value have been reported. **Home → Needs you** and **My Tasks** list them too.

### 2. Confirm an outcome

1. Open the case on stage 9 (**Outcome**). The case is *Closed*: every instruction was acknowledged, the last one being
   the actual cost posting in ERP finance (or the receipts, for a sale).
2. Read the tabs: *Delivery*, *Actual costs*, *Documents*.
3. Press **Confirm the outcome** ("Records the actual costs and value; stage 10 compares them with the prediction.").
4. Circularity records the actual per cost line of the approved route, links the lines to the decision and to the
   models that predicted them, and logs "Actual … against predicted …".

You can confirm only once, and only when the case is closed. Before that the server says: "The outcome has not been
reported yet; RT-… is still with the enterprise systems."

**Example (RT-1048).** After the redeploy of RT-1048 runs to the end, confirm its outcome. In the demo's reference run
the actual net is **$9,230** against **$9,600** predicted: a variance of −$370.

### 3. Review the variance

Stage 10 (**Reconcile and learn**) shows *Lines* (predicted against actual per line), *Learning record* (what the
models learn from it) and *Carried forward*. **Open in Analytics** takes you to **Analytics → Predicted vs actual** for
the case.

### 4. Track value

- **Analytics → Recovery waterfall**: from the baseline to the uplift Circularity adds.
- **Predicted vs actual**: forecast against outcome across cases.
- **Model versions**: the learning loop.
- **Overrides**: when people changed the plan, and what it cost or saved.
- **Command Center → Value realisation**: predicted against actual recovery.

### 5. Retirement, residual and credit at close

Packs with a fixed asset or a customer credit add close steps ([README](README.md#more-industries-plan-9)).

- **Retirement or transfer.** After the route steps the case sends the ERP a retirement (sale, salvage or write-off) or a
  transfer. The case shows the ERP's document, proceeds, book value and gain or loss exactly as the ERP answered; the
  app does not recompute them.
- **Lease residual** (leased vehicles and devices). The gain or loss is the ERP's proceeds minus the lease contract's
  residual, to the cent, on the case.
- **Customer credit** (trade-in or upgrade). The case computes the credit from the final payout, or from the quote and the
  grade received, and compares it with the amount the ERP posted. If they differ to the cent, an item opens for you and
  the case waits. Resolve it with one of two resolutions, accept the ERP's amount or send the credit again
  under the same key, and add a note of at least 15 characters. An agent cannot resolve it; it is your decision.
- **Core credit** (automotive cores). The credit owed for an accepted core is compared with what the ERP posted in the
  same way and resolved the same way. A core with a fraud flag is held before this: an Approver or Admin releases it
  ([approver.md](approver.md)), not Finance.

These accounting references are orientation only. Finance and Kinective's Legal team confirm them before anyone relies
on them.

### 6. Check the sources

**Connection Fabric → Source Map** shows which system each figure comes from; **Monitor** shows integration health
over time. Open a source to read its details and add a comment for the Developer. **Audit & Provenance → Fetch log**
shows every fetch with its source; *Evidence gaps* shows evidence without provenance. See the
[Connection Fabric guide](../connection-fabric.md).

## What you cannot do, and why

- **Submit, approve, override or decline** decisions, or **re-evaluate**: Finance confirms what happened; planners and
  approvers decide what should happen.
- **Confirm before the case is closed**: the systems must report the actual first.
- **Change sources or workflows**: integration belongs to the Developer and Admin.
- **Let an agent confirm for you**: confirming an outcome is done only by a person.

## Tips

- The ERP finance system stays the book of record for actual cost. Circularity links its posting to the decision; it
  does not replace it.
- A large variance is worth a comment: it is what the next model learns from.

See [the case journey](../case-journey.md) for all ten stages.

## For the technical team

Finance permissions: confirm (outcome.confirm), comment, ack. Not tenant-scoped. Connection Fabric sections: map,
overview, monitor.
