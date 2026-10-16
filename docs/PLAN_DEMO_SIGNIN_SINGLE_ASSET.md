# Plan: realistic sign-in, one-asset demo journey, retrieved vs predicted

**Purpose of this file:** a self-contained brief for a fresh session. It does not assume any earlier conversation. Read it top to bottom, then start at **Phase 0**.

**Status:** built on branch `feature/demo-refactor` (2026-10-16), phases 1–6, with every open decision on its default and marked **(assumed)**; see section 10 and `CHANGES.md` Update 9. Not pushed or merged. Still to do: the block diagram (E7), hosting (E13), the sales video.

**Original status:** draft, not started (2026-10-16). Source: the team review call of 2026-10-16 (Product Owner, a senior reviewer, and the build team), its transcript, and the first-draft spec `docs/Refactor Guided Flow.md`, which this plan refines and replaces. Open decisions are in **section 3**. Each has a recommended default; until the Product Owner answers, build the default and label it **(assumed)**.

**Builds on:** `docs/PLAN_RBAC_ADAPTIVE_UI.md` (roles, policy, sign-in, rules in section 7, harness in section 8) and `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` (Update 8: guided treatment page, Executive and Warehouse Manager, exceptions, Notify, orchestration, identity). **Branch:** `feature/demo-refactor`, cut from `feature/guided-flow` at `868f530`. Neither earlier branch is merged into `main` yet (section 4.8).

**Deadline:** the demo to a senior stakeholder is on **Monday 19 Oct 2026**. The Product Owner asked for the flow to be "channelized and sequenced… ready by tomorrow" (Sat 17 Oct) for a dry run. Section 7 gives a short order if time runs out.

> **Compliance note.** This work changes the sign-in experience (simulated credentials and SSO wording) and how predictions are labelled against source data. Per Kinective policy, wording about authentication, identity, data provenance and model outputs should be reviewed by Kinective's Legal team before it is relied on or used with clients. The demo stays synthetic: no real names, emails or customer data.

> **About the source transcript.** The meeting transcript's audio lines are reliable. Its *screen descriptions* were generated automatically, and several values in them do not match the app (for example "482 assets", "+$612k", "Exceptions 2621", "RUL 6.4 years", "$1,480"). This plan uses values checked in the app on 2026-10-16. Section 13 lists the corrections. Participants are referred to by role, never by name.

---

## 1. The feedback to solve

The call agreed the **story** for Monday: start with **one slide** showing the business problem as a user-journey block diagram, then show the screens that follow that diagram **one-to-one**, using **one record throughout**. Technical architecture, adapters and model performance come **last, only if asked**.

| # | Ask (transcript time) | Today (checked in the app) | Wanted |
|---|---|---|---|
| F1 | **No role-picker on entry** (02:06–03:08, 10:10–10:33). "I don't want to show this screen to anybody." "I'll just sign in, it'll go to my dashboard." | The app opens on *Sign in as* with eleven role cards and a "Simulated sign-in" note | A production-looking sign-in. Signing in lands **directly** on that user's home. The role list is internal only |
| F2 | **Two perspectives**: what senior management sees versus what an end user sees (10:33) | Eleven accounts, all equally prominent | Two demo identities lead the story: **senior management** → Executive Command Center; **end user** → the returned-asset flow. Other roles stay reachable for presenters |
| F3 | **One asset, one journey** (11:41, 15:17–15:32). "If I click that asset, it will show the next stage… and finally the outcome we predicted. That should be a one-asset journey." | The pieces exist (Returned assets → Asset intelligence → Treatment steps 1–5 → handoff → outcome) but nothing sequences them, and the Command Center and Returned assets open on *all* assets | A guided **demo path** for one record (RT-1048, a Voltara V4 motor) across 5 screen movements with clear Next/Back, no dead ends |
| F4 | **1:1 with the block diagram** (05:11–05:53, 08:36–09:15, 13:35–14:15) | The diagram is still not in the repo (it was D15 in the last plan). The in-app 10-step journey strip is close but not the same | Get the diagram, check the screens against it, and label the 5 movements with the diagram's box names. A one-slide version goes first in the deck |
| F5 | **Executive exceptions stay high level** (12:34–12:58). "If they click on exception, they get which warehouse has got what exception." "What warehouse, what item, what value." "An executive assigns it to somebody if it's not actioned." | Exceptions are ranked by type (value at risk by reason, bottlenecks, declining metrics, deteriorating condition), with Severity, Value, Cases, Trend, Status, **View cases** and **Notify owner**. The drawer lists Return, Asset, Location, Status, Value | Group by **warehouse**; each row shows **Warehouse · Exception · Item(s) · Value** and **Notify owner** as the main action. The drill-down shows only Warehouse, Item and Value |
| F6 | **Many units of one SKU** (18:04–19:53). "In one client you would have sold 100 of these machines… and returned 100. Each will have a different economic path, value, condition." Also: "the same asset would have got returned" many times | Asset intelligence switches between all 128 returns in one flat list (`RT-1001 · Industrial motor · MTR-2384`). Customer A alone has **15 live Voltara V4 motor returns** (grades A–D: redeploy, resale, harvest, parts sale), 28 across customers | Pick **SKU → customer → unit (serial)**, each unit with its own grade, life, value and route. Show how many units of the SKU came back, and a **return history** for the physical unit |
| F7 | **EAM does not decide commercial value** (16:37–17:18). "We are retrieving the information from EAM… so why would we have commercial value — *Refurbish, then sell* — here?" | The *Condition, life and commercial value* card mixes A (EAM condition), B (estimated RUL **and** certified period) and C (route and net) under one heading | Retrieved facts and predictions are separate. The recommended route and value appear only on the prediction side |
| F8 | **Information on one side, inference on the other** (19:58–21:33). "Maybe information to the left, inferences to the right." | Asset Overview panels are in mixed order: CLV card, Lifecycle, Condition, Product, Economic, Eligibility, Data quality, Related | Two labelled zones on Asset Overview: **Retrieved from enterprise systems** (left) and **Predicted and computed by Circularity** (right). Every card carries a source or model badge |
| F9 | **"Product intelligence" is just specs** (22:08) | Panel is titled *Product intelligence* but shows static specifications | Rename to **Product specs** |
| F10 | **Share the new build** (03:31–05:09). The Product Owner could not open the new UI; GitHub Pages still serves `main`; a single `index.html` was sent over chat | Pages deploys `main` only (`.github/workflows/static.yml`). Product photos load from `assets/products/`, so a lone `index.html` shows no photos | A hosted link to the demo build before Monday, and a self-contained fallback |
| F11 | **Narrative order and Q&A** (00:25–01:02, 05:55–06:46, 09:18–09:32, 14:27–15:02) | — | Deck order: problem slide → Executive → one-asset journey → architecture only if asked. Prepare answers on **adapters** (ready **31 Oct**), **integration effort** ("plug-and-play or a massive integration?") and the **POC or MVP by 15 Nov**. A **recorded video** of the demo may be needed for sales before the **29 Oct** meeting with IFS |

