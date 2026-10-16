# Demo script: one returned asset, start to finish

**For:** the stakeholder demo on Monday 19 Oct 2026, the dry run on Saturday 17 Oct, and the sales recording before the IFS meeting on 29 Oct.
**Length:** about 8 minutes, plus questions.
**Record used throughout:** **RT-1048**, a Voltara V4 motor returned by Customer A to Warehouse 1.

> All data in the demo is synthetic. Sign-in and single sign-on are simulated. Claims about integration effort, timelines and model accuracy (the Q&A notes below) should be reviewed before they are used with a client; wording about authentication, data provenance and model outputs should be reviewed by Kinective's Legal team.

---

## Before you start

1. Open the demo with presenter mode on: `index.html?presenter=1` (or the hosted link with `?presenter=1`). Presenter mode adds two small shortcuts under the sign-in form and a quick switch in the account menu. It is remembered on that browser; `?presenter=0` turns it off.
2. Use **light mode**, a browser window of about **1440 × 900**, and 100% zoom.
3. If you were signed in, choose **Sign out** (account menu, top right). Refresh the page to reset all demo data.
4. Have the slides ready: the Product Owner's **Typical User Journey** diagram ([`user-journey-diagram.png`](user-journey-diagram.png)) and, as a backup, the same ten boxes tagged with the screen that shows each one ([`journey-slide.svg`](journey-slide.svg)). The user flow as built, including sign-in and the executive's notification, is [`user-flow.svg`](user-flow.svg) (editable Mermaid in [`user-flow.md`](user-flow.md)).

**Without presenter mode**, type the IDs instead: `exec` for senior management, `ops` for the end user, `approver`, `finance`. Any password works.

---

## The order

| Part | Time | What |
|---|---|---|
| 0 | 1 min | The problem, on one slide |
| 1 | 1.5 min | Senior management: exceptions by warehouse, notify the owner |
| 2 | 5 min | The end user: RT-1048 through the ten journey boxes |
| 3 | 0.5 min | Close |
| — | if asked | Architecture, adapters, model performance |

---

## 0. The slide (1 min)

Show the **Typical User Journey** diagram ([`user-journey-diagram.png`](user-journey-diagram.png)): ten boxes from *1. Supply evidence* to *10. Reconcile & learn*.

> "When a leased asset comes back, today separate teams decide whether to sell it or scrap it, and nobody can see what it was worth. Here is the journey we want instead. We'll follow one returned motor through it, and every screen you'll see maps to these boxes; the numbers on screen are the box numbers."

---

## 1. Senior management (1.5 min)

1. On the sign-in form, press **Senior management** (or type `exec` and any password, then **Sign in**). You land on the **Circularity Command Center**.

   > "This is what a senior manager sees: value recovered, uplift over the old way, avoided spend. No line items."

2. Scroll to **Exceptions by warehouse**.

   > "When something needs attention, they see which warehouse, what item, and what value."

3. Click the **Warehouse 1 · Warehouse bottleneck** row. The drawer shows only **Warehouse · Item · Value**. Point to **RT-1048 Voltara V4 motor**.
4. Press **Notify owner**. Choose **Planner · Customer A**, keep or edit the message, **Send notification**.

   > "If it isn't being actioned, they assign it. That's all the executive does."

---

## 2. The end user, through the journey (5 min)

5. Account menu (top right) → **Presenter: switch to Planner · Customer A** (or **Sign out**, then **End user**, or type `ops`). You land on **Returned assets**.

   > "Now the person who does the work. They sign in and land on their returned assets. The executive's note is right at the top."

   A **Demo path · user journey** bar sits under the top bar. Each stop shows the diagram's box number(s), and the journey strip below it lights up the same boxes. From here, press **Next** on that bar to move on.

| Stop | Journey box | Screen |
|---|---|---|
| ▶ | Start | Returned assets, RT-1048 marked *Start here* |
| 1 | Supply evidence | Asset intelligence, left side (retrieved) |
| 2–3 | Build alternatives · Predict outcomes | Asset intelligence, right side (predicted) |
| 4 | Optimize plan | Treatment Intelligence, step 2 |
| 5 | Plan approval | Step 5, approval |
| 6–9 | Send instruction → Action & return outcome | Step 5, enterprise handoff |
| 10 | Reconcile & learn | Analytics, *Predicted vs actual* |

### ▶ Start · Returned assets

6. RT-1048 is the first row, marked **Start here**.

   > "A leased motor came back to Warehouse 1 on 3 October."

   *Optional:* press **Group by product**: *Voltara V4 motor · Customer A · 15 units*. "This customer returned fifteen of the same motor. Each one gets its own decision. The same works for a hundred." Press **List** to go back.

### Box 1 · Supply evidence (enterprise systems)

