# Writer F: Analytics headline per pack (plan 11, D1)

Nothing is staged, committed or pushed. Legal: the carbon figures and the "net recovered" wording go to Kinective's Legal team
before anyone relies on them (the factors are the sample set `cfs-2026.2`, synthetic).

## 1. What exists (findings before the design)

1. Analytics is `frontend/src/pages/analytics/AnalyticsPage.tsx` with three tabs: Decisions (the industrial demo: closed decisions,
   waterfall, route mix, model versions), Packs and Back-test. Decisions reads `GET /api/screens/analytics` (`services/screens/analytics.py`
   `page`), which is parity-tested against the golden files. I did not touch that read or its answer.
2. The Packs tab (`PackView.tsx`, `GET /api/screens/analytics/pack`) shows the KPIs and two questions of one chosen pack, computed from
   the pack JSON's `kpis` and `analytics` measures by the grammar in `services/modeler/kpis.py`. It is a pick-a-pack tab, not a headline.
3. Worked questions (`services/questions/used_cars.py`, `telecom_network.py`, `medical_rental.py`, `services/device/analytics.py`) are pure
   functions of typed rows, wrapped in `WorkedQuestion` and registered with `analytics.register`; `device.question` and Ask answer them
   by id, the Packs tab lists them (`PACK_QUESTIONS`). They load canonical-store rows (cars, trade-ins), not cases. D1 needs
   figures over cases, so I used the same shape (pure arithmetic module plus loaders in the screen service) but did not register them
   as worked questions (a headline is not a question with an id).
4. Dev database after `reset.sh`: 128 industrial cases only. Tool fleet and device cases exist only after `reset_starting.py` runs the demo
   seed (`tests/demo_seed.py`): three per pack (one held, one waiting, one closed). I built a private database (`di_f`, from the template
   via `wt-check.sh --prepare-db`), ran the seed there and read the case documents. The main database was never reset by me.
5. What a pack case holds (case document, `case_record.data`): `template`, `stage` (none, awaiting_approval, approved, executing, closed,
   reeval), `grade`, `routes[]` and `recommendation` (one route: `id`, `net`, `co2`, `co2Prov.set`), `chosen` once approved (same
   shape), `qty`, `received`. The pack JSON gives each route its `name` and `classes` (device: sale, parts, recycle, reuse; tool fleet:
   release, refurbish, reuse, sale, parts, recycle/exit) and `grades.scale`.
6. `net` is the valuer's modelled net at decision time; no realised amount is stored anywhere. `co2` is the route's avoided kg from
   `packs/carbon.json` (factor set `cfs-2026.2`, `basis: sample`), computed by the valuer when the case is decided, with its provenance
   on the route (`co2Prov`).
7. Dates: `received` in the seed is inconsistent with the stage log (future dates, and approval dates in October), so I did not use
   it. I used `case_record.created_at` (opened) and the last `case_stage_log` move to `closed`.
8. Tenant and role rules: `visible_cases(ctx)` (tenant boundary, warehouse lock), the same the Packs tab uses; the page needs
   `analytics` (`require_page`).

## 2. Figures, per pack, and what each rests on

All over cases of the pack the caller may see, opened in the last N days (period select: 30, 90, 180, 365; default 90). Every figure
states its count and period ("2 of 3 cases on a sale channel, last 90 days"); modelled and estimated ones are tagged.

| Figure | Tool fleet | Device | From |
|---|---|---|---|
| Net recovered (modelled) | yes | yes | sum of `chosen.net` over closed cases; "expected at approval, not yet reconciled" |
| Rate | Reuse rate: cases whose route class is release, refurbish, reuse or sale, of cases with a route | Sell-through: closed, of cases on a sale-class channel | `chosen` else `recommendation` route, `pack.routes[].classes`, `stage` |
| Days | Median days to close | Median days to sell (sale channels only) | `created_at` to last stage-log move to `closed`, closed cases |
| Open | Still open: every case not closed | Still listed: approved or executing on a sale channel | `stage` |
| Carbon avoided (estimated) | yes | yes | sum of route `co2` over closed cases that carry one; the factor set is named from `co2Prov.set` ("sample factors, synthetic") |

Also: a table of cases, closed share (bar and percent) and modelled net per route or channel; a grade-to-route (channel) table with a
tint by count. Grades come from the pack's scale, then any other grade, then "No grade".

Left out, and why:
- Price realised against forecast, days from return to listing, grading disputes: no case or table stores them for these packs
  (the pack KPIs list them with `measure: null`).
- A realised net: only the modelled net is stored, so the figure is tagged Modelled instead of presented as realised.
- A weekly trend: the seeded cases are minutes apart; a trend would be invented structure. Not built.
- Carbon for a case whose route has no factor: not counted (the figure shows how many of the closed cases carry one).
- Median days to next use (tool fleet) and days to sell measured from receipt: the receipt time is not reliable in the seeded data.

## 3. Changes per file

Backend
- `backend/di/services/questions/headline.py` (new): pure arithmetic (`share`, `median_days`, `carbon_estimate`, `route_table`,
  `grade_table`, `headline`) and `Spec`.
