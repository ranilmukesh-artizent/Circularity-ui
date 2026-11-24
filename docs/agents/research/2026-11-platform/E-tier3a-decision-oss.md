# E. Tier 3a: open-source decision, process and policy engines for Business Studio (24 Nov 2026)

Part E of the platform research (brief: [00-brief.md](00-brief.md)). Question: which open-source BPMN/DMN engines,
decision engines, policy engines, rollout tools and ML libraries should Business Studio (the Modeler) adopt, learn
from or avoid, and should it switch its model format to BPMN/DMN.

> **Legal review.** Every licence finding below comes from public licence files, package metadata and vendor posts read
> on 24 Nov 2026. It is not legal advice. It needs review by Kinective's Legal team before anyone relies on it,
> in particular for anything we would redistribute in the customer trial package.

## What changed in this revision and why (revision 2, 24 Nov 2026)

The target is now the team's Recover prototype ([01-recover-segments.md](01-recover-segments.md), "01"). Its flow
authoring, guardrails, customer layer, per-market rules, model catalogue and staged publish (01 §2–§4) need answers
that revision 1 did not give. New material is in **§11**. **01 is used for its concept only** (capabilities, data, rules, agents): its screens, menus, panels and step tabs are not UI requirements, and this report describes capabilities, not layout.

| Change | What | Why |
|---|---|---|
| **Added** §11.1 | The customer layer as layered configuration: base pack + customer overlay of typed operations + a 3-way rebase on pack updates; tighten-only locked guardrails; diversions; blocked compliance skips; JSON patch/merge/diff libraries with licences | 01 §2 "Customer layer" and every pack's blocked diversion (01 §4–§9) |
| **Added** §11.2 | Per-market decision tables (labour rates, credit rules, cover terms) on GoRules ZEN: fit confirmed, with the split between rate cards (data) and rules (tables) | 01 §4.2 |
| **Added** §11.3 | The model catalogue: remaining-life survival model, demand forecaster, resale price GBM, refurbishment cost, condition classifier fallback, with licences and dependency weight | 01 §3 "Model catalogue" |
| **Added** §11.4 | The disposition optimiser: what `plan_queue` does today, whether a solver is needed, solver options with licences and wheel sizes | 01 §3 agent 6 "plans the whole queue" |
| **Added** §11.5 | Model registry fields (quality, drift, last trained, cadence) and drift-detection OSS with licences | 01 §3 "quality, drift, last-trained date and retraining cadence" |
| **Added** §11.6 | Design note: publishing to a share of volume in one region (canary) vs shadow, and the replay report | 01 §2 |
| **Updated** Summary items 8–12, §5.1 canary row, §6 (pointer to §11.3), §9 ranks 13 and 27–43, §10 order of work, unconfirmed, sources, legal note | Follow the additions | — |
| **Updated** sktime: from "adopt if needed" to "learn from" | **statsforecast** (Apache-2.0) is the forecasting choice: lighter, and it has the intermittent-demand models the paths need | §11.3 |
| **Updated** the location of the queue planner | It is `plan_queue` in `services/modeler/valuers/tool_fleet.py` (not in `services/engine/`); the engine has a separate pool optimiser `services/engine/pool.py` | Code read in this revision |
| **Deleted** | Nothing | The new target adds needs; it does not contradict revision 1 |

**Decisions:** README decision **D2 is kept** (own flow graph, ZEN for tables, no BPMN engine, LightGBM + MAPIE, our
own model registry, authorization in `policy.py`). This revision **adds** to D2 (proposed): customer overlays of typed
operations with a 3-way rebase (own code, jsonpatch and deepdiff as helpers); lifelines for survival; statsforecast
for forecasting; SciPy's `milp` (HiGHS) behind a `QueuePlanner` port, with `plan_queue` kept as the parity default;
our own drift metrics (no drift library); canary by region and share of volume after shadow. The README is not edited
here.

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
8. **Customer layer (§11.1)**: the effective flow = base pack version + the customer's overlay, an ordered list of
   *typed* operations keyed by stable ids (tighten a guardrail, add an approver, add a diversion, add a rule, set a
   parameter). A pack update replays the overlay on the new base (a 3-way rebase); conflicts go to a person; the
   stricter value always wins for locked compliance guardrails; a diversion that skips a compliance guardrail fails
   validation. Own code; `jsonpatch` (BSD-3-Clause) and `deepdiff` (MIT) only as helpers.
9. **Per-market rules (§11.2)**: ZEN fits credit rules and cover terms; labour rates and price lists are dated
   *rate cards* (pack data) that tables read, not rules.
