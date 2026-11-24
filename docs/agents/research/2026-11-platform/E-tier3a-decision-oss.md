# E. Tier 3a: open-source decision, process and policy engines for Business Studio (24 Nov 2026)

Part E of the platform research (brief: [00-brief.md](00-brief.md)). Question: which open-source BPMN/DMN engines,
decision engines, policy engines, rollout tools and ML libraries should Business Studio (the Modeler) adopt, learn
from or avoid, and should it switch its model format to BPMN/DMN.

> **Legal review.** Every licence finding below comes from public licence files, package metadata and vendor posts read
> on 24 Nov 2026. It is not legal advice. It needs review by Kinective's Legal team before anyone relies on it,
> in particular for anything we would redistribute in the customer trial package.

## Summary

1. **Keep our own flow graph as the model of record.** It carries what BPMN/DMN do not: locked nodes, guardrails with
   owners, scope dimensions, maker-checker, shadow and parity with the demo. Add **export** to DMN 1.x decision tables
   and BPMN 2.0 (a documented subset), and a narrow **import** of DMN decision tables. That buys interop and
   credibility without a JVM or a second engine.
2. **Embed GoRules ZEN (MIT, Rust core, Python wheel 2.1.8, 20 Nov 2026)** as the evaluator for a new `table` rule
   node (decision tables and expressions), with the MIT React JDM editor for the table UI. Disable its function (JS)
   nodes. CEL (`cel-python`, Apache-2.0) is the fallback expression language.
3. **Do not embed a BPMN engine now.** Camunda 8 needs a paid licence for self-managed production (8.6 and later);
   Camunda 7 CE is end of life (7.24, Oct 2025, no more security patches); Operaton, Flowable and Apache KIE are
   healthy but JVM. SpiffWorkflow (pure Python, LGPL-3.0) is the only credible embeddable one; keep it as the plan B.
4. **Build the process layer (SLAs, timers, escalations, human tasks) ourselves** on the Postgres queue (`run_after`),
   the workflow Wait step, proposals and approvals, as declarative JSON, and export it as BPMN for people who want to
   see BPMN.
5. **Authorization stays in `di.core.policy`**; learn from Cedar for a declarative policy file later. Approval
   thresholds are decision rules, not authorization. Avoid OpenFGA (second store) and Oso OSS (deprecated Dec 2023).
6. **Back-testing, shadow and canary** extend what exists (`simulate.py`, `shadow_decision`); add a replay harness with
   as-of data, golden test cases per flow, and hash-bucket canary by org unit. Avoid Unleash (AGPLv3 since v8, Jun 2026).
7. **ML**: LightGBM/XGBoost quantile models behind the existing `Predictor` interface, MAPIE conformal intervals to
   drive "low confidence goes to a person", our own model-candidate table as the registry (MLflow only as a file format).

## 1. What we have today (the ground this advice stands on)

Read from `backend/di/services/modeler/` and the files it uses (24 Nov 2026, commit `0c71585`).

| Piece | File | What it does | Relevance to engines |
|---|---|---|---|
| Flow graph | `modeler/flow.py` | Nodes `{id, t, x, y, label, …}` of 11 types; 8 types are **locked** (trigger, agent, gate, guard, decision, approval, execute, learn); edges `a>b` | A BPMN-like graph, but most nodes are fixed stages, not free process steps |
| Compile | `modeler/compile.py` | A `rule` node counts only if it has a path, is reachable from the gate, reaches the decision and breaks no guardrail; unreachable paths become the pseudo-rule `FLOW` | This is our "deployment" step; DMN/BPMN export would hang here |
| Apply | `modeler/apply.py` | Rules in order: `exclude`, `require`, `prefer`, scoped by case; if nothing is left eligible, rules are waived | A first-hit, ordered decision table with a fallback; maps to DMN hit policy `FIRST` (approximately; see section 8) |
| Scope | `modeler/scope.py` | `set`, `min`, `max` dimensions per template | Equivalent to DMN unary tests (`"A","B"`, `>= x`, `< x`) |
| Guardrails | `modeler/guard.py`, `templates.py` | Each guardrail `forbids` (path, actions, scope) and `protects` (regexes on plain text); named owners | No direct equivalent in DMN or BPMN; this is our policy layer |
| Validate | `modeler/validate.py` | ok/warn/fail checks: lone nodes, unreachable rules, conflicts (same path, overlapping scopes) | Similar to DMN table completeness/overlap analysis |
| Simulate | `modeler/simulate.py` | Candidate vs published rules over a queue; flips and value delta; device extras (cash, days, SLA) | Our back-test kernel; pure, valuation injected |
| Parse / propose / suggest | `parse.py`, `propose.py`, `suggest.py` | Plain language to `{path, action, scope}`; suggestions from overrides (min 3, share 0.6) | Restricted target language is easy for an LLM to emit and check |
| Lifecycle | `services/actions/modeler.py`, `models/modeler.py` | draft → review → shadow → pub; maker ≠ checker; history for rollback; `shadow_decision` rows (live vs shadow route and net) | Already what DMN/BPMN suites sell as "governance" |
| Valuers | `modeler/valuers/tool_fleet.py`, `device.py` | Per-template valuation ported from the PO prototype | ML plugs in here |
| Predictor | `services/engine/predictor.py` | `FormulaPredictor`: "a trained model (XGBoost or LightGBM, as the demo names) can replace one formula at a time" | The ML seam exists |
| Calibration and models | `services/engine/calibration.py`, `services/actions/models.py` | Median actual/predicted per (template, route, class), clipped [0.5, 1.5]; fit → propose → promote with maker-checker | Our "model registry" |
| Policy | `di/core/policy.py` | Port of the demo's RBAC: roles, permissions, tenant grants, delegations, approval limits per role | Our authorization layer |
| Timers | `di/core/jobs.py`, `di/workflow/waits.py` | Jobs with `run_after`, retries, dead letters; the workflow Wait step parks records and resumes them | The building blocks of SLA timers and escalations |

Gaps that matter for the choices below:

- **No expression language.** A rule's condition is only set/min/max over template dimensions. Contract terms
  ("may we refurbish and resell?"), price bands and wear-index thresholds need richer conditions.
- **No confidence.** `grep confidence` finds nothing in `services/engine`, `services/modeler` or `services/cases`.
  "Low model confidence goes to a person" (brief, want 2) has no data to act on yet.
