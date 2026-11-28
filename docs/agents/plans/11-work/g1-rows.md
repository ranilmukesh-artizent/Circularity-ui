# G1: View data, backend (plan 11)

All data is synthetic. Net, baseline and forecast values are modelled; CO2e is estimated from sample factors (or measured where a
decision has a measured value). The carbon figures and the export wording go to Kinective's Legal team for review before anyone
relies on them.

## 1. Contract (for the frontend writer)

Three reads and one action. Every read needs a signed-in account that may open Analytics, then the section of the chart (below).

### `GET /api/screens/analytics/rows`

Query: `source=decisions|cases`, `chart`, `key` (default `all`), the page's filters (`tenant`, `cls`, `route`, `from`, `to`, `model`,
`tenant_filter`, `org`: they narrow the decisions' rows exactly as they narrow the page), `days` (0 to 730; only the `pack` chart:
cases opened in the last N days, 0 = all), `sort` (a column key of the answer), `dir=asc|desc` (default `desc`), `q` (search text,
at most 100 characters), `limit` (default 50, clamped to 1..200), `offset` (>= 0).

Answer:

```
{ title, subtitle,
  columns: [{key, label, kind: "text"|"money"|"number"|"date"|"days"|"percent", unit?}],
  rows: [{<column key>: value}],          // exactly the columns; money and numbers are numbers (or null), dates YYYY-MM-DD
  total,      // rows after the search box (the table's count)
  of,         // rows of the selection before the search box (the figure's count)
  shown,      // rows in this page
  period, tenants: [..],
  totals: {<money column key>: n},        // over all `total` rows (the table's totals row)
  sum: {label, value, unit: "usd"|"count"|"kg", n} | null,   // the figure the selection adds up to; before the search box
  truncated,  // total > 5,000: one export would be cut
  can_export } // total > 0 and the caller is a person (an agent token: false)
```

`subtitle` is `"<of> rows · <period> · <tenants>"` plus a note for some charts (`predicted`, `models`, `sustain`, `age`, `pack`).
`models` ends with `your rows`. `sum` is always an object in this build (never null). The reconciliation line is
`These {sum.n} rows add up to {sum.value} {sum.label}`; when the search box is used, `total` differs from `of` and `totals` follow
`total`, while `sum` stays the figure.

Errors: 401 signed out; 403 a role without the chart's section (or without the page); 422 unknown source, chart, key part, sort
column, a chart that does not belong to the source, `dir`, a negative `offset`, `days` out of range. Body is the usual
`{ok: false, error: {code, message}}`.

### `GET /api/screens/analytics/rows.csv`

Same query without `limit`/`offset`. Streams `text/csv` (`Content-Disposition: attachment; filename="circularity-<chart>.csv"`):
the header is the column labels, then the rows in the requested order, 5,000 at most, only the shown columns except the override
reason (never exported). Text cells that begin with `=`, `+`, `-`, `@` are written with a leading apostrophe. Same errors as above.
Each call is written to the journal (see 4).

### `GET /api/screens/analytics/open-age?tenant_filter=All&org=`

```
{ as_of, basis, total: {n, value}, routes: [{id, name}],
  bands: [{key: "0-7"|"8-14"|"15-30"|"30+", label, n, value, rows: {source:"cases", chart:"age", key},
           routes: [{id, name, n, value, rows: {source, chart, key}}]}] }
```

Open decisions are live cases at `awaiting_approval`; value is the recommended route's forecast net (modelled). `n` of all bands adds up
to the page's `liveOpen` ("awaiting approval") count. Section `pipeline`. Pass a band's `rows` object straight to `/rows`.

### Charts and keys

