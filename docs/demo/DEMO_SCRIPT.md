# Demo script: one returned asset, start to finish

**For:** the review with the senior stakeholder, the screen recording with an AI voiceover on **20–21 Oct 2026**, and the presentation on **22 Oct**. The demo is standard; only the first two deck slides are tailored to each prospect.
**Length:** about 9 minutes live, plus questions. The recorded video follows the same order in about 4 minutes; its narration is in [`VOICEOVER_SCRIPT.md`](VOICEOVER_SCRIPT.md).
**Record used throughout:** **RT-1048**, a Voltara V4 motor returned by Customer A to Warehouse 1. It is the *happy path*: every signal is in, so it is not waiting in a queue.

> All data in the demo is synthetic. Sign-in and single sign-on are simulated. Claims about integration effort, timelines and model accuracy (the Q&A notes below), the wording about which model learns from which cost line, and who certifies equipment, should be reviewed before they are used with a client; wording about authentication, data provenance, model outputs and accountability should be reviewed by the Legal team.

---

## Before you start

1. Open the demo with presenter mode on: `index.html?presenter=1` (or the hosted link with `?presenter=1`). Presenter mode adds two shortcuts under the sign-in form, a quick switch in the account menu, and *continue as Approver / Finance* buttons in the guide bar at the bottom of the screen. `?presenter=0` turns it off.
2. Use **light mode**, a browser window of about **1440 × 900**, and 100% zoom. Region menu (globe, top bar): **English · UTC**.
3. If you were signed in, choose **Sign out** (account menu, top right). Refresh the page to reset all demo data, so RT-1048 starts awaiting approval.
4. Slides: the user flow ([`user-flow.png`](user-flow.png)) and the Product Owner's **Typical User Journey** ([`user-journey-diagram.png`](user-journey-diagram.png)).

**Without presenter mode**, type the IDs instead: `ops` (planner), `approver`, `finance`, `exec`. Any password works.

---

## The order

| Part | Time | What |
|---|---|---|
| 0 | 1 min | The flow, on one slide |
| 1 | 4.5 min | The happy path: the planner signs in and follows RT-1048 through steps 1 to 10 |
| 2 | 1.5 min | Edge cases: a critical part that cannot be replaced, a customer who needs a new unit, certification shorter than the contract |
| 3 | 1 min | How easy integration is: Source map, manual import from a spreadsheet |
| 4 | 1 min | The Command Center, section by section |
| 5 | 0.5 min | Close |
| — | if asked | Cost, certification, figures, languages, architecture |

---

## 0. The slide (1 min)

Show **User Flow** ([`user-flow.png`](user-flow.png)): the planner signs in, opens Returned assets, picks one asset and follows it through ten steps, the same ten as the Typical User Journey.

> "When a leased asset comes back, today separate teams decide whether to sell it or scrap it. Here is the journey instead. Nobody types data in: as each signal arrives (receipt, diagnostics, certification) Circularity builds up the picture, and only when it is complete does it put a value on the routes. We'll follow one motor that has every signal in."

---

## 1. The happy path (4.5 min)

1. On the sign-in form, press **End user** (or type `ops` and any password). You land on **Returned assets**.

   > "The planner sees what has come back. Every row shows its signals: received, diagnostics, certification, and only then an economic path. This one has all four. Others are still waiting for EAM diagnostics, so they are not priced yet."

   Point to the **Status** column: RT-1048 *4/4 · ready*; RT-1051 *1/4 · awaiting EAM*, *Not priced yet*.

2. The strip under the top bar reads **Journey · RT-1048** with **Start** and steps **1 to 10**. Press **Continue to step 1** in the bar at the bottom.

### Step 1 · Supply evidence

3. Asset Intelligence opens on **Retrieved data**; nothing predicted is on this page. The bar at the bottom moves on to **Predictions**.

   > "Step one is what the enterprise systems tell us. Grade B from the EAM diagnostics. Certified for 24 months in QMS: the diagnostic and quality process certifies the motor, after any part is replaced; Circularity reads that certificate, it does not certify anything. And the cost inputs."

   Point to **Cost inputs**: catalogue value from PLM, the **RMA** from Order Management, the repair scope from EAM, the **contracted part prices** from procurement.

   > "That is how we get the cost: the product value from the catalogue, the return authorisation from order management, what needs repairing from diagnostics, and the part prices from the supplier contracts."

### Steps 2 and 3 · Build alternatives, predict outcomes

4. **Continue to step 2**: the **Predictions** page opens, with *Eligibility and gates* and *Matched demand* outlined.

   > "Six of seven routes are eligible. And there is demand: Customer A's contract needs a replacement at Site 3, order SO-48102. The contract accepts a certified refurbished motor; if it asked for a new one, we could not use this unit. It needs 24 months of certified life, and this motor has 24."

5. **Continue to step 3**: life and economics are outlined.

   > "Thirty to forty months of life, and a value for every route. The preparation cost, $1,800, is the contracted parts plus predicted labour and transfer."

### Step 4 · Optimize plan

6. **Continue to step 4**: Treatment Intelligence step 2, **Possible outcomes**: the **All pathways** table first, then the recommended one.

   > "Every option is here: redeploy to Customer A at $9,600, sell, re-lease, recover parts, recover material, a responsible exit, and the one a gate withheld, with its reason."

### Step 5 · Plan approval

7. **Continue to step 5**. Press **Submit for review**, then **Presenter: continue as Approver** in the bottom bar. **Approve redeployment**, reason *Matches Customer A's contract replacement order SO-48102*, tick the evidence box, **Approve and send instruction**.