- **No case-level SLAs, timers or escalations** on decisions and approvals (the execution plan has need-by slack;
  workflows have Wait steps; approvals do not time out or escalate).
- **No standard export.** Flows export as our JSON only.

## 2. BPMN and DMN engines

| Engine | Licence (verified 24 Nov 2026) | Runtime | Embeddable in Python? | Latest release seen | Fit for us | Effort to adopt |
|---|---|---|---|---|---|---|
| Camunda 8 (Zeebe, Operate, Tasklist, Optimize, Identity) | Source: Camunda License v1 (source-available). Compiled: proprietary; **production needs the Self-Managed Enterprise Edition**, "all Camunda 8 components version 8.6 and higher". Desktop Modeler MIT; Connector SDK and REST connector Apache-2.0 | JVM cluster plus a secondary store (Elasticsearch/OpenSearch, or RDBMS in recent versions, **unconfirmed** for our version) | No; gRPC/REST clients only | Docs at 8.10 | Poor: licence blocks the trial package; heavy | Very high |
| Camunda 7 CE | Apache-2.0 | JVM, embeddable in Java | No | **7.24, Oct 2025, the last CE release; no further releases or security patches**; Enterprise supported to April 2030 | Avoid: end of life | n/a |
| Operaton (Camunda 7 fork) | Apache-2.0 (licence link on operaton.org; governance "legal work in progress") | JVM (Spring Boot 4, Quarkus, WildFly in 2.2) | No; REST API | v2.2.2, 20 Nov 2026 (GitHub releases) | Good interop target for customers who mandate a BPMN engine; not embeddable | High (JVM service) |
| CIB seven (another Camunda 7 fork) | Open source, Apache-2.0 per vendor pages (**unconfirmed**, licence file not read) | JVM | No | 2.x (vendor page) | Same role as Operaton | High |
| Flowable | Apache-2.0 | JVM; Java 17+ for v7 | No; REST (`flowable/flowable-rest` image) | 8.0.0, 27 Feb (year not shown; 2026 by sequence, **unconfirmed**) | BPMN + CMMN + DMN in one; CMMN is a good model for case work; JVM | High |
| Apache KIE (Drools, jBPM, Kogito) | Apache-2.0; still **incubating** at the ASF; the README asks for "a thorough licensing review" | JVM (Quarkus, Spring Boot, GraalVM native) | No | 10.2.0, April 2026 | Strongest DMN/FEEL implementation in OSS; JVM; learn from | High |
| SpiffWorkflow | **LGPL-3.0** (PyPI classifier) | Pure Python library | **Yes**: in-process, serialises workflow state to JSON | 3.2.0, 10 Aug 2026 (3.2.1 pre-releases after) | Only real in-process BPMN option; DMN "baseline implementation"; Python expressions | Medium |
| SpiffArena (app around SpiffWorkflow) | **LGPL-2.1** in `LICENSE` (README says LGPL-3; inconsistent) | Python backend + Celery + React frontend, MySQL/Postgres, needs an OpenID server | It is an app, not a library | v5.1.0, 12 Nov (year not shown; 2026 likely, **unconfirmed**) | Avoid as a platform (second API server, auth, worker); learn from its BPMN-in-Python UX | n/a |
| bpmn-js / dmn-js (bpmn.io) | MIT text **plus a watermark clause**: the code that shows the bpmn.io watermark "MUST NOT be removed or changed" and it "must stay fully visible and not visually overlapped". Copyright Camunda Services GmbH | Browser (JS) | Frontend only | Active (not checked per release) | Fine as a read-only BPMN/DMN viewer of our exports, if the product accepts a visible bpmn.io watermark | Low (viewer) / high (editor) |

Notes per engine:

- **Camunda 8.** The licence page lists Zeebe, Operate, Tasklist, Identity and Optimize under Camunda License v1 for
  source and proprietary terms for compiled software, and says "To use the software in production, purchase the
  Camunda Self-Managed Enterprise Edition". Camunda's April 2024 blog announced this change for 8.6 (Oct 2024). We could
  not ship Camunda 8 inside a trial package that customers run, and a customer who already owns Camunda would bring
  their own. Camunda markets agentic orchestration (AI agent tasks in BPMN, ad-hoc sub-processes) in recent releases;
  we did not read release notes for exact versions (**unconfirmed**). This is the "BPMN + agents" competitor the brief
  names; see section 8 for how we answer it without adopting it.
- **Camunda 7 CE** is out: its final release 7.24 shipped in October 2025 with no further releases "including security
  patches"; only paying Enterprise customers get support to 2030.
- **Operaton** is the active community fork (Apache-2.0, BPMN 2.0 and DMN 1.3, 2.2.2 on 20 Nov 2026, patch releases
  planned to Mar 2027). Its site mentions managing the engine "via MCP". It is a sensible **target** for our BPMN export
  (a customer deploys our exported process on their Operaton), not something we embed.
- **Flowable** keeps its open-source engine under Apache-2.0 (BPMN, CMMN, DMN, REST). Its CMMN (case management:
  stages, sentries, milestones, discretionary tasks) is closer to our "case" than BPMN is; worth reading before we build
  the process layer.
- **Apache KIE** (Drools 10.2.0, April 2026) has the most complete DMN/FEEL stack and the DMN TCK culture. Still in the
  ASF Incubator; JVM only.
- **SpiffWorkflow** is the only engine that runs inside our Python process. Pros: pure Python, executes BPMN 2.0 with
  Python script tasks and a DMN baseline, workflow state serialises to JSON (which we would keep in Postgres JSONB, so
  no second store). Cons: LGPL-3.0 (dynamic linking of an unmodified Python library is usually fine under LGPL, but we
  redistribute it in the trial image, so Legal must confirm the obligations: notice, source offer, allowing
  replacement); Python expressions in diagrams are a code-injection surface we would have to sandbox; a single
  maintainer company (Sartography); its DMN is "baseline".
- **bpmn-js / dmn-js.** The watermark clause matters for a product UI: a hand-built canvas (ours today) has no such
  constraint. Use bpmn-js only for a "View as BPMN" tab on exported diagrams, never as our main editor.

## 3. Decision engines (rules and expressions)

