# [Task / PR Spec] Refactor Guided Flow: Realistic SSO Login, Single-Asset Journey, & Asset Intelligence Split

## 1. Repository & Context
- **Repository:** `ranilmukesh-artizent/Circularity-ui`
- **Target Branch:** `feature/demo-refractor`
- **Primary File(s):** `index.html` (and any associated documentation like `README.md` or `CHANGES.md`)
- **Objective:** Refactor the clickable UI prototype based on stakeholder review feedback for the upcoming executive and sales demos. The goal is to make the entry experience look like a real production application, align the navigation to a 1-to-1 single-asset business flow, and clearly separate retrieved database records from AI/ML model inferences.

---

## 2. Detailed Implementation Tasks for AI Agent

### Task 1: Replace Internal Role-Picker Landing Screen with Realistic Login Page
**Problem:** Currently, the landing screen displays an internal "Simulated sign-in" grid with 8 persona cards (`Planner - Customer A/B/C`, `Approver`, `Engineer`, `Finance`, `Developer`, `Admin`, `Executive`, `Warehouse Manager`). Stakeholders do not want external viewers to see an internal role-selection matrix upon opening the app.

**Implementation Requirements:**
1. **Build a Production-Style Sign-In Screen:**
   - Replace the 8-card persona grid on the initial landing screen with a clean, centered enterprise login view (`Email / User ID` input, `Password` input, `"Sign in"` primary button, and `"Continue with Enterprise SSO"` secondary/simulated option).
   - Keep the left-hand branding panel (`ARTIZENT — Circularity Decision Workbench`), but update the bottom helper text to remove references to "synthetic demo accounts" or "click a card".
2. **Credential-to-Role Routing Logic:**
   - Map simulated user IDs/emails so signing in routes the user **directly** to their respective landing dashboard without showing a role picker:
     - **Senior Management / Executive (`executive@northfield.com` or `exec`):** Routes directly to the **Executive View (`Circularity Command Center`)**.
     - **Operational / End-User (`planner@northfield.com`, `warehouse@northfield.com`, or `user`):** Routes directly to the **SKU / Returned Assets (`Returned assets` / `Asset & Product Intelligence`)** operational view.
   - Support any password (or pre-filled dummy password `••••••••`) for frictionless demoing.
   - Add subtle, small "Demo Quick-Fill" pills at the bottom of the login form (e.g., `[Demo: Executive]` | `[Demo: Operational User]`) that auto-fill the input and sign in with one click, plus retain the top-right header account dropdown once logged in so presenters can switch roles mid-demo if needed.

---

### Task 2: Channelize a 1-to-1 Single-Asset Guided Journey
**Problem:** Jumping across unrelated assets or showing all assets at once confuses business stakeholders. The UI must demonstrate a 1-to-1 correspondence with the business user journey block diagram using **one single record** from start to finish.

**Implementation Requirements:**
1. **Primary Demo Record (`Voltara V4 motor`):**
   - Ensure one primary asset (`Voltara V4 motor` or the top featured asset) has a complete, end-to-end data trail across all 4–5 screen movements:
     1. **Sign-In** $\rightarrow$
     2. **Returned Assets Intake (SKU / Asset Selection)** $\rightarrow$
     3. **Diagnostic & Condition Assessment (Retrieved from EAM/QMS)** $\rightarrow$
     4. **AI/ML Lifecycle & Economic Inference (Predicted RUL & Value)** $\rightarrow$
     5. **Predicted Outcome & Disposition Approval (`Redeploy`, `Refurbish, then sell`, etc.)**.
2. **Guided Navigation Cues:**
   - Ensure clicking on the primary asset in `Returned assets` smoothly transitions through the stages of its journey so the presenter can walk through the exact 4–5 step sequence without dead ends.

---

### Task 3: Multi-Instance / Serial Number Support per SKU
**Problem:** A single client may purchase 100 units of the same machine SKU (e.g., `Voltara V4 motor`) and return 100 units. Each physical returned unit has a different diagnostic condition, grade, and economic path. Currently, the UI looks like it only lists one static asset per product name.

**Implementation Requirements:**
1. **Add Serial / Return Instance Selector in `Asset & Product Intelligence` & `Returned assets`:**
   - Under or alongside the SKU/Product selector (`Voltara V4 motor`) and `Client ID`, add an **Instance / Serial / Return Batch selector** (e.g., showing that Client A returned `100 units` of `Voltara V4 motor`, and allowing the user to view specific returned unit instances such as:
     - `SN-V4-0014 (Grade B — Refurbish, then sell — $1,480 est.)`
     - `SN-V4-0042 (Grade A — Redeploy — $2,150 est.)`
     - `SN-V4-0089 (Grade C — Harvest parts / Scrap — $420 est.)`).
   - Switching between these returned instances of the same SKU should dynamically update the condition grade, diagnostic metrics, RUL, and predicted economic path on the page.