7. **Next**. Asset intelligence opens on the left side, **Retrieved from enterprise systems**.

   > "Box one: the enterprise systems supply the evidence. Condition from EAM, Grade B. A certified period of 24 months from QMS. The lifecycle from ERP, EAM and WMS. Specs from PLM. This motor has been back before: here's its return history. We don't own this data, we read it."

   Point to the grey **Retrieved · EAM / QMS** badges.

   *Optional:* the **Unit** selector at the top lists all 15 Voltara motors from Customer A, each with a different grade and route. Switch to one, then back to SN6399949.

### Boxes 2–3 · Build alternatives, predict outcomes (Circularity)

8. **Next**. The right side, **Predicted and computed by Circularity**, is highlighted.

   > "Boxes two and three are ours. Circularity links the evidence, works out which treatments are eligible, and predicts each one: 30 to 40 months of remaining life, and the value on each route. Every figure here says which model or rule produced it."

   Point to the black **Model · …** badges and the **Eligibility and gates** card.

### Box 4 · Optimize plan (Circularity)

9. **Next**. Treatment Intelligence opens at step 2, **Recommended outcome**.

   > "Box four: compare the net value across routes, timing and capacity, and pick the plan. Redeploy to Site 3 for an order we already have, $9,600, $4,800 more than selling it as-is."

   *Optional:* step 4, drag **Preparation, parts and fees** to show the what-if card and the pathways side by side.

### Box 5 · Plan approval (human in the loop)

10. **Next**. Step 5. As the Planner, press **Submit for review**.

    > "Box five is a person. The planner submits; one approver decides, and sees exactly what will be sent."

11. In the Demo path bar, press **Presenter: continue as Approver**. Point to the **instruction preview** (ERP Order Management first). Press **Approve redeployment**, type a reason (at least 15 characters, e.g. *Matches confirmed order SO-48102*), tick the evidence box, **Approve and send instruction**.

### Boxes 6–9 · Send instruction → Action & return outcome

12. **Next**. The page moves to **Enterprise handoff**. Press **Simulate system acknowledgement** four times (ERP order, EAM work, WMS transfer, ERP fulfilment).

    > "Box six is us sending the approved plan. Seven to nine are their systems: EAM and ERP create the work, the motor is repaired and certified, and the outcome comes back. We don't replace those systems."

13. Press **Presenter: continue as Finance**, then **Confirm outcome**.

### Box 10 · Reconcile & learn (Circularity)

14. **Next**. Analytics opens on **Predicted vs actual**.

    > "Box ten: the actual result is linked to the decision and compared with the forecast, across every closed decision. That's how the models get better for the next motor."

---

## 3. Close (30 s)

> "One asset, ten boxes: what the systems told us, what we predicted, the plan, who approved it, what the systems did, and what it returned. The same flow runs for every unit of every product."

---

## If something goes wrong

| Problem | Fix |
|---|---|
| The demo path bar is missing | You are on another record or page. Open `#/product/received?focus=RT-1048` and press **Next**, or click any stop on the bar |
| RT-1048 was already approved earlier in the session | Refresh the page: all data resets. Sign in again |
| You land on the wrong page after sign-in | Account menu → **Sign out**, then sign in again; each account opens on its own home |
| The shortcuts under the sign-in form are missing | Add `?presenter=1` to the address, before the `#` |
| Photos don't show | The page was opened without the `assets` folder. Use the hosted link or the full zip |
| An approver button is missing | Only the Approver approves and only Finance confirms; use the **Presenter: continue as …** buttons in the Demo path bar |

---

## Questions you may get

**"Is this plug-and-play, or a massive integration?"** Circularity reads from the systems the customer already has, through one adapter per system type (ERP, EAM, WMS, QMS, CRM, lease management and so on), into a common data model, and sends approved instructions back. The demo's Source map shows 19 source types. *Have this claim reviewed before using it with a client.*

**"Which adapters exist?"** Adapters are planned to be ready by **31 Oct**. Until then, every connection in the demo is simulated (vendor names make it realistic, but nothing is connected).

**"How good are the predictions?"** Analytics → *Predicted vs actual* compares predicted value with what was recovered on closed decisions. Keep this for questions; do not lead with it.

**"When can we try it?"** A POC or MVP by **15 Nov**.

**"Is this real customer data?"** No. Everything is synthetic: *Northfield Industrial Leasing*, three customer tenants, eight sites.

**"Can a user see other customers' assets?"** No. A Planner sees only their own customer; access to another one is requested and approved.

---

## Recording the sales video

After the dry run, record the same path (parts 0 to 3) as a 3–4 minute screen recording at 1440 × 900 in light mode, with presenter mode on. Refresh before recording so RT-1048 starts awaiting approval.

## Notes for the build team

- The stops follow the Product Owner's **Typical User Journey** diagram (decision E7, answered 16 Oct). The stops are `DP_STOPS` in `index.html`, and the journey strip names are `JSTEPS`.
- The internal role list is still at `#/signin?roles`.