| Library | Licence | Runtime | Python | Latest release seen | Fit | Effort |
|---|---|---|---|---|---|---|
| **GoRules ZEN engine** (JDM decision graphs) | MIT (engine, crates, bindings) | Rust core; bindings for Python, Node, Go, Java/Kotlin, .NET, Swift, Android | `pip install zen-engine` (abi3 wheels, Python ≥3.7 metadata, cp38 abi3 wheel) | Python 2.1.8, 20 Nov 2026; engine line 2.x "first stable release of the new engine line" | **High**: decision tables, switch, expression and sub-decision nodes in a JSON graph; same model in browser and server | Medium |
| GoRules JDM editor (`@gorules/jdm-editor`) | MIT ("MIT © GoRules") | React component (Decision Graph, Decision Table); uses Monaco | Frontend | Release list not shown on GitHub (**unconfirmed**) | High for the table editor; check its peer dependencies (UI kit, React version) against React 18 (**unconfirmed**) | Medium |
| GoRules BRMS | Commercial product (managed, self-hosted or embedded); terms not public on the repo page | n/a | n/a | n/a | Not needed; we have the lifecycle | n/a |
| CEL: `cel-python` | Apache-2.0 | Pure Python | Yes | 0.5.0, 31 Jan 2026 | Good fallback expression language: typed, non-Turing-complete, used by Kubernetes and Google APIs | Low |
| CEL: `common-expression-language` (PyO3 over cel-rust), `cel-expr-python` (C++ wrapper) | Not checked (**unconfirmed**) | Native | Yes | Not checked | Faster CEL options; less mature in Python | Low |
| JsonLogic | Original `json-logic` (MIT) last uploaded **4 Dec 2015**; forks `maykin-json-logic-py`, `python-jsonlogic`, `panzi-json-logic` (licences and dates **unconfirmed**) | Pure Python, JS | Yes | Stale upstream | JSON-shaped rules suit an LLM, but semantics differ between implementations (the `json-logic` page warns `==`/`===` differ from JS) | Low, but fragile |
| `rule-engine` | BSD-3-Clause | Pure Python | Yes | 5.2.1, uploaded 24 Nov 2026 | Small typed expression language over Python objects; a single maintainer | Low |
| `durable_rules` | MIT | C core + Python | Yes | **2.0.28, 7 Jun 2020** (no release since) | Avoid: unmaintained, Rete forward chaining we do not need | n/a |
| `pyDMNrules` | **GPLv3** (classifier) | Pure Python (pandas, openpyxl, pySFeel) | Yes | 1.4.5, 22 Aug 2026 | Reads DMN from **Excel workbooks**, not DMN XML; GPL is a redistribution problem | Avoid in the product; fine as a test oracle on a dev machine |
| SpiffWorkflow DMN | LGPL-3.0 | Python | Yes | 3.2.0 | "Baseline" DMN with Python expressions, not FEEL | Medium |

### 3.1 Why ZEN, and how it fits our graph

JDM is a JSON graph of nodes (input, output, decision table, switch, expression, function, sub-decision). Our rule
model is already a tiny decision table (ordered rows of scope → action on a path). ZEN would give us, without a JVM:

- **Decision tables** with first-hit by default and per-column collect (`tags[]`), close to DMN hit policies `FIRST`
  and `COLLECT` (ZEN does not name DMN hit policies; mapping **unconfirmed** beyond these two).
- **ZEN expression language** for conditions written as business statements (`grade in ["A","B"] and hours < 2000`),
  usable for contract-terms tables, price bands and wear-index thresholds that `scope.py` cannot express.
- **One model in browser and server**: the same JDM evaluates in the React editor's test panel (Node/WASM, **unconfirmed**
  for the browser) and in our worker through the Python wheel. That keeps "test run" and "live" identical, the same
  property our parity tests protect.
- **MIT licence** for the engine and editor: no redistribution issue for the trial package (Legal to confirm).

How to embed it without giving up our model:

1. Add a node type `table` to `flow.py` whose payload is a JDM decision (table or small graph). It sits between the
   gate and the decision, like a `rule` node, and **outputs the same thing a rule outputs**: per path one of exclude /
   require / prefer / waive / require approval, plus a reason text. `compile.py` turns each matched row into a
   `CompiledRule`, so `apply.py`, guardrails, validation, simulation and shadow keep working unchanged.
2. Evaluate JDM through a port (`DecisionTableEvaluator`) with ZEN as the adapter, so the engine can be swapped (CEL or
   our own) and tests can pin it.
3. **Disable function nodes** in our validator: in ZEN they run JavaScript in an embedded JS runtime (QuickJS in the
   versions we know of; **unconfirmed** for 2.x). Arbitrary code in a business user's decision is a security and
   explainability problem. Allow input, output, table, switch, expression and sub-decision only.
4. Guardrails run **after** the table (as today after rules): a table row that would break a guardrail is blocked by
   `rule_breaks`, so a JDM table can never weaken a guardrail.
5. Keep numbers exact: the ZEN 2.x Rust crates no longer enable `arbitrary_precision` by default; check what the
   Python wheel does with money values before using it for prices (**unconfirmed**).

Effort: about 2–3 weeks for one engineer for the node type, the port, the validator rules, the compile path and the
editor panel; plus template content for the tool-fleet contract-terms table and device price bands.

### 3.2 CEL as the fallback

If ZEN's Python binding disappoints (numeric behaviour, wheel availability on our base image, maintenance), use CEL for
expressions inside our own table model: `cel-python` (Apache-2.0, pure Python, 0.5.0 Jan 2026) is slow but simple;
the native wrappers are faster but younger. CEL is not a decision-table format, so we would keep our own table JSON and
write the table editor ourselves.

## 4. Policy and authorization (tenant boundaries, approval thresholds, maker-checker)

What we have: `di/core/policy.py` (327 lines) ports the demo's RBAC with tenant grants that end, delegations, approval
limits per role (`STARTING_LIMITS`), and the action pipeline enforces it at 12 steps. Maker-checker is enforced in the
action guards (the maker of a flow or model cannot approve, publish or promote it) and agents are refused by
`FORBIDDEN_ACTIONS`.