**Not in scope:** new analytics, model changes, backend work, adapters. The Product Owner said the build "is what it is", with room to improve after Monday.

---

## 2. Orientation: where the code is

Still **one file, `index.html`**, no build step. General structure (state `S`, hash routes, `ACT` handlers, `NAV`, marker blocks) is in `docs/PLAN_RBAC_ADAPTIVE_UI.md` section 2. Line numbers drift; search by name.

| Area | Where |
|---|---|
| Sign-in screen | `signInHTML`, `renderSignIn`, `ACT.signIn`, `sessionLoad`, `setAcct`, `RB_AV`, the `#siSso` note; account menu `acctMenuHTML`, `ACT.switchAcct`, `ACT.signOut` |
| Accounts and policy | `/*RBAC-START*/ … /*RBAC-END*/`: `ACCOUNTS` (11, incl. `executive`, `wm-1`, `wm-2`), `ROLE_POLICY` (`landing`), `homeFor`, `HOME_LABEL`, `canRoute` |
| Executive exceptions | `ccExList`, `ccExHTML`, `ACT.exView` (drawer), `ACT.notifyOpen` / `notifyOk`, `exOwner`, `S.notes` |
| Returned assets | `renderProduct`, `queueRows`, `queueTable`, `kpiStrip`, `openCase` (drawer) |
| Asset intelligence | `/*ASSET-START*/ … /*ASSET-END*/`: `assetPage`, `asOverview` (panel order), `asCond`, `asProduct`, `asEcon`, `asElig`, `asQuality`, `asRelated`, `asTimelineHTML`, `asEvents`, the *Switch asset* select, `asSerial`, `asModel`, `asTitle` |
| CLV card and guided steps | `/*TI-START*/ … /*TI-END*/`: `tiClv`, `caseDiag`, `caseRul`, `caseDemand`, `recert`, `tiOutcome` (step 2), `caseView` (steps 1–5), `ACT.tiStep`, `afterRender` (`?step=N`) |
| Handoff and outcome | `execBlock`, `ackStep`, `ACT.advance` ("Simulate system acknowledgement"), `ACT.confirmOutcome` |
| Journey strip | `JSTEPS`, `journey()`; mounted in `#jmount` by `route()` |
| Closed history | `ROWS` (1,400 closed decisions; fields include `assetId`, `model`, `tenant`, `grade`, `route`, `actual`). **70 asset IDs appear more than once**, so repeat returns already exist in the data |
| Hosting | `.github/workflows/static.yml` (deploys `main`), `assets/products/` (photos) |

**The demo record, RT-1048** (checked 2026-10-16): Voltara V4 motor, asset `MTR-2041`, serial `SN6399949`, Customer A, Warehouse 1, age 6.4 years, Grade B (75/100), awaiting approval. Recommendation **Redeploy RT-1048 · $9,600** (P10–P90 $8,371–$10,608), confidence High, estimated RUL 30–40 months, certified 24 months, matched order **SO-48102 at Site 3**. Evidence is complete. It is the hero case in the seed, with every one of these fields filled in.