### Steps 6 to 9 · Send instruction, create work, repair and certify, return the outcome

8. **Continue to step 6**, then step 7: **Simulate system acknowledgement**. Row 1: *Sales order SO-48102 returned by ERP*.
9. Step 8: press it again. Row 2: *Work order WO-… returned by EAM · repaired, tested and certified; QMS record updated*.
10. Step 9: press it twice more (WMS transfer, ERP order fulfilled).

    > "We send the approved plan. From there, their systems decide how the work is done, and send back the references: the sales order, the work order, the transfer, the fulfilment."

### Step 10 · Reconcile & learn

11. **Continue to step 10**. **Presenter: continue as Finance**, then **Confirm outcome** in the handoff panel.

    > "Predicted $9,600 against SO-48102, actual $9,230. Preparation cost $270 more than predicted, so the cost model learns from it. Each line names the model that learns."

---

## 2. Edge cases (1.5 min)

12. Click box **4** in the strip, scroll to **What-if and edge cases**.
13. Press **Critical part unavailable**.

    > "Now a different motor: the critical part has failed and no replacement is available in the supplier contracts, so nobody can re-certify its life. Redeploying, re-leasing or selling it whole are withheld, each with the reason, and recovering its parts comes first."

    Press it again to turn it off.
14. Press **Customer requires a new unit**.

    > "Or the demand line asks for a new motor. A refurbished one cannot be supplied, so redeploy is withheld."

15. *Optional:* **Certification shorter than demand**: redeploy becomes *Conditional: needs re-certification*.

---

## 3. How easy integration is (1 min)

16. Sidebar → **Integration → Source map** (sign in as `admin` or `developer` if needed).

    > "Each system the customer already has connects through one adapter per system type: ERP, EAM, WMS, QMS, CRM, procurement."

17. **Integration → Manual import**: **Load sample file**, **Validate**, then **Load … rows for evaluation**.

    > "And where there is no connector yet, even a spreadsheet works: the rows are checked, the bad ones rejected with a reason, and the good ones loaded as manual evaluation data."

---

## 4. The Command Center (1 min)

18. Account menu → **Presenter: switch to Executive** (or sign in as `exec`). The **Command Center** opens on **Key figures**.

    > "For senior management. The first page has the key figures, the portfolio charts and value realisation; exceptions are their own page in the sidebar. *What these figures mean* explains every number."

19. Sidebar → **Exceptions**: click a **Warehouse 1** row, then **Notify owner** to *Planner · Customer A*.

    > "When something in steps one to five goes wrong (missing evidence, a failed gate, a delayed approval) it shows here, by warehouse, and they hand it to the person who acts."

---

## 5. Close (30 s)

> "One asset, ten steps: what the systems told us, every option, the plan, who approved it, the orders their systems created, and what it returned, line by line. No data entry; the same journey runs for every unit, in any language, time zone and currency."

---

## If something goes wrong

| Problem | Fix |
|---|---|
| The strip shows no step links | You are on a page outside the journey. Open `#/product/received?focus=RT-1048` |
| RT-1048 was already approved earlier in the session | Refresh the page: all data resets. Sign in again |
| A step says *Not reached yet* | Expected: it says what has to happen first. Go to the ringed box |
| An edge-case button is still pressed | Press it again, or **Reset to base** |
| The screen is in another language | Globe menu (top bar) → Language → English |
| The shortcuts under the sign-in form are missing | Add `?presenter=1` to the address, before the `#` |
| Photos don't show | Use the hosted link or the full zip with the `assets` folder |

---

## Questions you may get

**"How do you get the cost?"** From the systems that own it: product value from the PLM/ERP catalogue; the return authorisation (RMA) from order management, which handles forward and reverse orders; the receipt from WMS; the repair scope from EAM diagnostics; part prices from the supplier contracts in procurement. Circularity predicts labour and transfer on top (Asset Intelligence → Cost inputs, and *How the preparation cost is built*).

**"Do you certify the equipment?"** No. The diagnostic and quality systems (EAM, QMS) certify after inspection and any part replacement. Circularity reads the certificate and checks that it covers what the contract needs.

**"Why redeploy instead of selling?"** Only where a customer's contract accepts a certified refurbished unit, and the certified life covers the contract. A demand line that needs a new unit is never matched.

**"What is Value at risk?"** Predicted recovery value on open returns that would be lost in the next 30 days if nobody acts, by reason: missing evidence, condition getting worse, delayed approval, falling prices, capacity.

**"What about uplift?"** Hidden for now. If asked: *extra value recovered compared with selling as-is or scrapping*, on closed decisions (Analytics shows it).

**"Other languages, time zones, currencies?"** The globe menu: language (a preview of the menu and the journey), time zone, local currency.

**"Is this plug-and-play?"** One adapter per system type into a common data model; approved instructions go back. Backend by 31 Oct; trial run by 15 Nov. *Have this reviewed before using it with a client.*

**"Is this real customer data?"** No. Everything is synthetic.

---

## Notes for the build team

- Hidden for now, still in the code: `FEAT.uplift` and `FEAT.pools` in `index.html`.
- Step links are `JG` (`?jstep=N`); edge cases are `TI_PRESETS` (`ecm`, `newonly`); signals are `sigOf`; the Region menu is `rgMenuHTML`. Decisions J1–J10 are in `docs/feature-demo-refactor-iter-three.md`.
- The internal role list is still at `#/signin?roles`.