| Engine | Licence | Runtime | Python | Latest release seen | Fit | Notes |
|---|---|---|---|---|---|---|
| OPA / Rego | Apache-2.0 (CNCF graduated) | Go binary (sidecar or server); WASM compile target | Through HTTP or WASM | v1.22.4, 12 Nov 2026 | Medium: powerful, but a sidecar and a new language | Aug 2025: OPA's creators and many Styra staff joined Apple; the OPA blog says governance and licence are unchanged; later reviews list all six `opa` maintainers as Apple-affiliated. Bus-factor risk to watch |
| Cedar (`cedarpy`) | Apache-2.0 (repo) | Rust core via Python wrapper | Yes, in-process | cedarpy 4.12.2 (wraps Cedar 4.12.0), 14 Oct 2026 | **Best fit to learn from**: RBAC + ABAC, schema validation, analysable policies, in-process | Wrapper says it "is in its early stages" and "is not officially supported by AWS or the Cedar Policy team"; partial evaluation experimental |
| OpenFGA | Apache-2.0; CNCF incubating since 28 Oct 2025 | Go server with its own datastore (Postgres possible) | SDK over HTTP | v1.23.0, 20 Nov 2026 | Low now: relationship-based access (Zanzibar) is more than we need and is a **second store** of who-may-see-what | Reconsider if customers need sharing across org trees at scale |
| Casbin (`pycasbin`) | Apache-2.0 | Pure Python | Yes | 2.8.0, 2 Feb 2026 | Medium: model + policy files, Postgres adapter; generic | Would duplicate `policy.py` without adding analysis |
| Oso (OSS library, Polar) | Apache-2.0 per listings | Rust core + bindings | Yes | Deprecated **18 Dec 2023**; the vendor moved to a hosted service (Oso Cloud); the repository was archived on 22 Oct 2026 and the README says the library is no longer maintained (corrected in verification, see V-verification.md) | Avoid | Licence was not changed; the library was deprecated |

Recommendations:

- **Keep authorization in `policy.py` and the pipeline.** It is small, tested against the demo and enforced on the
  server. Swapping in an engine buys little until customers want to **author** access policies themselves.
- **Approval thresholds are decision rules, not authorization.** "Over $25k needs a Finance approver", "low confidence
  goes to a person", "IT asset without an erasure certificate cannot be redeployed" belong in the Modeler as
  `require approval` rules and guardrails (versioned, simulated, maker-checker), with `policy.py` only answering "may
  this person approve this amount". This keeps want 3 (guardrails per asset type) in one place.
- **Learn from Cedar** for a later declarative policy file: principals (people, agents), actions (the ~125 catalogue
  actions), resources (cases, flows, org units), conditions on attributes (tenant, amount, role). If we adopt it, use
  it behind our `policy` port, keep the pipeline as the only enforcement point, and keep `FORBIDDEN_ACTIONS` as a
  hard-coded list outside any editable policy.
- **Maker-checker stays in our lifecycle**; no engine above models "a different person than the one who saved the
  draft" better than our journal does.

## 5. Rule testing, simulation, back-testing replay, shadow and canary

What exists: `simulate()` (candidate vs published rules on the open queue, flips and value delta), `flow.simulate` and
`flow.propose` (simulate before saving), shadow status with `shadow_decision` rows (live vs shadow route and net), and
rollback from `decision_flow_version`.

### 5.1 Patterns to add

