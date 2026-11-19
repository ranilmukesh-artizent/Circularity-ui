# Golden data

What the static demo (`index.html`) computes, frozen as JSON. The Python backend's parity tests compare against these files (docs/BACKEND_STEPS.md, step B1).

**Regenerate** only when `index.html` changes on purpose, then review the diff:

```sh
cd apps/web && npm run golden          # or: node apps/web/scripts/dump-golden.mjs from the repository root
```

The demo's script runs headless with the clock pinned to its as-of time (7 Oct 2026 09:00 UTC) and `Math.random` seeded, so the output is identical on every run. Numbers are rounded to 6 decimal places. A repeated object is written once and referenced afterwards as `{"$ref": "<path>"}`.

| File | Contents |
|---|---|
| `world.json` | As-of time, months, tenants, sites, facilities, routes, route mix, model versions, gates, asset classes, grade factors |
| `cases.json` | The 128 live cases: evidence, routes (terms, gates, P10/P90, rank), recommendation, stage, execution detail |
| `decisions.json` | The 1,400 closed decisions behind Analytics |
| `sources.json` | Source system types and the 21 configured sources |
| `canonical.json` | The seven canonical models and the field mappings per source |
| `events.json` | Event stream and conflict queue |
| `tools.json` | MCP tools, agents, hard rules, enterprise MCP servers |
| `policy.json` | Roles and their pages and permissions, demo accounts, sign-in IDs |
| `actions_catalog.json` | The 76 actions: id, risk, permission, scope, input schema |
| `figures.json` | The demo's 31 data checks (all passing), and for each of the 11 accounts: permissions, visible pages and sections, tenants, visible cases, totals, counts, key figures, inbox |
| `actions.json` | A scripted RT-1048 journey: each `invoke()` call (submit, approve, six system acknowledgements, confirm outcome, and the refusals in between) with its result and the case state after it |
| `reads.json` | The read actions from a fresh copy of the demo: six case reads for 22 cases as five accounts, and `cases.list`, `inbox.get`, `receiving.plan`, `access.lookup` and `kpi.explain` as all 11 accounts |
| `writes.json` | Write actions in 16 scripted scenarios (decisions, evidence, scenarios, notifications, tenant access, MCP proposals, delegation, identity, and execution: acknowledgements, resend, outcomes), each in a fresh copy of the demo: every call's result, then reads that show what changed |
| `execution.json` | Execution detail for the 17 read-fixture cases with routes: the plan (steps, systems, documents, owners, time limits), the move and its legs, the what-if guidance, and every eligible route's terms as cost lines (method, source, rupees) |
| `engine.json` | The decision engine's read answers: `case.whatIf` for every case with routes under 10 scenarios, and `pool.optimize` for the pooled cases |