A key is `all`, a token of the chart, or parts joined by `|` of `dim:value` (each dim at most once; a part not listed for the chart,
an empty value or an unknown value is a 422). Months are indexes `0..11` (`month:3` is the fourth month of the page's MONTHS list).

| source | chart | section needed | keys (beyond `all`) | what `sum` adds up | the figure it matches |
|---|---|---|---|---|---|
| decisions | `kpi` | waterfall | `avoided`, `pending` | uplift (actual minus baseline); avoided spend; pending count | the KPIs: `metrics.uplift`, `metrics.avoided`, `metrics.pend`. `all` also opens the "median days" card |
| decisions | `waterfall` | waterfall | `baseline`, `circularity`, `route:<id>` | `all` and `route`: uplift; `baseline`: baseline; `circularity`: actual | the bars: `metrics.base`, `metrics.act`, a route's step |
| decisions | `pipeline` | pipeline | `approved` (= `all`), `carried_out`, `reconciled` | decisions counted | the funnel's three clickable bars |
| decisions | `mix` | mix | `route:<id>`, `month:<0-11>`, both | decisions carried out (reconciled + pending) | a stacked segment (`route:redeploy\|month:3`) |
| decisions | `flow` | pipeline | `cls:<id>`, `route:<id>`, `status:<reconciled\|pending\|cancelled\|expired>`, any combination | decisions | class to route to status: a node is one part, a link is two (`cls:motor\|route:redeploy`, `route:resale\|status:pending`) |
| decisions | `heatmap` | mix | `route:<id>`, `cls:<id>`, both | median uplift per case (reconciled) | a route x class cell |
| decisions | `trend` | waterfall | `month:<0-11>` | net recovered (sum of actuals, reconciled) | a month's bar; `all` is the year |
| decisions | `predicted` | predicted | `model:<v>` | decisions counted | the scatter's points (reconciled, not exit, not override) |
| decisions | `models` | models | `model:<v>` | decisions counted, **the caller's rows** | the table keeps the demo's numbers over every tenant; the rows are the caller's own, the subtitle says `your rows` |
| decisions | `overrides` | overrides | `reason:<exact reason text>` | net effect vs the recommended route (estimated) | the override table's row and total |
| decisions | `eng` | eng | `equip:<model>`, `comp:<name>`, both | value lost (`ero`) | a heat cell (its rows are `ero > 0`, as the browser's drill) |
| decisions | `sustain` | sustain | `estimated` (= `all`), `measured`, `route:<id>` | `all`/`estimated`: CO2e estimated (kg); `measured` and `route`: CO2e measured (kg) | the three totals and a route's bars |
| cases | `age` | pipeline | `band:<0-7\|8-14\|15-30\|30+>`, `route:<id>`, both | forecast value of the open decisions | `open-age` bands and cells |
| cases | `pack` | the page (`analytics`) | `pack:<key>` (required, first), then `route:<id>`, `grade:<g>`, `state:<closed\|open\|live>` | net (modelled) of the cases | a pack headline tile or link; `days` as the headline's period |

Value sets: `route` ids are the reference ROUTES (`redeploy`, `resale`, `intparts`, `extparts`, `relase`, `material`, `exit`) for the
decision charts; `cls` the reference CLASSES plus any class in the rows; `model` MODELS (`v1.0`..`v1.3`); `equip` and `comp` the
reference EQUIP and COMPS; `reason` only a reason found in the caller's own override rows; for `age` and `pack` a route is one
present in the caller's cases (or a reference route), a grade one of the pack's cases (or `No grade`), and `pack` is a pack file or a
published pack. `status:` is the decision status; `state:` is the case's: `closed` (stage closed), `open` (not closed), `live`
(approved or executing).

Where the browser's drill sits (`frontend/src/pages/analytics/AnalyticsCharts.tsx`): `drills.all` = `kpi/all`, `drills.avoid` =
`kpi/avoided`, `drills.pend` = `kpi/pending`; waterfall bars = `waterfall/baseline|circularity|route:<id>`; mix segment =
`mix/route:<id>|month:<i>`; funnel = `pipeline/approved|carried_out|reconciled`; heat cell = `eng/equip:..|comp:..`; override row =
`overrides/reason:<text>`. The new charts' parts are `flow`, `heatmap`, `trend`, `age`.

Columns (labels are plain words; money columns carry `unit: "usd"`):

* decisions, default (kpi, waterfall, pipeline, mix, flow, heatmap, trend, models): `id` Case, `month` Month, `tenant` Tenant, `cls`
  Asset class, `route` Route, `status` Status, `model` Model, `asset` Asset (shown in full), `p50` Predicted P50, `actual` Actual,
  `baseline` Baseline (modelled), `vs` Vs baseline, `days` Days to realise, `avoided` Avoided spend, `co2e` CO2e estimated (kg),
  `co2m` CO2e measured (kg).
* `predicted`: id, month, tenant, cls, route, model, asset, `p10`, `p50`, `p90`, actual, vs.
* `overrides`: id, month, tenant, cls, asset, `rec` Recommended route, `exec` Carried-out route, `ovr` Estimated vs recommended,
  `reason` Override reason (cut at 200 characters, ends with an ellipsis; **not exported**), actual, baseline, vs.
* `eng`: id, month, tenant, cls, route, asset, `equip` Equipment model, `comp` Component, `ero` Value lost, actual, baseline, vs.
* `sustain`: id, month, tenant, cls, route, status, asset, co2e, co2m.
* `age`: `id`, `tenant`, `received` (date), `days` (days open), `route` (proposed route), `net` (forecast value, modelled).
* `pack` (a fixed whitelist, never the case document): `id`, `received` (date), `grade`, `route` (labelled `Channel` for the device
  pack), `status`, `days` (received to closed, or to now while open), `net` (modelled), `co2` (kg, estimated), `co2_set` (the factor
  set named on the route: the factor source).

Every column is sortable (`sort=<key>`); `month` sorts as a month, `received` as a date. Empty values sort last in both
directions. Ties keep the id order, in both directions, so paging is stable. The default order (no `sort`) is largest absolute
value first for decisions, oldest first for `age`, largest net first for `pack`.

### `POST /api/actions/analytics.export` (journals an export)

Input: the same parameters as `rows.csv` (`source`, `chart` required; `key`, filters, `sort`, `dir`, `q` optional; the filters are
named `from`, `to`, `tenant_filter`, ...). Output `{rows, capped, chart, columns}`. A person only: an agent-prepared call is refused
(`approval_required`). The browser needs only `rows.csv`; it calls this action itself.

## 2. What changed per file

New files, all mine:

* `backend/di/services/screens/analytics_rows.py`: the chart registry (id, source, section, dims, tokens, resolver, fixed column list),
  key parsing and validation, the selection (page rows via `analytics.page`, cases via `visible_cases` or the pack's `pack_cases`),
  stable sort, search, totals, `sum`, paging, the CSV lines, and the action `analytics.export` (declared with `ACTIONS.setdefault`,
  a guard that refuses agents, a handler that re-runs the same selection and the section gate).
* `backend/di/services/screens/analytics_open.py`: the open decisions by age (bands x proposed route, value at risk).
* `backend/di/schemas/analytics_rows.py`: response models.
* `backend/di/routes/screens/analytics_rows.py`: `/rows`, `/rows.csv`, `/open-age` (a new router with the same prefix as the
  existing analytics router; `routes/screens/__init__.py` includes every module that has a `router`, so no registration line was needed).
* `backend/tests/test_analytics_rows.py`.

No existing file was edited. No migration, no table, nothing under `fixtures/golden/`.

## 3. Access (how each rule is met)

* Section gate: `p.require_page("analytics")` in the route, then `p.require_page("analytics", <section of the chart>)` right after
  the chart is looked up, in the one `select()` every path (rows, csv, action) goes through. Engineer: only `eng` and `sustain`;
  Planner has no `eng` or `sustain`; Developer and Warehouse Manager have no analytics page. The hidden `pool` section has no chart.
* Decisions: the rows come from `analytics.page(...)`, the page's own read (`visible_rows`: tenant boundary and the top bar's tenant
  filter, then the page's filters and the org subtree), so a bar and its rows cannot disagree and no second access path exists.
* Cases: `visible_cases` (tenant boundary and warehouse lock), the top bar's tenant filter and the org subtree for `age` (the same
  predicate as the page's `liveOpen`); `pack` uses `analytics.pack_cases` (the Packs tab's and the headline's own set: they ignore the
  top bar filter and the org select, so the rows reconcile with the tiles).
* No free-form column, table or filter: `chart` and `key` pick a predicate from code; sort must be one of the chart's column keys.
* `reason:` values are validated against the caller's own rows, so a reason held only by another tenant is a 422, not an empty answer.

## 4. Export and the journal

A read is not journaled (`pipeline.py`: "Read actions stop after the handler: they are not journaled"). So the export is an action,
per AGENTS.md rule 8: `GET rows.csv` runs `invoke("analytics.export", ...)` first (risk `act`, journaled, one domain event), and only
when it succeeded builds and streams the file. The journal row has the actor, role and the input (chart, key, filters, sort, search);
the event payload carries the row count. The handler's output deliberately holds no rows (the event payload would copy them).

## 5. Needed from files I do not own

* `backend/di/services/agents/forbidden.py`: add `"analytics.export"` to `FORBIDDEN_ACTIONS`. I did not edit it. Today the action's own
  guard refuses a call that carries `ctx.preparer`, and the route passes the agent id as the preparer for an agent token, so an
  agent is refused either way; the list is the place AGENTS.md rule 10 wants it, and it also keeps the tool catalogue's `agent_mode`
  honest ("no").
* `backend/di/core/policy.py`: no change needed. The three new charts reuse existing sections (flow: pipeline, heatmap: mix, trend:
  waterfall); if the owner wants new sections for them, `EXTRA_SECTIONS` is where they would be declared.
* The action catalogue now has one more action (`analytics.export`). Suites that walk `ACTIONS` (`test_actions.py`,
  `test_agent_catalog.py`, `test_catalog_hygiene.py`) were not run (told not to); they take actions generically, as they did for
  `view.save`, but are the first place to look if the gate fails.

## 6. Checks

Run from the repo root in Git Bash (`export MSYS_NO_PATHCONV=1`):

```
API_TEST_NO_X=1 bash scripts/dev/api-test.sh tests/test_analytics_rows.py tests/test_screens_analytics.py
  -> 477 passed, 1 warning in 229.21s (0:03:49)
     (56 of them are the new file; an earlier run of the new file alone had one failing test, a wrong account id in the
      warehouse-lock test, fixed before this run)
docker compose exec -T api sh -c "ruff check <the 4 source files> tests/test_analytics_rows.py"
  -> All checks passed!
docker compose exec -T api sh -c "ruff format --check <the same 5 files>"
  -> 5 files already formatted
docker compose exec -T api mypy di/services/screens/analytics_rows.py di/services/screens/analytics_open.py \
    di/schemas/analytics_rows.py di/routes/screens/analytics_rows.py
  -> Success: no issues found in 4 source files
docker compose exec -T api lint-imports
  -> Contracts: 6 kept, 0 broken.
```

Not run (as instructed): the catalogue-wide suites, smokes, `reset.sh`, a browser. LF endings checked (no CR in any new file).

## 7. Left or uncertain

* Heatmap: the cell shows a median uplift; `sum` is that median (label `Median uplift per case`) and `totals.vs` the total, so the
  reconciliation line differs from the other charts (it says median, not total).
* `eng`: the heat cell's average divides by every row of the pair (including rows with no loss); its rows are `ero > 0`, as the
  browser's drill. `sum` is the total value lost, which equals the cell's average times its `n` only when every row has a loss.
* `sustain` `route:<id>`: rows are the decisions with both an estimate and a measured value; `sum` is the measured total (the
  estimate for the same rows is `totals`-free: read it from the `co2e` column). One `sum` per answer.
* `age` and `pack` dates use the workspace clock (`clock.now()`: pinned in tests, simulated in the dev stack). `received` is the case's
  own `received` when it has one, else its creation time.
* The `pack` rows have no tenant column (not on the whitelist); `tenants` in the answer lists the owners present.
* `truncated` means one export would be cut at 5,000; the JSON itself is paged, so it never loses rows. The current data has at most
  1,400 decisions, so it is `false` in practice.
* Performance: each `rows` call builds the page's whole answer (it also computes the model statistics) before narrowing. It is
  a few tens of milliseconds on 1,400 rows; if the page's read grows, the decisions' filter could be split out into a helper that
  `analytics.page` and this module share (a change in a file I do not own).
* Not checked in a browser or by the frontend; the `rows` object that writer F's headline tiles pass (`{source:"cases", filter}`)
  must be translated to `chart=pack&key=pack:<key>|route:..|grade:..|state:..&days=<period>`.