| Pattern | What it is | How it fits us | Effort |
|---|---|---|---|
| **Golden test cases per flow** (the DMN TCK idea, applied to one customer's rules) | A flow version carries example cases with the expected route; `validate` fails if a change flips one without an explicit "expected change" | A `tests` array in the flow JSON; reuse `simulate` to run them; show failures as `fail` checks | Small (days) |
| **Back-test replay** (want 4, the sales motion) | Load a month or quarter of historical returns with their actual disposition and realised value; decide each with the candidate flow using data **as known at decision time**; compare | New import (CSV template) into canonical records with an `as_of`; a replay job over the queue; a report: uplift as a range, per route, per class, with flips listed | Medium (2–4 weeks) |
| **Shadow** | Exists | Add a shadow report that aggregates `shadow_decision` by template/org: flip rate, value delta, guardrail hits | Small |
| **Canary by bucket** | Publish to a share of cases before all | New status `canary` with a percentage; bucket by a stable hash of case id (or by org unit); the decision records which flow version decided it | Medium |
| **Champion/challenger for models** | Two models score; one decides | Extend `model_version` with `challenger`; log both predictions; promote with maker-checker | Medium |

Back-test pitfalls to design in from the start (these decide whether the uplift number survives a customer's finance
team):

- **Leakage.** Use only facts dated before the historical decision (as-of joins on canonical records). Prices and
  channel fees must be those of the time.
- **Counterfactuals.** We observe the realised value only for the route actually taken. For other routes we have model
  estimates; report uplift as an interval (section 6), not one number, and separate "same route, better price" from
  "different route".
- **Capacity.** A replay that sends every unit to the best channel ignores channel capacity and lot caps; the device
  valuer already has lot-size caps and an SLA; keep them on in replay.
- **Explain every flip.** Each flipped case keeps its rule trace, the same as a live decision.

### 5.2 Feature-flag tools

| Tool | Licence | Notes | Verdict |
|---|---|---|---|
| OpenFeature (`openfeature-sdk`) | Apache-2.0; Python SDK 0.10.0, 1 Jun 2026; CNCF project | A vendor-neutral flag-evaluation API with providers and hooks | **Learn from / optional adopt**: if we expose "which flow version applies" as a flag, an in-house provider keeps the API standard. Not needed to ship canary |
| Unleash | **AGPLv3 from v8.0.0 (blog of 2 Jun 2026)**; official Docker images stay Apache-2.0 if unmodified; SDKs keep permissive licences; enterprise commercial | A second server and database | **Avoid** for embedding or redistribution |
| GrowthBook | MIT for most of the repo; directories `packages/*/enterprise` under the GrowthBook Enterprise License | Strong experiment statistics (Bayesian and frequentist) | **Learn from** for how to report uplift and significance; do not embed |

Our canary does not need a flag server: the flow version is already data in Postgres, and the pipeline already
journals which version decided.

## 6. ML for pricing and confidence

Seam: `services/engine/predictor.py` says a trained model can replace one formula at a time; `calibration.py` fits
factors on confirmed outcomes; `model.fit/propose/promote` give maker-checker. Missing: a stored model artefact, a
prediction interval, and confidence as a hold reason.

| Library | Licence | Latest release seen | Use |
|---|---|---|---|
| LightGBM | MIT (project licence; PyPI metadata empty, **unconfirmed** from metadata) | 4.7.0, 18 Jul 2026 | Device price per channel; quantile objective for P10/P50/P90 |
| XGBoost | Apache-2.0 | 3.4.1, 15 Aug 2026 | Same; pick one of the two to keep the image small |
| MAPIE | BSD-3-Clause | 1.6.0, 19 Oct 2026 | Conformal prediction: calibrated intervals with a coverage guarantee under exchangeability; conformalised quantile regression |
| sktime | BSD-3-Clause | 1.3.0, 8 Nov 2026 | Time-series models for telemetry and price trends |
| Darts | Apache-2.0 (**unconfirmed**; PyPI page did not load) | **unconfirmed** | Alternative to sktime; heavier (deep models) |
| MLflow | Apache-2.0 | 3.18.0, 3 Nov 2026 | Tracking server, registry; brings its own server and store |

### 6.1 Device trade-in template (price prediction, dynamic channel routing)

- Train one gradient-boosted model per channel (or one with channel as a feature) on recent sales: model, storage,
  grade, age, channel, days to sell, season. Predict expected cash and days to sell, which is what `device.py`'s
  `dScore` consumes (cash per unit, days, SLA penalty). The valuer stays the decider; the model only replaces formulas.
- Wrap it with MAPIE to get an interval per channel. Two simple confidence signals:
  1. **Interval width** relative to the point estimate above a template threshold.
  2. **Ambiguity**: the best two channels' intervals overlap so much that the ranking is not reliable.
- Either signal adds a hold reason "low confidence" and routes the decision to a person (a `require approval` with
  reason, not a new mechanism), which is exactly want 2. The threshold is a template setting in the Modeler, versioned
  and simulated like any rule; a back-test shows how many cases it would send to people.
- Conformal guarantees assume new data looks like the calibration data; recalibrate on a rolling window and show the
  observed coverage on the Models panel (a drift alarm when coverage falls).

### 6.2 Tool-fleet AMS template (RUL, wear index, explainable)

- The brief says we **read** grading and RUL from the repair centre and PLM, not compute them. Keep it so: RUL is a
  fact with a source and a timestamp, and rules are scoped on it (`min`/`max` dims, or a ZEN table).
- Where we must estimate (no PLM value), prefer explainable models: a wear-and-tear index as a weighted sum of
  operating hours, load cycles and alarms against design life, or a Weibull/survival fit per class. A person can read
  the formula on the disposition card. sktime is enough for trend features; avoid deep sequence models for the pilot.
- Show the inputs and their contribution on the card (a feature-contribution list for tree models; SHAP is the usual
  tool, MIT licence, version **unconfirmed**).

### 6.3 Registry: our model candidates vs MLflow

Keep our own table as the registry: it already has candidates, metrics, propose/promote with maker-checker, the
journal, and it lives in Postgres. Running an MLflow server in the trial package adds a second server and a store. Do
use plain artefact files (a pickled or native-format booster, its feature list, its conformal calibration scores, a
model card JSON) stored in Postgres (`bytea`) or a volume, referenced from `model_version`. MLflow's `MLmodel` file
format is optional if a customer's data team wants to bring a model trained in their MLflow.

## 7. How the pieces map onto the brief's wants

| Want (brief) | Answer in this report |
|---|---|
| 1. Pitch flow, Studio first ("create a template for my AMS process") | The LLM emits our flow JSON plus optional JDM tables (both JSON, both validated); BPMN export shows it in standard notation |
| 2. Humans approve, agents plan; people only on thresholds, low confidence, exceptions | Thresholds and confidence as `require approval` rules and guardrails; MAPIE intervals for confidence |
| 3. Guardrails per asset type | Stay our guardrails (locked, owned); tables run before them and cannot weaken them |
| 4. Back-testing as the sales motion | Replay harness with as-of data and uplift intervals (section 5.1) |
| 5. Two pilot templates | Tool fleet: contract-terms JDM table, RUL as read facts. Device: GBM + conformal per channel |
| 10. Declarative workflow JSON as the contract | Our JSON stays the contract; BPMN/DMN are exports |
| 12. Keep connection workflows separate from decision rules | ZEN lives only in Tier 3a; the Workflow Studio keeps its own blocks |
| 13. Positioning next to BPMN + agents vendors | Section 8 |

## 8. The key question: BPMN/DMN as our model format, and a process layer above decisions

### 8.1 Options

| Option | What it means | For | Against |
|---|---|---|---|
| **A. BPMN + DMN native**: our canvas edits BPMN/DMN XML; an engine executes it | Replace `flow.py` with BPMN, `rule` nodes with DMN tables; embed SpiffWorkflow or call Operaton/Flowable | Standard notation; customers' BPM teams recognise it; tool interop | Locked stages, guardrails with owners, scope dimensions and shadow are not BPMN/DMN concepts and become extension elements nobody else reads; a JVM or an LGPL engine; parity with the demo's 128 cases at risk; an LLM generating valid BPMN XML is harder than our small JSON; non-technical users find BPMN heavy |
| **B. Own graph + export/import** (recommended) | Our JSON stays the model of record; export BPMN 2.0 (process view) and DMN 1.x (rule tables); import DMN decision tables into `table` nodes | Keeps every existing guarantee; interop where it is cheap; credibility via "export to your BPM suite" | Round-trip is lossy (export carries our semantics as documentation/extension attributes); we must document the subset |
| **C. Own graph + embedded decision-table engine** (recommended, with B) | ZEN as evaluator for `table` nodes; JDM as a second import/export format | Rich conditions without a JVM; MIT; a ready table editor | A Rust wheel in the image; one more expression language to document |
| **D. Own decisions + embedded BPMN engine for the process layer** | SpiffWorkflow runs SLAs, timers, human tasks above our decisions | Real BPMN execution in Python | Two state machines for one case (Spiff state and our case/approval/proposal state) that must agree; LGPL; Python script tasks to sandbox; our pipeline must stay the only write path, so every Spiff task would call back into actions anyway |
| **E. External BPMN engine** (Camunda 8, Operaton, Flowable) as the orchestrator | Our product becomes a set of service tasks under someone else's process | Fits customers who already standardised on one | Camunda 8 licence; JVM; contradicts "one write path, control plane in-house" (already decided in `../2026-11-agent-foundation.md`) |

### 8.2 Recommendation

**Model format: B + C.** Keep our flow graph as the model of record, add `table` nodes evaluated by ZEN, and add
exporters:

- **DMN export** (DMN 1.3 or later XML, the version to match Operaton/Flowable/KIE import; **unconfirmed** which minor
  version each accepts): one decision per published flow; a decision table with hit policy `FIRST` whose rows are the
  compiled rules in order (inputs = template dimensions; output = path and action); guardrails exported as a second
  table with an annotation "locked, owner X". The waive-all fallback (`apply.py`: no route left means rules are waived)
  has no DMN equivalent; export it as an annotation and a final default row, and say so in the docs.
- **DMN import (narrow)**: decision tables with unary tests on known dimensions and outputs naming a known path and
  action; anything else is refused with a clear message. Map FEEL unary tests to ZEN expressions or to our scope.
- **BPMN 2.0 export** of the case process (section 8.3): start event per trigger, service tasks for read/predict/
  decide/execute, a business rule task referencing the DMN decision, user tasks for approvals, timer boundary events for
  SLAs, exclusive gateways for routes. View it with bpmn-js (watermark visible) or open it in any modeler.
- **JDM import/export** for `table` nodes, so a customer can author a table in the GoRules editor and paste it.

Why not A: what makes our flows valuable is not the boxes and arrows, it is the locked stages, owned guardrails,
scoped rules, simulation over real queues, maker-checker with shadow and rollback, and the agent gate. BPMN/DMN
encode none of that natively, so adopting them as the model makes the important parts second-class while adding a
JVM or an LGPL engine. The credibility argument is real, but buyers judge it by "can I see and export it in BPMN/DMN
and run it in my suite", which B gives at a fraction of the cost.

**Process layer: build it ourselves, declaratively, and export it as BPMN.** A "case process" per template:

- **Stages** (intake, triage, receiving/grading, decision, approval, execution, reconciliation; the four reverse-
  logistics stages the brief lists map onto these), each with an **SLA** (duration, calendar, clock start event).
- **Timers**: a job with `run_after` (exists in `di.core.jobs`) per open SLA; on fire it emits an event and takes the
  configured step.
- **Escalations**: notify, reassign to a role or a delegate (delegations exist in `policy.py`), raise priority in "My
  work", or hold for a person. Never approve automatically (rule 10 of AGENTS.md).
- **Human tasks**: what we already have as approvals, proposals and conflicts, given one shape (assignee or role,
  due date, outcome) and listed in "My work" (want 11).
- Stored as JSON beside the flow, versioned and published through the same maker-checker lifecycle; the canvas renders
  it (want 10); exported as BPMN for people who want it.

Why build: the hard parts (durable timers, retries, dead letters, the single write path, journal, delegations,
approvals) already exist in our code; an embedded engine would add a second state machine for the same case and
bypass or duplicate the pipeline. The missing parts are a few hundred lines of scheduling and a "My work" model.
Estimated effort: 3–5 weeks for stages, SLAs, timers, escalations and task unification, plus 1–2 weeks for BPMN export.

**Plan B (trigger to revisit):** if two or more pilot customers require executable BPMN (their own BPMN models
running inside our product), embed SpiffWorkflow behind a port, with its serialised state in our Postgres, every
service task calling `invoke()` on the pipeline, script tasks disabled, and Legal sign-off on LGPL-3.0. If a customer
mandates their own BPM suite, deliver our BPMN/DMN export plus an MCP/REST "decide this case" endpoint they call from
a business rule task (Operaton, Flowable, Camunda).

### 8.3 Trade-offs we accept

- We do not get "BPMN-certified" bragging rights; we answer with exports and a published subset.
- We maintain our own process layer; its scope must stay small (stages, SLAs, timers, escalations, tasks), not
  compensation, message correlation or multi-instance (if those are ever needed, that is the trigger for plan B).
- ZEN adds a native wheel and a second expression syntax beside our scope dims; we keep both small and convertible.

## 9. Adopt / learn from / avoid (ranked)

| Rank | Project | Verdict | Why | Licence flag |
|---|---|---|---|---|
| 1 | GoRules ZEN engine (Python) | **Adopt** | In-process decision tables and expressions behind a port; MIT; active (2.1.8, Nov 2026) | MIT |
| 2 | GoRules JDM editor | **Adopt** (table panel) | Ready decision-table UI in React; same JSON as the engine | MIT; check peer deps |
| 3 | MAPIE | **Adopt** | Calibrated intervals → "low confidence goes to a person" | BSD-3 |
| 4 | LightGBM (or XGBoost, pick one) | **Adopt** | Device price model behind `Predictor` | MIT / Apache-2.0 |
| 5 | DMN 1.x and BPMN 2.0 as **export** formats | **Adopt** | Interop and credibility without an engine | Standards (OMG) |
| 6 | bpmn-js / dmn-js | **Adopt, viewer only** | Show exports in standard notation | MIT + watermark clause |
| 7 | OpenFeature SDK | **Learn from / optional** | Standard flag API if we expose flow versions as flags | Apache-2.0 |
| 8 | Cedar (`cedarpy`) | **Learn from** (adopt later) | Model for a declarative, analysable access policy | Apache-2.0; wrapper "early stages", not AWS-supported |
| 9 | CEL (`cel-python`) | **Learn from / fallback** | Typed expression language if ZEN fails | Apache-2.0 |
| 10 | SpiffWorkflow | **Learn from / plan B** | Only in-process BPMN engine for Python | **LGPL-3.0** |
| 11 | Flowable (CMMN), Apache KIE (DMN/FEEL, TCK), Operaton | **Learn from / interop targets** | Case-management concepts, DMN conformance, export targets | Apache-2.0 (KIE incubating) |
| 12 | GrowthBook | **Learn from** | Experiment statistics for back-test and canary reports | MIT + enterprise dirs |
| 13 | sktime | **Learn from / adopt if needed** | Telemetry trend features for RUL | BSD-3 |
| 14 | MLflow | **Learn from** (file format only) | Registry concepts; server not shipped | Apache-2.0 |
| 15 | OPA / Rego | **Learn from** | Mature but a sidecar and a new language; maintainer concentration since Aug 2025 | Apache-2.0 |
| 16 | Casbin | **Avoid for now** | Duplicates `policy.py` without analysis | Apache-2.0 |
| 17 | OpenFGA | **Avoid for now** | Second store of access data; ReBAC not needed yet | Apache-2.0 |
| 18 | JsonLogic (Python ports) | **Avoid** | Stale upstream (2015), diverging forks | MIT (upstream) |
| 19 | `rule-engine` | **Avoid** (fine for scripts) | Single maintainer; ZEN/CEL cover it | BSD-3 |
| 20 | SpiffArena | **Avoid** as platform | Second API server, Celery, own auth | **LGPL-2.1/3 inconsistent** |
| 21 | pyDMNrules | **Avoid** in product | Excel input, GPL | **GPLv3** |
| 22 | durable_rules | **Avoid** | No release since June 2020 | MIT |
| 23 | Oso OSS library | **Avoid** | Deprecated Dec 2023 | Apache-2.0 |
| 24 | Unleash | **Avoid** | AGPLv3 from v8 (June 2026); second server | **AGPLv3** |
| 25 | Camunda 7 CE | **Avoid** | End of life Oct 2025, no security patches | Apache-2.0 |
| 26 | Camunda 8 Self-Managed | **Avoid** to embed or ship; interop only | Production needs a paid Enterprise licence (8.6+) | **Source-available (Camunda License v1) + proprietary** |

## 10. Target Tier 3a architecture

```
                     Business Studio (React)
   +-----------------------------------------------------------------------------+
   | Flow canvas (own)  | Table panel (JDM editor, MIT) | Process view (own canvas;|
   | rules, guardrails, |  decision tables, expressions |  "View as BPMN" with     |
   | locked stages      |  (no function nodes)          |  bpmn-js, watermark on)  |
   | Assistant: sentence -> flow JSON / table JSON (validated, never published)   |
   +-------------------------------------+---------------------------------------+
                                         | POST /api/actions/{id} (the one write path)
   +-------------------------------------v---------------------------------------+
   | Modeler services (pure)                                                      |
   |  flow.py  --compile.py-->  CompiledRule[]  --apply.py--> routes              |
   |    + table nodes --> DecisionTableEvaluator port --> ZEN adapter (zen-engine)|
   |    + guard.py (guardrails run last, owners only)                             |
   |    + validate.py (+ golden test cases, + "no function nodes")                |
   |    + simulate.py --> back-test replay (as-of), shadow report, canary buckets |
   |  Exporters: DMN 1.x XML, BPMN 2.0 XML, JDM;  Importer: DMN tables (subset)   |
   +-----------------------------+-----------------------------------------------+
                                 |
   +-----------------------------v----------------+   +---------------------------+
   | Case process layer (own, JSON, versioned)    |   | Valuers + Predictor port  |
   |  stages, SLAs, timers (jobs.run_after),      |   |  formulas | LightGBM      |
   |  escalations, human tasks = approvals,       |   |  + MAPIE intervals        |
   |  proposals, conflicts -> "My work"           |   |  -> confidence hold reason|
   +-----------------------------+----------------+   |  model_version registry   |
                                 |                    |  (fit/propose/promote)    |
   +-----------------------------v----------------+   +---------------------------+
   | Action pipeline (12 steps), policy.py         |
   | (tenant, permission, limits, delegations),    |
   | FORBIDDEN_ACTIONS, journal, Postgres queue    |
   +----------------------------------------------+
   Postgres only. No JVM, no second state store, no second API server.
   Interop out: BPMN/DMN files for Operaton, Flowable, KIE or Camunda; MCP/REST "decide case" for their rule tasks.
```

Order of work (suggested; each step independently useful):

1. Golden test cases per flow + shadow report (days).
2. `table` node with the evaluator port and ZEN adapter; tool-fleet contract-terms table (2–3 weeks).
3. MAPIE intervals on the device valuer; "low confidence" hold reason and its threshold as a template setting
   (2 weeks, after a first price model exists).
4. Back-test replay with as-of import and an uplift report (2–4 weeks; the sales motion).
5. DMN and BPMN exporters, DMN table import, bpmn-js viewer (2–3 weeks).
6. Case process layer: stages, SLAs, timers, escalations, "My work" tasks (3–5 weeks).
7. Canary status and champion/challenger models (2 weeks).
8. Later, on demand: Cedar behind the policy port; SpiffWorkflow (plan B).

Estimates are rough single-engineer figures, not commitments.

## Unconfirmed

- Camunda 8: the secondary store options in the current version and the release in which AI agent tasks / ad-hoc
  sub-processes shipped (release notes not read). Non-production licence terms (linked legal pages not read).
- CIB seven licence (vendor page only, licence file not read).
- Flowable 8.0.0 year (GitHub shows "27 Feb" without year) and whether its UI apps are open source in v8.
- SpiffArena v5.1.0 year (GitHub shows "12 Nov" without year); the repo's licence is inconsistent (LICENSE file
  LGPL-2.1, README LGPL-3.0).
