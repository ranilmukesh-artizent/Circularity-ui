# Writer G2: Analytics charts and View data, frontend (plan 11)

Nothing is staged, committed or pushed. All data is synthetic. Net, baseline and forecast are modelled; carbon is estimated from sample
factors. Kinective's Legal team reviews the carbon, export and reporting wording before anyone relies on it.

## What I built, per file

New, all under `frontend/src/`:
- `api/analyticsRows.ts` (+ test): facade for G1's `rows`, `rows.csv`, `open-age` and the `analytics.export` journal action (contract read
  from `g1-rows.md`; names match). `rowsPath`, `fetchRows`, `downloadRowsCsv` (fetches with the sign-in token, saves a file), `useOpenAge`.
- `pages/analytics/data/dataView.ts` (+ test): the one table both sources feed. Facets (removable filters), columns, search, sort, paging,
  totals, the reconciliation sentence, CSV text (no override reason, formula-safe), the server answer mapped to the same table.
  `DataTable.tsx` (sticky header and first column, `aria-sort`, tabular numerals, totals row), `DataDrawer.tsx` (+ test), `dataDrawer.css`.
- `pages/analytics/charts/`: `Flow.tsx` + `flowLayout.ts` (@visx/sankey layout only; marks, colours, labels ours), `HeatGrid.tsx`,
  `TrendBars.tsx`, `AgeBands.tsx`, `chartData.ts` (pure counts, summaries), `specs.ts` (each chart's View data spec), `roving.ts`
  (one tab stop per chart, arrow keys between marks), `useWidth.ts`, `charts.css`; tests `chartData`, `flowLayout`, `ChartA11y`.
- `pages/analytics/Headline.tsx` + `headlineText.ts`, `AnalysisBuilder.tsx` + `analysisModel.ts` (+ tests). The pure modules are not named
  `headline.ts` / `analysisBuilder.ts` because the dev server's mount is case-insensitive and resolved them to the component (the same
  trap writer F hit); the page broke until I renamed them.
- `package.json` / lockfile: `@visx/sankey` `4.0.0` exact, installed in the web container and in host `frontend/node_modules`. (The lockfile
  diff also carries the `react-markdown` / `remark-gfm` entries another writer added.)

Integration (F's report existed, so I did it): `AnalyticsPage.tsx`, `AnalyticsCharts.tsx`, `PackView.tsx`.
- Page order: headline sentence, the four figures (numbers and texts unchanged), F's pack headline, filter strip, waterfall + funnel
  (unchanged), flow (full width), heat grid + trend, route mix, predicted + models, overrides + ageing, engineering + sustainability,
  Build an analysis. The inline drill panel is gone; every panel header has View data; every figure, bar, segment and cell opens the drawer
  (existing charts through a title-chip, new ones with real chips). Pool section removed (it was hidden for every role).
- `AnalyticsCharts.tsx`: waterfall bars and mix segments are now buttons with names, one tab stop per chart (arrows move). Figures,
  labels and texts untouched. `PoolChart` deleted (unused).
- `PackView.tsx`: a View data button on the Packs tab opens the pack's cases (server `pack` chart, modelled net and carbon).

## Decisions worth knowing
- Decisions are counted in the browser (a mark and its rows cannot disagree); live cases (ageing, packs) come from the server. Chips on
  decisions are removable; server chips are fixed.
- Export CSV for decisions: built in the browser from the exact selection on screen, after journalling `analytics.export` (chart name,
  key `all`); if the journal refuses, nothing is exported. Cases use the server's `rows.csv`. A built analysis has no export (the server has
  no chart name to journal it under).
- "Save as a view": the server's saved views accept only registered worked questions (`question_id` must be in `analytics.REGISTRY`), so a
  decisions analysis cannot be saved there. I save it for the person in this browser (localStorage, guarded) and say so on screen.
  Sharing and alerts for analyses need a backend change: `view.save` accepting analysis `params`.
- Page order puts the filter strip below the headline and figures as the brief says, although the filters change them; the headline's own
  meta line shows period and tenants.

## Checks (foreground, last lines)
- `docker compose exec -T web npx tsc --noEmit -p tsconfig.app.json`: no errors in my files. One error in a file I do not own:
  `src/layout/assistant/modes/SetupMode.tsx(108,9) TS2322` (code `"sample"` not in the error code union). Not fixed.
- `docker compose exec -T web npx vitest run src/pages/analytics src/api`: `Test Files  53 passed (53)`, `Tests  393 passed (393)`.
- `docker compose exec -T web npx eslint src/pages/analytics src/api/analyticsRows.ts src/api/analyticsRows.test.ts`: no output (clean,
  jsx-a11y as errors).
- Not run (instructed): api tests, smokes, `reset.sh`. Existing smoke scripts that click a KPI and expect the inline `#drill` panel will
  now open a drawer instead; they need updating by whoever owns them.

## Bundle
`vite build` (4.5 s): the Analytics chunk is 84.25 kB, 25.90 kB gzip, and holds all new code (charts, drawer, builder) plus the sankey layout.
The package alone was not isolated from a build; the brief's esbuild figure for it is 10.7 kB minified, 4.1 kB gzip.

## Screenshots (`...\scratchpad\g2\`, admin, one-time read-only)
- `admin-desk-1-light.png`: the whole Decisions page at 1440 px, in the new order.
- `admin-desk-2-drawer-flow.png`, `admin-desk-3-drawer-band.png`: View data on the flow (all rows, then one band); `admin-desk-4-drawer-age.png`:
  the ageing drawer (caught while the read was still loading); `admin-desk-5-dark.png`, `admin-desk-6-drawer-dark.png`: dark page and drawer.
- `admin-phone-*.png`: the same at 390 px.
- `admin-1440-{flow,heat,trend,age,build}.png`, `admin-1440d-*` (dark), `admin-390-*`: element crops. No horizontal page scroll at 1440 or 390;
  flow, heat and trend scroll inside their own frame on a phone.
- Not done: `planner.a` and `engineer` screenshots, and the final trend/flow labels after my last fixes (code-checked, unit tests pass).

## Against the owner's prototype
Better: every chart is real server data and every figure opens real rows with sort, search, filter chips, totals, a reconciliation line,
paging, a CSV, and Back to the same table; one headline sentence computed from the data; heat cells show the median with its count and a
dash under five; flow, heat, trend and ageing each carry a one-sentence finding, keyboard marks with names, sign and number (not colour
alone), light and dark; roles and tenants enforced; honest modelled/estimated wording.
Behind: no sell-through-by-item table with a best-channel chip per row (our packs do not carry that measure here); no weekly trend (months);
the builder is a form with examples, not free text (the assistant remains the text path); the page is long (about 5,200 px).

## Left or uncertain
- F's pack headline tiles and links do not open the drawer: they live in `HeadlineSection.tsx` (F's file, outside my list). Exact edit:
  give `PackHeadlines` an `onViewData(spec)` prop and open `{source:'cases', chart:'pack', key:'pack:<key>|route:<id>', days}`; the drawer
  already accepts it (`days` is supported).
- The ageing legend shows route names a pack brings (for example `rerent:REQ-1`); they come from the data. Non-reference routes get spare
  colours in server order.
- Error state of the ageing chart reuses `Boundary`'s wording ("This page could not load"), which reads oddly inside a panel.
- Row detail for a live case navigates to `#/product/<id>` (leaving the page); decisions open the existing closed-decision drawer on top,
  and Back returns to the same table.
- The sort of Model-versions rows and the "your rows" note are as G1 specified; the table's counts still cover every tenant (open question 4).
- Decision-log entry for the reorder is still owed (brief open question 1).
