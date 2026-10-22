# Video script: the agentic decision layer for assets that come back

**For:** a recorded, business-outcome demo for an enterprise (Fortune 500) audience. **Length:** 6 minutes (7 at most). **Build:** branch `feature/live-run` (agent-first, live run board). **Recorded version:** [`video/circularity-agentic-demo.mp4`](video/circularity-agentic-demo.mp4) (5:13, generated from the UI with a public-domain synthetic voice; adds four short lines to the scenes below; how to regenerate it is in [`video/pipeline/README.md`](video/pipeline/README.md)). **Record used:** **RT-1048**, a returned industrial motor; the same record as [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

> **Review before release.** The video shows the product as a live, connected application, names enterprise software vendors on screen, and shows model accuracy figures (only resale-price's are computed from data; the others are configured values). Kinective's Legal team should review the recording and its narration before it is shown to a client or prospect. Nobody should state or imply that a named vendor product is connected for that client.

---

## 1. What the video must say without saying it

The audience already runs a large ERP, asset-management and service suite. We do not compete with it; we make it decide better. Every scene carries one of these five messages, and none of them names a vendor or a suite.

| Message | How the video shows it | Words to use | Words to avoid |
|---|---|---|---|
| **Your systems keep running the work** | The approval form says the owning systems *remain authoritative*; the board's Execute stage sends instructions into order, work-order and warehouse processes that send references back | "Your systems of record stay authoritative. We decide what the work should be; they do the work." | "replace", "rip out", "instead of your ERP" |
| **We plug into decisions your processes already ask for** | The case opens at the point where someone has to choose (return approved, item inspected, asset to be disposed of) and the decision packet arrives there | "At the moments your process already stops for a choice: return approval, inspection disposition, material review, asset disposal, remanufacture or teardown" | Any product or module name |
| **We add what a transaction system does not do** | Seven routes on one economic basis; six gates before price; demand matching; external market evidence; learning by cost line | "Every possible next life, compared on one economic basis, with eligibility checked before price" | "AI that runs your assets", "repair, defer or replace" for equipment still in service (keep the claim to assets that come back) |
| **Agent-first, human-governed** | Agents stream their tool calls; the live run board names the agent behind every step; a person approves; Access shows autonomy limits and kill switches | "Agents do the legwork, people make the commitments" | "autonomous decisions", "no humans needed" |
| **Your agents and ours work together** | MCP & Tools: Circularity exposes governed tools to other agent platforms and consumes enterprise MCP servers | "Open by design: your agents can call ours, and ours call your systems through the same governed tools" | Any competitor or partner agent product name |

**Scope line, if you need one sentence:** *"Circularity decides the best next life for every asset that comes back to you: returned, end-of-lease, retired or surplus, in any industry. And it hands the work to the systems you already run."*

---

## 2. Before you record

1. Open the build with presenter tools once to reset: `index.html?presenter=1`, then **Presenter** (top bar) → **Reset all** → confirm. State is kept in the browser, so a refresh alone does **not** reset RT-1048.
2. Open `index.html?presenter=0` so the **Presenter** pill and its *Presenter: continue as …* buttons are **not** on camera. Role changes below use **Sign out** and sign in again; cut the sign-in screens in the edit.
3. Browser window **1440 × 900**, zoom 100 %, light mode, region menu **EN · UTC**. Hide the bookmarks bar; turn on a cursor highlight in your recorder.
4. Sign out. Any password works for every ID below.
5. Slides ready: deck slide 1 (*Decision Intelligence Framework*), slide 2 (*business modules*), slide 3 (*one returned asset, applications involved*).

**Never on camera**

| Avoid | Why |
|---|---|
| The **Presenter** menu | It says what the data is |
| **Integration › Source map › + Add source** and the vendor picker in a source's edit form | The vendor lists include suite vendors |
| **Data checks** modal | Internal integrity checks; not a story for this audience |
| Close-ups of vendor names in the Source map | Narrate categories (CRM, ERP, EAM, WMS, quality, market data), not vendors |
| The *▼ %* chip next to Net recovery on the Command Center | Period comparison that invites a question we do not answer here |

---

## 3. Shot list (6 minutes, hard stop at 7)

The narration below is about 500 words, about 3.5 minutes spoken at a calm 140 words a minute. The rest of the 6 minutes is the screen doing the work: the agent streaming, the board playing, the toasts landing. Let those moments breathe. If a take runs past 7 minutes, drop the row marked *optional* and shorten the board at 2× to 5 seconds.

| # | Time | Scene | Business outcome it proves |
|---|---|---|---|
| 0 | 0:00–0:15 | Title | — |
| 1 | 0:15–0:45 | The outcome first: Executive Home | Recovered value, avoided spend |
| 2 | 0:45–1:05 | Where the value leaks: the journey slide | The decision gap between the systems |
| 3 | 1:05–2:35 | One asset, decided by agents | Faster, evidence-backed decisions |
| 4 | 2:35–3:10 | A person commits | Governance and accountability |
| 5 | 3:10–4:30 | Agents carry it through: the live run board | Execution in your systems, closed loop |
| 6 | 4:30–5:15 | Fits the landscape you already run | Low integration risk, open agent ecosystem |
| 7 | 5:15–5:40 | It learns, and it proves it | Measured uplift |
| 8 | 5:40–6:00 | Close: how to start | Phased, low-risk adoption |

---

## 4. Scene by scene

Each row: **Click** (what you do), **On screen** (what to frame or call out in the edit), **Voiceover**.

### Scene 0 · Title (0:00–0:15)

| Click | On screen | Voiceover |
|---|---|---|
| Deck slide 1 | *Decision Intelligence Framework*; the ring Sense → Evaluate → Optimize → Execute → Learn | "Every large enterprise gets assets back: end-of-lease equipment, returns, retired fleet, surplus. Each one is a decision worth money. This is Circularity, the agentic decision layer that makes it." |

### Scene 1 · The outcome first (0:15–0:45)

| Click | On screen | Voiceover |
|---|---|---|
| Sign in as `exec` | **Home**: the **Briefing** card (*$2,433,569 recovered on 1277 reconciled decisions; $1,741,546 of new purchases avoided*, the Warehouse 1 line with its owner) and **Key figures** | "An executive doesn't start with dashboards. They start with a briefing: two point four million recovered, one point seven million of new purchases avoided, and where value is at risk right now, with its owner." |
| Press **Brief me** | The Ask panel streams **inbox.get · RETRIEVED**, then the briefing card | "Every answer shows the tools the agent called, so no number is taken on trust." |

### Scene 2 · Where the value leaks (0:45–1:05)

| Click | On screen | Voiceover |
|---|---|---|
| Deck slide 3 | The journey: lease ends → return → pickup → received → inspect → **Circularity decides** → enterprise applications carry it out → outcome back | "Your systems already run every step of a return. None of them decides the asset's best next life across all that evidence. Circularity sits at exactly that moment, and hands the work back to the systems you run." |

### Scene 3 · One asset, decided by agents (1:05–2:35)

| Click | On screen | Voiceover |
|---|---|---|
| **Sign out**, sign in as `ops` | Planner **Home**: *21 decisions ready to submit*; **Needs you** with **RT-1048 · Redeploy RT-1048 · $9,600** | "For the planner, the agent has already prepared twenty-one decisions and ranked what needs a person." |
| Type `RT-1048` in the search box (top bar), pick the result, then **Evaluate treatments** in the panel that opens | **Decision packet · RT-1048**: **Redeploy · $9,600**, *P10–P90 $8,371–$10,608 · High confidence*; **Alternatives** (Sell $4,800, Re-lease $3,600, Recover parts $3,200); **Not eligible**: *Sell parts externally · Demand fit gate*; six green **Gates** | "One returned motor, seven possible next lives, compared on one economic basis. Redeploying it against a customer's replacement order is worth ninety-six hundred dollars, forty-eight hundred more than selling it, with a range, not a guess. One route is ruled out before price is even considered: no confirmed buyer, so the gate excludes it." |
| Press **Ask about RT-1048**; type *What should we do with RT-1048, and why?* | Streams **decision.prepare · RULES**, **case.routes · MODEL**, **case.evidence · RETRIEVED · 10 items**; the answer with **PREPARED BY AGENT** and a **Drafted rationale** | "Ask it why. It calls the rules, the prediction models and the evidence, each labelled retrieved, model or rules, and drafts the rationale for you." |
| Esc. Point to **AFTER APPROVAL** in the packet, then press **Submit for review** | *Redeployment order → ERP · Order Management; Refurbishment work order → EAM; Transfer to site → WMS*; toast *1 step done.* | "It already shows what will be sent where after approval. The planner submits. Agents prepare; people commit." |

### Scene 4 · A person commits (2:35–3:10)

| Click | On screen | Voiceover |
|---|---|---|
| **Sign out**, sign in as `approver`; search `RT-1048` → **Evaluate treatments**; press **Approve…** | **Approve RT-1048**: *Approving sends an instruction to the owning systems; they remain authoritative for the work.* Agent-drafted rationale, *Your approval limit*, *Raw instruction that will be sent* | "The approver sees the drafted rationale, their own limit and the exact instruction before anything leaves. Your systems stay authoritative for the work." |
| Tick *I reviewed evidence snapshot …*; press **Approve and send instruction** | Toast *APR-2026-10-3161 created. Instruction handed to ERP.* | "One approval reference, carried by every instruction. There is no auto-approve path." |

### Scene 5 · Agents carry it through (3:10–4:30)

| Click | On screen | Voiceover |
|---|---|---|
| Sidebar → **Process orchestration**; press **2×** | The board plays by itself: **orchestrated by ✦ Circularity Agent**; boxes open, lines spin then tick (*✦ Evidence Assembler · Read lease contract · LC-4739 · `get_case_evidence` → …*); counters for agents, tool calls, model calls, audit entries climb | "Behind the screen, every stage was run by Circularity's agents. Each line shows the agent, the tool it called, the system it reached, what it got, and the audit ID that proves it." |
| After about 10 s press **Skip to now**; click box **5 · Inspect and grade** | **condition-vision v2.1 · CNN** *agrees with grade B*; **rul-survival v1.4**; the **Models used at this stage** card | "Where models are used, it names them: a vision model checks the inspection photos, a survival model estimates remaining life." |
| Click box **6 · Decide** | **✦ Opportunity Finder**: demand match, comparable sales, *Ran 6 gates on 7 routes*, **resale-price v1.3 · XGBoost regressor** with **MAE and P10–P90 coverage**, *Decided: recommend Redeploy* | "The Opportunity Finder matches demand, prices every route and decides, and each model shows its measured error." |
| Click box **8 · Execute**; press **Check for the next acknowledgement →** three times (two order steps, then the outcome) | *Redeployment order acknowledged* (it answered on its own), then *Refurbishment work order · WO-…*, *Transfer to site · TR-…*; box 9 *Collected the actual result · $9,230* | "The Handoff Coordinator sends the approved plan into your order, maintenance and warehouse processes, and each sends its reference back. Then the actual result comes back on its own." |
| **Sign out**, sign in as `finance`; **Process orchestration**; box 9 → **Confirm the outcome →** | Box **10**: *Predicted $9,600, actual $9,230 (−$370)*; *Proposed 3 learning records* | "Finance confirms. Ninety-six hundred predicted, ninety-two thirty actual, explained line by line, and the model learns from the difference." |

### Scene 6 · Fits the landscape you already run (4:30–5:15)

| Click | On screen | Voiceover |
|---|---|---|
| **Sign out**, sign in as `admin`; **Integration → Source map** | *Existing lease, ERP, asset, repair, warehouse and service systems keep owning their transactions.* **19 sources · 96.8% integration health** | "It connects to what you already run (lease, ERP, asset, repair, warehouse, service, quality and market data) and those systems keep owning their transactions." |
| **MCP & Tools → As MCP client**, then tab **Agent registry** | Enterprise MCP servers and their tools; nine agents with scopes and authority | "It's open by design: Circularity uses your platforms' agent tools, and your agents can call its governed tools. Every agent has a scope it can't exceed." |
| *Optional:* **Access → Agent autonomy** | *Off · Suggest · Prepare · Act and notify*, by role and action | "You decide how far each agent goes, with a kill switch for each." |

### Scene 7 · It learns, and it proves it (5:15–5:40)

| Click | On screen | Voiceover |
|---|---|---|
| **Sign out**, sign in as `finance`; **Analytics** | **+$652k** vs baseline (**+37%**); **$1.74M** confirmed avoided spend; **21 days** *vs 27 today · 22% faster* | "Against current practice: thirty-seven percent more recovered, one point seven million of spend avoided, and value realised twenty-two percent faster." |

### Scene 8 · Close (5:40–6:00)

| Click | On screen | Voiceover |
|---|---|---|
| Deck slide 2 | The three modules on one shared framework | "Start in shadow mode beside your teams, then one route, then the closed loop, then the portfolio. Your systems run the work; Circularity makes sure it's the right work. Agent-first, human-governed." |

---

## 5. Edit notes

- **Stay under 7 minutes:** cut every sign-in to a 0.5-second dissolve with a role caption (*Planner*, *Approver*, *Finance*, *Admin*); trim loading pauses; the optional row in scene 6 saves 10 seconds.
- **Callouts (150 % zoom):** the recommendation and gates in the packet; *remain authoritative* in the approval card; one board line (agent → tool → system → audit ID); the model card's error line; the Analytics headline row.
- **Lower thirds:** "Agents prepare · People commit" (scenes 3–4); "Your systems stay authoritative" (scene 5); "Open by design" (scene 6).
- **If a number differs on screen:** reset (section 2, step 1) and re-record. All figures come from the build on 22 Oct with RT-1048 reset.

## 6. If asked after the video

| Question | Answer |
|---|---|
| "Do you replace our ERP or asset management?" | No. They stay the system of record and do the work; Circularity decides what the work should be, sends the approved instruction, and reads the outcome back. |
| "Where would it plug in?" | At the points your process already stops for a choice: return approval, inspection disposition, material review, asset disposal, remanufacture or teardown requests, and contract or rental end. |
| "We already have AI in our suite." | Good. Circularity works with it: it can call your platform's agent tools and expose its own as governed tools. Its focus is narrow: the best compliant next life for assets that come back, compared across seven routes, with eligibility checked before price and every forecast reconciled against the outcome. |
| "How do we start?" | Shadow mode on one asset class, compared with the decisions your coordinators make; then one route with approval; then the closed loop; then the portfolio. |
| "Are the model figures real?" | resale-price's error is computed from reconciled decisions. The other model figures shown are configured values for this demonstration and will be confirmed per customer. *(Have this answer reviewed before use.)* |