---

## 3. Decisions needed from the Product Owner

Ask these in one message today (16 Oct). If there is no answer, build the **default** and mark it **(assumed)** here and in the UI notes.

| # | Question | Recommended default |
|---|---|---|
| E1 | Which two identities lead the demo? | **Executive** (senior management) and **Planner · Customer A** as the end user (they own RT-1048, at Warehouse 1). The Warehouse Manager and Approver are used later in the journey via *Switch account* |
| E2 | Where does the end user land after sign-in? | **Product → Returned assets**, scoped to Customer A and opened on the demo record, instead of the Command Center. Actions on me remains one click away. Executive still lands on the Command Center |
| E3 | Should the internal role list stay reachable? | **Yes, but hidden**: only at `#/signin?roles` (or Ctrl+Shift+R on the sign-in screen), never shown by default. *Switch account* in the header opens the sign-in page, not the grid |
| E4 | Quick-fill buttons on the sign-in form (from the draft spec)? | **Off by default**; shown only in **presenter mode** (`?presenter=1`, remembered on the device), so an audience never sees role shortcuts. The email field offers the demo IDs as autocomplete in both modes |
| E5 | Demo email domain? | **`@northfield.example`** (reserved test domain; `northfield.com` may be a real company). Short aliases `exec`, `ops` and the role names also work. Any non-empty password is accepted |
| E6 | Which record is "one record throughout"? | **RT-1048** (above). It is a Voltara V4 motor, the SKU the call discussed |
| E7 | Do the five screen movements match your block diagram? | Use the provisional names in 4.2 until the diagram arrives, then rename to its boxes. **We still need the diagram file** (it is not in the repo) |
| E8 | Executive exceptions: group by warehouse only, or warehouse then type? | **Warehouse first** (Warehouse 1, Warehouse 2, Repair centre), one row per warehouse × exception type, sorted by value. Portfolio-wide items (declining metrics) sit in a *Portfolio* row |
| E9 | How many units should the SKU view claim? | **Only what the data holds**: 15 live returns of Voltara V4 motor from Customer A, plus the closed returns of that model in the history. We do not invent "100 units"; the presenter says "the same works for 100" |
| E10 | Retrieved-side badges name the production source (EAM, QMS, ERP, WMS), but the demo data is synthetic. Is the global *Demo data* label enough? | **Yes**: badges name the system the value comes from in production; the header *Demo data* pill and the sign-in footer say all data is synthetic. Values that are modelled even in production keep their *Modelled* label |
| E11 | Rename *Condition intelligence* too? | **Yes, to "Inspection findings"**, since it is also retrieved information. *Economic intelligence* keeps its name (it holds predictions) |
| E12 | Executive KPI strip: add an *Exceptions* count as a sixth figure (the draft spec lists one)? | **No**: keep the five value figures that equal Finance's; show the exception count in the Exceptions header |
| E13 | Hosting before Monday | **Merge to `main`** (RBAC PR first, then guided flow, then this branch) after the dry run, so the existing Pages URL serves the demo. Until then share a **zip** of `index.html` + `assets/` |

---

## 4. Design

### 4.1 Production-style sign-in (F1, F2)

Replace the role grid with a standard sign-in. Keep the left brand panel.

- **Layout:** brand panel left (ARTIZENT · Circularity Decision Workbench, one line on what it does). Right: **Work email or user ID**, **Password**, **Sign in** (primary), a divider, **Continue with single sign-on** (secondary), and a small footer: "Demo environment · synthetic data". No mention of "demo accounts" or "click a card".
- **Routing:** `ACT.signInCreds` resolves the ID to an account through `SIGNIN_IDS` (new, inside the RBAC block), then reuses `setAcct` → `shell()` → home. Unknown IDs show an inline error ("We could not find that account"), not a role list.

| ID (any password) | Account | Lands on |
|---|---|---|
| `exec@northfield.example` · `exec` | Executive | Command Center (senior view) |
| `ops@northfield.example` · `ops` · `planner.a@…` | Planner · Customer A | Returned assets, on RT-1048 (E2) |
| `planner.b@…`, `planner.c@…` | Planner · Customer B / C | Returned assets |
| `warehouse1@…`, `warehouse2@…` | Warehouse Manager · Warehouse 1 / 2 | Command Center (operational) |
| `approver@…`, `engineer@…`, `finance@…`, `developer@…`, `admin@…` | as named | their current home |

- **Single sign-on button:** if the email field holds a known ID, show a short "Redirecting to your organisation's identity provider… (simulated)" state for about 600 ms, then sign in as that account. If it is empty, focus the field with "Enter your work email to continue with single sign-on". This mirrors home-realm discovery. It stays labelled simulated (rule in section 8).
- **Presenter mode (E4):** `?presenter=1` shows two quiet chips under the form, **Senior management** and **End user**, that fill and submit. The internal role grid stays at `#/signin?roles` (E3).
- **Session:** unchanged (`circ-session`). *Switch account* and *Sign out* return to this form.
- **Accessibility:** labelled inputs, `autocomplete="username"` and `current-password`, Enter submits, the error is `role="alert"`, and focus moves to the first field.
- **Remove** the "Sign in as" grid text and the "Simulated sign-in…eight demo accounts" box from the default view. Keep the SSO note from Update 8 as one line: "In production you sign in with your company account."

