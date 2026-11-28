# H: Analytics close (plan 11)

Nothing staged, committed or pushed. All data is synthetic; net and forecast are modelled, carbon is estimated from sample factors.
Kinective's Legal team reviews the carbon, export and reporting wording before anyone relies on it.

## Per item
1. **Flow labels** (`charts/Flow.tsx`, `charts.css`): the middle column's labels sit on a solid plate (panel colour, hairline border, rounded), name and "count . value" kept; left and right columns were already clear. Legible in light and dark at 1440 px, nothing overlaps; at 390 px the chart scrolls inside its frame (page scrollWidth 375 of 390).
2. **Trend** (`TrendBars.tsx`): the code already held bar values in the foot row under the month names (no labels over the bars or the line), the line has its direct end label and the summary sentence stays. Verified in the screenshot: no collisions. Values sit close together at about 514 px width (for example "238k 215k"); not changed.
3. **Ageing** (`AgeBands.tsx`): renders with data (48 decisions, $152k at risk, bands, route key; drawer shows 48 rows summing to $152,201). Empty state "No decisions are waiting." Loading shows "Loading open decisions..." and after 15 s turns into "This is taking longer than usual. The server may be restarting." with Try again. Error state: "The waiting decisions could not be loaded", the message, "Check that you are still signed in, then try again", and a retry. Own Suspense and error boundary, so the page never waits on it.
4. **Pack headline opens View data** (`HeadlineSection.tsx`, `packHeadline.css`, `AnalyticsPage.tsx`): `PackHeadlines` and `Headline` take `onViewData`; `headlineSpec()` builds `chart=pack`, `key=pack:<pack>|route:<id>|grade:<g>|state:<closed|open>`, `days` = the tile's period, fixed chips (pack, period, route/channel, grade, cases). Figures: net, days, carbon open closed cases; still open/listed opens open cases; the sell-through/reuse figure opens all cases of the period. Each route row (name and count) and each non-zero grade cell is a button with a label ("Grade B on Pre-owned sale: 2 cases. Opens the cases."). Verified: tile click opens drawer "Tool fleet returns: Net recovered", 1 row, $375, sums to $375.
5. **Save in this browser** (`AnalysisBuilder.tsx`): button reads "Save in this browser" / "Saved in this browser", note "Kept on this device only; nobody else sees it and it is not synced.", list heading "Saved in this browser".
6. **Smaller roles**: planner.a (Customer A): 11 View data panels (no eng, sustain), waterfall drawer 563 rows, Customer A only, requests only analytics, pack-headline, open-age. engineer: only Engineering and Sustainability panels, 2 View data buttons; the pack headline was rendered and requested for the engineer (the server read has no section gate), so I render it only when the person sees the waterfall section (`{sections && <PackHeadlines/>}`); engineer now requests only `/api/screens/analytics` (phl 0). Export CSV: decisions are local, shown by section access; server-read drawers by `can_export`.
7. **Decision log**: four rows appended (reorder, View data and `analytics.export`, `@visx/sankey`, pack headline). `AGENTS.md`: one Map row.

## Checks (foreground)
- `docker compose exec -T web npx tsc --noEmit -p tsconfig.app.json`: only `src/layout/assistant/modes/SetupMode.tsx(108,9): error TS2322` ("sample" not in the error code union), not my file, not fixed. (`-p .` has no files; the app config is the real one.)
- `docker compose exec -T web npx vitest run src/pages/analytics src/api`: Test Files 53 passed (53), Tests 393 passed (393).
- `docker compose exec -T web npx eslint src/pages/analytics src/api/analyticsRows.ts src/api/analyticsRows.test.ts`: no output (clean).
- Not run: api tests, smokes, reset.sh.

## Screenshots (`C:\Users\ranilmj\AppData\Local\Temp\claude\780921fb27081449\df3f1b00-d9b3-4212-932e-39cbcbf03b94\scratchpad\h`, read-only, script `hshots.mjs`)
- `admin-desk-{l,d}-flow.png`: flow with plated labels, light and dark. `admin-phone-l-flow.png`: 390 px, scrolls in its frame.
- `admin-desk-{l,d}-trend.png`, `-age.png`, `-heat.png`, `-build.png`, `-pack.png` and `admin-phone-*`: crops of each panel.
- `admin-desk-x-drawer-{flow-band,heat,age,pack}.png`: drawers (flow band, heat cell, ageing, pack tile).
- `planner.a-*`, `engineer-*` (and `engineer2.log` after the fix): whole pages and a drawer at 1440 and 390 px, light and dark.
Against the prototype top of page: the headline sentence, four figures and View data per panel match its intent; not re-compared pixel by pixel.

## Smoke scripts needing an update because the inline drill panel is gone
None found: no script under `frontend/scripts/` mentions `#drill`, a drill panel or the analytics KPI click (grep). `smoke-pages.mjs` only visits the page.

## Left / for the lead
- Backend: `pack-headline` and the `pack` chart of `rows` have no section gate (only the page); the client now hides them from roles without the waterfall section, the server should enforce it.
- Subtitle of the pack drawer says "1 rows" (server text); and the tile "Median days to close: Under 1 day" differs from the drawer's Days column (52.2 days: received to closed); two definitions, F and G1 to align.
- The ageing key lists pack routes by raw id (`rerent:REQ-1`, `retail:LOT-S`); names come from the data.
- Dev database has tool fleet and device cases, so the headline showed and was verified in the browser.