10. **Models (§11.3)**: lifelines (MIT) for remaining life, **not scikit-survival (GPL-3.0-or-later, confirmed)**;
    statsforecast (Apache-2.0) for demand; LightGBM + MAPIE for price, refurbishment cost and the condition fallback;
    the service-desk estimate is a "similar past repairs" lookup, not a model.
11. **Queue plan (§11.4)**: no solver is needed for the pilot or for parity; `plan_queue` is a regret heuristic that the
    golden files pin. Add SciPy's `milp` (BSD-3-Clause, HiGHS inside, arrives with the ML stack) behind a port for
    larger queues and to report the gap to optimal. OR-Tools (Apache-2.0, ~30 MB wheel) only if scheduling over time
    slots is needed. Avoid PuLP's CBC extra (EPL-2.0, large).
12. **Drift and rollout (§11.5, §11.6)**: own drift metrics in Postgres (PSI, interval coverage, error on closed
    outcomes). Avoid alibi-detect (**BSL 1.1**); Evidently is Apache-2.0 but heavy. Canary = one region at a share of
    volume, decided by a stable hash, after a replay and optionally a shadow period; widening needs a person.

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
| **Canary by bucket** | Publish to a share of cases before all | New status `canary` with a percentage; bucket by a stable hash of case id (or by org unit); the decision records which flow version decided it. Revision 2: Recover scopes it as one region at a share of volume (§11.6) | Medium |
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
prediction interval, and confidence as a hold reason. Revision 2: the full Recover model catalogue (survival,
forecasting, cost, condition fallback, queue optimiser) and the registry fields are in §11.3–§11.5.

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
| 13 | sktime | **Learn from** (updated in revision 2; was "adopt if needed") | Broad toolbox, 36.5 MB wheel; statsforecast covers our forecasting (§11.3) | BSD-3 |
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
| 27 | Customer overlay of typed operations + 3-way rebase (§11.1) | **Build (ours)** | Tighten-only and blocked-skip rules are domain checks no merge library knows | — |
| 28 | `jsonpatch` (+ `jsonpointer`) | **Adopt** as a helper | RFC 6902 patches for the audit view of an overlay | BSD-3-Clause |
| 29 | `deepdiff` | **Adopt** as a helper | Readable diffs for reviewing a pack update and approving an overlay | MIT |
| 30 | `json-merge-patch`, `jsonmerge`, `dictdiffer` | **Learn from** / not needed | RFC 7386 cannot address list items; `jsonmerge` last released Jul 2023 | BSD / MIT |
| 31 | lifelines | **Adopt** (worker, training) | Weibull AFT and Cox models for remaining life, explainable | MIT |
| 32 | scikit-survival | **Avoid** in anything shipped | Copyleft | **GPL-3.0-or-later** |
| 33 | statsforecast | **Adopt** (worker, training) | Intermittent-demand models (Croston family, TSB, ADIDA) and AutoETS | Apache-2.0 |
| 34 | Darts, Prophet | **Avoid** | Heavy (Darts: shap, pyod; Prophet: CmdStan binaries); wrong shape for intermittent demand | Apache-2.0 / MIT |
| 35 | SciPy `milp` (HiGHS) and `linear_sum_assignment` | **Adopt** behind `QueuePlanner` | Arrives with the ML stack; exact queue plans for larger queues and the "gap to optimal" report | BSD-3-Clause (HiGHS MIT) |
| 36 | highspy | **Optional** | Direct HiGHS API if incremental solves are needed | MIT |
| 37 | OR-Tools | **Only if** time-slot scheduling is needed | CP-SAT is strong, but ~30 MB wheel and a protobuf pin | Apache-2.0 |
| 38 | PuLP with CBC, Python-MIP, Timefold (Python) | **Avoid** | CBC is EPL-2.0 and ~200 MB; Timefold Python runs a JVM through JPype and is a beta | EPL-2.0 / Apache-2.0 |
| 39 | Own drift metrics (PSI, KS, interval coverage, error on closed outcomes) | **Build (ours)** | Small, in Postgres, readable through the model actions | — |
| 40 | alibi-detect | **Avoid** | Licence | **BSL 1.1** |
| 41 | Evidently | **Learn from** / dev tool | Apache-2.0, but heavy (Litestar, uvicorn, Plotly, NLTK, statsmodels) and a telemetry dependency (UI only, opt-out) | Apache-2.0 |
| 42 | NannyML, frouros | **Avoid** | Stale (Jul 2025, Oct 2024) with pins that clash with our stack (`lightgbm<4.6`, `numpy<2.2`) | Apache-2.0 / BSD-3 |
| 43 | river | **Optional** | Streaming drift detectors (ADWIN, Page-Hinkley) if we need online alarms | BSD-3-Clause |

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

