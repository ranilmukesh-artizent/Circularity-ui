# Executive guide

**Sign in as** `exec`. Any password.

The Executive has the "senior view: value realised, portfolio health and ranked exceptions. Read-only, plus Notify
the owner." You see **all customers**. Your Command Center is described as: "Value realised, portfolio health and the
exceptions that need attention. Drill into the cases or notify the owner."

> All data is synthetic (Northfield Industrial Leasing). The enterprise systems are simulations; no real vendor system
> is connected.

## What you can see

| Page | Sections |
|---|---|
| Home | Briefing, Needs you, Agent activity, Key figures |
| Command Center | Key figures, Exceptions, Portfolio charts, Value realisation; optionally the operational queues, read only |
| Decision Workbench | Returned assets, Expected returns, Asset intelligence, the case pages (read only) |
| Analytics | All sections (Recovery waterfall, Pipeline, Route mix, Predicted vs actual, Model versions, Overrides, Engineering economics, Sustainability) |
| Modeler | Every organisation's decision flow and business rules (read only) |
| Also | My Tasks, Alerts, Process Orchestration, Audit & Provenance, Reports, Data Checks, Settings |

## What you can do

| Action | Where |
|---|---|
| **Notify the owner** of an exception | Command Center → Exceptions |

Everything else is read only. You cannot acknowledge notifications either: the people you notify do that.

## Your day

### 1. Read the senior view

**Command Center** opens with the value figures and charts: how much value Circularity realised, how the portfolio
moves through its lifecycle and which routes it takes. **Value realisation** compares predicted with actual recovery.
**Analytics** goes deeper: the *Recovery waterfall* from baseline to uplift, *Predicted vs actual*, *Route mix* over
time, *Overrides* (when people changed the plan), *Sustainability* (estimated against measured CO₂e).

Each key figure on **Home** is explained; ask **Ask Circularity** (Ctrl+J) for anything else ("why did recovery drop
this month?").

### 2. Act on exceptions

**Command Center → Exceptions** ranks the issues that need attention (for example decisions close to their window).
Open an exception to see what is behind it, or press **Notify owner**. In *Notify the owner* the recipient is
prefilled by the exception type (you can change it); pick the severity (High, Medium, Low), edit the message (at
least 5 characters) and press **Send notification**. It "creates an Actions on me item and an audit entry".

The demo starts with one such notification: the Executive asked the Approver to clear delayed approvals ("Decisions
are close to their window. Please clear the oldest first.").

Tick **Show operational queues (read-only)** to see the teams' queues without acting on them.

### 3. Look at a case

Open any case from the lists or charts to read its ten stages, the evidence, the routes and the approval history. The
buttons that change a case are not shown to you.

### 4. Look at the rules

The **Modeler** shows the decision flow and business rules each organisation uses, their versions and history. It is
read only for you; Planners and Admin change rules, and an Approver or Admin approves them. The **Models** panel at its
foot shows the model that values new cases, its calibration and the fitted candidates, also read only.

## What you cannot do, and why

- **Change anything on a case** (request, submit, approve, confirm): the Executive view is read only by design.
- **Edit or approve rules**, change access, or manage sources and agents.
- **See the Connection Fabric, MCP & Tools, Agents or Access**.

## Tips

- Start from an exception, drill to the case, then notify the owner with the case in your message: it is faster than
  a meeting.
- *Overrides* in Analytics is where you see when people disagreed with the recommendation and what it changed.

See [the case journey](../case-journey.md) and [Approvals](../approvals.md) for how decisions are made.

## For the technical team

Executive permissions: notify (notify.send). Not tenant-scoped. Pages include modeler (read only: no manageFlows or
approve.flows). Command Center layout: senior.
