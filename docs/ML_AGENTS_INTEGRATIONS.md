# Circularity: ML models, agents, integrations and MCP servers

A high-level inventory, drawn from `README.md` and the data and logic blocks in `index.html`.

> **Note.** The demo does not contain any real ML. Its "predictions" are formulas driven by a random seed: per-class life constants, grade factors and a spread around each value, with fake model versions v1.0–v1.3. Section 1 is therefore a recommendation for what a real build would use, based on the prediction tasks the UI shows. Sections 2–4 list what the code actually defines.

---

## Contents

1. [ML models that fit Circularity](#1-ml-models-that-fit-circularity)
2. [Agents](#2-agents)
3. [Integrations, end to end](#3-integrations-end-to-end)
4. [MCP servers, end to end](#4-mcp-servers-end-to-end)

---

## 1. ML models that fit Circularity

### 1.1 Prediction tasks the product implies

| # | Task (where it appears) | Recommended models | Other options |
|---|---|---|---|
| 1 | **Resale price, with a P10/P50/P90 range** (`resale-price`, `predict_outcomes`) | XGBoost, LightGBM or CatBoost trained for the 10th, 50th and 90th percentiles; conformal prediction for honest ranges | NGBoost, a simple regression baseline, Bayesian hierarchical models for asset classes with little data |
| 2 | **Time to sell** (`time-to-sell`) | Survival models: XGBoost survival (Cox/AFT), Weibull AFT, Cox proportional hazards | DeepSurv, random survival forest |
| 3 | **Preparation cost and time** (`prep-cost-time`) | Percentile-trained gradient-boosted regression | Random forest, Tweedie GLM |
| 4 | **Repair success chance** (`repair-success`) | Gradient-boosted classifier, calibrated (isotonic or Platt) | Logistic regression (easy to explain to approvers) |
| 5 | **Service exposure**, i.e. expected service cost over the horizon (`service-exposure`) | Weibull reliability models, Poisson or Tweedie gradient-boosted models | Bayesian survival models |
| 6 | **Remaining useful life (RUL) as a range** | Weibull or survival models now. Once telemetry (AWS IoT Core) is connected: LSTM, GRU, TCN or Transformer sequence models | **Liquid neural networks (LNNs)**, which suit irregular, edge-sampled sensor data; physics-informed neural networks |
| 7 | **Condition grade from inspection photos** (SafetyCulture media) | Fine-tuned CNN or ViT (EfficientNet, ConvNeXt, ViT) | Multimodal LLM as an assistant to the human grader |
| 8 | **Lease outcome**: return, buyout, extension or early termination (Expected returns) | Multiclass gradient-boosted classifier | Multinomial logistic regression, competing-risks survival |
| 9 | **Return volumes and demand forecasts** by site and asset class | ARIMA/SARIMA, ETS, Prophet as baselines; then one global LightGBM with lag features | N-BEATS, N-HiTS, Temporal Fusion Transformer, DeepAR, with forecasts reconciled across site and class |
| 10 | **Market price index and commodity prices** (Ritchie Bros., material recovery) | ARIMA, VAR, GARCH for volatility | LightGBM with lag features |
| 11 | **Emerging signals and anomalies** (Command Center) | Isolation Forest, STL-residual anomaly detection, change-point detection (PELT, BOCPD) | Autoencoders |
| 12 | **Identity resolution** (the "Resolve identity" transform) | Probabilistic record linkage (Splink, Dedupe) | Siamese or embedding-based matching |
| 13 | **Ranking routes and settling close calls** | Learning-to-rank (LambdaMART), with the six gates kept as hard rules | Contextual bandits, but only after enough reconciled outcomes |
| 14 | **Reading documents**: certificates, test reports, rationale text | LLM extraction plus structured output | Layout models (LayoutLMv3, Donut) |

### 1.2 Not ML, but part of the decision engine

- **Pool optimizer:** an allocation problem, solved with mixed-integer or linear programming (OR-Tools, HiGHS, Gurobi). Stochastic optimisation if demand is uncertain.
- **Six gates:** deterministic rules. Keep them that way, since the hard rules say no agent may waive a gate.
- **CO₂e:** factor-based calculation from Persefoni emission factors, not a learned model.

### 1.3 Deep neural networks versus gradient boosting

The demo has about 1,400 closed decisions, which is a small tabular dataset. **Gradient-boosted trees will usually beat deep networks here.** Tabular deep models (TabNet, FT-Transformer, SAINT) are worth benchmarking but are unlikely to win. Deep networks earn their place in three areas: telemetry sequences (task 6), photos (task 7) and global forecasting at scale (task 9).

### 1.4 AutoML to consider

| Tool | Good for |
|---|---|
| **AutoGluon** (Tabular and TimeSeries) | The strongest open-source baselines for tasks 1–5, 8 and 9 |
| **H2O AutoML** | Tabular work, with leaderboards and explainability |
| **FLAML** | Lightweight, cost-aware tuning |
| **Nixtla StatsForecast / NeuralForecast** | AutoARIMA, AutoETS and neural forecasting |
| **Databricks AutoML** | Fits if you go the Databricks route (the Source map already offers Delta Sharing) |
| **Azure ML AutoML, Vertex AI, SageMaker Autopilot** | Managed options on each cloud (Azure fits with Entra ID) |
| **Optuna** | Tuning whatever model you hand-pick |

Use AutoML to set baselines and choose models, then lock each model into a registry such as **MLflow**. The product already relies on versioned models, calibration and bias checks (`get_model_validation`), and a rule that retraining never overwrites earlier evidence snapshots.

---

## 2. Agents

### 2.1 Five AI agents (`AGENTS` in `index.html`)

| Agent | Journey steps | Permissions | Tools it can call | Limit |
|---|---|---|---|---|
| Evidence Assembler | 1–2 | evidence:read | get_case_evidence, list_eligible_routes, get_model_validation | Read-only; can't change eligibility |
| Opportunity Finder | 2–4 | demand:read, market:read, pool:read | find_demand, predict_outcomes, optimize_pool, list_eligible_routes, get_case_evidence | Proposes options; can't commit stock or price |
| Gap Requester | 2 | evidence:read, request:write | get_case_evidence, request_missing_evidence | At most 5 inspection or test requests per case |
| **Handoff Coordinator** | 6 | instruction:write | get_case_evidence, request_approval, send_instruction | Sends only what a person approved; spend capped at the approved amount |
| Reconciler | 10 | outcome:write, evidence:read | get_case_evidence, reconcile_outcome, get_model_validation | Can't edit the original evidence snapshot |

> The README calls the fourth agent the "Execution Coordinator", but the code calls it the "Handoff Coordinator". This should be made consistent.

### 2.2 Services in Process orchestration that are not agents

Data preparation service, Gate engine, Prediction models, plus the human approval step.

### 2.3 Five hard rules for agents

- An agent can't waive a failed gate.
- An agent can't make a commercial commitment beyond its authority.
- Write tools that commit stock, spend or price always stop for a human.
- Tenant consent is checked on every call.
- Retraining never overwrites an earlier evidence snapshot.

---

## 3. Integrations, end to end

### 3.1 Nineteen source systems (`SOURCES` in `index.html`)

| Type | Vendor in the demo | Connection | Read or write | Also listed as alternatives |
|---|---|---|---|---|
| CRM | Salesforce Sales Cloud | API + events | R/W | Dynamics 365 Sales, HubSpot, SAP Sales Cloud |
| Lease management | Oracle Lease and Finance Mgmt | Poll 15 min | R | Odessa LeaseWave, SAP CLM, NetSuite Lease |
| ERP | SAP S/4HANA | API + events | R/W | Oracle Fusion, NetSuite, D365 Finance, Infor CloudSuite |
| Procurement | SAP Ariba | Poll 30 min | R | Coupa, Jaggaer, Oracle Procurement |
| EAM | IBM Maximo | API + events | R/W | SAP PM, Infor EAM, IFS, Oracle EAM |
| Field service (FSM) | ServiceNow FSM | API + webhook | R/W | Salesforce FS, D365 FS, IFS FSM, ServiceMax |
| PLM | Siemens Teamcenter | Poll 15 min | R | PTC Windchill, ENOVIA, Arena |
| BOM | Aras Innovator | Poll 15 min | R | OpenBOM, SAP ECC, Autodesk Fusion Manage |
| Quality (QMS) | MasterControl | Poll 30 min | R | ETQ, Veeva Vault QMS, Intelex |
| Engineering | Bentley AssetWise | Poll 60 min | R | Hexagon, Ansys Minerva, 3DEXPERIENCE |
| WMS | Manhattan Active WM | Events | R/W | SAP EWM, Blue Yonder, Oracle WMS, Körber |
| Reverse logistics | Optoro | API + webhook | R/W | Happy Returns, Narvar, Blue Yonder Returns |
| Inspection | SafetyCulture (iAuditor) | API + webhook | R/W | Fluke Connect, GoCanvas, Intelex |
| Repair | Fixably | API + webhook | R/W | RepairShopr, ServiceMax, Oracle Depot Repair |
| Device telemetry | AWS IoT Core (**not connected**) | n/a | n/a | Azure IoT Hub, ThingWorx, Siemens Insights Hub |
| Market pricing | Ritchie Bros. Market Data (**stale**) | Poll 60 min | R | Machinery Trader, EquipmentWatch, IronPlanet |
| Dealer network | Machinio | API + events | R | Dealer Spike, TractorHouse |
| Recycler partner | Sims Lifecycle Services (**manual**) | SFTP CSV import | R | ERI, Cascade, Li-Cycle |
| ESG and carbon | Persefoni | Poll 60 min | R | Watershed, Sphera, MS Sustainability Mgr |

### 3.2 Where approved instructions go (handoff targets)

- **ERP:** order management, stock transfer, receipts, finance
- **EAM:** diagnostic and repair work orders
- **WMS:** reservation, putaway, transfer, shipment, release
- **CRM / Lease:** sale task, lease contract
- **Recycler or exit partner:** collection, processing, custody certificate

### 3.3 Integration layer (Workflow studio)

- **Ingestion:** API gateway, event ingestion, file ingestion (SFTP or object store)
- **Validation and transforms:** validation and enrichment, unit normalisation, currency conversion, timestamps to UTC, code-table lookup, identity resolution, ordering late events, instruction envelope
- **File pipeline:** trigger file → unzip → chunk → manifest → import log → notify
- **Four delivery methods:** outbound API, event trigger, file generation, process orchestration
- **Seven canonical models:** Asset and component, Condition and eligibility, Demand opportunity, Intervention, Route candidate, Decision, Outcome
- **Connection types offered:** native connector, JDBC, API, event API, Delta Sharing, flat file
- **Authentication used:** OAuth 2.0 (client credentials, JWT bearer, mTLS), API key, API key with IP allow-list, service principal, basic auth over TLS, signed SFTP manifest

### 3.4 Platform integrations

- Identity: Microsoft Entra ID single sign-on and SCIM provisioning (simulated)
- Hosting: GitHub Pages via GitHub Actions (`.github/workflows/static.yml`)
- Google Fonts, the page's only external request

---

## 4. MCP servers, end to end

### 4.1 Circularity as an MCP server: 10 tools (`TOOLS` in `index.html`)

| Tool | Read or write | Gate |
|---|---|---|
| get_case_evidence | Read | none |
| list_eligible_routes | Read | none |
| predict_outcomes | Read | none |
| optimize_pool | Read | none |
| find_demand | Read | none |
| get_model_validation | Read | none |
| request_missing_evidence | Write | Gap Requester only |
| request_approval | Write | human approval |
| send_instruction | Write | human approval, plus an approval reference |
| reconcile_outcome | Write | Reconciler only |

### 4.2 Circularity as an MCP client: 5 enterprise servers (`CLIENT_SERVERS` in `index.html`)

| Server | Vendor in the demo | Status | Tools |
|---|---|---|---|
| ERP MCP server | LedgerOne | connected | inventory.get, purchase_plan.get, cost.get, reservation.create |
| EAM MCP server | AssetCore | connected | asset.get, work_order.create, work_order.status, failure.list |
| CRM MCP server | LeaseDesk | connected | opportunity.list, contract.get, sale_task.create |
| Market data MCP server | DealerBridge | token expired | comparables.search, offers.list |
| PLM MCP server | BOMGraph | not available | none (falls back to polling the REST API) |

### 4.3 MCP server proposals: 3

| Server | Vendor in the demo | Access | Tools | Status |
|---|---|---|---|---|
| Fleet telematics MCP server | TrackLine | read | telemetry.hours, telemetry.duty_cycle | pending |
| Freight booking MCP server | ShipLane | write | shipment.book, shipment.cancel | **declined** (no human approval step) |
| Supplier catalogue MCP server | PartsHub | read | part.search, part.price | approved |

> The vendors behind the MCP servers (LedgerOne, AssetCore and the rest) are invented. The 19 source systems use real product names, but nothing is actually connected.
