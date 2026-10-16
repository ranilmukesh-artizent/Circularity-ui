# Demo script: one returned asset, start to finish

**For:** the in-person review with the Product Owner on Monday 19 Oct 2026, the stakeholder meeting on Monday or Tuesday that week, and the sales recording before the IFS meeting on 29 Oct.
**Length:** about 8 minutes, plus questions.
**Record used throughout:** **RT-1048**, a Voltara V4 motor returned by Customer A to Warehouse 1.

> All data in the demo is synthetic. Sign-in and single sign-on are simulated. Claims about integration effort, timelines and model accuracy (the Q&A notes below), and the wording about which model learns from which cost line, should be reviewed before they are used with a client; wording about authentication, data provenance, model outputs and accountability should be reviewed by Kinective's Legal team.

---

## Before you start

1. Open the demo with presenter mode on: `index.html?presenter=1` (or the hosted link with `?presenter=1`). Presenter mode adds two small shortcuts under the sign-in form, a quick switch in the account menu, and *continue as Approver / Finance* buttons in the guide bar at the bottom of the screen. It is remembered on that browser; `?presenter=0` turns it off.
2. Use **light mode**, a browser window of about **1440 × 900**, and 100% zoom.
3. If you were signed in, choose **Sign out** (account menu, top right). Refresh the page to reset all demo data, so RT-1048 starts awaiting approval.
4. Have the slides ready: the user flow ([`user-flow.png`](user-flow.png), SVG [`user-flow.svg`](user-flow.svg), editable Mermaid in [`user-flow.md`](user-flow.md)), and the Product Owner's **Typical User Journey** diagram ([`user-journey-diagram.png`](user-journey-diagram.png)). [`journey-slide.png`](journey-slide.png) is the same ten boxes tagged with the screen that shows each one.

**Without presenter mode**, type the IDs instead: `ops` for the end user, `approver`, `finance`, `exec` for senior management. Any password works.

---

## The order

| Part | Time | What |
|---|---|---|
| 0 | 1 min | The flow, on one slide |
| 1 | 5.5 min | The end user: sign in, Returned assets, RT-1048 through steps 1 to 10 |
| 2 | 1 min | The side dashboard: exceptions by warehouse, notify the owner |
| 3 | 0.5 min | Close |
| — | if asked | Architecture, adapters, model performance |

---

## 0. The slide (1 min)

Show **User Flow** ([`user-flow.png`](user-flow.png)): *Sign in → Returned assets → 1. Supply evidence … 10. Reconcile & learn*, the same ten boxes as the Typical User Journey. The Exceptions dashboard sits beside the journey, not in it.

> "When a leased asset comes back, today separate teams decide whether to sell it or scrap it, and nobody can see what it was worth. Here is the journey instead. You sign in, you see what has come back, you pick one asset and follow it through ten steps. Every step on screen is clickable and has the same number as on this slide. Problems in the first five steps show up on a side dashboard for executives and planners; we'll come to that at the end."

---

## 1. The end user, through the journey (5.5 min)

1. On the sign-in form, press **End user** (or type `ops` and any password, then **Sign in**). You land on **Returned assets**.

   > "The person who does the work signs in and sees their returned assets."

   The strip under the top bar reads **Journey · RT-1048** with **▶ Start** and boxes **1 to 10**. Filled boxes are done for this asset, the ringed one is where it is now, dimmed ones are still to come. The bar at the bottom says what this step established and what comes next; press **Continue** there (or **Next** on the strip, or click any box).

| Step | Screen | What to point at |
|---|---|---|
| ▶ Start | Returned assets | RT-1048 marked *Start here* |
| 1 Supply evidence | Asset Intelligence, left side | Retrieved from EAM, QMS, ERP, WMS, PLM; the right side waits |
| 2 Build alternatives | Asset Intelligence, eligibility and matched demand | Six gates, 6 of 7 routes, SO-48102 at Site 3, LS-5530 |
| 3 Predict outcomes | Asset Intelligence, life and economics | 30–40 months, value by route |
| 4 Optimize plan | Treatment Intelligence, step 2 | **All pathways**: every route, the withheld one with its reason |
| 5 Plan approval | Step 5, decision card | Submit, then the Approver approves |
| 6 Send instruction | Step 5, instruction | What goes to ERP, EAM and WMS |
| 7 Create execution work | Handoff rows 1–2 | ERP returns **SO-48102**; EAM returns a **WO** |
| 8 Repair & certify | Handoff row 2 | *Repaired, tested and certified; QMS record updated* |
| 9 Action & return outcome | Handoff rows 3–4 | WMS transfer, ERP order fulfilled |
| 10 Reconcile & learn | Reconcile and learn block | Predicted vs actual, line by line, and which model learns |