---

### Task 4: Asset & Product Intelligence Page — Separate "Information" vs. "Inferences"
**Problem:** On the `Asset & Product Intelligence` page, raw data retrieved from databases (`EAM`, `QMS-818`, etc.) is mixed together with AI/ML model predictions. Furthermore:
- The `Condition, life and commercial value` card shows `EAM` as the source, but displays `Refurbish, then sell` under commercial value—even though `EAM` only provides raw condition data and does not decide commercial outcomes.
- The `Product intelligence` card only shows static product specifications, not intelligence.

**Implementation Requirements:**
1. **Two-Column / Two-Zone Structural Split:**
   - Reorganize the `Asset & Product Intelligence` dashboard into two distinct visual zones/columns with clear section headers:
     - **LEFT ZONE — `Retrieved Asset Information & Provenance (Database Source)`:**
       - Contains all raw facts and lineage pulled from enterprise systems (`EAM`, `QMS-818`, ERP, WMS).
       - Includes:
         - **Condition & Diagnostic Data** (sourced from `EAM` — Grade, physical inspection notes, cosmetic damage).
         - **Operating History** (sourced from `QMS-818` — e.g., `Certified operating period: 12 months`).
         - **Lifecycle Evidence Timeline** (consolidated from multiple databases).
         - **Product Specs** (renamed from `Product intelligence`).
     - **RIGHT ZONE — `AI / ML Model Inferences & Predictions`:**
       - Contains all model-computed estimations, statistical inferences, and disposition recommendations.
       - Includes:
         - **Estimated Remaining Useful Life (RUL)** (clearly badged as `ML Model Estimation`).
         - **Economic Intelligence & Predicted Commercial Value** (predicted recovery value, uplift vs. baseline, cost of refurbishment).
         - **Predicted Outcome / Recommended Disposition** (`Refurbish, then sell`, `Redeploy`, etc., with confidence score).
2. **Fix the `Condition, life and commercial value` Card:**
   - Remove the pre-populated commercial outcome (`Refurbish, then sell`) from the `EAM`-sourced condition block. `EAM` is only the source for condition/retrieval data; commercial value and disposition must only appear in the **Right Zone (Model Inferences)**.
3. **Rename `Product intelligence` $\rightarrow$ `Product Specs`:**
   - Change the card header `Product intelligence` to **`Product Specs`** (or `Product Specifications`), since it displays static hardware/product specifications rather than model intelligence.

---

### Task 5: Executive View (`Circularity Command Center`) Exception Refinements
**Problem:** Senior executives do not need to see operational line-item clutter. They only need high-level portfolio KPIs and a clean way to view exceptions by warehouse/value and notify the responsible owner.

**Implementation Requirements:**
1. **Verify Executive Exceptions View:**
   - Ensure the Executive view (`Circularity Command Center`) prominently displays top-level financial KPIs (`Baseline`, `Uplift`, `Recovery rate`, `Value recovered`, `Exceptions`).
   - In the **Exceptions** section, keep the drill-down strictly high-level: show **Warehouse**, **Item / Asset**, and **Value**. Do not clutter the executive view with deep operational line items.
   - Ensure the primary action on each exception row is **`Notify owner`** (assigning/pinging the operational owner when an item hasn't been actioned).

---

## 3. Acceptance Criteria (Definition of Done)
- [ ] Opening `index.html` displays a realistic **Login / Sign-In page** instead of the 8-card persona grid.
- [ ] Signing in as **Executive** lands directly on the `Circularity Command Center` with high-level Exceptions (`Warehouse`, `Item`, `Value`, and `Notify owner` action).
- [ ] Signing in as **Operational User / Planner** lands directly on the SKU / Returned Assets operational flow.
- [ ] A single asset (`Voltara V4 motor`) can be clicked and traced cleanly through a 4–5 step end-to-end journey matching the business flow.
- [ ] The `Asset & Product Intelligence` view supports selecting multiple returned instances/serials of the same SKU for a client (demonstrating how 100 returned units of the same machine have different conditions and economic paths).
- [ ] Raw database fields (`EAM`, `QMS-818`, `Lifecycle evidence timeline`, `Product Specs`) are visually separated on the **Left (Information)** from model outputs (`Estimated RUL`, `Predicted Commercial Value`, `Economic Intelligence`, `Predicted Outcome`) on the **Right (Inferences)**.
- [ ] `Refurbish, then sell` (commercial outcome) is removed from the raw `EAM` source block and placed strictly under the ML Inference/Prediction section.
- [ ] `Product intelligence` section is renamed to **`Product Specs`**.
- [ ] No console errors; single-file HTML/CSS/JS portability is preserved so it runs both locally and on GitHub Pages.