### 4.2 The five screen movements (F3, F4)

Provisional names, to be replaced by the block diagram's box names (E7):

| # | Movement | Screen and state for RT-1048 | What the presenter says |
|---|---|---|---|
| 1 | **Return received** | Returned assets (Planner · Customer A), RT-1048 row highlighted with *Start here* | "A leased motor came back to Warehouse 1." |
| 2 | **What we know** (retrieved condition) | Asset intelligence for MTR-2041, **left zone**: EAM condition Grade B, QMS certified 24 months, lifecycle timeline, inspection findings, specs | "Everything here is pulled from EAM, QMS, ERP and WMS. We don't own it, we retrieve it." |
| 3 | **What we predict** (life and value) | Same page, **right zone**: estimated RUL 30–40 months, predicted value and uplift, recommended route *Redeploy · $9,600*, confidence High | "Here Circularity predicts: how long it will last, and what it is worth on each route." |
| 4 | **Decide and approve** | Treatment Intelligence steps 2 → 5: recommended outcome, why, what-if, instruction preview, **Approve redeployment** (switch to Approver, or sign in as Admin) | "One person approves; they see exactly what will be sent." |
| 5 | **Hand off and outcome** | Step 5 *Enterprise handoff*: ERP Order Management → EAM → WMS acknowledged (*Simulate system acknowledgement* ×4) → *Outcome reported* → Finance **Confirm outcome** | "ERP, EAM and WMS do the work; the actual result comes back and teaches the model." |

**Demo path rail.** A slim bar under the top bar, shown on any page of a case when the case is opened from the path (or always for the demo record): `① Return received → ② What we know → ③ What we predict → ④ Decide and approve → ⑤ Hand off and outcome`, the current stop highlighted, with **Back** and **Next**. Each stop is a deep link (`#/product/received?focus=RT-1048`, `#/product/asset/RT-1048?zone=known`, `…?zone=predicted`, `#/product/RT-1048?step=2`, `#/product/RT-1048?step=5`). Prefix classes `dp`. It replaces nothing; the 10-step journey strip stays, and the rail notes which journey steps each stop covers (1 → steps 1–2, 2 → 1, 3 → 3–4, 4 → 5, 5 → 6–10) so the two agree.

**Executive entry to the same record.** The Warehouse 1 exception (4.4) includes RT-1048. The presenter can start as the Executive, open Warehouse 1, see RT-1048 among the items, press **Notify owner** (to Planner · Customer A), switch to the end user and find it at the top of *Actions on me*, then follow the rail. One record links both perspectives.

**No dead ends.** Every stop's main button goes to the next stop. Pages that are not on the path still work, but the rail only appears on the path.

### 4.3 The deck and narrative (F4, F11)

Outside the app, delivered with this branch:

- `docs/demo/DEMO_SCRIPT.md`: the exact clicks for the Monday flow (problem slide → Executive → 5 movements → close), the presenter's lines from 4.2, timing (target 8 minutes), recovery steps if something goes wrong, and **Q&A notes**:
  - **Adapters:** which source types exist today (19 sources in the Source map) and which arrive by **31 Oct**.
  - **Integration effort:** the standard pattern (adapter per system type, canonical models, event stream) answers "plug-and-play or a massive effort". Claims must be reviewed before use.
  - **Model performance:** the *Predicted vs actual* view; keep it for questions.
  - **Timeline:** POC or MVP by **15 Nov**.
- **One slide** (the block diagram), redrawn so its five boxes carry the same names as the rail. If the Product Owner's diagram differs, theirs wins and the rail is renamed.
- **Video:** a 3–4 minute screen recording of the same path for the sales audience before **29 Oct**. Record it at 1440×900 in light mode, after the dry run.

### 4.4 Executive exceptions by warehouse (F5)

Rework `ccExHTML` without changing `ccExList`'s ranking or the Notify flow:

- **Rows:** grouped by warehouse (Warehouse 1, Warehouse 2, Repair centre, then *Portfolio* for metrics that have no warehouse), one row per warehouse × exception type, sorted by value inside each group, groups sorted by total value.
- **Columns:** **Warehouse · Exception · Items · Value · Status · Notify owner**. *Items* shows the count and the top item by value (for example "55 items · top: RT-1048 Voltara V4 motor"). Severity becomes a small marker on the row, not a column. Trend moves to the row's tooltip.
- **Drill-down** (row click or *View items*): a drawer with three columns only, **Warehouse · Item · Value** (item = return ID + product), sorted by value, with *Open* links only for roles that may open cases. No status chips or operational detail.
- **Notify owner** stays the primary button on every row; the recipient default stays by exception type (D7 of the last plan), with Warehouse Manager of that warehouse for warehouse rows.
- `ccExList` needs a `wh` per item: a case's `location`; a value-at-risk reason is split per warehouse by its cases. Totals must equal today's totals (invariant).