### ▶ Start · Returned assets

2. RT-1048 is the first row, marked **Start here**.

   > "A leased motor came back to Warehouse 1 on 3 October. We pick it and follow its journey."

   *Optional:* press **Group by product**: *Voltara V4 motor · Customer A · 15 units*. "This customer returned fifteen of the same motor. Each one gets its own journey." Press **List** to go back.

### Step 1 · Supply evidence (enterprise systems)

3. **Continue to step 1**. Asset Intelligence opens with the left side, **Retrieved from enterprise systems**, outlined.

   > "Step one: the enterprise systems supply the evidence. Condition from EAM, Grade B. A certified period of 24 months from QMS. Received under a WMS receipt, back from a lease that has ended. This motor has been back twice before. We read this data; we don't own it."

   Point to the right side: **Not evaluated yet**. "Nothing is priced yet. That side fills in as we go." Read the bottom bar: *Grade B from EAM, certified for 24 months (QMS-2906), received at Warehouse 1, returned twice before.*

### Step 2 · Build alternatives (Circularity)

4. **Continue to step 2**. The **Eligibility and gates** and **Matched demand** cards are outlined.

   > "Step two is ours. Circularity links the evidence and works out what is possible: six gates passed, six of seven routes eligible, and there is demand: a confirmed order, SO-48102, at Site 3, and a re-lease opportunity."

### Step 3 · Predict outcomes (Circularity)

5. **Continue to step 3**. Remaining useful life and economic intelligence are outlined.

   > "Step three: how long it will last, 30 to 40 months, and what each route is worth. Every figure says which model or rule produced it."

### Step 4 · Optimize plan (Circularity)

6. **Continue to step 4**. Treatment Intelligence opens at **Recommended outcome**, with **All pathways** outlined underneath.

   > "Step four: every option is on the table. Redeploy to Site 3 is recommended at $9,600, but you also see selling, re-leasing, recovering parts, recovering material and a responsible exit, and the one we withheld: selling parts externally, because there's no confirmed buyer within 30 days."

   *Optional:* step 4 of the page, drag **Preparation, parts and fees** to show the what-if card and the top pathways side by side.

### Step 5 · Plan approval (human in the loop)

7. **Continue to step 5**. As the Planner, press **Submit for review**.

   > "Step five is a person. The planner submits; one approver decides, and sees exactly what will be sent."

8. In the bottom bar, press **Presenter: continue as Approver**. Press **Approve redeployment**, type a reason (at least 15 characters, e.g. *Matches confirmed order SO-48102*), tick the evidence box, **Approve and send instruction**.

### Step 6 · Send instruction

9. **Continue to step 6**. The instruction is outlined.

   > "Step six: we send the approved plan to ERP, EAM and WMS. From here, their systems decide how the work is carried out; we receive references and acknowledgements."

### Steps 7 to 9 · Create execution work, repair and certify, return the outcome (enterprise systems)

10. **Continue to step 7**. Press **Simulate system acknowledgement**. Row 1 now reads **Sales order SO-48102 returned by ERP**.
11. **Continue to step 8**. Press it again. Row 2 reads **Work order WO-… returned by EAM · repaired, tested and certified; QMS record updated**.

    > "The redeployment is against that sales order; the refurbishment is a work order in EAM. Those numbers come from their systems."

12. **Continue to step 9**. Press it twice more (WMS transfer, ERP order fulfilled).

    > "The motor is moved to Site 3 and ERP reports the order fulfilled, with the actual costs."

### Step 10 · Reconcile & learn (Circularity)