- Apache KIE graduation status (no graduation announcement found; still "incubating" on 10.2.0).
- ZEN: whether function nodes still use QuickJS in 2.x; how the Python wheel treats decimal precision; mapping of ZEN
  table behaviour to DMN hit policies beyond FIRST and COLLECT; browser evaluation path of the JDM editor's simulator;
  JDM editor peer dependencies and latest release.
- Licences and dates of `common-expression-language`, `cel-expr-python`, `python-jsonlogic`, `maykin-json-logic-py`,
  `panzi-json-logic`; Darts version and date; SHAP version; LightGBM licence from metadata (project licence is MIT by
  repository, PyPI metadata fields are empty).
- `cedarpy` licence in PyPI metadata (null); Apache-2.0 is from the GitHub repo.
- Which DMN minor version (1.3/1.4/1.5) each interop target imports.
- The effort estimates in sections 3.1, 8.2 and 10 are judgement, not measured.
- `rule-engine` 5.2.1 shows an upload time of 24 Nov 2026 00:30 UTC (today); taken from PyPI JSON as read.

## Sources (read 24 Nov 2026 unless stated)

Repo (commit `0c71585`, 24 Nov 2026):
- `backend/di/services/modeler/flow.py`, `compile.py`, `apply.py`, `scope.py`, `guard.py`, `validate.py`,
  `simulate.py`, `parse.py`, `suggest.py`, `templates.py`, `valuers/device.py`, `valuers/tool_fleet.py`