### 4.5 One SKU, many units, repeat returns (F6)

**Selector.** On Asset intelligence, replace the flat *Switch asset* list with three linked selects: **Product (SKU)** → **Customer** → **Unit**. The unit option reads `SN6399949 · MTR-2041 · Grade B · Redeploy · $9,600 · Warehouse 1`. Changing any select navigates to that unit's `#/product/asset/RT-xxxx`, so the whole page (grade, RUL, value, route) changes with it. Respect tenant and warehouse scope (`myCases()`).

**SKU summary strip** above the zones: "Voltara V4 motor · Customer A · **15 units returned now** · by grade (A, B, C, D counts) · by recommended route (Redeploy, Resale, Parts, Harvest counts) · **N returned in the last 12 months** (closed)". The numbers come from `CASES` and `ROWS` filtered by model and tenant. Clicking a grade or route filters the Unit select. This is the answer to "100 units, each with a different path".

**Returned assets:** add a **Group by product** toggle. Grouped rows read "Voltara V4 motor · Customer A · 15 units · grades A–D · $X predicted" and expand to the units. Default stays ungrouped.

**Return history of one unit** (the "same asset returned many times" point). In the left zone, a *Return history* list for the physical unit: previous lease cycles and returns with customer, dates and what was decided, taken from `ROWS` where `assetId` matches (70 assets already repeat). Where a unit has none in the history, derive one or two earlier cycles deterministically from `asHex` and label them *from lease history (synthetic)*. RT-1048 must show at least one earlier cycle so the presenter can make the point.

### 4.6 Retrieved vs predicted (F7, F8, F9)

**Asset Overview layout:** two zones with headers and a one-line explainer each.

| Left: **Retrieved from enterprise systems** | Right: **Predicted and computed by Circularity** |
|---|---|
| **Diagnostic condition**: Grade B (75/100), winding insulation, *EAM* | **Estimated remaining useful life**: 30–40 months, most likely 36, *Prediction model v1.3* |
| **Certified operating period**: 24 months, ref QMS-xxxx, *QMS* | **Predicted value by route**: the routes with net and P10–P90, *Prediction model* (from *Economic intelligence*) |
| **Inspection findings** (was *Condition intelligence*), *Inspection* | **Recommended outcome**: Redeploy · $9,600 · confidence High, matched order SO-48102, *Recommendation service* |
| **Lifecycle evidence timeline**, *ERP, EAM, WMS, Lease* | **Uplift vs baseline**: from *Economic intelligence* |
| **Return history** (4.5), *Lease, WMS* | **Eligibility and gates**: rule-based, *Gate engine* (badge says *Rules*, not *Model*) |
| **Product specs** (was *Product intelligence*), *PLM* | **Data and evidence quality**: computed over the left zone |
| **Related assets and fleet context**, *ERP* | |

- **Badges:** every card header carries one badge kind: **Retrieved · {system}** (neutral outline chip), **Model · {name}** (a filled chip using an existing token), or **Rules · Gate engine**. Never colour alone: the badge text says which.
- **No commercial outcome on the left.** `tiClv` is split into `tiKnown(c)` (A condition, certified period) and `tiPredicted(c)` (estimated RUL, value for that life, matched demand, re-certification flag). The *Condition, life and commercial value* card is removed from the left; its parts land in the two zones.
- **Treatment step 2** uses the same split: the summary card stays, and the old A/B/C card becomes two side-by-side blocks, **What we know** | **What we predict**, so the estimated-vs-certified rule (never one merged number) still holds across the divider.
- **Layout:** two columns above 1100 px container width (`as` container), stacked below with *What we know* first. Classes prefixed `asz`.
- **Tabs:** the eight tabs stay; the *Overview* tab is the one that changes. Role tab rules (`asTabs`) still decide which cards appear in each zone; an empty zone shows a short note, never a gap.
- **Rename** *Product intelligence* → **Product specs** in the panel, the tab label (*Product & Components* stays), and any README or test references.

### 4.7 What stays the same

Update 8 behaviour is kept: guided treatment steps, what-if card, tie-breaker, instruction preview, handoff wording, orchestration, identity page, Actions on me and Notify. The 128 seeded cases and every total are unchanged.

### 4.8 Hosting and sharing (F10)

- **Before Monday:** after the dry run, merge in order `feature/rbac-adaptive-ui` → `main`, then `feature/guided-flow`, then `feature/demo-refactor` (each by PR). The existing Pages URL then serves the demo. If merging is not approved in time, temporarily point the Pages workflow at the demo branch and revert after the demo (E13). Neither is done without the user's go-ahead.
- **Fallback file:** a zip of `index.html` + `assets/` (photos load from `assets/products/`; a lone `index.html` shows no photos). The demo script links both.

### 4.9 Do not break