- `backend/di/services/questions/tool_fleet.py`, `device.py` (new): each pack's `Spec` (labels, route classes).
- `backend/di/services/questions/__init__.py`: imports them and adds `HEADLINES`.
- `backend/di/repositories/case_times.py` (new): `times(s, ids)`, opened and closed time of cases (read only, no new table).
- `backend/di/services/screens/analytics.py`: `pack_headlines(session, p, days)` and a docstring entry; existing functions unchanged.
- `backend/di/routes/screens/analytics.py`: `GET /api/screens/analytics/pack-headline?days=` (page `analytics`, `days` 1 to 730).
- `backend/tests/test_analytics_pack_headline.py` (new).

Frontend
- `frontend/src/api/analytics.ts`: added `HeadlineFigure`, `HeadlineRoute`, `HeadlineGrades`, `PackHeadline`, `usePackHeadlines` (nothing existing changed).
- `frontend/src/pages/analytics/headlineFigures.ts` (new, pure view module), `HeadlineSection.tsx` (new), `packHeadline.css` (new),
  `HeadlineSection.test.tsx` (new).
- `frontend/src/pages/analytics/AnalyticsPage.tsx`: two lines, the import and `<PackHeadlines />` on the Decisions tab under the tab
  strip. The section renders nothing when the server returns no pack, and a failed read renders nothing (a quiet boundary), so the
  industrial page is exactly as before for an account with no pack cases.
- File names: the component is `HeadlineSection.tsx`, not `PackHeadline.tsx`. The dev server runs on a case-insensitive mount, and a
  `packHeadline.ts` next to a `PackHeadline.tsx` resolved to the wrong file (the page showed "does not provide an export"); the
  names now differ by more than case.

Design: a ruled row of five figures (not cards; the first is wider), the tag Modelled or Estimated beside the value, one basis line
with count and period, sentence-case labels, tabular numbers via `Intl.NumberFormat`; the route table has a closed and open bar in the
page's ink and grey; the grade table tints cells with the brand yellow (text switches to ink above half strength, contrast held in
both themes); tables sit in the kit's `TableScroll`, so a phone scrolls the table inside its frame, never the page. No new charting
library, no gradient, no all-caps label, no emoji.

## 4. Checks (all run by me)

- `export MSYS_NO_PATHCONV=1; API_TEST_NO_X=1 bash scripts/dev/api-test.sh tests/test_analytics_pack_headline.py tests/test_screens_analytics.py tests/test_device_analytics.py`
  last line: `436 passed, 1 warning in 322.42s (0:05:22)` (the first run of the new file alone had one failure, in the test's own fixture:
  the intake's stage-log row for a closed case was stamped now; the test now removes it. No product change).
- `docker compose exec -T api sh -c "ruff check ...; ruff format --check ...; mypy <my modules>; lint-imports"`: `All checks passed!`,
  `Success: no issues found in 5 source files`, `Contracts: 6 kept, 0 broken.`
- `docker compose exec -T web npx vitest run src/pages/analytics`: `Test Files 13 passed (13)`, `Tests 86 passed (86)` (my file has 8; the folder now also
  holds writer G's tests). One earlier run failed on my own test (a null carbon figure shows no tag); the test was corrected, not the product.
- `docker compose exec -T web npx tsc --noEmit -p .`: exit 0 (no errors, none in files I do not own).
- `docker compose exec -T web npx eslint` on my four frontend files: clean after the test file got a Pascal-case name.
- Not run: the full suite, smokes, `reset.sh` (instructed).

## 5. Screenshots (scratchpad `...\scratchpad\f\`)

The shared api on :8000 hung twice while I worked (as writer G also found), and the main database has no pack cases. So the screenshots
use the dev server on :5173 with real sign-in, and the one request `GET /api/screens/analytics/pack-headline` answered from a file:
`hl.json` is the real answer of a private api (`di_f`, demo seed) for the admin account; `hl-rich.json` is that answer reshaped with
34 device cases and five channels, for layout only (not data).
- `real-1440-light.png`, `real-1100-light.png`, `real-375-light.png`: the real seeded answer (three cases per pack). `real-1440-dark.png`
  was taken before I toggled the app's theme and shows light: use `rich-1440-dark.png`.
- `rich-1440-light.png` (taken before the reload fix, it still shows the real data), `rich-1100-light.png`, `rich-375-light.png`, `rich-1440-dark.png`
  (the reshaped answer: five channels, grades against channels, an empty carbon figure that says what it needs).
No horizontal page scroll at 1440, 1100 or 375 px in any run.

## 6. Left or uncertain

- With the demo seed there are three cases per pack, closed within seconds, so "Under 1 day" and 100% rates appear; a real source gives
  real spans. The headline appears on Decisions for any account that sees such cases, so the demo seed adds it to the admin's Analytics;
  the industrial figures below it are unchanged.
- "Net recovered" is modelled; if the owner wants realised values, the close step must store the acknowledged amount first.
- The grade table counts a case on its approved (else recommended) route, so a recommended-but-open case counts there too.
- The period is by case opening; a long-running case opened before the period is not counted even if it closed inside it.
- Only tool fleet and device (D2, the other eleven packs, is out of scope). `HEADLINES` in `questions/__init__.py` is where a third
  pack would be added with a `Spec`.
- Writer G is editing `AnalyticsPage.tsx` too (View data, charts); my two lines (the import and `<PackHeadlines />`) are in the file now. Their `Headline.tsx`
  and `headline.ts` are different files from my `HeadlineSection.tsx` and `headlineFigures.ts`.
- Cleanup done: my private database `di_f` is dropped and my container `circ-f-api` removed.
