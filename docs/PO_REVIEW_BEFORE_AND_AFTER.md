# Circularity: before and after the Product Owner review

**For:** the Product Owner review, 2026-10-15 · **Branch:** `feature/guided-flow` (commit `408da8e`) · **Full detail:** [`CHANGES.md` → Update 8](../CHANGES.md) · **Plan and open questions:** [`PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md`](PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md)

> All data is synthetic. Kinective's Legal team should review the new roles, the identity wording and the positioning statement ("decision intelligence, not an execution system") before they are used with clients.

## In one line

**Before:** every screen had the right information, but the user had to hunt for it. **After:** each user starts on a view built for their job, the decision page reads top to bottom, and it is clear that Circularity **recommends** while ERP, EAM and WMS **carry out the work**.

## What was there, what was wrong, what we did

| # | Area | Before | Problem | Now | Why it is better |
|---|---|---|---|---|---|
| 1 | **Command Center for leaders** | Admin mixed headline figures with operational queues. Net recovery, uplift, yield, avoided spend and CO₂e were only in the Finance view | A CEO or COO had to be "Finance" to see value, and had to scroll past approval queues | New **Executive** account: value figures on top (the same numbers as Finance), portfolio health and ranked **Exceptions** (value at risk, warehouse bottlenecks, declining metrics, deteriorating condition), each with **View cases** and **Notify owner**. Queues are hidden unless asked for. Admin gets a **Senior / Operational** switch | Leaders see value and problems first, drill into the cases, and pass the problem to the right person in one click |
| 2 | **Command Center for operations** | Queues were not personal and not scoped to a site | Planners, Engineers and warehouse staff saw everything and had to filter it themselves | **Actions on me** first, then *Waiting for approval* and *Handed off, awaiting outcome* (with target system, reference and age). Planner and Engineer start on their home site. The new **Warehouse Manager** is locked to one warehouse | Each person opens the app to their own to-do list. A notification from a leader lands there, and the leader sees "In hand by …" |
| 3 | **Expected returns** | Looked like inventory or inspection signals | Wrong source: returns are known from contracts and leases, not inspections | Comes from the **Contract Management** application: Contract ID, Customer, Lease period, Contract expiry, Source. Adds the **likely outcome** (return, buyout, extension or early end) with a probability and a return window | Planners can trust where the forecast comes from, and the forecast reflects that not every lease end is a return |
| 4 | **Decision (treatment) page** | Five side-by-side panels plus a long "Detailed analysis" | The reader jumped around to work out status → answer → reason → action | **Five guided steps**: 1 asset and status (why, and what is outstanding) → 2 recommended outcome → 3 why → 4 what-if and edge cases → 5 approval and handoff. A sticky step bar; decision buttons only in step 5 | Anyone can read a case like a story, in the order a decision is actually made |
| 5 | **Condition, life and value** | Remaining useful life was buried in gate notes or a small column | Nobody could see whether the commercial plan fits how long the asset will last | One card: **A** diagnostic condition (e.g. winding Grade B) → **B** estimated life **30–40 months** next to the **certified 24 months** → **C** value for that life with the matched order (*SO-48102 at Site 3*). If demand needs longer than the certified period, it says **Needs re-certification** | Links engineering to money, and stops us promising a lease longer than the asset is certified for |
| 6 | **What-if** | The result was a small "Scenario impact (preview)" text box | Easy to miss the financial impact | A large card: **Base · Simulated · Δ $ · Δ %** with ▲ ▼, live while dragging, plus the assumptions changed. Presets: *Demand cancelled*, *Parts +30%*, *Resale −20%*, *Certification shorter than demand* | The impact is impossible to miss, and edge cases are one click away |
| 7 | **Close calls between options** | Ranking was by net value only | When two routes were worth about the same, nothing explained the choice | A **Close call** box (within 5% or $250) names the deciding factor: risk/confidence → demand certainty → cycle time → remaining life → carbon. A side-by-side comparison opens by itself. Confidence shows as **High / Medium / Low** with what to do | Recommendations are explainable even when money alone does not decide |
| 8 | **Approval** | The instruction payload was visible only after approval | The Approver approved without seeing what would be sent | An **instruction preview** before approval (what ERP, EAM or WMS will receive, plus the raw payload). It matches what is sent afterwards | The person approving knows exactly what will be sent. This follows OWASP guidance for AI agent actions |
| 9 | **Behind the screen** | Demos showed results, not how they were produced | Customers could not see how agents and services work together | New **Process orchestration** page with ten stages (pull data → prepare → gates → predictions → optimise → recommend → approve → hand off → outcome). Each stage shows its agent, sources, status and timing, with **Replay** and **Simulate failure**, and it is built from the real audit trail | A transparent demo story that shows how a recommendation is made |
| 10 | **Positioning wording** | "Executing", "Execution timeline", "Executed" | Implied that Circularity does the physical work | **Handed off**, **Enterprise handoff**, **Handoff readiness**. Each step names its system: Redeploy → **ERP Order Management**, Repair → **EAM**, Return to stock → **WMS putaway** | Matches what the product really is: decision intelligence that instructs enterprise systems |
| 11 | **Users and SSO** | Simulated sign-in only. "How do I add users?" had no answer | No story for enterprise identity | **Access → Identity and users**: identity provider (Entra ID as an example), SSO → provisioning (SCIM) → role mapping, **Sync from directory**, group-to-role mapping, a leaver who loses access, escalation and out-of-office delegation | Answers the question: users and roles come from the customer's directory; they are not typed into the app |

## Also done earlier (context for this review)

- **Role-based views (Update 7):** sign in as a role; each role sees only its own pages and buttons. A Planner is locked to their customer, Admin delegates approvals, and Finance can comment.
- **Product guide:** `README.md`, written for the Product Owner, executives and client pitches.

## How we know it works

- **208 / 208** role checks and **110 / 110** guided-flow checks pass in an automated browser run.
- No page scrolls sideways at phone width (390 px). Light and dark modes both checked.
- All 128 seeded recommendations are unchanged, and figures match across pages (for example, the Executive figures equal Finance's; 38 items handed off on every page that counts them).

## Three-minute demo for this meeting

1. **Executive** → Exceptions → *Warehouse 1 bottleneck* → **Notify owner**.
2. Switch to **Warehouse Manager · Warehouse 1** → it is first in **Actions on me** → **Acknowledge**. Back as Executive: *In hand by …*.
3. **Approver** → **RT-1048**: read steps 1 → 5, drag a what-if slider, check the instruction preview, then **Approve**.
4. **RT-1094**: the **Close call** explanation.
5. **Process orchestration** → **Replay**.

## Decisions we need from you

These are built on a sensible default and marked *(assumed)* in the app until you confirm them. The full list (D2, D5–D20) is in the plan.

1. **Close call:** is "within 5% or $250" the right threshold, and is the factor order right? Should Admin be able to change it?
2. **Certification:** may a lease or demand horizon ever be longer than the certified period? (Today: no; the route becomes Conditional.)
3. **Lease data:** do customer contracts include past buyouts and extensions? (The likely-outcome forecast needs them.)
4. **Identity:** which identity providers at launch (Entra ID, Okta)? Is automatic provisioning (SCIM) required?
5. **Executive:** besides the Command Center, what may the Executive open?
6. **Resale slider:** should it be split into *Resale price* and *Lease income*?
7. **Still needed:** the **user journey diagram** you mentioned, and what "**increase the count of the rows… with the same button**" referred to.