- RBAC: hide-don't-disable, tenant lock, Warehouse Manager lock, delegations, the forbidden-control scan. Every account must still be reachable (via IDs, presenter chips or `#/signin?roles`).
- Legacy and malformed sessions still fall back to the sign-in page (now the form).
- Deep links (`#/product/RT-xxxx`, `?step=N`, `#/product/asset/RT-xxxx`, `#explain`) keep working, and the new `?focus=` and `?zone=` are additive.
- Numbers: 128 live cases, 1,400 closed, Executive figures equal Finance's, 38 handed off, exception totals unchanged by grouping.
- Phone width 390 px, dark mode, print.

---

## 5. Landing and visibility changes

| Account | Lands on (before) | Lands on (after) | Notes |
|---|---|---|---|
| Executive | Command Center (senior) | same | Exceptions grouped by warehouse |
| Planner · Customer A | Command Center | **Returned assets, focus RT-1048** (E2) | Command Center still in the menu |
| Planner · Customer B / C | Command Center | Returned assets (E2) | |
| Warehouse Manager | Command Center (operational) | same | |
| Others | unchanged | unchanged | |

No page access changes. The sign-in grid becomes internal (E3).

---

## 6. Data additions (synthetic, deterministic)

Derive at render time from existing fields (`asHex`, `ROWS`, `CASES`). **Do not add `rnd()` calls to the generator**: that would shift every seeded number.

| Field | Derived from | Notes |
|---|---|---|
| `SIGNIN_IDS` | `ACCOUNTS` | ID and alias → account id (4.1) |
| SKU summary | `CASES` and `ROWS` by `asModel` / `model` and tenant | counts by grade and route, closed count in 12 months |
| Unit label | `asSerial`, `assetId`, grade, recommendation, location | 4.5 |
| Return history | `ROWS` by `assetId`, else 1–2 cycles from `asHex(c,'rh')` | labelled synthetic when derived |
| Exception `wh` | case `location` | 4.4; totals equal today's |
| Provenance badge map | panel → `{kind, system}` | one table, used by both zones and step 2 |

New invariants in `runInvariants`: exception value total by warehouse equals the ungrouped total; SKU unit counts equal the Returned assets count for that model and tenant.

---

## 7. Phases (each ends with tests, a screenshot and a short report)

**Phase 0: Baseline and questions (today).** Branch `feature/demo-refactor` (done). Rebuild the harness (RBAC plan section 8; known traps in the "headless harness quirks" note), run the role suite (208) and the guided-flow suite (110), take baseline screenshots of sign-in, Executive Command Center, Returned assets, Asset Overview for RT-1048 and step 2. Send section 3 to the Product Owner, and ask again for the block diagram (E7).

**Phase 1: Sign-in (F1, F2).** Form, ID routing, SSO button, presenter mode, hidden role grid, E2 landing. Test: no role grid on first load; each ID lands on its home; unknown ID shows an error; every account still reachable; legacy session migration still works.

**Phase 2: Demo path (F3, F4).** Rail, `?focus=` and `?zone=`, *Start here* highlight, Next/Back wiring, Executive → Notify → Actions on me link to RT-1048. Test: the five stops render in order with no dead end; Next from each stop lands on the next; the rail's journey-step mapping matches `JSTEPS`.

**Phase 3: Retrieved vs predicted (F7, F8, F9).** Zones on Asset Overview, badges, `tiKnown` / `tiPredicted`, step 2 split, renames. Test: no route name or net value inside the left zone for any case; every card has exactly one badge kind; estimated and certified are never in the same block; renames applied.

**Phase 4: Executive exceptions by warehouse (F5).** Grouping, columns, three-column drawer. Test: totals unchanged; drawer has exactly Warehouse, Item, Value; Notify still creates the Actions on me item and the audit entry; Warehouse 1 includes RT-1048.

**Phase 5: SKU, units and return history (F6).** Three-level selector, SKU strip, Group by product, return history. Test: unit counts match `CASES`; switching unit changes grade, RUL, value and route; scope respected; RT-1048 shows at least one earlier cycle.

**Phase 6: Hosting, docs, demo kit.** README (sign-in, landing, Asset Overview zones, exceptions), `CHANGES.md` **Update 9** with screenshots `docs/screenshots/demo-*.webp`, `docs/demo/DEMO_SCRIPT.md`, the one-slide diagram, the zip, and the merge or Pages step only on the user's go-ahead. Record the video after the dry run.

**If time is short:** Phase 1 → 2 → 3 → 4 → 6, then 5. Sign-in, the one-record path and the split carry the call's main asks; the SKU selector can be shown as the SKU strip alone.

---

## 8. Project rules

All rules in `docs/PLAN_RBAC_ADAPTIVE_UI.md` **section 7** and `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` **section 8** apply unchanged: palette tokens only, prefixed class names (new prefixes here: `si2` sign-in form, `dp` demo path, `asz` asset zones, `sku` SKU strip and selector), reuse existing components, no new libraries, `data-act` + `ACT` + `esc()`, hash routes for every state, container queries, 390/768/1280/1600 px, synthetic data only, plain English, `CHANGES.md` for every visible change, decision-intelligence wording, no push until asked.