- `backend/di/services/actions/modeler.py`, `backend/di/models/modeler.py`, `backend/di/repositories/live_rules.py`
- `backend/di/services/engine/predictor.py`, `calibration.py`; `backend/di/services/actions/models.py`
- `backend/di/core/policy.py`, `backend/di/core/jobs.py`, `backend/di/workflow/waits.py`
- `docs/agents/research/2026-11-platform/00-brief.md`; `docs/agents/research/2026-11-agent-foundation.md` (referenced
  by the brief, not re-read)

BPMN/DMN:
- Camunda licences (docs v8.10): https://docs.camunda.io/docs/reference/licenses/
- Camunda blog, licensing update for 8 Self-Managed (Apr 2024): https://camunda.com/blog/2024/04/licensing-update-camunda-8-self-managed/
- Camunda blog, licensing what you need to know (Oct 2024): https://camunda.com/blog/2024/10/camunda-licensing-what-you-need-to-know/
- Camunda 7 CE end of life (forum announcement): https://forum.camunda.io/t/important-update-camunda-7-community-edition-end-of-life-announced/50921
- Camunda 7 Enterprise EoL extension (Feb 2025, updated Jul 2025): https://camunda.com/blog/2025/02/camunda-7-enterprise-end-of-life-extension/
- Operaton site: https://operaton.org/ ; releases (v2.2.2, 20 Nov 2026): https://github.com/operaton/operaton/releases
- CIB seven: https://cibseven.org/en
- Flowable engine repo and releases (8.0.0, 27 Feb): https://github.com/flowable/flowable-engine , https://github.com/flowable/flowable-engine/releases
- Apache KIE history and 10.2.0 (Apr 2026): https://kie.apache.org/about/history , https://kie.apache.org/blog/kie_10_2_0_release ; Drools repo: https://github.com/apache/incubator-kie-drools
- SpiffWorkflow on PyPI (3.2.0, 10 Aug 2026): https://pypi.org/project/SpiffWorkflow/
- SpiffArena repo, licence and releases (v5.1.0, 12 Nov): https://github.com/sartography/spiff-arena , https://raw.githubusercontent.com/sartography/spiff-arena/main/LICENSE , https://github.com/sartography/spiff-arena/releases
- bpmn-js licence: https://github.com/bpmn-io/bpmn-js/blob/develop/LICENSE ; dmn-js licence: https://github.com/bpmn-io/dmn-js/blob/develop/LICENSE

