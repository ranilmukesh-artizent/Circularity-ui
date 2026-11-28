# Analytics brief (writer G, research only)

Scope: compare the owner's two prototypes with our Analytics, propose a design that beats both, add "View data" on every
chart, and split the build between two writers. Nothing in product code was changed. All figures in the prototypes and in
our app are synthetic. A client name in a prototype is not carried over (it is "a recommerce customer" here).
Legal: the carbon figures and any accounting or reporting wording go to Kinective's Legal team before anyone relies on them.

Screenshots (scratchpad `C:\Users\ranilmj\AppData\Local\Temp\claude\780921fb27081449\df3f1b00-d9b3-4212-932e-39cbcbf03b94\scratchpad\g\`):
- `proto-rec-analytics.png` (recommerce, full page, 1440 px), `proto-ams-analytics.png`, `proto-car-analytics.png`,
  `proto-tel-analytics.png`, `proto-med-analytics.png` (same engine, other labels)
- `proto-rec-drill.png` (the "records behind the figure" sheet), `proto-rec-build.png` (weekly trend, grade x channel, "Build an analysis")
- `dinesh-analytics.png` (the older file's Analytics)
- Ours: the live screenshots FAILED. The shared dev stack's api hung while other writers' edits kept reloading it (`/api/screens/reference`
  timed out; page stayed on "Loading..."; `ours-decisions.png` shows only that). Our side below is from code. Re-shoot
  with `ours.mjs` in the same folder once the api is healthy.

## 1. What the prototypes' Analytics has

Two files, one idea. `Recover_App dinesh.html` is the older one: tool fleet only, one Analytics view. `Recover- Prefinal- 5 Industry
Segments.html` has a second, generated Analytics (`rAnalytics`, `dFinance`, `dBuilder`) that runs one engine over five industries
(`DXC` config: only labels, channels, grades, items and 1,100 to 1,600 generated sample records each). Both draw everything as
hand-written SVG and div bars from template strings. No chart library, no canvas. Colours are CSS tokens (six route colours `--p-*`,
`ok/warn/crit`, a light and a dark set). Data is generated in the browser from a seeded random function, so nothing is real.

### 1a. The five-industry engine (Prefinal file)

| Industry | Item / grade / route words | Headline measure names |
|---|---|---|
| Tool fleet (after-market) | Tool family / Condition A-D / Route: redeploy to pool, refurbish and re-rent, fix and return, sell pre-owned, harvest parts; 5 depots | Value recovered, back-in-use rate, days to next use |
| Recommerce | SKU / Grade A, B+, B, C / Channel: Buy Now, Offers, Auction, Wholesale lot; 5 sources | Net recovered, sell-through, days to sell |
| Used cars | Model / Score 5-2 / Channel: retail lot, online retail, dealer trade, wholesale auction; 3 sources | Gross recovered, sell-through, days in stock |
| Telecom equipment | Equipment type / Bench test pass, minor, fail / Route: redeploy to site, hold as spare, resell to broker, harvest boards; 4 regions | New spend avoided, reuse rate, days to redeploy |
| Medical rental | Device model / Inspection pass, service due, fail / Route: re-rent, service then re-rent, hold at depot, retire; 3 depots | Rental value, re-rent rate, turnaround days |

Layout order (top to bottom, identical for all five):
1. One sentence: "Every figure below opens the devices behind it. Shared definitions: sell-through = ..." (the definitions are on the page).
2. Four KPI cards: net recovered 30 days (hero), rate, days, still listed. Each ends in "Drill".
3. Panel "Financial outcomes", headed by one sentence: "$7,274 more than the standard route, 87.1% of gross kept as net".
   Four more cards (gross, net after fees and holding, gain over standard route, value at risk in ageing stock), then:
   - Waterfall gross to net: gross, channel fees, handling and repair, holding cost, net. Bars tap through. Colour: ink, crit, warn, ok.
   - Weekly gain over the standard route: bars per week (green positive, red negative) with a cumulative line, direct label on the line end.
   - Value tied up in open items by age (0-7, 8-14, 15-30, over 30 days): one stacked bar per band split by channel, legend below, each segment taps through.
   - Sell-through heatmap, item x channel: diverging tint around 50 percent (green above, red below), "-" where under 4 records, cell title shows count.
   - Sankey: grade to channel to outcome (sold, still listed), band width = count, every band taps through.
4. Table "Sell-through by item": routed, sold, inline rate bar (warn colour under 45 percent), days, price realised vs forecast, and a chip with the best channel and its net each. Row and chip tap through.
5. Two panels: net recovered by week (line, area, point labels, all values also as chips below), and rate by grade and channel (horizontal bars, only combinations with 12 or more records).
6. "Build an analysis": one text box plus five example chips per industry. The parser (regexes) finds one measure (rate, days, realised, net, count, offers per listing), up to two dimensions (item, channel, grade, source, week), and filters (grade, channel, model, source, "last N days"). Result: a sentence naming highest and lowest, then horizontal bars, a line (by week) or a pivot table tinted by value; each bar or cell drills. "Save as a view" keeps it on the page for everyone with access.

Interactions: every KPI, bar, cell, week, Sankey band and waterfall bar opens one sheet "Records behind the figure": a title built from the
filter ("sold, grade B, Offers, last 30 days"), count and "sample data", four summary KPIs for those records, a table of the first 60 rows
(id, item, grade, channel, status pill with days, opened, offers, forecast, realised), a "Showing the first 60 of 490" line, and each open row opens its case. No sort, no
filter box, no export, no pagination. No period switch other than fixed 30 days and the weekly axis. Hover is the browser `title`.

### 1b. The older file (tool fleet, `renderAnalytics` and `xAnalyticsSection`)
Four KPI cards (recovered 60 days, above standard route, forecast accuracy, owner overrides); weekly value line; value by path (bars in the
path colours); gain over standard route by function; path mix by return channel (stacked bars); 2x2 matrix forecast within 5 percent against
who decided; forecast vs realised scatter with a perfect-forecast line; then a second block "service desk and contract refresh" (four
KPIs, upgrade rate by market before and after, estimate accuracy by family, a site x family "where value is leaking" heatmap with one hot cell, and "Looking ahead" signals with an action button each).
This is what our page already resembles; the Prefinal engine is the better design.

### 1c. What makes it read well
- One headline sentence then four numbers, then charts: the reader gets the answer before the evidence.
- Each chart has a plain title, a one-line "tap ..." instruction and a one-line meaning below it ("holding cost is the cost of capital and storage for each day a device waits").
- Definitions printed on the page; the same nouns per industry (one config), so five industries cost one screen.
- Direct labels on bars, line ends and Sankey nodes (no legend hunting except the stacked bars); value shown on every bar.
- Pairing: two charts per row, a full-width flow chart, a table with inline bars. Density is high but groups are boxed.
- Colour: one accent, six categorical route colours, status colours reserved for good, warn, bad. Heatmap is diverging around a meaningful midpoint.
- Weak spots to beat: no table alternative to charts, Sankey paths and labels carry meaning by colour and width only, 11 px chart text,
  sample data made in the browser, drill sheet capped at 60 rows with no sort, search or export, the builder is a regex parser that
  fails silently on wording it does not know.

## 2. What ours has today

Code: `frontend/src/pages/analytics/` (`AnalyticsPage.tsx` 392 lines, `AnalyticsCharts.tsx` 359, `PackView.tsx`, `SavedViews.tsx`, `BacktestReport.tsx`,
`RenewalReport.tsx`), facade `frontend/src/api/analytics.ts`, server `backend/di/services/screens/analytics.py` and `backend/di/routes/screens/analytics.py`.
Charts are hand-written SVG in JSX plus div bars (`.bar > i`), same as the prototype. `frontend/package.json` has no chart library
(dependencies: dagre, @xyflow/react for the Modeler, react-query, react-markdown). Route colours are tokens `--rt-*` in `analytics.css`, 3:1 against the card in both themes.
Accessibility already partly there: `role="img"` + `aria-label` on SVGs, `role="button" tabIndex=0` with Enter and Space on bars and heat cells, every chart drillable.

Tabs: Decisions, Packs, Back-test (only when a replay run exists).

| Section (role-gated by `canPage('analytics', id)`) | Chart | Feeds from |
|---|---|---|
| Header filters | month from/to, tenant, org unit, asset class, route, reset | query of `GET /api/screens/analytics`; `visible_rows` (tenant boundary) |
| KPI x4 | uplift, avoided spend, median days, unresolved | `metrics` of the same answer; `liveOpen` = live cases at `awaiting_approval` (`visible_cases`, tenant + warehouse lock) |
| waterfall | baseline to Circularity by route | rows: `baseline`, `actual`, `route` |
| pipeline | funnel case to reconciled | rows by status + `liveOpen` |
| mix | route mix by month (stacked) | rows `mi`, `route` |
| predicted | scatter p50 vs actual, log scale, calibration band | rows `p10/p50/p90/actual` |
| models | model-version table (error, bias, P10-P90 coverage) | `model_stats`, computed over EVERY closed decision, not the account's |
| pool | pool efficiency | rows `pool`; hidden for every role (`HIDDEN_SECTIONS`) |
| overrides | override rate, reasons | rows `override` |
| eng | equipment x component heat (value lost) | rows `ero`, `equip`, `comp` |
| sustain | CO2e estimated vs measured by route | rows `co2e`, `co2m`; `telemetry_unavailable` from `source_system` |
| Drill | one inline panel at the page bottom, 12 rows per page, Export CSV of the whole selection, row opens `ClosedDrawer` | the same rows, filtered in the browser |
| Packs tab | KPI tiles with sparkline, 2 worked questions as bars with example case ids, renewals, saved views, stage agents | `GET /api/screens/analytics/pack`: `kpis.kpi_rows(pack, cases)` and `question_rows` over live cases of that pack (`visible_cases`) |

Source of the Decisions rows: `fixtures/golden/decisions.json` through `repositories/decisions.all_rows()`: 1,400 rows (612 / 419 / 369 for the three
tenants; 1,277 reconciled, 61 pending, 39 cancelled, 23 expired). Fields: id, month index, tenant, site, class, route, model, assetId, snapshot, status,
p10/p50/p90, actual, baseline, days, baseDays, avoided, co2e, co2m, pool, ero, comp, equip, override {rec, exec, reason, cf, delta}. The server sends all
rows of the account and the browser computes every chart and the drill from them (documented in the module docstring). So: the "real backend data"
requirement is met for Decisions only in the sense that a server read, tenant-filtered, feeds it; the rows are a fixed synthetic fixture, not a table. Pack
numbers (Packs tab) are computed from live cases in Postgres, so those are real. All page numbers are parity with the demo and must not change (AGENTS.md rule 1).

## 3. Gap list

Theirs does better:
1. A headline sentence plus four cards that answer "how are we doing and what did Circularity add" in one glance. Ours opens on a filter bar.
2. Flow chart (grade to channel to outcome) and a gross-to-net waterfall with fees, handling and holding (ours has baseline-to-actual only).
3. One heatmap of the main measure (item x channel) with a meaningful midpoint; ours has only the engineering loss heat.
4. Ageing of open stock with value at risk, split by route.
5. Table with inline rate bars and "best route" chip: the reader sees the winner per item.
6. A chart for the weekly trend with a cumulative line and direct end label (ours: monthly stacked mix only).
7. "Build an analysis" with example chips and a saved view on the page; ours has the assistant (Ask) and saved views only for pack questions.
8. Same screen for five industries from one config.
9. Every figure opens records. Ours does too, but at the page bottom, 12 rows per page, far from the chart.

Ours does better (keep): server-side tenant boundary and role sections on every read; real live-case numbers on Packs; honest estimated
vs measured CO2e (never mixed); predicted-vs-actual with P10-P90 band, model versions and overrides (the prototype's learning loop is
a faked 2x2); parity with the demo; maker-checker and audit context; theme-safe tokens with contrast checked; keyboard and screen-reader basics;
saved views with sharing and alerts; the back-test tab; contract renewals comparison with a stated caveat.

## 4. Proposed Analytics (Decisions tab, then the pack headline)

### 4a. Order (top to bottom)
1. Headline sentence (computed, never typed): "+$X more than the baseline across N reconciled decisions; median M days, K percent faster." One line of definitions under the KPIs ("uplift = actual net minus the agreed baseline (modelled)").
2. Four KPI cards, unchanged numbers and drills. A pack with a headline (4c) shows its five instead.
3. Filter bar (kept, as a compact strip) with the row count chip.
4. Row A: Waterfall (kept) and Flow (new): class -> route -> status. Flow replaces the funnel's job of "where do cases go"; the funnel stays beside it as a slim strip.
5. Row B: Heatmap route x class showing median uplift per case (new; diverging around 0, number in every cell, "-" under 5 rows) and Trend (new): net recovered per month bars + cumulative uplift line, direct end label.
6. Row C: Route mix over time (kept), Predicted vs actual (kept) with the model table.
7. Row D: Overrides (kept), Open decisions by age and route with value at risk (new, from live cases; see 4d).
8. Row E: Engineering heat and Sustainability (kept).
9. "Build an analysis" (4f), then Saved views.
10. Drop: the inline Drill panel at the page bottom (replaced by the View data drawer); the pool section (already hidden for all roles); the long intro paragraph (replaced by the headline). Keep the journey-step chips but smaller (`Stp`), they carry the demo's story.
Parity rule: existing charts keep their numbers and text; the new ones are additive, and the reorder needs a decision-log entry (open question 1).

### 4b. The "View data" drawer (one component, `DataDrawer`)
- Opens (1) from a "View data" button in every chart's panel header, showing all rows behind the chart; (2) from a click or Enter on a bar, flow band, heat cell,
  KPI or week point, pre-filtered, with the filter shown as removable chips ("Route: Redeploy", "Month: Mar", "Status: reconciled"). Uses the existing `Drawer` (`components/Overlay.tsx`, `wide`) so focus trap, Esc and focus return are already right.
- Title: the chart title. Subtitle: "1,277 rows · Jan to Dec · Customer A, B" (count, period, the tenants the account may see).
- Table: plain-word column headers sent by the server (Case, Month, Tenant, Asset class, Route, Status, Model, Predicted P50, Actual, Baseline, Vs baseline, Days, Avoided, CO2e estimated, CO2e measured, Override reason).
  Money right-aligned, tabular numerals, sticky header, click a header to sort (`aria-sort`), 50 rows per page, filter box that matches id, model, asset, site.
- Footer: a reconciliation line "These 1,277 rows add up to $2.31M, the bar you opened" so the rows prove the figure; totals row for money columns.
- Row click opens the existing `ClosedDrawer` (or the case page for a live case) and Back returns to the same filtered table.
- Export CSV: the same server filter and sort, all rows up to a cap of 5,000, only the columns shown. Offered only to roles that already see those rows in the table (same permission as the section).
- A table alternative for every chart: the drawer is it. Each chart also gets a `<figure>` with a one-sentence text summary (`aria-describedby`) so a screen reader hears the finding before the SVG.
- Keyboard: every mark is a button (bars, cells, flow bands) with an `aria-label` that says label, value and "opens the rows"; visible focus ring from tokens; no hover-only content.
- Motion: none beyond the drawer's existing open. Empty state: "No rows match. Clear the chips".

### 4c. Per-pack headline (coordinate with writer F, section D, `11-work/f-analytics.md`)
F builds the five numbers (net recovered, sell-through by channel, days to sell, still listed, carbon avoided) and the grade-to-channel chart for `tool_fleet` and `device`.
Agree one contract before either writes UI: extend `GET /api/screens/analytics/pack` with
`headline: {kpis: [{id, label, value, unit, sub, rows: {source: "cases", filter: {...}}}], flow: {nodes: [{id, label, col}], links: [{from, to, n, rows: {...}}]}}`.
F fills it (backend `kpis.py`/pack data, `PackView` tiles). G's Flow and DataDrawer accept exactly this `rows` object as their open argument, so F's tiles and links drill with no
extra code from F. Until F lands, G builds the Flow on the Decisions rows (class -> route -> status). Shared files: `AnalyticsPage.tsx` and `PackView.tsx` are edited by F first; G rebases onto them (see 5).
The remaining packs keep their tiles (section D2).

### 4d. Data for the new charts
- Flow, heatmap, trend, waterfall, mix: counted in the browser from the Decisions rows already loaded (as today), so a bar and its rows can never disagree.
- Open decisions by age: live cases in `awaiting_approval` (server read over `visible_cases`; needs `received` age and forecast value). New small read, see 5.
- Pack headline: server computes (cases are the source); carbon avoided through `modeler/carbon.py` with its factor provenance shown in the drawer column "Factor source".

### 4e. Charts: decision on a library
Firm choice: **`@visx/sankey` 4.0.0 and nothing else.** Everything else stays hand-drawn SVG, as today and as the prototype does.
- Why a library at all: only the flow chart is non-trivial. A correct Sankey (node ordering, link widths, collision-free vertical spacing, curved ribbons) is the d3-sankey layout, about 600 lines to rewrite and test. Bars, lines, heat cells, waterfall and the stacked mix are 20 to 60 lines each and we already have them with tokens and keyboard handling; a general chart library would re-skin and re-test all of that and fight our token colours.
- Facts (`npm view`, 28 Nov 2026): `@visx/sankey` 4.0.0, MIT, published 11 Jun 2026, 20 kB unpacked; peers `react ^18 || ^19` (we run 18.3.1) and `@types/react`; it wraps `d3-sankey` 0.12.3 (BSD-3-Clause, layout only), `@visx/group` and `@visx/vendor` (the d3 pieces, bundled). No Vite coupling (plain ESM). Measured with esbuild in a scratch folder: a bundle that imports `Sankey` is 10.7 kB minified, 4.1 kB gzip (the measuring is for the layout code; re-measure with `vite build` before merge).
- What we still draw by hand: all marks (we use only its layout: nodes and links with x0, x1, y0, y1, width), so colours are `var(--rt-*)` and `var(--ink)`, text is our 12 px+ labels, bands are `<path>` with `role="button"`, `tabIndex`, `aria-label`, and keyboard handlers; the table alternative is the drawer. No Visx tooltip or hover layer.
- Rejected: Recharts 3.11.2 (MIT, has Sankey but pulls redux, immer, reselect, es-toolkit: far larger and themes through props, not tokens); d3-sankey directly (smallest, but last published 2022, BSD-3: acceptable licence, but the maintained wrapper is cheaper in typing and React fit); plain hand-written Sankey (about 120 lines for the prototype's fixed 3 columns, but ordering and label collisions break on real data; the cost is owner-visible only when it breaks).
- Needs the owner's OK to add the dependency; the owner has already approved a library in principle, so this is a go/no-go on this one package, not a new question.

### 4f. "Build an analysis"
v1 is a structured builder, not text parsing: pick a measure (uplift per case, net recovered, median days, override rate, count), up to two breakdowns (route, class, tenant, month, model), and filters as chips; result is bars, a line (by month) or a pivot heat table with the same drill and View data. A one-line summary names highest and lowest like the prototype. "Save as a view" reuses `SavedViews` (`services/analytics_views.py`), which stores the question and parameters, not the answer, and re-asks within the viewer's own tenants (R21). A text box that sends the sentence to the existing assistant (Ask, `openAssistant`) stays as the natural-language path, with the five example chips per pack; it never silently misparses because the assistant answers in words and offers the builder pre-filled. Aggregation for the builder runs on the browser over rows already loaded (Decisions) and on the new server rows endpoint (pack cases).

## 5. "View data" feasibility, per chart

All Decisions charts: the rows are already in the browser, in the account's tenant boundary (`visible_rows`, no warehouse lock because decisions are not at a location), so
View data needs no new read for them. The server rows endpoint (below) is still recommended so the drawer pages, sorts, filters and exports on the server and the page stops
depending on shipping all 1,400 rows (it would not scale; 1,400 rows is fine for the demo).

| Chart | Rows behind it | Approx. count | Safe columns | Note |
|---|---|---|---|---|
| KPIs, waterfall, mix, funnel | closed decisions (`all_rows`) filtered like today's `drills` | up to 1,400 | all in section 4b | `liveOpen` KPI: live cases, case columns only (id, stage, owner, age) |
| Flow, heatmap, trend | same rows | 1,400 | same | cells under 5 rows show "-" in the chart but the drawer shows the actual rows |
| Predicted vs actual | reconciled rows | 1,277 | p10, p50, p90, actual, model | overrides excluded from model error: say so in the drawer subtitle |
| Model versions | rows of a version | 100s | same | `model_stats` is computed over ALL tenants today; the drawer must show only the account's rows and say "your rows" (otherwise it contradicts the table or leaks counts). Flag for owner |
| Overrides | rows with an override | tens | + recommended route, carried-out route, reason, estimated delta | `reason` is free text: role-gated by the `overrides` section; synthetic here, but real reasons can name people, so truncate at 200 chars and never export it |
| Engineering heat | rows with `ero` > 0 | 100s | equip, comp, value lost | section `eng` (Engineer role sees only `eng` and `sustain`) |
| Sustainability | rows with CO2e | up to 1,277 | co2e, co2m, route; factor source from `carbon.json` | sample factors, synthetic: Legal review before any reporting use |
| Open decisions by age | live cases `awaiting_approval` | tens | id, route proposed, age, forecast value, owner tenant | `visible_cases`: tenant AND warehouse lock; Warehouse Manager has no analytics page at all |
| Pack headline and Packs KPIs | live cases of the pack (`pack_cases`) | tens to 1,000s | per-pack whitelist (id, received, grade, channel/route, status, days, net, CO2e avoided) | never return the case document: it holds evidence records, partner and supplier fields; whitelist per pack in the rows module |

Access rules the endpoint must repeat (same as the page read): `p.require_page("analytics", section)` per chart, `visible_rows(ctx, tenant_filter)` for decisions,
`visible_cases(ctx, tenant_filter)` for cases, org subtree narrowing (`orgs.subtree`) when an org is picked, and the page's own filters. Planner is tenant-scoped; Engineer sees only
two sections; Warehouse Manager and Developer have none. Do not accept a free-form column or filter name: map `chart` + `key` to a server-side predicate and a fixed column list (no injection, no leak).
Must not be shown: any person's name, email or contact (none is stored in these rows: the device id identifies a device, no person), free-text from evidence records, credentials,
other tenants' counts. Row id shown in full for decisions; for pack devices show the id the pack calls the asset, masked to the last 4 characters in export (open question 5).

## 6. Build plan: two writers, disjoint files

Order: F (section D) merges first. Then G1 and G2 run in parallel on disjoint files; G2's integration commit to `AnalyticsPage.tsx` and `PackView.tsx` comes last, after F.

### Writer G1: backend (about 8 agent-hours)
Files (all new unless noted):
- `backend/di/services/screens/analytics_rows.py`: `rows(session, principal, source, chart, key, filters, sort, dir, q, limit, offset)`; the chart-to-predicate table; column lists (label, kind, unit); totals and the reconciliation sum; the CSV cap. Reads only through `visible_rows`, `visible_cases`, `orgs.subtree`.
- `backend/di/routes/screens/analytics.py` (edit, add one route `GET /api/screens/analytics/rows`, and `.../rows.csv`): `p.require_page("analytics", section)` first.
- `backend/di/schemas/analytics_rows.py`: response model `{title, columns[{key,label,kind}], rows[], total, shown, period, tenants, totals, sum_label, truncated}`.
- `backend/di/services/screens/analytics_open.py`: the open-decisions-by-age read (live cases; value at risk) for chart D.
- `backend/tests/test_analytics_rows.py`: each chart key returns exactly the rows the browser's `drills` would (parity against `fixtures/golden/decisions.json` counts: 1,277 reconciled, 61 pending); the rows sum equals the bar; tenant boundary (Planner of tenant A never sees B); section gate (Engineer gets 403 for `waterfall`); warehouse lock on cases; unknown chart or filter key gives 422; limit cap; sort stability; CSV has only the shown columns.
- Extend the `GET .../analytics/pack` answer only through F's agreed `headline` shape, not before (F owns that file region).
Targeted tests: `bash scripts/dev/api-test.sh tests/test_analytics_rows.py tests/test_screens_analytics.py` (name of the existing analytics screen test file to confirm), then `tests/test_pack_view*.py` if F changed it. No full suite until the gate.

### Writer G2: frontend (about 16 agent-hours)
Files:
- `frontend/src/api/analyticsRows.ts` (+ `analyticsRows.test.ts`): facade for the rows endpoint (pages call only the facade), `rowsQuery` type, CSV link builder. `frontend/src/api/analytics.ts` edit: export the drill keys.
- `frontend/src/pages/analytics/data/DataDrawer.tsx`, `DataTable.tsx`, `dataDrawer.css`, `dataView.ts` (+ `dataView.test.ts`: filter chips, sort, reconciliation text), `DataDrawer.test.tsx` (opens pre-filtered, Esc closes and returns focus, sort sets `aria-sort`, empty state, export hidden when the role lacks the section).
- `frontend/src/pages/analytics/charts/Flow.tsx` (uses `@visx/sankey` layout only), `HeatGrid.tsx`, `TrendBars.tsx`, `AgeBands.tsx`, `charts.css`, with `flowLayout.test.ts` and `chartA11y.test.tsx` (every mark is a button with a label; summary sentence present).
- `frontend/src/pages/analytics/Headline.tsx` (computed sentence and cards; consumes F's `headline` contract).
- `frontend/src/pages/analytics/AnalysisBuilder.tsx` + `analysisBuilder.ts` (+ test): the structured builder and the chip row; saved view through the existing `SavedViews`.
- Edits last: `AnalyticsPage.tsx` (new order, remove the inline `DrillPanel`, wire `View data` buttons), `AnalyticsCharts.tsx` (each chart takes `onViewData`), `PackView.tsx` (open drawer from F's tiles), `package.json` and lockfile (`@visx/sankey` 4.0.0, exact version, after the owner's go).
Targeted tests: `bash scripts/dev/web-check.sh` (typecheck, lint with jsx-a11y, unit), then a browser check by `node frontend/scripts/smoke-pages.mjs` for the `admin`, `planner.a` (tenant scoped) and `engineer` accounts on `#/analytics`, light and dark, 1440 and 390 px. A read-only smoke: open every View data and compare the count in the subtitle with the reconciliation line.

Estimate: G1 8 h, G2 16 h, review and gate fixes 4 h, total about 28 agent-hours, about 2 working days with the two writers in parallel. Cheapest useful cut (6 to 8 h, G2 alone, no backend):
View data on the existing charts over the rows already in the browser, headline sentence, heatmap and trend. Phase 2 (G1 + Flow + ageing + builder) is the rest. Risks: F's changes to `PackView.tsx`
and `AnalyticsPage.tsx` (merge order); the demo-parity decision; the dev api hanging under parallel writers (use private databases for G1's tests).

## 7. Open questions for the owner
1. Parity: may the demo's Analytics page be reordered and extended (new headline, flow, heatmap, trend), with a decision-log entry, or must the Decisions tab stay as is and only the pack headline and View data be new?
2. Pack scope: should the new charts (flow, heatmap, ageing) exist for the industrial Decisions rows only, or also for each pack's cases once F's headline exists for `tool_fleet` and `device`?
3. Export: which roles may export CSV (proposed: only those who already see the rows in the drawer), and should an export be written to the audit journal?
4. The model-versions table is computed over all tenants today; should it be limited to the account's rows (a change from the demo) so the drawer and table agree?
5. Device identifiers and override reasons in the drawer and export: show in full, mask the last 4 characters, or leave out of the export?