13. **Continue to step 10**. In the bottom bar, press **Presenter: continue as Finance**, then **Confirm outcome** in the handoff panel. The **Reconcile and learn** block fills in.

    > "Step ten: predicted $9,600 against SO-48102, actual $9,230. And we can see where the difference came from: preparation cost $270 more than predicted, service a bit more, residual value a bit better. Each line names the model that learns from it. The avoided purchase price came from ERP, so there's nothing for a model to learn there."

14. *Optional:* click box **1**, then the **Asset Intelligence** right side: the commercial value now reads **Predicted vs actual**, against SO-48102.

---

## 2. The side dashboard (1 min)

15. Account menu → **Presenter: switch to Executive** (or **Sign out** and type `exec`). You land on the **Circularity Command Center**.

    > "Executives and planners have a dashboard on the side of the journey. When something goes wrong in steps one to five, missing evidence, a failed gate, a delayed approval, a capacity problem, it shows up here."

16. Scroll to **Exceptions by warehouse** and click a **Warehouse 1** row. The drawer shows only **Warehouse · Item · Value**. Press **Notify owner**, choose **Planner · Customer A**, **Send notification**.

    > "They assign it to the person who acts, who opens that asset's journey from Returned assets."

---

## 3. Close (30 s)

> "One asset, ten steps: what the systems told us, every option we found, the plan, who approved it, the orders their systems created, and what it returned, line by line. The same journey runs for every unit of every product."

---

## If something goes wrong

| Problem | Fix |
|---|---|
| The strip shows no step links | You are on a page outside the journey (for example the Command Center). Open `#/product/received?focus=RT-1048`, or click RT-1048 in Returned assets |
| RT-1048 was already approved earlier in the session | Refresh the page: all data resets. Sign in again |
| A step says *Not reached yet* | That is expected: it says what has to happen first. Go back to the step where the asset is (the ringed box) |
| You land on the wrong page after sign-in | Account menu → **Sign out**, then sign in again; each account opens on its own home |
| The shortcuts under the sign-in form are missing | Add `?presenter=1` to the address, before the `#` |
| Photos don't show | The page was opened without the `assets` folder. Use the hosted link or the full zip |
| An approver or Finance button is missing | Only the Approver approves and only Finance confirms; use the **Presenter: continue as …** buttons in the bottom bar |

---

## Questions you may get

**"Is this plug-and-play, or a massive integration?"** Circularity reads from the systems the customer already has, through one adapter per system type (ERP, EAM, WMS, QMS, CRM, lease management and so on), into a common data model, and sends approved instructions back. The demo's Source map shows 19 source types. *Have this claim reviewed before using it with a client.*

**"Which adapters exist?"** Adapters are planned to be ready by **31 Oct**. Until then, every connection in the demo is simulated (vendor names make it realistic, but nothing is connected).

**"Who decides how the work is done?"** The enterprise systems. Circularity sends the approved plan and records the references and acknowledgements they return (sales order, work order, transfer, fulfilment).

**"How does it learn?"** Each cost line of the actual outcome is compared with its prediction, and the model that made that prediction learns from the difference (step 10). Analytics → *Predicted vs actual* shows the same across closed decisions. Keep this for questions; do not lead with accuracy figures.

**"When can we try it?"** A POC or MVP by **15 Nov**.

**"Is this real customer data?"** No. Everything is synthetic: *Northfield Industrial Leasing*, three customer tenants, eight sites.

**"Can a user see other customers' assets?"** No. A Planner sees only their own customer; access to another one is requested and approved.

---

## Recording the sales video

After the dry run, record the same path (parts 0 to 3) as a 3–4 minute screen recording at 1440 × 900 in light mode, with presenter mode on. Refresh before recording so RT-1048 starts awaiting approval.

## Notes for the build team

- The steps follow the Product Owner's **Typical User Journey** diagram. The step links are `JG` in `index.html` (`?jstep=N`, with the targets in `JG_TGT`), the guide text is built by `jgEst` and `jgWait`, and the journey strip names are `JSTEPS`. Decisions H1–H10 are in `docs/feature-demo-refractor-iter-two.md`.
- The internal role list is still at `#/signin?roles`.