Decision engines:
- ZEN engine repo: https://github.com/gorules/zen ; PyPI `zen-engine` (2.1.8, 20 Nov 2026): https://pypi.org/project/zen-engine/
- JDM editor: https://github.com/gorules/jdm-editor
- `cel-python` (0.5.0, 31 Jan 2026): https://pypi.org/project/cel-python/ ; `common-expression-language`: https://pypi.org/project/common-expression-language/ ; `cel-expr-python`: https://pypi.org/project/cel-expr-python
- `json-logic` (0.6.3, 4 Dec 2015): https://pypi.org/pypi/json-logic/json ; forks: https://pypi.org/project/maykin-json-logic-py/ , https://pypi.org/project/python-jsonlogic , https://github.com/pjchungmd/panzi-json-logic
- `rule-engine` (5.2.1): https://pypi.org/pypi/rule-engine/json
- `durable_rules` (2.0.28, 7 Jun 2020): https://pypi.org/pypi/durable_rules/json
- `pyDMNrules` (1.4.5, 22 Aug 2026): https://pypi.org/pypi/pyDMNrules/json

Policy:
- OPA releases (v1.22.4, 12 Nov 2026): https://github.com/open-policy-agent/opa/releases
- OPA blog, note to the community (20 Aug 2025): https://openpolicyagent.org/blog/note-from-teemu-tim-and-torin-to-the-open-policy-agent-community-2dbbfe494371
- Review of OPA maintainers after the move (17 Jul 2026, secondary): https://www.youngju.dev/blog/2026-07-17-opa-post-styra-apple-acquihire-reality.en
- cedar-py repo: https://github.com/k9securityio/cedar-py ; PyPI `cedarpy` (4.12.2, 14 Oct 2026): https://pypi.org/project/cedarpy/
- OpenFGA releases (v1.23.0, 20 Nov 2026): https://github.com/openfga/openfga/releases ; CNCF incubation (11 Nov 2025): https://www.cncf.io/blog/2025/11/11/openfga-becomes-a-cncf-incubating-project/
- PyCasbin (2.8.0, 2 Feb 2026): https://pypi.org/pypi/pycasbin/json
- Oso library deprecation notice (18 Dec 2023): https://github.com/osohq/oso

Rollout and experiments:
- OpenFeature Python SDK (0.10.0, 1 Jun 2026): https://pypi.org/project/openfeature-sdk/
- Unleash licence: https://github.com/Unleash/unleash/blob/main/LICENSE ; blog "moving to AGPLv3" (2 Jun 2026): https://www.getunleash.io/blog/unleash-moving-to-agplv3
- GrowthBook licence: https://github.com/growthbook/growthbook/blob/main/LICENSE

ML:
- MAPIE (1.6.0, 19 Oct 2026): https://pypi.org/pypi/mapie/json
- LightGBM (4.7.0, 18 Jul 2026): https://pypi.org/project/lightgbm/
- XGBoost (3.4.1, 15 Aug 2026): https://pypi.org/project/xgboost/
- sktime (1.3.0, 8 Nov 2026): https://pypi.org/project/sktime/
- MLflow (3.18.0, 3 Nov 2026): https://pypi.org/project/mlflow/
- Darts: https://pypi.org/project/darts/ (page did not load; details unconfirmed)

## Legal note

All licence statements in this report (Camunda License v1 and the Enterprise requirement, LGPL for SpiffWorkflow and
SpiffArena, GPLv3 for pyDMNrules, AGPLv3 for Unleash, the bpmn.io watermark clause, the GrowthBook enterprise
directories, and every permissive licence listed) are findings from public pages read on 24 Nov 2026. They must be
reviewed by Kinective's Legal team before anyone relies on them, and in particular before any of these components is
included in the customer trial package or another redistributed artefact.