Added in revision 2 (Recover):

9. Customer layer: overlay operations, validator (tighten-only, blocked skips), rebase report (3–4 weeks; §11.1).
10. Rate cards and per-market ZEN tables for the service desk (credit rules, cover terms) (1.5 weeks after step 2;
    §11.2).
11. Model registry fields and drift metrics (1.5 weeks; §11.5).
12. Models: refurbishment-cost lookup and quantile model, condition fallback, remaining-life model, demand forecaster
    (1–2 weeks each, after the pilots supply data; §11.3).
13. `QueuePlanner` port: `plan_queue` as the default, `milp` adapter, gap-to-optimal in the back-test report (1.5 weeks;
    §11.4).
14. Canary by region and share of volume, with the replay report before publish (extends step 7; §11.6).

Estimates are rough single-engineer figures, not commitments.

## 11. Recover additions (added in revision 2)

### 11.1 The customer layer: base pack + customer overlay + rebase

**What 01 §2 requires.** A customer may tighten a guardrail or give it an extra approver. Compliance guardrails locked
by the pack cannot be weakened, suspended or removed. Diversions add a step or a shortcut at a stage for a condition;
a diversion that skips a compliance guardrail is blocked (each pack has one example, such as "quote under $50: skip
the blacklist check"). Pack updates never overwrite the customer's changes.

**Model: three layers, folded at publish time.**

| Layer | Owner | Holds | Changes through |
|---|---|---|---|
| L0 platform | Us (code) | Invariants: forbidden list, guardrails run after rules, one write path | Releases |
| L1 pack base | Us (pack author) | Pack version (for example tool fleet v3.2): stages, routes, guardrails with `type` (Compliance, Data quality, Threshold, Approval) and `locked`, default rules, parameters, stage agents | Pack releases |
| L2 customer overlay | The customer (per tenant or org unit) | An **ordered list of typed operations**, each keyed by stable ids, each recording the base value it saw | Flow authoring, maker-checker |

Effective flow = `apply(L2, L1)`, compiled as today (`compile.py`), so `apply.py`, guardrails, simulation and shadow are
unchanged. A market layer (DE, FR …) between L1 and L2 can come later with the same mechanics.

**Why typed operations, not a JSON patch, as the overlay.** RFC 7386 merge patch cannot address an item in a list and
uses `null` to delete; RFC 6902 JSON Patch addresses list items by index, which breaks when the next pack version
inserts a guardrail. Neither knows that "threshold 600 → 500" is a tightening and "600 → 800" a weakening. So the
overlay is a closed set of operations our validator understands:

| Operation | Allowed on | Check |
|---|---|---|
| `guardrail.tighten {id, field, value, seen}` | Any guardrail | The new value is stricter, using the field's direction from the pack (`stricter: lower` for "repair over $600 → fleet manager", `higher` for "never below 60 % of the forecast price") |
| `guardrail.addApprover {id, role}` | Any guardrail | Adds only |
| `guardrail.add {type, stage, condition, owner}` | — | A new, customer-owned guardrail ("write-off under 24 months → service operations") |
| `guardrail.relax / suspend / remove {id}` | Customer-owned guardrails only | Refused on any pack guardrail marked `locked` |
| `diversion.add {stage, condition, kind: step \| shortcut, target}` | Any stage | **Blocked** if, for items matching the condition, any Compliance guardrail of a skipped stage would no longer be evaluated |
| `rule.add / update / remove` | Customer-owned business rules | As today (`validate.py`, guardrails last) |
| `param.set {path, value}` | Declared parameters | Range from the pack (confidence threshold 65–85 %, ageing days 7/10/14/21, repair slots) |
| `stageAgent.set {stage, autonomy, limits}` | Any stage (the flow's agent mapping) | Within the role ceiling (F §8b) |

The blocked-skip check is a graph check, not a text match: compile the effective flow, and for each diversion walk the
stages its items would pass; if a Compliance guardrail sits on a stage they no longer pass, refuse with "skips
compliance guardrail *safety recall check*". The same validator runs on overlays drafted by the configuration agent
(F §8c).

**Pack update = a 3-way rebase** (base old, base new, overlay), like a git rebase or Helm 3's three-way merge
(learned from, not used):

1. Replay each operation in order on the new base, finding its target by id.
2. Target gone (removed or renamed in the pack) → conflict for a person.
3. `seen` equals the new base's value → apply unchanged.
4. A tighten on a guardrail the pack also changed → keep the **stricter** of the two; if the pack is now stricter,
   drop the operation with a note. No person needed: the direction is known.
5. Any other field the pack changed → conflict: keep mine, take the pack's, or edit.
6. Re-validate every diversion against the new base: a diversion that now skips a *new* compliance guardrail is
   disabled and flagged (fail safe).
7. Output a rebase report: the diff of the effective flow before and after (deepdiff), the conflicts, and a replay
   (§11.6) of the new effective flow; then maker-checker publish as for any flow version.

So "pack updates never overwrite customer changes" holds by construction: the overlay is stored apart and every
collision is either resolved by a known rule (stricter wins) or shown to a person.

**Libraries (PyPI, 24 Nov 2026).** None does the domain part; two help with display and audit:

| Library | Licence | Latest | Use |
|---|---|---|---|
| `jsonpatch` (+ `jsonpointer` 3.12) | BSD-3-Clause | 1.48, 19 Nov 2026 | Render an overlay as an RFC 6902 patch (paths by id after turning lists into maps) for audit and export |
| `deepdiff` | MIT | 9.2.1, 18 Nov 2026 | Human-readable diffs (reviewing a pack update, approving an overlay); `Delta` objects for tests |
| `json-merge-patch` | BSD (PyPI field) | 0.3.0, 25 Mar 2025 | Not needed (RFC 7386 limits above) |
| `jsonmerge` | MIT | 1.9.2, 19 Jul 2023 | Learn from its per-key merge strategies in a schema; stale |
| `dictdiffer` | MIT | 0.10.0, 16 Jul 2026 | Not needed beside deepdiff |
| Kustomize overlays, Helm 3 three-way merge | Apache-2.0 (Go tools) | — | Learn from; not embedded (general knowledge, **not re-read**) |

Effort: 3–4 weeks (operation set, validator incl. the graph check, fold into compile, rebase and report, actions).

### 11.2 Per-market decision tables: GoRules ZEN fit confirmed

01 §4.2 (service desk): labour rates per market (for example €42/h DE, €46/h FR), price lists and credit rules per
market, cover terms ("swap allowed for cordless tools"), the rule "upgrade only when the tool is past 50 % of its life
or the cover rules allow it", credits above $300 need sales approval, markets DE, UK, US, AU with FR in pilot.

ZEN (MIT, `zen-engine` 2.1.8, 20 Nov 2026, still the latest on PyPI) fits the *rules* part. Split it this way:

| Item | Where it lives | Why |
|---|---|---|
| Labour rates, price lists, logistics rates | **Rate cards**: pack data, versioned, dated (`market, kind, valid_from, valid_to, currency, values`), maker-checker | They are numbers that change monthly, not rules; replay must read the card valid at the decision date (§5.1 as-of). ZEN has no effective dating |
| Cover terms ("swap allowed for cordless tools") | ZEN decision table: inputs `market, family, cover_type, age_months`; outputs `swap_allowed, reason`; first hit | A classic table a business user edits |
| Credit rules per market | ZEN table: outputs `credit_pct, credit_cap` | Same |
| "Upgrade only past 50 % of life or when cover allows" | ZEN expression or a business rule in the flow | Uses the remaining-life fact (§11.3) |
| "Credits above $300 need sales approval" | A **guardrail** of type Approval, not a table row | Guardrails cannot be weakened by a table or by an overlay (§11.1) |
| FR "in pilot" | The table's market scope + canary (§11.6) | Rollout, not logic |

Money stays in our code (Decimal), multiplied by the rate card; ZEN returns booleans, percentages and classes, which
sidesteps the open question on the wheel's decimal precision (§3.1, still **unconfirmed**). "Test this decision" (the
credit lever with take-up from the last 24 months) is a what-if over the table plus a take-up curve fitted on past
offers (logistic regression, scikit-learn), never a publish.

### 11.3 The model catalogue (01 §3)

Rule from 01: every model shows quality, drift, last-trained date and retraining cadence; thresholds and factor tables
change only with a person's approval. The brief's rule still holds: **read** grade and remaining life from the repair
centre and PLM when they exist; models are fallbacks, labelled as estimates.

| Model (01 §3) | Recommended method | Library | Licence | Latest (PyPI, read 24 Nov 2026) | Weight and notes |
|---|---|---|---|---|---|
| Remaining-life estimator (per tool and per part) | Weibull accelerated failure time per family, covariates hours × load, repair resets; censored data (tools still running) handled properly; output median remaining life and P(survives the next term) | **lifelines** | MIT | 0.30.3, 5 Mar 2026 | Pure Python; needs autograd, formulaic, matplotlib, `pandas<3` (watch the pin). The Weibull parameters and covariate effects are readable on the card |
| (alternative) | Same, gradient-boosted | scikit-survival | **GPL-3.0-or-later** (PyPI licence expression; confirmed) | 0.28.0, 5 Jul 2026 | **Avoid in anything shipped**; copyleft in a redistributed image |
| (alternative) | `survival:aft` objective | XGBoost | Apache-2.0 | 3.4.1, 15 Aug 2026 | The Linux wheel is ~58 MB and depends on `nvidia-nccl-cu13`; another reason to stay on LightGBM |
| Demand forecaster (per path) | Forecast only the *unnamed* part: named demand (renewals 60–90 days ahead, open orders, pool requests, bids) is read, not forecast. Intermittent counts → Croston SBA / TSB / ADIDA; smooth series → AutoETS | **statsforecast** | Apache-2.0 | 2.1.1, 16 Jul 2026 | Brings statsmodels, fugue, coreforecast, `pandas<3`; weight of fugue's tree **unconfirmed** |
| (alternatives) | — | sktime (BSD-3, 1.3.0, 36.5 MB wheel); Darts (Apache-2.0, 0.48.1, 16 Oct 2026; shap, pyod, matplotlib, holidays); Prophet (MIT, 1.5.0, 5 Oct 2026; cmdstanpy + CmdStan in an ~12 MB wheel) | — | — | Learn from / avoid: heavier, and Prophet suits smooth seasonal series, not sparse return-path demand |
| Resale price estimator | LightGBM quantile (P10/P50/P90) per channel + MAPIE intervals (unchanged, §6.1) | LightGBM, MAPIE | MIT, BSD-3-Clause | 4.7.0 (18 Jul 2026), 1.6.0 (19 Oct 2026) | Already chosen (D2) |
| Refurbishment cost estimator | Two tiers. (a) **Similar past repairs** (01 §4.2: same family, age band and fault, last 3 years): empirical median and P10–P90 from SQL; ≥ 50 matches → priced without a technician. (b) Fewer matches → LightGBM quantile on hours and parts + MAPIE; a technician checks. Predict **hours and parts**, then multiply by the market's rate card, so a rate change needs no retraining | Postgres; LightGBM, MAPIE | — | — | Accuracy shown on held-out repairs (01 §4.2) |
| Condition estimate (fallback) | LightGBM multiclass on telematics, age, repair history and return reason; calibrated probabilities; MAPIE conformal **prediction sets**: a set of more than one grade = low confidence → wait for the workbench or ask a person. Never overrides a real grade; when the grade arrives the case is re-evaluated and the hit is logged | LightGBM, MAPIE, scikit-learn (BSD-3, 1.9.1) | — | — | Always labelled "estimate" |
| Disposition optimiser | §11.4 | SciPy | BSD-3-Clause | 1.18.1, 21 Aug 2026 | Arrives with scikit-learn, LightGBM and MAPIE (none of numpy, scipy or scikit-learn is in `requirements.lock` today) |

Packaging: today's backend image has no numeric stack. Put the training libraries (lifelines, statsforecast) in the
**worker** image's dependency group only, and keep inference light (LightGBM boosters, Weibull parameters and
forecasts stored as numbers). The trial package gains image weight, not a container.

