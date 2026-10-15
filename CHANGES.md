# Circularity UI: what changed

For the product overview (what Circularity does, every screen and every role) read [`README.md`](README.md). This file is the reviewer walk-through, one section per update, newest first.

Open `index.html`. The app opens on a **sign-in screen** (Update 7): pick a demo account, and it opens on that role's home page. Update 8 adds the **Executive** and **Warehouse Manager** accounts, the guided treatment page and **Process orchestration**. Updates 1 and 2 live under **Integration** in the left menu, on the tabs along the top.

**Quick links:** [Update 8: Guided flow and senior views](#update-8-guided-decision-flow-senior-and-operational-views-enterprise-handoffs) · [Update 7: Role-based views](#update-7-role-based-views-sign-in-as-a-role) · [Update 6: Treatment intelligence](#update-6-treatment-intelligence) · [Update 5: Asset intelligence](#update-5-asset--product-intelligence) · [Update 4: Sidebar sections](#update-4-sidebar-with-sections) · [Update 3: Command Center](#update-3-command-center-new-home-page) · [Update 1](#update-1-separate-systems-and-crud) · [Update 2](#update-2-live-connections-workflow-states-tables-and-health) · [Demo script](#two-minute-demo-script) · [Good to know](#good-to-know)

---

## Update 8: Guided decision flow, senior and operational views, enterprise handoffs

**Why:** the Product Owner asked to *structure the flow*, so a viewer sees where a user starts, how they move and what outcome they get. The plan, the decisions taken and what is still assumed are in [`docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md`](docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md). Points marked **(assumed)** follow the plan's default until the Product Owner confirms them.

> **Legal review.** This update adds roles, site scoping, identity-provider settings and positioning wording ("decision intelligence, not an execution system"). Kinective's Legal team should review the role matrix and that wording before it is used with clients.

### What changed, where

| Area | Where | What you see |
|---|---|---|
| **Wording and handoffs** (R8) | Everywhere | Circularity **recommends and sends approved instructions**; ERP, EAM and WMS **carry out the work** and report back. "Executing" is now **Handed off**, "Execution timeline" is **Enterprise handoff**, "Execution readiness" is **Handoff readiness**, the agent is the **Handoff Coordinator**. Every handoff step names its target system: Redeploy → **ERP · Order Management**, Refurbish or repair → **EAM · Diagnostic and Repair**, Return to stock → **WMS putaway** (legend under each handoff and on Process orchestration). Buttons: **Simulate system acknowledgement**, **Resend instruction**. Seeded approver names are now account labels |
| **Expected returns** (R2) | Product → Expected returns | Derived from contract and lease expiry in the **Contract Management** application: Contract ID, Customer, Asset, Lease period, Contract expiry, **Likely outcome** with probability (assumed, D19), return window, Site, Planning range (also weighted by the chance of return), Source application. A row opens the contract and a lease timeline |
| **Guided treatment page** (R6) | Any case, e.g. `#/product/RT-1048` | Five steps top to bottom with a sticky step bar: **1** asset and status (why, and what is outstanding), **2** recommended outcome, **3** why this outcome, **4** what-if and edge cases, **5** approval and enterprise handoff. The decision buttons now live only in step 5. Links such as `#/product/RT-1048?step=4` open a step |
| **Condition → life → value** (R5) | Step 2 and Asset intelligence → Overview | A. diagnostic condition (e.g. *Winding insulation: Grade B*), B. **estimated RUL 30–40 months** next to the **certified operating period 24 months**, C. commercial value for that life with the matched order (*SO-48102 at Site 3*). The demand horizon is capped at the certified period; if demand needs longer, **Needs re-certification** and the route becomes Conditional (assumed, D10) |
| **What-if result** (R3) | Step 4 | A large card: **Base net · Simulated net · Δ $ · Δ %**, ▲ ▼ with signs, the assumptions changed, and one sentence on the ranking. It updates on every slider move. **Apply to** one pathway; presets **Demand cancelled**, **Parts cost +30%**, **Resale price −20%**, **Certification shorter than demand** |
| **Tie-breaker and comparison** (R4) | Steps 2–4 | When the top two are within 5% or $250, a **Close call** box names the deciding factor in order: risk/confidence, demand certainty, cycle time, RUL, carbon (assumed, D8). The rules are on screen. The **top pathways side by side** (base, simulated, Δ, the factors, rank) open by themselves on a close call or Low confidence. Confidence shows as **High / Medium / Low**, each saying what to do. Seeded recommendations are unchanged |
| **Instruction preview** | Step 5 | Before approval the Approver sees what each target system will receive, plus **View raw payload**; after approval the sent payload matches it |
| **Senior view** (R1) | New **Executive** account; Admin → *Senior* switch | Value figures on top (same as Finance), portfolio health, ranked **Exceptions** (value at risk by reason, warehouse bottlenecks, declining metrics, deteriorating condition) with **View cases** and **Notify owner**. *Show operational queues* reveals them read-only |
| **Operational view** (R1) | Planner, Engineer, new **Warehouse Manager** | **Actions on me** first, then **Waiting for approval** (status only) and **Handed off · awaiting outcome** with target system, external reference and age. Planner and Engineer default to their home site and can widen it; the Warehouse Manager is locked to one warehouse everywhere |
| **Notify** (D7) | Exceptions | Recipient prefilled by exception type (changeable). Creates an *Actions on me* item and an audit entry, nothing leaves the app (simulated). When the recipient acknowledges, the exception shows **In hand by …** |
| **Process orchestration** (R7) | New menu item | Ten stages, each with agent or service, source systems, status, start, end and duration, for any case you can see; **Replay**, **Simulate failure at stage**, a run trace from the audit trail and call log with redacted values, and links to Audit, the event stream and (Developer, Admin) the live call log |
| **Identity and users** (M1) | Access → Identity and users (Admin) | Identity provider card (Microsoft Entra ID as an example, simulated), SSO → SCIM → role mapping, **Sync from directory**, App Roles or groups mapped to role and site (editable; membership read-only), directory users with `example.com` addresses, a simulated leaver, escalation path and **out-of-office delegation** to an eligible Approver. The sign-in screen explains SSO in production |

### Screenshots

| Executive (senior view) | Warehouse Manager (operational) | Treatment page, steps 1–2 |
|---|---|---|
| [![Executive](docs/screenshots/flow-executive-command.webp)](docs/screenshots/flow-executive-command.webp) | [![Warehouse Manager](docs/screenshots/flow-wm-command.webp)](docs/screenshots/flow-wm-command.webp) | [![Steps 1–2](docs/screenshots/flow-case-steps-1-2.webp)](docs/screenshots/flow-case-steps-1-2.webp) |
| **What-if** | **Close call (RT-1094)** | **Approval and handoff** |
| [![What-if](docs/screenshots/flow-case-whatif.webp)](docs/screenshots/flow-case-whatif.webp) | [![Close call](docs/screenshots/flow-case-neartie.webp)](docs/screenshots/flow-case-neartie.webp) | [![Handoff](docs/screenshots/flow-case-handoff.webp)](docs/screenshots/flow-case-handoff.webp) |
| **Process orchestration** | **Expected returns** | **Identity and users** |
| [![Orchestration](docs/screenshots/flow-orchestration.webp)](docs/screenshots/flow-orchestration.webp) | [![Expected returns](docs/screenshots/flow-expected-returns.webp)](docs/screenshots/flow-expected-returns.webp) | [![Identity](docs/screenshots/flow-identity.webp)](docs/screenshots/flow-identity.webp) |
| **Dark mode** | **Phone** | **Planner (operational)** |
| [![Dark](docs/screenshots/flow-dark-executive.webp)](docs/screenshots/flow-dark-executive.webp) | [![Phone](docs/screenshots/flow-phone-case.webp)](docs/screenshots/flow-phone-case.webp) | [![Planner](docs/screenshots/flow-planner-command.webp)](docs/screenshots/flow-planner-command.webp) |

### Try it (three minutes)

1. Sign in as **Executive**. The value figures match Finance. In **Exceptions**, press **View cases** on *Warehouse bottleneck: Warehouse 1*, then **Notify owner** and send it to *Warehouse Manager · Warehouse 1*.
2. **Switch account** to *Warehouse Manager · Warehouse 1*. The notification is first in **Actions on me**; press **Acknowledge**. Only Warehouse 1 cases appear anywhere. Switch back to Executive: the exception says *In hand by Warehouse Manager · Warehouse 1*.
3. Sign in as **Approver** and open **RT-1048**. Read down: status and what is outstanding → *Redeploy · $9,600*, RUL 30–40 months against 24 certified, order SO-48102 at Site 3 → why → what-if. Drag **Preparation, parts and fees**: the card shows ▼ and the new net as you drag.
4. Open **RT-1094**: the **Close call** box explains which factor decides, and the comparison is already open.
5. In step 5 of RT-1048, read the **instruction preview** (ERP · Order Management first), then **Approve redeployment**. The **Enterprise handoff** names each target system.
6. Open **Process orchestration**: RT-1048's stages, then **Replay** and **Simulate failure at stage 4**.
7. As **Admin**, open **Access → Identity and users**: change a site mapping, press **Sync from directory**, and see both in the audit log. Use the **Senior / Operational** switch on the Command Center.

### Checks

- Existing role suite: **208 of 208** pass (the 178 earlier checks, updated only where this plan changes a label or adds a menu group, plus the two new roles in every loop).
- New guided-flow suite: **110 of 110** pass: wording scan on every page for every account, expected-return columns and scope, five steps in order and decision buttons only in step 5 for every case, RUL range and certified period, what-if card maths and signs (under 16 ms), tie-breaker and comparison rules, all 128 recommendations unchanged, Executive KPIs equal Finance, Notify → Actions on me → In hand, handed-off count equals the lifecycle legend (38), Warehouse Manager scope in pages, search and audit, orchestration for every account, failure propagation and redaction, identity rules, instruction preview equals the sent payload, data invariants, no console errors.
- Phone width (390 px): no sideways scroll on the new and changed screens.

### Still assumed or open

D2 and D5–D20 in the plan are still waiting for the Product Owner and are built on the defaults. The user journey diagram (D15) is not in the repo yet, and the "increase the count of the rows… with the same button" point (D12) is not built until it is clarified.

---

## Update 7: Role-based views (sign in as a role)

**Where:** the app now opens on a **sign-in screen**. Pick a demo account. Each role then sees only the pages, panels, figures and buttons that belong to its job. Controls a role can never use are **not shown at all**, rather than greyed out. The account menu (top right) has **Switch account** and **Sign out**.

| Sign-in | Phone |
|---|---|
| [![Sign-in](docs/screenshots/rbac-signin.webp)](docs/screenshots/rbac-signin.webp) | [![Phone sign-in](docs/screenshots/rbac-phone-signin.webp)](docs/screenshots/rbac-phone-signin.webp) |

**Simulated sign-in.** There are eight demo accounts: three Planners (one per customer tenant), Approver, Engineer, Finance, Developer and Admin. There are no passwords and no real authentication. Labels are synthetic. The choice is remembered on this device until you sign out. An old saved role from earlier versions is carried over automatically.

> Access control is close to compliance. The role matrix below, and any wording about access, should be reviewed by Kinective's Legal team before it is relied on.

### What each role sees

| Role | Lands on | Left menu | Can do | Does not see |
|---|---|---|---|---|
| **Planner** (Customer A, B or C) | Command Center | Command Center, Product, Analytics (read-only), Audit (own tenant) | Request evidence, **Submit for review**, scenarios, re-evaluate, **request access to another tenant** | Integration, MCP, other tenants' cases (until access is granted) |
| **Approver** | Command Center, with the **Approvals inbox** | Command Center, Product, Analytics, Integration (Event stream and Conflict queue, read-only), MCP (read-only), Audit | **Approve, Override, Decline** decisions; approve or decline **MCP server proposals** and **tenant access requests**, each only if Admin delegated it | Workflow studio, Source map, Manual import, MCP playground |
| **Engineer** | Asset intelligence | Command Center, Product (no Pool optimizer), Analytics (engineering economics and sustainability), Integration (Source map, tables, models, read-only), MCP (read-only), Audit | Request inspection, **Record assessment result** | Economic tab, approval, Finance actions |
| **Finance** | Analytics | Command Center, Product (read-only), Analytics, Integration (Source map, read-only), Audit | **Confirm outcome**, **comment** on audit entries and Source map sources | Approval, evidence requests, MCP, workflows |
| **Developer** | Integration, Source map | Command Center (integration health), Integration, MCP and Tools, Audit | Everything in Integration, MCP playground, **Propose MCP server**, comment | Product and Analytics (no case data) |
| **Admin** | Command Center | Everything, plus **Access** | Everything, plus Approver delegations and every request | Nothing hidden |

Opening a page your role cannot see (for example from an old bookmark) takes you to your home page with a short message saying why. A link to another tenant's case says that the record belongs to another tenant.

### Command Center for each role

Each role gets its own key figures and panels, computed from the same data, so numbers still match Product and Analytics.

| Role | Key figures | Panels |
|---|---|---|
| Planner | Assets in scope, Awaiting approval, Evidence gaps, Closing within 5 days | Lifecycle portfolio, time to action, actions to prioritise, signals |
| Approver | Awaiting approval (value), Potential recovery, Value at risk, Closing within 5 days, Requests waiting | **Approvals inbox**, value at risk by reason, time to action, actions, capacity, value realisation |
| Engineer | Inspection queue, Failed gates, Graded A or B, Parts on backorder (illustrative) | Lifecycle portfolio, treatment opportunity, actions, signals, capacity |
| Finance | Net recovery, Uplift vs baseline, Recovery yield, Avoided spend, CO₂e avoided | **Outcomes to confirm**, treatment opportunity, value realisation |
| Developer | Integration health, Sources needing attention, Failing workflows, Open conflicts, My MCP proposals | Integration health, mapping exceptions, recent events (live) |
| Admin | Requests waiting, Potential recovery, Value at risk, Integration health, Uplift | Everything above |

| Planner | Approver | Finance | Developer |
|---|---|---|---|
| [![Planner](docs/screenshots/rbac-planner-command.webp)](docs/screenshots/rbac-planner-command.webp) | [![Approver](docs/screenshots/rbac-approver-command.webp)](docs/screenshots/rbac-approver-command.webp) | [![Finance](docs/screenshots/rbac-finance-command.webp)](docs/screenshots/rbac-finance-command.webp) | [![Developer](docs/screenshots/rbac-developer-command.webp)](docs/screenshots/rbac-developer-command.webp) |

### Treatment Intelligence and Asset intelligence

| Moment | Planner | Approver | Engineer | Finance |
|---|---|---|---|---|
| Decision waiting | **Submit for review** | **Approve**, **Override**, **Decline** | Status only | Status only |
| Evidence missing | Request evidence | Request evidence | Request inspection, then **Record assessment result** | Status only |
| Outcome reported | Status only | Status only | Status only | **Confirm outcome** |
| Scenarios | Save, load, delete | Save, load, delete | Preview only | Preview only |

- **Submit for review** records who submitted and when; the Approver sees it on the decision card.
- **Decline** needs a reason. The case goes back to re-evaluation and the Planner sees the reason.
- **Asset intelligence** shows the tabs of the role: the Engineer has no Economic tab; Finance gets an economic view (Overview, Lifecycle, Economic, Data, Related). The overview reflows, so there are no empty gaps.

| Planner: Submit for review | Approver: Approve, Override, Decline | Engineer: asset page |
|---|---|---|
| [![Planner case](docs/screenshots/rbac-planner-case.webp)](docs/screenshots/rbac-planner-case.webp) | [![Approver case](docs/screenshots/rbac-approver-case.webp)](docs/screenshots/rbac-approver-case.webp) | [![Engineer asset](docs/screenshots/rbac-engineer-asset.webp)](docs/screenshots/rbac-engineer-asset.webp) |

### Approvals, requests and the Access page

- **Approvals inbox** (Approver and Admin, on the Command Center, with a count in the left menu): tenant access requests and MCP server proposals. **Approve** adds an optional note; **Decline** needs a reason.
- **Tenant access:** a Planner picks **Request access…** in the tenant menu (or **Request tenant access** in the account menu), chooses a tenant and gives a reason. Once approved, that tenant appears in the Planner's menu for the rest of the session.
- **MCP server proposals:** the Developer uses **Propose MCP server** under **MCP and Tools → Server proposals** (name, owner, purpose, tools, read or write, data it touches). An approved server joins the MCP client list as "approved, not yet connected".
- **Access** page (Admin only): accounts and roles, **Approver delegations** (decisions, MCP proposals, tenant access) and all requests. Untick a delegation and its buttons, inbox items and key figure disappear for the Approver straight away.
- Every request, decision and delegation change is written to the event stream and audit log with the account that made it.

[![Access page](docs/screenshots/rbac-admin-access.webp)](docs/screenshots/rbac-admin-access.webp)

### Read-only views and comments

- Integration and MCP pages say **Read-only view** for roles that may look but not change. A source opens with every field read-only.
- **Comments:** Finance, Developer and Admin can comment on an **audit entry** (open it from the audit log) and on a **Source map source** (open it, then the **Comments** tab). Everyone who can see the item can read the comments. Do not enter personal data.

### Try it (three minutes)

1. Sign in as **Planner · Customer A**. Open **RT-1048** and press **Submit for review**.
2. Account menu → **Switch account** → **Approver**. In the **Approvals inbox**, approve **REQ-304** (tenant access for Planner · Customer B). Open **RT-1048**, see who submitted it, and press **Decline** with a reason.
3. Switch to **Planner · Customer A**: RT-1048 shows your reason. Press **Run re-evaluation**.
4. Switch to **Planner · Customer B**: the tenant menu now includes Customer A.
5. Switch to **Admin** → **Access** → untick **MCP server proposals**. Switch to **Approver**: the proposal has left the inbox.
6. Switch to **Developer** → **MCP and Tools → Server proposals** → **Propose MCP server**.
7. Switch to **Finance** → **Integration → Source map** → open **ERP** → **Comments**. Post a comment.

[![Dark mode](docs/screenshots/rbac-dark-approver.webp)](docs/screenshots/rbac-dark-approver.webp) [![Phone](docs/screenshots/rbac-phone-planner.webp)](docs/screenshots/rbac-phone-planner.webp)

### Also fixed

- **Five key figures on a laptop screen:** the Approver, Finance, Developer and Admin Command Centers have five key figures. On laptop-size windows (roughly 1,050 to 1,500 px wide) they sat three on one row and two on the next, leaving an empty slot. The second row now stretches to fill the width.
- **Phone layout:** Analytics and MCP and Tools no longer scroll sideways at phone width. Some rows stayed in two columns on small screens, and two tables and the engineering heat map now scroll inside their panels.

### Still assumed (please confirm)

These points were not covered by the Product Owner's answers, so the app follows the draft plan:
- Approver and Engineer access to the Integration sections and the audit log stays as in the draft matrix.
- Roles other than Planner see all tenants.
- Developer and Admin can reply to Finance comments.
- The Access page lists the demo accounts but does not create new ones.

### How it was checked

An automated headless-browser suite runs 178 checks. It covers:
- sign-in, migration of the old saved role, and recovery from a broken saved value
- every route for every account (allowed pages render; forbidden ones send you home with a reason)
- no forbidden control anywhere on any page, drawer or modal, and no link to a page the role cannot open
- the Command Center figures and panels per role, with no gaps
- all visible cases rendering for every role
- the tenant lock
- inbox, approve and decline, delegations and proposals
- comments, including escaped text
- numbers that match across Command Center, Product and Analytics
- the existing data integrity checks

A second run opens every page each role can reach at 390 px and finds no sideways scrolling. Every colour added in this update comes from the existing palette; no new colour values were added.

---

## Update 6: Treatment Intelligence

**Where:** open any returned asset (click a row in Returned assets, or **Evaluate treatments →** on the asset page). This is the old "Decision analysis" page, rebuilt into five connected panels. The address is unchanged, so every existing link still works.

| Screenshot (desktop, top) | Bottom half | Phone |
|---|---|---|
| [![Top](docs/screenshots/treatment-top.webp)](docs/screenshots/treatment-top.webp) | [![Bottom](docs/screenshots/treatment-bottom.webp)](docs/screenshots/treatment-bottom.webp) | [![Phone](docs/screenshots/treatment-phone.webp)](docs/screenshots/treatment-phone.webp) |

**Header buttons**
- **Asset Decision Mode / Portfolio Optimization Mode:** the second one opens the Pool optimizer, which allocates assets that compete for the same demand.
- **Save scenario**, **Compare (n)**, **Evidence snapshot**, and **Submit for review →**.

> **Since Update 7** the decision buttons depend on the role: the Planner sees **Submit for review**; the Approver sees **Approve**, **Override** and **Decline** (with a reason); the Engineer sees **Record assessment result**; Finance sees **Confirm outcome**. Scenario saving is for Planner, Approver and Admin. See the Treatment Intelligence table in Update 7.
- Below it, a card with the product photo, key facts, a link back to **Asset Intelligence**, and four **business objective sliders** (net recovery, turnaround time, environmental impact, serviceability).

**The five panels**

| Panel | What it does |
|---|---|
| **1. Treatment eligibility and feasible pathways** | Every pathway with an **Eligible**, **Conditional** or **Restricted** tag and the reason. Click one to highlight it in the table and chart |
| **2. Predicted outcomes and comparison** | A table per pathway: recovery value, cost, net recovery bar, cycle time, success probability, useful life, CO₂e avoided, and an objective **Fit** score. Tick up to three to compare, and see a net recovery vs cycle time chart |
| **3. Recommendation and rationale** | The recommended pathway with its net and how much better it is than the next best, why, the key drivers, why the runner-up lost, binding constraints, and the two next-best alternatives. The existing **Approve** and **Review alternatives / override** buttons sit at the bottom |
| **4. Scenario simulation (what-if)** | Four sliders (purchase price, prep and fees, service exposure, resale and lease income) and a cancelled-demand switch. The impact line updates as you drag. **Save scenario** keeps it for the asset, with **Load** and **Delete**. The approved recommendation never changes until it is re-evaluated |
| **5. Execution readiness** | Six checks (repair capacity, parts, hazmat and battery rules, customer release, EAM work order, ERP reservation) with a status each, followed by the existing execution timeline |

**Your weights matter:** the **Fit** column and a note in panel 3 show which pathway wins under your objective weights. If it differs from the approved recommendation, the page says so, without changing the approval.

**Nothing was removed.** The evidence, prediction, options-and-gates, pool and explanation sections are all still there under **Detailed analysis**, and they follow the same scenario sliders.

**Same numbers everywhere:** the recommended net is the same figure shown on Returned assets, Command Center and Asset Intelligence.

**Cases with no recommendation yet** (awaiting inspection or evidence) still show all five panels, with a clear message and the existing "request evidence" action in panel 3.

**Works on phone, tablet and desktop:** panels stack, wide tables scroll inside their panel, and nothing overflows the screen.

---

## Update 5: Asset & Product Intelligence

**Where:** Product → **Asset intelligence** in the left menu, or click any **asset ID** in the Returned assets table, or the **Asset intelligence** button on a decision page. Every asset has its own link, such as `#/product/asset/RT-1048`.

**Screenshots**

| Overview (desktop) | Economic Analysis tab | Data & Evidence tab | Phone |
|---|---|---|---|
| [![Overview](docs/screenshots/asset-overview.webp)](docs/screenshots/asset-overview.webp) | [![Economic](docs/screenshots/asset-economic-tab.webp)](docs/screenshots/asset-economic-tab.webp) | [![Data](docs/screenshots/asset-data-tab.webp)](docs/screenshots/asset-data-tab.webp) | [![Phone](docs/screenshots/asset-phone.webp)](docs/screenshots/asset-phone.webp) |

Command Center, for reference: [docs/screenshots/command-center.webp](docs/screenshots/command-center.webp)

**Top of the page**
- Breadcrumb, a **switch asset** dropdown, **Open in new tab**, and an **Actions** menu (open the decision analysis, evidence snapshot, copy link, print or save as PDF).
- The product **photo**, the title, twelve key facts (asset ID, serial, manufacturer, revision, ownership, location, site demand, received, age, engineering life, next inspection), and an **overall health score** ring.
- Two buttons: **Compare similar assets** (side-by-side table of up to four) and **Evaluate treatments →** (opens the decision page).

**Eight tabs** (each tab is a focused view of one area)

| Tab | What you see |
|---|---|
| **Overview** | All seven panels at once: lifecycle timeline, condition, product, economics, eligibility, data quality, related assets |
| **Lifecycle** | The seven-step evidence timeline with source and notes, plus the service history (work orders) |
| **Condition** | Condition summary, per-component condition bars, inspection evidence table, photo close-ups |
| **Product & Components** | Specifications, component health, parts availability, and a bill of materials with lead times and approved alternates |
| **Economic Analysis** | Recovery value, treatment cost, predicted net with its range, USD or local currency, historical cost, market demand, resale price trend, every route compared, and how the recommended net is built |
| **Eligibility & Compliance** | Ownership, contract, warranty, safety and environmental checks, the six gates with the reason for each, and any routes withheld |
| **Data & Evidence** | Data confidence score, key sources and freshness, and a table of every evidence item with links to the audit log, evidence snapshot and Source map |
| **Related Assets** | The closest assets of the same class, with health, net and status, plus **Open** and **Compare** buttons |

**Same numbers as the rest of the app:** the predicted net on this page is the same figure as on the Returned assets table and the decision page (for example, $9,600 for RT-1048). Evidence, gates and conditions come from the same data, and the market figures come from the 1,400 closed decisions.

**Product photos:** five real-looking, unbranded photos (motor, pump, control unit, power tool, laptop). Tool-fleet batches use the power-tool photo with a "×quantity" badge. If an image file is missing, a labelled tile appears instead, so nothing breaks.

**Honest labels:** component health, part numbers, stock levels and historical costs are modelled from grade, age and class for this demo, and the page says so where it matters.

**Works on phone, tablet and desktop:** the timeline turns into a vertical list on narrow screens, panels stack, and tables scroll.

---

## Update 4: Sidebar with sections

The left menu now has a dropdown under every page, listing the sections that actually exist on it.

> **Since Update 7** the menu shows only the pages and sections of the signed-in role. Update 7 also added **Approvals inbox**, **Outcomes to confirm** and **Integration health** to Command Center, **Server proposals** to MCP and Tools, and a new **Access** page for Admin.

| Page | Sections in its dropdown |
|---|---|
| **Command Center** | Key figures, Portfolio charts, Actions to prioritise, Signals and capacity, Value realisation |
| **Product** | Returned assets, Expected returns, Pool optimizer, Asset intelligence |
| **Analytics** | Recovery waterfall, Pipeline, Route mix, Predicted vs actual, Model versions, Pool efficiency, Overrides, Engineering economics, Sustainability |
| **Integration** | Workflow studio, Source map, Source tables, Canonical models, Event stream, Conflict queue (with its live count), Manual import |
| **MCP & Tools** | Tool catalog, Agent registry, Playground, Permission matrix, Call log and gate, As MCP client |
| **Audit & provenance** | Fetch log, Evidence gaps |

**How to use it**
- **Click the arrow** on a page to open or close its list. Click the page name to go to it. The list for the page you are on opens by itself, and your choices are remembered.
- **Hover** a page whose list is closed to see its sections in a small flyout, each with a one-line description.
- **Click a section** to jump straight to it. On Analytics, MCP, Audit and Command Center the page scrolls to that section. On Product and Integration it switches the tab or view.
- **Badges** show live counts: open conflicts on Integration and Conflict queue, systems needing attention on Source map, and failing workflows on Workflow studio.
- **Collapse button** at the bottom (the « arrows) shrinks the menu to icons. Hover an icon to see its sections.
- **Every section has its own link**, such as `#/integration/map`, so you can share it and the browser back button works.
- **Phone:** the menu stays as a scrolling bar at the top, and a second row of buttons shows the sections of the page you are on.

**Product images:** five unbranded studio photos (motor, pump, control unit, power tool, laptop) are in `assets/products/` as optimized WebP, ready for the upcoming asset pages. `IMAGE_PROMPTS.md` records the prompt and file name for each, in case they need regenerating.

---

## Update 3: Command Center (new home page)

**Where:** the first item in the left menu, **Command Center**. It is now the page the app opens on.

> **Since Update 7** each role has its own Command Center: its own key figures and panels, built from the same data. The five figures below are the original layout; the Admin view is closest to it. See "Command Center for each role" in Update 7. The old Returned assets list is still there under **Product**.

**What it replaces:** a long table of returned assets. The new page shows the same data as charts first, with the table below as the action list.

**Top to bottom**

| Section | What it shows | Click to |
|---|---|---|
| **Data health strip** | Integration health %, how many sources are live, stale or not connected | Open the Source map |
| **Filters** | Tenant, site, asset class, recommended route, time horizon | Filter every number on the page |
| **Needs attention now** | Up to four plain-language lines, such as "41 decisions await approval, 6 close within 5 days" | Filter the table to those assets |
| **Five KPIs** | Assets in scope, potential recovery value, value at risk, CO₂e avoided opportunity, uplift vs baseline. Each has a change vs last month and a sparkline | Filter, or jump to Analytics. Hover for what the number means |
| **Lifecycle portfolio** | Donut of where every asset is in the process | Click a slice or legend row to filter the table |
| **Treatment opportunity** | Bars of predicted volume by recommended route | Click a bar to scope the whole page to that route |
| **Value at risk by reason** | Delayed approval, condition deterioration, missing evidence, market price decline, capacity constraints | Click a reason to see those assets |
| **Assets by time to action** | Donut by days left (under 5, 5–7, 8–10, over 10) | Click a slice |
| **Actions to be prioritised** | Top 10 ranked by predicted value and urgency, with confidence bar, priority and status | Click a row to open the case |
| **Emerging signals** | Closing decision windows, evidence gaps, stale market feed, re-evaluations, parts hotspots, late events | Click to filter or open the related page |
| **Capacity and bottlenecks** | Repair centre, warehouses, inspection queue and execution load, coloured only when tight | Hover for the detail |
| **Value realisation** | Predicted vs actual by month, recovery yield line, plus net recovery, cycle time and CO₂e. Switch between 3, 6 and 12 months | Hover a month |

**Buttons:** **Refresh** (recomputes everything), **Share** (copies the page link), **Export** (opens print, choose *Save as PDF* for a one-page summary). **Ctrl+K** jumps to the search box.

**Same numbers everywhere:** every figure comes from the same 128 live returns and 1,400 closed decisions as Product and Analytics. Awaiting approval is 41 on both pages, and the uplift matches Analytics when the filters match.

**Works on phone, tablet and desktop**
- **Desktop:** five KPIs in a row, four charts in a row, full table.
- **Tablet:** KPIs and charts in two or three columns, table without the extra columns.
- **Phone:** KPIs swipe sideways, charts stack, and each table row becomes a compact card. The side menu becomes a scrolling bar, and the search box takes the full width.
- **Print:** the Export button prints a clean one-pager without menus or buttons.

**Also fixed this round:** the new KPI strip on the Source map shared a style name with Analytics and could have changed how Analytics looked. It now has its own style name, so the two no longer affect each other.

---

## Update 1: Separate systems and CRUD

### Source map tab

**What changed:** the combined cards ("EAM / FSM", "Lease / CRM", "QMS & engineering" and so on) are now **19 separate systems**, each with a real product name.

| System | Product shown |
|---|---|
| CRM | Salesforce Sales Cloud |
| Lease management | Oracle Lease and Finance Management |
| ERP | SAP S/4HANA |
| Procurement | SAP Ariba |
| EAM | IBM Maximo |
| FSM | ServiceNow Field Service Management |
| PLM | Siemens Teamcenter |
| BOM management | Aras Innovator |
| QMS | MasterControl |
| Engineering | Bentley AssetWise |
| WMS | Manhattan Active Warehouse Management |
| Reverse logistics | Optoro |
| Inspection | SafetyCulture |
| Repair management | Fixably |
| Device telemetry | AWS IoT Core |
| Market pricing | Ritchie Bros. Market Data |
| Dealer network | Machinio |
| Recycler partner | Sims Lifecycle Services |
| ESG & carbon | Persefoni |

**Buttons to try**

| Where | Button | What it does |
|---|---|---|
| Top right | **+ Add source** | Opens a form to connect a new system |
| End of each group | **+ Add source** tile | Same, pre-set to that group |
| Each tile | **Edit** | Opens the source: connection, operations, field mapping, history |
| Each tile | **Sync** | Runs a sync now, with a progress bar |
| Each tile | **Delete** | Asks you to type the system name, then removes it. **Undo** appears for 8 seconds |
| Top bar | **Sync all** | Syncs every live source |
| Top bar | Search and filters | Search by system, vendor or owner; filter by category or status |

**Inside the Edit panel** (tabs along the top of the panel)
- **Connection:** name, vendor product, environment, owner, endpoint, authentication. **Test connection** and **Rotate credentials** are here.
- **Operations:** add or remove the read and write calls this system allows.
- **Field mapping:** add, edit or delete rows that map a source field to a canonical field.
- **History:** every sync run and every saved change, with version numbers.
- **Save changes**, **Revert** and **Delete** are at the bottom of the panel. Save stays disabled until something changes.

**Feels live**
- "Updated 6 min 12 s ago" keeps counting up.
- Sources sync on their own every few seconds.
- A **Live sync activity** feed under the tiles shows each sync as it happens.
- Everything also shows up in the **Event stream** tab.

### Workflow studio tab

**What changed:** it now opens on a **list of 31 workflows**, one per system. Nothing is combined.
- **Ingest** workflows: one per source system, from that system into a canonical model.
- **Outbound** workflows: one per system we can write to.
- **Decision** workflows: the three six-gate decision workflows.

**Buttons to try**

| Where | Button | What it does |
|---|---|---|
| Top right | **+ New workflow** | Create an ingest, outbound, decision or blank workflow |
| Each row | **Edit** | Opens the canvas |
| Each row | **Run** | Runs it now, with a live status |
| Each row | **Pause / Resume / Publish** | Changes whether it runs on its trigger |
| Each row | **Copy** | Makes a draft copy |
| Each row | **Delete** | Removes it, with **Undo** |

**In the canvas:** name, trigger and owner are editable. Use **Save**, **Discard**, **Reset to template**, **Validate**, **Run simulation**, **Publish** or **Unpublish**, **Duplicate** and **Delete workflow**. A **Recent runs** table under the list keeps filling as workflows run on their own.

**Linked to the Source map:** adding a source creates a draft workflow for it. Deleting a source makes the workflows that use it fail validation, with a clear message.

---

## Update 2: Live connections, workflow states, tables and health

### Connection methods (Source map tab)

Each source now says **how it connects**, using the six methods from the Celonis list:

| Method | Badge | Settings you will see |
|---|---|---|
| Native connector | Native | Source system, extraction mode, scope, pull interval |
| JDBC extractor | JDBC | Host, port, database, driver, uplink server, schema |
| API extractor (REST / OData) | API | API style, pagination, rate limit, interval |
| Event / Ingestion API | Event API | Delivery type, idempotency key, ordering |
| Delta Sharing | Delta Sharing | Platform, sharing endpoint, share name |
| Flat file upload | Flat file | Format (CSV, Parquet, JSON, ZIP), size limit, SFTP path |

**Where to see it**
- The badge on every tile. Hover it for a one-line explanation.
- The **All methods** filter in the top bar.
- Edit any source and change **Connection method** on the Connection tab. The fields change with it.
- Flat file enforces the **1 GB** limit, and JDBC requires host, port and database before it will save.

### Workflow canvas, Airflow style (Workflow studio tab)

Open any workflow, for example **Ingest · Fixably**, which starts out failing.
- Steps show **green** (success), **red** (failed) or **orange** (upstream failed).
- Lines between steps take the same colours. Lines on a running step animate.
- A **minimap** sits in the corner of the canvas.
- A **Task instances** table below shows each step's state, start, end, duration, try number and pool. Search it, or click a coloured chip to filter by state.
- **Run simulation** replays it step by step. Select a step and use **Fail this step in the next run** to see a failure spread downstream.
- Background runs occasionally fail on their own and recover on the next run, so the red and orange states come and go.

### Source tables tab (new)

A table graph for a system's data, with clusters and foreign keys.
- **System dropdown:** SAP S/4HANA, IBM Maximo, ServiceNow, Manhattan WM, Salesforce, Teamcenter.
- **Hover** a table, a field or a link to see what it is and why Circularity uses it.
- **Drag** a table by its header to move it. **Auto Align** and the zoom buttons are bottom right.
- **Graph / List** toggle. The list view also shows a **Foreign keys** table.
- **Add Tables**, **New Foreign Key**, the **⋮** menu on a table (edit or delete), and **Undo** after deleting.

### Integration health (Source map tab)

- A **KPI strip** across the top: connected sources, tables modelled, workflows published, mappings needing attention, and overall health.
- Under the tiles: **Integration health** (donut plus a 24-hour bar chart), **Mapping exceptions**, and **Recent integration events**. They update as syncs and runs happen.

---

## Two-minute demo script

Sign in as **Admin** to follow every step below (Update 7 has its own role walk-through). Integration changes need the **Developer** or **Admin** account.

1. **Command Center** (after sign-in). Click the **Awaiting approval** slice, then a **Value at risk** reason, then a table row. Resize the window to show the phone layout.
2. **Product → Asset intelligence** (or click an asset ID in Returned assets). Walk the eight tabs, then press **Compare similar assets**.
3. Open **any asset → Treatment Intelligence**. Drag a scenario slider, change an objective weight, tick pathways and press **Compare**, then **Save scenario**.
4. **Integration → Source map.** Point at the KPI strip and the live "Updated … ago" counters.
5. Click the **API / JDBC / Native** badges, or use the **All methods** filter.
6. Click **Edit** on **EAM**, switch **Connection method**, change the owner, press **Save changes**, then open **History**.
7. Click **+ Add source**, fill it in, and **Create connection**. Watch the initial sync.
8. Click **Delete** on that new source, then **Undo**.
9. **Workflow studio.** Open **Ingest · Fixably** to show red and orange failure states and the Task instances table.
10. Click **Run simulation** on a healthy workflow, then **Publish**.
11. **Source tables.** Hover a table and a link, drag one around, then click **New Foreign Key**.

---

## Good to know

- This is a **demo skeleton**. All changes live in the browser and **reset on refresh**. There is no backend.
- **Sign in as a role** (Update 7). Only the **Developer** and **Admin** can add, edit, sync and delete in Integration; Engineer, Finance and Approver see read-only views, and Planners do not see Integration at all.
- **Device telemetry (AWS IoT Core)** is deliberately **not connected**. It shows how an unavailable source looks and how workflows react to it.
- **Market pricing** is deliberately **stale** (expired token). Open it and use **Refresh token and re-sync** to bring it back.
- **Recycler partner** is a **flat file** import, so its Sync button is disabled. It is loaded from the **Manual import** tab.
- The Source tables tab covers six systems. Other systems show no table model yet.
- Vendor and product names are used to make the demo feel real. Data, volumes and run results are synthetic.
- The Command Center uses planning assumptions for capacity limits and the value-at-risk factors. They are labelled as such when you hover, and are easy to change.
- The colours and fonts are the same as before. Update 7 adds no new colours.