Additional rules for this plan:
- **Simulated means labelled.** The sign-in form may look real, but the SSO step, the footer and README say it is simulated. No real identity provider is contacted.
- **No real-looking identities.** Demo IDs use `@northfield.example` and role names; no personal names.
- **Retrieved vs predicted is a rule, not a layout.** Any new figure must state whether it is retrieved (and from which system), modelled, or rule-based. A predicted value never appears under a retrieved badge.
- **One record throughout.** Demo copy, screenshots and the script use RT-1048 only, unless a step exists to contrast units of the same SKU.

---

## 9. Test plan (extends the existing suites)

Run both existing suites unchanged except where this plan deliberately changes a landing page or a label (update those expectations and note them in `CHANGES.md`). Add:

1. **Sign-in:** fresh load shows the form and no `.sia` role cards; each ID in 4.1 lands on its home; unknown ID → `role="alert"` error, still signed out; SSO with a known ID signs in, with an empty field asks for the email; `#/signin?roles` shows the grid; `?presenter=1` shows exactly two chips; malformed `circ-session` still shows the form.
2. **Landing:** Planner accounts land on Returned assets with RT-1048 focused (Customer A) or the first visible return (B, C); all other homes unchanged.
3. **Demo path:** stops 1–5 render for RT-1048 with the rail and the right stop highlighted; Next and Back walk the path both ways; no stop has a console error, `undefined` or `NaN`.
4. **Exceptions:** grouped by warehouse; drawer columns are exactly Warehouse, Item, Value; grouped total equals ungrouped total; Notify → Actions on me → In hand still works; RT-1048 is in a Warehouse 1 row.
5. **Retrieved vs predicted:** for every case visible to Admin, the left zone contains no route name, recommended plan or money value from `routes`; every panel header has exactly one badge kind; *Product specs* and *Inspection findings* exist and the old titles do not.
6. **SKU and units:** the Unit select for Voltara V4 motor · Customer A lists 15 units; switching changes the grade and route shown; Customer B planner cannot see Customer A units; Warehouse Manager sees only its warehouse's units; return history for RT-1048 has ≥ 1 earlier cycle.
7. **Regression:** 390 px overflow on sign-in, Executive Command Center, Returned assets (grouped and ungrouped), Asset Overview zones; dark mode screenshots; palette audit; invariants.

---

## 10. Product Owner decisions

*To be filled in.* One row per section 3 question: the answer and where it lands. Unanswered points stay **(assumed)**.