### 11.4 The disposition optimiser: is a solver needed?

**What exists.** `plan_queue` / `_plan_queue` in `backend/di/services/modeler/valuers/tool_fleet.py` (a port of the
prototype, "planQueue") plans every open return of the queue:

- one return per named order (lease renewal, sales order, project: `POOLK`), refurbishment within the repair centre's
  free slots (`BASEP["slots"] = 8` minus refurbishments in progress);
- a **regret heuristic**, up to 40 rounds: each return is decided with its blocked set; an order claimed by two or
  more returns goes to the one that would lose most without it; if refurbishments exceed the slots, the ones with the
  highest regret keep them; then freed slots and unused orders are handed back to whoever gains most (up to 6 rounds);
- two baselines: each return decided alone (orders promised twice) and first come, first served (oldest first); the
  plan reports its gain over FCFS and the contested orders; results are memoised per (parameters, rules, queue).

`backend/di/services/engine/pool.py` (the demo's `solvePool`) is a separate allocator: greedy vs an **exact
enumeration** of every split, fine because "pools are small", exponential otherwise.

**Answer: not for the pilot or parity; yes as an option behind a port.** The golden files pin the heuristic's
outcomes and texts (`fixtures/golden/po/equip_decisions.json` includes "No repair center slot in the next two weeks:
the queue plan gives the slots to refurbishments that add more"), so replacing it would break parity (golden rule 1).
But the heuristic has no optimality guarantee, and Recover adds constraints it was not built for: several depots each
with capacity, labour hours per market, lot caps (device pack), budgets, and replays of thousands of items. Plan:

1. A `QueuePlanner` port with two adapters: `regret` (today's code, the default for the tool-fleet pack and the demo)
   and `milp`. A pack setting chooses.
2. The MILP: for each open case *c* and each option *k* (a path and, where relevant, a named destination) a binary
   `x[c,k]` with value `v[c,k]` from the valuer (net of cost, logistics and time held); each case takes exactly one
   option; each named order at most once; refurbishments per depot ≤ its slots; later, lot caps and budgets as more
   linear rows. Maximise total value. A few hundred cases × ~10 options is small for HiGHS (no benchmark run:
   **unconfirmed**).
3. Explanations stay per case: "regret" = the value lost if this case had to take its second option, obtained by
   re-solving with that option forced (cheap at this size), and the uplift against the standard route as today.
4. Back-test reports both: the heuristic's plan and the optimal one, and the gap, the same way `pool.py` shows greedy
   vs optimal. If the gap is material on real queues, switch the pack's default.
5. "Learns from every closed outcome" is about the **inputs** (prices, costs, pass rates, remaining life from §11.3),
   not the solver.

**Solver options (PyPI, read 24 Nov 2026):**

| Option | Licence | Latest | Linux wheel | Notes | Verdict |
|---|---|---|---|---|---|
| **SciPy** `optimize.milp` (HiGHS inside) and `linear_sum_assignment` | BSD-3-Clause (HiGHS is MIT) | 1.18.1, 21 Aug 2026 | ~35 MB, but it arrives anyway with scikit-learn, LightGBM and MAPIE | `linear_sum_assignment` handles the pure one-to-one case (slots can be modelled as extra columns) but no further side constraints; `milp` handles all of the above, with a time limit | **Adopt** |
| highspy | MIT | 1.16.0, 11 Nov 2026 | ~3 MB | Direct HiGHS API: incremental models, warm starts | Optional |
| OR-Tools (CP-SAT, MIP, routing) | Apache-2.0 | 9.15.6755, 14 Jan 2026 | ~30 MB | Pins `protobuf>=6.33.1,<6.34` and needs absl-py; best for scheduling over time slots (technician calendars) | Only if scheduling is needed |
| PuLP | MIT (modelling layer) | 4.3.1, 19 Nov 2026 | <1 MB | Solvers through extras; the `cbc` extra installs `cbcbox` (EPL-2.0, ~200 MB) | Avoid (EPL and size; a modelling layer we don't need) |
| Python-MIP | EPL-2.0 | 2.0.2, 9 Nov 2026 | ~10 MB + cbcbox | Copyleft (weak) | Avoid |
| Pyomo, CVXPY | BSD-3 / Apache-2.0 | 6.11.0 / 1.9.3 | 16.5 MB / 4.5 MB + solvers | General modelling frameworks | Not needed |
| Timefold Solver (Python) | Apache-2.0 | 1.24.0b0, 8 Jul 2025 | ~22 MB, runs a JVM through JPype | Beta, JVM | Avoid |

### 11.5 Model registry fields and drift

Keep our registry (`model.fit/propose/promote`, maker-checker; `model.propose/promote` are forbidden to agents). Add
these fields so every model carries what 01 asks for:

| Field | Content |
|---|---|
| Identity | `model_id`, `version`, `kind` (classifier, survival, time series, GBM, regression, optimiser), `target`, `pack`, scope (markets, classes) |
| Training | data window, row count, feature list with a schema hash, code version, trained by (job), **last trained** |
| **Quality** | metric and value on a held-out window (MAE/MAPE for prices and costs, concordance index and calibration for survival, MASE for forecasts, accuracy and set size for the classifier), the baseline it beats (formula or previous champion), interval coverage target vs observed |
| **Drift** | per top feature: population stability index (PSI) and a KS test against training; prediction drift; error drift on closed outcomes; coverage drift; a status `ok`, `watch`, `alert` with the rule that set it |
| **Cadence** | retraining schedule (weekly, monthly) or trigger (drift alert, N new closed outcomes), next due |
| State | candidate, challenger, champion, retired; who proposed, who approved, when |
| Thresholds used | the confidence thresholds and factor tables that flows read from this model; changing one is a maker-checker change (01 §3) |

**Drift detection: compute it ourselves.** The metrics are a few dozen lines on SciPy (`stats.ks_2samp`) and SQL over
our prediction and outcome tables, run by a weekly worker job, stored in Postgres. The libraries checked:

| Library | Licence | Latest | Finding | Verdict |
|---|---|---|---|---|
| Evidently | **Apache-2.0** (repo LICENSE file read 24 Nov 2026; PyPI licence field agrees) | 0.7.23, 11 Sep 2026 | Not a licence problem. Heavy: Litestar, uvicorn, Plotly, NLTK, statsmodels, dynaconf; an `iterative-telemetry` dependency. Its docs say telemetry is collected only in the Monitoring UI, not when used as a library, with a `DO_NOT_TRACK` opt-out (one page names `EVIDENTLY_DISABLE_TELEMETRY` instead) | **Learn from** / a dev tool for our data scientists; not in the image |
| alibi-detect | **Business Source License 1.1** (PyPI licence field; classifier "Other/Proprietary") | 0.13.0, 11 Dec 2025 | Source-available; changed from Apache-2.0 on 22 Jan 2024 (Seldon licensing FAQ); earlier releases stay Apache-2.0 | **Avoid** |
| NannyML | Apache-2.0 | 0.13.1, 12 Jul 2025 | Pins `lightgbm<4.6` (we choose 4.7.0), pulls FLAML and gcsfs; no release for 16 months | Avoid |
| frouros | BSD-3-Clause | 0.9.0, 5 Oct 2024 | Pins `numpy<2.2`, `scipy<1.15`; stale | Avoid |
| river | BSD-3-Clause | 0.27.0, 13 Nov 2026 | Streaming detectors (ADWIN, Page-Hinkley); ~3 MB | Optional, for online alarms later |

### 11.6 Canary publish vs shadow (design note)

01 §2 (concept): a capability to publish a new version to **one region at a share of volume** (20 % in the
prototype), and a replay of past items compares the route
mix (actual against flow) and reports straight-through %, approvals and exceptions per day, and modelled value
uplift.

| | Replay (before publish) | Shadow | Canary |
|---|---|---|---|
| What runs | The new version over past items, as of each decision date | The new version beside the live one on live items; it never acts | The new version **decides** for a slice of live items |
| Risk | None | None | Real, bounded by the slice; guardrails and approvals unchanged |
| What it tells | Route mix vs actual, straight-through %, approvals and exceptions per day, modelled uplift | Flip rate and value delta on today's data (`shadow_decision` exists) | Real outcomes: override rate, exceptions, days to next use, realised value |
| Weakness | Counterfactual values are model estimates (§5.1) | No realised outcomes for the flipped items | Needs enough volume to tell a difference |

Recommended sequence: **replay (always) → shadow (optional, when the replay shows many flips) → canary → full**.

Canary mechanics:

- Assignment: `region == R and hash(case_id, flow_id, salt) mod 100 < p`. Stable and **sticky**: a case keeps the
  version that first decided it through approval, execution and close (the decision records `flow_version`). Raising
  `p` only adds cases.
- Control group: the rest of the same region in the same period, so canary and control share market and season; the
  report compares the two with a bootstrap band, as the back-test does, and states the sample size needed before a
  difference means anything.
- Stop rules, set at publish: if the canary's exception rate, override rate or guardrail holds exceed the control's by
  a set margin, the platform **pauses** the canary (new cases go back to the previous version) and tells the owner.
  Pausing moves towards the known-good version, so it may be automatic; **widening (raising `p`, adding regions,
  going full) is always a person's action** through maker-checker, and is forbidden to agents (`flow.publish` already
  is).
- Market pilots ("FR in pilot", 01 §4.2) use the same mechanism with the market as the region.

### 11.7 Unconfirmed in §11

- Whether `plan_queue`'s heuristic is optimal on the demo queue (no MILP comparison was run); HiGHS solve times at
  Recover's queue sizes (no benchmark).
- Evidently's exact telemetry variable (its docs disagree).
- statsforecast's full dependency weight (fugue's tree); lifelines' `pandas<3` pin against our future pandas.
- Kustomize and Helm three-way merge behaviour (general knowledge, not re-read).
- That the device pack's lot caps and budgets are linear (assumed for the MILP).

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
- Revision 2: see §11.7.

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
- Darts: https://pypi.org/project/darts/ (page did not load; details unconfirmed). Revision 2: PyPI JSON read; 0.48.1
  (16 Oct 2026), Apache-2.0.

Revision 2 (read 24 Nov 2026; PyPI JSON `https://pypi.org/pypi/<name>/json` for version, upload date, licence field,
dependencies and wheel size):
- Target: [01-recover-segments.md](01-recover-segments.md) §2, §3, §4.1, §4.2, §9
- Repo (read, not changed): `backend/di/services/modeler/valuers/tool_fleet.py` (`plan_queue`, `_plan_queue`, `BASEP`,
  `POOLK`), `backend/di/services/engine/pool.py`, `fixtures/golden/po/equip_decisions.json`,
  `backend/requirements.in`, `backend/requirements.lock`, `backend/Dockerfile`
- Customer layer: jsonpatch 1.48 (19 Nov 2026) and jsonpointer 3.12 (11 Nov 2026), BSD-3-Clause; deepdiff 9.2.1
  (18 Nov 2026), MIT; json-merge-patch 0.3.0 (25 Mar 2025), BSD; jsonmerge 1.9.2 (19 Jul 2023), MIT; dictdiffer
  0.10.0 (16 Jul 2026), MIT. Standards: RFC 6902 (JSON Patch), RFC 7386 (JSON Merge Patch), IETF (not re-read)
- Decision tables: zen-engine 2.1.8 (20 Nov 2026), still the latest: https://pypi.org/project/zen-engine/
- Survival: lifelines 0.30.3 (5 Mar 2026), MIT: https://pypi.org/project/lifelines/ ; scikit-survival 0.28.0
  (5 Jul 2026), licence expression GPL-3.0-or-later: https://pypi.org/project/scikit-survival/ ; XGBoost 3.4.1
  (15 Aug 2026), Apache-2.0, Linux wheel depends on `nvidia-nccl-cu13`: https://pypi.org/project/xgboost/
- Forecasting: statsforecast 2.1.1 (16 Jul 2026), Apache-2.0: https://pypi.org/project/statsforecast/ ; sktime 1.3.0
  (8 Nov 2026), BSD-3-Clause; darts 0.48.1 (16 Oct 2026), Apache-2.0; prophet 1.5.0 (5 Oct 2026), MIT
- Optimisation: SciPy 1.18.1 (21 Aug 2026), BSD: https://pypi.org/project/scipy/ ; highspy 1.16.0 (11 Nov 2026), MIT;
  ortools 9.15.6755 (14 Jan 2026), Apache-2.0; PuLP 4.3.1 (19 Nov 2026), MIT, `cbc` extra = cbcbox 2.937 (EPL-2.0);
  mip 2.0.2 (9 Nov 2026), EPL-2.0; Pyomo 6.11.0, BSD-3-Clause; CVXPY 1.9.3, Apache-2.0; timefold 1.24.0b0
  (8 Jul 2025), Apache-2.0, depends on JPype1
- ML: scikit-learn 1.9.1 (10 Sep 2026), BSD-3-Clause
- Drift: Evidently 0.7.23 (11 Sep 2026), Apache-2.0: https://pypi.org/project/evidently/ , LICENSE:
  https://raw.githubusercontent.com/evidentlyai/evidently/main/LICENSE ; telemetry:
  https://docs.evidentlyai.com/faq/telemetry ; alibi-detect 0.13.0 (11 Dec 2025), licence field "Business Source
  License 1.1": https://pypi.org/project/alibi-detect/ ; nannyml 0.13.1 (12 Jul 2025), Apache-2.0; frouros 0.9.0
  (5 Oct 2024), BSD-3-Clause; river 0.27.0 (13 Nov 2026), BSD-3-Clause

## Legal note

All licence statements in this report (Camunda License v1 and the Enterprise requirement, LGPL for SpiffWorkflow and
SpiffArena, GPLv3 for pyDMNrules, AGPLv3 for Unleash, the bpmn.io watermark clause, the GrowthBook enterprise
directories, and every permissive licence listed; revision 2 adds GPL-3.0-or-later for scikit-survival, BSL 1.1 for
alibi-detect, EPL-2.0 for CBC (`cbcbox`) and Python-MIP, and the permissive licences of lifelines, statsforecast,
SciPy, HiGHS, OR-Tools, jsonpatch, deepdiff and Evidently) are findings from public pages read on 24 Nov 2026. They must be
reviewed by Kinective's Legal team before anyone relies on them, and in particular before any of these components is
included in the customer trial package or another redistributed artefact.