| # | Answer | Where it lands |
|---|---|---|
| E1 | (assumed) Executive and Planner · Customer A | `SIGNIN_LEAD`, presenter chips, demo script |
| E2 | (assumed) Planners land on Returned assets; Customer A on `?focus=RT-1048` | `ROLE_POLICY.Planner.landing`, `ACCOUNTS[planner-a].home`, `homeOf` |
| E3 | (assumed) Role grid only at `#/signin?roles`; Ctrl+Shift+R not used (it is the browser's hard reload) | `signInRolesWanted`, `renderSignIn` |
| E4 | (assumed) Quick-fill chips only with `?presenter=1`; datalist offers the demo IDs | `presenterOn`, `signInFormHTML`, `dpHint` |
| E5 | (assumed) `@northfield.example` plus aliases `exec`, `ops`, `user` and role names; any non-empty password | `SIGNIN_IDS`, `signInResolve` |
| E6 | (assumed) RT-1048 | `DEMO_ID` |
| E7 | **open**: provisional names until the diagram arrives | `DP_STOPS`, `docs/demo/journey-slide.svg` |
| E8 | (assumed) Warehouse first, one row per warehouse × type, Portfolio last | `ccExRows`, `ccExHTML` |
| E9 | (assumed) Real counts (15 Voltara V4 motors for Customer A) | `skuStrip`, `skuUnits` |
| E10 | (assumed) Badges name the production system; *Demo data* pill and sign-in footer say it is synthetic | `provB` |
| E11 | (assumed) *Inspection findings* | `asOverview`, `asTabCondition` |
| E12 | (assumed) No sixth figure; the count and total are in the Exceptions header | `ccExHTML` |
| E13 | **open**: nothing merged or pushed; a zip can be shared until then | — |

**Still open from earlier plans:** the user journey diagram (was D15; now E7), "increase the count of the rows… with the same button" (D12), and D2, D5–D20 of the guided-flow plan.

---

## 11. Definition of done

- Opening the app shows a real-looking sign-in, never the role grid. `exec` lands on the Executive Command Center; `ops` lands on Returned assets with RT-1048 ready.
- A presenter can walk RT-1048 through the five movements with Next only, from *Return received* to *Outcome confirmed*, and the movement names match the block diagram slide.
- The Executive sees exceptions by warehouse with item and value, drills into Warehouse · Item · Value, and notifies an owner who then sees it in *Actions on me*.
- Asset intelligence separates **what we know** (retrieved, with the system named) from **what we predict** (model or rules named); no commercial outcome appears on the retrieved side; *Product specs* is renamed.
- One SKU shows many units with different grades, lives, values and routes, and one unit shows its earlier returns.
- A hosted link (or the zip) and `docs/demo/DEMO_SCRIPT.md` are ready for Monday, and the sales video is recorded after the dry run.
- All checks pass with no console errors; no new colours; light and dark correct; no overflow at 390 px; numbers reconcile. `CHANGES.md` Update 9 and `README.md` updated; committed, not pushed until asked.

---

## 12. Prompt to paste into the fresh session

> Read `docs/PLAN_DEMO_SIGNIN_SINGLE_ASSET.md` fully, then `docs/PLAN_RBAC_ADAPTIVE_UI.md` sections 2, 7 and 8 and `docs/PLAN_GUIDED_FLOW_AND_EXEC_VIEWS.md` sections 4.6, 4.7, 8 and 9. Skim `index.html` around `signInHTML`, `/*RBAC-START*/`, `ccExHTML`, `renderProduct`, `/*ASSET-START*/` (`assetPage`, `asOverview`) and `/*TI-START*/` (`tiClv`, `tiOutcome`). Work on branch `feature/demo-refactor`. Follow the project rules in section 8 exactly (palette tokens only, no new libraries, prefixed class names, reconcile numbers, synthetic data, no personal data, retrieved-vs-predicted labelling). Start with Phase 0, then one phase at a time in the order of section 7, running tests and sharing a screenshot after each. Commit with detailed messages; do not push or merge until I say so.

---

## 13. Corrections to the meeting notes

The transcript's screen descriptions were auto-generated. Checked against the app on 2026-10-16:

| Transcript says | The app shows | Note |
|---|---|---|
| "Eight demo accounts" box on sign-in | Eleven accounts (Executive and two Warehouse Managers were added in Update 8) | The call saw the older text on one machine |
| Executive KPIs "Baseline recovery $2.43M · Circularity uplift +$612k · Recovery vs predicted 97% · Value recovered (YTD) $1.74M · Exceptions 2621" | Net recovery **$2.43M** · Uplift **+$652k** · Recovery yield **97%** · Avoided spend **$1.74M** · CO₂e avoided **263 t** | No "Exceptions" KPI exists (E12) |
| Exceptions rows "AST-10421 Voltara V4 motor…" and a browser alert on Notify | Rows are exception types (bottleneck, value at risk, declining metric, condition); Notify opens a form and shows a toast | F5 changes the rows to warehouse × type |
| "Lifecycle portfolio 482 assets" | 128 live assets | |
| Asset card with four columns: "RUL 6.4 years · ML Model", "Refurbish, then sell · $1,480", "Certified 12 months · QMS-818" | For RT-1048: three columns A/B/C; estimated RUL **30–40 months**, certified **24 months**, *Redeploy · $9,600*. **6.4 years is the asset's age.** *Refurbish, then sell* is the plan name on other units (for example RT-1001, $2,381) | The substance of F7 still holds: the card mixes retrieved and predicted values |
| Asset selector shows "~15 SKUs" | *Switch asset* lists all 128 returns by return ID | F6 |

---

## 14. Does the plan match the asks?

| Ask | Covered in | Match | Notes |
|---|---|---|---|
| No role picker; sign in and land on my screen (F1) | 4.1, E3, E4 | Yes | Grid only at `#/signin?roles` |
| Senior vs end-user perspectives (F2) | 4.1, E1, E2, 5 | Yes | End user lands on the returned asset flow |
| One asset, one journey, ending in the predicted outcome (F3) | 4.2 | Yes | RT-1048, five movements, Next/Back |
| One-to-one with the block diagram (F4) | 4.2, 4.3, E7 | **Blocked on the diagram** | Provisional names until it arrives |
| Exceptions: warehouse, item, value; Notify owner (F5) | 4.4 | Yes | Totals unchanged |
| 100 units of one SKU, each with its own path; repeat returns (F6) | 4.5, E9 | Yes, at the data's real scale | 15 live units for Customer A, no invented count |
| EAM does not decide commercial value (F7) | 4.6 | Yes | Split of `tiClv` |
| Information left, inference right (F8) | 4.6 | Yes | Zones plus badges, also on step 2 |
| Product intelligence → Product specs (F9) | 4.6 | Yes | Plus *Inspection findings* (E11) |
| Share the new build (F10) | 4.8, E13 | Yes, on approval | No merge or Pages change without the go-ahead |
| Deck order, Q&A, video (F11) | 4.3 | Yes | Claims on integration effort need review |

**Changed from the first draft** (`docs/Refactor Guided Flow.md`): demo emails use `@northfield.example` instead of `northfield.com`; quick-fill pills appear only in presenter mode; the end user lands on RT-1048 in Returned assets; the SKU view uses the real counts instead of "100 units"; the right zone also holds rule-based results, badged as rules, not ML; Executive exceptions are grouped by warehouse; hosting, the demo script, the slide and the video are added; values come from the app rather than the auto-generated screen notes.
